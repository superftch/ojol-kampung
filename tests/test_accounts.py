import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import call as mock_call

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


async def click(manager, owner, label, profile=None):
    markup = manager.reply.call_args.args[2]
    button = next(b for row in markup["inline_keyboard"] for b in row if b["text"] == label)
    if profile is None:
        await manager.dispatch(owner, button["callback_data"], callback=True)
    else:
        await manager.dispatch(owner, button["callback_data"], callback=True, profile=profile)


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
    await manager.dispatch(222, "Tambah Akun")
    manager.reply.assert_not_awaited()
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Tambah User")
    await manager.dispatch(111, "222")
    await click(manager, 111, "Ubah Batas Akun")
    await manager.dispatch(111, "2")
    assert manager.registry.allowed(222) and manager.registry.quota(222) == 2
    await manager.dispatch(222, "admin:add_user", callback=True)
    assert 222 not in manager.pending
    await manager.dispatch(222, "admin:worker_limit", callback=True)
    assert manager.registry.value("max_active_workers") == 3
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Batas Akun Default")
    await manager.dispatch(111, "4")
    await click(manager, 111, "Batas Worker")
    await manager.dispatch(111, "2")
    assert manager.registry.value("max_accounts_per_user") == 4
    assert manager.registry.value("max_active_workers") == 2
    await manager.dispatch(222, "Tambah Akun")
    await manager.dispatch(222, "Malam")
    account = manager.registry.selected(222)
    assert account["name"] == "Malam"
    await click(manager, 222, "Ubah Nama")
    await manager.dispatch(222, "Akun Baru")
    assert manager.registry.get(account["id"])["name"] == "Akun Baru"
    admin = manager.registry.selected(111)
    await manager.dispatch(222, "select:" + admin["id"], callback=True)
    assert manager.registry.selected(222)["id"] == account["id"]
    await manager.dispatch(222, "Akun Saya")
    await click(manager, 222, "Pilih Akun Baru")
    await click(manager, 222, "Arsipkan Akun")
    assert manager.registry.selected(222)["id"] == account["id"]
    await click(manager, 222, "Ya, Arsipkan")
    assert manager.registry.selected(222) is None
    await click(manager, 222, "Pulihkan Akun Baru")
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
    await manager.dispatch(111, "user:222", callback=True)
    await click(manager, 111, "Cabut Akses")
    assert manager.registry.allowed(222)
    await click(manager, 111, "Ya, Cabut Akses")
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
        mock_call(111, "Status", False, profile={"id": 111}),
        mock_call(222, "Status", False, profile={"id": 222}),
        mock_call(333, "Status", False, profile={"id": 333}),
        mock_call(222, "select:fixture", True, profile={"id": 222}),
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
    assert manager.pending[111] == {"kind": "name"}
    await manager.dispatch(111, "select:" + original["id"], callback=True)
    assert 111 not in manager.pending
    assert len(manager.registry.list(111)) == 1


@pytest.mark.parametrize(
    "text",
    ["/akun tambah Forbidden", "/whitelist tambah 333", "/batas worker 99", "/akun arsip anything"],
)
async def test_old_slash_commands_only_show_buttons(managed, text):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    await manager.dispatch(111, text)
    assert len(manager.registry.list(111)) == 1
    assert not manager.registry.allowed(333)
    assert manager.registry.value("max_active_workers") == 3
    assert "keyboard" in manager.reply.call_args.args[2]
    assert "/" not in manager.reply.call_args.args[1]


