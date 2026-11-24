import asyncio
import json
from contextlib import closing
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ojol.auto_settings import set_auto_flag
from ojol.control import ControlService
from ojol.controller import Controller, StopRequested, VerificationPending
from ojol.finance import completion_evidence, received_income
from ojol.http_api import HttpCoreError
from ojol.journal import Journal
from ojol.models import GameReceipt, Product
from ojol.reconciliation import reconcile, wait_until_resolved
from ojol.telegram import queue_error, queued_text, set_notifications


def claim_states(state):
    before = state.model_copy(
        update={
            "phase": "complete",
            "remaining_seconds": 0,
            "today_income": Decimal(0),
            "trip_id": "fixture-trip",
            "trip": "Antar · 📍 Toko A🏁 Rumah B",
            "buttons": ["✅ Sampai! Terima ongkos"],
            "history": [],
        }
    )
    receipt = GameReceipt(
        id="fixture-trip",
        done_at=before.observed_at + timedelta(seconds=2),
        kind="MAKANAN",
        origin="Toko A",
        destination="Rumah B",
        amount="0.72",
    )
    after = before.model_copy(
        update={
            "observed_at": before.observed_at + timedelta(seconds=3),
            "phase": "idle",
            "remaining_seconds": None,
            "trip_id": None,
            "trip": None,
            "wallet": before.wallet + Decimal("0.72"),
            "today_income": Decimal("0.72"),
            "game_history": [receipt],
            "history": ["08.00 🍱 Toko A → Rumah B · +0,72"],
            "buttons": ["📲 Cari order"],
        }
    )
    return before, after


async def test_timed_out_claim_reconciles_receipt_without_another_post(settings, state):
    before, after = claim_states(state)
    ui = SimpleNamespace(job_click=AsyncMock(), snapshot=AsyncMock(return_value=after))
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.verify = AsyncMock(side_effect=VerificationPending("fixture timeout"))
        await controller.job_action(before, "complete")
        ui.job_click.assert_awaited_once()
        assert not journal.unresolved() and controller.completed == 1
        assert journal.profit()["pendapatan_ojol"] == "0.72"
        await reconcile(ui, journal)
        assert journal.profit()["pendapatan_ojol"] == "0.72"
        assert journal.profit()["trip_tercatat"] == 1
        sync = json.loads((settings.runtime_dir / "game-sync.json").read_text())
        assert sync["snapshot"]["game_history"][0]["id"] == "fixture-trip"


@pytest.mark.parametrize("resource", ["fuel", "condition", "data", "makan"])
@pytest.mark.parametrize("failure", ["verify", "uncertain", "transport"])
async def test_purchase_reconciles_delayed_result_without_another_post(
    settings, state, shop_preview, monkeypatch, resource, failure
):
    set_notifications(settings, True)
    before = state.model_copy(update={"fuel": 36, "condition": 46, "needs": {"makan": 45}})
    product = Product(
        name={
            "fuel": "Isi Pertalite",
            "condition": "Tambal ban",
            "data": "Isi pulsa",
            "makan": "Soto",
        }[resource],
        price="0.5",
        effects={resource: 40},
        row_text="fixture",
        enabled=True,
    )
    shop = shop_preview([product]).model_copy(update={"name": "Akademis.ai Uji"})
    after = before.model_copy(
        update={
            "observed_at": before.observed_at + timedelta(seconds=3),
            "wallet": before.wallet - product.price,
            **(
                {"needs": {resource: 85}}
                if resource == "makan"
                else {resource: before.resource_value(resource) + 40}
            ),
        }
    )
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop]),
        buy=AsyncMock(
            side_effect=HttpCoreError("fixture", category=failure) if failure != "verify" else None
        ),
        snapshot=AsyncMock(side_effect=[before, after, after]),
    )
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.verify = AsyncMock(side_effect=VerificationPending("fixture"))
        assert await controller.purchase(before, resource)
        ui.buy.assert_awaited_once()
        assert controller.state == after
        assert controller.spent == product.price
        assert controller.last_event == "pembelian_terverifikasi"
        assert not journal.unresolved()
        assert journal.history()["actions"][0]["status"] == "verified"
        assert Decimal(journal.profit()["pengeluaran"]) == product.price
        await reconcile(ui, journal)
        assert Decimal(journal.profit()["pengeluaran"]) == product.price
    assert not (settings.runtime_dir / "STOP").exists()
    notices = [
        json.loads(path.read_text())["text"]
        for path in (settings.runtime_dir / "notifications").glob("*.json")
    ]
    assert sum("berhasil diperbarui" in text for text in notices) == 1


