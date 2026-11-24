import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ojol.accounts import Accounts
from ojol.control import create_app
from ojol.identity import save_profile
from ojol.maintenance import MaintenanceWindow
from ojol.management import MultiAccountService
from ojol.session_transfer import parse_cookie_input
from ojol.web_auth import hash_password, verify_password, verify_telegram_widget
from ojol.worker_service import WorkerService


def make_tg_auth_data(
    bot_token: str,
    telegram_id: int,
    username: str = "testuser",
    first_name: str = "Test",
    auth_date: int | None = None,
) -> dict:
    if auth_date is None:
        auth_date = int(time.time())
    data = {
        "id": str(telegram_id),
        "first_name": first_name,
        "username": username,
        "auth_date": str(auth_date),
    }
    data_check = sorted(f"{k}={v}" for k, v in data.items())
    data_check_string = "\n".join(data_check)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    data["hash"] = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return data


def test_password_hashing():
    pwd = "secretpassword123"
    hashed, salt = hash_password(pwd)
    assert verify_password(pwd, salt, hashed) is True
    assert verify_password("wrongpass", salt, hashed) is False


def test_telegram_widget_verification():
    bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    data = make_tg_auth_data(bot_token, 987654321)
    assert verify_telegram_widget(data, bot_token) is True

    # Tampered data
    bad_data = dict(data, first_name="Hacker")
    assert verify_telegram_widget(bad_data, bot_token) is False

    # Expired data
    old_data = make_tg_auth_data(bot_token, 987654321, auth_date=int(time.time()) - 90000)
    assert verify_telegram_widget(old_data, bot_token) is False


def test_web_auth_registration_approval_flow(settings):
    # Setting with admin chat id and telegram enabled
    admin_settings = settings.model_copy(update={"telegram_chat_id": 999, "telegram_enabled": True})
    registry = Accounts(admin_settings)

    # 1. Register new user -> status pending
    user = registry.web.register("driver_budi", "password123", "Budi Santoso")
    assert user["username"] == "driver_budi"
    assert user["status"] == "pending"
    assert user["role"] == "user"

    # 2. Cannot login while pending
    with pytest.raises(ValueError, match="menunggu persetujuan admin"):
        registry.web.authenticate_password("driver_budi", "password123")

    # 3. Wrong password
    with pytest.raises(ValueError, match="Username atau password salah"):
        registry.web.authenticate_password("driver_budi", "wrongpass")

    # 4. Admin reviews and approves user
    approved = registry.web.review_user(user["id"], 999, approve=True)
    assert approved["status"] == "approved"

    # 5. Now can login
    logged_in = registry.web.authenticate_password("driver_budi", "password123")
    assert logged_in["username"] == "driver_budi"

    # 6. Session issuance & lookup
    token = registry.web.issue_session(logged_in["id"])
    retrieved = registry.web.get_user_by_session(token)
    assert retrieved is not None
    assert retrieved["username"] == "driver_budi"
    assert "password_hash" not in retrieved

    # 7. Session revocation
    registry.web.revoke_session(token)
    assert registry.web.get_user_by_session(token) is None


def test_telegram_code_login_and_connect_flow(settings):
    admin_settings = settings.model_copy(update={"telegram_chat_id": 111})
    registry = Accounts(admin_settings)

    # Allow a telegram user first in bot
    registry.whitelist(222, enabled=True, name="Siti", username="siti_tg")

    # 1. Telegram login code
    code = registry.web.issue_telegram_login_code(222)
    user = registry.web.authenticate_telegram_code(code)
    assert user["telegram_id"] == 222
    assert user["status"] == "approved"

    # Re-using code fails
    with pytest.raises(ValueError, match="Kode login tidak valid"):
        registry.web.authenticate_telegram_code(code)

    # 2. Register a web user, approve them, then connect Telegram
    web_user = registry.web.register("joko_web", "passjoko123", "Joko")
    registry.web.review_user(web_user["id"], 111, approve=True)

    # Joko creates game accounts while still web-only
    owner = registry.web.get_owner_for_user(web_user)
    acc = registry.create(owner, "Akun Ojol Joko")
    assert acc["owner"] == owner

    # Joko issues a connect code to link with his Telegram (say ID 333)
    link_code = registry.web.issue_telegram_link_code(web_user["id"])
    linked_user = registry.web.consume_telegram_link_code(
        link_code, 333, name="Joko Anwar", username="joko_tg"
    )
    assert linked_user["telegram_id"] == 333

    # Verify accounts are now owned by 333
    joko_accounts = registry.list(333)
    assert len(joko_accounts) == 1
    assert joko_accounts[0]["name"] == "Akun Ojol Joko"

    # Disconnect Telegram
    disconnected = registry.web.disconnect_telegram(web_user["id"])
    assert disconnected["telegram_id"] is None
    new_owner = registry.web.get_owner_for_user(disconnected)
    assert len(registry.list(new_owner)) == 1


