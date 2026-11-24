"""Tests for kebun & kolam (garden & pond) automation, actions, and cooldown tracking."""

import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.modules.gameplay.garden import garden_effective_state, run_garden
from app.modules.ledger.repository import Journal
from app.modules.worker.controller import Controller, StopRequested
from app.modules.worker.settings import auto_flags, set_auto_flag


def garden_ui(state, gardens=None, now_str=None):
    if now_str is None:
        now_str = datetime.now(UTC).isoformat()
    status = {
        "now": now_str,
        "gardens": gardens
        if gardens is not None
        else [
            {
                "id": "garden-1",
                "kind": "kebun-sayur",
                "label": "Kebun sayur",
                "icon": "🥬",
                "state": "siap",
                "readyAt": now_str,
                "cared": False,
                "seedMilli": 300,
                "growHours": 6,
                "yield": 2,
                "caredYield": 3,
                "item": "sayur",
            }
        ],
    }
    ui = AsyncMock()
    ui.prepare_action = lambda kind: {}
    ui.job_click = AsyncMock(side_effect=StopRequested("loop finished"))
    ui.garden_status = AsyncMock(return_value=status)
    ui.garden_action = AsyncMock(return_value={"ok": True})
    ui.snapshot = AsyncMock(return_value=state)
    return ui, status


def test_garden_auto_flags_default_and_toggle(settings):
    assert auto_flags(settings.runtime_dir)["kebun"] is True
    set_auto_flag(settings.runtime_dir, "kebun", False)
    assert auto_flags(settings.runtime_dir)["kebun"] is False
    set_auto_flag(settings.runtime_dir, "kebun", True)
    assert auto_flags(settings.runtime_dir)["kebun"] is True


def test_garden_effective_state_calculation():
    now_dt = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)

    # Empty
    assert garden_effective_state({"state": "kosong"}, now_dt) == "kosong"

    # Explicitly siap
    assert garden_effective_state({"state": "siap"}, now_dt) == "siap"

    # Tumbuh but readyAt has passed
    past_ready = "2026-11-19T11:59:00Z"
    assert garden_effective_state({"state": "tumbuh", "readyAt": past_ready}, now_dt) == "siap"

    # Tumbuh and readyAt is in the future
    future_ready = "2026-11-19T13:00:00Z"
    assert garden_effective_state({"state": "tumbuh", "readyAt": future_ready}, now_dt) == "tumbuh"


@pytest.mark.asyncio
async def test_garden_harvest_when_siap(settings, state):
    ui, _status = garden_ui(state)
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        c = Controller(ui, settings, journal, run)
        c.state = state

        assert await run_garden(c) is True
        ui.garden_action.assert_awaited_once_with("garden-1", "panen")
        assert not journal.unresolved()


@pytest.mark.asyncio
async def test_garden_care_when_growing_and_not_cared(settings, state):
    now_dt = datetime.now(UTC)
    future_ready = (now_dt + timedelta(hours=3)).isoformat()
    gardens = [
        {
            "id": "garden-1",
            "kind": "kebun-sayur",
            "label": "Kebun sayur",
            "icon": "🥬",
            "state": "tumbuh",
            "readyAt": future_ready,
            "cared": False,
            "seedMilli": 300,
        }
    ]
    ui, _status = garden_ui(state, gardens=gardens, now_str=now_dt.isoformat())
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        c = Controller(ui, settings, journal, run)
        c.state = state

        assert await run_garden(c) is True
        ui.garden_action.assert_awaited_once_with("garden-1", "rawat")


@pytest.mark.asyncio
async def test_garden_plant_when_empty_and_sufficient_wallet(settings, state):
    now_dt = datetime.now(UTC)
    gardens = [
        {
            "id": "kolam-1",
            "kind": "kolam-ikan",
            "label": "Kolam ikan",
            "icon": "🐟",
            "state": "kosong",
            "readyAt": None,
            "cared": False,
            "seedMilli": 800,
        }
    ]
    ui, _status = garden_ui(state, gardens=gardens, now_str=now_dt.isoformat())
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        c = Controller(ui, settings, journal, run)
        c.state = state.model_copy(update={"wallet": Decimal(50)})

        assert await run_garden(c) is True
        ui.garden_action.assert_awaited_once_with("kolam-1", "tanam")
        assert c.spent == Decimal("0.8")
        assert Decimal(journal.profit()["pengeluaran"]) == Decimal("0.8")


