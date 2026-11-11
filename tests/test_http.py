import json
from contextlib import closing
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from ojol.auto_settings import set_auto_flag
from ojol.cleanup import scan
from ojol.control import ControlService
from ojol.controller import Controller, StopRequested
from ojol.healing import write_private
from ojol.http_api import CATEGORIES, ITEMS, ORIGIN, HttpCoreError, OjolHttpApi, extract_effects
from ojol.http_core import HTTP_TOOLS, HttpUI
from ojol.journal import Journal
from ojol.models import ShopPreview
from ojol.planner import select_need, select_shop
from ojol.shop_locations import NeedShop, ShopLocation

SHOP = "00000000-0000-4000-8000-000000000001"


async def test_cleanup_scan_uses_get_and_ranks_dirty_houses(settings):
    paths = []
    home = {"plotId": "K39-R01", "block": "K39", "x": 0, "y": 0}
    house = {"k": "R", "s": "O", "kt": 1, "y": 0}
    plots = [
        {**house, "id": "K39-R01", "x": 0},
        {**house, "id": "K39-R04", "x": 8},
        {**house, "id": "K39-R03", "x": 2},
        {**house, "id": "K39-R05", "x": 1, "kt": 0},
        {**house, "id": "K39-R06", "x": 1, "e": True},
    ]

    def handle(request):
        assert request.method == "GET"
        paths.append(request.url.raw_path)
        return httpx.Response(200, json={"home": home} if len(paths) == 1 else {"plots": plots})

    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        result = await scan(OjolHttpApi(settings.runtime_dir, client=client), None, 1)
    assert paths == [b"/api/game/me", b"/api/world/plots?v=2&blocks=K39"]
    assert result == {
        "blocks": ["K39"],
        "total_candidates": 2,
        "candidates": [{"plot_id": "K39-R03", "x": 2, "y": 0}],
    }


async def test_cleanup_scan_can_pick_from_neighbor_when_home_block_is_empty(settings):
    house = {"id": "L40-R01", "k": "R", "s": "O", "kt": 1, "x": 4, "y": 2}

    def handle(request):
        assert request.method == "GET"
        if request.url.path == "/api/game/me":
            return httpx.Response(200, json={"home": {"block": "K40", "x": 0, "y": 0}})
        assert request.url.params["blocks"].split(",") == [
            "K40",
            "J39",
            "J40",
            "J41",
            "K39",
            "K41",
            "L39",
            "L40",
            "L41",
        ]
        return httpx.Response(200, json={"plots": [house]})

    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        result = await scan(
            OjolHttpApi(settings.runtime_dir, client=client), None, None, include_neighbors=True
        )
    assert result["candidates"] == [{"plot_id": "L40-R01", "x": 4, "y": 2}]


EFFECTS = {
    "isi-pertalite": {"bensin": 60},
    "isi-pertamax": {"bensin": 100},
    "servis-motor": {"kendaraan": 60},
    "ganti-oli": {"kendaraan": 40},
    "tambal-ban": {"kendaraan": 25},
    "isi-angin": {"kendaraan": 5},
    "cuci-motor": {"kendaraan": 15, "penampilan": 5},
    "pulsa": {"kuota": 40},
    "paket-data": {"kuota": 60},
    "servis-hp": {"kuota": 30},
    "casing-hp": {"kuota": 10, "penampilan": 5},
}


@pytest.fixture
def world():
    world = {
        "ojol": {
            "enabled": True,
            "mitra": True,
            "trip": None,
            "problem": None,
            "vehicle": "motor",
            "earnedTodayMilli": 1000,
            "bars": {"bensin": 40, "kendaraan": 70, "kuota": 50},
            "history": [],
        },
        "me": {
            "balanceMilli": 35000,
            "configVersion": "fixture-v1",
            "home": {"desa": "fixture-desa", "x": 0, "y": 0},
        },
        "needs": {"asleep": False},
        "need_locations": {},
        "need_fallback": {},
        "plot_details": {},
        "need_effects": {},
        "facilities": {},
        "time": {"now": "2030-01-02T10:00:00Z"},
        "shop": {
            "mine": False,
            "open": True,
            "plang": "Konter fixture",
            "menu": [
                {"item": "pulsa", "name": "Isi pulsa", "priceMilli": 500, "service": True},
                {"item": "paket-data", "name": "Paket data", "priceMilli": 1000, "service": True},
            ],
        },
    }

    world["locations"] = {"data": [ShopLocation(SHOP, "K22-U07", "Konter fixture", 0, 0)]}
    world["shops"] = {SHOP: world["shop"]}
    world["failed_paths"] = set()
    world["conflicting_catalogs"] = {}
    return world


def add_shop(world, number, name, category, item, product_name, price_milli, **catalog_fields):
    shop_id = f"00000000-0000-4000-8000-{number:012}"
    plot_id = f"K22-U{number:02}"
    resource = next(resource for resource, value in CATEGORIES.items() if value == category)
    world["locations"].setdefault(resource, []).append(
        ShopLocation(shop_id, plot_id, name, number, 0)
    )
    world["shops"][shop_id] = {
        "mine": False,
        "open": True,
        "plang": name,
        "menu": [{"item": item, "name": product_name, "priceMilli": price_milli}],
        **catalog_fields,
    }
    return shop_id


