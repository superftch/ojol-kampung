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
from ojol.identity import cached_profile, save_profile, verified_profile
from ojol.journal import Journal
from ojol.models import ShopPreview
from ojol.planner import next_step, select_need, select_shop
from ojol.shop_locations import NeedShop, ShopLocation
from ojol.study import set_subject
from ojol.ui import HTTP_TOOLS, HttpUI

SHOP = "00000000-0000-4000-8000-000000000001"


def study_fixture(world, settings, monkeypatch, mode):
    identifier, visit_id = str(uuid4()), str(uuid4())
    price = 0 if mode == "perpus" else 4000
    facility = {
        "id": identifier,
        "title": "Belajar fixture",
        "state": "DONE",
        "item": "perpustakaan-desa-t6" if mode == "perpus" else "universitas",
        "nextAt": None,
        "myVisitUntil": None,
        "service": {
            "label": "Belajar",
            "priceMilli": price,
            "studySessions": 1,
            "open": True,
            "studyTracks": None,
        },
    }
    skill = {"id": "administrasi", "next": {"library": True}, "pending": None}
    world["me"]["skill"] = {"tracks": [skill]}
    world["facilities"][identifier] = facility
    quiz = {
        "available": True,
        "visitId": visit_id,
        "track": {"id": "administrasi"},
        "bacaan": ["Notulen adalah catatan rapat."],
        "soal": [{"q": "Catatan rapat disebut?", "options": ["Brosur", "Notulen", "Kuitansi"]}],
    }
    world["extra_responses"] = {f"/api/facilities/{identifier}/kuis": quiz}
    world["quiz_bank"] = {
        "facilities": {"perpustakaan-desa": {"bonus_sessions": 1}},
        "tracks": {
            "administrasi": [
                {
                    "q": "Catatan rapat disebut?",
                    "a": "Notulen",
                    "fakta": "Notulen adalah catatan rapat.",
                }
            ]
        },
    }
    world["post_responses"] = {
        f"/api/facilities/{identifier}/use": lambda req: {
            "id": visit_id,
            "projectId": identifier,
            "priceMilli": price,
            "requestId": json.loads(req.content)["requestId"],
        },
        f"/api/facilities/{identifier}/kuis": {
            "track": {"id": "administrasi"},
            "benar": 1,
            "total": 1,
            "bonus": 1,
        },
    }
    monkeypatch.setattr(
        "ojol.http_api.STUDY_FACILITIES_BY_VILLAGE", {"fixture-desa": {mode: identifier}}
    )
    set_subject(settings.runtime_dir, mode, "administrasi")
    set_auto_flag(settings.runtime_dir, mode, True)
    return facility, skill, quiz


@pytest.mark.parametrize("mode", ["perpus", "kuliah"])
async def test_study_start_validates_and_posts_one_observed_visit(
    api, world, settings, monkeypatch, mode
):
    facility, _, _ = study_fixture(world, settings, monkeypatch, mode)
    request_id = str(uuid4())
    price = Decimal(facility["service"]["priceMilli"]) / 1000
    result = await api.study_start(mode, "administrasi", str(price), "35", "20", request_id)
    posts = [request for request in api.calls if request.method == "POST"]
    assert len(posts) == 1
    assert json.loads(posts[0].content) == {"requestId": request_id, "track": "administrasi"}
    assert result["requestId"] == request_id


@pytest.mark.parametrize(
    "change",
    [
        "off",
        "subject",
        "price",
        "cooldown",
        "closed",
        "pending",
        "advanced",
        "wallet",
        "sleeping",
        "floor",
    ],
)
async def test_study_guards_reject_without_charging(api, world, settings, monkeypatch, change):
    facility, skill, _ = study_fixture(world, settings, monkeypatch, "kuliah")
    if change == "off":
        set_auto_flag(settings.runtime_dir, "kuliah", False)
    elif change == "subject":
        set_subject(settings.runtime_dir, "kuliah", "boga")
    elif change == "price":
        facility["service"]["priceMilli"] = 5000
    elif change == "cooldown":
        facility["nextAt"] = "2030-01-03T00:00:00Z"
    elif change == "closed":
        facility["service"]["open"] = False
    elif change == "pending":
        skill["pending"] = {"level": 3}
    elif change == "advanced":
        skill["next"]["library"] = False
    elif change == "wallet":
        world["me"]["balanceMilli"] = 34999
    elif change == "sleeping":
        world["needs"]["asleep"] = True
    elif change == "floor":
        world["me"]["balanceMilli"] = 23000
    with pytest.raises(HttpCoreError):
        await api.study_start(
            "kuliah", "administrasi", "4", "23" if change == "floor" else "35", "20", str(uuid4())
        )
    assert not any(request.method == "POST" for request in api.calls)


async def test_study_quiz_uses_current_visit_and_shuffled_options(
    api, world, settings, monkeypatch
):
    facility, _, quiz = study_fixture(world, settings, monkeypatch, "perpus")
    result = await api.study_quiz("perpus", quiz["visitId"], "administrasi")
    posts = [request for request in api.calls if request.method == "POST"]
    assert len(posts) == 1 and posts[0].url.path == f"/api/facilities/{facility['id']}/kuis"
    assert json.loads(posts[0].content) == {"visitId": quiz["visitId"], "answers": [1]}
    assert result["benar"] == 1


@pytest.mark.parametrize("change", ["visit", "done", "unknown", "ambiguous", "off", "sleeping"])
async def test_study_quiz_never_guesses_or_submits_stale_visit(
    api, world, settings, monkeypatch, change
):
    _, _, quiz = study_fixture(world, settings, monkeypatch, "perpus")
    visit_id = quiz["visitId"]
    if change == "visit":
        visit_id = str(uuid4())
    elif change == "done":
        quiz["available"] = False
    elif change == "unknown":
        quiz["soal"][0]["q"] = "Pertanyaan baru"
    elif change == "ambiguous":
        quiz["soal"][0]["options"] = ["Notulen", "Notulen"]
    elif change == "off":
        set_auto_flag(settings.runtime_dir, "perpus", False)
    elif change == "sleeping":
        world["needs"]["asleep"] = True
    with pytest.raises(HttpCoreError):
        await api.study_quiz("perpus", visit_id, "administrasi")
    assert not any(request.method == "POST" for request in api.calls)


@pytest.mark.parametrize("quiz_action", [False, True])
async def test_study_transport_loss_never_replays_post(
    api, world, settings, monkeypatch, quiz_action
):
    facility, _, quiz = study_fixture(world, settings, monkeypatch, "kuliah")
    world["lost_response"] = f"/api/facilities/{facility['id']}/{'kuis' if quiz_action else 'use'}"
    with pytest.raises(HttpCoreError) as error:
        if quiz_action:
            await api.study_quiz("kuliah", quiz["visitId"], "administrasi")
        else:
            await api.study_start("kuliah", "administrasi", "4", "35", "20", str(uuid4()))
    assert error.value.category == "uncertain"
    assert len([request for request in api.calls if request.method == "POST"]) == 1