async def test_purchase_handoff_preserves_session_budget_without_booking_unproven_cost(
    settings, state, shop_preview, monkeypatch
):
    set_notifications(settings, True)
    settings = settings.model_copy(update={"max_spend": Decimal("0.5")})
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    observed = state.model_copy(update={"observed_at": state.observed_at + timedelta(seconds=301)})
    after = observed.model_copy(update={"observed_at": observed.observed_at + timedelta(seconds=1)})
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop_preview([product])]),
        buy=AsyncMock(),
        snapshot=AsyncMock(side_effect=[observed, after]),
    )
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.verify = AsyncMock(side_effect=VerificationPending("fixture"))
        assert await controller.purchase(state, "data")
        assert journal.history()["actions"][0]["status"] == "handed_off"
        assert not journal.unresolved()
        assert journal.profit()["pengeluaran"] == "0"
        assert controller.spent == product.price
        assert await controller.purchase(controller.state, "data") is False
        ui.buy.assert_awaited_once()
    notices = [
        json.loads(path.read_text())["text"]
        for path in (settings.runtime_dir / "notifications").glob("*.json")
    ]
    assert not any("berhasil diperbarui" in text for text in notices)


async def test_stop_interrupts_purchase_recovery_without_replaying(
    settings, state, shop_preview, monkeypatch
):
    cancel = asyncio.Event()
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop_preview([product])]),
        buy=AsyncMock(),
        snapshot=AsyncMock(return_value=state),
    )

    async def stop(seconds):
        cancel.set()

    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", stop)
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings), cancel)
        controller.verify = AsyncMock(side_effect=VerificationPending("fixture"))
        with pytest.raises(StopRequested):
            await controller.purchase(state, "data")
        ui.buy.assert_awaited_once()
        assert len(journal.unresolved()) == 1
        assert journal.profit()["pengeluaran"] == "0"


@pytest.mark.parametrize("category", ["auth", "schema"])
async def test_purchase_recovery_does_not_swallow_permanent_errors(
    settings, state, shop_preview, category
):
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop_preview([product])]),
        buy=AsyncMock(side_effect=HttpCoreError("fixture", category=category)),
        snapshot=AsyncMock(),
    )
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        with pytest.raises(HttpCoreError) as error:
            await controller.purchase(state, "data")
        assert error.value.category == category
        ui.buy.assert_awaited_once()
        ui.snapshot.assert_not_awaited()
        assert len(journal.unresolved()) == 1


@pytest.mark.parametrize("legacy_snapshot", [False, True])
async def test_old_claim_can_handoff_current_state_without_attributing_income(
    settings, state, monkeypatch, legacy_snapshot
):
    before, after = claim_states(state)
    before = before.model_copy(update={"trip_id": None})
    current = after.model_copy(
        update={
            "observed_at": before.observed_at + timedelta(hours=1),
            "game_history": [],
            "history": [],
            "today_income": Decimal(20),
        }
    )
    ui = SimpleNamespace(
        snapshot=AsyncMock(
            side_effect=[
                current,
                current.model_copy(
                    update={"observed_at": current.observed_at + timedelta(seconds=1)}
                ),
            ]
        ),
    )
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        action = journal.begin(run, "complete", before, {})
        if legacy_snapshot:
            saved = before.model_dump(mode="json", exclude={"trip_id", "game_history"})
            saved["history_done_at"] = []
            with journal.db:
                journal.db.execute(
                    "UPDATE actions SET before_state=? WHERE id=?", (json.dumps(saved), action)
                )
        journal.settle(action, False)
        await reconcile(ui, journal)
        assert journal.history()["actions"][0]["status"] == "handed_off"
        assert journal.profit()["pendapatan_ojol"] == "0"
        assert not journal.unresolved()
        assert journal.start(settings) > run