@pytest.mark.asyncio
async def test_garden_plant_skipped_when_wallet_insufficient(settings, state):
    now_dt = datetime.now(UTC)
    gardens = [
        {
            "id": "kolam-1",
            "kind": "kolam-ikan",
            "label": "Kolam ikan",
            "icon": "🐟",
            "state": "kosong",
            "readyAt": None,
            "cared": False,
            "seedMilli": 800,
        }
    ]
    ui, _status = garden_ui(state, gardens=gardens, now_str=now_dt.isoformat())
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        c = Controller(ui, settings, journal, run)
        # Wallet is exactly 20 (min_balance=20), seed costs 0.8 -> cannot plant
        c.state = state.model_copy(update={"wallet": Decimal(20)})

        assert await run_garden(c) is False
        ui.garden_action.assert_not_awaited()
        # Cooldown fallback is set
        assert c.garden_retry_at > time.monotonic()


@pytest.mark.asyncio
async def test_garden_cooldown_calculation(settings, state):
    now_dt = datetime.now(UTC)
    ready_in_30m = (now_dt + timedelta(minutes=30)).isoformat()
    ready_in_2h = (now_dt + timedelta(hours=2)).isoformat()
    gardens = [
        {
            "id": "garden-1",
            "kind": "kebun-sayur",
            "label": "Kebun sayur",
            "state": "tumbuh",
            "readyAt": ready_in_2h,
            "cared": True,
        },
        {
            "id": "kolam-1",
            "kind": "kolam-ikan",
            "label": "Kolam ikan",
            "state": "tumbuh",
            "readyAt": ready_in_30m,
            "cared": True,
        },
    ]
    ui, _status = garden_ui(state, gardens=gardens, now_str=now_dt.isoformat())
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        c = Controller(ui, settings, journal, run)
        c.state = state

        before = time.monotonic()
        assert await run_garden(c) is False
        ui.garden_action.assert_not_awaited()

        # Cooldown should be around 1800s + 5s = 1805s
        expected_retry = before + 1805
        assert abs(c.garden_retry_at - expected_retry) < 10

        # While in cooldown, running again returns False immediately without calling API
        ui.garden_status.reset_mock()
        assert await run_garden(c) is False
        ui.garden_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_garden_disabled_via_auto_flags(settings, state):
    set_auto_flag(settings.runtime_dir, "kebun", False)
    ui, _status = garden_ui(state)
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        c = Controller(ui, settings, journal, run)
        c.state = state

        assert await run_garden(c) is False
        ui.garden_status.assert_not_awaited()
        ui.garden_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_garden_runs_in_controller_loop_harvest_then_care_then_cooldown(settings, state):
    set_auto_flag(settings.runtime_dir, "ojol", False)
    now_dt = datetime.now(UTC)
    future_ready = (now_dt + timedelta(hours=6)).isoformat()
    garden_obj: dict[str, str | int | None] = {
        "id": "garden-1",
        "kind": "kebun-sayur",
        "label": "Kebun sayur",
        "state": "siap",
        "readyAt": now_dt.isoformat(),
        "cared": False,
        "seedMilli": 300,
    }
    status = {"now": now_dt.isoformat(), "gardens": [garden_obj]}

    ui = AsyncMock()
    ui.prepare_action = lambda kind: {}
    ui.job_click = AsyncMock(side_effect=StopRequested("loop finished"))
    ui.garden_status = AsyncMock(return_value=status)

    async def do_action(gid, action):
        if action == "panen":
            garden_obj["state"] = "kosong"
            garden_obj["readyAt"] = None
        elif action == "tanam":
            garden_obj["state"] = "tumbuh"
            garden_obj["readyAt"] = future_ready
            garden_obj["cared"] = False
        elif action == "rawat":
            garden_obj["cared"] = True
        return {"ok": True}

    ui.garden_action = AsyncMock(side_effect=do_action)

    # Controller snapshots: each action reads snapshot inside run_garden, then next loop reads at top
    after_tanam = state.model_copy(update={"wallet": state.wallet - Decimal("0.3")})
    ui.snapshot = AsyncMock(
        side_effect=[
            state,  # initial top of loop 1 -> panen
            state,  # after panen
            state,  # top of loop 2 -> tanam
            after_tanam,  # after tanam
            after_tanam,  # top of loop 3 -> rawat
            after_tanam,  # after rawat
            after_tanam,  # top of loop 4 -> cooldown computed
            StopRequested("loop finished"),
        ]
    )

    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.wait = AsyncMock(side_effect=StopRequested("loop finished"))
        with pytest.raises(StopRequested, match="loop finished"):
            await c.run()

        # All 3 actions should have been executed in sequence: panen -> tanam -> rawat
        assert [call.args for call in ui.garden_action.await_args_list] == [
            ("garden-1", "panen"),
            ("garden-1", "tanam"),
            ("garden-1", "rawat"),
        ]
        # And after rawat, cooldown should be set based on future_ready (approx 6h = 21600s)
        assert c.garden_retry_at > time.monotonic() + 20000
        assert not journal.unresolved()
