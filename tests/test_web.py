import hashlib
import hmac
import time
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from ojol.accounts import Accounts
from ojol.control import create_app
from ojol.management import MultiAccountService
from ojol.web_auth import hash_password, verify_password, verify_telegram_widget


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
        update={"telegram_chat_id": 111, "telegram_bot_token": "mock-token", "telegram_enabled": True}
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
        assert "ojol_web_session" in client.cookies

        # 8. Now root page returns 200 dashboard HTML
        dash_page = client.get("/")
        assert dash_page.status_code == 200
        assert "Dashboard" in dash_page.text
        assert "limitNoticeCard" in dash_page.text
        assert "extensionModal" in dash_page.text

        # 9. GET /api/dashboard
        dash_api = client.get("/api/dashboard")
        assert dash_api.status_code == 200
        dash_json = dash_api.json()
        assert "accounts" in dash_json
        assert "summary" in dash_json
        assert "limit_reached" in dash_json

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

        # 11. Rename account
        acc_id = create_acc.json()["account"]["id"]
        rename_res = client.post(
            "/api/accounts/rename", json={"account_id": acc_id, "name": "Akun Agus Utama"}
        )
        assert rename_res.status_code == 200

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