async def test_house_material_is_bought_and_applied_even_when_not_service(api, world, settings):
    world["need_locations"]["rumah"] = [
        NeedShop(SHOP, "K40-U01", "Akademis.ai Bangunan", "toko-bangunan")
    ]
    world["shop"].update(
        plang="Akademis.ai Bangunan",
        menu=[{"item": "pipa", "name": "Pipa paralon", "priceMilli": 800, "service": False}],
    )
    world["need_effects"].update({"nasi-goreng": {"makan": 35}, "pipa": {"rumah": 20}})
    world["needs"].update(enabled=True, needs=[{"id": "rumah", "value": 40}])
    ui = HttpUI(settings, api=api)

    async def call(name, **args):
        if name == "ojol_preview_shop":
            return await api.preview(args["resource"])
        if name == "ojol_snapshot":
            return (await api.snapshot()).model_dump(mode="json")
        assert name == "ojol_purchase"
        await api.purchase(**args)
        world["me"]["balanceMilli"] -= 800
        world["needs"]["needs"][0]["value"] += 20
        return {"accepted": True}

    ui.call_tool = call

    async def _buy(product, wallet, current, min_balance=5):
        return await call(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            request_id=ui.request_id,
            expected_wallet=str(wallet),
            expected_resource=current,
            min_balance=str(min_balance),
        )

    ui.buy = _buy
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        assert await c.purchase(await ui.snapshot(), "rumah")
        assert c.state.needs["rumah"] == 60
        assert Decimal(journal.profit()["pengeluaran"]) == Decimal("0.8")
        assert journal.history()["actions"][0]["status"] == "verified"
    assert len([request for request in api.calls if request.method == "POST"]) == 1


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
        "directory": [],
        "plot_details": {},
        "need_effects": {},
        "facility_effects": {
            "gym-desa": {"fisik": 55, "kesehatan": 15},
            "kolam-renang": {"fisik": 50, "rekreasi": 15},
        },
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

    def handle(request):
        calls.append(request)
        assert request.url.host == "www.kampungsebelah.com"
        path = request.url.path
        query_path = f"{path}?{request.url.query.decode()}" if request.url.query else path
        if path in world["failed_paths"]:
            return httpx.Response(404)
        if request.method == "POST":
            if path == world.get("lost_response"):
                raise httpx.ReadTimeout("fixture response lost", request=request)
            response = world.get("post_responses", {}).get(path, {"ok": True})
            return httpx.Response(200, json=response(request) if callable(response) else response)
        if query_path in world.get("text_responses", {}):
            return httpx.Response(200, text=world["text_responses"][query_path])
        if path in world.get("text_responses", {}):
            return httpx.Response(200, text=world["text_responses"][path])
        if path in world["conflicting_catalogs"]:
            return httpx.Response(409, json=world["conflicting_catalogs"][path])
        data = {
            "/api/ojol": world["ojol"],
            "/api/kendaraan": world.get("garage", {"items": []}),
            "/api/game/me": world["me"],
            "/api/kebutuhan": world["needs"],
            "/api/time": world["time"],
            "/api/tujuan": {"usaha": world["directory"]},
            **{"/api/shops/" + key: value for key, value in world["shops"].items()},
            **{"/api/facilities/" + key: value for key, value in world["facilities"].items()},
            **{"/api/world/plots/" + key: value for key, value in world["plot_details"].items()},
            **world.get("extra_responses", {}),
        }
        if path == "/kampung":
            return httpx.Response(
                200, text='<script src="/_next/static/chunks/fixture.js"></script>'
            )
        if path == "/_next/static/chunks/fixture.js":
            return httpx.Response(
                200,
                text=json.dumps(
                    {
                        "barang": {**EFFECTS, **world["need_effects"]},
                        "fasum": world.get("facility_effects", {}),
                    },
                    separators=(",", ":"),
                )
                + (
                    ";JSON.parse(" + repr(json.dumps(world["quiz_bank"])) + ")"
                    if "quiz_bank" in world
                    else ""
                ),
            )
        query_path = f"{path}?{request.url.query.decode()}" if request.url.query else path
        key = query_path if query_path in data else path
        if key not in data:
            return httpx.Response(404)
        resp_data = data[key]
        return httpx.Response(200, json=resp_data(request) if callable(resp_data) else resp_data)

    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        instance = OjolHttpApi(settings.runtime_dir, client=client)
        instance.calls = calls
        # Instans lain (HttpUI/controller) ikut memakai transport fixture.
        from ojol.session_transfer import parse_cookie_input

        write_private(
            settings.runtime_dir / "http-session.json", parse_cookie_input("fixture-cookie")
        )
        real_async_client = httpx.AsyncClient

        def mock_client(**kwargs):
            kwargs.setdefault("transport", httpx.MockTransport(handle))
            return real_async_client(**kwargs)

        monkeypatch.setattr("ojol.http_api.httpx.AsyncClient", mock_client)
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


@pytest.mark.parametrize(
    ("inventory", "vehicle"),
    [(None, "motor"), (["motor"], "motor"), (["mobil"], "mobil"), (["motor", "mobil"], "mobil")],
)
async def test_order_uses_available_car_before_motor(api, world, inventory, vehicle):
    if inventory is not None:
        world["ojol"]["vehicles"] = inventory
    world["ojol"]["pakai"] = {"bensin": 5, "kendaraan": 2, "kuota": 4}
    assert (await api.snapshot()).ojol_vehicle == vehicle
    await api.job_action("search")
    posts = [r for r in api.calls if r.method == "POST"]
    assert [json.loads(r.content) for r in posts] == [{"action": "ambil", "vehicle": vehicle}]
    assert not any(r.url.path == "/api/kendaraan" for r in api.calls)


async def test_active_motor_trip_can_finish_after_buying_car(api, world):
    world["ojol"].update(vehicle="mobil", vehicles=["motor", "mobil"], trip=trip())
    world["time"]["now"] = "2030-01-02T10:01:00Z"
    assert (await api.snapshot()).ojol_vehicle == "motor"
    await api.job_action("complete")
    assert [json.loads(r.content) for r in api.calls if r.method == "POST"] == [
        {"action": "selesai"}
    ]


async def test_trip_order_code_is_sent_when_claiming_fare(api, world):
    world["ojol"]["trip"] = {**trip(), "cek": "93"}
    world["time"]["now"] = "2030-01-02T10:01:00Z"

    assert (await api.snapshot()).order_code == "93"
    await api.job_action("complete")
    assert [json.loads(request.content) for request in api.calls if request.method == "POST"] == [
        {"action": "selesai", "kode": "93"}
    ]


def _cek_svg(digits):
    import base64
    import json

    from ojol.svg_captcha_solver import SvgCaptchaSolver

    model = json.loads(base64.b64decode(SvgCaptchaSolver.model))
    paths = []
    for index, digit in enumerate(digits):
        pattern = next(key for key, value in model.items() if value == digit)
        paths.append(f'<path d="{index}.0 {pattern}"/>')
    return "<svg>" + "".join(paths) + "</svg>"


async def test_trip_cek_boolean_is_not_order_code(api, world):
    world["ojol"]["trip"] = {**trip(), "cek": False}
    world["time"]["now"] = "2030-01-02T10:01:00Z"

    snapshot = await api.snapshot()
    assert snapshot.order_code is None
    assert snapshot.order_verify is False
    await api.job_action("complete")
    assert [json.loads(request.content) for request in api.calls if request.method == "POST"] == [
        {"action": "selesai"}
    ]


async def test_trip_cek_true_solves_svg_captcha(api, world):
    world["ojol"]["trip"] = {**trip(), "cek": True}
    world["time"]["now"] = "2030-01-02T10:01:00Z"
    world["text_responses"] = {
        "/api/ojol/cek?t=trip-fixture&a=2030-01-02T10:00:00.001Z&m=1": _cek_svg("42")
    }

    snapshot = await api.snapshot()
    assert snapshot.order_code is None
    assert snapshot.order_verify is True
    await api.job_action("complete")
    assert [json.loads(request.content) for request in api.calls if request.method == "POST"] == [
        {"action": "selesai", "kode": "42"}
    ]