async def test_pending_claim_waits_automatically_until_receipt_is_visible(
    settings, state, monkeypatch
):
    before, after = claim_states(state)
    first = before.model_copy(update={"observed_at": before.observed_at + timedelta(seconds=1)})
    second = first.model_copy(update={"observed_at": before.observed_at + timedelta(seconds=2)})
    ui = SimpleNamespace(
        snapshot=AsyncMock(side_effect=[first, second, after]),
        check_cancel=lambda: None,
    )
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        action = journal.begin(journal.start(settings), "complete", before, {})
        journal.settle(action, False)
        await wait_until_resolved(ui, journal, settings)
        assert not journal.unresolved()
        assert journal.profit()["trip_tercatat"] == 1
    notices = [
        json.loads(path.read_text())["text"]
        for path in (settings.runtime_dir / "notifications").glob("*.json")
    ]
    assert len(notices) == 2 and any("otomatis" in notice for notice in notices)


async def test_transient_read_failure_retries_without_replaying_claim(settings, state, monkeypatch):
    before, after = claim_states(state)
    ui = SimpleNamespace(
        snapshot=AsyncMock(
            side_effect=[
                HttpCoreError("fixture", category="transport"),
                HttpCoreError("fixture", category="transport"),
                after,
            ]
        ),
        job_click=AsyncMock(),
        check_cancel=lambda: None,
    )
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        journal.begin(journal.start(settings), "complete", before, {})
        await wait_until_resolved(ui, journal, settings)
        assert journal.profit()["pendapatan_ojol"] == "0.72"
        assert not journal.unresolved()
    ui.job_click.assert_not_awaited()
    notices = [
        json.loads(path.read_text())
        for path in (settings.runtime_dir / "notifications").glob("*.json")
    ]
    errors = [notice for notice in notices if notice["context"].get("error_id")]
    assert len(errors) == 1
    assert errors[0]["context"]["error_id"] in errors[0]["text"]
    assert "otomatis setiap 10 detik" in errors[0]["text"]
    assert not (settings.runtime_dir / "STOP").exists()


@pytest.mark.parametrize("stop", [False, True])
async def test_auto_reconcile_keeps_auth_and_stop_errors(settings, monkeypatch, stop):
    ui = SimpleNamespace(
        snapshot=AsyncMock(side_effect=HttpCoreError("fixture auth", category="auth")),
        check_cancel=lambda: None,
    )
    if stop:

        def cancel():
            raise StopRequested("fixture stop")

        ui.check_cancel = cancel
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        with pytest.raises(StopRequested if stop else HttpCoreError):
            await wait_until_resolved(ui, journal, settings)
    assert ui.snapshot.await_count == (0 if stop else 1)


async def test_stop_interrupts_waiting_reconciliation(settings, state, monkeypatch):
    before, _ = claim_states(state)
    observed = before.model_copy(update={"observed_at": before.observed_at + timedelta(seconds=1)})
    confirmed = observed.model_copy(
        update={"observed_at": observed.observed_at + timedelta(seconds=1)}
    )
    checks = iter([None, None, StopRequested("fixture stop")])

    def cancel():
        error = next(checks)
        if error:
            raise error

    ui = SimpleNamespace(snapshot=AsyncMock(side_effect=[observed, confirmed]), check_cancel=cancel)
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        journal.begin(journal.start(settings), "complete", before, {})
        with pytest.raises(StopRequested):
            await wait_until_resolved(ui, journal, settings)
        assert len(journal.unresolved()) == 1
    assert ui.snapshot.await_count == 2


def test_receipt_id_selects_only_claimed_trip_even_if_more_payouts_arrive(state):
    before, after = claim_states(state)
    old = after.game_history[0].model_copy(update={"id": "older-trip"})
    other = after.game_history[0].model_copy(update={"id": "other-trip", "amount": Decimal(2)})
    before = before.model_copy(update={"game_history": [old], "history": ["old payout"]})
    after = after.model_copy(
        update={
            "game_history": [other, *after.game_history, old],
            "history": ["other payout", *after.history, "old payout"],
            "phase": "complete",
            "trip_id": "new-trip",
        }
    )
    assert completion_evidence(before, after)["receipt_id"] == "fixture-trip"
    assert received_income(before, after)[0] == Decimal("0.72")


