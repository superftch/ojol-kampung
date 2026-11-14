import asyncio
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from starlette.testclient import TestClient

from ojol.control import ControlService, create_app
from ojol.healing import write_private
from ojol.http_api import HttpCoreError
from ojol.login_access import LoginAccess
from ojol.models import Settings, SleepSchedule
from ojol.telegram import (
    BUTTON_COMMANDS,
    KEYBOARD,
    TelegramClient,
    TelegramError,
    authorized_message,
    event_text,
    flush_notices,
    queue_error,
    queue_notice,
    set_notifications,
)


def bot_settings(settings):
    return settings.model_copy(
        update={
            "env": "local",
            "telegram_bot_token": SecretStr("fake-test-token"),
            "telegram_chat_id": 123,
        }
    )


@pytest.mark.parametrize("auto", [True, False])
def test_status_shows_account_sleep_hours_in_wib(settings, state, auto):
    service = ControlService(settings)
    state = state.model_copy(
        update={"sleep_schedule": SleepSchedule(auto=auto, start=1395, end=405, in_schedule=False)}
    )
    write_private(settings.runtime_dir / "status.json", {"snapshot": state.model_dump(mode="json")})
    assert f"Tidur otomatis • {'ON' if auto else 'OFF'} • 23.15–06.45 WIB" in service.status()


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
        "cleanup_scan",
        "visit_scan",
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


@pytest.mark.parametrize(
    "error,stage,expected",
    [
        (HttpCoreError("fixture", category="auth"), "observe.ojol", "Import Cookie"),
        (HttpCoreError("fixture", category="uncertain"), "job.search.click", "pemeriksaan hasil"),
        (HttpCoreError("fixture", category="transport"), "observe.ojol", "Coba lagi"),
        (HttpCoreError("fixture", category="schema"), "observe.ojol", "perubahan API"),
        (HttpCoreError("fixture", category="blocked"), "job.search.click", "Cek kondisi akun"),
        (TimeoutError(), "control.command.cleanup_scan", "responsnya terlalu lama"),
        (RuntimeError("sedang tidur"), "job.search.click", "Bangunkan karakter"),
        (RuntimeError("saldo minimum"), "shop.preview.data", "Cek saldo"),
        (
            RuntimeError("Tidak ada pembelian sesuai resource, anggaran, dan saldo minimum"),
            "shop.preview.data",
            "Cek stok toko",
        ),
        (RuntimeError("fixture"), "session.import.verify", "Import Cookie"),
        (RuntimeError("fixture"), "tunnel.process_exit", "Hubungi admin"),
        (RuntimeError("fixture"), "telegram.poll", "Cek Status"),
        (RuntimeError("fixture"), "worker.auto_start", "Tekan Status"),
        (RuntimeError("fixture"), "purchase.verify.data", "pemeriksaan hasil"),
        (RuntimeError("fixture"), "control.command.visit_scan", "Coba lagi"),
        (RuntimeError(), "unknown.stage", "Hubungi admin"),
    ],
)
def test_all_error_notices_have_guidance_and_correlated_id(
    settings, capsys, error, stage, expected
):
    bot = bot_settings(settings)
    path = queue_error(bot, error, stage)
    notice = json.loads(path.read_text())
    saved = json.loads((bot.runtime_dir / "last-error.json").read_text())
    logged = json.loads(capsys.readouterr().out)
    reference = notice["context"]["error_id"]
    assert reference.startswith("OJL-") and len(reference) == 16
    assert reference in notice["text"]
    assert saved["error_id"] == logged["error_id"] == reference
    assert saved["stage"] == stage and saved["notice_id"] == path.stem
    assert "Saat:" in notice["text"] and expected in notice["text"]
    assert stage not in notice["text"]
    assert f"Detail: {str(error) or type(error).__name__}" in notice["text"]
    second = queue_error(bot, error, stage)
    assert json.loads(second.read_text())["context"]["error_id"] != reference


