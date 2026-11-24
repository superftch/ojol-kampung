import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.testclient import TestClient

from ojol.auto_settings import set_auto_flag
from ojol.control import ControlService, create_app
from ojol.healing import write_private
from ojol.http_api import HttpCoreError
from ojol.login_access import LoginAccess
from ojol.models import Settings, SleepSchedule
from ojol.notices import event_text, queue_error


@pytest.mark.parametrize("auto", [True, False])
def test_status_shows_account_sleep_hours_in_wib(settings, state, auto):
    service = ControlService(settings)
    state = state.model_copy(
        update={"sleep_schedule": SleepSchedule(auto=auto, start=1395, end=405, in_schedule=False)}
    )
    write_private(settings.runtime_dir / "status.json", {"snapshot": state.model_dump(mode="json")})
    assert f"Tidur otomatis • {'ON' if auto else 'OFF'} • 23.15–06.45 WIB" in service.status()


@pytest.mark.parametrize(
    "error,stage,expected",
    [
        (HttpCoreError("fixture", category="auth"), "observe.ojol", "Import Cookie"),
        (HttpCoreError("fixture", category="uncertain"), "job.search.click", "pemeriksaan hasil"),
        (HttpCoreError("fixture", category="transport"), "observe.ojol", "Coba lagi"),
        (HttpCoreError("fixture", category="schema"), "observe.ojol", "perubahan API"),
        (HttpCoreError("fixture", category="blocked"), "job.search.click", "Cek kondisi akun"),
        (
            HttpCoreError("Akun belum menjadi mitra Ojol", category="blocked"),
            "worker.reconcile",
            "Daftar jadi mitra",
        ),
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
        (RuntimeError("fixture"), "worker.auto_start", "Tekan Status"),
        (RuntimeError("fixture"), "purchase.verify.data", "pemeriksaan hasil"),
        (RuntimeError("fixture"), "control.command.visit_scan", "Coba lagi"),
        (RuntimeError(), "unknown.stage", "Hubungi admin"),
    ],
)
def test_all_error_notices_have_guidance_and_correlated_id(
    settings, capsys, error, stage, expected
):
    bot = settings
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


@pytest.mark.parametrize("command", ["cleanup_scan", "visit_scan"])
@pytest.mark.parametrize("error", [TimeoutError(), ValueError("fixture"), RuntimeError("fixture")])
async def test_scan_errors_have_ids_without_stopping_worker(settings, monkeypatch, command, error):
    service = ControlService(settings)
    service.command = AsyncMock(side_effect=error)
    await service.execute(command)
    path = next((settings.runtime_dir / "notifications").glob("*.json"))
    data = json.loads(path.read_text())
    assert data["context"]["error_id"] in data["text"]
    assert data["context"]["message"] == str(error)
    assert not (settings.runtime_dir / "STOP").exists()


@pytest.mark.parametrize("fatal", [False, True])
async def test_worker_crash_after_nonfatal_error_still_notifies(settings, monkeypatch, fatal):
    service = ControlService(settings)
    worker = SimpleNamespace(pid=123, returncode=2)
    monkeypatch.setattr(service, "worker", worker)
    previous = queue_error(
        settings,
        RuntimeError("earlier fixture"),
        "worker.reconcile",
        {"pid": 123},
        stop_worker=fatal,
    )
    previous_id = json.loads(previous.read_text())["context"]["error_id"]

    async def stop_loop(seconds):
        service.closing = True

    monkeypatch.setattr("ojol.control_service.asyncio.sleep", stop_loop)
    await service.supervise()
    details = json.loads((settings.runtime_dir / "last-error.json").read_text())
    assert (details["error_id"] == previous_id) is fatal
    if not fatal:
        assert details["stage"] == "worker.process_exit"


def test_in_app_events_announce_confirmed_results():
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
    monkeypatch.setattr(service, "worker", child)
    monkeypatch.setattr("ojol.control_service.running", lambda directory: False)
    assert "sudah aktif" in await service.command("run")
    await service.stop_worker()
    child.terminate.assert_called_once()
    assert service.expected_stop and (settings.runtime_dir / "STOP").exists()


def test_status_lists_need_percentage_and_auto_state_together(settings, state):
    state = state.model_copy(update={"needs": {"makan": 55, "fisik": 31, "rumah": 40}})
    write_private(settings.runtime_dir / "status.json", {"snapshot": state.model_dump(mode="json")})
    set_auto_flag(settings.runtime_dir, "makan", False)
    message = ControlService(settings).status()
    assert "Makan • OFF • 55%" in message
    assert "Fisik • ON • 31%" in message
    assert "Kondisi rumah • ON • 40%" in message
    assert message.count("Makan • OFF") == 1
    assert "Auto Perpus (gratis) • OFF" in message


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "resource,label,cost",
    [
        ("makan", "Makan", "0.7"),
        ("fisik", "Fisik", "2"),
        ("fisik", "Fisik", "0"),
        ("rumah", "Kondisi rumah", "0.8"),
    ],
)
def test_need_update_message_shows_verified_change_real_cost_and_auto_state(
    resource, label, cost, enabled
):
    message = event_text(
        "pembelian_terverifikasi",
        {
            "resource": resource,
            "product": "Produk fixture",
            "shop": "Tempat fixture",
            "cost": cost,
            "before": 40,
            "after": 60,
            "wallet": "30",
            "auto_enabled": enabled,
        },
    )
    assert f"✅ {label} berhasil diperbarui" in message
    assert f"{label} • 40% → 60%" in message
    assert f"Auto {label} • {'ON' if enabled else 'OFF'}" in message
    assert f"Biaya • {cost.replace('.', ',')} koin" in message
    assert "Tempat • Tempat fixture" in message and "Aksi • Produk fixture" in message
    assert "Saldo tersisa • 30 koin" in message
    if resource == "fisik" and cost == "2":
        assert "gratis" not in message


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