def test_same_unresolved_trip_cannot_be_handed_off(settings, state):
    before, _ = claim_states(state)
    observed = before.model_copy(update={"observed_at": before.observed_at + timedelta(minutes=1)})
    after = observed.model_copy(update={"observed_at": observed.observed_at + timedelta(seconds=1)})
    with closing(Journal(settings.runtime_dir)) as journal:
        action = journal.begin(journal.start(settings), "complete", before, {})
        assert not journal.handoff_action(action, observed, after)
        assert journal.unresolved()[0]["id"] == action


async def test_live_worker_reconciles_before_creating_next_run(settings, state, monkeypatch):
    import ojol.app as app

    settings = settings.model_copy(update={"env": "local"})
    before, after = claim_states(state)
    with closing(Journal(settings.runtime_dir)) as journal:
        old_run = journal.start(settings)
        action = journal.begin(old_run, "complete", before, {})
        journal.settle(action, False)
    ui = SimpleNamespace(snapshot=AsyncMock(return_value=after))
    context = AsyncMock()
    context.__aenter__.return_value = ui
    monkeypatch.setattr(app, "HttpUI", lambda *args: context)

    async def run(controller, **kwargs):
        assert not controller.journal.unresolved()
        assert controller.run_id > old_run

    monkeypatch.setattr(app.Controller, "run", run)
    await app.run_app(settings, "run", live=True)
    ui.snapshot.assert_awaited_once()
    with closing(Journal(settings.runtime_dir)) as journal:
        assert journal.history()["actions"][0]["status"] == "verified"


def test_status_shows_game_totals_history_limits_and_individual_switches(settings, state):
    _, current = claim_states(state)
    current = current.model_copy(
        update={"today_count": 5, "home_plot": "K40-R01", "village": "desa-utara"}
    )
    with closing(Journal(settings.runtime_dir)) as journal:
        journal.sync_game(current)
        assert journal.profit()["pendapatan_ojol"] == "0"
    set_auto_flag(settings.runtime_dir, "makan", False)
    text = ControlService(settings).status()
    for value in (
        "K40-R01",
        "desa-utara",
        "hari data game • 5",
        "0,72 koin",
        "Toko A → Rumah B",
        "Makan • OFF",
        "Riwayat dicocokkan",
        "Batas belanja",
        "Sesi game",
    ):
        assert value in text


@pytest.mark.parametrize("kind", ["purchase", "take"])
@pytest.mark.parametrize("phase", ["idle", "sleeping", "delivering", "complete"])
async def test_stale_action_hands_off_stable_game_without_booking_or_replay(
    settings, state, monkeypatch, kind, phase, capsys
):
    observed = state.model_copy(
        update={
            "observed_at": state.observed_at + timedelta(minutes=20),
            "phase": phase,
            "wallet": Decimal("31.23"),
            "remaining_seconds": 100 if phase == "delivering" else None,
        }
    )
    after = observed.model_copy(
        update={
            "observed_at": observed.observed_at + timedelta(seconds=1),
            "remaining_seconds": 99 if phase == "delivering" else None,
        }
    )
    ui = SimpleNamespace(
        snapshot=AsyncMock(side_effect=[observed, after]),
        job_click=AsyncMock(),
        buy=AsyncMock(),
        check_cancel=lambda: None,
    )
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        payload = {
            "resource": "data",
            "shop": "Konter uji",
            "product": {"name": "Pulsa", "price": "1"},
        }
        action = journal.begin(journal.start(settings), kind, state, payload)
        journal.settle(action, False)
        assert await wait_until_resolved(ui, journal, settings) == after
        row = journal.history()["actions"][0]
        assert row["status"] == "handed_off" and not journal.unresolved()
        assert row["before_state"] == state.model_dump_json()
        assert journal.profit()["pengeluaran"] == journal.profit()["pendapatan_ojol"] == "0"
        proof = json.loads(
            journal.db.execute(
                "SELECT data FROM events WHERE event='aksi_lama_diserahkan_ke_state_teramati'"
            ).fetchone()[0]
        )
        assert proof["original_outcome"] == "uncertain"
        assert proof["expense_attributed"] is proof["payout_attributed"] is False
        sync = json.loads((settings.runtime_dir / "game-sync.json").read_text())
        assert sync["resolved"] == [action]
        assert sync["reconciliation"][0]["status_after"] == "handed_off"
        assert journal.start(settings) > row["run_id"]
        assert "Hasil transaksi lama tetap belum pasti" in capsys.readouterr().out
    ui.job_click.assert_not_awaited()
    ui.buy.assert_not_awaited()


