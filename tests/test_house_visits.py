import json
from unittest.mock import AsyncMock

import httpx
import pytest

from ojol.cleanup import find_unvisited
from ojol.control import ControlService
from ojol.http_api import ORIGIN, HouseUnavailable, HttpCoreError, OjolHttpApi


def houses():
    return [
        {"id": "K40-R01", "k": "R", "s": "O", "x": 0, "y": 0, "w": {"n": "Sendiri"}},
        {"id": "K40-R02", "k": "R", "s": "O", "x": 1, "y": 0, "w": {"n": "Sudah"}},
        {"id": "L40-R03", "k": "R", "s": "O", "x": 3, "y": 0, "w": {"n": "Tetangga"}},
        {"id": "L40-R03", "k": "R", "s": "O", "x": 3, "y": 0, "w": {"n": "Tetangga"}},
        {"id": "K40-R04", "k": "R", "s": "O", "x": 0, "y": 0, "w": {"n": "Sendiri"}},
        {"id": "K40-R05", "k": "R", "s": "O", "x": 5, "y": 0, "e": True, "w": {"n": "X"}},
        {"id": "K40-R06", "k": "R", "s": "O", "x": 6, "y": 0},
        {"id": "K40-R07", "k": "R", "s": "K", "x": 7, "y": 0, "w": {"n": "X"}},
        {"id": "K40-U01", "k": "U", "s": "O", "x": 8, "y": 0, "w": {"n": "X"}},
        {"id": "Z99-R01", "k": "R", "s": "O", "x": 9, "y": 0, "w": {"n": "X"}},
    ]


@pytest.mark.parametrize("visited", [False, True])
async def test_find_unvisited_uses_current_account_status_not_dirty_flag(
    settings, monkeypatch, visited
):
    calls = []
    monkeypatch.setattr("ojol.cleanup.shuffle", lambda value: None)

    def handle(request):
        assert request.method == "GET"
        calls.append(request)
        if request.url.path == "/api/game/me":
            return httpx.Response(
                200, json={"home": {"plotId": "K40-R01", "block": "K40", "x": 0, "y": 0}}
            )
        if request.url.path == "/api/world/plots":
            assert "L40" in request.url.params["blocks"].split(",")
            return httpx.Response(200, json={"plots": houses()})
        if request.url.path == "/api/rumah/interior/lihat":
            return httpx.Response(200, json={"bentuk": "standar", "layout": []})
        assert request.url.path == "/api/daily/house"
        return httpx.Response(
            200,
            json={"visitedToday": True if request.url.params["plotId"] == "K40-R02" else visited},
        )

    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        result = await find_unvisited(OjolHttpApi(settings.runtime_dir, client=client))
    if visited:
        assert result is None
    else:
        assert result == {"plot_id": "L40-R03", "x": 3, "y": 0, "nickname": "Tetangga"}
    assert [r.url.params["plotId"] for r in calls if r.url.path == "/api/daily/house"] == [
        "K40-R02",
        "L40-R03",
    ]
    assert sum(r.url.path == "/api/rumah/interior/lihat" for r in calls) == (0 if visited else 1)


@pytest.mark.parametrize("open_neighbor", [False, True])
async def test_unvisited_closed_house_is_skipped_without_requesting_login(
    settings, monkeypatch, open_neighbor
):
    monkeypatch.setattr("ojol.cleanup.shuffle", lambda value: None)
    checked = []

    def handle(request):
        assert request.method == "GET"
        if request.url.path == "/api/game/me":
            return httpx.Response(
                200, json={"home": {"plotId": "K40-R01", "block": "K40", "x": 0, "y": 0}}
            )
        if request.url.path == "/api/world/plots":
            return httpx.Response(200, json={"plots": houses()})
        if request.url.path == "/api/daily/house":
            return httpx.Response(200, json={"visitedToday": False})
        assert request.url.path == "/api/rumah/interior/lihat"
        checked.append(request.url.params["plotId"])
        if open_neighbor and checked[-1] == "L40-R03":
            return httpx.Response(200, json={"bentuk": "standar", "layout": []})
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "🕘 Rumah ini menerima tamu jam 06.00–21.00 WIB. Datang lagi nanti, ya.",
                }
            },
        )

    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        house = await find_unvisited(OjolHttpApi(settings.runtime_dir, client=client))
    assert checked == ["K40-R02", "L40-R03"]
    assert (house["plot_id"] if house else None) == ("L40-R03" if open_neighbor else None)