def test_web_routes_and_dashboard_api(settings, monkeypatch):
    admin_settings = settings.model_copy(
        update={
            "telegram_chat_id": 111,
            "telegram_bot_token": "mock-token",
            "telegram_enabled": True,
        }
    )
    manager = MultiAccountService(admin_settings)
    manager.start = AsyncMock()
    manager.close = AsyncMock()

    app = create_app(admin_settings, service=None)
    with TestClient(app, base_url="http://localhost:6080") as client:
        # 1. Unauthenticated root redirects to /login
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/login"

        # 2. Login page renders
        res = client.get("/login")
        assert res.status_code == 200
        assert "Kampung Ojol Automation" in res.text

        # 3. Register page renders
        res = client.get("/register")
        assert res.status_code == 200
        assert "Daftar Akun Baru" in res.text

        # 4. Register via API
        reg_res = client.post(
            "/api/auth/register",
            json={"username": "agus_ojol", "password": "password123", "name": "Agus"},
        )
        assert reg_res.status_code == 200
        assert reg_res.json()["user"]["status"] == "pending"
        assert {"password_hash", "salt"}.isdisjoint(reg_res.json()["user"])

        # 5. Try login before approval -> 400
        login_res = client.post(
            "/api/auth/login",
            json={"username": "agus_ojol", "password": "password123"},
        )
        assert login_res.status_code == 400
        assert "menunggu persetujuan" in login_res.json()["detail"]

        # 6. Admin approves user
        user_id = reg_res.json()["user"]["id"]
        manager.registry.web.review_user(user_id, 111, approve=True)

        # 7. Login after approval -> success with cookie
        login_ok = client.post(
            "/api/auth/login",
            json={"username": "agus_ojol", "password": "password123"},
        )
        assert login_ok.status_code == 200
        assert {"password_hash", "salt"}.isdisjoint(login_ok.json()["user"])
        assert "ojol_web_session" in client.cookies

        # 8. Now root page returns 200 dashboard HTML
        dash_page = client.get("/")
        assert dash_page.status_code == 200
        assert "Dashboard" in dash_page.text
        assert "limitNoticeCard" in dash_page.text
        assert "extensionModal" in dash_page.text
        assert "btnCookieToolbar" in dash_page.text
        assert "openCookieModalFor" in dash_page.text
        assert "cookieTargetAccountId" in dash_page.text
        assert '<dialog id="cookieModal"' in dash_page.text
        assert 'aria-label="Pilih akun game"' in dash_page.text
        assert "tab-bank-angka" in dash_page.text
        assert "Bank Angka" in dash_page.text
        assert "bankReviewBanner" in dash_page.text
        assert "manualGlyphModal" in dash_page.text
        stylesheet = client.get("/ui/console.css")
        assert stylesheet.status_code == 200 and "DM Sans" in stylesheet.text
        assert client.get("/ui/dm-sans.woff2").content.startswith(b"wOF2")

        # 9. GET /api/dashboard
        dash_api = client.get("/api/dashboard")
        assert dash_api.status_code == 200
        dash_json = dash_api.json()
        assert "accounts" in dash_json
        assert "summary" in dash_json
        assert "limit_reached" in dash_json
        assert "pending_bank_reviews_count" in dash_json

        # Bank Angka Endpoints
        bank_get = client.get("/api/bank-angka")
        assert bank_get.status_code == 200
        bank_data = bank_get.json()
        assert "templates" in bank_data
        assert "pending" in bank_data
        assert "total_templates" in bank_data

        save_res = client.post(
            "/api/bank-angka/save",
            json={"digit": "4", "glyph": [[[0.86, 1.0], [0.86, 0.0], [0.0, 0.74]]]},
        )
        assert save_res.status_code == 200
        assert save_res.json()["ok"] is True
        assert save_res.json()["digit"] == "4"

        bank_after = client.get("/api/bank-angka").json()
        assert "4" in bank_after["templates"]

        del_res = client.post(
            "/api/bank-angka/delete",
            json={"digit": "4", "index": len(bank_after["templates"]["4"]) - 1},
        )
        assert del_res.status_code == 200
        assert del_res.json()["ok"] is True

        dismiss_res = client.post(
            "/api/bank-angka/dismiss",
            json={"review_id": "dummy-rev-id"},
        )
        assert dismiss_res.status_code == 200

        # 9b. Download extension zip endpoint
        import io
        import zipfile

        dl_res = client.get("/api/extension/download")
        assert dl_res.status_code == 200
        assert dl_res.headers["content-type"] == "application/zip"
        assert "kampungsebelah-extension.zip" in dl_res.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(dl_res.content), "r") as zf:
            namelist = zf.namelist()
            assert "kampungsebelah-extension/manifest.json" in namelist
            assert "kampungsebelah-extension/ojol.js" in namelist
            assert "kampungsebelah-extension/mancing.js" in namelist

        dl_alias = client.get("/download/extension.zip")
        assert dl_alias.status_code == 200
        assert dl_alias.headers["content-type"] == "application/zip"

        # 10. Create account via Web API
        create_acc = client.post("/api/accounts/create", json={"name": "Akun Agus 1"})
        assert create_acc.status_code == 200
        assert create_acc.json()["account"]["name"] == "Akun Agus 1"
        second_acc = client.post("/api/accounts/create", json={"name": "Akun Agus 2"})
        third_acc = client.post("/api/accounts/create", json={"name": "Akun Agus 3"})
        assert second_acc.status_code == third_acc.status_code == 200
        assert client.get("/api/accounts").json()["quota"] == 3
        over_quota = client.post("/api/accounts/create", json={"name": "Akun Agus 4"})
        assert over_quota.status_code == 400
        assert "Batas akun" in over_quota.json()["detail"]

        # 11. Rename account
        acc_id = create_acc.json()["account"]["id"]
        rename_res = client.post(
            "/api/accounts/rename", json={"account_id": acc_id, "name": "Akun Agus Utama"}
        )
        assert rename_res.status_code == 200

        # 11b. Attempt to run ojol without permission -> returns 400 JSON detail, not unhandled 500
        run_res = client.post("/api/control/run")
        assert run_res.status_code == 400
        assert "detail" in run_res.json()
        assert "belum diizinkan" in run_res.json()["detail"]

        # 11c. With operator authorization but no cookie -> returns 400 JSON with session missing message
        app.state.manager.settings.operator_authorized = True
        run_res2 = client.post("/api/control/run")
        assert run_res2.status_code == 400
        assert "detail" in run_res2.json()
        assert (
            "Sesi game belum tersedia" in run_res2.json()["detail"]
            or "Import Cookie" in run_res2.json()["detail"]
        )

        # 12. Toggle auto flag
        toggle_res = client.post(
            "/api/control/toggle-auto", json={"flag": "makan", "enabled": True}
        )
        assert toggle_res.status_code == 200
        assert toggle_res.json()["enabled"] is True

        # 13. Mode Ojol & study subject
        mode_res = client.post("/api/control/mode-ojol", json={"mode": "kendara"})
        assert mode_res.status_code == 200
        study_res = client.post("/api/control/study-subject", json={"subject": "teknik"})
        assert study_res.status_code == 200

        # 14. Issue telegram connect code
        conn_res = client.post("/api/auth/connect-telegram/issue-code")
        assert conn_res.status_code == 200
        assert "code" in conn_res.json()

        # Non-admin cannot access admin endpoints
        assert client.get("/api/admin/pending").status_code == 403
        assert client.get("/api/admin/users").status_code == 403

        # 15. Logout
        logout_res = client.post("/api/auth/logout")
        assert logout_res.status_code == 200
        # Cookie removed or invalidated
        unauth_dash = client.get("/api/dashboard")
        assert unauth_dash.status_code == 401


