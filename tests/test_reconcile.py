import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ojol.journal import Journal


@pytest.fixture
def search_before(state):
    return state.model_copy(
        update={
            "observed_at": datetime.fromisoformat("2030-01-02T15:12:12+00:00"),
            "phase": "idle",
            "wallet": Decimal("45.09"),
            "fuel": 48,
            "condition": 71,
            "data": 97,
            "today_income": Decimal("26.399"),
            "raw_text": "Narik pakai motor\n📲 Cari order",
            "trip": "undefined | undefined",
            "buttons": ["📲 Cari order", "Berhenti jadi mitra ojol"],
        }
    )


@pytest.mark.parametrize("asleep", [False, True])
@pytest.mark.parametrize("drain", [0, 1])
@pytest.mark.parametrize("unstable", [False, True])
async def test_reconcile_idle_search_records_unknown_resource_deltas_without_replay_or_money(
    settings, search_before, monkeypatch, capsys, asleep, drain, unstable
):
    import ojol.app as module

    before = search_before
    if asleep:
        before = before.model_copy(
            update={
                "raw_text": "Kamu sedang tidur. Tekan ☀ Bangun dulu.",
                "trip": "Kamu sedang tidur. Tekan ☀ Bangun dulu. | undefined",
            }
        )
    after = search_before.model_copy(
        update={
            "observed_at": before.observed_at + timedelta(minutes=26),
            "fuel": before.fuel - drain,
            "data": before.data - drain,
        }
    )
    confirmed = after.model_copy(update={"observed_at": after.observed_at + timedelta(seconds=2)})
    if unstable:
        confirmed = confirmed.model_copy(update={"data": confirmed.data - 1})
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "search", before, {"label": "📲 Cari order"})
        journal.settle(action, False)
        browser = SimpleNamespace(open_owned_tab=AsyncMock(), call=AsyncMock(), js=AsyncMock())
        context = AsyncMock()
        context.__aenter__.return_value = browser
        monkeypatch.setattr(module, "McpBrowser", lambda *args, **kwargs: context)
        monkeypatch.setattr(module, "ToolContext", lambda ctx: None)
        monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
        ui = SimpleNamespace(
            snapshot=AsyncMock(side_effect=[after, confirmed, after, confirmed]),
            job_click=AsyncMock(),
        )
        monkeypatch.setattr(module, "GameUI", lambda browser: ui)
        agent = module.OjolAutomationAgent(
            name="IsolatedSearchReconcile",
            settings=settings.model_copy(update={"env": "local"}),
            command="reconcile",
        )
        for _ in range(2):
            async for _ in agent._run_async_impl(None):
                pass
        row = journal.history()["actions"][0]
        assert row["status"] == ("uncertain" if unstable else "closed_idle")
        assert row["before_state"] == before.model_dump_json()
        assert journal.profit()["trip_tercatat"] == 0
        assert journal.profit()["pengeluaran"] == "0"
        if unstable:
            with pytest.raises(RuntimeError, match="belum terverifikasi"):
                journal.start(settings)
        else:
            assert journal.start(settings) > run
        events = journal.db.execute(
            "SELECT data FROM events WHERE event='pencarian_ditutup_tanpa_order_aktif'"
        ).fetchall()
        assert len(events) == (0 if unstable else 1)
        if events:
            proof = json.loads(events[0]["data"])
            assert proof["resource_delta"] == {"fuel": -drain, "condition": 0, "data": -drain}
            assert proof["resource_delta_cause"] == "not_attributed"
            assert proof["original_outcome"] == "uncertain"
        else:
            line = next(
                line
                for line in capsys.readouterr().out.splitlines()
                if line.startswith("Bukti pencarian: ")
            )
            diagnostic = json.loads(line.removeprefix("Bukti pencarian: "))
            assert not diagnostic["observations_stable"]
            assert not diagnostic["history_changed"]
            assert diagnostic["current"]["data"] == confirmed.data
        ui.snapshot.assert_awaited()
        assert ui.snapshot.await_count == (4 if unstable else 2)
        browser.open_owned_tab.assert_awaited_with(refresh=True)
        browser.call.assert_not_awaited()
        browser.js.assert_not_awaited()
        ui.job_click.assert_not_awaited()
    finally:
        journal.close()