def _kendara_posts(world, pilihan):
    def respond(request):
        action = json.loads(request.content).get("action")
        if action == "tawar":
            return {"pilihan": pilihan}
        if action == "ambil":
            return {
                "trip": {
                    **trip(),
                    "from": {"x": 3, "y": 3},
                    "to": {"x": 4, "y": 4},
                    "arrived": False,
                }
            }
        if action == "jemput":
            return {"trip": {**trip(), "arrived": False, "jemput": True}}
        return {"trip": {**trip(), "arrived": False}}

    world["post_responses"] = {"/api/ojol": respond}


async def test_job_action_kendara_mode_tawar_picks_highest_fare(api, world):
    world["ojol"]["pakai"] = {"bensin": 5, "kendaraan": 2, "kuota": 4}
    _kendara_posts(
        world,
        [
            {"id": "rendah", "fareMilli": 500, "from": {"x": 1, "y": 1}, "to": {"x": 2, "y": 2}},
            {"id": "tinggi", "fareMilli": 900, "from": {"x": 3, "y": 3}, "to": {"x": 4, "y": 4}},
        ],
    )
    await api.job_action("search", mode="kendara")
    posts = [json.loads(r.content) for r in api.calls if r.method == "POST"]
    assert posts[0] == {"action": "tawar", "vehicle": "motor", "mode": "kendara"}
    assert posts[1] == {
        "action": "ambil",
        "mode": "kendara",
        "pilih": "tinggi",
        "vehicle": "motor",
    }
    assert posts[-1] == {"action": "lacak", "x": 4, "y": 4}


async def test_job_action_kendara_mode_complete_sends_destination_lacak_and_selesai(api, world):
    world["ojol"]["trip"] = {
        **trip(),
        "mode": "kendara",
        "to": {"label": "Toko B", "x": -35.0, "y": -118.4},
    }
    world["time"]["now"] = "2030-01-02T10:01:00Z"
    await api.job_action("complete")
    posts = [json.loads(r.content) for r in api.calls if r.method == "POST"]
    assert posts == [
        {"action": "lacak", "x": -35.0, "y": -118.4},
        {"action": "selesai"},
    ]


async def test_snapshot_tracks_12_hour_limit_from_narik_menit(api, world):
    world["ojol"].update(
        narikMenit=360,
        narikMaksMenit=720,
    )
    state = await api.snapshot()
    assert state.ojol_hours_left == 6.0
    assert state.ojol_shift_done is False


@pytest.mark.parametrize(
    ("vehicle", "item", "name"),
    [
        ("motor", "isi-pertalite", "Isi Pertalite"),
        ("mobil", "isi-daya", "Isi daya SPKLU (mobil listrik)"),
    ],
)
async def test_refill_uses_matching_power_source(api, world, settings, vehicle, item, name):
    world["ojol"].update(vehicle=vehicle, vehicles=[vehicle])
    fuel = 20 if vehicle == "motor" else 4
    world["ojol"]["bars"]["bensin"] = fuel
    if vehicle == "mobil":
        world["ojol"].update(problem="Daya tidak cukup", fix="bensin")
        with pytest.raises(HttpCoreError, match="belum mengizinkan"):
            await api.job_action("search")
    world["garage"] = {"items": [{"family": vehicle, "listrik": vehicle == "mobil"}]}
    world["need_effects"]["isi-daya"] = {"bensin": 70}
    shop = add_shop(
        world, 2, "SPBU fixture", CATEGORIES["fuel"], "isi-pertalite", "Isi Pertalite", 1000
    )
    world["shops"][shop]["menu"].append(
        {"item": "isi-daya", "name": "Isi daya SPKLU (mobil listrik)", "priceMilli": 800}
    )
    state = await api.snapshot()
    previews = [ShopPreview.model_validate(row) for row in (await api.preview("fuel"))["shops"]]
    assert [product.name for product in previews[0].products] == [name]
    selection, _ = select_shop(state, "fuel", previews, settings, Decimal(0))
    product = selection[1].product
    await api.purchase(product.model_dump(mode="json"), "35", fuel, "20", str(uuid4()))
    posts = [r for r in api.calls if r.method == "POST"]
    assert len(posts) == 1 and json.loads(posts[0].content)["item"] == item


@pytest.mark.parametrize(
    ("vehicle", "tank", "other_tank"),
    [
        ("motor", "bensin", "bensinMobil"),
        ("mobil", "bensinMobil", "bensin"),
    ],
)
async def test_spbu_worker_reads_selected_tank_and_waits_for_refill(
    api, world, settings, vehicle, tank, other_tank
):
    world["ojol"].update(
        vehicle=vehicle,
        vehicles=["motor", "mobil"],
        pakai={"bensin": 6, "bensinMin": 3, "kendaraan": 2, "kuota": 4},
        problem="Bensin kurang",
        fix="bensin",
        bars={"bensin": 88, "kendaraan": 90, "kuota": 90},
    )
    rows = [{"id": other_tank, "value": 88}, {"id": tank, "value": 2}]
    world["needs"].update(enabled=True, needs=rows)
    state = await api.snapshot()
    assert state.ojol_vehicle == vehicle
    assert state.fuel == 2
    assert next_step(state, settings).action == "wait"
    assert next_step(state, settings).resource == "fuel"
    preview = await api.preview("fuel")
    assert preview["shops"] == [] and preview["navigation"]["method"] == "spbu_visit"
    rows[-1]["value"] = 100
    world["ojol"].update(problem=None, fix=None)
    assert next_step(await api.snapshot(), settings).action == "search"
    assert all(request.method == "GET" for request in api.calls)


async def test_car_condition_prefers_lower_cost_for_same_recovery(api, world, settings):
    world["ojol"].update(vehicle="mobil", vehicles=["motor", "mobil"])
    world["ojol"]["bars"]["kendaraan"] = 20
    world["need_effects"]["servis-mobil"] = {"kendaraan": 60}
    add_shop(
        world, 2, "Akademis.ai Mobil", CATEGORIES["condition"], "servis-mobil", "Servis mobil", 2500
    )
    add_shop(
        world, 3, "Bengkel fixture", CATEGORIES["condition"], "servis-motor", "Servis motor", 1500
    )
    state = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("condition"))["shops"]]
    selection, _ = select_shop(state, "condition", shops, settings, Decimal(0))
    product = selection[1].product
    assert product.name == "Servis motor"
    assert selection[1].total_cost == Decimal("1.5")
    await api.purchase(product.model_dump(mode="json"), "35", 20, "20", str(uuid4()))
    assert [json.loads(r.content)["item"] for r in api.calls if r.method == "POST"] == [
        "servis-motor"
    ]


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
    ui = HttpUI(settings, api=api)

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

    async def _buy(product, wallet, current, min_balance=5):
        return await call(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            request_id=ui.request_id,
            expected_wallet=str(wallet),
            expected_resource=current,
            min_balance=str(min_balance),
        )

    ui.buy = _buy
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
    ui = HttpUI(settings, api=api)

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

    async def _buy(product, wallet, current, min_balance=5):
        return await call(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            request_id=ui.request_id,
            expected_wallet=str(wallet),
            expected_resource=current,
            min_balance=str(min_balance),
        )

    ui.buy = _buy
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


