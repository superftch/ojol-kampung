"""Tests for Smart Dynamic Thresholds per Kebutuhan."""

from decimal import Decimal

from ojol.models import Product, Settings, ShopPreview
from ojol.planner import next_step, select_need


def test_settings_threshold_for_default():
    settings = Settings(threshold=60, smart_thresholds=False)
    assert settings.threshold_for("fuel") == 60
    assert settings.threshold_for("fisik") == 60
    assert settings.threshold_for("makan") == 60


def test_settings_smart_thresholds_optimal():
    settings = Settings(threshold=60, smart_thresholds=True)
    assert settings.threshold_for("fuel") == 30
    assert settings.threshold_for("condition") == 40
    assert settings.threshold_for("data") == 40
    assert settings.threshold_for("fisik") == 45
    assert settings.threshold_for("makan") == 50
    assert settings.threshold_for("kesehatan") == 50
    assert settings.threshold_for("rekreasi") == 50
    assert settings.threshold_for("penampilan") == 50
    assert settings.threshold_for("rumah") == 50


def test_settings_custom_need_thresholds_override():
    settings = Settings(
        threshold=60,
        smart_thresholds=True,
        need_thresholds={"fisik": 42, "fuel": 28},
    )
    assert settings.threshold_for("fisik") == 42
    assert settings.threshold_for("fuel") == 28
    # Fallback to optimal if smart_thresholds is active
    assert settings.threshold_for("makan") == 50


def test_settings_parses_json_string_need_thresholds():
    settings = Settings(
        threshold=60,
        need_thresholds='{"fisik": 40, "fuel": 25}',
    )
    assert settings.need_thresholds == {"fisik": 40, "fuel": 25}
    assert settings.threshold_for("fisik") == 40
    assert settings.threshold_for("fuel") == 25


def test_next_step_uses_smart_threshold_fuel(state):
    # Default without smart thresholds triggers at < 60
    legacy_settings = Settings(threshold=60, smart_thresholds=False)
    state_31 = state.model_copy(update={"fuel": 31, "condition": 90, "data": 90})
    assert next_step(state_31, legacy_settings).resource == "fuel"

    # With smart thresholds, fuel optimal threshold is 30%
    smart_settings = Settings(threshold=60, smart_thresholds=True)
    # At 31%, fuel is safe (waiting for SPKLU +70 capacity)
    assert next_step(state_31, smart_settings).action == "search"

    # At 29%, fuel triggers maintain
    state_29 = state.model_copy(update={"fuel": 29, "condition": 90, "data": 90})
    assert next_step(state_29, smart_settings).resource == "fuel"


def test_select_need_uses_smart_threshold_fisik(settings, state):
    smart_settings = settings.model_copy(update={"smart_thresholds": True})
    paid_gym = Product(
        name="Gym desa",
        price=Decimal("1.5"),
        effects={"fisik": 55},
        row_text='{"shop": "gym-1", "item": "use", "resource": "fisik"}',
        enabled=True,
    )
    shop = ShopPreview(
        id="gym-1",
        plot_id="gym-1",
        name="Gym desa 2",
        category="fasum",
        distance_squared=0,
        products=[paid_gym],
    )

    # At 46% fisik, smart threshold for fisik is 45%, so paid gym is held (avoiding 12h cooldown & overflow)
    state_46 = state.model_copy(update={"needs": {"fisik": 46}})
    assert select_need(state_46, "fisik", [shop], smart_settings, Decimal(0), {}) is None

    # At 44% fisik (< 45%), paid gym triggers and restores to 99% with zero overflow
    state_44 = state.model_copy(update={"needs": {"fisik": 44}})
    choice = select_need(state_44, "fisik", [shop], smart_settings, Decimal(0), {})
    assert choice is not None
    supplier, plan = choice
    assert plan.product.name == "Gym desa"
    assert plan.projected_percent == 99


def test_tiered_balance_prioritizes_ojol_emergency_under_20_coins(settings, state):
    from ojol.planner import select_shop

    spklu = Product(
        name="Isi daya SPKLU (mobil listrik)",
        price=Decimal("0.8"),
        effects={"fuel": 70},
        row_text="spklu",
        enabled=True,
    )
    spklu_shop = ShopPreview(
        id="spklu-1",
        plot_id="spklu-1",
        name="SPKLU",
        category="spklu",
        distance_squared=0,
        products=[spklu],
    )
    nasi = Product(
        name="Nasi bungkus",
        price=Decimal("0.7"),
        effects={"makan": 50},
        row_text='{"item": "nasi"}',
        enabled=True,
    )
    warung = ShopPreview(
        id="warung-1",
        plot_id="warung-1",
        name="Warung akademis.ai",
        category="warung",
        distance_squared=0,
        products=[nasi],
    )
    free_gym = Product(
        name="Angkat beban",
        price=Decimal("0"),
        effects={"fisik": 10},
        row_text='{"item": "minigame"}',
        enabled=True,
    )
    gym_shop = ShopPreview(
        id="gym-1",
        plot_id="gym-1",
        name="Gym",
        category="fasum",
        distance_squared=0,
        products=[free_gym],
    )
    salon = Product(
        name="Potong rambut",
        price=Decimal("2.0"),
        effects={"penampilan": 50},
        row_text='{"item": "salon"}',
        enabled=True,
    )
    salon_shop = ShopPreview(
        id="salon-1",
        plot_id="salon-1",
        name="Salon akademis.ai",
        category="salon",
        distance_squared=0,
        products=[salon],
    )

    # Wallet is 15 coins: in emergency tier (5 <= wallet < 20)
    state_15 = state.model_copy(
        update={
            "wallet": Decimal("15"),
            "fuel": 20,
            "needs": {"makan": 30, "fisik": 30, "penampilan": 30},
        }
    )

    # 1. Ojol emergency package (fuel) is ALLOWED
    fuel_choice, _ = select_shop(state_15, "fuel", [spklu_shop], settings, Decimal(0))
    assert fuel_choice is not None
    assert fuel_choice[1].product.name == "Isi daya SPKLU (mobil listrik)"

    # 2. Vital survival need (makan) is ALLOWED
    makan_choice = select_need(state_15, "makan", [warung], settings, Decimal(0), {})
    assert makan_choice is not None
    assert makan_choice[1].product.name == "Nasi bungkus"

    # 3. Free minigame gym (fisik) is ALLOWED
    fisik_choice = select_need(state_15, "fisik", [gym_shop], settings, Decimal(0), {})
    assert fisik_choice is not None
    assert fisik_choice[1].product.name == "Angkat beban"

    # 4. Secondary paid need (penampilan) is DEFERRED (blocked until 20 coins)
    penampilan_choice = select_need(state_15, "penampilan", [salon_shop], settings, Decimal(0), {})
    assert penampilan_choice is None

    # At 25 coins: secondary need is UNLOCKED and ALLOWED
    state_25 = state.model_copy(
        update={
            "wallet": Decimal("25"),
            "needs": {"penampilan": 30},
        }
    )
    penampilan_25 = select_need(state_25, "penampilan", [salon_shop], settings, Decimal(0), {})
    assert penampilan_25 is not None
    assert penampilan_25[1].product.name == "Potong rambut"

    # At 5.2 coins: emergency package needing 0.8 leaves 4.4 (< 5 min_balance), so it is BLOCKED
    state_poor = state.model_copy(update={"wallet": Decimal("5.2"), "fuel": 20})
    fuel_poor, _ = select_shop(state_poor, "fuel", [spklu_shop], settings, Decimal(0))
    assert fuel_poor is None