@pytest.mark.parametrize(
    "change",
    [
        {"wallet": Decimal("45.08")},
        {"fuel": 49},
        {"condition": 72},
        {"data": 98},
        {"today_income": Decimal("27.00")},
        {"history": ["22.30 A → B · +0,72"]},
        {"phase": "delivering", "remaining_seconds": 10},
        {"phase": "searching"},
        {"buttons": ["📲 Cari order", "Terima order"]},
        {"buttons": []},
        {"trip": "📍 Toko Contoh 🏁 Rumah Contoh"},
        {"observed_at": datetime.fromisoformat("2030-01-03T15:30:31+00:00")},
    ],
)
def test_idle_search_remains_blocked_with_financial_changes_gains_or_active_orders(
    settings, search_before, change
):
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "search", search_before, {"label": "📲 Cari order"})
        journal.settle(action, False)
        after = search_before.model_copy(
            update={"observed_at": search_before.observed_at + timedelta(minutes=20), **change}
        )
        confirmed = after.model_copy(
            update={"observed_at": after.observed_at + timedelta(seconds=2)}
        )
        assert not journal.resolve_search(action, after, confirmed)
        assert journal.history()["actions"][0]["status"] == "uncertain"
        with pytest.raises(RuntimeError, match="belum terverifikasi"):
            journal.start(settings)
    finally:
        journal.close()


@pytest.mark.parametrize("kind", ["complete", "purchase", "take"])
def test_idle_search_resolution_never_clears_other_action_kinds(settings, search_before, kind):
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, kind, search_before, {})
        after = search_before.model_copy(
            update={"observed_at": search_before.observed_at + timedelta(minutes=20)}
        )
        confirmed = after.model_copy(
            update={"observed_at": after.observed_at + timedelta(seconds=2)}
        )
        assert not journal.resolve_search(action, after, confirmed)
        assert journal.history()["actions"][0]["status"] == "pending"
    finally:
        journal.close()


def test_idle_search_requires_two_distinct_stable_observations(settings, search_before):
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "search", search_before, {})
        after = search_before.model_copy(
            update={"observed_at": search_before.observed_at + timedelta(minutes=20)}
        )
        assert not journal.resolve_search(action, after, after)
        changed = after.model_copy(
            update={"observed_at": after.observed_at + timedelta(seconds=2), "data": 96}
        )
        assert not journal.resolve_search(action, after, changed)
        assert journal.history()["actions"][0]["status"] == "pending"
    finally:
        journal.close()


@pytest.mark.parametrize("age_minutes", [2, 20])
@pytest.mark.parametrize("matching_route", [True, False])
async def test_reconcile_claim_requires_exact_receipt_and_never_replays_or_double_books(
    settings, state, monkeypatch, age_minutes, matching_route
):
    import ojol.app as module

    before = state.model_copy(
        update={
            "observed_at": datetime.fromisoformat("2030-01-02T01:10:31+00:00"),
            "phase": "complete",
            "trip": "Antar · ongkos0,8 | 📍 Toko Contoh🏁 Rumah Contoh",
            "today_income": Decimal("3.00"),
        }
    )
    shop = "Toko Contoh" if matching_route else "Other Shop"
    after = before.model_copy(
        update={
            "observed_at": before.observed_at + timedelta(minutes=age_minutes),
            "phase": "idle",
            "today_income": Decimal("3.72"),
            "history": [f"08.10 🧍 {shop} → Rumah Contoh · +0,72", *before.history],
        }
    )
    monkeypatch.setattr("ojol.models.now", lambda: after.observed_at)
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "complete", before, {"label": "Sampai"})
        journal.settle(action, False)
        browser = SimpleNamespace(open_owned_tab=AsyncMock(), call=AsyncMock(), js=AsyncMock())
        context = AsyncMock()
        context.__aenter__.return_value = browser
        monkeypatch.setattr(module, "McpBrowser", lambda *args, **kwargs: context)
        monkeypatch.setattr(module, "ToolContext", lambda ctx: None)
        ui = SimpleNamespace(snapshot=AsyncMock(return_value=after), job_click=AsyncMock())
        monkeypatch.setattr(module, "GameUI", lambda browser: ui)
        agent = module.OjolAutomationAgent(
            name="IsolatedReconcile",
            settings=settings.model_copy(update={"env": "local"}),
            command="reconcile",
        )
        for _ in range(2):
            async for _ in agent._run_async_impl(None):
                pass
        row = journal.history()["actions"][0]
        assert row["status"] == ("verified" if matching_route else "uncertain")
        browser.open_owned_tab.assert_awaited_with(refresh=True)
        assert journal.profit()["trip_tercatat"] == int(matching_route)
        assert journal.profit()["pendapatan_ojol"] == ("0.72" if matching_route else "0")
        ui.job_click.assert_not_awaited()
        browser.call.assert_not_awaited()
        browser.js.assert_not_awaited()
        if not matching_route:
            with pytest.raises(RuntimeError, match="belum terverifikasi"):
                journal.start(settings)
    finally:
        journal.close()