@pytest.fixture
async def api(settings, world, monkeypatch):
    calls = []
    monkeypatch.setattr("ojol.http_api.SHOPS_BY_VILLAGE", {"fixture-desa": world["locations"]})
    monkeypatch.setattr(
        "ojol.http_api.NEED_SHOPS_BY_VILLAGE", {"fixture-desa": world["need_locations"]}
    )
    monkeypatch.setattr(
        "ojol.http_api.NEED_FALLBACK_PLOTS", {"fixture-desa": world["need_fallback"]}
    )

    def handle(request):
        calls.append(request)
        assert request.url.host == "www.kampungsebelah.com"
        path = request.url.path
        if path in world["failed_paths"]:
            return httpx.Response(404)
        if request.method == "POST":
            if path == world.get("lost_response"):
                raise httpx.ReadTimeout("fixture response lost", request=request)
            return httpx.Response(200, json={"ok": True})
        if path in world["conflicting_catalogs"]:
            return httpx.Response(409, json=world["conflicting_catalogs"][path])
        data = {
            "/api/ojol": world["ojol"],
            "/api/game/me": world["me"],
            "/api/kebutuhan": world["needs"],
            "/api/time": world["time"],
            **{"/api/shops/" + key: value for key, value in world["shops"].items()},
            **{"/api/facilities/" + key: value for key, value in world["facilities"].items()},
            **{"/api/world/plots/" + key: value for key, value in world["plot_details"].items()},
        }
        if path == "/kampung":
            return httpx.Response(
                200, text='<script src="/_next/static/chunks/fixture.js"></script>'
            )
        if path == "/_next/static/chunks/fixture.js":
            return httpx.Response(
                200,
                text=json.dumps(
                    {"barang": {**EFFECTS, **world["need_effects"]}}, separators=(",", ":")
                ),
            )
        assert path in data, path
        return httpx.Response(200, json=data[path])

    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        instance = OjolHttpApi(settings.runtime_dir, client=client)
        instance.calls = calls
        async with instance:
            yield instance


def trip():
    return {
        "id": "trip-fixture",
        "kind": "PENUMPANG",
        "vehicle": "motor",
        "distance": 20,
        "fareMilli": 800,
        "from": {"label": "Toko A"},
        "to": {"label": "Toko B"},
        "startAt": "2030-01-02T09:56:00Z",
        "arriveAt": "2030-01-02T10:00:00.001Z",
        "arrived": True,
    }


async def test_snapshot_keeps_receipt_ids_game_totals_and_home(api, world):
    receipt = {**trip(), "doneAt": "2030-01-02T09:59:00Z", "netMilli": 720}
    world["ojol"].update(history=[receipt, receipt], todayCount=5)
    world["me"]["home"]["plotId"] = "K40-R01"
    state = await api.snapshot()
    assert state.today_count == 5 and state.home_plot == "K40-R01"
    assert state.village == "fixture-desa"
    assert len(state.game_history) == len(state.history) == 1
    assert state.game_history[0].id == "trip-fixture"
    assert state.game_history[0].amount == Decimal("0.72")
    world["ojol"]["history"][1] = {**receipt, "netMilli": 800}
    with pytest.raises(HttpCoreError, match="ID sama"):
        await api.snapshot()


async def test_snapshot_exact_coins_sleep_and_server_countdown(api, world):
    world["ojol"]["trip"] = trip()
    state = await api.snapshot()
    assert state.trip_id == "trip-fixture"
    assert state.arrive_at.isoformat() == "2030-01-02T10:00:00.001000+00:00"
    assert (
        state.wallet == Decimal("35")
        and state.phase == "delivering"
        and state.remaining_seconds == 1
    )
    # API's arrived flag cannot claim earlier than the server timestamp.
    with pytest.raises(HttpCoreError, match="waktu server"):
        await api.job_action("complete")
    assert all(request.method == "GET" for request in api.calls)
    world["time"]["now"] = "2030-01-02T10:00:01Z"
    assert (await api.snapshot()).phase == "complete"
    await api.job_action("complete")
    assert json.loads(api.calls[-1].content) == {"action": "selesai"}
    world["needs"]["asleep"] = True
    assert (await api.snapshot()).phase == "sleeping"


async def test_auto_ojol_off_rejects_new_orders_and_allows_existing_trip_claim(api, world):
    set_auto_flag(api.directory, "ojol", False)
    with pytest.raises(HttpCoreError) as error:
        await api.job_action("search")
    assert error.value.category == "auto_disabled"
    assert all(request.method == "GET" for request in api.calls)
    world["ojol"]["trip"] = trip()
    world["time"]["now"] = "2030-01-02T10:00:01Z"
    await api.job_action("complete")
    posts = [request for request in api.calls if request.method == "POST"]
    assert [json.loads(request.content) for request in posts] == [{"action": "selesai"}]


@pytest.mark.parametrize("kind", ["search", "complete"])
async def test_sleep_before_job_action_sends_no_post(api, world, kind):
    world["needs"]["asleep"] = True
    if kind == "complete":
        world["ojol"]["trip"] = trip()
        world["time"]["now"] = "2030-01-02T10:00:01Z"
    with pytest.raises(HttpCoreError) as error:
        await api.job_action(kind)
    assert error.value.category == "sleeping"
    assert all(request.method == "GET" for request in api.calls)


@pytest.mark.parametrize(
    "asleep,resting", [(True, False), (False, True), (True, True), (False, False)]
)
async def test_sleep_status_uses_both_game_sources_and_preserves_manual_wake(
    api, world, asleep, resting
):
    world["needs"]["asleep"] = asleep
    world["me"]["profile"] = {
        "resting": resting,
        "sleep": {"auto": True, "from": 1395, "to": 405, "inSchedule": True},
    }
    state = await api.snapshot()
    assert state.phase == ("sleeping" if asleep or resting else "idle")
    assert state.sleep_schedule.start == 1395
    assert state.sleep_schedule.end == 405
    assert state.sleep_schedule.auto is True
    assert state.sleep_schedule.in_schedule is True


@pytest.mark.parametrize(
    "field,value",
    [("from", -1), ("to", 1440), ("from", True), ("auto", "false"), ("inSchedule", None)],
)
async def test_invalid_sleep_schedule_cannot_allow_job_post(api, world, field, value):
    schedule = {"auto": True, "from": 1320, "to": 300, "inSchedule": False, field: value}
    world["me"]["profile"] = {"resting": False, "sleep": schedule}
    with pytest.raises(ValidationError):
        await api.job_action("search")
    assert all(request.method == "GET" for request in api.calls)