async def test_invalid_report_date_never_stops_gameplay(settings, monkeypatch):
    service = ControlService(settings)
    await service.execute("profit:2026-02-31")
    assert not (settings.runtime_dir / "STOP").exists()
    notice = next((settings.runtime_dir / "notifications").glob("*.json"))
    assert "Tanggal tidak valid" in json.loads(notice.read_text())["text"]
    data = json.loads(notice.read_text())
    assert data["context"]["error_id"] in data["text"]


def test_status_snapshot_freshness_and_worker_stop_reason(settings, monkeypatch):
    from datetime import datetime

    import ojol.control_service as control

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
    monkeypatch.setattr("ojol.ui.HttpUI", Mock(side_effect=RuntimeError("unavailable")))
    await service.execute("profit")
    files = list((settings.runtime_dir / "notifications").glob("*.json"))
    assert len(files) == 1
    assert "Riwayat game tidak dapat dibaca" in json.loads(files[0].read_text())["text"]
    assert not (settings.runtime_dir / "STOP").exists()


def test_status_shows_unresolved_action_and_starting_worker(settings, state, monkeypatch):
    from types import SimpleNamespace

    from ojol.journal import Journal

    service = ControlService(settings)
    worker = SimpleNamespace(pid=123, returncode=None)
    monkeypatch.setattr(service, "worker", worker)
    assert "Worker memulai" in service.status()
    worker.returncode = 1
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

    monkeypatch.setattr("ojol.ui.HttpUI", core)
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


def test_control_summary_and_dashboard_command(settings):
    service = ControlService(settings)
    summary = service.summary()
    assert summary["active"] is False
    assert summary["has_cookie"] is False
    assert summary["icon"] == "⚪"

    dash = asyncio.run(service.command("dashboard"))
    assert "📊 Dashboard Akun" in dash
    assert "Belum hubungkan cookie" in dash


async def test_kebutuhan_and_ojol_separate_buttons(settings, monkeypatch):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    from ojol.auto_settings import auto_flags
    from ojol.session_transfer import parse_cookie_input

    settings = settings.model_copy(update={"env": "local", "operator_authorized": True})
    service = ControlService(settings)
    (service.settings.runtime_dir / "http-session.json").write_text(
        json.dumps(parse_cookie_input("fixture-session"))
    )

    child = SimpleNamespace(returncode=None)
    child.terminate = Mock(side_effect=lambda: setattr(child, "returncode", -15))
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr("ojol.control_service.asyncio.create_subprocess_exec", spawn)

    # 1. Jalankan Kebutuhan starts worker with ojol OFF and needs ON
    res = await service.command("run_kebutuhan")
    assert "Auto Kebutuhan" in res
    spawn.assert_awaited_once()
    flags = auto_flags(settings.runtime_dir)
    assert flags["ojol"] is False
    assert flags["makan"] is True
    assert flags["fisik"] is True

    # 2. While running, calling run_kebutuhan again returns active notice
    res2 = await service.command("run_kebutuhan")
    assert "Auto kebutuhan aktif" in res2

    # 3. Jalankan Ojol enables Ojol in existing worker without second process
    spawn.reset_mock()
    res_ojol = await service.command("run", mode="kendara")
    assert "Auto Ojol diaktifkan" in res_ojol
    spawn.assert_not_awaited()
    flags = auto_flags(settings.runtime_dir)
    assert flags["ojol"] is True

    # 4. Hentikan Ojol disables Ojol, keeps worker and auto kebutuhan running
    res_stop_ojol = await service.command("stop_ojol")
    assert "Fitur auto kebutuhan tetap berjalan normal" in res_stop_ojol
    assert child.terminate.call_count == 0
    flags = auto_flags(settings.runtime_dir)
    assert flags["ojol"] is False
    assert flags["makan"] is True

    # 5. Hentikan Kebutuhan when Ojol is OFF stops worker
    res_stop_keb = await service.command("stop_kebutuhan")
    assert "Aktivitas akun sudah dihentikan" in res_stop_keb
    child.terminate.assert_called_once()


async def test_status_kebutuhan_and_auto_kebutuhan_commands(settings):
    service = ControlService(settings)
    (settings.runtime_dir / "status.json").write_text(
        json.dumps(
            {
                "snapshot": {
                    "observed_at": "2026-11-23T10:00:00Z",
                    "wallet": "50.0",
                    "phase": "idle",
                    "needs": {
                        "makan": 70,
                        "kesehatan": 80,
                        "fisik": 60,
                        "rekreasi": 75,
                        "kebersihan": 90,
                        "wc": 100,
                        "penampilan": 85,
                        "rumah": 95,
                    },
                    "kondisi": {"bau": False, "kebelet": False, "upahPotongBps": 0},
                    "bersih": {"mandi": 1, "sikat": 2, "mandiMaks": 2, "sikatMaks": 3},
                    "home_plot": "K40-R01",
                    "village": "kampung-sebelah",
                }
            }
        )
    )
    status_keb = await service.command("status_kebutuhan")
    assert "Status Kebutuhan" in status_keb
    assert "Makan • 70%" in status_keb
    assert "Kebersihan • 90%" in status_keb
    assert "Buang air • 100%" in status_keb
    assert "Kondisi Karakter" in status_keb
    assert "Kuota mandi hari ini • 1/2" in status_keb
    assert "Kuota sikat gigi hari ini • 2/3" in status_keb

    auto_keb = await service.command("auto_kebutuhan")
    assert "Auto Kebutuhan" in auto_keb
    assert "Makan" in auto_keb
    assert "Kebersihan" in auto_keb
    assert "Buang air" in auto_keb