@pytest.mark.parametrize("phase", ["complete", "delivering", "idle"])
async def test_reconciled_search_hands_off_current_trip_without_claiming_early_or_replaying(
    settings, search_before, monkeypatch, phase
):
    import ojol.app as module
    from ojol.controller import Controller

    buttons = {
        "complete": ["✅ Sampai! Terima ongkos", "📍 Lihat di peta"],
        "delivering": ["🛵 Mengantar… 1:20", "📍 Lihat di peta"],
        "idle": ["Terima order", "📍 Lihat di peta"],
    }
    remaining = {"complete": 0, "delivering": 80, "idle": None}
    ready = search_before.model_copy(
        update={
            "observed_at": search_before.observed_at + timedelta(minutes=36),
            "phase": phase,
            "remaining_seconds": remaining[phase],
            "trip": "Antar penumpang · ongkos 0,8 koin | 📍 Toko Contoh🏁 Rumah Contoh",
            "fuel": 42,
            "condition": 69,
            "data": 92,
            "buttons": buttons[phase],
            "raw_text": "Current observed order",
        }
    )
    confirmed = ready.model_copy(update={"observed_at": ready.observed_at + timedelta(seconds=2)})
    if phase == "delivering":
        confirmed = confirmed.model_copy(
            update={
                "remaining_seconds": 78,
                "buttons": ["🛵 Mengantar… 1:18", "📍 Lihat di peta"],
                "raw_text": "Current order 1:18",
            }
        )
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        search = journal.begin(run, "search", search_before, {"label": "📲 Cari order"})
        journal.settle(search, False)
        browser = SimpleNamespace(open_owned_tab=AsyncMock(), call=AsyncMock(), js=AsyncMock())
        context = AsyncMock()
        context.__aenter__.return_value = browser
        monkeypatch.setattr(module, "McpBrowser", lambda *args, **kwargs: context)
        monkeypatch.setattr(module, "ToolContext", lambda ctx: None)
        monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
        ui = SimpleNamespace(
            snapshot=AsyncMock(side_effect=[ready, confirmed]), job_click=AsyncMock()
        )
        monkeypatch.setattr(module, "GameUI", lambda browser: ui)
        agent = module.OjolAutomationAgent(
            name="IsolatedSearchHandoff",
            settings=settings.model_copy(update={"env": "local"}),
            command="reconcile",
        )
        for _ in range(2):
            async for _ in agent._run_async_impl(None):
                pass
        assert journal.history()["actions"][0]["status"] == "handed_off"
        assert journal.profit()["pendapatan_ojol"] == "0"
        ui.job_click.assert_not_awaited()
        events = journal.db.execute(
            "SELECT data FROM events WHERE event='pencarian_diserahkan_ke_state_teramati'"
        ).fetchall()
        assert len(events) == 1
        evidence = json.loads(events[0]["data"])
        assert evidence["resource_delta"] == {"fuel": -6, "condition": -2, "data": -5}
        resumed = journal.start(settings)
        if phase == "complete":
            paid = confirmed.model_copy(
                update={
                    "phase": "idle",
                    "remaining_seconds": None,
                    "buttons": ["📲 Cari order"],
                    "wallet": confirmed.wallet + Decimal("0.72"),
                    "today_income": confirmed.today_income + Decimal("0.72"),
                    "history": ["22.49 Toko Contoh → Rumah Contoh · +0,72", *confirmed.history],
                }
            )
            ui.snapshot = AsyncMock(return_value=paid)
            controller = Controller(ui, settings, journal, resumed)
            await controller.job_action(confirmed, "complete")
            ui.job_click.assert_awaited_once_with("✅ Sampai! Terima ongkos")
            assert journal.profit()["pendapatan_ojol"] == "0.72"
            assert journal.profit()["trip_tercatat"] == 1
            async for _ in agent._run_async_impl(None):
                pass
            ui.job_click.assert_awaited_once()
            assert journal.profit()["trip_tercatat"] == 1
    finally:
        journal.close()


@pytest.mark.parametrize(
    "change",
    [
        {"trip": "Unknown order"},
        {"buttons": ["✅ Sampai! Terima ongkos", "Selesaikan"]},
        {"buttons": ["✅ Sampai! Terima ongkos", "Terima order"]},
        {"wallet": Decimal("45.81")},
        {"history": ["22.49 Other → Route · +0,72"]},
        {"remaining_seconds": 1},
    ],
)
def test_ready_trip_search_handoff_rejects_ambiguous_or_paid_states(
    settings, search_before, change
):
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "search", search_before, {})
        ready = search_before.model_copy(
            update={
                "observed_at": search_before.observed_at + timedelta(minutes=36),
                "phase": "complete",
                "remaining_seconds": 0,
                "buttons": ["✅ Sampai! Terima ongkos"],
                "trip": "Antar | 📍 Toko Contoh🏁 Rumah Contoh",
                **change,
            }
        )
        confirmed = ready.model_copy(
            update={"observed_at": ready.observed_at + timedelta(seconds=2)}
        )
        assert not journal.resolve_search(action, ready, confirmed)
        assert journal.history()["actions"][0]["status"] == "pending"
        assert journal.profit()["pendapatan_ojol"] == "0"
    finally:
        journal.close()