@pytest.mark.parametrize(
    "change",
    [
        "wallet",
        "fuel",
        "history",
        "needs",
        "trip_id",
        "phase",
        "time",
        "searching",
        "unknown",
        "timer",
    ],
)
def test_stale_handoff_requires_stable_resource_wallet_trip_and_advancing_time(
    settings, state, change
):
    observed = state.model_copy(update={"observed_at": state.observed_at + timedelta(minutes=10)})
    after = observed.model_copy(update={"observed_at": observed.observed_at + timedelta(seconds=1)})
    if change == "time":
        after = observed
    elif change in {"searching", "unknown"}:
        observed = observed.model_copy(update={"phase": change})
        after = after.model_copy(update={"phase": change})
    elif change == "timer":
        observed = observed.model_copy(update={"phase": "delivering", "remaining_seconds": 30})
        after = after.model_copy(update={"phase": "delivering", "remaining_seconds": 40})
    else:
        values = {
            "wallet": Decimal("20"),
            "fuel": 50,
            "history": ["new"],
            "needs": {"makan": 20},
            "trip_id": "new-trip",
            "phase": "complete",
        }
        after = after.model_copy(update={change: values[change]})
    with closing(Journal(settings.runtime_dir)) as journal:
        action = journal.begin(journal.start(settings), "purchase", state, {})
        assert journal.handoff_action(action, observed, after) is None
        assert journal.unresolved()[0]["id"] == action


def test_recent_purchase_still_requires_transaction_evidence(settings, state):
    observed = state.model_copy(update={"observed_at": state.observed_at + timedelta(seconds=300)})
    after = observed.model_copy(update={"observed_at": observed.observed_at + timedelta(seconds=1)})
    with closing(Journal(settings.runtime_dir)) as journal:
        action = journal.begin(journal.start(settings), "purchase", state, {})
        assert journal.handoff_action(action, observed, after) is None
        assert journal.unresolved()[0]["id"] == action


async def test_waiting_status_names_purchase_and_explains_unstable_game(
    settings, state, monkeypatch
):
    import os

    import ojol.control as control

    observed = state.model_copy(update={"observed_at": state.observed_at + timedelta(minutes=10)})
    after = observed.model_copy(
        update={"observed_at": observed.observed_at + timedelta(seconds=1), "fuel": 50}
    )
    ui = SimpleNamespace(snapshot=AsyncMock(side_effect=[observed, after]))
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(control, "running", lambda _: True)
    with closing(Journal(settings.runtime_dir)) as journal:
        action = journal.begin(
            journal.start(settings),
            "purchase",
            state,
            {
                "resource": "fuel",
                "shop": "SPBU uji",
                "product": {"name": "Pertalite", "price": "1"},
            },
        )
        await reconcile(ui, journal)
        (settings.runtime_dir / "status.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "event": "rekonsiliasi_otomatis",
                    "reconciliation_pending": 1,
                    "reconciliation_attempt": 2,
                }
            )
        )
        text = ControlService(settings).status()
        assert f"Aksi #{action}" in text and "Beli Pertalite di SPBU uji" in text
        assert "Field berubah: fuel" in text and "Waktu aksi" in text and "Saldo" in text
        assert "Pemeriksaan otomatis 2/3" in text
        assert "sebelum mulai" not in text