@pytest.fixture
def admin_web(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        credentials = {"username": "web_admin", "password": "fixture-password"}
        assert (
            client.post(
                "/api/auth/register", json={**credentials, "name": "Admin & <Ops>"}
            ).status_code
            == 200
        )
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        yield client, app.state.manager


def test_web_cookie_onboarding_and_archive(admin_web, monkeypatch):
    client, manager = admin_web

    async def install_fixture(settings, payload):
        directory = settings.runtime_dir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "http-session.json").write_text(payload)
        profile = {"nickname": "Akun pertama", "balanceMilli": 112113}
        save_profile(directory, profile)
        return profile

    install = AsyncMock(side_effect=install_fixture)
    monkeypatch.setattr("ojol.session_transfer.import_session", install)
    assert r"Admin & \u003cOps>" in client.get("/").text
    assert client.get("/api/dashboard").json()["account"] is None
    response = client.post("/api/control/import-cookie", json={"cookie": "fixture-session"})
    assert response.status_code == 200
    first = client.get("/api/dashboard").json()["account"]
    assert first["name"] == "Akun pertama"
    assert first["has_cookie"] is True
    assert "cookie_hash" not in first

    archived = client.post("/api/accounts/archive", json={"account_id": first["id"]})
    assert archived.status_code == 200
    row = client.get("/api/accounts").json()["accounts"][0]
    assert row["archived"] and row["has_cookie"] and not row["is_running"]
    assert client.get("/api/dashboard").json()["accounts"] == []
    account = manager.registry.get(first["id"], archived=True)
    assert (manager.registry.scoped_settings(account).runtime_dir / "STOP").is_file()

    second = client.post("/api/accounts/create", json={"name": "Cadangan"}).json()["account"]
    invalid = client.post(
        "/api/control/import-cookie",
        json={"cookie": "different-fixture", "account_id": first["id"]},
    )
    assert invalid.status_code == 400
    assert install.await_count == 1
    assert client.get("/api/dashboard").json()["account"]["id"] == second["id"]
    restored = client.post(
        "/api/accounts/archive", json={"account_id": first["id"], "archived": False}
    )
    assert restored.status_code == 200
    assert len(client.get("/api/dashboard").json()["accounts"]) == 2


def test_web_dashboard_keeps_fractional_balances(admin_web):
    client, manager = admin_web
    for name, wallet, income in (("Satu", "112.113", "0.704"), ("Dua", "1500", "1.001")):
        account = client.post("/api/accounts/create", json={"name": name}).json()["account"]
        directory = manager.service(account["id"]).settings.runtime_dir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "status.json").write_text(
            json.dumps(
                {
                    "snapshot_received_at": "2026-11-24T01:00:00+00:00",
                    "snapshot": {"wallet": wallet, "today_income": income, "today_count": 1},
                }
            )
        )
        (directory / "game-sync.json").write_text(
            json.dumps(
                {
                    "checked_at": "2026-11-24T00:00:00+00:00",
                    "snapshot": {"wallet": "0", "today_income": "0", "today_count": 0},
                }
            )
        )
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    totals = response.json()["all_accounts_summary"]
    assert totals["total_wallet"] == "1.612,113"
    assert totals["total_income"] == "1,705"
    assert totals["total_wallet_num"] == 1612.113
    assert totals["total_trips"] == 2
    assert response.json()["snapshot"]["wallet"] == "1500"


def test_web_admin_rejects_invalid_worker_settings(admin_web):
    client, manager = admin_web
    response = client.post(
        "/api/admin/settings", json={"max_active_workers": 0, "idle_poll_seconds": 25}
    )
    assert response.status_code == 400
    assert manager.registry.get_all_settings()["max_active_workers"] == 3
    assert manager.registry.get_all_settings()["idle_poll_seconds"] == 10
    valid = client.post("/api/admin/settings", json={"max_active_workers": "2"})
    assert valid.status_code == 200
    assert valid.json()["settings"]["max_active_workers"] == 2


def test_web_run_respects_account_target_and_worker_capacity(admin_web, monkeypatch):
    client, manager = admin_web
    manager.settings.operator_authorized = True
    manager.registry.set_limit("max_active_workers", 1)
    first, second = [
        client.post("/api/accounts/create", json={"name": name}).json()["account"]["id"]
        for name in ("Satu", "Dua")
    ]
    for account_id in (first, second):
        directory = manager.service(account_id).settings.runtime_dir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "http-session.json").write_text(json.dumps(parse_cookie_input(account_id)))

    worker = WorkerService(manager.settings)
    spawn = AsyncMock(return_value=SimpleNamespace(pid=1234, returncode=None))
    monkeypatch.setattr("ojol.worker_service.asyncio.create_subprocess_exec", spawn)

    async def dispatch(directory, command, **kwargs):
        return await worker.handle_request(command) if command["action"] == "start" else None

    monkeypatch.setattr("ojol.worker_service.send_worker_command", dispatch)
    manager.maintenance_file.write_text(json.dumps(MaintenanceWindow.create_manual().payload()))
    response = client.post("/api/control/run-needs", params={"account_id": first})
    assert response.status_code == 200
    assert first in worker.workers and second not in worker.workers
    manager.maintenance_file.unlink()
    assert client.get("/api/dashboard").json()["account"]["id"] == second
    rejected = client.post("/api/control/run", params={"account_id": second})
    assert rejected.status_code == 400
    assert "Slot worker penuh" in rejected.json()["detail"]
    spawn.assert_awaited_once()


