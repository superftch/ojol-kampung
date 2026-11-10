from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ojol.journal import Journal


@pytest.fixture
def sleeping_search(state):
    return state.model_copy(
        update={
            "observed_at": datetime.fromisoformat("2030-01-02T01:10:31+00:00"),
            "phase": "idle",
            "raw_text": "Kamu sedang tidur. Tekan ☀ Bangun dulu.\n📲 Cari order",
            "trip": "Kamu sedang tidur. Tekan ☀ Bangun dulu. | undefined",
            "buttons": ["📲 Cari order", "Berhenti jadi mitra ojol"],
            "today_income": Decimal("3.00"),
        }
    )


@pytest.mark.parametrize("awake", [False, True])
async def test_reconcile_sleep_rejection_before_or_after_waking_never_clicks_or_books_income(
    settings, sleeping_search, monkeypatch, awake
):
    import ojol.app as module

    before = sleeping_search
    after = before.model_copy(
        update={
            "observed_at": before.observed_at + timedelta(minutes=20),
            "phase": "idle" if awake else "sleeping",
            "raw_text": "Narik pakai motor\n📲 Cari order" if awake else before.raw_text,
            "trip": "Narik pakai motor | undefined" if awake else before.trip,
        }
    )
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "search", before, {"label": "📲 Cari order"})
        journal.settle(action, False)
        browser = SimpleNamespace(open_owned_tab=AsyncMock(), call=AsyncMock(), js=AsyncMock())
        context = AsyncMock()
        context.__aenter__.return_value = browser
        monkeypatch.setattr(module, "McpBrowser", lambda *args: context)
        monkeypatch.setattr(module, "ToolContext", lambda ctx: None)
        ui = SimpleNamespace(snapshot=AsyncMock(return_value=after), job_click=AsyncMock())
        monkeypatch.setattr(module, "GameUI", lambda browser: ui)
        agent = module.OjolAutomationAgent(
            name="IsolatedSleepReconcile",
            settings=settings.model_copy(update={"env": "local"}),
            command="reconcile",
        )
        for _ in range(2):
            async for _ in agent._run_async_impl(None):
                pass
        assert journal.history()["actions"][0]["status"] == "rejected"
        assert journal.profit()["trip_tercatat"] == 0
        assert journal.profit()["pengeluaran"] == "0"
        assert journal.start(settings) > run
        assert (
            journal.db.execute(
                "SELECT count(*) FROM events WHERE event='pencarian_ditolak_saat_tidur'"
            ).fetchone()[0]
            == 1
        )
        browser.call.assert_not_awaited()
        browser.js.assert_not_awaited()
        ui.job_click.assert_not_awaited()
    finally:
        journal.close()


@pytest.mark.parametrize(
    "change",
    [
        {"wallet": Decimal("99.00")},
        {"fuel": 1},
        {"condition": 1},
        {"data": 1},
        {"today_income": Decimal("3.72")},
        {"history": ["08.11 New → Route · +0,72"]},
        {"phase": "delivering", "remaining_seconds": 10},
        {"phase": "searching"},
        {"buttons": ["📲 Cari order", "Terima order"]},
        {"buttons": []},
        {"trip": "📍 Toko Contoh 🏁 Rumah Contoh"},
        {"observed_at": datetime.fromisoformat("2030-01-03T01:30:31+00:00")},
    ],
)
def test_sleep_rejection_remains_blocked_with_changed_effects_or_active_order(
    settings, sleeping_search, change
):
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "search", sleeping_search, {"label": "📲 Cari order"})
        journal.settle(action, False)
        after = sleeping_search.model_copy(
            update={
                "phase": "idle",
                "raw_text": "Narik pakai motor",
                "trip": "Narik pakai motor | undefined",
                "observed_at": sleeping_search.observed_at + timedelta(minutes=20),
                **change,
            }
        )
        assert not journal.reject_sleeping_search(action, after)
        assert journal.history()["actions"][0]["status"] == "uncertain"
        with pytest.raises(RuntimeError, match="belum terverifikasi"):
            journal.start(settings)
    finally:
        journal.close()


@pytest.mark.parametrize("kind", ["complete", "purchase", "take", "search"])
def test_sleep_rejection_never_clears_other_kinds_or_an_awake_search(
    settings, sleeping_search, kind
):
    journal = Journal(settings.runtime_dir)
    try:
        before = sleeping_search
        if kind == "search":
            before = before.model_copy(update={"raw_text": "Narik pakai motor"})
        run = journal.start(settings)
        action = journal.begin(run, kind, before, {})
        assert not journal.reject_sleeping_search(action, sleeping_search)
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
        monkeypatch.setattr(module, "McpBrowser", lambda *args: context)
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