def test_food_rotation_after_3_purchases_falls_back_to_next_worth_it(settings, state):
    mi_instan = Product(
        name="Mi instan",
        price=Decimal("0.4"),
        effects={"makan": 24},
        row_text='{"item": "mi-instan"}',
        enabled=True,
    )
    nasi_goreng = Product(
        name="Nasi goreng",
        price=Decimal("1.5"),
        effects={"makan": 63},
        row_text='{"item": "nasi-goreng"}',
        enabled=True,
    )
    soto = Product(
        name="Soto",
        price=Decimal("1.5"),
        effects={"makan": 63},
        row_text='{"item": "soto"}',
        enabled=True,
    )
    shop = ShopPreview(
        id="resto-1",
        plot_id="resto-1",
        name="Akademis.ai Kuliner",
        category="restoran",
        distance_squared=0,
        products=[mi_instan, nasi_goreng, soto],
    )

    state_hungry = state.model_copy(update={"wallet": Decimal("25"), "needs": {"makan": 20}})

    # 1. Streak 0 to 2: Mi instan (cheapest 0.0167 koin/poin) is chosen
    choice_0 = select_need(
        state_hungry,
        "makan",
        [shop],
        settings,
        Decimal(0),
        {},
        streak_product="Mi instan",
        streak_count=0,
    )
    assert choice_0[1].product.name == "Mi instan"

    choice_2 = select_need(
        state_hungry,
        "makan",
        [shop],
        settings,
        Decimal(0),
        {},
        streak_product="Mi instan",
        streak_count=2,
    )
    assert choice_2[1].product.name == "Mi instan"

    # 2. Streak 3 (max 3 reached): Mi instan is rotated out, falls back to next worth-it food (Nasi goreng/Soto)
    choice_3 = select_need(
        state_hungry,
        "makan",
        [shop],
        settings,
        Decimal(0),
        {},
        streak_product="Mi instan",
        streak_count=3,
    )
    assert choice_3[1].product.name in {"Nasi goreng", "Soto"}

    # 3. Direct game "bosan" flag also rotates to fallback
    bored_mi = Product(
        name="Mi instan",
        price=Decimal("0.4"),
        effects={"makan": 24},
        row_text='{"item": "mi-instan", "bosan": true}',
        enabled=True,
    )
    bored_shop = ShopPreview(
        id="resto-1",
        plot_id="resto-1",
        name="Akademis.ai Kuliner",
        category="restoran",
        distance_squared=0,
        products=[bored_mi, nasi_goreng, soto],
    )
    choice_bored = select_need(state_hungry, "makan", [bored_shop], settings, Decimal(0), {})
    assert choice_bored[1].product.name in {"Nasi goreng", "Soto"}


def test_select_shop_fills_multiple_units_up_to_capacity_without_overflow(settings, state):
    from ojol.planner import select_shop

    tambal = Product(
        name="Tambal ban",
        price=Decimal("0.5"),
        effects={"condition": 25},
        row_text="tambal",
        enabled=True,
    )
    bengkel = ShopPreview(
        id="bengkel-1",
        plot_id="bengkel-1",
        name="Akademis.ai Motor",
        category="bengkel-motor",
        distance_squared=0,
        products=[tambal],
    )

    # Condition at 10%, threshold at 70%:
    # 3 units of Tambal ban needed to reach 70%, giving +75 condition up to 85%!
    # Cost = 3 * 0.5 = 1.5 coins, giving exactly +75 condition!
    test_settings = settings.model_copy(update={"threshold": 70, "smart_thresholds": False})
    state_10 = state.model_copy(update={"wallet": Decimal("25"), "condition": 10})
    choice, _ = select_shop(state_10, "condition", [bengkel], test_settings, Decimal(0))
    assert choice is not None
    _, plan = choice
    assert plan.product.name == "Tambal ban"
    assert plan.quantity == 3
    assert plan.total_cost == Decimal("1.5")
    assert plan.projected_percent == 85