def test_telegram_widget_login_and_existing_accounts_merge(settings):
    bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    admin_settings = settings.model_copy(
        update={"telegram_chat_id": 999, "telegram_bot_token": bot_token}
    )
    manager = MultiAccountService(admin_settings)
    manager.start = AsyncMock()
    manager.close = AsyncMock()

    # Pre-existing Telegram user with game accounts
    manager.registry.whitelist(555, enabled=True, name="Bambang TG", username="bambang555")
    manager.registry.create(555, "Akun Motor Bambang")
    manager.registry.create(555, "Akun Mobil Bambang")
    assert len(manager.registry.list(555)) == 2

    app = create_app(admin_settings, service=None)
    with TestClient(app, base_url="http://localhost:6080") as client:
        # A. Login directly via Telegram Widget
        tg_data = make_tg_auth_data(bot_token, 555, username="bambang555", first_name="Bambang")
        query_str = "&".join(f"{k}={v}" for k, v in tg_data.items())
        res = client.get(f"/api/auth/telegram/callback?{query_str}", follow_redirects=False)
        assert res.status_code == 303
        assert "ojol_web_session" in client.cookies

        # Dashboard now lists both pre-existing game accounts
        dash_res = client.get("/api/dashboard")
        assert dash_res.status_code == 200
        accounts = dash_res.json()["accounts"]
        account_names = [a["name"] for a in accounts]
        assert "Akun Motor Bambang" in account_names
        assert "Akun Mobil Bambang" in account_names

        # Logout
        client.post("/api/auth/logout")

        # B. User created with username/password, then links existing Telegram account
        reg_res = client.post(
            "/api/auth/register",
            json={"username": "bambang_web", "password": "bambangpass", "name": "Bambang Web"},
        )
        assert reg_res.status_code == 200
        web_user_id = reg_res.json()["user"]["id"]
        # Admin approves
        manager.registry.web.review_user(web_user_id, 999, approve=True)

        # Login with username/password
        login_res = client.post(
            "/api/auth/login",
            json={"username": "bambang_web", "password": "bambangpass"},
        )
        assert login_res.status_code == 200

        # Bambang generates link code from web
        code_res = client.post("/api/auth/connect-telegram/issue-code")
        assert code_res.status_code == 200
        link_code = code_res.json()["code"]

        # In bot, /connect <code_res>
        manager.registry.web.consume_telegram_link_code(
            link_code, 555, name="Bambang", username="bambang555"
        )

        # Now Web user bambang_web has access to his existing Telegram accounts!
        dash_merged = client.get("/api/dashboard")
        assert dash_merged.status_code == 200
        merged_names = [a["name"] for a in dash_merged.json()["accounts"]]
        assert "Akun Motor Bambang" in merged_names
        assert "Akun Mobil Bambang" in merged_names


def test_telegram_bot_commands_for_web_login_and_connect(settings):
    bot_token = "123456:mock"
    admin_settings = settings.model_copy(
        update={"telegram_chat_id": 999, "telegram_bot_token": bot_token}
    )
    manager = MultiAccountService(admin_settings)
    manager.reply = AsyncMock()

    # Allow a user
    manager.registry.whitelist(777, enabled=True, name="Dewi", username="dewi777")

    # 1. Dewi types /web in bot
    import asyncio

    asyncio.run(manager.dispatch(777, "/web"))
    assert manager.reply.called
    reply_text = manager.reply.call_args.args[1]
    assert "Kode login Anda:" in reply_text

    # Extract code
    import re

    m = re.search(r"`(\d{6})`", reply_text)
    assert m is not None
    code = m.group(1)

    # Dewi uses code on web
    app = create_app(admin_settings, service=None)
    with TestClient(app, base_url="http://localhost:6080") as client:
        code_login = client.post("/api/auth/telegram-code", json={"code": code})
        assert code_login.status_code == 200
        assert code_login.json()["user"]["telegram_id"] == 777
        assert "ojol_web_session" in client.cookies

    # 2. Web user connects via /connect command in bot
    web_user = manager.registry.web.register("dewi_portal", "dewipassword", "Dewi Portal")
    manager.registry.web.review_user(web_user["id"], 999, approve=True)
    link_code = manager.registry.web.issue_telegram_link_code(web_user["id"])

    # Disconnect 777 first so it can link to dewi_portal
    manager.registry.web.disconnect_telegram(code_login.json()["user"]["id"])

    # Dewi sends /connect <link_code> to bot
    asyncio.run(manager.dispatch(777, f"/connect {link_code}"))
    connect_reply = manager.reply.call_args.args[1]
    assert "berhasil dihubungkan" in connect_reply


def test_web_first_user_is_admin_and_notifications_flow(settings):
    from ojol.control import create_app
    from ojol.telegram import queue_notice

    app = create_app(settings, service=None)
    with TestClient(app, base_url="http://localhost:6080") as client:
        # Register first user -> should be approved admin
        reg_res = client.post(
            "/api/auth/register",
            json={
                "username": "superadmin",
                "password": "superpassword123",
                "name": "Super Admin",
            },
        )
        assert reg_res.status_code == 200
        user = reg_res.json()["user"]
        assert user["status"] == "approved"
        assert user["role"] == "admin"

        # Login
        login_res = client.post(
            "/api/auth/login",
            json={"username": "superadmin", "password": "superpassword123"},
        )
        assert login_res.status_code == 200
        assert "ojol_web_session" in client.cookies

        # Queue a notice
        notice_path = queue_notice(
            settings,
            "📣 trip_selesai_otomatis_teramati · Order selesai",
            {"event": "trip_selesai_otomatis_teramati"},
        )
        assert notice_path.is_file()

        # Check /api/notifications
        notif_res = client.get("/api/notifications")
        assert notif_res.status_code == 200
        notifs = notif_res.json()["notifications"]
        assert len(notifs) >= 1
        target_notif = next(n for n in notifs if n["id"] == notice_path.stem)
        assert target_notif["read"] is False

        # Mark as read
        read_res = client.post(
            "/api/notifications/read",
            json={"ids": [notice_path.stem]},
        )
        assert read_res.status_code == 200
        assert read_res.json()["marked_count"] == 1

        # Re-check /api/notifications
        notif_res2 = client.get("/api/notifications")
        notifs2 = notif_res2.json()["notifications"]
        target_notif2 = next(n for n in notifs2 if n["id"] == notice_path.stem)
        assert target_notif2["read"] is True