async def test_error_id_survives_delivery_retry_with_routine_notifications_off(settings):
    bot = bot_settings(settings)
    set_notifications(bot, False)
    path = queue_error(bot, RuntimeError("fake-test-token"), "shop.preview.data")
    reference = json.loads(path.read_text())["context"]["error_id"]
    attempts = []

    def handler(request):
        attempts.append(json.loads(request.content)["text"])
        ok = len(attempts) > 1
        return httpx.Response(200 if ok else 503, json={"ok": ok, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await flush_notices(bot, client) == 0
        data = json.loads(path.read_text())
        data["next_attempt"] = 0
        path.write_text(json.dumps(data))
        assert await flush_notices(bot, client) == 1
    assert attempts[0] == attempts[1]
    assert reference in attempts[1] and "kuota HP" in attempts[1]
    assert "fake-test-token" not in attempts[1]
    assert reference in ControlService(bot).status()


@pytest.mark.parametrize("command", ["cleanup_scan", "visit_scan"])
@pytest.mark.parametrize("error", [TimeoutError(), ValueError("fixture"), RuntimeError("fixture")])
async def test_scan_errors_have_ids_without_stopping_worker(settings, monkeypatch, command, error):
    service = ControlService(settings)
    service.command = AsyncMock(side_effect=error)
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())
    await service.execute(command)
    path = next((settings.runtime_dir / "notifications").glob("*.json"))
    data = json.loads(path.read_text())
    assert data["context"]["error_id"] in data["text"]
    assert data["context"]["message"] == str(error)
    assert not (settings.runtime_dir / "STOP").exists()


@pytest.mark.parametrize("fatal", [False, True])
async def test_worker_crash_after_nonfatal_error_still_notifies(settings, monkeypatch, fatal):
    service = ControlService(settings)
    service.worker = SimpleNamespace(pid=123, returncode=2)
    previous = queue_error(
        settings,
        RuntimeError("earlier fixture"),
        "worker.reconcile",
        {"pid": 123},
        stop_worker=fatal,
    )
    previous_id = json.loads(previous.read_text())["context"]["error_id"]
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())

    async def stop_loop(seconds):
        service.closing = True

    monkeypatch.setattr("ojol.control.asyncio.sleep", stop_loop)
    await service.supervise()
    details = json.loads((settings.runtime_dir / "last-error.json").read_text())
    assert (details["error_id"] == previous_id) is fatal
    if not fatal:
        assert details["stage"] == "worker.process_exit"


async def test_telegram_renders_pending_legacy_notices_without_debug_fields(settings):
    bot = bot_settings(settings)
    set_notifications(bot, True)
    purchase = {
        "resource": "makan",
        "shop": "Akademis.ai Restaurant",
        "product": "Soto",
        "cost": "0.7",
        "before": 55,
        "after": 90,
        "wallet": "34.3",
    }
    queue_notice(
        bot,
        "📣 pembelian_terverifikasi · 11-11-2026\nRun 7 · purchase.verify.makan\n"
        + json.dumps(purchase),
        {"routine_event": True, "event": "pembelian_terverifikasi", "run_id": 7},
    )
    queue_notice(
        bot,
        "👀 Cek kondisi · idle",
        {"routine_event": True, "event": "observasi", "run_id": 7},
    )
    notice = queue_error(
        bot, RuntimeError("internal-fixture"), "purchase.verify.makan", {"pid": 22}
    )
    data = json.loads(notice.read_text())
    data["text"] = "🛑 Ojol STOP karena error\nstage: purchase.verify.makan\npid: 22"
    notice.write_text(json.dumps(data))
    sent = []

    def handle(request):
        sent.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await flush_notices(bot, client) == 2
    assert any("pemeriksaan hasil transaksi secara otomatis" in message for message in sent)
    assert any("Soto berhasil dibeli" in message and "55% ke 90%" in message for message in sent)
    assert all(
        field not in message
        for message in sent
        for field in ("purchase.verify", "run_id", "stage:", "pid:")
    )
    assert any("Detail: internal-fixture" in message for message in sent)
    diagnostics = json.loads((settings.runtime_dir / "last-error.json").read_text())
    assert diagnostics["stage"] == "purchase.verify.makan" and diagnostics["pid"] == 22


