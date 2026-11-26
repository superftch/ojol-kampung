import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.cli import main
from app.core.models import ROOT, Product, ShopPreview
from app.core.storage import write_private
from app.integrations.kampung.http_api import OjolHttpApi
from app.main import ControlService
from app.modules.ledger.repository import Journal
from app.modules.worker.controller import Controller
from app.modules.worker.fleet import MultiAccountService
from app.modules.worker.settings import set_auto_flag
from app.modules.worker.ui import HttpUI
from tests.conftest import seed_legacy_account


@pytest.fixture
def session_file(settings):
    path = settings.runtime_dir / "http-session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    session_data = {
        "cookies": [
            {
                "name": "session",
                "value": "token-test",
                "domain": "www.kampungsebelah.com",
                "path": "/",
                "expires": time.time() + 3600,
            }
        ]
    }
    path.write_text(json.dumps(session_data))
    return path


async def test_ojol_http_api_fetch_online_status_success(settings, session_file):
    api = OjolHttpApi(settings.runtime_dir)
    api.request = AsyncMock()

    def mock_request(path, *args, **kwargs):
        if path == "/api/game/me":
            return {
                "configVersion": "v1",
                "balanceMilli": 25000,
                "home": {"desa": "desa-utara", "plotId": "K40-R04"},
                "profile": {
                    "nickname": "TesterOnline",
                    "resting": False,
                    "sleep": {"auto": False, "from": 120, "to": 300, "inSchedule": False},
                },
            }
        if path == "/api/time":
            return {"now": "2026-11-19T09:00:00.000Z"}
        if path == "/api/realtime/token":
            return {"url": "wss://realtime.kampungsebelah.com/ws"}
        raise ValueError(f"Unexpected path: {path}")

    api.request.side_effect = mock_request

    status = await api.fetch_online_status()

    assert status["online"] is True
    assert status["nickname"] == "TesterOnline"
    assert status["balance_milli"] == 25000
    assert status["realtime_connected"] is True
    assert status["resting"] is False
    assert status["server_time"] == "2026-11-19T09:00:00.000Z"

    # Verify online-status.json was written
    status_file = settings.runtime_dir / "online-status.json"
    assert status_file.is_file()
    saved = json.loads(status_file.read_text())
    assert saved["nickname"] == "TesterOnline"
    assert saved["online"] is True


async def test_ojol_http_api_fetch_online_status_when_realtime_fails(settings, session_file):
    api = OjolHttpApi(settings.runtime_dir)
    api.request = AsyncMock()

    def mock_request(path, *args, **kwargs):
        if path == "/api/game/me":
            return {
                "configVersion": "v1",
                "balanceMilli": 10000,
                "profile": {"nickname": "NoRealtime", "resting": False},
            }
        if path == "/api/time":
            return {"now": "2026-11-19T09:05:00.000Z"}
        if path == "/api/realtime/token":
            raise RuntimeError("Realtime gateway unavailable")
        raise ValueError(f"Unexpected path: {path}")

    api.request.side_effect = mock_request

    status = await api.fetch_online_status()
    assert status["online"] is True
    assert status["nickname"] == "NoRealtime"
    assert status["realtime_connected"] is False


async def test_controller_wait_pings_online_presence(settings, state):
    ui = AsyncMock()
    ui.snapshot.return_value = state
    ui.fetch_online_status = AsyncMock()

    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        cur_time = [100.0]

        def advancing_monotonic():
            val = cur_time[0]
            cur_time[0] += 10.0
            return val

        with patch("time.monotonic", side_effect=advancing_monotonic):
            await controller.wait(60)

        ui.fetch_online_status.assert_awaited()
    finally:
        journal.close()