@pytest.mark.parametrize("failures", ["pending", "transport", "mixed"])
async def test_auto_reconcile_fails_after_three_attempts_and_notifies_even_when_muted(
    settings, state, monkeypatch, failures
):
    import ojol.reconciliation as recovery

    set_notifications(settings, False)
    ui = SimpleNamespace(check_cancel=lambda: None, buy=AsyncMock(), job_click=AsyncMock())
    transport_error = HttpCoreError("fixture connection", category="transport")
    results = {
        "pending": [state] * 6,
        "transport": [transport_error] * 6,
        "mixed": [
            transport_error,
            state,
            transport_error,
            transport_error,
            transport_error,
            transport_error,
        ],
    }[failures]
    reconcile_mock = AsyncMock(side_effect=results)
    sleep = AsyncMock()
    monkeypatch.setattr(recovery, "reconcile", reconcile_mock)
    monkeypatch.setattr(recovery.asyncio, "sleep", sleep)
    with closing(Journal(settings.runtime_dir)) as journal:
        action = journal.begin(journal.start(settings), "complete", state, {})
        journal.settle(action, False)
        with pytest.raises(HttpCoreError) as error:
            await wait_until_resolved(ui, journal, settings)
        assert error.value.category == "reconciliation_failed"
        assert reconcile_mock.await_count == 6
        assert (
            sleep.await_count == 300
        )  # Five 60-iteration waits of 0.25s; no wait after the sixth attempt.
        assert journal.unresolved()[0]["id"] == action
        assert journal.profit()["pendapatan_ojol"] == "0"
        assert journal.profit()["pengeluaran"] == "0"
        with pytest.raises(RuntimeError, match="belum terverifikasi"):
            journal.start(settings)
        status = json.loads((settings.runtime_dir / "status.json").read_text())
        assert status["event"] == "gagal"
        assert status["reconciliation_attempt"] == status["reconciliation_limit"] == 6
        # The CLI uses the same error handler for startup and in-session failures.
        notice = queue_error(settings, error.value, "worker.reconcile")
        data = json.loads(notice.read_text())
        assert data["context"]["action_ids"] == [action]
        assert data["context"]["fatal"] is True
        assert "gagal setelah 6 percobaan" in queued_text(data)
        assert "Bot dihentikan" in queued_text(data)
        assert "belum pasti" in queued_text(data)
        assert (settings.runtime_dir / "STOP").exists()
    ui.buy.assert_not_awaited()
    ui.job_click.assert_not_awaited()
    text = ControlService(settings).status()
    assert "gagal setelah 6 percobaan" in text
    assert "menunggu rekonsiliasi" not in text


async def test_auto_reconcile_can_succeed_on_third_attempt(settings, state, monkeypatch):
    import ojol.reconciliation as recovery

    before, after = claim_states(state)
    transient = HttpCoreError("fixture", category="transport")
    with closing(Journal(settings.runtime_dir)) as journal:
        action = journal.begin(journal.start(settings), "complete", before, {})
        attempts = 0

        async def check(ui, current):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return before
            if attempts == 2:
                raise transient
            current.settle(action, True, after)
            return after

        check = AsyncMock(side_effect=check)
        sleep = AsyncMock()
        monkeypatch.setattr(recovery, "reconcile", check)
        monkeypatch.setattr(recovery.asyncio, "sleep", sleep)
        assert (
            await wait_until_resolved(SimpleNamespace(check_cancel=lambda: None), journal, settings)
            == after
        )
        assert check.await_count == 3
        assert sleep.await_count == 120  # Two waits of 60 x 0.25s; no wait after the third attempt.
        assert not journal.unresolved()
        assert journal.profit()["pendapatan_ojol"] == "0.72"
    assert not (settings.runtime_dir / "STOP").exists()
    notices = [
        json.loads(path.read_text())
        for path in (settings.runtime_dir / "notifications").glob("*.json")
    ]
    assert any("Bot melanjutkan" in data["text"] for data in notices)
    assert all(data["context"].get("http_category") != "reconciliation_failed" for data in notices)