def test_telegram_only_announces_confirmed_results():
    assert event_text("observasi", {"phase": "idle"}) is None
    assert event_text("menunggu", {"seconds": 10}) is None
    assert event_text("rencana_beli", {"product": "Soto"}) is None
    assert "Ongkos 0,704 koin sudah masuk" in event_text(
        "pendapatan_ojol_tercatat", {"amount": "0.704"}
    )
    assert "Ongkos" not in event_text("trip_selesai_otomatis_teramati", {"income": None})


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
        "Saldo utama" in status and "Notifikasi • OFF" in status and "Pendapatan Ojol" not in status
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
    assert "Notifikasi • ON" in ControlService(settings).status()
    journal = Journal(settings.runtime_dir)
    controller = Controller(None, settings, journal, journal.start(settings))
    for event in ("observasi", "menunggu", "rencana_beli"):
        controller.report(event, fixture=True)
    assert not list((settings.runtime_dir / "notifications").glob("*.json"))
    controller.report("mulai", live=True)
    controller.report(
        "pembelian_terverifikasi",
        resource="makan",
        product="Soto",
        shop="Akademis.ai Restaurant",
        cost="0.7",
        before=55,
        after=90,
        wallet="34.3",
    )
    controller.report("pendapatan_ojol_tercatat", amount="0.704")
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
    assert len(calls) == 1 and "Tekan Status" in calls[0] and "fixture.error" not in calls[0]
    assert len(list((settings.runtime_dir / "notifications").glob("*.muted"))) == 3


@pytest.mark.parametrize("enabled", [False, True])
async def test_critical_notices_keep_details_and_deliver_with_routine_toggle(
    settings, monkeypatch, enabled
):
    from ojol.controller import Controller
    from ojol.journal import Journal

    bot = bot_settings(settings)
    set_notifications(bot, enabled)
    journal = Journal(bot.runtime_dir)
    try:
        controller = Controller(None, bot, journal, journal.start(bot))
        for event, data in (
            ("maintenance", {"sampai": "2026-11-14T06:30:00+00:00"}),
            ("maintenance_selesai", {}),
            ("tidur_mulai", {}),
            ("bangun", {}),
        ):
            controller.report(event, **data)
        # Already queued maintenance from an older worker may still carry the routine flag.
        queue_notice(bot, "🛠 Maintenance lama", {"routine_event": True, "event": "maintenance"})
        path = queue_error(
            bot, RuntimeError("Stok konter habis; Cookie: secret-cookie"), "shop.preview.data"
        )
        reference = json.loads(path.read_text())["context"]["error_id"]
    finally:
        journal.close()
    sent = []

    def handler(request):
        sent.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True, "result": {}})

    monkeypatch.setattr("ojol.telegram.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        while await flush_notices(bot, client):
            pass
    assert len(sent) == 6
    assert any("13:30 WIB" in text for text in sent)
    assert any("Maintenance selesai" in text for text in sent)
    assert any("Karakter sedang tidur" in text for text in sent)
    assert any("Karakter sudah bangun" in text for text in sent)
    assert any(reference in text and "Detail: Stok konter habis" in text for text in sent)
    assert all("secret-cookie" not in text for text in sent)
    assert not list((bot.runtime_dir / "notifications").glob("*.muted"))


@pytest.mark.parametrize(
    "message,secret",
    [
        ("Cookie: raw-session; extra=abc", "raw-session"),
        ("Authorization: Bearer raw-auth", "raw-auth"),
        ('password="raw-password"', "raw-password"),
        ('{"token": "raw-token"}', "raw-token"),
        ("__Secure-next-auth.session-token=raw-cookie", "raw-cookie"),
    ],
)
def test_error_detail_redacts_credentials(settings, message, secret):
    path = queue_error(settings, RuntimeError(message), "unknown.stage")
    data = json.loads(path.read_text())
    assert "Detail:" in data["text"]
    assert secret not in path.read_text()
    assert "[REDACTED]" in data["text"]


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
    data = json.loads(notice.read_text())
    assert data["context"]["error_id"] in data["text"]


def test_status_snapshot_freshness_and_worker_stop_reason(settings, monkeypatch):
    import os
    from datetime import datetime

    import ojol.control as control

    service = ControlService(settings.model_copy(update={"account_name": "Akun uji"}))
    assert "belum dijalankan" in service.status()
    (settings.runtime_dir / "last-error.json").write_text(json.dumps({"message": "Error lama"}))
    (settings.runtime_dir / "status.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "event": "menunggu",
                "snapshot_received_at": "2026-11-11T10:00:00+00:00",
                "snapshot": {"phase": "delivering", "remaining_seconds": 90},
            }
        )
    )
    monkeypatch.setattr(control, "now", lambda: datetime.fromisoformat("2026-11-11T10:00:30+00:00"))
    monkeypatch.setattr(control, "running", lambda _: True)
    active = service.status()
    assert "Akun uji" in active and "Worker aktif" in active
    assert "17:00:00 WIB" in active and "30 detik lalu" in active and "1:00" in active
    assert "Error lama" not in active and "data lama" not in active

    monkeypatch.setattr(control, "running", lambda _: False)
    stopped = service.status()
    assert "Worker berhenti" in stopped and "data lama" in stopped and "sisa trip" not in stopped
    (settings.runtime_dir / "last-error.json").write_text(
        json.dumps({"message": "Sesi kedaluwarsa"})
    )
    assert "Sesi kedaluwarsa" in service.status()