@pytest.mark.parametrize(
    "interior", [None, {}, {"layout": []}, {"bentuk": "standar", "layout": None}]
)
async def test_unknown_house_access_is_never_offered(interior, monkeypatch):
    monkeypatch.setattr("ojol.cleanup.shuffle", lambda value: None)
    api = AsyncMock()
    api.request.side_effect = [
        {"home": {"plotId": "K40-R01", "block": "K40", "x": 0, "y": 0}},
        {"plots": houses()},
        {"visitedToday": False},
        interior,
    ]
    with pytest.raises(HttpCoreError, match="Status akses"):
        await find_unvisited(api)


@pytest.mark.parametrize(
    "path,status,code,expected",
    [
        ("/api/rumah/interior/lihat?plotId=K40-R02", 403, "FORBIDDEN", HouseUnavailable),
        ("/api/rumah/interior/lihat?plotId=K40-R02", 401, "UNAUTHENTICATED", HttpCoreError),
        ("/api/rumah/interior/lihat?plotId=K40-R02", 403, "UNAUTHENTICATED", HttpCoreError),
        ("/api/daily/house?plotId=K40-R02", 403, "FORBIDDEN", HttpCoreError),
    ],
)
async def test_house_access_denial_is_scoped_without_hiding_auth(
    settings, path, status, code, expected
):
    def handle(request):
        return httpx.Response(status, json={"error": {"code": code, "message": "fixture"}})

    async with httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(expected) as error:
            await OjolHttpApi(settings.runtime_dir, client=client).request(path)
    assert error.value.category == ("blocked" if expected is HouseUnavailable else "auth")


@pytest.mark.parametrize("status", [{}, {"visitedToday": "false"}, {"visitedToday": 0}, None])
async def test_unknown_visit_status_never_becomes_available(status, monkeypatch):
    monkeypatch.setattr("ojol.cleanup.shuffle", lambda value: None)
    api = AsyncMock()
    api.request.side_effect = [
        {"home": {"plotId": "K40-R01", "block": "K40", "x": 0, "y": 0}},
        {"plots": houses()},
        status,
    ]
    with pytest.raises(HttpCoreError, match="belum bisa dipastikan"):
        await find_unvisited(api)


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/daily/house?plotId=K40-R01&other=1", None),
        ("/api/daily/house?plotId=../secret", None),
        ("/api/daily/house?plotId=K40-R01", {}),
        ("/api/daily/visit", {"plotId": "K40-R01"}),
        ("/api/rumah/interior/lihat?plotId=../secret", None),
        ("/api/rumah/interior/lihat?plotId=K40-R01", {}),
    ],
)
async def test_visit_search_only_allows_valid_house_get(settings, path, payload):
    async with httpx.AsyncClient(
        base_url=ORIGIN,
        transport=httpx.MockTransport(lambda _: pytest.fail("Forbidden network call")),
    ) as client:
        api = OjolHttpApi(settings.runtime_dir, client=client)
        with pytest.raises(HttpCoreError, match="di luar izin"):
            await api.request(path, payload)


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (
            {"plot_id": "K40-R02", "x": 1, "y": 0, "nickname": "Tetangga"},
            "Menerima tamu sekarang dan belum kamu kunjungi hari ini",
        ),
        (None, "Belum ditemukan rumah"),
        (TimeoutError(), "responsnya terlalu lama"),
        (HttpCoreError("fixture", category="auth"), "Import Cookie"),
        (HttpCoreError("fixture"), "Respons game belum bisa dibaca"),
    ],
)
async def test_telegram_visit_search_messages_do_not_start_worker(
    settings, monkeypatch, outcome, expected
):
    service = ControlService(settings.model_copy(update={"env": "local"}))
    service.stop_worker = AsyncMock()
    context = AsyncMock()
    monkeypatch.setattr("ojol.control.OjolHttpApi", lambda *args: context)
    find = (
        AsyncMock(side_effect=outcome)
        if isinstance(outcome, Exception)
        else AsyncMock(return_value=outcome)
    )
    monkeypatch.setattr("ojol.control.find_unvisited", find)
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())
    await service.execute("visit_scan")
    notice = next((settings.runtime_dir / "notifications").glob("*.json"))
    data = json.loads(notice.read_text())
    assert expected in data["text"]
    if isinstance(outcome, Exception):
        assert data["context"]["error_id"] in data["text"]
    assert not (settings.runtime_dir / "STOP").exists()
    assert service.worker is None
    service.stop_worker.assert_not_awaited()


async def test_visit_search_is_blocked_in_testing(settings, monkeypatch):
    api = AsyncMock()
    monkeypatch.setattr("ojol.control.OjolHttpApi", api)
    assert "diblokir" in await ControlService(settings).command("visit_scan")
    api.assert_not_called()