async def test_purchase_stops_after_reconciliation_limit_without_replaying_or_booking_cost(
    settings, state, shop_preview, monkeypatch
):
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop_preview([product])]),
        buy=AsyncMock(),
        snapshot=AsyncMock(return_value=state),
    )
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.verify = AsyncMock(side_effect=VerificationPending("fixture"))
        with pytest.raises(HttpCoreError) as error:
            await controller.purchase(state, "data")
        assert error.value.category == "reconciliation_failed"
        ui.buy.assert_awaited_once()
        assert len(journal.unresolved()) == 1
        assert controller.spent == product.price
        assert journal.profit()["pengeluaran"] == "0"
        notices = [
            json.loads(path.read_text())["text"]
            for path in (settings.runtime_dir / "notifications").glob("*.json")
        ]
        assert not any(
            "Bot melanjutkan" in text or "berhasil diperbarui" in text for text in notices
        )


async def test_claim_failure_retries_and_defines_error_after_three_strikes(
    settings, state, monkeypatch
):
    before, _ = claim_states(state)
    # Set auto flag ojol dan kebutuhan agar handle_ojol_failure menguji nonaktifkan ojol
    from ojol.auto_settings import set_auto_flag

    set_auto_flag(settings.runtime_dir, "ojol", True)
    set_auto_flag(settings.runtime_dir, "makan", True)

    ui = SimpleNamespace(
        job_click=AsyncMock(),
        snapshot=AsyncMock(return_value=before),
        check_cancel=lambda: None,
    )
    monkeypatch.setattr("ojol.controller.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("ojol.reconciliation.asyncio.sleep", AsyncMock())

    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.human_pause = AsyncMock()
        controller.verify = AsyncMock(side_effect=VerificationPending("fixture receipt missing"))

        # Percobaan 1: Gagal verifikasi -> diskip di rekonsiliasi, retry count = 1
        await controller.job_action(before, "complete")
        assert controller.completed == 0
        assert controller.claim_failures[before.trip_id] == 1
        assert len(journal.unresolved()) == 0  # Action diskip, tidak tertahan

        # Percobaan 2: Masih gagal -> diskip di rekonsiliasi, retry count = 2
        await controller.job_action(before, "complete")
        assert controller.completed == 0
        assert controller.claim_failures[before.trip_id] == 2
        assert len(journal.unresolved()) == 0

        # Percobaan 3: Gagal ke-3 kali berturut-turut -> definisikan error dan matikan Auto Ojol
        await controller.job_action(before, "complete")
        assert before.trip_id not in controller.claim_failures
        assert len(journal.unresolved()) == 0

        # Verifikasi Auto Ojol dinonaktifkan
        from ojol.auto_settings import auto_flags

        flags = auto_flags(settings.runtime_dir)
        assert flags["ojol"] is False
        assert flags["makan"] is True

        # Verifikasi file last-error.json terisi diagnosis yang jelas
        last_error_path = settings.runtime_dir / "last-error.json"
        assert last_error_path.exists()
        last_error = json.loads(last_error_path.read_text())
        assert "setelah 3 percobaan" in last_error["message"]
        assert "payout/receipt" in last_error["message"]
        assert (
            "solusi" in last_error["tindakan"].lower()
            or "periksa" in last_error["tindakan"].lower()
        )


async def test_run_worker_skips_unresolved_on_reconciliation_failed(settings, state, monkeypatch):
    import ojol.app as app

    settings = settings.model_copy(update={"env": "local"})
    before, after = claim_states(state)
    with closing(Journal(settings.runtime_dir)) as journal:
        old_run = journal.start(settings)
        action = journal.begin(old_run, "complete", before, {})
        journal.settle(action, False)
        assert len(journal.unresolved()) == 1

    ui = SimpleNamespace(
        snapshot=AsyncMock(return_value=after),
        check_cancel=lambda: None,
    )
    monkeypatch.setattr(
        app,
        "wait_until_resolved",
        AsyncMock(
            side_effect=HttpCoreError("Reconciliation failed", category="reconciliation_failed")
        ),
    )
    monkeypatch.setattr(app.Controller, "run", AsyncMock())

    stop_file = settings.runtime_dir / "STOP"
    stop_file.touch()

    cancel = asyncio.Event()
    await app.run_worker(ui, settings, live=True, cancel=cancel)

    assert not stop_file.exists()
    with closing(Journal(settings.runtime_dir)) as journal:
        assert len(journal.unresolved()) == 0
        assert journal.history()["actions"][0]["status"] == "skipped"