async def test_sleep_during_purchase_preflight_waits_without_post_or_uncertain_ledger(
    api, world, settings
):
    ui = HttpUI(settings)

    async def call(name, **args):
        if name == "ojol_snapshot":
            return (await api.snapshot()).model_dump(mode="json")
        if name == "ojol_preview_shop":
            return await api.preview(**args)
        if name == "ojol_purchase":
            world["needs"]["asleep"] = True
            return await api.purchase(**args)
        pytest.fail(name)

    ui.call_tool = call
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))

        async def wake(seconds):
            assert all(request.method == "GET" for request in api.calls)
            assert journal.history()["actions"][0]["status"] == "rejected"
            world["needs"]["asleep"] = False

        controller.wait = AsyncMock(side_effect=wake)
        assert await controller.purchase(await ui.snapshot(), "data") is False
        controller.wait.assert_awaited_once()
        assert controller.state.phase == "idle"
        assert not journal.unresolved() and controller.spent == 0
        assert all(request.method == "GET" for request in api.calls)


async def test_needs_snapshot_works_without_active_ojol_membership(api, world):
    set_auto_flag(api.directory, "ojol", False)
    world["ojol"] = {"enabled": True, "mitra": False}
    world["needs"].update(enabled=True, needs=[{"id": "makan", "value": 33}])
    state = await api.snapshot()
    assert state.phase == "idle" and state.needs == {"makan": 33}


def setup_food_catalog(world):
    world["needs"].update(
        enabled=True,
        needs=[{"id": "makan", "value": 55}, {"id": "bensin", "value": 3}],
    )
    world["need_effects"].update(
        {
            "nasi-goreng": {"makan": 35},
            "ayam-bakar": {"makan": 40},
            "soto": {"makan": 35},
            "roti-bakar": {"makan": 20},
        }
    )
    world["need_locations"]["makan"] = [
        NeedShop(SHOP, "K22-U07", "Akademis.ai Restaurant", "restoran")
    ]
    world["shop"].update(
        plang="Akademis.ai Restaurant",
        menu=[
            {"item": "nasi-goreng", "name": "Nasi goreng", "priceMilli": 900},
            {"item": "ayam-bakar", "name": "Ayam bakar", "priceMilli": 500, "habis": "ayam"},
            {"item": "soto", "name": "Soto", "priceMilli": 700},
            {"item": "roti-bakar", "name": "Roti bakar", "priceMilli": 500},
        ],
    )


async def test_worker_buys_best_value_for_food_then_returns_to_ojol(api, world, settings):
    setup_food_catalog(world)
    world["ojol"]["bars"].update(bensin=80, kuota=85)
    ui = HttpUI(settings)

    async def call(name, **args):
        if name == "ojol_snapshot":
            return (await api.snapshot()).model_dump(mode="json")
        if name == "ojol_preview_shop":
            assert args["resource"] == "makan"
            return await api.preview(args["resource"])
        if name == "ojol_purchase":
            assert args["product"]["name"] == "Soto"
            await api.purchase(**args)
            world["me"]["balanceMilli"] -= 700
            world["needs"]["needs"][0]["value"] = 90
            return {"accepted": True}
        assert name == "ojol_job_action" and args["kind"] == "search"
        await api.job_action(args["kind"])
        world["ojol"]["trip"] = trip()
        return {"accepted": True}

    ui.call_tool = call
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.wait = AsyncMock(side_effect=StopRequested("selesai fixture"))
        with pytest.raises(StopRequested):
            await controller.run()
        rows = journal.history()["actions"]
        assert [(row["kind"], row["status"]) for row in rows] == [
            ("search", "verified"),
            ("purchase", "verified"),
        ]
        assert journal.profit()["biaya_per_kategori"] == {"makan": "0.7"}
        assert controller.state.needs == {"makan": 90}
    posts = [request for request in api.calls if request.method == "POST"]
    assert [request.url.path for request in posts] == [f"/api/shops/{SHOP}/buy", "/api/ojol"]
    assert json.loads(posts[0].content)["item"] == "soto"


async def test_need_disabled_during_preflight_never_posts(api, world, settings, monkeypatch):
    setup_food_catalog(world)
    before = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    _, plan = select_need(before, "makan", shops, settings, Decimal(0), {})
    validate = api.validate_purchase

    async def validate_and_disable(*args):
        await validate(*args)
        set_auto_flag(api.directory, "makan", False)

    monkeypatch.setattr(api, "validate_purchase", validate_and_disable)
    with pytest.raises(HttpCoreError) as error:
        await api.purchase(plan.product.model_dump(mode="json"), "35", 55, "20", str(uuid4()))
    assert error.value.category == "auto_disabled"
    assert all(request.method == "GET" for request in api.calls)


async def test_need_value_prefers_item_that_fills_multiple_needs_within_budget(
    api, world, settings
):
    setup_food_catalog(world)
    world["needs"]["needs"].extend(
        [{"id": "kesehatan", "value": 58}, {"id": "rekreasi", "value": 55}]
    )
    world["need_effects"]["wedang-jahe"] = {"makan": 5, "kesehatan": 3, "rekreasi": 5}
    world["shop"]["menu"].append({"item": "wedang-jahe", "name": "Wedang jahe", "priceMilli": 900})
    before = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    _, plan = select_need(before, "makan", shops, settings, Decimal(0), {})
    assert plan.product.name == "Wedang jahe"

    limited = settings.model_copy(update={"max_spend": Decimal("0.7")})
    _, plan = select_need(before, "makan", shops, limited, Decimal(0), {})
    assert plan.product.name == "Soto"


