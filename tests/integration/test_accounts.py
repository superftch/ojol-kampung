import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from app.cli import main
from app.core.models import ROOT
from app.core.storage import write_private
from app.integrations.kampung.http_api import HttpCoreError
from app.integrations.kampung.identity import save_profile, verified_profile
from app.integrations.kampung.session_transfer import parse_cookie_input
from app.main import create_app
from app.modules.accounts.repository import Accounts
from app.modules.worker.fleet import MultiAccountService
from app.modules.worker.ui import HttpUI
from tests.conftest import seed_legacy_account


@pytest.fixture
def managed(settings):
    seed_legacy_account(Accounts(settings))
    return settings


def test_list_accounts_prints_names_and_ids_without_archived_accounts(managed, monkeypatch, capsys):
    registry = Accounts(managed)
    original = registry.selected(111)
    second = registry.create(111, "Kedua")
    archived = registry.create(111, "Arsip")
    registry.archive(111, archived["id"])
    monkeypatch.setenv("OJOL_RUNTIME_DIR", str(managed.runtime_dir))

    assert main(["--env-file", str(ROOT / ".env.testing"), "list-accounts"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "NAMA\tACCOUNT_ID",
        f"Kedua\t{second['id']}",
        f"Utama\t{original['id']}",
    ]


def test_whitelist_admin_ownership_and_legacy_preservation(managed):
    legacy = managed.runtime_dir / "history.sqlite3"
    legacy.write_bytes(b"unchanged fixture")
    accounts = Accounts(managed)
    assert accounts.allowed(111) and not accounts.allowed(222)
    assert not accounts.allowed(True) and not accounts.allowed(-1)
    with pytest.raises(ValueError, match="Akses Anda belum aktif"):
        accounts.create(222, "Forbidden")
    accounts.set_owner_access(222)
    account = accounts.create(222, "Second user")
    assert (
        accounts.scoped_settings(account).runtime_dir
        == managed.runtime_dir / "accounts" / account["id"]
    )
    admin_account = accounts.selected(111)
    assert accounts.scoped_settings(admin_account).runtime_dir == managed.runtime_dir
    assert legacy.read_bytes() == b"unchanged fixture"
    with pytest.raises(ValueError, match="bukan milik"):
        accounts.get(account["id"], 111)
    with pytest.raises(ValueError):
        accounts.select(111, account["id"])
    assert Accounts(managed).selected(222)["id"] == account["id"]


def test_atomic_quota_persistence_and_archive_restore(managed):
    accounts = Accounts(managed)
    accounts.set_owner_access(222)

    def create(index):
        try:
            return accounts.create(222, f"User {index}")
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        created = [a for a in pool.map(create, range(6)) if a]
    assert len(created) == 3
    accounts.set_limit("max_accounts_per_user", 1)
    assert len(accounts.list(222)) == 3
    with pytest.raises(ValueError, match="Batas akun"):
        accounts.create(222, "over quota")
    accounts.set_owner_access(222, maximum=4)
    extra = accounts.create(222, "Extra")
    directory = accounts.scoped_settings(extra).runtime_dir
    directory.mkdir(parents=True)
    (directory / "history.sqlite3").write_text("keep ledger")
    accounts.archive(222, extra["id"])
    assert accounts.selected(222) is None
    assert (directory / "history.sqlite3").read_text() == "keep ledger"
    with pytest.raises(ValueError):
        accounts.get(extra["id"])
    accounts.archive(222, extra["id"], archived=False)
    accounts.select(222, extra["id"])
    restarted = Accounts(managed)
    assert restarted.selected(222)["id"] == extra["id"]
    assert restarted.quota(222) == 4 and restarted.quota(111) == 1


@pytest.mark.parametrize("value", [0, -1, 101, "nan", "1.5", "' OR 1=1"])
def test_invalid_limits_rejected(managed, value):
    accounts = Accounts(managed)
    with pytest.raises(ValueError):
        accounts.set_limit("max_active_workers", value)
    assert accounts.value("max_active_workers") == 3


def test_same_cookie_cannot_be_attached_to_another_account_including_archives(managed):
    accounts = Accounts(managed)
    first = accounts.selected(111)
    second = accounts.create(111, "Second")
    payload = parse_cookie_input("isolated-session-cookie")
    digest = accounts.check_cookie(first["id"], payload)
    accounts.bind_cookie(first["id"], digest)
    assert accounts.check_cookie(first["id"], payload) == digest
    accounts.archive(111, first["id"])
    with pytest.raises(ValueError, match="akun lain"):
        accounts.check_cookie(second["id"], payload)
    assert b"isolated-session-cookie" not in accounts.path.read_bytes()


async def test_worker_child_receives_only_its_runtime_owner_and_label(managed, monkeypatch):
    manager = MultiAccountService(managed)
    manager.registry.set_owner_access(222)
    account = manager.registry.create(222, "Second")
    service = manager.service(account["id"])
    service.settings = service.settings.model_copy(
        update={"operator_authorized": True, "env": "local"}
    )
    write_private(
        service.settings.runtime_dir / "http-session.json", parse_cookie_input("fixture-cookie")
    )
    child = SimpleNamespace(returncode=None)
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr("app.modules.worker.service.asyncio.create_subprocess_exec", spawn)
    await service.command("run")
    await service.command("run")
    spawn.assert_awaited_once()
    env = spawn.call_args.kwargs["env"]
    assert env["OJOL_RUNTIME_DIR"] == str(service.settings.runtime_dir)
    assert env["OJOL_ACCOUNT_NAME"] == "Second"
    assert "fixture-cookie" not in str(spawn.call_args)
    assert not (managed.runtime_dir / "http-session.json").exists()


def test_import_routes_account_cookie_path_csrf_isolation_and_revocation(managed, monkeypatch):
    async def import_fixture(settings, payload):
        save_profile(
            settings.runtime_dir,
            verified_profile(
                {"profile": {"nickname": "Verified Game Nick"}, "balanceMilli": 35000}
            ),
        )

    imported = AsyncMock(side_effect=import_fixture)
    monkeypatch.setattr("app.integrations.kampung.session_transfer.import_session", imported)
    app = create_app(managed)
    manager = app.state.management
    manager.registry.set_owner_access(222)
    one = manager.registry.create(222, '<One & "test">')
    two = manager.registry.create(222, "Two")
    a, b = manager.service(one["id"]), manager.service(two["id"])
    ticket_a, ticket_b = a.access.issue("ticket"), b.access.issue("ticket")
    with TestClient(app, base_url="http://localhost:6080") as client:
        prefix_a, prefix_b = a.url_prefix, b.url_prefix
        assert client.get(prefix_b + "/access/" + ticket_a).status_code == 403
        response = client.get(prefix_a + "/access/" + ticket_a, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == prefix_a + "/import-cookie"
        assert f"Path={prefix_a}/" in response.headers["set-cookie"]
        page = client.get(prefix_a + "/import-cookie")
        assert f'action="{prefix_a}/import-cookie"' in page.text
        assert "&lt;One &amp; &quot;test&quot;&gt;" in page.text
        assert client.get(prefix_b + "/import-cookie").status_code == 403
        csrf = a.access.csrf_token(
            next(c.value for c in client.cookies.jar if c.path == prefix_a + "/")
        )
        result = client.post(
            prefix_a + "/import-cookie", data={"csrf": csrf, "cookie": "isolated-a"}
        )
        assert result.status_code == 200
        assert imported.call_args.args[0].runtime_dir == a.settings.runtime_dir
        assert manager.registry.get(one["id"])["name"] == "Verified Game Nick"
        assert a.settings.account_name == "Verified Game Nick"
        assert client.get(prefix_a + "/import-cookie").status_code == 403
        manager.registry.set_owner_access(222, False)
        assert client.get(prefix_b + "/access/" + ticket_b).status_code == 403
        assert client.get("/health").json()["service"] == "ok"


async def test_existing_account_names_refresh_from_game_without_stopping_worker(
    managed, monkeypatch
):
    import app.modules.worker.fleet as module

    manager = MultiAccountService(managed.model_copy(update={"env": "local"}))
    account = manager.registry.selected(111)
    service = manager.service(account["id"])
    service.stop_worker = AsyncMock()
    write_private(
        service.settings.runtime_dir / "http-session.json",
        parse_cookie_input("isolated-profile-cookie"),
    )
    api = SimpleNamespace(
        request=AsyncMock(
            return_value={"profile": {"nickname": "Fetched Nick"}, "balanceMilli": 12345}
        )
    )
    context = AsyncMock()
    context.__aenter__.return_value = api
    monkeypatch.setattr(module, "OjolHttpApi", lambda *args: context)
    await manager.refresh_account_profile(account)
    api.request.assert_awaited_once_with("/api/game/me")
    assert manager.registry.get(account["id"])["name"] == "Fetched Nick"
    service.stop_worker.assert_not_awaited()
    api.request.side_effect = HttpCoreError("fixture expired", category="auth")
    await manager.refresh_account_profile(account)
    assert manager.registry.get(account["id"])["name"] == "Fetched Nick"
    service.stop_worker.assert_not_awaited()
    assert not (service.settings.runtime_dir / "STOP").exists()


def test_import_rejects_duplicate_cookie_before_verification(managed, monkeypatch):
    imported = AsyncMock()
    monkeypatch.setattr("app.integrations.kampung.session_transfer.import_session", imported)
    app = create_app(managed)
    manager = app.state.management
    first = manager.registry.selected(111)
    second = manager.registry.create(111, "Second")
    digest = manager.registry.check_cookie(first["id"], parse_cookie_input("fixture-duplicate"))
    manager.registry.bind_cookie(first["id"], digest)
    service = manager.service(second["id"])
    with TestClient(app, base_url="http://localhost:6080") as client:
        client.get(service.url_prefix + "/access/" + service.access.issue("ticket"))
        session = next(c.value for c in client.cookies.jar if c.path == service.url_prefix + "/")
        response = client.post(
            service.url_prefix + "/import-cookie",
            data={"cookie": "fixture-duplicate", "csrf": service.access.csrf_token(session)},
        )
        assert response.status_code == 409
        imported.assert_not_awaited()


async def test_http_read_failure_propagates_without_starting_browser(settings):
    error = HttpCoreError("fixture read failure", recoverable=True)
    api = SimpleNamespace(snapshot=AsyncMock(side_effect=error))
    ui = HttpUI(settings, api=api)
    with pytest.raises(HttpCoreError) as result:
        await ui.snapshot()
    assert result.value is error
    assert not hasattr(ui, "activate_fallback")


async def test_manager_start_testing_never_starts_gameplay(managed, monkeypatch):
    manager = MultiAccountService(managed.model_copy(update={"env": "local"}))
    manager.registry.set_owner_access(222)
    manager.registry.create(222, "Second")
    services = [manager.service(row["id"]) for row in manager.registry.list()]
    for service in services:
        service.start = AsyncMock()
        service.close = AsyncMock()
    manager.start_tunnel = AsyncMock()
    manager.supervisor.supervise = AsyncMock()
    await manager.start()
    for service in services:
        service.start.assert_awaited_once_with()
        assert service.worker is None
    assert len(manager.supervisor.tasks) == 1  # No bot token: supervision only.
    await manager.close()


async def test_fatal_control_error_stops_every_account_not_only_admin(managed, monkeypatch):
    manager = MultiAccountService(managed)
    manager.registry.set_owner_access(222)
    manager.registry.create(222, "Second")
    services = [manager.service(row["id"]) for row in manager.registry.list()]
    for service in services:
        service.stop_worker = AsyncMock()

    async def fail():
        raise RuntimeError("fixture failure")

    await manager.supervisor.guard_task(fail, "management.supervise")
    for service in services:
        service.stop_worker.assert_awaited_once()
    assert (
        json.loads((manager.control_settings.runtime_dir / "last-error.json").read_text())["stage"]
        == "management.supervise"
    )


async def test_http_ui_forwards_kantor_and_kerja_malam(settings):
    """Auto Kerja hanya jalan bila HttpUI meneruskan kantor_action (guard hasattr)."""
    api = SimpleNamespace(
        kantor_action=AsyncMock(return_value={"kantor": {"nama": "Bank desa"}}),
        kerja_malam_status=AsyncMock(return_value={"enabled": True}),
        kerja_malam_action=AsyncMock(return_value={"ok": True}),
    )
    ui = HttpUI(settings, api=api)
    assert await ui.kantor_action("detak") == {"kantor": {"nama": "Bank desa"}}
    api.kantor_action.assert_awaited_once_with("detak")
    await ui.kantor_action("kejadian", idx=2)
    api.kantor_action.assert_awaited_with("kejadian", idx=2)
    assert await ui.kerja_malam_status() == {"enabled": True}
    assert await ui.kerja_malam_action("lampu", key="L1") == {"ok": True}
    api.kerja_malam_action.assert_awaited_once_with("lampu", key="L1")
