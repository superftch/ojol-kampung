import asyncio
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from starlette.testclient import TestClient

from ojol.control import ControlService, create_app
from ojol.login_access import LoginAccess
from ojol.models import Settings
from ojol.telegram import (
    BUTTON_COMMANDS,
    KEYBOARD,
    TelegramClient,
    TelegramError,
    authorized_message,
    flush_notices,
    queue_error,
)


def bot_settings(settings):
    return settings.model_copy(
        update={
            "env": "local",
            "telegram_bot_token": SecretStr("fake-test-token"),
            "telegram_chat_id": 123,
        }
    )


async def test_telegram_private_message_and_sanitized_network_error(settings):
    settings = bot_settings(settings)
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async with TelegramClient(settings, client) as api:
            await api.send("fixture")
    assert calls == [
        {
            "chat_id": 123,
            "text": "fixture",
            "link_preview_options": {"is_disabled": True},
            "protect_content": True,
            "reply_markup": KEYBOARD,
        }
    ]
    assert set(BUTTON_COMMANDS.values()) == {
        "import_cookie",
        "run",
        "stop",
        "status",
        "profit",
        "notifications_on",
        "notifications_off",
    }
    assert all(not label.startswith("/") for label in BUTTON_COMMANDS)

    def unavailable(request):
        raise httpx.ConnectError("fake-test-token", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
        async with TelegramClient(settings, client) as api:
            with pytest.raises(TelegramError) as error:
                await api.send("fixture")
    assert "fake-test-token" not in str(error.value)
    assert "telegram_bot_token" not in settings.model_dump()


def test_only_configured_private_sender_can_control(settings):
    settings = bot_settings(settings)
    message = {"chat": {"type": "private", "id": 123}, "from": {"id": 123}}
    assert authorized_message({"message": message}, settings)
    for change in [
        {"chat": {"type": "group", "id": 123}},
        {"from": {"id": 456}},
        {"chat": {"type": "private", "id": 456}},
    ]:
        assert not authorized_message({"message": {**message, **change}}, settings)
    assert not authorized_message({}, settings)


async def test_error_stops_before_send_retries_and_recovers_interrupted_outbox(settings):
    settings = bot_settings(settings)
    notice = queue_error(
        settings,
        RuntimeError("fake-test-token https://host/login/secret?state=token"),
        "purchase.verify.fuel",
        {"run_id": 7, "tab_id": "owned"},
    )
    assert (settings.runtime_dir / "STOP").exists()
    data = json.loads(notice.read_text())
    assert data["context"]["stage"] == "purchase.verify.fuel"
    assert "fake-test-token" not in notice.read_text() and "/login/secret" not in notice.read_text()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(503, json={"ok": False, "description": "offline"})
        )
    ) as client:
        assert await flush_notices(settings, client) == 0
    data = json.loads(notice.read_text())
    assert data["attempts"] == 1
    data["next_attempt"] = 0
    notice.write_text(json.dumps(data))
    claimed = notice.with_suffix(".sending")
    notice.rename(claimed)
    os.utime(claimed, (time.time() - 120, time.time() - 120))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"ok": True, "result": {}})
        )
    ) as client:
        results = await asyncio.gather(
            flush_notices(settings, client), flush_notices(settings, client)
        )
    assert sum(results) == 1
    assert notice.with_suffix(".sent").exists()


def test_login_ticket_single_use_expiry_and_revoke(settings):
    access = LoginAccess(settings.runtime_dir)
    expired = access.issue("ticket", ttl=-1)
    assert access.consume_ticket(expired) is None
    ticket = access.issue("ticket")
    assert ticket.encode() not in access.path.read_bytes()
    session = access.consume_ticket(ticket)
    assert access.expiry(session, "session")
    csrf = access.csrf_token(session)
    assert access.valid_csrf(session, csrf)
    assert not access.valid_csrf(access.issue("session"), csrf)
    assert access.consume_ticket(ticket) is None
    assert not access.expiry(ticket, "session")
    access.revoke()
    assert access.expiry(session, "session") is None


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example",
        "https://",
        "https://user:password@host",
        "https://host/path",
        "https://host?token=x",
    ],
)
def test_login_origin_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        Settings(login_public_url=url)


def test_testing_blocks_live_telegram(settings):
    with pytest.raises(ValidationError):
        Settings(env="testing", runtime_dir=settings.runtime_dir, telegram_bot_token="test")