@pytest.mark.parametrize("change", ["stock", "balance", "brand", "missing_catalog", "sleeping"])
async def test_need_purchase_rechecks_catalog_and_wallet_before_post(api, world, settings, change):
    setup_food_catalog(world)
    before = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    _, plan = select_need(before, "makan", shops, settings, Decimal(0), {})
    if change == "stock":
        world["shop"]["menu"][2]["habis"] = "bahan"
    elif change == "balance":
        world["me"]["balanceMilli"] -= 1000
    elif change == "brand":
        world["shop"]["plang"] = "Toko baru"
    elif change == "sleeping":
        world["needs"]["asleep"] = True
    else:
        world["failed_paths"].add(f"/api/shops/{SHOP}")
    with pytest.raises(HttpCoreError) as error:
        await api.purchase(plan.product.model_dump(mode="json"), "35", 55, "20", str(uuid4()))
    assert error.value.category == ("sleeping" if change == "sleeping" else "rejected")
    assert all(request.method == "GET" for request in api.calls)


def add_food_supplier(world, name, price, *, fallback=False):
    shop_id = str(uuid4())
    plot = "K22-U09" if fallback else "K22-U08"
    category = "restoran"
    world["shops"][shop_id] = {
        "mine": False,
        "open": True,
        "plang": name,
        "menu": [{"item": "soto", "name": "Soto", "priceMilli": price}],
    }
    if fallback:
        world["need_fallback"]["makan"] = (plot, category)
        world["plot_details"][plot] = {
            "id": plot,
            "business": {
                "id": shop_id,
                "name": name,
                "desa": "fixture-desa",
                "catalogId": category,
            },
        }
    else:
        world["need_locations"]["makan"].append(NeedShop(shop_id, plot, name, category))
    return shop_id


async def test_need_rotation_uses_oldest_eligible_akademis_shop(api, world, settings):
    setup_food_catalog(world)
    other = add_food_supplier(world, "Akademis.ai Cabang", 1200)
    before = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    choice, _ = select_need(before, "makan", shops, settings, Decimal(0), {SHOP: 20, other: 10})
    assert choice.id == other
    limited = settings.model_copy(update={"max_spend": Decimal(1)})
    choice, _ = select_need(before, "makan", shops, limited, Decimal(0), {SHOP: 20, other: 10})
    assert choice.id == SHOP


@pytest.mark.parametrize("status", ["in_stock", "closed", "own_shop", "empty_menu", "unknown"])
async def test_need_fallback_requires_all_akademis_catalogs_prove_stockout(api, world, status):
    setup_food_catalog(world)
    for row in world["shop"]["menu"]:
        row["habis"] = "bahan"
    other = add_food_supplier(world, "Akademis.ai Cabang", 1200)
    add_food_supplier(world, "Warung cadangan", 100, fallback=True)
    catalog = world["shops"][other]
    if status == "closed":
        catalog["open"] = False
    elif status == "own_shop":
        catalog["mine"] = True
    elif status == "empty_menu":
        catalog["menu"] = []
    elif status == "unknown":
        catalog["menu"][0]["habis"] = {"missing": "bahan"}
    if status == "unknown":
        with pytest.raises(HttpCoreError, match="stok"):
            await api.preview("makan")
    else:
        preview = await api.preview("makan")
        assert preview["navigation"]["akademis_sold_out"] is False
        assert [shop["id"] for shop in preview["shops"]] == (
            [other] if status == "in_stock" else []
        )
    assert not any("/api/world/plots/" in request.url.path for request in api.calls)


async def test_need_fallback_rechecks_akademis_stock_before_purchase(api, world, settings):
    setup_food_catalog(world)
    for row in world["shop"]["menu"]:
        row["habis"] = "bahan"
    other = add_food_supplier(world, "Akademis.ai Cabang", 1200)
    stock = world["shops"][other]["menu"][0]
    stock["habis"] = "bahan"
    fallback = add_food_supplier(world, "Warung cadangan", 100, fallback=True)
    before = await api.snapshot()
    preview = await api.preview("makan")
    assert preview["navigation"]["akademis_sold_out"] is True
    shops = [ShopPreview.model_validate(row) for row in preview["shops"]]
    assert select_need(before, "makan", shops, settings, Decimal(0), {}) is None
    supplier, plan = select_need(
        before, "makan", shops, settings, Decimal(0), {}, allow_fallback=True
    )
    assert supplier.id == fallback
    product = plan.product.model_dump(mode="json")
    stock.pop("habis")
    with pytest.raises(HttpCoreError) as error:
        await api.purchase(product, "35", 55, "20", str(uuid4()))
    assert error.value.category == "rejected"
    assert all(request.method == "GET" for request in api.calls)
    stock["habis"] = "bahan"
    await api.purchase(product, "35", 55, "20", str(uuid4()))
    assert [request.url.path for request in api.calls if request.method == "POST"] == [
        f"/api/shops/{fallback}/buy"
    ]


async def test_need_purchase_keeps_uncertain_post_single_attempt(api, world, settings):
    setup_food_catalog(world)
    before = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    _, plan = select_need(before, "makan", shops, settings, Decimal(0), {})
    world["lost_response"] = f"/api/shops/{SHOP}/buy"
    with pytest.raises(HttpCoreError) as error:
        await api.purchase(plan.product.model_dump(mode="json"), "35", 55, "20", str(uuid4()))
    assert error.value.category == "uncertain"
    assert sum(request.method == "POST" for request in api.calls) == 1


@pytest.mark.parametrize("blocked", ["cooldown", "sleeping"])
async def test_physical_facility_requires_free_active_service_on_second_read(api, world, blocked):
    facility_id = str(uuid4())
    world["needs"].update(
        enabled=True,
        needs=[
            {
                "id": "fisik",
                "value": 30,
                "places": [
                    {
                        "id": facility_id,
                        "name": "Gym fixture",
                        "kind": "fasum",
                        "open": True,
                        "priceMilli": 0,
                        "gain": 55,
                    }
                ],
            }
        ],
    )
    details = {
        "id": facility_id,
        "state": "DONE",
        "nextAt": None,
        "service": {"label": "Latihan", "priceMilli": 0},
    }
    world["facilities"][facility_id] = details
    preview = await api.preview("fisik")
    product = preview["shops"][0]["products"][0]
    if blocked == "cooldown":
        details["nextAt"] = "2030-01-02T12:00:00Z"
    else:
        world["needs"]["asleep"] = True
    with pytest.raises(HttpCoreError) as error:
        await api.purchase(product, "35", 30, "20", str(uuid4()))
    assert error.value.category == ("sleeping" if blocked == "sleeping" else "rejected")
    assert all(request.method == "GET" for request in api.calls)
    details["nextAt"] = None
    world["needs"]["asleep"] = False
    product = (await api.preview("fisik"))["shops"][0]["products"][0]
    request_id = str(uuid4())
    await api.purchase(product, "35", 30, "20", request_id)
    posts = [request for request in api.calls if request.method == "POST"]
    assert [request.url.path for request in posts] == [f"/api/facilities/{facility_id}/use"]
    assert json.loads(posts[0].content) == {"requestId": request_id}


