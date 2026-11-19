"""Tests for automated gym minigame execution (Angkat beban 3x daily)."""

import json
from contextlib import closing
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from ojol.auto_settings import set_auto_flag
from ojol.controller import Controller
from ojol.gym import run_gym
from ojol.journal import Journal
from ojol.models import Product, ShopPreview
from ojol.planner import select_need


def gym_ui(state, plays_left=3):
    ui = AsyncMock()
    ui.prepare_action = lambda kind: {}
    ui.gym_plays_left = AsyncMock(
        side_effect=[plays_left, max(0, plays_left - 1), max(0, plays_left - 2), 0]
    )
    ui.snapshot = AsyncMock(return_value=state)
    return ui


@pytest.mark.asyncio
async def test_gym_disabled_when_flag_false(settings, state):
    set_auto_flag(settings.runtime_dir, "fisik", False)
    ui = gym_ui(state, plays_left=3)
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        assert await run_gym(c) is False
        ui.gym_plays_left.assert_not_awaited()


@pytest.mark.asyncio
async def test_gym_skipped_when_no_plays_left(settings, state):
    set_auto_flag(settings.runtime_dir, "fisik", True)
    ui = AsyncMock()
    ui.gym_plays_left = AsyncMock(return_value=0)
    ui.snapshot = AsyncMock(return_value=state)
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        assert await run_gym(c) is False
        assert c.gym_retry_at > 0


@pytest.mark.asyncio
async def test_gym_executes_3_times_directly(settings, state):
    set_auto_flag(settings.runtime_dir, "fisik", True)
    ui = AsyncMock()
    # Sequence of playsLeft: 3 -> 2 -> 1 -> 0
    ui.gym_plays_left = AsyncMock(side_effect=[3, 2, 1, 0])
    ui.snapshot = AsyncMock(return_value=state)

    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        purchase_calls = []

        async def fake_purchase(st, resource):
            purchase_calls.append(resource)
            return True

        c.purchase = fake_purchase

        assert await run_gym(c) is True
        assert len(purchase_calls) == 3
        assert purchase_calls == ["fisik", "fisik", "fisik"]
        assert c.gym_retry_at > 0


def test_select_need_allows_free_minigame_even_when_fisik_100(settings, state):
    state_full = state.model_copy(update={"needs": {"fisik": 100, "makan": 100}})
    minigame_prod = Product(
        name="Angkat beban",
        price=Decimal(0),
        effects={"fisik": 15},
        row_text=json.dumps(
            {"shop": "gym-1", "item": "minigame", "game": "gym", "resource": "fisik"}
        ),
        enabled=True,
    )
    paid_prod = Product(
        name="Gym desa",
        price=Decimal("1.5"),
        effects={"fisik": 55},
        row_text=json.dumps({"shop": "gym-1", "item": "use", "resource": "fisik"}),
        enabled=True,
    )
    shop = ShopPreview(
        id="gym-1",
        plot_id="gym-1",
        name="Gym desa 2",
        category="fasum",
        distance_squared=0,
        products=[minigame_prod, paid_prod],
    )

    # When fisik is 100, select_need should STILL select "Angkat beban" (free minigame)
    choice = select_need(state_full, "fisik", [shop], settings, Decimal(0), {})
    assert choice is not None
    supplier, plan = choice
    assert supplier.id == "gym-1"
    assert plan.product.name == "Angkat beban"
    assert plan.total_cost == Decimal(0)


def test_select_need_rejects_paid_facilities_when_fisik_high(settings, state):
    state_high = state.model_copy(update={"needs": {"fisik": 80, "makan": 100}})
    paid_prod = Product(
        name="Gym desa",
        price=Decimal("1.5"),
        effects={"fisik": 55},
        row_text=json.dumps({"shop": "gym-1", "item": "use", "resource": "fisik"}),
        enabled=True,
    )
    shop = ShopPreview(
        id="gym-1",
        plot_id="gym-1",
        name="Gym desa 2",
        category="fasum",
        distance_squared=0,
        products=[paid_prod],
    )

    # Without free minigame, paid facility is not selected when fisik >= threshold (30)
    choice = select_need(state_high, "fisik", [shop], settings, Decimal(0), {})
    assert choice is None