async def test_need_value_counts_multiple_needs_without_overpaying_for_thresholds(
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
    assert plan.product.name == "Soto"

    world["shop"]["menu"][-1]["priceMilli"] = 100
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    _, plan = select_need(before, "makan", shops, settings, Decimal(0), {})
    assert plan.product.name == "Wedang jahe"

    limited = settings.model_copy(update={"max_spend": Decimal("0.7")})
    assert select_need(before, "makan", shops, limited, Decimal("0.65"), {}) is None
    world["shop"]["menu"][-1]["habis"] = "bahan"
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
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
        world["directory"].append({"plotId": plot, "name": name, "item": category, "x": 2, "y": 0})
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


async def test_need_rotates_available_akademis_shops_before_comparing_item_value(
    api, world, settings
):
    setup_food_catalog(world)
    other = add_food_supplier(world, "Akademis.ai Cabang", 1200)
    before = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    choice, _ = select_need(before, "makan", shops, settings, Decimal(0), {SHOP: 20, other: 10})
    assert choice.id == other
    limited = settings.model_copy(update={"max_spend": Decimal(1)})
    choice, _ = select_need(before, "makan", shops, limited, Decimal(0), {SHOP: 20, other: 10})
    assert choice.id == SHOP

    world["shops"][other]["menu"][0]["priceMilli"] = 700
    shops = [ShopPreview.model_validate(row) for row in (await api.preview("makan"))["shops"]]
    choice, _ = select_need(before, "makan", shops, settings, Decimal(0), {SHOP: 20, other: 10})
    assert choice.id == other


@pytest.mark.parametrize("status", ["in_stock", "closed", "own_shop", "empty_menu", "unknown"])
async def test_need_fallback_requires_akademis_unavailable(api, world, status):
    setup_food_catalog(world)
    for row in world["shop"]["menu"]:
        row["habis"] = "bahan"
    other = add_food_supplier(world, "Akademis.ai Cabang", 1200)
    fallback = add_food_supplier(world, "Warung cadangan", 100, fallback=True)
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
        assert preview["navigation"]["akademis_unavailable"] is (status != "in_stock")
        assert [shop["id"] for shop in preview["shops"]] == (
            [other] if status == "in_stock" else [fallback]
        )
    if status in {"in_stock", "unknown"}:
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
    assert preview["navigation"]["akademis_unavailable"] is True
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


async def test_need_directory_prioritizes_new_akademis_and_limits_fallback(api, world):
    setup_food_catalog(world)
    for row in world["shop"]["menu"]:
        row["habis"] = True
    preferred = add_food_supplier(world, "Akademis.ai Cabang Baru", 1100)
    location = world["need_locations"]["makan"].pop()
    world["directory"].append(
        {
            "plotId": location.plot_id,
            "item": location.category,
            "name": location.name,
            "x": 10,
            "y": 0,
        }
    )
    world["plot_details"][location.plot_id] = {
        "id": location.plot_id,
        "business": {
            "id": preferred,
            "name": location.name,
            "catalogId": location.category,
            "desa": "fixture-desa",
        },
    }
    fallback = add_food_supplier(world, "Usaha dekat", 100, fallback=True)
    assert [shop["id"] for shop in (await api.preview("makan"))["shops"]] == [preferred]
    world["shops"][preferred]["open"] = False
    assert [shop["id"] for shop in (await api.preview("makan"))["shops"]] == [fallback]
    world["directory"][-1]["x"] = 61
    assert (await api.preview("makan"))["shops"] == []
    assert all(request.method == "GET" for request in api.calls)


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
@pytest.mark.parametrize("price_milli", [0, 2000])
async def test_physical_facility_requires_matching_active_service_on_second_read(
    api, world, blocked, price_milli
):
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
                        "priceMilli": price_milli,
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
        "service": {"label": "Latihan", "priceMilli": price_milli, "open": True},
    }
    world["facilities"][facility_id] = details
    preview = await api.preview("fisik")
    product = preview["shops"][0]["products"][0]
    assert Decimal(product["price"]) == Decimal(price_milli) / 1000
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
        wallet = "5.49"
        world["me"]["balanceMilli"] = 5490
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

    ui = HttpUI(settings, api=api)
    ui.call_tool = call

    async def _buy(product, wallet, current, min_balance=5):
        return await call(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            request_id=ui.request_id,
            expected_wallet=str(wallet),
            expected_resource=current,
            min_balance=str(min_balance),
        )

    ui.buy = _buy
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
    ui = HttpUI(settings.model_copy(update={"core": "http"}), api=api)

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

    async def _buy(product, wallet, current, min_balance=5):
        return await call(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            request_id=ui.request_id,
            expected_wallet=str(wallet),
            expected_resource=current,
            min_balance=str(min_balance),
        )

    ui.buy = _buy
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
    ui = HttpUI(settings, api=api)

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

    async def _buy(product, wallet, current, min_balance=5):
        return await call(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            request_id=ui.request_id,
            expected_wallet=str(wallet),
            expected_resource=current,
            min_balance=str(min_balance),
        )

    ui.buy = _buy
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


async def test_stop_cancels_waiting_http_tool_without_repeating(api, settings):
    import asyncio

    from ojol.controller import StopRequested

    ui = HttpUI(settings, api=api)

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


@pytest.mark.parametrize(
    "outcome",
    [
        "valid",
        "rejected",
        "expired",
        "wrong_schema",
        "missing_nickname",
        "invalid_nickname",
        "negative_balance",
    ],
)
async def test_http_cookie_import_is_atomic_and_preserves_old_session_on_failure(
    settings, monkeypatch, outcome
):
    import ojol.http_api as module
    import ojol.session_transfer as transfer

    settings = settings.model_copy(update={"core": "http", "env": "local"})
    previous = transfer.parse_cookie_input("old-isolated-fixture")
    payload = transfer.parse_cookie_input("new-isolated-fixture")
    if outcome == "expired":
        payload["cookies"][0]["expires"] = 1
    active = settings.runtime_dir / "http-session.json"
    write_private(active, previous)
    save_profile(
        settings.runtime_dir,
        verified_profile({"profile": {"nickname": "Old Nick"}, "balanceMilli": 40000}),
    )

    async def verify(path):
        assert path == "/api/game/me"
        pending = settings.runtime_dir / "http-session.pending.json"
        assert pending.stat().st_mode & 0o777 == 0o600
        assert json.loads(active.read_text()) == previous
        if outcome == "rejected":
            raise HttpCoreError("Fixture session rejected", category="auth")
        if outcome == "wrong_schema":
            return {}
        return {
            "balanceMilli": -1 if outcome == "negative_balance" else 35000,
            "profile": {}
            if outcome == "missing_nickname"
            else {"nickname": "Bad\nNick" if outcome == "invalid_nickname" else "Game Nick"},
        }

    core = SimpleNamespace(request=verify)
    context = AsyncMock()
    context.__aenter__.return_value = core
    monkeypatch.setattr(module, "OjolHttpApi", lambda *args, **kwargs: context)
    monkeypatch.setattr(transfer, "flush_notices", AsyncMock())
    monkeypatch.setattr(transfer, "queue_notice", Mock())
    if outcome == "valid":
        profile = await transfer.import_session(settings, json.dumps(payload))
        assert profile["nickname"] == "Game Nick"
        assert transfer.queue_notice.call_args.args[0].account_name == "Game Nick"
        assert "Saldo profil • 35 koin" in transfer.queue_notice.call_args.args[1]
    else:
        with pytest.raises(HttpCoreError):
            await transfer.import_session(settings, json.dumps(payload))
    assert json.loads(active.read_text()) == (payload if outcome == "valid" else previous)
    assert not (settings.runtime_dir / "http-session.pending.json").exists()
    assert cached_profile(settings.runtime_dir)["nickname"] == (
        "Game Nick" if outcome == "valid" else "Old Nick"
    )
    if outcome == "expired":
        context.__aenter__.assert_not_awaited()