def test_cookie_gateway_access_origin_size_and_single_use(settings, monkeypatch):
    import ojol.session_transfer as transfer

    imported = AsyncMock()
    monkeypatch.setattr(transfer, "import_session", imported)
    service = ControlService(settings)
    app = create_app(settings, service=service)
    with TestClient(app, base_url="http://localhost:6080") as client:
        assert client.get("/import-cookie").status_code == 403
        assert client.get("/login/anything").status_code == 404
        assert client.get("/view/vnc.html").status_code == 404
        ticket = service.access.issue("ticket")
        response = client.get("/access/" + ticket, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/import-cookie"
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=lax" in response.headers["set-cookie"].lower()
        page = client.get("/import-cookie")
        assert page.status_code == 200 and "Cookie sesi game" in page.text
        assert page.headers["cache-control"] == "no-store"
        assert client.get("/access/" + ticket).status_code == 403
        assert (
            client.post(
                "/import-cookie",
                data={"cookie": "dummy"},
                headers={"origin": "https://attacker.example"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/import-cookie",
                content="x" * 17000,
                headers={
                    "origin": "http://localhost:6080",
                    "content-type": "application/x-www-form-urlencoded",
                },
            ).status_code
            == 413
        )
        csrf = service.access.csrf_token(client.cookies.get("ojol_import"))
        assert (
            client.post(
                "/import-cookie", data={"cookie": "", "csrf": csrf}, headers={"origin": "null"}
            ).status_code
            == 400
        )
        result = client.post(
            "/import-cookie",
            data={"cookie": "dummy-local-session", "csrf": csrf},
            headers={"origin": "null"},
        )
        assert result.status_code == 200 and "berhasil diimpor" in result.text
        assert "dummy-local-session" not in result.text
        imported.assert_awaited_once()
        assert client.get("/import-cookie").status_code == 403


async def test_import_stops_worker_before_issuing_ticket_and_guards_errors(settings, monkeypatch):
    service = ControlService(settings)
    service.stop_worker = AsyncMock(side_effect=RuntimeError("still running"))
    with pytest.raises(RuntimeError):
        await service.cookie_link()
    service.stop_worker = AsyncMock()

    async def fail():
        raise RuntimeError("fixture")

    await service.guard_task(fail, "control.supervise")
    service.stop_worker.assert_awaited_once()
    assert (
        json.loads((settings.runtime_dir / "last-error.json").read_text())["stage"]
        == "control.supervise"
    )


def test_game_cookie_transfer_excludes_google_and_other_cookie_fields():
    from ojol.session_transfer import session_cookie

    cookie = {
        "name": "__Secure-better-auth.session_token",
        "value": "dummy-test-session",
        "domain": "www.kampungsebelah.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "size": 42,
        "session": True,
        "expires": -1,
    }
    assert set(session_cookie(cookie)) == {"name", "value", "domain", "path", "secure", "httpOnly"}
    for change in [
        {"domain": ".google.com"},
        {"name": "SID"},
        {"secure": False},
        {"httpOnly": False},
        {"path": "/other"},
    ]:
        with pytest.raises(ValueError):
            session_cookie({**cookie, **change})


async def test_restart_reports_interrupted_worker_without_restarting_gameplay(settings):
    settings = settings.model_copy(update={"env": "local", "auto_start": False})
    (settings.runtime_dir / "status.json").write_text(
        json.dumps({"pid": 999999, "run_id": 3, "event": "menunggu", "stage": "wait.countdown"})
    )
    service = ControlService(settings)
    await service.start()
    try:
        error = json.loads((settings.runtime_dir / "last-error.json").read_text())
        assert error["stage"] == "worker.interrupted" and error["last_stage"] == "wait.countdown"
        assert service.worker is None
        assert (settings.runtime_dir / "STOP").exists()
    finally:
        await service.close()


async def test_fast_double_start_and_stop_before_child_takes_lock(settings, monkeypatch):
    from unittest.mock import Mock

    settings = settings.model_copy(update={"env": "local", "operator_authorized": True})
    service = ControlService(settings)
    child = SimpleNamespace(returncode=None)
    child.terminate = Mock(side_effect=lambda: setattr(child, "returncode", -15))
    service.worker = child
    monkeypatch.setattr("ojol.control.running", lambda directory: False)
    assert "sudah aktif" in await service.command("run")
    await service.stop_worker()
    child.terminate.assert_called_once()
    assert service.expected_stop and (settings.runtime_dir / "STOP").exists()


async def test_status_profit_and_date_buttons_are_distinct(settings):
    from ojol.finance import report_date

    service = ControlService(settings)
    status = await service.command("status")
    profit = await service.command("profit")
    assert (
        "Saldo utama" in status
        and "Notifikasi event: OFF" in status
        and "Pendapatan Ojol" not in status
    )
    assert "Pendapatan Ojol" in profit and "Saldo utama" not in profit
    assert report_date().isoformat() in profit
    assert "2026-01-02" in await service.command("profit:02-01-2026")
    markup = service.profit_buttons("2026-01-02")
    values = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]
    assert (
        "profit:2026-01-01" in values and "profit:2026-01-03" in values and "choose_date" in values
    )
    assert "YYYY-MM-DD" in await service.command("choose_date") and service.awaiting_date


async def test_notification_toggle_persists_and_mutes_pending_events_but_not_errors(settings):
    from ojol.controller import Controller
    from ojol.journal import Journal
    from ojol.telegram import notifications_enabled

    service = ControlService(settings)
    assert not notifications_enabled(settings)
    await service.command("notifications_on")
    assert notifications_enabled(settings)
    assert "Notifikasi event: ON" in ControlService(settings).status()
    journal = Journal(settings.runtime_dir)
    controller = Controller(None, settings, journal, journal.start(settings))
    for event in ("observasi", "menunggu", "pembelian_terverifikasi"):
        controller.report(event, fixture=True)
    notices = list((settings.runtime_dir / "notifications").glob("*.json"))
    assert len(notices) == 3
    await service.command("notifications_off")
    assert not notifications_enabled(settings)
    controller.report("observasi")
    assert len(list((settings.runtime_dir / "notifications").glob("*.json"))) == 3
    journal.close()
    bot = bot_settings(settings)
    queue_error(bot, RuntimeError("fixture"), "fixture.error")
    calls = []

    def handler(request):
        calls.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await flush_notices(bot, client) == 1
    assert len(calls) == 1 and "fixture.error" in calls[0]
    assert len(list((settings.runtime_dir / "notifications").glob("*.muted"))) == 3


def test_cookie_form_parser_only_imports_game_session():
    from ojol.session_transfer import parse_cookie_input

    value = parse_cookie_input("dummy-test-session")
    assert value["cookies"][0]["value"] == "dummy-test-session"
    cookie = value["cookies"][0]
    assert parse_cookie_input(json.dumps([cookie])) == value
    assert parse_cookie_input(json.dumps({"cookies": [cookie]})) == value
    for source in ("", "a; SID=google", json.dumps([{**cookie, "domain": ".google.com"}])):
        with pytest.raises(ValueError):
            parse_cookie_input(source)


def test_callback_authorization(settings):
    settings = bot_settings(settings)
    callback = {
        "from": {"id": 123},
        "message": {"chat": {"id": 123, "type": "private"}},
        "data": "profit:2026-11-10",
    }
    assert authorized_message({"callback_query": callback}, settings)
    assert not authorized_message({"callback_query": {**callback, "from": {"id": 456}}}, settings)


async def test_telegram_date_callback_ack_and_message_routing(settings, monkeypatch):
    import ojol.control as module

    service = ControlService(bot_settings(settings))
    service.execute = AsyncMock()
    authorized = {
        "from": {"id": 123},
        "message": {"chat": {"id": 123, "type": "private"}},
        "id": "callback-fixture",
        "data": "profit:2026-11-09",
    }
    updates = [
        {"update_id": 1, "callback_query": {**authorized, "from": {"id": 456}}},
        {"update_id": 2, "callback_query": authorized},
        {
            "update_id": 3,
            "message": {
                "from": {"id": 123},
                "chat": {"id": 123, "type": "private"},
                "text": "09-11-2026",
            },
        },
    ]
    api = SimpleNamespace()

    async def call(method, **kwargs):
        if method == "getUpdates":
            assert kwargs["allowed_updates"] == ["message", "callback_query"]
            service.closing = True
            return updates
        assert method == "answerCallbackQuery" and kwargs["callback_query_id"] == "callback-fixture"

    api.call = AsyncMock(side_effect=call)
    context = AsyncMock()
    context.__aenter__.return_value = api
    monkeypatch.setattr(module, "TelegramClient", lambda settings: context)
    await service.poll_telegram()
    assert [c.args[0] for c in service.execute.await_args_list] == [
        "profit:2026-11-09",
        "profit:09-11-2026",
    ]
    assert (settings.runtime_dir / "telegram-offset").read_text() == "4"


async def test_invalid_report_date_never_stops_gameplay(settings, monkeypatch):
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())
    service = ControlService(settings)
    await service.execute("profit:2026-02-31")
    assert not (settings.runtime_dir / "STOP").exists()
    notice = next((settings.runtime_dir / "notifications").glob("*.json"))
    assert "Tanggal tidak valid" in json.loads(notice.read_text())["text"]