async def test_preview_reads_only_configured_catalog_and_never_discovers_shops(api, world):
    await api.snapshot()
    add_shop(
        world, 8, "Akademis.ai outside configuration", "konter-pulsa", "pulsa", "Isi pulsa", 100
    )
    world["locations"]["data"].pop()
    preview = await api.preview("data")
    assert preview["navigation"]["method"] == "fixed_catalog_http"
    assert preview["navigation"]["travel_request_sent"] is False
    products = ShopPreview.model_validate(preview["shops"][0]).products
    assert products[0].effects == {"data": 40} and products[0].price == Decimal("0.5")
    assert all(r.method == "GET" for r in api.calls)
    assert [r.url.path for r in api.calls if r.url.path.startswith("/api/shops/")] == [
        f"/api/shops/{SHOP}"
    ]
    assert not any(r.url.path.startswith(("/api/tujuan", "/api/world/plots")) for r in api.calls)
    assert (api.directory / "http-effects.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "case",
    ["wallet", "price", "floor", "overflow", "resource", "phase", "closed", "forged", "village"],
)
async def test_purchase_rechecks_identity_price_cash_floor_and_no_overflow(api, world, case):
    product = (await api.preview("data"))["shops"][0]["products"][0]
    wallet = "35"
    resource = 50
    if case == "wallet":
        world["me"]["balanceMilli"] -= 1
    if case == "price":
        world["shop"]["menu"][0]["priceMilli"] += 1
    if case == "floor":
        wallet = "20.49"
        world["me"]["balanceMilli"] = 20490
    if case == "overflow":
        resource = 61
        world["ojol"]["bars"]["kuota"] = resource
    if case == "resource":
        world["ojol"]["bars"]["kuota"] = 49
    if case == "phase":
        world["ojol"]["trip"] = trip()
    if case == "closed":
        world["shop"]["open"] = False
    if case == "forged":
        product["price"] = "0.001"
    if case == "village":
        world["me"]["home"]["desa"] = "outside-fixture"
    with pytest.raises(HttpCoreError) as error:
        await api.purchase(product, wallet, resource, "0", str(uuid4()))
    assert error.value.category == "rejected"
    assert not any(r.method == "POST" for r in api.calls)


async def test_purchase_uses_fresh_observed_item_and_single_request_id(api):
    product = (await api.preview("data"))["shops"][0]["products"][0]
    request_id = str(uuid4())
    await api.purchase(product, "35", 50, "20", request_id)
    posts = [r for r in api.calls if r.method == "POST"]
    assert len(posts) == 1 and posts[0].url.path == f"/api/shops/{SHOP}/buy"
    assert json.loads(posts[0].content) == {"item": "pulsa", "requestId": request_id}


@pytest.mark.parametrize("change", [{"balanceMilli": 20250}, {"configVersion": "fixture-v2"}])
async def test_state_change_during_catalog_read_rejects_without_locking_journal(
    api, world, settings, monkeypatch, change
):
    original = api.products

    async def products(*args):
        catalog = await original(*args)
        world["me"].update(change)
        return catalog

    async def call(name, **args):
        if name == "ojol_preview_shop":
            return await api.preview(**args)
        if name == "ojol_purchase":
            monkeypatch.setattr(api, "products", products)
            return await api.purchase(**args)
        pytest.fail(name)

    ui = HttpUI(settings)
    ui.call_tool = call
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        controller = Controller(ui, settings, journal, run)
        with pytest.raises(HttpCoreError, match="berubah sebelum pembelian"):
            await controller.purchase(await api.snapshot(), "data")
        assert all(request.method == "GET" for request in api.calls)
        assert journal.history()["actions"][0]["status"] == "rejected"
        assert controller.spent == 0
        assert journal.start(settings) > run
    finally:
        journal.close()


@pytest.mark.parametrize(
    ("resource", "category", "item", "label"),
    [
        ("fuel", "spbu-pertamina", "isi-pertalite", "Isi Pertalite"),
        ("condition", "bengkel-motor", "tambal-ban", "Tambal ban"),
        ("data", "konter-pulsa", "pulsa", "Isi pulsa"),
    ],
)
async def test_brand_wins_over_cheaper_fallback_and_ranks_branches(
    api, world, settings, resource, category, item, label
):
    world["ojol"]["bars"]["kendaraan"] = 50
    state = await api.snapshot()
    add_shop(world, 8, "AkademisXai", category, item, label, 100)
    add_shop(world, 9, "Cabang aKaDeMiS.AI Barat", category, item, label, 1200)
    selected = add_shop(world, 20, "Cabang AKADEMIS.AI Timur", category, item, label, 900, plang="")
    result = await api.preview(resource)
    shops = [ShopPreview.model_validate(shop) for shop in result["shops"]]
    (shop, plan), deferred = select_shop(state, resource, shops, settings, Decimal(0))
    assert shop.id == selected and shop.preferred and plan.total_cost == Decimal("0.9")
    assert not deferred
    assert all(request.method == "GET" for request in api.calls)