async def test_invalid_input_can_retry_and_cancel_without_changing_settings(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Tambah User")
    await manager.dispatch(111, "not-an-id")
    assert manager.pending[111] == {"kind": "add_user"}
    await click(manager, 111, "Batal")
    assert 111 not in manager.pending
    assert len(manager.registry.users()) == 1
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Batas Worker")
    await manager.dispatch(111, "0")
    assert manager.registry.value("max_active_workers") == 3
    assert 111 in manager.pending
    await manager.dispatch(111, "2")
    assert manager.registry.value("max_active_workers") == 2
    assert 111 not in manager.pending
    await manager.dispatch(111, "Tambah Akun")
    await manager.dispatch(111, "Batal")
    assert 111 not in manager.pending
    assert len(manager.registry.list(111)) == 1


async def test_user_enable_and_revoke_confirmation_cannot_be_replayed(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    manager.registry.whitelist(222)
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Daftar User")
    await click(manager, 111, "222 · aktif")
    await click(manager, 111, "Cabut Akses")
    confirm = manager.reply.call_args.args[2]["inline_keyboard"][0][0]["callback_data"]
    await click(manager, 111, "Batal")
    await manager.dispatch(111, confirm, callback=True)
    assert manager.registry.allowed(222)
    await manager.dispatch(111, "user:222", callback=True)
    await click(manager, 111, "Cabut Akses")
    await click(manager, 111, "Ya, Cabut Akses")
    assert not manager.registry.allowed(222)
    await click(manager, 111, "Aktifkan Akses")
    assert manager.registry.allowed(222)
    await manager.dispatch(111, confirm, callback=True)
    assert manager.registry.allowed(222)
    await manager.dispatch(111, "revoke:111", callback=True)
    assert manager.registry.allowed(111)
    assert 111 not in manager.pending


@pytest.mark.parametrize(
    "action", ["rename:", "archive:", "archive_confirm:", "restore:", "select:"]
)
async def test_account_management_buttons_reject_foreign_account(managed, action):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    manager.registry.whitelist(222)
    own = manager.registry.create(222, "Own")
    foreign = manager.registry.selected(111)
    await manager.dispatch(222, action + foreign["id"], callback=True)
    assert manager.registry.get(foreign["id"])["name"] == "Utama"
    assert manager.registry.selected(222)["id"] == own["id"]
    assert 222 not in manager.pending
    assert not (managed.runtime_dir / "STOP").exists()


async def test_pending_inputs_are_separate_per_user_and_old_rename_does_not_switch_selection(
    managed,
):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    manager.registry.whitelist(222)
    first = manager.registry.selected(111)
    second = manager.registry.create(111, "Second")
    await manager.dispatch(111, "rename:" + first["id"], callback=True)
    await manager.dispatch(222, "Tambah Akun")
    await manager.dispatch(111, "Renamed")
    assert manager.registry.get(first["id"])["name"] == "Renamed"
    assert manager.registry.selected(111)["id"] == second["id"]
    assert "Akun terpilih: Second" in manager.reply.call_args.args[1]
    await manager.dispatch(222, "New User Account")
    assert manager.registry.selected(222)["name"] == "New User Account"
    assert manager.pending == {}


async def test_date_prompt_retries_invalid_input_and_cancel_keeps_gameplay_running(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    account = manager.registry.selected(111)
    service = manager.service(account["id"])
    service.execute = AsyncMock()
    await manager.dispatch(111, f"acct:{account['id']}:choose_date", callback=True)
    await manager.dispatch(111, "not-a-date")
    assert manager.pending[111] == {"kind": "date", "account": account["id"]}
    await manager.dispatch(111, "03-01-2030")
    service.execute.assert_awaited_once_with("profit:03-01-2030")
    await manager.dispatch(111, f"acct:{account['id']}:choose_date", callback=True)
    await click(manager, 111, "Batal")
    assert 111 not in manager.pending
    assert not (managed.runtime_dir / "STOP").exists()


async def test_lists_paginate_without_losing_buttons_or_exposing_account_ids(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    manager.registry.whitelist(222, maximum=10)
    rows = [manager.registry.create(222, f"Slot {i}") for i in range(10)]
    await manager.dispatch(222, "Akun Saya")
    assert all(row["id"] not in manager.reply.call_args.args[1] for row in rows)
    await click(manager, 222, "Berikutnya ▶")
    await click(manager, 222, "Pilih Slot 9")
    assert manager.registry.selected(222)["id"] == rows[9]["id"]
    for uid in range(300, 310):
        manager.registry.whitelist(uid)
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Daftar User")
    await click(manager, 111, "Berikutnya ▶")
    await click(manager, 111, "309 · aktif")
    assert "Telegram ID: 309" in manager.reply.call_args.args[1]
    assert all(
        len(b["callback_data"].encode()) <= 64
        for call in manager.reply.call_args_list
        for row in (call.args[2].get("inline_keyboard", []) if len(call.args) > 2 else [])
        for b in row
    )


async def test_archive_confirmation_stops_only_target_and_restore_respects_quota(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    first = manager.registry.selected(111)
    second = manager.registry.create(111, "Second")
    a, b = manager.service(first["id"]), manager.service(second["id"])
    a.stop_worker, b.stop_worker = AsyncMock(), AsyncMock()
    ticket = a.access.issue("ticket")
    await manager.dispatch(111, "archive:" + first["id"], callback=True)
    confirm = manager.reply.call_args.args[2]["inline_keyboard"][0][0]["callback_data"]
    await click(manager, 111, "Batal")
    await manager.dispatch(111, confirm, callback=True)
    a.stop_worker.assert_not_awaited()
    assert manager.registry.get(first["id"])
    await manager.dispatch(111, "archive:" + first["id"], callback=True)
    await click(manager, 111, "Ya, Arsipkan")
    a.stop_worker.assert_awaited_once()
    b.stop_worker.assert_not_awaited()
    assert a.access.consume_ticket(ticket) is None
    manager.registry.set_limit("max_accounts_per_user", 1)
    await click(manager, 111, "Pulihkan Utama")
    assert manager.registry.get(first["id"], archived=True)
    assert manager.registry.selected(111)["id"] == second["id"]
    assert "Batas akun" in manager.reply.call_args.args[1]


@pytest.mark.parametrize("reactivate", [False, True])
async def test_granting_access_sends_main_keyboard_to_correct_user(managed, reactivate):
    from ojol.telegram import KEYBOARD

    manager = MultiAccountService(managed)
    manager.reply = AsyncMock(return_value=1)
    if reactivate:
        manager.registry.whitelist(222, False)
        await manager.dispatch(111, "user:222", callback=True)
        await click(manager, 111, "Aktifkan Akses")
    else:
        await manager.dispatch(111, "Management")
        await click(manager, 111, "Tambah User")
        await manager.dispatch(111, "222")
    welcome = [call for call in manager.reply.call_args_list if call.args[0] == 222]
    assert len(welcome) == 1
    assert welcome[0].args[2] == KEYBOARD
    assert "Tambah Akun" in welcome[0].args[1] and "Import Cookie" in welcome[0].args[1]
    assert manager.registry.allowed(222)
    assert not manager.registry.list(222)
    assert not manager.services
    assert manager.reply.call_args.args[0] == 111


async def test_resending_menu_is_admin_only_and_preserves_user_input(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock(return_value=1)
    manager.registry.whitelist(222)
    await manager.dispatch(222, "Tambah Akun")
    await manager.dispatch(111, "user:222", callback=True)
    await click(manager, 111, "Kirim Menu")
    assert manager.pending[222] == {"kind": "name"}
    assert any(
        call.args[0] == 222 and "keyboard" in call.args[2] for call in manager.reply.call_args_list
    )
    manager.reply.reset_mock()
    await manager.dispatch(222, "send_menu:111", callback=True)
    assert all(call.args[0] == 222 for call in manager.reply.call_args_list)
    assert "Management hanya" in manager.reply.call_args.args[1]
    manager.registry.whitelist(333, False)
    manager.reply.reset_mock()
    await manager.dispatch(111, "send_menu:333", callback=True)
    assert all(call.args[0] == 111 for call in manager.reply.call_args_list)
    assert not manager.registry.allowed(333)


async def test_start_offers_application_before_whitelist_then_shows_main_menu(managed):
    from ojol.telegram import KEYBOARD

    manager = MultiAccountService(managed)
    manager.reply = AsyncMock()
    await manager.dispatch(222, "/start")
    assert "Ajukan Akses" in str(manager.reply.call_args.args[2])
    assert not manager.registry.allowed(222)
    manager.reply.reset_mock()
    manager.registry.whitelist(222)
    await manager.dispatch(222, "menu")
    manager.reply.assert_awaited_once()
    assert manager.reply.call_args.args[0] == 222
    assert manager.reply.call_args.args[2] == KEYBOARD
    assert not manager.registry.list(222)


@pytest.mark.parametrize("pending_message", [False, True])
async def test_failed_welcome_stays_queued_and_admin_gets_recovery_steps(
    managed, monkeypatch, pending_message
):
    import httpx
    from pydantic import SecretStr

    import ojol.management as module
    from ojol.telegram import KEYBOARD, flush_notices, queue_notice

    manager = MultiAccountService(
        managed.model_copy(update={"telegram_bot_token": SecretStr("isolated-test-token")})
    )
    sent = []
    if pending_message:
        queue_notice(manager.notice_settings(222), "older fixture")

    def handle(request):
        data = json.loads(request.content)
        sent.append(data)
        if data["chat_id"] == 222 and data["text"] != "older fixture":
            return httpx.Response(
                403, json={"ok": False, "description": "bot cannot initiate conversation"}
            )
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:

        async def flush(settings):
            return await flush_notices(settings, client)

        monkeypatch.setattr(module, "flush_notices", flush)
        monkeypatch.setattr("ojol.telegram.asyncio.sleep", AsyncMock())
        await manager.dispatch(111, "Management")
        await manager.dispatch(111, "admin:add_user", callback=True)
        await manager.dispatch(111, "222")
    assert manager.registry.allowed(222)
    notice_dir = manager.notice_settings(222).runtime_dir / "notifications"
    pending = list(notice_dir.glob("*.json"))
    assert len(pending) == 1
    payload = json.loads(pending[0].read_text())
    assert payload["reply_markup"] == KEYBOARD and payload["attempts"] == 1
    assert any(
        data["chat_id"] == 111 and "menu belum terkirim" in data["text"] and "Start" in data["text"]
        for data in sent
    )
    assert not (manager.hub.settings.runtime_dir / "STOP").exists()
    assert not (manager.notice_settings(222).runtime_dir / "STOP").exists()


async def test_unlisted_start_requests_access_with_telegram_name_and_no_duplicate_admin_notices(
    managed,
):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock(return_value=True)
    profile = {"id": 222, "first_name": "Siti", "last_name": "Aminah", "username": "siti_aminah"}
    await manager.dispatch(222, "/start", profile=profile)
    assert manager.registry.access_request(222) is None
    assert manager.reply.call_args.args[0] == 222
    await click(manager, 222, "Ajukan Akses", profile=profile)
    request = manager.registry.access_request(222)
    assert request["name"] == "Siti Aminah" and request["username"] == "siti_aminah"
    assert request["status"] == "pending" and not manager.registry.allowed(222)
    admin_notices = [c for c in manager.reply.call_args_list if c.args[0] == 111]
    assert len(admin_notices) == 1
    assert "Siti Aminah" in admin_notices[0].args[1] and "@siti_aminah" in admin_notices[0].args[1]
    assert "222" in admin_notices[0].args[1]
    for _ in range(3):
        await manager.dispatch(222, "access:request", callback=True, profile=profile)
    assert len([c for c in manager.reply.call_args_list if c.args[0] == 111]) == 1
    assert not manager.registry.list(222) and not manager.services
    assert Accounts(managed).access_request(222)["id"] == request["id"]
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Pengajuan Akses")
    await click(manager, 111, "Siti Aminah · 222")
    assert "Siti Aminah" in manager.reply.call_args.args[1]
    assert {
        b["text"] for row in manager.reply.call_args.args[2]["inline_keyboard"] for b in row
    } >= {"Setujui", "Tolak"}


@pytest.mark.parametrize("approve", [True, False])
async def test_only_admin_can_review_request_and_old_decision_buttons_cannot_replay(
    managed, approve
):
    from ojol.management import ACCESS_STATUS
    from ojol.telegram import KEYBOARD

    manager = MultiAccountService(managed)
    manager.reply = AsyncMock(return_value=True)
    manager.registry.whitelist(444)
    profile = {"id": 222, "first_name": "Pemohon"}
    await manager.dispatch(222, "access:request", callback=True, profile=profile)
    row = manager.registry.access_request(222)
    for actor in (222, 444):
        await manager.dispatch(actor, "approve_request:" + row["id"], callback=True)
        assert not manager.registry.allowed(222)
    for text in ("Import Cookie", "Tambah Akun", "Management", "select:any"):
        await manager.dispatch(222, text, callback=text.startswith("select:"))
        assert not manager.services
    manager.reply.reset_mock()
    await manager.dispatch(111, "request:" + row["id"], callback=True)
    await click(manager, 111, "Setujui" if approve else "Tolak")
    result = manager.registry.access_request(222)
    assert result["status"] == ("approved" if approve else "rejected")
    assert result["decided_by"] == 111 and result["decided_at"] >= result["created"]
    assert manager.registry.allowed(222) is approve
    applicant_notices = [c for c in manager.reply.call_args_list if c.args[0] == 222]
    assert len(applicant_notices) == 1
    assert applicant_notices[0].args[2] == (KEYBOARD if approve else ACCESS_STATUS)
    assert not manager.registry.list(222) and not manager.services
    await manager.dispatch(111, "approve_request:" + row["id"], callback=True)
    await manager.dispatch(111, "reject_request:" + row["id"], callback=True)
    assert manager.registry.allowed(222) is approve
    assert not manager.registry.access_requests()
    manager.reply.reset_mock()
    await manager.dispatch(222, "/start")
    assert manager.reply.call_args.args[2] == (KEYBOARD if approve else ACCESS_STATUS)
    if not approve:
        await manager.dispatch(222, "access:request", callback=True, profile=profile)
        assert not any(c.args[0] == 111 for c in manager.reply.call_args_list)


def test_access_request_is_atomic_persistent_and_manual_whitelist_resolves_it(managed):
    registry = Accounts(managed)
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(
            pool.map(
                lambda _: registry.request_access(222, "Nama\nPemohon\x00", "username"), range(6)
            )
        )
    assert sum(created for _, created in rows) == 1
    assert len({row["id"] for row, _ in rows}) == 1
    assert not registry.allowed(222)
    assert not any(u["telegram_id"] == 222 for u in registry.users())
    restarted = Accounts(managed)
    assert restarted.access_requests()[0]["name"] == "Nama Pemohon"
    with pytest.raises(ValueError):
        restarted.review_request(rows[0][0]["id"], 222, True)
    restarted.whitelist(222, maximum=5)
    assert restarted.access_request(222)["status"] == "approved"
    assert restarted.quota(222) == 5
    assert not restarted.access_requests()
    restarted.whitelist(222, False)
    assert restarted.access_request(222)["status"] == "rejected"
    assert restarted.quota(222) == 5


async def test_poller_accepts_private_start_and_application_with_actual_sender_profile(
    managed, monkeypatch
):
    import ojol.management as module

    manager = MultiAccountService(managed)
    manager.reply = AsyncMock(return_value=True)
    profile = {"id": 222, "first_name": "Dewi", "last_name": "Putri", "username": "dewi_putri"}
    message = {"chat": {"id": 222, "type": "private"}, "from": profile, "text": "/start"}
    updates = [
        {"update_id": 1, "message": message},
        {
            "update_id": 2,
            "callback_query": {
                "id": "foreign",
                "from": {**profile, "id": 333},
                "message": message,
                "data": "access:request",
            },
        },
        {"update_id": 3, "message": {**message, "chat": {"type": "group", "id": -1}}},
        {
            "update_id": 4,
            "callback_query": {
                "id": "application",
                "from": profile,
                "message": message,
                "data": "access:request",
            },
        },
    ]

    async def api_call(method, **kwargs):
        if method == "getUpdates":
            manager.closing = True
            return updates
        assert method == "answerCallbackQuery" and kwargs["callback_query_id"] == "application"

    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(call=AsyncMock(side_effect=api_call))
    monkeypatch.setattr(module, "TelegramClient", lambda settings: context)
    await manager.poll_telegram()
    request = manager.registry.access_request(222)
    assert request["name"] == "Dewi Putri" and request["username"] == "dewi_putri"
    assert manager.registry.access_request(333) is None
    assert not manager.registry.allowed(222)
    assert (managed.runtime_dir / "telegram-offset").read_text() == "5"


async def test_request_buttons_do_not_allow_spoofing_identity_or_decision(managed):
    manager = MultiAccountService(managed)
    manager.reply = AsyncMock(return_value=True)
    await manager.dispatch(
        222, "access:request", callback=True, profile={"id": 333, "first_name": "Forged"}
    )
    row = manager.registry.access_request(222)
    assert row["telegram_id"] == 222 and row["name"] == "Tanpa nama"
    assert manager.registry.access_request(333) is None
    await manager.dispatch(222, "access:request:333", callback=True)
    await manager.dispatch(222, "approve_request:" + row["id"], callback=True)
    assert not manager.registry.allowed(222)
    assert manager.registry.access_request(222)["status"] == "pending"
    await manager.dispatch(111, "Management")
    await click(manager, 111, "Pengajuan Akses")
    for c in manager.reply.call_args_list:
        if len(c.args) > 2:
            for buttons in c.args[2].get("inline_keyboard", []):
                assert all(len(b["callback_data"].encode()) <= 64 for b in buttons)


def test_access_request_schema_upgrade_preserves_existing_accounts_and_limits(managed):
    registry = Accounts(managed)
    registry.whitelist(222, maximum=4)
    account = registry.create(222, "Existing account")
    registry.set_limit("max_active_workers", 2)
    with registry.db() as db:
        db.execute("DROP TABLE access_requests")  # Simulate the previous registry schema.
    upgraded = Accounts(managed)
    assert upgraded.allowed(222)
    assert upgraded.selected(222)["id"] == account["id"]
    assert upgraded.quota(222) == 4
    assert upgraded.value("max_active_workers") == 2
    assert upgraded.access_requests() == []