def test_telegram_login_prompts_setup_password_flow(settings):
    from ojol.accounts import Accounts
    from ojol.control import create_app

    admin_settings = settings.model_copy(update={"telegram_chat_id": 999})
    registry = Accounts(admin_settings)
    registry.whitelist(888, enabled=True, name="Budi", username="budi_tg")
    app = create_app(admin_settings, service=None)

    with TestClient(app, base_url="http://localhost:6080") as client:
        # 1. User arrives via telegram code
        code = registry.web.issue_telegram_login_code(888)
        login_res = client.post("/api/auth/telegram-code", json={"code": code})
        assert login_res.status_code == 200
        data = login_res.json()
        assert data["setup_required"] is True
        assert data["redirect"] == "/setup-password"
        assert "ojol_web_session" in client.cookies

        # 2. Accessing "/" should redirect to "/setup-password"
        dash_res = client.get("/", follow_redirects=False)
        assert dash_res.status_code == 303
        assert dash_res.headers["location"] == "/setup-password"

        # 3. Accessing "/setup-password" renders HTML form
        setup_page = client.get("/setup-password")
        assert setup_page.status_code == 200
        assert "Buat Akun Web Anda" in setup_page.text

        # 4. Submit setup password with mismatch confirm password
        bad_sub = client.post(
            "/api/auth/setup-password",
            json={
                "username": "driver_hebat",
                "password": "mypassword123",
                "confirm_password": "differentpassword",
            },
        )
        assert bad_sub.status_code == 400

        # 5. Submit valid credentials
        good_sub = client.post(
            "/api/auth/setup-password",
            json={
                "username": "driver_hebat",
                "password": "mypassword123",
                "confirm_password": "mypassword123",
            },
        )
        assert good_sub.status_code == 200
        assert good_sub.json()["user"]["username"] == "driver_hebat"
        assert good_sub.json()["user"]["has_password"] == 1

        # 6. Now accessing "/" succeeds and shows dashboard
        dash_res2 = client.get("/", follow_redirects=False)
        assert dash_res2.status_code == 200
        assert "Kampung Ojol" in dash_res2.text

        # 7. Logout and login using new username and password directly
        client.post("/api/auth/logout")
        pw_login = client.post(
            "/api/auth/login",
            json={"username": "driver_hebat", "password": "mypassword123"},
        )
        assert pw_login.status_code == 200
        assert pw_login.json()["user"]["username"] == "driver_hebat"


def test_admin_notifications_panel_and_api(settings):
    from unittest.mock import AsyncMock

    from ojol.control import create_app
    from ojol.management import MultiAccountService
    from ojol.notifications import list_all_admin_notifications
    from ojol.telegram import queue_notice

    admin_settings = settings.model_copy(update={"telegram_chat_id": 999})
    manager = MultiAccountService(admin_settings)
    manager.start = AsyncMock()
    manager.close = AsyncMock()

    app = create_app(admin_settings, service=manager)
    with TestClient(app, base_url="http://localhost:6080") as client:
        # 1. Register first user (Super Admin)
        reg_admin = client.post(
            "/api/auth/register",
            json={"username": "bossadmin", "password": "adminpassword123", "name": "Boss Admin"},
        )
        assert reg_admin.status_code == 200
        admin_data = reg_admin.json()["user"]
        assert admin_data["role"] == "admin"

        # 2. Register second user (Regular User)
        reg_user = client.post(
            "/api/auth/register",
            json={"username": "driveragus", "password": "aguspassword123", "name": "Agus Driver"},
        )
        assert reg_user.status_code == 200
        user_data = reg_user.json()["user"]
        assert user_data["role"] == "user"

        # Admin approves user
        manager.registry.web.review_user(user_data["id"], admin_data["id"], True)

        # 3. Create game accounts for both users
        admin_owner = manager.registry.owner_for_user(admin_data)
        user_owner = manager.registry.owner_for_user(user_data)

        acc_admin = manager.registry.create(admin_owner, "Akun Admin Alpha")
        acc_user = manager.registry.create(user_owner, "Akun Agus Motor")

        scoped_admin = manager.registry.scoped_settings(acc_admin)
        scoped_user = manager.registry.scoped_settings(acc_user)

        # 4. Queue notices in different scopes
        notice_user = queue_notice(
            scoped_user,
            "Pesanan baru masuk untuk Agus Motor",
            context={"event": "order_masuk"},
        )
        notice_admin = queue_notice(
            scoped_admin,
            "Sistem warning kapasitas baterai",
            context={"event": "low_battery", "stage": "battery"},
        )
        notice_system = queue_notice(
            admin_settings,
            "Pemberitahuan pemeliharaan server pusat",
        )

        # Test direct notifications helper functions
        all_notices = list_all_admin_notifications(admin_settings, registry=manager.registry)
        assert len(all_notices) >= 3
        notice_ids = {n["id"] for n in all_notices}
        assert notice_user.stem in notice_ids
        assert notice_admin.stem in notice_ids
        assert notice_system.stem in notice_ids

        # Check account and user mapping
        user_item = next(n for n in all_notices if n["id"] == notice_user.stem)
        assert user_item["account_name"] == "Akun Agus Motor"
        assert user_item["user"]["username"] == "driveragus"

        admin_item = next(n for n in all_notices if n["id"] == notice_admin.stem)
        assert admin_item["account_name"] == "Akun Admin Alpha"
        assert admin_item["is_error"] is True

        # 5. Non-admin user interaction
        client.post(
            "/api/auth/login", json={"username": "driveragus", "password": "aguspassword123"}
        )
        dash_user_res = client.get("/")
        assert dash_user_res.status_code == 200
        # Admin subnav and panel should NOT be visible to regular user in the DOM
        assert 'id="btnSubNotifAdmin"' not in dash_user_res.text
        assert 'id="panelNotifAdmin"' not in dash_user_res.text

        # Non-admin forbidden from admin notifications API
        admin_notif_forbidden = client.get("/api/admin/notifications")
        assert admin_notif_forbidden.status_code == 403
        admin_read_forbidden = client.post("/api/admin/notifications/read")
        assert admin_read_forbidden.status_code == 403

        # Regular notification endpoint works for user's own active account
        user_notif_res = client.get("/api/notifications")
        assert user_notif_res.status_code == 200
        user_notif_ids = {n["id"] for n in user_notif_res.json()["notifications"]}
        assert notice_user.stem in user_notif_ids
        assert notice_admin.stem not in user_notif_ids
        bad_target = client.post("/api/control/run", params={"account_id": acc_admin["id"]})
        assert bad_target.status_code == 400
        archived = client.post("/api/accounts/archive", json={"account_id": acc_user["id"]})
        assert archived.status_code == 200
        assert client.get("/api/notifications").json()["notifications"] == []
        assert client.post("/api/notifications/read").json()["marked_count"] == 0

        client.post("/api/auth/logout")

        # 6. Admin user interaction
        client.post(
            "/api/auth/login", json={"username": "bossadmin", "password": "adminpassword123"}
        )
        dash_admin_res = client.get("/")
        assert dash_admin_res.status_code == 200
        # Admin subnav and admin panel elements MUST exist
        assert 'id="btnSubNotifAdmin"' in dash_admin_res.text
        assert 'id="panelNotifAdmin"' in dash_admin_res.text
        assert 'id="adminNotificationsList"' in dash_admin_res.text
        assert 'id="filterAdminNotifUser"' in dash_admin_res.text
        assert 'id="filterAdminNotifAccount"' in dash_admin_res.text
        assert "loadAdminNotifications" in dash_admin_res.text

        # Admin notifications API works
        admin_api_res = client.get("/api/admin/notifications")
        assert admin_api_res.status_code == 200
        admin_notif_data = admin_api_res.json()["notifications"]
        admin_notif_ids = {n["id"] for n in admin_notif_data}
        assert notice_user.stem in admin_notif_ids
        assert notice_admin.stem in admin_notif_ids
        assert notice_system.stem in admin_notif_ids
        assert not next(n for n in admin_notif_data if n["id"] == notice_system.stem)["read"]

        # Admin mark all read
        mark_res = client.post("/api/admin/notifications/read")
        assert mark_res.status_code == 200
        assert mark_res.json()["success"] is True
        assert mark_res.json()["marked_count"] >= 3

        # Verify all are marked read
        recheck = client.get("/api/admin/notifications")
        recheck_data = recheck.json()["notifications"]
        for n in recheck_data:
            if n["id"] in {notice_user.stem, notice_admin.stem, notice_system.stem}:
                assert n["read"] is True