async def test_account_profit_unavailable_does_not_stop_worker(settings, monkeypatch):
    service = ControlService(settings.model_copy(update={"env": "local"}))
    (settings.runtime_dir / "http-session.json").touch()
    monkeypatch.setattr("ojol.http_core.HttpUI", Mock(side_effect=RuntimeError("unavailable")))
    await service.execute("profit")
    files = list((settings.runtime_dir / "notifications").glob("*.json"))
    assert len(files) == 1
    assert "Riwayat game tidak dapat dibaca" in json.loads(files[0].read_text())["text"]
    assert not (settings.runtime_dir / "STOP").exists()


def test_status_shows_unresolved_action_and_starting_worker(settings, state):
    from types import SimpleNamespace

    from ojol.journal import Journal

    service = ControlService(settings)
    service.worker = SimpleNamespace(pid=123, returncode=None)
    assert "Worker memulai" in service.status()
    service.worker.returncode = 1
    journal = Journal(settings.runtime_dir)
    try:
        run_id = journal.start(settings)
        action = journal.begin(run_id, "search", state, {})
        journal.settle(action, False)
        assert f"Aksi #{action} (search) menunggu rekonsiliasi" in service.status()
    finally:
        journal.close()


async def test_daily_report_uses_only_selected_account_session(settings, monkeypatch):
    from contextlib import asynccontextmanager

    from ojol.finance import report_date

    root = settings.runtime_dir
    for name in ("alpha", "beta"):
        (root / name).mkdir()
        (root / name / "http-session.json").touch()
    selected = root / "beta"
    fetched = []

    @asynccontextmanager
    async def core(account_settings):
        fetched.append(account_settings.runtime_dir)
        yield type(
            "Core",
            (),
            {
                "daily_wallet": AsyncMock(
                    return_value={
                        "income_milli": 2400,
                        "payout_count": 3,
                        "expenses_milli": {"fuel": 2700},
                        "expense_issue": None,
                        "complete": True,
                        "today_income_milli": None,
                        "issue": None,
                    }
                )
            },
        )()

    monkeypatch.setattr("ojol.http_core.HttpUI", core)
    service = ControlService(settings.model_copy(update={"env": "local", "runtime_dir": selected}))
    result = await service.account_profit(report_date("2026-11-11"))
    assert fetched == [selected]
    assert "Pendapatan Ojol seluruh akun 2,4 koin · 3 payout" in result
    assert "Estimasi laba Ojol -0,3 koin" in result
    assert "⛽ Bensin 2,7 koin · 🔧 Bengkel 0 koin · 📶 Kuota 0 koin" in result
    assert "Biaya worker terverifikasi 0 koin" in result


def test_profit_omits_estimate_when_coverage_or_expense_details_are_partial(settings):
    service = ControlService(settings)
    wallet = {
        "income_milli": 500,
        "payout_count": 1,
        "expenses_milli": {"data": 500},
        "expense_issue": None,
        "complete": True,
        "today_income_milli": None,
    }
    assert "Estimasi laba Ojol 0 koin" in service.profit(wallet=wallet)
    for complete, expense_issue in [(False, None), (True, "Nama barang kosong")]:
        report = service.profit(
            wallet={**wallet, "complete": complete, "expense_issue": expense_issue}
        )
        assert "Estimasi laba Ojol" not in report
        assert "Belanja produk Ojol ditemukan (parsial) 0,5 koin" in report