async def test_worker_snapshot_refreshes_cached_game_nickname_and_balance(api, world, settings):
    world["me"]["profile"] = {"nickname": "Game Nick"}
    await api.snapshot()
    assert cached_profile(settings.runtime_dir)["nickname"] == "Game Nick"
    assert cached_profile(settings.runtime_dir)["balanceMilli"] == 35000
    world["me"]["profile"]["nickname"] = "Changed In Game"
    await api.snapshot()
    assert cached_profile(settings.runtime_dir)["nickname"] == "Changed In Game"
    assert (settings.runtime_dir / "game-profile.json").stat().st_mode & 0o777 == 0o600


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


async def test_bpjs_auto_buy_when_not_owned(api, world, monkeypatch):
    kantor_id = "5149bd70-4b0b-4b4e-be2e-839b7099f8dc"
    monkeypatch.setattr("ojol.http_api.BPJS_KANTOR_BY_VILLAGE", {"fixture-desa": kantor_id})
    bpjs_state = {
        "rules": {"iuranMilli": 5000, "masaHari": 30, "gratisPerHari": 1},
        "kartu": None,
        "gratisSisa": 0,
        "walletMilli": 15000,
    }
    world["extra_responses"] = {"/api/bpjs": bpjs_state}
    paid = False

    def handle_pay(req):
        nonlocal paid
        body = json.loads(req.content)
        assert body["projectId"] == kantor_id
        assert "requestId" in body
        paid = True
        bpjs_state["kartu"] = {"noKartu": "0001", "aktif": True, "sisaHari": 30}
        bpjs_state["gratisSisa"] = 1
        return {"ok": True}

    world["post_responses"] = {"/api/bpjs/bayar": handle_pay}
    res = await api.ensure_bpjs()
    assert paid
    assert res["kartu"]["aktif"] is True
    assert res["gratisSisa"] == 1


async def test_kesehatan_free_checkup_at_puskesmas_with_tensi_minigame(api, world, monkeypatch):
    puskesmas_id = "2ff500f4-fe31-438b-be99-801eb4e6b363"
    monkeypatch.setattr(
        "ojol.http_api.HEALTH_FACILITIES_BY_VILLAGE", {"fixture-desa": (puskesmas_id,)}
    )
    world["needs"].update(enabled=True, needs=[{"id": "kesehatan", "value": 50}])
    bpjs_state = {
        "rules": {"iuranMilli": 5000, "masaHari": 30, "gratisPerHari": 1},
        "kartu": {"noKartu": "0001", "aktif": True, "sisaHari": 30},
        "gratisSisa": 1,
        "walletMilli": 35000,
    }
    facility_data = {
        "id": puskesmas_id,
        "title": "Puskesmas Desa",
        "state": "DONE",
        "nextAt": None,
        "myVisitUntil": None,
        "service": {
            "label": "Pemeriksaan tensi darah",
            "priceMilli": 0,
            "open": True,
        },
    }
    visit_id = str(uuid4())
    kegiatan_data = {
        "available": True,
        "visitId": visit_id,
        "kind": "tensi",
        "plan": {"periods": [1000, 1200, 1100], "lead_ms": 0},
    }
    world["extra_responses"] = {
        "/api/bpjs": bpjs_state,
        f"/api/facilities/{puskesmas_id}": facility_data,
        f"/api/facilities/{puskesmas_id}/kegiatan": kegiatan_data,
    }
    tensi_submitted = False

    def handle_kegiatan(req):
        nonlocal tensi_submitted
        body = json.loads(req.content)
        assert body["visitId"] == visit_id
        assert body["stops"] == [250, 300, 275]
        tensi_submitted = True
        return {"score": 3, "maxScore": 3, "bonus": 1, "bonusGains": {"kesehatan": 10}}

    world["post_responses"] = {
        f"/api/facilities/{puskesmas_id}/use": {"id": visit_id, "ok": True},
        f"/api/facilities/{puskesmas_id}/kegiatan": handle_kegiatan,
    }

    data = await api.preview("kesehatan")
    shops = data["shops"]
    assert len(shops) == 1
    assert shops[0]["id"] == puskesmas_id
    assert shops[0]["products"][0]["price"] == "0"

    product = shops[0]["products"][0]
    await api.purchase(product, "35", 50, "20", str(uuid4()))
    assert tensi_submitted


async def test_kesehatan_free_checkup_at_rs_with_detak_minigame(api, world, monkeypatch):
    rs_id = "dbc8fb79-43d3-4b75-b3ab-dac2d0c17b10"
    monkeypatch.setattr("ojol.http_api.HEALTH_FACILITIES_BY_VILLAGE", {"fixture-desa": (rs_id,)})
    world["needs"].update(enabled=True, needs=[{"id": "kesehatan", "value": 50}])
    bpjs_state = {
        "rules": {"iuranMilli": 5000, "masaHari": 30, "gratisPerHari": 1},
        "kartu": {"noKartu": "0001", "aktif": True, "sisaHari": 30},
        "gratisSisa": 1,
        "walletMilli": 35000,
    }
    facility_data = {
        "id": rs_id,
        "title": "Rumah Sakit Desa",
        "state": "DONE",
        "nextAt": None,
        "myVisitUntil": None,
        "service": {
            "label": "Pemeriksaan detak jantung",
            "priceMilli": 0,
            "open": True,
        },
    }
    visit_id = str(uuid4())
    kegiatan_data = {
        "available": True,
        "visitId": visit_id,
        "kind": "detak",
        "plan": {"beats": [500, 1000, 1500], "bpm": 72},
    }
    world["extra_responses"] = {
        "/api/bpjs": bpjs_state,
        f"/api/facilities/{rs_id}": facility_data,
        f"/api/facilities/{rs_id}/kegiatan": kegiatan_data,
    }
    detak_submitted = False

    def handle_kegiatan(req):
        nonlocal detak_submitted
        body = json.loads(req.content)
        assert body["visitId"] == visit_id
        assert body["taps"] == [500, 1000, 1500]
        detak_submitted = True
        return {"score": 3, "maxScore": 3, "bonus": 1, "bonusGains": {"kesehatan": 10}}

    world["post_responses"] = {
        f"/api/facilities/{rs_id}/use": {"id": visit_id, "ok": True},
        f"/api/facilities/{rs_id}/kegiatan": handle_kegiatan,
    }

    data = await api.preview("kesehatan")
    shops = data["shops"]
    assert len(shops) == 1
    assert shops[0]["id"] == rs_id
    assert shops[0]["products"][0]["price"] == "0"

    product = shops[0]["products"][0]
    await api.purchase(product, "35", 50, "20", str(uuid4()))
    assert detak_submitted


