"""Web API endpoints for dashboard, account management, control, and auth."""

import json
from urllib.parse import quote_plus, urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .auto_settings import auto_flags, set_auto_flag
from .control import status_record
from .study import set_subject, subjects
from .web_ui import dashboard_html, login_html, register_html, setup_password_html


def register_web_routes(app, settings, manager=None, service=None):
    registry = (
        manager.registry
        if manager
        else (service.registry if hasattr(service, "registry") else None)
    )

    async def get_bot_username() -> str:
        raw = settings.telegram_bot_token
        token = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw or "")
        if not token:
            return ""
        if manager and getattr(manager, "bot_username", None):
            return manager.bot_username
        from .telegram import TelegramClient

        try:
            async with TelegramClient(settings) as client:
                res = await client.call("getMe")
                uname = res.get("username") or (res.get("result") or {}).get("username", "")
                if manager:
                    manager.bot_username = uname
                return uname
        except Exception:
            return ""

    def get_current_user(request: Request) -> dict | None:
        if not registry:
            return None
        session_token = request.cookies.get("ojol_web_session")
        if not session_token:
            return None
        return registry.web.get_user_by_session(session_token)

    def require_user(request: Request) -> dict:
        user = get_current_user(request)
        if not user:
            raise HTTPException(401, "Sesi kedaluwarsa atau belum login")
        if user.get("status") != "approved":
            raise HTTPException(403, "Akun belum disetujui admin")
        return user

    def require_admin(request: Request) -> dict:
        user = require_user(request)
        if user.get("role") != "admin":
            raise HTTPException(403, "Akses ditolak: Hanya admin yang diizinkan")
        return user

    def resolve_account_service(request: Request, account_id: str | None = None):
        if manager is None:
            return service
        if account_id:
            return manager.service(account_id)
        # Fallback to selected account for current user
        user = require_user(request)
        owner = registry.owner_for_user(user)
        selected = registry.selected(owner)
        if not selected:
            active = registry.list(owner)
            if active:
                registry.select(owner, active[0]["id"])
                selected = active[0]
        if selected:
            return manager.service(selected["id"])
        return None

    async def parse_body(request: Request) -> tuple[dict, bool]:
        is_json = request.headers.get("content-type", "").startswith("application/json")
        if is_json:
            try:
                return await request.json(), True
            except Exception:
                return {}, True
        from urllib.parse import parse_qs

        body_bytes = await request.body()
        parsed = parse_qs(body_bytes.decode("utf-8", errors="replace"))
        return {k: v[0] for k, v in parsed.items()}, False

    # ==================== HTML PAGES ====================

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        if user.get("status") != "approved":
            return RedirectResponse(
                "/login?error=" + quote_plus("Akun Anda sedang menunggu persetujuan admin."),
                status_code=303,
            )
        if not user.get("has_password", 1):
            return RedirectResponse("/setup-password", status_code=303)
        bot_uname = await get_bot_username()
        return dashboard_html(user, bot_username=bot_uname)

    @app.get("/setup-password", response_class=HTMLResponse)
    async def setup_password_page(request: Request, error: str = ""):
        user = get_current_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        if user.get("has_password", 1):
            return RedirectResponse("/", status_code=303)
        return setup_password_html(user, error=error)

    @app.post("/api/auth/setup-password")
    async def setup_password_api(request: Request):
        if not registry:
            raise HTTPException(500, "Registry belum siap")
        user = get_current_user(request)
        if not user:
            raise HTTPException(401, "Sesi belum aktif")
        body, is_json = await parse_body(request)
        username = body.get("username", "")
        password = body.get("password", "")
        confirm = body.get("confirm_password", "")

        if password != confirm:
            err = "Konfirmasi password tidak cocok."
            if is_json:
                raise HTTPException(400, err)
            return RedirectResponse("/setup-password?error=" + quote_plus(err), status_code=303)

        try:
            updated = registry.web.setup_password(user["id"], username, password)
            if is_json:
                return {"success": True, "user": updated, "redirect": "/"}
            return RedirectResponse("/", status_code=303)
        except ValueError as exc:
            if is_json:
                raise HTTPException(400, str(exc))
            return RedirectResponse(
                "/setup-password?error=" + quote_plus(str(exc)), status_code=303
            )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, error: str = "", success: str = "", code: str = ""):
        user = get_current_user(request)
        if user and user.get("status") == "approved":
            return RedirectResponse("/", status_code=303)
        bot_uname = await get_bot_username()
        return login_html(bot_username=bot_uname, error=error, success=success, default_code=code)

    @app.get("/register", response_class=HTMLResponse)
    async def register_page(request: Request, error: str = "", success: str = ""):
        user = get_current_user(request)
        if user and user.get("status") == "approved":
            return RedirectResponse("/", status_code=303)
        return register_html(error=error, success=success)

    @app.get("/logout")
    async def logout_get(request: Request):
        token = request.cookies.get("ojol_web_session")
        if token and registry:
            registry.web.revoke_session(token)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("ojol_web_session", path="/")
        return response

    # ==================== AUTH APIS ====================

    @app.post("/api/auth/register")
    async def register_api(request: Request):
        if not registry:
            raise HTTPException(500, "Registry belum siap")
        body, is_json = await parse_body(request)

        username = body.get("username", "")
        password = body.get("password", "")
        confirm = body.get("confirm_password", "")
        name = body.get("name", "")

        if not is_json and confirm and password != confirm:
            return RedirectResponse(
                "/register?error=" + quote_plus("Konfirmasi password tidak cocok."), status_code=303
            )

        try:
            user = registry.web.register(username, password, name)
            # Notify Telegram admin if configured
            if manager and registry.admin:
                try:
                    await manager.reply(
                        registry.admin,
                        f"🔔 Pendaftaran akun web baru:\n"
                        f"Username: `{user['username']}`\n"
                        f"Nama: {user.get('name')}\n"
                        f"Status: Menunggu Persetujuan\n\n"
                        f"Kirim perintah `/web` atau tinjau di panel admin web.",
                    )
                except Exception:
                    pass

            if user.get("status") == "approved":
                msg = "Pendaftaran berhasil! Akun Anda aktif sebagai admin. Silakan masuk."
            else:
                msg = "Pendaftaran berhasil! Akun Anda sedang menunggu persetujuan admin."
            if is_json:
                return {"success": True, "message": msg, "user": user}
            return RedirectResponse("/login?success=" + quote_plus(msg), status_code=303)
        except ValueError as exc:
            if is_json:
                raise HTTPException(400, str(exc))
            return RedirectResponse("/register?error=" + quote_plus(str(exc)), status_code=303)

    @app.post("/api/auth/login")
    async def login_api(request: Request):
        if not registry:
            raise HTTPException(500, "Registry belum siap")
        body, is_json = await parse_body(request)

        username = body.get("username", "")
        password = body.get("password", "")

        try:
            user = registry.web.authenticate_password(username, password)
            token = registry.web.issue_session(user["id"])
            is_secure = urlsplit(request.base_url._url).scheme == "https"
            if is_json:
                res = JSONResponse({"success": True, "user": user})
            else:
                res = RedirectResponse("/", status_code=303)
            res.set_cookie(
                "ojol_web_session",
                token,
                max_age=604800,
                httponly=True,
                secure=is_secure,
                samesite="lax",
                path="/",
            )
            return res
        except ValueError as exc:
            if is_json:
                raise HTTPException(400, str(exc))
            return RedirectResponse("/login?error=" + quote_plus(str(exc)), status_code=303)

    @app.get("/api/auth/telegram/callback")
    async def telegram_callback(request: Request):
        if not registry:
            raise HTTPException(500, "Registry belum siap")
        params = dict(request.query_params)
        try:
            user = registry.web.authenticate_telegram_widget(params)
            token = registry.web.issue_session(user["id"])
            is_secure = urlsplit(request.base_url._url).scheme == "https"
            dest = "/setup-password" if not user.get("has_password", 1) else "/"
            res = RedirectResponse(dest, status_code=303)
            res.set_cookie(
                "ojol_web_session",
                token,
                max_age=604800,
                httponly=True,
                secure=is_secure,
                samesite="lax",
                path="/",
            )
            return res
        except ValueError as exc:
            return RedirectResponse("/login?error=" + quote_plus(str(exc)), status_code=303)

    @app.post("/api/auth/telegram-code")
    async def telegram_code_login(request: Request):
        if not registry:
            raise HTTPException(500, "Registry belum siap")
        body, is_json = await parse_body(request)

        code = body.get("code", "")
        try:
            user = registry.web.authenticate_telegram_code(code)
            token = registry.web.issue_session(user["id"])
            is_secure = urlsplit(request.base_url._url).scheme == "https"
            dest = "/setup-password" if not user.get("has_password", 1) else "/"
            if is_json:
                res = JSONResponse(
                    {
                        "success": True,
                        "user": user,
                        "setup_required": not user.get("has_password", 1),
                        "redirect": dest,
                    }
                )
            else:
                res = RedirectResponse(dest, status_code=303)
            res.set_cookie(
                "ojol_web_session",
                token,
                max_age=604800,
                httponly=True,
                secure=is_secure,
                samesite="lax",
                path="/",
            )
            return res
        except ValueError as exc:
            if is_json:
                raise HTTPException(400, str(exc))
            return RedirectResponse("/login?error=" + quote_plus(str(exc)), status_code=303)

    @app.post("/api/auth/logout")
    async def logout_post(request: Request):
        token = request.cookies.get("ojol_web_session")
        if token and registry:
            registry.web.revoke_session(token)
        res = JSONResponse({"success": True})
        res.delete_cookie("ojol_web_session", path="/")
        return res

    @app.get("/api/auth/me")
    async def get_me(user: dict = Depends(require_user)):
        return {"logged_in": True, "user": user}

    @app.post("/api/auth/connect-telegram/issue-code")
    async def issue_connect_code(user: dict = Depends(require_user)):
        code = registry.web.issue_telegram_link_code(user["id"])
        bot_uname = await get_bot_username()
        return {"code": code, "bot_username": bot_uname}

    @app.post("/api/auth/disconnect-telegram")
    async def disconnect_telegram_api(user: dict = Depends(require_user)):
        try:
            updated = registry.web.disconnect_telegram(user["id"])
            return {"success": True, "user": updated}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    # ==================== DASHBOARD & ACCOUNTS ====================

    async def build_dashboard_payload(request: Request, user: dict) -> dict:
        owner = registry.owner_for_user(user)
        accounts_list = registry.list(owner) + registry.list(owner, archived=True)
        selected = registry.selected(owner)
        if not selected and accounts_list:
            active_only = [a for a in accounts_list if not a["archived"]]
            if active_only:
                registry.select(owner, active_only[0]["id"])
                selected = active_only[0]

        accounts_payload = []
        for acc in accounts_list:
            acc_service = resolve_account_service(request, acc["id"]) if manager else service
            sum_info = acc_service.summary() if acc_service else {}
            accounts_payload.append(
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "archived": bool(acc["archived"]),
                    "legacy": bool(acc["legacy"]),
                    "is_selected": bool(selected and acc["id"] == selected["id"]),
                    "has_cookie": sum_info.get("has_cookie", False),
                    "is_running": sum_info.get("active", False),
                    "icon": sum_info.get("icon", "⚪"),
                }
            )

        if not selected:
            return {
                "account": None,
                "accounts": accounts_payload,
                "summary": {},
                "snapshot": {},
                "auto_flags": {},
                "study_subject": "dagang",
                "ojol_mode": "otomatis",
                "limit_reached": False,
                "hours_left": None,
                "logs": [],
                "notifications": [],
            }

        cur_service = resolve_account_service(request, selected["id"])
        summary = cur_service.summary() if cur_service else {}
        directory = cur_service.settings.runtime_dir

        # Read state & sync
        data, _ = status_record(directory / "status.json")
        state = data.get("snapshot") or {}
        sync, _ = status_record(directory / "game-sync.json")
        if isinstance(sync.get("snapshot"), dict):
            state = {**state, **sync["snapshot"]}

        flags = auto_flags(directory)
        subj_dict = subjects(directory)
        cur_subj = subj_dict.get("perpus") or subj_dict.get("kuliah") or "dagang"

        flags_payload = dict(flags)
        flags_payload["study"] = bool(flags.get("perpus") or flags.get("kuliah"))
        flags_payload["garden"] = bool(flags.get("kebun"))
        flags_payload["auto_subject"] = (cur_subj == "auto")

        # Read last logs from history or journal or status
        logs = []
        if data.get("event"):
            logs.append(
                f"[{data.get('time', '')}] Status: {data.get('event')} ({data.get('stage', '')})"
            )
        hist_file = directory / "history.jsonl"
        if hist_file.is_file():
            try:
                lines = hist_file.read_text().strip().splitlines()[-15:]
                logs.extend(lines)
            except Exception:
                pass
        if not logs and summary.get("status_text"):
            logs.append(f"Status saat ini: {summary.get('status_text')}")

        from .notifications import list_notifications

        notices = list_notifications(cur_service.settings, limit=10)

        limit_reached = bool(
            summary.get("shift_done")
            or state.get("ojol_shift_done")
            or (state.get("ojol_hours_left") is not None and state.get("ojol_hours_left") <= 0)
            or "Batas narik" in str(summary.get("status_text") or "")
        )

        return {
            "account": selected,
            "accounts": accounts_payload,
            "summary": summary,
            "snapshot": state,
            "auto_flags": flags_payload,
            "study_subject": cur_subj,
            "ojol_mode": getattr(cur_service.settings, "ojol_mode", "otomatis"),
            "limit_reached": limit_reached,
            "hours_left": summary.get("hours_left") or state.get("ojol_hours_left"),
            "logs": logs,
            "notifications": notices,
        }

    @app.get("/api/extension/download")
    @app.get("/download/extension.zip")
    async def download_extension_zip():
        import io
        import zipfile
        from pathlib import Path
        from fastapi.responses import Response

        extension_dir = Path(__file__).resolve().parent.parent / "tools" / "chrome-diving-radar"
        if not extension_dir.is_dir():
            raise HTTPException(404, "Direktori ekstensi tidak ditemukan")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            allowed_files = [
                "manifest.json",
                "content.js",
                "ojol.js",
                "mancing.js",
                "tpu.js",
                "inject.js",
                "popup.html",
                "popup.js",
                "README.md",
                "package.json",
            ]
            for fname in allowed_files:
                fpath = extension_dir / fname
                if fpath.is_file():
                    zf.writestr(f"kampungsebelah-extension/{fname}", fpath.read_bytes())

        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="kampungsebelah-extension.zip"',
                "Cache-Control": "no-cache",
            },
        )

    @app.get("/api/dashboard")
    async def get_dashboard(request: Request, user: dict = Depends(require_user)):
        return await build_dashboard_payload(request, user)

    @app.get("/api/dashboard/stream")
    async def get_dashboard_stream(request: Request, user: dict = Depends(require_user)):
        import asyncio

        from fastapi.responses import StreamingResponse

        async def event_generator():
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await build_dashboard_payload(request, user)
                    yield f"data: {json.dumps(payload, default=str)}\n\n"
                except Exception:
                    break
                await asyncio.sleep(2)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/accounts")
    async def list_accounts(request: Request, user: dict = Depends(require_user)):
        owner = registry.owner_for_user(user)
        accounts_list = registry.list(owner) + registry.list(owner, archived=True)
        selected = registry.selected(owner)
        payload = []
        for acc in accounts_list:
            acc_service = resolve_account_service(request, acc["id"]) if manager else service
            sum_info = acc_service.summary() if acc_service else {}
            payload.append(
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "archived": bool(acc["archived"]),
                    "legacy": bool(acc["legacy"]),
                    "is_selected": bool(selected and acc["id"] == selected["id"]),
                    "has_cookie": sum_info.get("has_cookie", False),
                    "is_running": sum_info.get("active", False),
                }
            )
        return {"accounts": payload, "quota": registry.quota(owner)}

    @app.post("/api/accounts/select")
    async def select_account_api(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        account_id = body.get("account_id")
        if not account_id:
            raise HTTPException(400, "ID akun diperlukan")
        owner = registry.owner_for_user(user)
        try:
            registry.select(owner, account_id)
            return {"success": True}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/accounts/create")
    async def create_account_api(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        name = body.get("name")
        owner = registry.owner_for_user(user)
        try:
            acc = registry.create(owner, name) if name else registry.create(owner)
            return {"success": True, "account": acc}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/accounts/rename")
    async def rename_account_api(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        account_id = body.get("account_id")
        name = body.get("name")
        if not account_id or not name:
            raise HTTPException(400, "ID akun dan nama baru diperlukan")
        owner = registry.owner_for_user(user)
        try:
            registry.rename(owner, account_id, name)
            return {"success": True}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/accounts/archive")
    async def archive_account_api(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        account_id = body.get("account_id")
        archived = bool(body.get("archived", True))
        if not account_id:
            raise HTTPException(400, "ID akun diperlukan")
        owner = registry.owner_for_user(user)
        try:
            registry.archive(owner, account_id, archived=archived)
            return {"success": True}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    # ==================== WORKER & GAMEPLAY CONTROL ====================

    @app.post("/api/control/run")
    async def run_ojol(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        mode = getattr(cur_service.settings, "ojol_mode", "otomatis")
        res = await cur_service.command("run", mode=mode)
        return {"success": True, "message": res}

    @app.post("/api/control/stop")
    async def stop_ojol(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        res = await cur_service.command("stop")
        return {"success": True, "message": res}

    @app.post("/api/control/run-needs")
    async def run_needs(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        res = await cur_service.command("run_kebutuhan")
        return {"success": True, "message": res}

    @app.post("/api/control/stop-needs")
    async def stop_needs(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        res = await cur_service.command("stop_kebutuhan")
        return {"success": True, "message": res}

    @app.post("/api/control/toggle-auto")
    async def toggle_auto_api(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        flag = body.get("flag")
        enabled = bool(body.get("enabled", False))
        if not flag:
            raise HTTPException(400, "Nama flag diperlukan")
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        try:
            if flag == "study":
                set_auto_flag(cur_service.settings.runtime_dir, "perpus", enabled)
                set_auto_flag(cur_service.settings.runtime_dir, "kuliah", enabled)
            elif flag == "garden":
                set_auto_flag(cur_service.settings.runtime_dir, "kebun", enabled)
            elif flag == "auto_subject":
                from .study import STUDY_LABELS, set_subject
                for m in STUDY_LABELS:
                    try:
                        set_subject(cur_service.settings.runtime_dir, m, "auto" if enabled else "dagang")
                    except Exception:
                        pass
            else:
                set_auto_flag(cur_service.settings.runtime_dir, flag, enabled)
            return {"success": True, "flag": flag, "enabled": enabled}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/control/mode-ojol")
    async def set_mode_ojol(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        mode = body.get("mode")
        if mode not in {"kendara", "otomatis"}:
            raise HTTPException(400, "Mode harus 'kendara' atau 'otomatis'")
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        cur_service.settings.ojol_mode = mode
        return {"success": True, "mode": mode}

    @app.post("/api/control/study-subject")
    async def set_study_subject_api(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        subject = body.get("subject")
        mode = body.get("mode")
        if not subject:
            raise HTTPException(400, "Bidang belajar diperlukan")
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        from .study import STUDY_LABELS, set_subject

        try:
            if mode and mode in STUDY_LABELS:
                set_subject(cur_service.settings.runtime_dir, mode, subject)
            else:
                errors = []
                for m in STUDY_LABELS:
                    try:
                        set_subject(cur_service.settings.runtime_dir, m, subject)
                    except ValueError as ve:
                        errors.append(f"{m}: {ve}")
                if len(errors) == len(STUDY_LABELS):
                    raise ValueError(errors[0])
            return {"success": True, "subject": subject}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/control/import-cookie")
    async def import_cookie_direct(request: Request, user: dict = Depends(require_user)):
        body = await request.json()
        cookie_raw = body.get("cookie", "")
        if not cookie_raw.strip():
            raise HTTPException(400, "Cookie tidak boleh kosong")

        from .session_transfer import import_session, parse_cookie_input

        try:
            payload = parse_cookie_input(cookie_raw)
        except Exception as exc:
            raise HTTPException(400, f"Format cookie tidak valid: {exc}")

        owner = registry.owner_for_user(user) if registry else 0
        custom_name = (body.get("name") or "").strip()
        account_name = custom_name or "Akun Utama"

        # Check if an account was explicitly targeted or already exists for this owner
        account_id = (body.get("account_id") or "").strip()
        if account_id and registry:
            try:
                registry.get(account_id, owner=owner)
            except ValueError:
                account_id = None

        if not account_id and registry:
            selected = registry.selected(owner)
            if selected:
                account_id = selected["id"]
            else:
                active_list = registry.list(owner)
                if active_list:
                    account_id = active_list[0]["id"]
                    registry.select(owner, account_id)

        # If user has no account yet, create a new one specifically for this owner
        if not account_id and registry:
            account_id = registry.create(owner, account_name)
            registry.select(owner, account_id)

        cur_service = manager.service(account_id) if (manager and account_id) else service
        if not cur_service:
            raise HTTPException(500, "Layanan akun tidak dapat diinisialisasi")

        digest = None
        if registry and account_id:
            try:
                digest = registry.check_cookie(account_id, payload)
            except ValueError as exc:
                raise HTTPException(409, str(exc))

        if cur_service and hasattr(cur_service, "stop_worker"):
            await cur_service.stop_worker()
        try:
            profile = await import_session(cur_service.settings, json.dumps(payload))
            nickname = (profile or {}).get("nickname")
            if registry and account_id and nickname:
                if not custom_name or custom_name in {"Akun Utama", "Draft"}:
                    try:
                        registry.rename(owner, account_id, nickname)
                    except Exception:
                        pass
            if registry and account_id and digest:
                registry.bind_cookie(account_id, digest)
            display_name = nickname if (nickname and not custom_name) else account_name
            return {
                "success": True,
                "message": f"Cookie berhasil diimpor! Akun terhubung sebagai '{display_name}'.",
                "nickname": nickname,
            }
        except Exception as exc:
            raise HTTPException(400, f"Verifikasi sesi gagal: {exc}")

    # ==================== NOTIFICATIONS ====================

    @app.get("/api/notifications")
    async def get_notifications(request: Request, user: dict = Depends(require_user)):
        from .notifications import list_notifications

        cur_service = resolve_account_service(request)
        target_settings = cur_service.settings if cur_service else settings
        notices = list_notifications(target_settings)
        return {"notifications": notices}

    @app.post("/api/notifications/read")
    async def mark_read(request: Request, user: dict = Depends(require_user)):
        from .notifications import mark_notifications_read

        body = (
            await request.json()
            if request.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        notice_ids = body.get("ids")
        cur_service = resolve_account_service(request)
        target_settings = cur_service.settings if cur_service else settings
        count = mark_notifications_read(target_settings, notice_ids)
        return {"success": True, "marked_count": count}

    # ==================== ADMIN APIS ====================

    @app.get("/api/admin/pending")
    async def admin_pending(user: dict = Depends(require_admin)):
        return registry.web.list_pending()

    @app.get("/api/admin/users")
    async def admin_users(user: dict = Depends(require_admin)):
        return registry.web.list_users()

    @app.post("/api/admin/review")
    async def admin_review(request: Request, user: dict = Depends(require_admin)):
        body = await request.json()
        target_user_id = int(body.get("user_id", 0))
        approve = bool(body.get("approve", False))
        if not target_user_id:
            raise HTTPException(400, "user_id diperlukan")
        try:
            updated = registry.web.review_user(target_user_id, user["id"], approve)
            return {"success": True, "user": updated}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/admin/set-limit")
    async def admin_set_limit(request: Request, user: dict = Depends(require_admin)):
        body = await request.json()
        name = body.get("name")
        value = body.get("value")
        try:
            registry.set_limit(name, value)
            return {"success": True}
        except ValueError as exc:
            raise HTTPException(400, str(exc))
