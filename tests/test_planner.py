from decimal import Decimal

import pytest
from pydantic import ValidationError

from ojol.models import Product, Settings, Snapshot
from ojol.planner import best_value_product, decimal_id, next_step, parse_snapshot, select_product


@pytest.mark.parametrize(
    ("text", "expected"), [("0,704", "0.704"), ("1.234,56", "1234.56"), ("100", "100")]
)
def test_indonesian_numbers(text, expected):
    assert decimal_id(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["1e4", "NaN", "1,2,3", "-1", "1.2", "0;alert(1)"])
def test_ambiguous_numbers_rejected(text):
    with pytest.raises(ValueError):
        decimal_id(text)


def test_real_dom_shape_and_countdown():
    raw = {
        "text": "Antar penumpang",
        "wallet": "🪙 35,68 koin",
        "tiles": {"Bensin": "72%", "Kondisi": "97%", "Kuota HP": "46%", "Hasil hari ini": "2,052"},
        "buttons": [{"text": "🛵 Mengantar… 2:14", "disabled": True}],
        "trip": "Antar A → B",
    }
    state = parse_snapshot(raw)
    assert state.remaining_seconds == 134 and state.phase == "delivering"
    assert state.data == 46 and state.today_income == Decimal("2.052")
    raw["buttons"] = [{"text": "✅ Sampai! Terima ongkos", "disabled": False}]
    assert parse_snapshot(raw).phase == "complete"
    raw["buttons"] = [{"text": "⏳ Mencari…", "disabled": True}]
    assert parse_snapshot(raw).phase == "searching"


def test_busy_search_waits_without_duplicate_click(state, settings):
    searching = state.model_copy(update={"phase": "searching", "buttons": ["⏳ Mencari…"]})
    step = next_step(searching, settings)
    assert step.action == "wait" and step.wait_seconds == 2


def test_delivering_waits_before_any_replenishment(state, settings):
    state = state.model_copy(update={"phase": "delivering", "remaining_seconds": 175, "fuel": 1})
    step = next_step(state, settings)
    assert step.action == "wait" and step.wait_seconds == 176


def test_60_percent_is_not_below_threshold(state, settings):
    for resource in ("fuel", "condition", "data"):
        state = state.model_copy(update={resource: 60})
    assert next_step(state, settings).action == "search"
    state = state.model_copy(update={"fuel": 59})
    assert next_step(state, settings).resource == "fuel"


def test_kuota_hp_is_data_not_daily_job_quota(state, settings):
    assert next_step(state, settings).resource == "data"


def product(name, price, resource, gain, enabled=True):
    return Product(name=name, price=price, effects={resource: gain}, row_text=name, enabled=enabled)


def test_economical_data_replenishment(state, settings):
    products = [product("Isi pulsa", "0.5", "data", 40), product("Paket data", "1", "data", 60)]
    plan = select_product(state, "data", products, settings, Decimal(0))
    assert plan.product.name == "Isi pulsa"
    assert plan.projected_percent == 86 and plan.total_cost == Decimal("0.5")


def test_only_motor_fuel_not_solar_or_electric(state, settings):
    state = state.model_copy(update={"fuel": 30})
    products = [
        product("Isi Solar (mobil)", "0.1", "fuel", 80),
        product("Isi Pertalite", "1", "fuel", 60),
        product("Isi Pertamax", "1.5", "fuel", 100),
    ]
    plan = select_product(state, "fuel", products, settings, Decimal(0))
    assert plan.product.name == "Isi Pertalite"


def test_capacity_waste_accounted(state, settings):
    state = state.model_copy(update={"fuel": 59})
    products = [
        product("Isi Pertalite", "1", "fuel", 60),
        product("Isi Pertamax", "1.5", "fuel", 100),
    ]
    assert select_product(state, "fuel", products, settings, Decimal(0)) is None
    assert (
        next_step(state.model_copy(update={"data": 80}), settings, {"fuel": products}).action
        == "search"
    )
    plan = select_product(
        state.model_copy(update={"fuel": 40}), "fuel", products, settings, Decimal(0)
    )
    assert plan.product.name == "Isi Pertalite" and plan.projected_percent == 100


def test_best_nominal_value_stays_within_safe_reserve(settings):
    products = [
        product("Isi Pertalite", "1", "fuel", 60),
        product("Isi Pertamax", "1.5", "fuel", 100),
    ]
    assert best_value_product("fuel", products, settings).name == "Isi Pertalite"


def test_no_purchase_can_overflow(state, settings):
    catalogs = {
        "fuel": [
            product("Isi Pertalite", "1", "fuel", 60),
            product("Isi Pertamax", "1.5", "fuel", 100),
        ],
        "condition": [
            product("Tambal ban", "0.5", "condition", 25),
            product("Servis motor", "1.5", "condition", 60),
        ],
        "data": [product("Isi pulsa", "0.5", "data", 40), product("Paket data", "1", "data", 60)],
    }
    for resource, products in catalogs.items():
        for current in range(60):
            sample = state.model_copy(update={resource: current})
            plan = select_product(sample, resource, products, settings, Decimal(0))
            if plan:
                assert (
                    plan.projected_percent
                    == current + plan.quantity * plan.product.effects[resource]
                )
                assert plan.projected_percent <= 100


def test_workshop_best_value_is_tire_patch(state, settings):
    state = state.model_copy(update={"condition": 59})
    products = [
        product("Tambal ban", "0.5", "condition", 25),
        product("Isi angin", "0.2", "condition", 5),
        product("Ganti oli", "1", "condition", 40),
    ]
    plan = select_product(state, "condition", products, settings, Decimal(0))
    assert plan.product.name == "Tambal ban" and plan.projected_percent == 84


def test_budget_reserve_price_disabled(state, settings):
    settings = settings.model_copy(update={"max_spend": Decimal(10), "min_balance": Decimal(5)})
    products = [product("Isi pulsa", "0.5", "data", 40)]
    assert select_product(state, "data", products, settings, Decimal("9.6")) is None
    poor = state.model_copy(update={"wallet": Decimal("5.5")})
    assert select_product(poor, "data", products, settings, Decimal(0)) is None
    products[0] = products[0].model_copy(update={"enabled": False})
    assert select_product(state, "data", products, settings, Decimal(0)) is None


def test_multi_unit_plan_never_assumes_one_click_sufficient(state, settings):
    state = state.model_copy(update={"data": 5})
    plan = select_product(
        state, "data", [product("Isi pulsa", "0.5", "data", 40)], settings, Decimal(0)
    )
    assert plan.quantity == 2 and plan.total_cost == 1 and plan.projected_percent == 85


def test_unknown_and_invalid_stop(state, settings):
    assert next_step(state.model_copy(update={"phase": "unknown"}), settings).action == "stop"
    with pytest.raises(ValidationError):
        Snapshot(wallet="NaN", fuel=72, condition=97, data=46, phase="idle")
    with pytest.raises(ValidationError):
        Snapshot(wallet=1, fuel=101, condition=97, data=46, phase="idle")
    with pytest.raises(ValidationError):
        Settings(env="testing", operator_authorized=True)
