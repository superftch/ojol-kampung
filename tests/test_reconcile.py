from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ojol.journal import Journal


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