async def test_controller_wait_with_http_ui_pings_online_presence(settings, state):
    api = AsyncMock()
    api.fetch_online_status = AsyncMock(return_value={"online": True})
    ui = HttpUI(settings, api=api)

    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        cur_time = [100.0]

        def advancing_monotonic():
            val = cur_time[0]
            cur_time[0] += 10.0
            return val

        with patch("time.monotonic", side_effect=advancing_monotonic):
            await controller.wait(60)

        api.fetch_online_status.assert_awaited()
    finally:
        journal.close()


async def test_control_service_fetch_online_status_and_command(settings, session_file):
    service = ControlService(settings)
    mock_status = {
        "online": True,
        "nickname": "AgusOnline",
        "balance_milli": 15000,
        "server_time": "2026-11-19T10:00:00Z",
        "resting": False,
    }
    with patch.object(service, "fetch_online_status", AsyncMock(return_value=mock_status)):
        res = await service.command("online")
        assert "Presence Online · AgusOnline" in res
        assert "Akun aktif di game" in res
        assert "Saldo 15 koin" in res


def test_control_service_summary_reports_online_presence(settings):
    service = ControlService(settings)
    write_private(
        settings.runtime_dir / "online-status.json",
        {"online": True, "nickname": "Budi", "server_time": "2026-11-19T10:00:00Z"},
    )
    s = service.summary()
    assert s["online"] is True
    assert s["online_updated"] is not None


async def test_multi_account_maintain_and_fetch_all(settings):
    manager = MultiAccountService(settings)
    seed_legacy_account(manager.registry, 999)
    registry = manager.registry
    acc1 = registry.create(999, "Akun-1")
    acc2 = registry.create(999, "Akun-2")

    dir1 = registry.scoped_settings(acc1).runtime_dir
    dir2 = registry.scoped_settings(acc2).runtime_dir
    dir1.mkdir(parents=True, exist_ok=True)
    dir2.mkdir(parents=True, exist_ok=True)

    # acc1 has session file, acc2 doesn't
    (dir1 / "http-session.json").write_text(json.dumps({"cookies": []}))

    svc1 = manager.service(acc1["id"])
    mock_status = {"online": True, "nickname": "Pemain-1", "server_time": "10:00"}
    with patch.object(svc1, "fetch_online_status", AsyncMock(return_value=mock_status)) as fetch1:
        res = await manager.fetch_all_online_status()
        assert res[acc1["id"]]["online"] is True
        assert res[acc1["id"]]["nickname"] == "Pemain-1"
        assert res[acc2["id"]]["online"] is False
        assert "Belum ada sesi cookie" in res[acc2["id"]]["error"]

        # Test maintain_online_presence triggers fetch
        await manager.supervisor.maintain_online_presence()
        assert fetch1.await_count >= 1


def test_cli_online_command(capsys):
    mock_status = {"online": True, "nickname": "CliTester", "server_time": "12:00:00"}
    api_mock = AsyncMock()
    api_mock.fetch_online_status.return_value = mock_status
    with patch("app.integrations.kampung.http_api.OjolHttpApi.__aenter__", return_value=api_mock):
        assert main(["--env-file", str(ROOT / ".env.testing"), "online"]) == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["online"] is True
        assert data["nickname"] == "CliTester"


def test_cli_online_all_command(settings, monkeypatch, capsys):
    manager_mock = AsyncMock()
    manager_mock.fetch_all_online_status.return_value = {"acc1": {"name": "Akun 1", "online": True}}
    with patch("app.modules.worker.fleet.MultiAccountService", return_value=manager_mock):
        monkeypatch.setenv("OJOL_RUNTIME_DIR", str(settings.runtime_dir))
        assert main(["--env-file", str(ROOT / ".env.testing"), "online", "--all"]) == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["acc1"]["online"] is True