async def test_kesehatan_fallback_to_medicine_when_no_free_quota(api, world, monkeypatch):
    puskesmas_id = "2ff500f4-fe31-438b-be99-801eb4e6b363"
    monkeypatch.setattr(
        "ojol.http_api.HEALTH_FACILITIES_BY_VILLAGE", {"fixture-desa": (puskesmas_id,)}
    )
    bpjs_state = {
        "rules": {"iuranMilli": 5000, "masaHari": 30, "gratisPerHari": 1},
        "kartu": {"noKartu": "0001", "aktif": True, "sisaHari": 30},
        "gratisSisa": 0,
        "walletMilli": 35000,
    }
    world["needs"].update(enabled=True, needs=[{"id": "kesehatan", "value": 50}])
    world["need_effects"].update(
        {
            "nasi-goreng": {"makan": 35},
            "tambal-ban": {"kendaraan": 30},
            "pulsa": {"kuota": 30},
            "obat-flu": {"kesehatan": 25},
        }
    )
    toko_id = "00000000-0000-4000-8000-000000000999"
    toko_shop = NeedShop(toko_id, "K40-U06", "Akademis.ai Farma", "toko-obat")
    world["need_locations"]["kesehatan"] = (toko_shop,)
    monkeypatch.setattr(
        "ojol.http_api.NEED_SHOPS_BY_VILLAGE", {"fixture-desa": {"kesehatan": (toko_shop,)}}
    )
    world["shops"][toko_id] = {
        "mine": False,
        "open": True,
        "plang": "Akademis.ai Farma",
        "menu": [{"item": "obat-flu", "name": "Obat flu", "priceMilli": 1500}],
    }
    world["extra_responses"] = {"/api/bpjs": bpjs_state}

    data = await api.preview("kesehatan")
    shops = data["shops"]
    assert len(shops) == 1
    assert shops[0]["id"] == toko_id
    assert shops[0]["name"] == "Akademis.ai Farma"
    assert shops[0]["products"][0]["name"] == "Obat flu"


@pytest.mark.parametrize("gain", [None, True, -1, 101, "36"])
async def test_need_taste_effect_rejects_malformed_values(api, world, gain):
    setup_food_catalog(world)
    world["shop"]["menu"][0]["rasa"] = {"isi": {"makan": gain}}
    with pytest.raises(HttpCoreError, match="selera"):
        await api.preview("makan")
    assert all(request.method == "GET" for request in api.calls)


@pytest.mark.parametrize("resource", ["makan", "rekreasi"])
async def test_need_taste_effect_drives_value_and_is_rechecked_before_purchase(
    api, world, settings, resource
):
    setup_food_catalog(world)
    world["needs"]["needs"].append({"id": "rekreasi", "value": 67})
    if resource == "rekreasi":
        world["needs"]["needs"][-1]["value"] = 55
        world["need_locations"]["rekreasi"] = world["need_locations"]["makan"]
    row = world["shop"]["menu"][0]
    row["rasa"] = {"isi": {"makan": 63, "rekreasi": 5}}
    before = await api.snapshot()
    shops = [ShopPreview.model_validate(row) for row in (await api.preview(resource))["shops"]]
    _, plan = select_need(before, resource, shops, settings, Decimal(0), {})
    assert plan.product.name == "Nasi goreng"
    assert plan.product.effects == {"makan": 63, "rekreasi": 5}
    row["rasa"]["isi"]["makan"] = 35
    with pytest.raises(HttpCoreError) as error:
        await api.purchase(plan.product.model_dump(mode="json"), "35", 55, "20", str(uuid4()))
    assert error.value.category == "rejected"
    assert all(request.method == "GET" for request in api.calls)


async def test_physical_value_uses_verified_secondary_effects_and_refreshes_old_cache(
    api, world, settings
):
    world["facility_effects"] = {
        "gym-desa": {"fisik": 55, "kesehatan": 15},
        "kolam-renang": {"fisik": 50, "rekreasi": 15},
    }
    places = []
    for item, gain in [("gym-desa", 55), ("kolam-renang", 50)]:
        identifier = str(uuid4())
        places.append(
            {
                "id": identifier,
                "name": item,
                "kind": "fasum",
                "open": True,
                "priceMilli": 2000,
                "gain": gain,
            }
        )
        world["facilities"][identifier] = {
            "id": identifier,
            "item": item,
            "state": "DONE",
            "nextAt": None,
            "service": {"label": item, "priceMilli": 2000, "open": True},
        }
    world["needs"].update(
        enabled=True,
        needs=[
            {"id": "fisik", "value": 25, "places": places},
            {"id": "kesehatan", "value": 99},
            {"id": "rekreasi", "value": 20},
        ],
    )
    write_private(
        api.directory / "http-effects.json",
        {
            "version": "fixture-v1",
            "effects": EFFECTS,
            "needs_effects": {"gym-desa": {"fisik": 55}},
        },
    )
    before = await api.snapshot()
    preview = await api.preview("fisik")
    shops = [ShopPreview.model_validate(row) for row in preview["shops"]]
    gym = next(shop for shop in shops if shop.name == "gym-desa")
    assert gym.products[0].effects == {"fisik": 55, "kesehatan": 15}
    supplier, plan = select_need(before, "fisik", shops, settings, Decimal(0), {})
    assert supplier.name == "kolam-renang"
    assert plan.product.effects == {"fisik": 50, "rekreasi": 15}
    await api.purchase(plan.product.model_dump(mode="json"), "35", 25, "20", str(uuid4()))
    assert sum(request.method == "POST" for request in api.calls) == 1
    places[1]["gain"] = 40
    await api.snapshot()
    preview = await api.preview("fisik")
    pool = next(shop for shop in preview["shops"] if shop["name"] == "kolam-renang")
    assert pool["products"][0]["effects"] == {"fisik": 40}


async def test_garden_status_and_actions_in_http_api(api, world):
    garden_id = "garden-sayur-1"
    now_str = "2026-11-19T10:00:00Z"
    world.setdefault("extra_responses", {})["/api/daily/garden"] = {
        "now": now_str,
        "gardens": [
            {
                "id": garden_id,
                "kind": "kebun-sayur",
                "label": "Kebun sayur",
                "state": "siap",
                "readyAt": now_str,
                "cared": False,
                "seedMilli": 300,
            }
        ],
    }

    status = await api.garden_status()
    assert status["gardens"][0]["id"] == garden_id

    # Test panen action
    res_panen = await api.garden_action(garden_id, "panen")
    assert res_panen.get("ok") is True

    # Test rawat action
    res_rawat = await api.garden_action(garden_id, "rawat")
    assert res_rawat.get("ok") is True

    # Test tanam action
    res_tanam = await api.garden_action(garden_id, "tanam")
    assert res_tanam.get("ok") is True

    # Invalid action raises ValueError
    with pytest.raises(ValueError):
        await api.garden_action(garden_id, "invalid")


async def test_physical_facility_with_angkat_beban_minigame(api, world):
    api.minigame_wait_multiplier = 0.0
    gym_id = str(uuid4())
    world["needs"].update(
        enabled=True,
        needs=[
            {
                "id": "fisik",
                "value": 30,
                "places": [
                    {
                        "id": gym_id,
                        "name": "Gym desa 2",
                        "kind": "fasum",
                        "open": True,
                        "priceMilli": 2000,
                        "gain": 55,
                    }
                ],
            }
        ],
    )
    # Facility on cooldown for normal service (nextAt is set), matching user screenshot
    world["facilities"][gym_id] = {
        "id": gym_id,
        "item": "gym-desa",
        "title": "Gym desa 2",
        "state": "DONE",
        "nextAt": "2026-11-19T21:18:00Z",
        "service": {"label": "Latihan gym", "priceMilli": 2000, "open": True},
    }
    minigame_status = {
        "game": "gym",
        "name": "Angkat beban",
        "icon": "🏋️",
        "playsLeft": 3,
        "playsPerDay": 3,
        "maxRewardMilli": 1000,
        "kebutuhan": {"fisik": 15},
    }
    world.setdefault("extra_responses", {})[f"/api/minigame?projectId={gym_id}&game=gym"] = (
        minigame_status
    )

    play_id = str(uuid4())
    start_resp = {
        "playId": play_id,
        "plan": {
            "reps": [
                {"fill": 1400, "center": 0.72, "half": 0.09},
                {"fill": 1200, "center": 0.65, "half": 0.10},
            ]
        },
    }
    finish_resp = {
        "playId": play_id,
        "game": "gym",
        "score": 4,
        "rewardMilli": 240,
        "detail": {
            "reps": [{"points": 2, "outcome": "sempurna"}, {"points": 2, "outcome": "sempurna"}],
            "kebutuhan": {"fisik": 15},
            "invalid": False,
            "expired": False,
        },
    }

    start_called = False
    finish_called = False

    def handle_minigame_post(req):
        nonlocal start_called, finish_called
        body = json.loads(req.content)
        if body.get("action") == "start":
            assert body["projectId"] == gym_id
            assert body["game"] == "gym"
            start_called = True
            return start_resp
        if body.get("action") == "finish":
            assert body["playId"] == play_id
            # round(1400 * 0.72) = 1008, round(1200 * 0.65) = 780
            assert body["holds"] == [1008, 780]
            finish_called = True
            return finish_resp
        raise ValueError(f"Unknown action: {body.get('action')}")

    world.setdefault("post_responses", {})["/api/minigame"] = handle_minigame_post

    preview = await api.preview("fisik")
    shops = preview["shops"]
    assert len(shops) == 1
    assert shops[0]["id"] == gym_id
    assert len(shops[0]["products"]) == 1
    product = shops[0]["products"][0]
    assert product["name"] == "Angkat beban"
    assert Decimal(product["price"]) == Decimal(0)
    assert product["effects"] == {"fisik": 15}

    receipt = await api.purchase(product, "35", 30, "20", str(uuid4()))
    assert start_called
    assert finish_called
    assert receipt["score"] == 4
    assert receipt["rewardMilli"] == 240