@pytest.mark.parametrize("cause", ["closed", "mine", "sold_out", "budget", "overflow"])
async def test_fallback_when_preferred_shop_has_no_eligible_plan(api, world, settings, cause):
    settings = settings.model_copy(update={"max_spend": Decimal(1)})
    item, label = ("paket-data", "Paket data") if cause == "overflow" else ("pulsa", "Isi pulsa")
    preferred = add_shop(
        world, 8, "Akademis.ai", "konter-pulsa", item, label, 1200 if cause == "budget" else 800
    )
    catalog = world["shops"][preferred]
    catalog["open"] = cause != "closed"
    catalog["mine"] = cause == "mine"
    catalog["menu"][0]["habis"] = cause == "sold_out"
    state = await api.snapshot()
    result = await api.preview("data")
    shops = [ShopPreview.model_validate(shop) for shop in result["shops"]]
    (shop, _), deferred = select_shop(state, "data", shops, settings, Decimal(0))
    assert shop.id == SHOP and not shop.preferred and not deferred


async def test_preview_without_configured_village_never_reads_catalog(api, world):
    world["me"]["home"]["desa"] = "outside-fixture"
    with pytest.raises(HttpCoreError, match="Toko tetap belum dikonfigurasi"):
        await api.preview("data")
    assert not any(r.url.path.startswith("/api/shops/") for r in api.calls)


async def test_incomplete_scan_clears_previous_preview_and_never_buys(api, world):
    product = (await api.preview("data"))["shops"][0]["products"][0]
    preferred = add_shop(world, 8, "Akademis.ai", "konter-pulsa", "pulsa", "Isi pulsa", 500)
    world["failed_paths"].add(f"/api/shops/{preferred}")
    with pytest.raises(HttpCoreError, match="HTTP404"):
        await api.preview("data")
    with pytest.raises(HttpCoreError, match="preview sesi"):
        await api.purchase(product, "35", 50, "20", str(uuid4()))
    assert all(request.method == "GET" for request in api.calls)


@pytest.mark.parametrize("closed", [True, False])
async def test_preview_skips_only_verified_closed_catalog_conflict(api, world, closed):
    shop_id = add_shop(world, 8, "Konter lain", "konter-pulsa", "pulsa", "Isi pulsa", 100)
    world["conflicting_catalogs"]["/api/shops/" + shop_id] = {
        "error": {
            "code": "REQUIREMENT_NOT_MET",
            "message": "Usaha ini belum buka." if closed else "Konflik lain.",
        }
    }
    if closed:
        result = await api.preview("data")
        assert [shop["id"] for shop in result["shops"]] == [SHOP]
    else:
        with pytest.raises(HttpCoreError, match="HTTP409"):
            await api.preview("data")
    assert all(request.method == "GET" for request in api.calls)


async def test_preview_skips_configured_shop_when_catalog_name_changes(api, world):
    world["shop"]["plang"] = "Konter berubah"
    result = await api.preview("data")
    assert result["shops"] == []


async def test_preview_timeout_leaves_no_buyable_catalog(api, monkeypatch):
    product = (await api.preview("data"))["shops"][0]["products"][0]
    monkeypatch.setattr(api, "preview_shop", AsyncMock(side_effect=TimeoutError))
    with pytest.raises(HttpCoreError, match="Deadline preview"):
        await api.preview("data")
    with pytest.raises(HttpCoreError, match="preview sesi"):
        await api.purchase(product, "35", 50, "20", str(uuid4()))
    assert all(request.method == "GET" for request in api.calls)


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_transport_retries_only_reads(settings, monkeypatch, method):
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("PRIVATE_BODY_NOT_FOR_LOGS")

    monkeypatch.setattr("ojol.http_api.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(fail)) as client:
        api = OjolHttpApi(settings.runtime_dir, client=client)
        with pytest.raises(HttpCoreError) as error:
            await api.request("/api/ojol", {"action": "ambil"} if method == "POST" else None)
        assert len(calls) == (1 if method == "POST" else 3)
        assert error.value.recoverable is (method == "GET")
        assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("status", [302, 401, 403])
async def test_auth_never_retries_or_follows_redirect(settings, status):
    handle = Mock(
        return_value=httpx.Response(status, headers={"location": "https://accounts.google.com/"})
    )
    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        api = OjolHttpApi(settings.runtime_dir, client=client)
        with pytest.raises(HttpCoreError) as error:
            await api.request("/api/ojol")
        assert error.value.category == "auth" and not error.value.recoverable
        assert handle.call_count == 1


async def test_expired_cookie_is_rejected_before_client_or_worker_starts(settings, monkeypatch):
    from ojol.session_transfer import parse_cookie_input

    settings = settings.model_copy(update={"env": "local", "operator_authorized": True})
    payload = parse_cookie_input("expired-isolated-cookie")
    payload["cookies"][0]["expires"] = 1
    write_private(settings.runtime_dir / "http-session.json", payload)
    client = Mock()
    monkeypatch.setattr("ojol.http_api.httpx.AsyncClient", client)
    api = OjolHttpApi(settings.runtime_dir)
    with pytest.raises(HttpCoreError) as error:
        await api.__aenter__()
    assert error.value.category == "auth"
    client.assert_not_called()
    service = ControlService(settings)
    service.account_id = "a" * 32
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await service.execute("run")
    spawn.assert_not_awaited()
    notice = json.loads(next((settings.runtime_dir / "notifications").glob("*.json")).read_text())
    assert "Login ulang diperlukan" in notice["text"]
    buttons = notice["reply_markup"]["inline_keyboard"]
    assert buttons[1][0]["callback_data"] == f"acct:{service.account_id}:import_cookie"
    assert "expired-isolated-cookie" not in json.dumps(notice)


async def test_cookie_that_expires_during_work_never_sends_next_request(api):
    api.expires_at = 1
    with pytest.raises(HttpCoreError) as error:
        await api.request("/api/ojol", {"action": "ambil", "vehicle": "motor"})
    assert error.value.category == "auth" and not api.calls


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example/api/ojol",
        "//evil.example/api/ojol",
        "/api/bank/tarik",
        "/api/rest",
        "/api/tujuan/../../bank",
        "/_next/static/../../api/ojol.js",
    ],
)
async def test_no_arbitrary_url_or_unrelated_actions(api, path):
    with pytest.raises(HttpCoreError):
        await api.request(path, {"action": "ambil"})
    assert api.calls == []