def test_web_dashboard_logs_formatting(admin_web):
    client, manager = admin_web
    create_res = client.post("/api/accounts/create", json={"name": "Akun Test Logs"})
    assert create_res.status_code == 200
    account = create_res.json()["account"]
    scoped = manager.registry.scoped_settings(account)
    r_dir = scoped.runtime_dir
    r_dir.mkdir(parents=True, exist_ok=True)

    import json

    status = {
        "pid": 12345,
        "event": "gagal",
        "stage": "worker.reconcile",
        "time": "2026-11-24T02:49:29.700820+00:00",
        "reason": "Auto rekonsiliasi gagal setelah 6 percobaan. Bot dihentikan; hasil transaksi terakhir masih belum pasti.",
        "category": "reconciliation_failed",
        "reconciliation_pending": 1,
    }
    (r_dir / "status.json").write_text(json.dumps(status))

    last_err = {
        "error_id": "OJL-DF67EFD4AB5D",
        "message": "Gagal memecahkan gambar cek: Glyph cek belum dikenali",
        "tindakan": "Review angka di menu Bank Angka",
    }
    (r_dir / "last-error.json").write_text(json.dumps(last_err))

    res = client.get(f"/api/dashboard?account={account['id']}")
    assert res.status_code == 200
    logs = res.json()["logs"]
    assert any("Worker GAGAL saat Rekonsiliasi Transaksi Game" in line for line in logs)
    assert any("Auto rekonsiliasi gagal setelah 6 percobaan" in line for line in logs)
    assert any("1 transaksi game belum terkonfirmasi" in line for line in logs)
    assert any("OJL-DF67EFD4AB5D" in line for line in logs)

    # Test skip endpoint
    skip_res = client.post("/api/control/skip")
    assert skip_res.status_code == 200
    assert skip_res.json()["success"] is True


def test_shared_bank_angka_and_crowdsourced_contribution(admin_web):
    client, manager = admin_web
    create_res = client.post("/api/accounts/create", json={"name": "Akun Eskobar"})
    account = create_res.json()["account"]
    scoped = manager.registry.scoped_settings(account)
    r_dir = scoped.runtime_dir
    r_dir.mkdir(parents=True, exist_ok=True)

    # 1. Simulate an unknown glyph error in Akun Eskobar
    err_dir = r_dir / "errors"
    err_dir.mkdir(parents=True, exist_ok=True)
    import json

    dummy_glyph = [[[0.86, 1.0], [0.86, 0.0], [0.0, 0.74]]]
    sample_error = {
        "error_id": "OJL-998877665544",
        "category": "SvgCaptchaSolverError",
        "message": f"Gagal memecahkan gambar cek: Glyph cek belum dikenali: {json.dumps(dummy_glyph)}",
        "time": "2026-11-24T10:00:00Z",
    }
    (err_dir / "OJL-998877665544.json").write_text(json.dumps(sample_error))

    # 2. Bank Angka API shows pending review with account_name 'Akun Eskobar'
    bank_res = client.get("/api/bank-angka")
    assert bank_res.status_code == 200
    bank_data = bank_res.json()
    assert any(p.get("error_id") == "OJL-998877665544" for p in bank_data["pending"])
    eskobar_pending = next(p for p in bank_data["pending"] if p.get("error_id") == "OJL-998877665544")
    assert eskobar_pending["account_name"] == "Akun Eskobar"

    # 3. User contributes / saves digit to Bank Angka
    save_res = client.post(
        "/api/bank-angka/save",
        json={"digit": "7", "glyph": dummy_glyph, "error_id": "OJL-998877665544"},
    )
    assert save_res.status_code == 200
    save_json = save_res.json()
    assert save_json["ok"] is True
    assert save_json["by"] is not None
    assert "Akun Eskobar" in save_json["retried_accounts"]
    # WAKE file created and Auto Ojol enabled
    from ojol.auto_settings import auto_flags
    assert auto_flags(r_dir)["ojol"] is True
    assert (r_dir / "WAKE").is_file()

    # 4. Bank Angka now has the new variant marked with contributor and pending is cleared
    bank_after = client.get("/api/bank-angka").json()
    assert any(p.get("error_id") == "OJL-998877665544" for p in bank_after["pending"]) is False
    variants_7 = bank_after["templates"]["7"]
    assert any(v.get("by") == save_res.json()["by"] for v in variants_7)
    assert bank_after["total_contributions"] >= 1


