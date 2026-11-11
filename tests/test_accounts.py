import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from ojol.accounts import Accounts
from ojol.control import create_app
from ojol.healing import write_private
from ojol.http_api import HttpCoreError
from ojol.http_core import HttpUI
from ojol.management import MultiAccountService
from ojol.models import Settings
from ojol.session_transfer import parse_cookie_input
from ojol.telegram import TelegramClient


@pytest.fixture
def managed(settings):
    return settings.model_copy(update={"telegram_chat_id": 111})


def test_whitelist_admin_ownership_and_legacy_preservation(managed):
    legacy = managed.runtime_dir / "history.sqlite3"
    legacy.write_bytes(b"unchanged fixture")
    accounts = Accounts(managed)
    assert accounts.allowed(111) and not accounts.allowed(222)
    assert not accounts.allowed(True) and not accounts.allowed(-1)
    with pytest.raises(ValueError, match="Admin"):
        accounts.whitelist(111, False)
    with pytest.raises(ValueError, match="whitelist"):
        accounts.create(222, "Forbidden")
    accounts.whitelist(222)
    account = accounts.create(222, "Second user")
    assert accounts.scoped_settings(account).telegram_chat_id == 222
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
    accounts.whitelist(222)

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
    accounts.whitelist(222, maximum=4)
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