def test_effect_extraction_dynamic_values_and_ambiguity():
    effects = extract_effects(json.dumps(EFFECTS, separators=(",", ":")))
    assert set.union(*ITEMS.values()) == effects.keys()
    assert effects["cuci-motor"] == {"condition": 15}
    assert extract_effects('{"pulsa":{"kuota":37}}')["pulsa"] == {"data": 37}
    with pytest.raises(HttpCoreError, match="ambigu"):
        extract_effects('{"pulsa":{"kuota":40},"pulsa":{"kuota":30}}')


async def test_real_stdio_mcp_exposes_only_ojol_tools_and_blocks_test_network(settings):
    settings = settings.model_copy(update={"core": "http"})
    async with HttpUI(settings) as ui:
        assert set(ui.tools) == HTTP_TOOLS
        with pytest.raises(HttpCoreError, match="testing"):
            await ui.snapshot()
        assert not hasattr(ui, "fallback")


@pytest.mark.parametrize("preferred", [False, True])
async def test_http_controller_keeps_pending_request_id_and_books_once(
    api, world, settings, preferred
):
    shop_id = SHOP
    if preferred:
        shop_id = add_shop(world, 8, "Akademis.ai", "konter-pulsa", "pulsa", "Isi pulsa", 500)
    journal = Journal(settings.runtime_dir)
    run = journal.start(settings)
    ui = HttpUI(settings.model_copy(update={"core": "http"}))

    async def call(name, **args):
        if name == "ojol_snapshot":
            return (await api.snapshot()).model_dump(mode="json")
        if name == "ojol_preview_shop":
            return await api.preview(args["resource"])
        if name == "ojol_purchase":
            pending = journal.history()["actions"][0]
            assert pending["status"] == "pending"
            assert json.loads(pending["payload"])["request_id"] == args["request_id"]
            await api.purchase(**args)
            world["me"]["balanceMilli"] -= 500
            world["ojol"]["bars"]["kuota"] += 40
            return {"accepted": True}
        if name == "ojol_job_action":
            await api.job_action(args["kind"])
            done = trip()
            done.update(doneAt="2030-01-02T10:00:01Z", netMilli=720)
            world["ojol"]["trip"] = None
            world["ojol"]["history"] = [done]
            world["ojol"]["earnedTodayMilli"] += 720
            world["me"]["balanceMilli"] += 720
            return {"accepted": True}
        pytest.fail(name)

    ui.call_tool = call
    controller = Controller(ui, settings, journal, run)
    try:
        await controller.purchase(await ui.snapshot(), "data")
        world["ojol"]["trip"] = trip()
        world["time"]["now"] = "2030-01-02T10:00:01Z"
        await controller.job_action(await ui.snapshot(), "complete")
        assert Decimal(journal.profit(run)["laba_bersih"]) == Decimal("0.220")
        purchase = next(row for row in journal.history()["actions"] if row["kind"] == "purchase")
        selection = json.loads(purchase["payload"])
        assert selection["source"] == ("akademis" if preferred else "cadangan")
        assert selection["shop_id"] == shop_id
        assert any(
            r.method == "POST" and r.url.path == f"/api/shops/{shop_id}/buy" for r in api.calls
        )
        assert "Akademis.ai" in selection["reason"]
        assert all(row["status"] == "verified" for row in journal.history()["actions"])
        assert len([r for r in api.calls if r.method == "POST"]) == 2
    finally:
        journal.close()


async def test_controller_rotates_only_eligible_akademis_shops(api, world, settings):
    first = add_shop(world, 8, "Akademis.ai", "konter-pulsa", "pulsa", "Isi pulsa", 700)
    second = add_shop(world, 9, "Akademis.ai Cabang", "konter-pulsa", "pulsa", "Isi pulsa", 800)
    ui = HttpUI(settings)

    async def call(name, **args):
        if name == "ojol_preview_shop":
            return await api.preview(args["resource"])
        if name == "ojol_snapshot":
            return (await api.snapshot()).model_dump(mode="json")
        assert name == "ojol_purchase"
        await api.purchase(**args)
        world["me"]["balanceMilli"] -= int(Decimal(args["product"]["price"]) * 1000)
        world["ojol"]["bars"]["kuota"] += 40
        return {"accepted": True}

    ui.call_tool = call
    first_item = world["shops"][first]["menu"][0]
    second_item = world["shops"][second]["menu"][0]
    second_item["habis"] = True

    async def purchase_in_new_session():
        world["ojol"]["bars"]["kuota"] = 50
        with closing(Journal(settings.runtime_dir)) as journal:
            controller = Controller(ui, settings, journal, journal.start(settings))
            await controller.purchase(await ui.snapshot(), "data")

    await purchase_in_new_session()
    await purchase_in_new_session()
    first_item["habis"] = True
    await purchase_in_new_session()
    first_item["habis"] = False
    second_item["habis"] = False
    await purchase_in_new_session()
    await purchase_in_new_session()
    assert [r.url.path for r in api.calls if r.method == "POST"] == [
        f"/api/shops/{shop_id}/buy" for shop_id in (first, first, SHOP, second, first)
    ]


async def test_http_mode_with_session_never_starts_chromium(settings):
    from ojol.session_transfer import parse_cookie_input

    settings = settings.model_copy(update={"core": "http"})
    write_private(
        settings.runtime_dir / "http-session.json", parse_cookie_input("isolated-test-session")
    )
    service = ControlService(settings)
    await service.ensure_backend(require_session=True)


