import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest

from ojol.control import ControlService
from ojol.controller import Controller
from ojol.healing import write_private
from ojol.http_api import ITEMS, ORIGIN, HttpCoreError, OjolHttpApi, extract_effects
from ojol.http_core import HTTP_TOOLS, HttpUI
from ojol.journal import Journal
from ojol.models import ShopPreview
from ojol.planner import select_shop

SHOP = "00000000-0000-4000-8000-000000000001"
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
        "time": {"now": "2030-01-02T10:00:00Z"},
        "places": {
            "usaha": [
                {
                    "plotId": "K22-U07",
                    "name": "Konter fixture",
                    "item": "konter-pulsa",
                    "x": 0,
                    "y": 0,
                }
            ]
        },
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

    world["plots"] = {
        "K22-U07": {
            "business": {
                "id": SHOP,
                "catalogId": "konter-pulsa",
                "name": "Konter fixture",
                "desa": "fixture-desa",
            }
        }
    }
    world["shops"] = {SHOP: world["shop"]}
    world["failed_paths"] = set()
    world["conflicting_catalogs"] = {}
    return world


def add_shop(world, number, name, category, item, product_name, price_milli, **catalog_fields):
    shop_id = f"00000000-0000-4000-8000-{number:012}"
    plot_id = f"K22-U{number:02}"
    world["places"]["usaha"].append(
        {"plotId": plot_id, "name": "Nama dari daftar", "item": category, "x": number, "y": 0}
    )
    world["plots"][plot_id] = {
        "business": {"id": shop_id, "catalogId": category, "name": name, "desa": "fixture-desa"}
    }
    world["shops"][shop_id] = {
        "mine": False,
        "open": True,
        "plang": name,
        "menu": [{"item": item, "name": product_name, "priceMilli": price_milli}],
        **catalog_fields,
    }
    return shop_id


@pytest.fixture
async def api(settings, world):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.url.host == "www.kampungsebelah.com"
        path = request.url.path
        if path in world["failed_paths"]:
            return httpx.Response(404)
        if request.method == "POST":
            return httpx.Response(200, json={"ok": True})
        if path in world["conflicting_catalogs"]:
            return httpx.Response(409, json=world["conflicting_catalogs"][path])
        data = {
            "/api/ojol": world["ojol"],
            "/api/game/me": world["me"],
            "/api/kebutuhan": world["needs"],
            "/api/time": world["time"],
            "/api/tujuan": world["places"],
            **{"/api/world/plots/" + key: value for key, value in world["plots"].items()},
            **{"/api/shops/" + key: value for key, value in world["shops"].items()},
        }
        if path == "/kampung":
            return httpx.Response(
                200, text='<script src="/_next/static/chunks/fixture.js"></script>'
            )
        if path == "/_next/static/chunks/fixture.js":
            return httpx.Response(200, text=json.dumps(EFFECTS, separators=(",", ":")))
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


async def test_snapshot_exact_coins_sleep_and_server_countdown(api, world):
    world["ojol"]["trip"] = trip()
    state = await api.snapshot()
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


async def test_preview_reads_catalog_effects_and_never_sends_travel(api):
    await api.snapshot()
    preview = await api.preview("data")
    assert preview["navigation"]["method"] == "eye_preview_http"
    assert preview["navigation"]["travel_request_sent"] is False
    products = ShopPreview.model_validate(preview["shops"][0]).products
    assert products[0].effects == {"data": 40} and products[0].price == Decimal("0.5")
    assert all(r.method == "GET" for r in api.calls)
    assert not any(r.url.path == "/api/tujuan" and r.method == "POST" for r in api.calls)
    assert (api.directory / "http-effects.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "case", ["wallet", "price", "floor", "overflow", "resource", "phase", "closed", "forged"]
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
    with pytest.raises(HttpCoreError):
        await api.purchase(product, wallet, resource, "0", str(uuid4()))
    assert not any(r.method == "POST" for r in api.calls)


async def test_purchase_uses_fresh_observed_item_and_single_request_id(api):
    product = (await api.preview("data"))["shops"][0]["products"][0]
    request_id = str(uuid4())
    await api.purchase(product, "35", 50, "20", request_id)
    posts = [r for r in api.calls if r.method == "POST"]
    assert len(posts) == 1 and posts[0].url.path == f"/api/shops/{SHOP}/buy"
    assert json.loads(posts[0].content) == {"item": "pulsa", "requestId": request_id}


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


async def test_preferred_spbu_can_service_motor_but_regular_spbu_is_not_fallback(
    api, world, settings
):
    world["ojol"]["bars"]["kendaraan"] = 50
    state = await api.snapshot()
    add_shop(world, 8, "SPBU biasa", "spbu-pertamina", "tambal-ban", "Tambal ban", 100)
    preferred = add_shop(
        world, 9, "SPBU Akademis.ai", "spbu-pertamina", "isi-angin", "Isi angin", 200
    )
    fallback = add_shop(
        world, 10, "Bengkel biasa", "bengkel-motor", "tambal-ban", "Tambal ban", 300
    )
    for is_open, expected in ((True, preferred), (False, fallback)):
        world["shops"][preferred]["open"] = is_open
        result = await api.preview("condition")
        shops = [ShopPreview.model_validate(shop) for shop in result["shops"]]
        (shop, _), deferred = select_shop(state, "condition", shops, settings, Decimal(0))
        assert shop.id == expected and not deferred


async def test_incomplete_scan_clears_previous_preview_and_never_buys(api, world):
    product = (await api.preview("data"))["shops"][0]["products"][0]
    add_shop(world, 8, "Akademis.ai", "konter-pulsa", "pulsa", "Isi pulsa", 500)
    world["failed_paths"].add("/api/world/plots/K22-U08")
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


async def test_preview_considers_more_than_twelve_matching_shops(api, world):
    for number in range(8, 21):
        add_shop(world, number, "Konter biasa", "konter-pulsa", "pulsa", "Isi pulsa", 500)
    preferred = add_shop(world, 21, "Akademis.ai", "konter-pulsa", "pulsa", "Isi pulsa", 500)
    result = await api.preview("data")
    assert len(result["shops"]) == 15
    assert result["shops"][-1]["id"] == preferred


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


async def test_http_mode_with_session_never_starts_chromium(settings):
    settings = settings.model_copy(update={"core": "http"})
    write_private(settings.runtime_dir / "http-session.json", {"cookies": []})
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


@pytest.mark.parametrize("valid", [True, False])
async def test_http_cookie_import_is_atomic_and_preserves_old_session_on_failure(
    settings, monkeypatch, valid
):
    from pathlib import Path

    import ojol.http_core as module
    import ojol.session_transfer as transfer

    settings = settings.model_copy(update={"core": "http", "env": "local"})
    previous = transfer.parse_cookie_input("old-isolated-fixture")
    payload = transfer.parse_cookie_input("new-isolated-fixture")
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