async def test_maintain_online_presence_respects_kerja_and_kebutuhan_flags(settings):
    manager = MultiAccountService(settings)
    seed_legacy_account(manager.registry, 999)
    acc_kerja = manager.registry.create(999, "KerjaOnly")
    acc_needs = manager.registry.create(999, "NeedsOnly")

    dir_kerja = manager.registry.scoped_settings(acc_kerja).runtime_dir
    dir_needs = manager.registry.scoped_settings(acc_needs).runtime_dir
    dir_kerja.mkdir(parents=True, exist_ok=True)
    dir_needs.mkdir(parents=True, exist_ok=True)
    (dir_kerja / "http-session.json").write_text(json.dumps({"cookies": []}))
    (dir_needs / "http-session.json").write_text(json.dumps({"cookies": []}))

    set_auto_flag(dir_kerja, "ojol", False)
    set_auto_flag(dir_kerja, "kerja", True)

    set_auto_flag(dir_needs, "ojol", False)
    set_auto_flag(dir_needs, "kerja", False)
    set_auto_flag(dir_needs, "makan", True)

    svc_kerja = manager.service(acc_kerja["id"])
    svc_needs = manager.service(acc_needs["id"])
    mock_status = {"online": True, "nickname": "Pemain", "server_time": "10:00"}

    with (
        patch.object(manager, "settings", settings.model_copy(update={"env": "local"})),
        patch.object(svc_kerja, "fetch_online_status", AsyncMock(return_value=mock_status)) as f_kerja,
        patch.object(svc_needs, "fetch_online_status", AsyncMock(return_value=mock_status)) as f_needs,
    ):
        await manager.supervisor.maintain_online_presence()
        f_kerja.assert_awaited_once()
        f_needs.assert_not_awaited()


async def test_controller_wait_respects_kerja_and_kebutuhan_flags(settings):
    set_auto_flag(settings.runtime_dir, "ojol", False)
    set_auto_flag(settings.runtime_dir, "kerja", False)
    set_auto_flag(settings.runtime_dir, "makan", True)

    api = AsyncMock()
    api.fetch_online_status = AsyncMock(return_value={"online": True})
    ui = HttpUI(settings, api=api)

    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        cur_time = [100.0]

        def advancing_monotonic():
            val = cur_time[0]
            cur_time[0] += 10.0
            return val

        with patch("time.monotonic", side_effect=advancing_monotonic):
            await controller.wait(60)
        api.fetch_online_status.assert_not_awaited()

        set_auto_flag(settings.runtime_dir, "kerja", True)
        cur_time[0] = 200.0
        with patch("time.monotonic", side_effect=advancing_monotonic):
            await controller.wait(60)
        api.fetch_online_status.assert_awaited()
    finally:
        journal.close()


async def test_controller_purchase_need_fetches_online_status(settings, state):
    set_auto_flag(settings.runtime_dir, "ojol", False)
    set_auto_flag(settings.runtime_dir, "kerja", False)
    set_auto_flag(settings.runtime_dir, "makan", True)

    before = state.model_copy(
        update={"wallet": 100, "needs": {**state.needs, "makan": 30}}
    )
    after = state.model_copy(
        update={
            "wallet": 95,
            "needs": {**state.needs, "makan": 80},
        }
    )
    shop = ShopPreview(
        id="shop-1",
        plot_id="plot-1",
        category="makan",
        distance_squared=10,
        name="Warung Makan",
        products=[
            Product(
                name="Nasi",
                price=5,
                effects={"makan": 50},
                row_text="Nasi +50%",
                enabled=True,
            )
        ],
    )

    api = AsyncMock()
    api.fetch_online_status = AsyncMock(return_value={"online": True})
    ui = HttpUI(settings, api=api)
    ui.last_navigation = {"akademis_unavailable": True}
    ui.preview_shops = AsyncMock(return_value=[shop])
    ui.buy = AsyncMock()
    ui.snapshot = AsyncMock(return_value=after)

    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.human_pause = AsyncMock()
        result = await controller.purchase(before, "makan")
        assert result is True
        api.fetch_online_status.assert_awaited_once()
        ui.buy.assert_awaited_once()
    finally:
        journal.close()