async def test_stop_cancels_waiting_http_tool_without_repeating(settings):
    import asyncio

    from ojol.controller import StopRequested

    ui = HttpUI(settings)

    async def waiting(**kwargs):
        await asyncio.Event().wait()

    tool = AsyncMock(side_effect=waiting)
    ui.tools = {"ojol_snapshot": SimpleNamespace(run_async=tool)}
    checks = 0

    def stop():
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise StopRequested("Fixture user stop")

    ui.check_cancel = stop
    with pytest.raises(StopRequested):
        await ui.snapshot()
    tool.assert_awaited_once()


@pytest.mark.parametrize(("valid", "expired"), [(True, False), (False, False), (False, True)])
async def test_http_cookie_import_is_atomic_and_preserves_old_session_on_failure(
    settings, monkeypatch, valid, expired
):
    from pathlib import Path

    import ojol.http_core as module
    import ojol.session_transfer as transfer

    settings = settings.model_copy(update={"core": "http", "env": "local"})
    previous = transfer.parse_cookie_input("old-isolated-fixture")
    payload = transfer.parse_cookie_input("new-isolated-fixture")
    if expired:
        payload["cookies"][0]["expires"] = 1
    active = settings.runtime_dir / "http-session.json"
    write_private(active, previous)
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda p: True if str(p) == "/.dockerenv" else original(p))

    async def verify():
        pending = settings.runtime_dir / "http-session.pending.json"
        assert pending.stat().st_mode & 0o777 == 0o600
        assert json.loads(active.read_text()) == previous
        if not valid:
            raise HttpCoreError("Fixture session rejected", category="auth")
        return SimpleNamespace(phase="idle", wallet=Decimal(35))

    core = SimpleNamespace(snapshot=verify)
    context = AsyncMock()
    context.__aenter__.return_value = core
    monkeypatch.setattr(module, "HttpUI", lambda *args, **kwargs: context)
    monkeypatch.setattr(transfer, "flush_notices", AsyncMock())
    monkeypatch.setattr(transfer, "queue_notice", Mock())
    if valid:
        await transfer.import_session(settings, json.dumps(payload))
    else:
        with pytest.raises(HttpCoreError):
            await transfer.import_session(settings, json.dumps(payload))
    assert json.loads(active.read_text()) == (payload if valid else previous)
    assert not (settings.runtime_dir / "http-session.pending.json").exists()
    if expired:
        context.__aenter__.assert_not_awaited()


async def test_effect_cache_invalidates_when_server_config_version_changes(api, world):
    await api.snapshot()
    await api.effects()
    world["me"]["configVersion"] = "fixture-v2"
    await api.snapshot()
    await api.effects()
    assert len([r for r in api.calls if r.url.path.endswith("fixture.js")]) == 2


async def test_asset_get_cannot_escape_origin_or_static_directory(api):
    with pytest.raises(HttpCoreError):
        await api.request("/_next/static/../../api/ojol.js")
    assert not api.calls


@pytest.mark.parametrize(
    "repeat_cursor, missing_detail", [(False, False), (True, False), (False, True)]
)
async def test_daily_wallet_wib_pagination_and_dedup(
    settings, monkeypatch, repeat_cursor, missing_detail
):
    from datetime import datetime

    def row(identifier, at, amount, kind="OJOL_ONGKOS"):
        return {"id": identifier, "at": at, "amountMilli": amount, "type": kind}

    def purchase(identifier, at, amount, detail):
        return {**row(identifier, at, amount, "SHOP_PURCHASE"), "detail": detail}

    start = purchase("at-start", "2026-11-10T17:00:00Z", -1000, "Isi Pertalite")
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path == "/api/me/koin"
        if not request.url.params:
            return httpx.Response(
                200,
                json={
                    "items": [
                        row("next-day", "2026-11-11T17:00:00Z", 9000),
                        purchase("end", "2026-11-11T17:00:00Z", -1000, "Isi Pertalite"),
                        row("manual", "2026-11-11T10:00:00Z", 800),
                        row("worker", "2026-11-11T09:30:00Z", 1200),
                        purchase("pulsa", "2026-11-11T09:00:00Z", -500, "  ISI   pulsa  "),
                        purchase("ban", "2026-11-11T08:00:00Z", -500, "Tambal ban"),
                        purchase("oli", "2026-11-11T07:00:00Z", -600, "Ganti oli"),
                        purchase("positive", "2026-11-11T06:00:00Z", 100, "Isi pulsa"),
                        purchase(
                            "unclassified",
                            "2026-11-11T05:00:00Z",
                            -300,
                            None if missing_detail else "Bonus Isi pulsa",
                        ),
                        start,
                    ],
                    "next": "opaque?&cursor",
                },
            )
        assert dict(request.url.params) == {"after": "opaque?&cursor"}
        return httpx.Response(
            200,
            json={
                "items": [start, row("older", "2026-11-10T16:59:59Z", 4000)],
                "next": "opaque?&cursor" if repeat_cursor else None,
            },
        )

    monkeypatch.setattr(
        "ojol.http_api.now", lambda: datetime.fromisoformat("2026-11-12T10:00:00+00:00")
    )
    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        result = await OjolHttpApi(settings.runtime_dir, client=client).daily_wallet("2026-11-11")
    assert result["income_milli"] == 2000 and result["payout_count"] == 2
    assert result["expenses_milli"] == {"data": 500, "condition": 1100, "fuel": 1000}
    assert bool(result["expense_issue"]) is missing_detail
    assert result["complete"] is not repeat_cursor
    assert result["issue"] == ("Cursor riwayat berulang" if repeat_cursor else None)
    assert len(calls) == 2


async def test_daily_wallet_page_limit_is_partial(settings, monkeypatch):
    from datetime import datetime

    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"items": [], "next": str(len(calls))})

    monkeypatch.setattr(
        "ojol.http_api.now", lambda: datetime.fromisoformat("2026-11-12T10:00:00+00:00")
    )
    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        result = await OjolHttpApi(settings.runtime_dir, client=client).daily_wallet("2026-11-11")
    assert len(calls) == 10
    assert not result["complete"] and result["issue"] == "Batas 10 halaman tercapai"
