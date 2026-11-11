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
from ojol.models import GameReceipt
from ojol.reconciliation import reconcile, wait_until_resolved


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


async def test_old_claim_can_handoff_current_state_without_attributing_income(
    settings, state, monkeypatch
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
        snapshot=AsyncMock(side_effect=[HttpCoreError("fixture", category="transport"), after]),
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
        assert not journal.handoff_complete(action, observed, after)
        assert journal.unresolved()[0]["id"] == action


async def test_live_worker_reconciles_before_creating_next_run(settings, state, monkeypatch):
    import ojol.app as app

    settings = settings.model_copy(update={"env": "local"})
    before, after = claim_states(state)
    with closing(Journal(settings.runtime_dir)) as journal:
        old_run = journal.start(settings)
        action = journal.begin(old_run, "complete", before, {})
        journal.settle(action, False)
    ui = SimpleNamespace(snapshot=AsyncMock(return_value=after), core_name="fixture")
    context = AsyncMock()
    context.__aenter__.return_value = ui
    monkeypatch.setattr(app, "HttpUI", lambda *args: context)
    monkeypatch.setattr(app, "ToolContext", lambda *args: None)

    async def run(controller, **kwargs):
        assert not controller.journal.unresolved()
        assert controller.run_id > old_run

    monkeypatch.setattr(app.Controller, "run", run)
    agent = app.OjolAutomationAgent(name="fixture", settings=settings, command="run", live=True)
    async for _ in agent._run_async_impl(None):
        pass
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