async def test_physical_facility_angkat_beban_quota_exhausted_fallback(api, world):
    api.minigame_wait_multiplier = 0.0
    gym_id = str(uuid4())
    world["needs"].update(
        enabled=True,
        needs=[
            {
                "id": "fisik",
                "value": 30,
                "places": [
                    {
                        "id": gym_id,
                        "name": "Gym desa 2",
                        "kind": "fasum",
                        "open": True,
                        "priceMilli": 2000,
                        "gain": 55,
                    }
                ],
            }
        ],
    )
    # When playsLeft is 0 and nextAt is None, regular service is used
    world["facilities"][gym_id] = {
        "id": gym_id,
        "item": "gym-desa",
        "title": "Gym desa 2",
        "state": "DONE",
        "nextAt": None,
        "service": {"label": "Latihan gym", "priceMilli": 2000, "open": True},
    }
    world.setdefault("extra_responses", {})[f"/api/minigame?projectId={gym_id}&game=gym"] = {
        "game": "gym",
        "name": "Angkat beban",
        "icon": "🏋️",
        "playsLeft": 0,
        "playsPerDay": 3,
        "maxRewardMilli": 1000,
        "kebutuhan": {"fisik": 15},
    }

    preview = await api.preview("fisik")
    shops = preview["shops"]
    assert len(shops) == 1
    assert len(shops[0]["products"]) == 1
    assert shops[0]["products"][0]["name"] == "Latihan gym"
    assert Decimal(shops[0]["products"][0]["price"]) == Decimal(2)


async def test_physical_facility_angkat_beban_invalid_rejected(api, world):
    api.minigame_wait_multiplier = 0.0
    gym_id = str(uuid4())
    world["needs"].update(
        enabled=True,
        needs=[
            {
                "id": "fisik",
                "value": 30,
                "places": [
                    {
                        "id": gym_id,
                        "name": "Gym desa 2",
                        "kind": "fasum",
                        "open": True,
                        "priceMilli": 2000,
                        "gain": 55,
                    }
                ],
            }
        ],
    )
    world["facilities"][gym_id] = {
        "id": gym_id,
        "item": "gym-desa",
        "title": "Gym desa 2",
        "state": "DONE",
        "nextAt": None,
        "service": {"label": "Latihan gym", "priceMilli": 2000, "open": True},
    }
    world.setdefault("extra_responses", {})[f"/api/minigame?projectId={gym_id}&game=gym"] = {
        "game": "gym",
        "name": "Angkat beban",
        "icon": "🏋️",
        "playsLeft": 1,
        "playsPerDay": 3,
        "maxRewardMilli": 1000,
        "kebutuhan": {"fisik": 15},
    }
    play_id = str(uuid4())
    world.setdefault("post_responses", {})["/api/minigame"] = lambda req: (
        {"playId": play_id, "plan": [{"fill": 1000, "center": 0.5, "half": 0.1}]}
        if json.loads(req.content).get("action") == "start"
        else {
            "playId": play_id,
            "game": "gym",
            "score": 0,
            "rewardMilli": 0,
            "detail": {"invalid": True},
        }
    )

    preview = await api.preview("fisik")
    product = preview["shops"][0]["products"][0]
    assert product["name"] == "Angkat beban"

    with pytest.raises(HttpCoreError) as exc:
        await api.purchase(product, "35", 30, "20", str(uuid4()))
    assert exc.value.category == "rejected"
    assert "terlalu cepat" in str(exc.value)


async def test_hardcoded_gym_included_and_prioritized_over_paid_gym(
    api, world, settings, monkeypatch
):
    gym_id = str(uuid4())
    monkeypatch.setattr("ojol.http_api.GYM_FACILITIES_BY_VILLAGE", {"fixture-desa": (gym_id,)})
    # physical_places in world["needs"] does NOT include the gym (e.g. only contains badminton)
    other_id = str(uuid4())
    world["needs"].update(
        enabled=True,
        needs=[
            {
                "id": "fisik",
                "value": 40,
                "places": [
                    {
                        "id": other_id,
                        "name": "GOR badminton",
                        "kind": "fasum",
                        "open": True,
                        "priceMilli": 2000,
                        "gain": 50,
                    }
                ],
            }
        ],
    )
    world["facilities"][other_id] = {
        "id": other_id,
        "item": "gor-badminton",
        "title": "GOR badminton",
        "state": "DONE",
        "nextAt": None,
        "service": {"label": "Main badminton", "priceMilli": 2000, "open": True},
    }
    world["facilities"][gym_id] = {
        "id": gym_id,
        "item": "gym-desa",
        "title": "Gym desa fixture",
        "state": "DONE",
        "nextAt": None,
        "service": {"label": "Latihan gym", "priceMilli": 2000, "open": True},
    }
    world.setdefault("extra_responses", {})[f"/api/minigame?projectId={gym_id}&game=gym"] = {
        "game": "gym",
        "name": "Angkat beban",
        "icon": "🏋️",
        "playsLeft": 2,
        "playsPerDay": 3,
        "maxRewardMilli": 1000,
        "kebutuhan": {"fisik": 15},
    }

    # Verify hardcoded gym is included in preview shops even if not in needs.places
    preview = await api.preview("fisik")
    shops = [ShopPreview.model_validate(row) for row in preview["shops"]]
    shop_ids = [s.id for s in shops]
    assert gym_id in shop_ids
    assert other_id in shop_ids

    # select_need prioritizes minigame "Angkat beban" over paid gym and other fasum
    before = await api.snapshot()
    selected_shop, plan = select_need(before, "fisik", shops, settings, Decimal(0), {})
    assert selected_shop.id == gym_id
    assert plan.product.name == "Angkat beban"
    assert plan.total_cost == Decimal(0)


async def test_snapshot_handles_ojol_daily_8_hour_limit(api, world):
    world["ojol"].update(
        problem="Mitra ojol bisa narik paling lama 8 jam per hari, lanjut besok mulai jam 00.00.",
        fix=None,
        sisaJam=0,
    )
    state = await api.snapshot()
    assert state.ojol_shift_done is True
    assert state.ojol_hours_left == 0.0
    assert "8 jam per hari" in state.raw_text
    assert "Berhenti jadi mitra ojol" in state.buttons