async def test_management_admin_boundary_and_user_account_operations(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    await manager.dispatch(222, "/akun tambah Denied")
    manager.reply.assert_not_awaited()
    await manager.dispatch(111, "/whitelist tambah 222 2")
    assert manager.registry.allowed(222) and manager.registry.quota(222) == 2
    await manager.dispatch(222, "/whitelist tambah 333")
    assert not manager.registry.allowed(333)
    await manager.dispatch(222, "/batas worker 99")
    assert manager.registry.value("max_active_workers") == 3
    await manager.dispatch(111, "/batas default 4")
    await manager.dispatch(111, "/batas worker 2")
    assert manager.registry.value("max_accounts_per_user") == 4
    assert manager.registry.value("max_active_workers") == 2
    await manager.dispatch(222, "Tambah Akun")
    await manager.dispatch(222, "Malam")
    account = manager.registry.selected(222)
    assert account["name"] == "Malam"
    await manager.dispatch(222, f"/akun nama {account['id']} Akun Baru")
    assert manager.registry.get(account["id"])["name"] == "Akun Baru"
    admin = manager.registry.selected(111)
    await manager.dispatch(222, "select:" + admin["id"], callback=True)
    assert manager.registry.selected(222)["id"] == account["id"]
    await manager.dispatch(222, f"/akun arsip {account['id']}")
    assert manager.registry.selected(222) is None
    await manager.dispatch(222, f"/akun pulihkan {account['id']}")
    await manager.dispatch(222, "select:" + account["id"], callback=True)
    assert manager.registry.selected(222)["id"] == account["id"]


async def test_global_worker_cap_serializes_simultaneous_starts_and_deduplicates(managed):
    manager = MultiAccountService(managed)
    manager.registry.whitelist(222)
    second = manager.registry.create(222, "Second")
    first = manager.registry.selected(111)
    a, b = manager.service(first["id"]), manager.service(second["id"])
    manager.reply = AsyncMock()
    manager.start_tunnel = AsyncMock()
    manager.registry.set_limit("max_active_workers", 1)
    starts = []

    async def start_a(command):
        if command == "run":
            starts.append("a")
            await asyncio.sleep(0)
            a.worker = SimpleNamespace(returncode=None)

    a.execute = AsyncMock(side_effect=start_a)
    b.execute = AsyncMock()
    await asyncio.gather(
        manager.dispatch(111, "Jalankan Ojol"), manager.dispatch(222, "Jalankan Ojol")
    )
    assert starts == ["a"]
    b.execute.assert_not_awaited()
    assert "Batas worker" in manager.reply.call_args.args[1]
    a.execute = AsyncMock()
    await manager.dispatch(111, "Jalankan Ojol")
    a.execute.assert_awaited_once_with("run")


async def test_worker_child_receives_only_its_runtime_owner_and_label(managed, monkeypatch):
    manager = MultiAccountService(managed)
    manager.registry.whitelist(222)
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
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await service.command("run")
    await service.command("run")
    spawn.assert_awaited_once()
    env = spawn.call_args.kwargs["env"]
    assert env["OJOL_TELEGRAM_CHAT_ID"] == "222"
    assert env["OJOL_RUNTIME_DIR"] == str(service.settings.runtime_dir)
    assert env["OJOL_ACCOUNT_NAME"] == "Second"
    assert "fixture-cookie" not in str(spawn.call_args)
    assert not (managed.runtime_dir / "http-session.json").exists()


async def test_whitelist_revoke_stops_all_user_workers_revokes_links_preserves_admin(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    manager.registry.whitelist(222)
    rows = [manager.registry.create(222, name) for name in ("One", "Two")]
    services = [manager.service(row["id"]) for row in rows]
    tickets = [s.access.issue("ticket") for s in services]
    for service in services:
        service.stop_worker = AsyncMock()
    admin = manager.service(manager.registry.selected(111)["id"])
    admin.stop_worker = AsyncMock()
    await manager.dispatch(111, "/whitelist hapus 222")
    assert not manager.registry.allowed(222)
    for service, ticket in zip(services, tickets, strict=True):
        service.stop_worker.assert_awaited_once()
        assert service.access.consume_ticket(ticket) is None
    admin.stop_worker.assert_not_awaited()
    manager.registry.whitelist(222)
    assert len(manager.registry.list(222)) == 2
    assert not manager.services.get(rows[0]["id"])


async def test_finance_buttons_keep_original_account_after_selection_changes(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    first = manager.registry.selected(111)
    second = manager.registry.create(111, "Second")
    a, b = manager.service(first["id"]), manager.service(second["id"])
    a.execute, b.execute = AsyncMock(), AsyncMock()
    markup = a.profit_buttons("2030-01-02")
    data = markup["inline_keyboard"][0][0]["callback_data"]
    assert len(data.encode()) <= 64
    await manager.dispatch(111, data, callback=True)
    a.execute.assert_awaited_once_with("profit:2030-01-01")
    b.execute.assert_not_awaited()
    await manager.dispatch(111, f"acct:{first['id']}:choose_date", callback=True)
    await manager.dispatch(111, "03-01-2030")
    assert a.execute.call_args.args == ("profit:03-01-2030",)
    await manager.dispatch(111, "profit:2030-01-01", callback=True)
    b.execute.assert_not_awaited()


def test_import_routes_account_cookie_path_csrf_isolation_and_revocation(managed, monkeypatch):
    imported = AsyncMock()
    monkeypatch.setattr("ojol.session_transfer.import_session", imported)
    app = create_app(managed)
    manager = app.state.management
    manager.registry.whitelist(222)
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
        assert imported.call_args.args[0].telegram_chat_id == 222
        assert client.get(prefix_a + "/import-cookie").status_code == 403
        manager.registry.whitelist(222, False)
        assert client.get(prefix_b + "/access/" + ticket_b).status_code == 403
        assert client.get("/health").json()["core"] == "http"


def test_import_rejects_duplicate_cookie_before_verification(managed, monkeypatch):
    imported = AsyncMock()
    monkeypatch.setattr("ojol.session_transfer.import_session", imported)
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
    ui = HttpUI(settings)
    error = HttpCoreError("fixture read failure", recoverable=True)
    ui.call_tool = AsyncMock(side_effect=error)
    with pytest.raises(HttpCoreError) as result:
        await ui.snapshot()
    assert result.value is error
    assert not hasattr(ui, "activate_fallback")
    with pytest.raises(ValidationError):
        Settings(core="browser")


async def test_account_notifications_target_owner_and_include_account_name(managed):
    settings = managed.model_copy(update={"account_name": "Night", "telegram_chat_id": 222})
    api = TelegramClient(settings)
    api.call = AsyncMock()
    await api.send("fixture message")
    assert api.call.call_args.kwargs["chat_id"] == 222
    assert api.call.call_args.kwargs["text"] == "[Night]\nfixture message"


async def test_single_poller_routes_whitelisted_private_users_and_rejects_foreign_callbacks(
    managed, monkeypatch
):
    import ojol.management as module

    manager = MultiAccountService(managed)
    manager.registry.whitelist(222)
    manager.dispatch = AsyncMock()

    def message(owner, chat_type="private", chat_id=None):
        return {
            "from": {"id": owner},
            "chat": {"id": owner if chat_id is None else chat_id, "type": chat_type},
            "text": "Status",
        }

    updates = [
        {"update_id": 1, "message": message(111)},
        {"update_id": 2, "message": message(222)},
        {"update_id": 3, "message": message(333)},
        {"update_id": 4, "message": message(222, "group")},
        {
            "update_id": 5,
            "callback_query": {
                "id": "foreign",
                "from": {"id": 222},
                "message": message(111),
                "data": "acct:any:profit:2030-01-01",
            },
        },
        {
            "update_id": 6,
            "callback_query": {
                "id": "valid",
                "from": {"id": 222},
                "message": message(222),
                "data": "select:fixture",
            },
        },
    ]

    async def call(method, **kwargs):
        if method == "getUpdates":
            assert kwargs["offset"] == 0
            manager.closing = True
            return updates
        assert method == "answerCallbackQuery" and kwargs["callback_query_id"] == "valid"

    api = SimpleNamespace(call=AsyncMock(side_effect=call))
    context = AsyncMock()
    context.__aenter__.return_value = api
    monkeypatch.setattr(module, "TelegramClient", lambda settings: context)
    await manager.poll_telegram()
    assert manager.dispatch.call_args_list == [
        ((111, "Status", False),),
        ((222, "Status", False),),
        ((222, "select:fixture", True),),
    ]
    assert (managed.runtime_dir / "telegram-offset").read_text() == "7"


async def test_manager_start_never_starts_account_pollers_or_gameplay(managed, monkeypatch):
    manager = MultiAccountService(managed.model_copy(update={"env": "local"}))
    manager.registry.whitelist(222)
    manager.registry.create(222, "Second")
    services = [manager.service(row["id"]) for row in manager.registry.list()]
    for service in services:
        service.start = AsyncMock()
        service.close = AsyncMock()
    manager.start_tunnel = AsyncMock()
    manager.supervise = AsyncMock()
    manager.poll_telegram = AsyncMock()
    await manager.start()
    for service in services:
        service.start.assert_awaited_once_with(poll=False)
        assert service.worker is None
    assert len(manager.tasks) == 1  # No bot token: supervision only.
    await manager.close()


async def test_fatal_control_error_stops_every_account_not_only_admin(managed, monkeypatch):
    manager = MultiAccountService(managed)
    manager.registry.whitelist(222)
    manager.registry.create(222, "Second")
    services = [manager.service(row["id"]) for row in manager.registry.list()]
    for service in services:
        service.stop_worker = AsyncMock()
    monkeypatch.setattr("ojol.management.flush_notices", AsyncMock())

    async def fail():
        raise RuntimeError("fixture failure")

    await manager.guard_task(fail, "management.supervise")
    for service in services:
        service.stop_worker.assert_awaited_once()
    assert (
        json.loads((manager.hub.settings.runtime_dir / "last-error.json").read_text())["stage"]
        == "management.supervise"
    )


async def test_telegram_outage_stops_all_accounts_once_and_queues_one_error(managed, monkeypatch):
    import ojol.management as module
    from ojol.telegram import TelegramError

    manager = MultiAccountService(managed)
    manager.registry.whitelist(222)
    manager.registry.create(222, "Second")
    services = [manager.service(row["id"]) for row in manager.registry.list()]
    for service in services:
        service.stop_worker = AsyncMock()
    calls = 0

    async def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise TelegramError("fixture offline")

    async def wait(seconds):
        if calls == 2:
            manager.closing = True

    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(call=AsyncMock(side_effect=fail))
    monkeypatch.setattr(module, "TelegramClient", lambda settings: context)
    monkeypatch.setattr(module.asyncio, "sleep", wait)
    await manager.poll_telegram()
    assert calls == 2
    assert len(list((manager.hub.settings.runtime_dir / "notifications").glob("*.json"))) == 1
    for service in services:
        service.stop_worker.assert_awaited_once()


async def test_selecting_account_cancels_pending_name_input(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    original = manager.registry.selected(111)
    await manager.dispatch(111, "Tambah Akun")
    assert manager.pending[111] == "name"
    await manager.dispatch(111, "select:" + original["id"], callback=True)
    assert 111 not in manager.pending
    assert len(manager.registry.list(111)) == 1