def test_dashboard_html_javascript_syntax_valid():
    import json
    import re
    import shutil
    import subprocess
    from ojol.web_ui import dashboard_html

    html = dashboard_html({"id": 1, "username": "admin", "is_admin": True, "name": "Admin"})
    scripts = re.findall(r"<script[\s\S]*?>([\s\S]*?)</script>", html, re.IGNORECASE)
    assert len(scripts) >= 1
    node_bin = shutil.which("node")
    if node_bin:
        for idx, s in enumerate(scripts):
            check_code = f"new Function({json.dumps(s)});"
            res = subprocess.run(
                [node_bin, "-e", check_code],
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"Script {idx} has JS syntax error: {res.stderr}"


def test_web_dashboard_finance_and_expense_history(admin_web):
    import sqlite3
    from datetime import UTC, datetime, timedelta
    from ojol.finance import WIB, report_date

    client, manager = admin_web
    create_res = client.post("/api/accounts/create", json={"name": "Akun Finansial"})
    assert create_res.status_code == 200
    account = create_res.json()["account"]

    r_dir = manager.registry.scoped_settings(account).runtime_dir
    r_dir.mkdir(parents=True, exist_ok=True)

    today = report_date()
    yesterday = today - timedelta(days=1)
    today_dt = datetime.combine(today, datetime.min.time(), WIB).astimezone(sqlite3.sqlite_version and UTC)
    yest_dt = datetime.combine(yesterday, datetime.min.time(), WIB).astimezone(UTC)

    # Inisialisasi history.sqlite3 via Journal
    from ojol.journal import Journal
    j = Journal(r_dir)
    with j.db:
        j.db.execute("INSERT INTO runs(id,started,outcome,settings) VALUES (1, ?, 'ok', '{}')", (yest_dt.isoformat(),))
        j.db.execute("INSERT INTO runs(id,started,outcome,settings) VALUES (2, ?, 'ok', '{}')", (today_dt.isoformat(),))
        # Kemarin: income 10000, expense 2000 (net 8000)
        j.db.execute(
            "INSERT INTO cashflows(run_id,source_key,created,kind,category,amount,detail) VALUES (?,?,?,?,?,?,?)",
            (1, "yest_inc", (yest_dt + timedelta(hours=2)).isoformat(), "income", "ojol", "10000", "{}"),
        )
        j.db.execute(
            "INSERT INTO cashflows(run_id,source_key,created,kind,category,amount,detail) VALUES (?,?,?,?,?,?,?)",
            (1, "yest_exp", (yest_dt + timedelta(hours=3)).isoformat(), "expense", "bensin", "2000", json.dumps({"product": "Pertalite", "shop": "SPBU"})),
        )
        # Hari ini: income 15000, expense 3000 (net 12000)
        j.db.execute(
            "INSERT INTO cashflows(run_id,source_key,created,kind,category,amount,detail) VALUES (?,?,?,?,?,?,?)",
            (2, "today_inc", (today_dt + timedelta(hours=2)).isoformat(), "income", "ojol", "15000", "{}"),
        )
        j.db.execute(
            "INSERT INTO cashflows(run_id,source_key,created,kind,category,amount,detail) VALUES (?,?,?,?,?,?,?)",
            (2, "today_exp", (today_dt + timedelta(hours=3)).isoformat(), "expense", "bensin", "3000", json.dumps({"product": "Pertamax 2 Liter", "shop": "SPBU Pertamina"})),
        )
    j.close()

    dash_res = client.get("/api/dashboard")
    assert dash_res.status_code == 200
    data = dash_res.json()

    # Periksa fleet totals
    totals = data["all_accounts_summary"]
    assert totals["total_income"] == "15.000"
    assert totals["total_expenses"] == "3.000"
    assert totals["total_net_profit"] == "12.000"
    assert totals["income_growth"]["percent"] == 50.0
    assert totals["income_growth"]["direction"] == "up"
    assert totals["income_growth"]["text"] == "+50.0%"
    assert totals["profit_growth"]["percent"] == 50.0
    assert totals["profit_growth"]["direction"] == "up"
    assert totals["profit_growth"]["text"] == "+50.0%"

    # Periksa selected account finance
    fin = data["finance"]
    assert fin["today_income"] == "15.000"
    assert fin["today_expenses"] == "3.000"
    assert fin["today_net_profit"] == "12.000"
    assert fin["profit_growth"]["direction"] == "up"
    assert len(fin["expense_history"]) == 2
    latest_exp = fin["expense_history"][0]
    assert latest_exp["category"] == "bensin"
    assert "Pertamax 2 Liter • SPBU Pertamina" in latest_exp["item_name"]
    assert latest_exp["amount"] == "3.000"

    # Periksa HTML root menyertakan elemen UI finansial
    html_res = client.get("/")
    assert html_res.status_code == 200
    assert "fleetTotalExpenses" in html_res.text
    assert "fleetTotalNetProfit" in html_res.text
    assert "fleetIncomeGrowth" in html_res.text
    assert "fleetNetGrowth" in html_res.text
    assert "accProfitVal" in html_res.text
    assert "accExpenseVal" in html_res.text
    assert "accNetProfitVal" in html_res.text
    assert "expenseList" in html_res.text
    assert "Riwayat Pengeluaran" in html_res.text


def test_web_dashboard_study_history(admin_web):
    import json
    from datetime import UTC, datetime, timedelta
    from ojol.journal import Journal
    from ojol.study import save_skills

    client, manager = admin_web
    create_res = client.post("/api/accounts/create", json={"name": "Akun Belajar"})
    assert create_res.status_code == 200
    account = create_res.json()["account"]

    r_dir = manager.registry.scoped_settings(account).runtime_dir
    r_dir.mkdir(parents=True, exist_ok=True)

    # Simpan skills akun
    skills = [
        {"id": "administrasi", "name": "Administrasi", "level": 3, "next": {"level": 4, "library": True}},
        {"id": "boga", "name": "Tata boga", "level": 2, "next": {"level": 3, "library": True}},
    ]
    save_skills(r_dir, skills)

    now_utc = datetime.now(UTC)

    # Inisialisasi history.sqlite3 via Journal
    j = Journal(r_dir)
    with j.db:
        j.db.execute("INSERT INTO runs(id,started,outcome,settings) VALUES (1, ?, 'ok', '{}')", (now_utc.isoformat(),))

        # 1. Sesi Perpustakaan: study + study_quiz
        visit_perpus = "visit-perpus-123"
        st_perpus_payload = {
            "mode": "perpus",
            "track": "administrasi",
            "facility_id": "fac-perpus",
            "shop": "Perpustakaan Desa T6",
            "product": {"name": "Belajar", "price": "0"},
            "receipt": {"id": visit_perpus},
        }
        j.db.execute(
            "INSERT INTO actions(id,run_id,created,kind,status,before_state,payload,after_state) VALUES (?,?,?,?,?,?,?,?)",
            (10, 1, (now_utc - timedelta(hours=2)).isoformat(), "study", "verified", "{}", json.dumps(st_perpus_payload), "{}"),
        )
        qz_perpus_payload = {
            "mode": "perpus",
            "track": "administrasi",
            "facility_id": "fac-perpus",
            "visit_id": visit_perpus,
            "receipt": {"benar": 3, "total": 3, "bonus": 1},
        }
        j.db.execute(
            "INSERT INTO actions(id,run_id,created,kind,status,before_state,payload,after_state) VALUES (?,?,?,?,?,?,?,?)",
            (11, 1, (now_utc - timedelta(hours=2, minutes=-5)).isoformat(), "study_quiz", "verified", "{}", json.dumps(qz_perpus_payload), "{}"),
        )

        # 2. Sesi Kuliah: study + study_quiz
        visit_kuliah = "visit-kuliah-456"
        st_kuliah_payload = {
            "mode": "kuliah",
            "track": "boga",
            "facility_id": "fac-kuliah",
            "shop": "Universitas Terbuka",
            "product": {"name": "Kuliah", "price": "4000"},
            "receipt": {"id": visit_kuliah},
        }
        j.db.execute(
            "INSERT INTO actions(id,run_id,created,kind,status,before_state,payload,after_state) VALUES (?,?,?,?,?,?,?,?)",
            (20, 1, (now_utc - timedelta(hours=1)).isoformat(), "study", "verified", "{}", json.dumps(st_kuliah_payload), "{}"),
        )
        qz_kuliah_payload = {
            "mode": "kuliah",
            "track": "boga",
            "facility_id": "fac-kuliah",
            "visit_id": visit_kuliah,
            "receipt": {"benar": 5, "total": 5, "bonus": 1},
        }
        j.db.execute(
            "INSERT INTO actions(id,run_id,created,kind,status,before_state,payload,after_state) VALUES (?,?,?,?,?,?,?,?)",
            (21, 1, (now_utc - timedelta(hours=1, minutes=-10)).isoformat(), "study_quiz", "verified", "{}", json.dumps(qz_kuliah_payload), "{}"),
        )
    j.close()

    dash_res = client.get("/api/dashboard")
    assert dash_res.status_code == 200
    data = dash_res.json()

    # Pastikan study_history dan skills ada di respons
    assert "study_history" in data
    assert "skills" in data
    history = data["study_history"]
    assert len(history) == 2

    # Sesi terbaru: Kuliah
    sesi_kuliah = history[0]
    assert sesi_kuliah["mode"] == "kuliah"
    assert sesi_kuliah["mode_label"] == "Universitas"
    assert sesi_kuliah["facility_name"] == "Universitas Terbuka"
    assert sesi_kuliah["track_name"] == "Tata boga"
    assert sesi_kuliah["cost"] == "-4.000 koin"
    assert "Kuis 5/5 Benar (+1 Keahlian)" in sesi_kuliah["skill_gain"]
    assert sesi_kuliah["skill_level"] == 2
    assert sesi_kuliah["level_display"] == "Lv. 2"
    assert sesi_kuliah["status"] == "Selesai"

    # Sesi pertama: Perpus
    sesi_perpus = history[1]
    assert sesi_perpus["mode"] == "perpus"
    assert sesi_perpus["mode_label"] == "Perpustakaan"
    assert sesi_perpus["facility_name"] == "Perpustakaan Desa T6"
    assert sesi_perpus["track_name"] == "Administrasi"
    assert sesi_perpus["cost"] == "Gratis (0 koin)"
    assert "Kuis 3/3 Benar (+1 Keahlian)" in sesi_perpus["skill_gain"]
    assert sesi_perpus["skill_level"] == 3
    assert sesi_perpus["level_display"] == "Lv. 3"
    assert sesi_perpus["status"] == "Selesai"

    # Periksa elemen DOM di HTML root
    html_res = client.get("/")
    assert html_res.status_code == 200
    assert "studyHistoryList" in html_res.text
    assert "studyHistoryBadge" in html_res.text
    assert "Riwayat Belajar Lengkap" in html_res.text