async def test_snapshot_tracks_ojol_remaining_hours(api, world):
    world["ojol"].update(sisaJam=4.5)
    state = await api.snapshot()
    assert state.ojol_shift_done is False
    assert state.ojol_hours_left == 4.5


async def test_kamar_mandi_wc_preview_and_purchase(api, world):
    world["needs"].update(
        enabled=True,
        needs=[
            {"id": "wc", "name": "Buang air", "value": 0, "label": "Kebelet sekali"},
            {"id": "kebersihan", "name": "Kebersihan", "value": 10, "label": "Bau sekali"},
        ],
        kondisi={"bau": True, "kebelet": True, "upahPotongBps": 1000},
        bersih={"mandi": 0, "sikat": 0, "mandiMaks": 2, "sikatMaks": 3, "aktif": True},
    )
    preview = await api.preview("wc")
    shops = preview["shops"]
    assert len(shops) == 1
    assert shops[0]["category"] == "kamar-mandi"
    product = shops[0]["products"][0]
    assert product["name"] == "Buang air di kloset"
    assert Decimal(product["price"]) == Decimal(0)
    assert product["effects"]["wc"] == 100

    wc_posted = []
    world.setdefault("post_responses", {})["/api/rumah/kamar-mandi"] = lambda req: (
        wc_posted.append(json.loads(req.content)),
        {"isi": 100, "wc": 100, "detik": 5},
    )[1]

    # Purchase WC
    before = await api.snapshot()
    assert before.needs["wc"] == 0
    receipt = await api.purchase(product, str(before.wallet), before.needs["wc"], "5", str(uuid4()))
    assert receipt["isi"] == 100
    assert any(p.get("aksi") == "wc" for p in wc_posted)


async def test_kamar_mandi_kebersihan_preview_and_purchase(api, world):
    world["needs"].update(
        enabled=True,
        needs=[
            {"id": "kebersihan", "name": "Kebersihan", "value": 15, "label": "Bau"},
        ],
        kondisi={"bau": True, "kebelet": False, "upahPotongBps": 1000},
        bersih={"mandi": 1, "sikat": 0, "mandiMaks": 2, "sikatMaks": 3, "aktif": True},
    )
    preview = await api.preview("kebersihan")
    shops = preview["shops"]
    assert len(shops) == 1
    assert shops[0]["category"] == "kamar-mandi"
    product_names = [p["name"] for p in shops[0]["products"]]
    assert "Mandi di kamar mandi" in product_names
    assert "Sikat gigi" in product_names

    posted = []
    world.setdefault("post_responses", {})["/api/rumah/kamar-mandi"] = lambda req: (
        posted.append(json.loads(req.content)),
        {"aksi": "mandi", "isi": 65, "kebersihan": 80},
    )[1]

    mandi_prod = next(p for p in shops[0]["products"] if p["name"] == "Mandi di kamar mandi")
    before = await api.snapshot()
    receipt = await api.purchase(
        mandi_prod, str(before.wallet), before.needs["kebersihan"], "5", str(uuid4())
    )
    assert receipt["aksi"] == "mandi"
    assert any(p.get("aksi") == "mandi" for p in posted)


async def test_penampilan_fallback_kampung_sebelah(api, world):
    setup_food_catalog(world)
    world["needs"]["needs"].append({"id": "penampilan", "name": "Penampilan", "value": 0})
    world["me"]["home"]["desa"] = "kampung-sebelah"
    await api.snapshot()
    shop_id = "57458327-df64-483f-8904-0ec40bfc28fe"
    world["directory"].append(
        {
            "plotId": "S09-U09",
            "item": "barbershop",
            "name": "Cukur Sisi Jalan",
            "x": 10,
            "y": 0,
        }
    )
    world["plot_details"]["S09-U09"] = {
        "id": "S09-U09",
        "business": {
            "id": shop_id,
            "catalogId": "barbershop",
            "name": "Cukur Sisi Jalan",
            "desa": "kampung-sebelah",
        },
    }
    world["shops"][shop_id] = {
        "mine": False,
        "open": True,
        "plang": "Cukur Sisi Jalan",
        "menu": [
            {"item": "potong-rambut", "name": "Potong rambut", "priceMilli": 1000, "service": True},
        ],
    }
    world["need_effects"]["potong-rambut"] = {"penampilan": 60}

    preview = await api.preview("penampilan")
    shops = preview["shops"]
    assert len(shops) == 1
    assert shops[0]["name"] == "Cukur Sisi Jalan"
    assert shops[0]["products"][0]["name"] == "Potong rambut"
    assert Decimal(shops[0]["products"][0]["price"]) == Decimal(1)

    bought = []
    world.setdefault("post_responses", {})[f"/api/shops/{shop_id}/buy"] = lambda req: (
        bought.append(json.loads(req.content)),
        {"ok": True, "penampilan": 60},
    )[1]

    prod = shops[0]["products"][0]
    before = await api.snapshot()
    receipt = await api.purchase(
        prod, str(before.wallet), before.needs.get("penampilan", 0), "5", str(uuid4())
    )
    assert receipt["ok"] is True
    assert any(b.get("item") == "potong-rambut" for b in bought)


async def test_ojol_failure_continues_auto_kebutuhan(api, world, settings):
    from ojol.auto_settings import auto_flags

    # Ojol is broken / not a partner
    world["ojol"] = {"enabled": False, "mitra": False, "problem": "Bukan mitra ojol"}
    world["needs"].update(
        enabled=True,
        needs=[
            {"id": "wc", "name": "Buang air", "value": 0, "label": "Kebelet"},
            {"id": "kebersihan", "name": "Kebersihan", "value": 15, "label": "Bau"},
        ],
        kondisi={"bau": True, "kebelet": True, "upahPotongBps": 1000},
        bersih={"mandi": 1, "sikat": 0, "mandiMaks": 2, "sikatMaks": 3, "aktif": True},
    )
    set_auto_flag(settings.runtime_dir, "ojol", True)
    set_auto_flag(settings.runtime_dir, "wc", True)
    set_auto_flag(settings.runtime_dir, "kebersihan", True)

    km_posted = []

    def handle_km(req):
        body = json.loads(req.content)
        km_posted.append(body)
        if body.get("aksi") == "wc":
            for n in world["needs"]["needs"]:
                if n["id"] == "wc":
                    n["value"] = 100
            return {"isi": 100, "wc": 100}
        if body.get("aksi") == "mandi":
            for n in world["needs"]["needs"]:
                if n["id"] == "kebersihan":
                    n["value"] = 80
            return {"isi": 65, "kebersihan": 80}
        return {"ok": True}

    world.setdefault("post_responses", {})["/api/rumah/kamar-mandi"] = handle_km

    ui = HttpUI(settings, api=api)
    with closing(Journal(settings.runtime_dir)) as journal:
        controller = Controller(ui, settings, journal, journal.start(settings))
        # After completing need action, let next wait terminate the loop
        controller.wait = AsyncMock(side_effect=StopRequested("done"))
        with pytest.raises(StopRequested):
            await controller.run()

        # Check: Ojol was disabled because it failed
        flags = auto_flags(settings.runtime_dir)
        assert flags["ojol"] is False
        assert flags["wc"] is True
        assert flags["kebersihan"] is True

        # Check: WC need was fulfilled automatically
        assert any(p.get("aksi") == "wc" for p in km_posted)
        actions = journal.history()["actions"]
        assert any(a["kind"] == "purchase" and a["status"] == "verified" for a in actions)
