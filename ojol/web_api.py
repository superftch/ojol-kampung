"""Web API endpoints for dashboard, account management, control, and auth."""

import json
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus, urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError

from .auto_settings import auto_flags, set_auto_flag
from .control import status_record, status_timestamp
from .maintenance import held_window
from .models import Settings
from .study import set_subject, subjects
from .web_ui import dashboard_html, login_html, register_html, setup_password_html


def public_user(user):
    return {key: value for key, value in user.items() if key not in {"password_hash", "salt"}}


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

    def get_all_fleet_directories():
        dirs = [settings.runtime_dir]
        acc_names = {}
        if registry:
            for acc in registry.list() + registry.list(archived=True):
                sc = registry.scoped_settings(acc)
                dirs.append(sc.runtime_dir)
                acc_names[str(sc.runtime_dir)] = acc.get("name", "Akun")
                acc_names[acc["id"]] = acc.get("name", "Akun")
        return dirs, acc_names

    def resolve_account_service(request: Request, account_id: str | None = None):
        if manager is None:
            return service
        if account_id:
            return manager.service(account_id)
        # Fallback to selected account for current user
        user = require_user(request)
        owner = registry.owner_for_user(user)
        explicit_id = request.query_params.get("account_id")
        if explicit_id:
            try:
                registry.get(explicit_id, owner=owner)
                return manager.service(explicit_id)
            except ValueError as exc:
                raise HTTPException(400, str(exc))
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
                return {"success": True, "message": msg, "user": public_user(user)}
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
                res = JSONResponse({"success": True, "user": public_user(user)})
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
                        "user": public_user(user),
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

    def parse_coins(val) -> Decimal:
        try:
            amount = Decimal(str(val))
            return amount if amount.is_finite() else Decimal(0)
        except InvalidOperation:
            return Decimal(0)

    def format_coins(num: Decimal) -> str:
        whole, _, fraction = f"{num:,f}".partition(".")
        fraction = fraction.rstrip("0")
        return whole.replace(",", ".") + ("," + fraction if fraction else "")

    def dashboard_snapshot(directory, data):
        snapshot = data.get("snapshot") or {}
        sync, _ = status_record(directory / "game-sync.json")
        checked = status_timestamp(sync.get("checked_at"))
        observed = status_timestamp(data.get("snapshot_received_at") or snapshot.get("observed_at"))
        if (
            checked
            and (observed is None or checked > observed)
            and isinstance(sync.get("snapshot"), dict)
        ):
            return sync["snapshot"]
        return snapshot

    async def build_dashboard_payload(request: Request, user: dict) -> dict:
        owner = registry.owner_for_user(user)
        accounts_list = registry.list(owner)
        selected = registry.selected(owner)
        if not selected and accounts_list:
            selected = accounts_list[0]
            registry.select(owner, selected["id"])

        accounts_payload = []
        total_wallet = Decimal(0)
        total_income = Decimal(0)
        total_trips = 0
        active_workers = 0
        online_accounts = 0

        for acc in accounts_list:
            acc_service = resolve_account_service(request, acc["id"]) if manager else service
            sum_info = acc_service.summary() if acc_service else {}

            r_dir = acc_service.settings.runtime_dir if acc_service else None
            acc_snap = {}
            if r_dir:
                st_data, _ = status_record(r_dir / "status.json")
                acc_snap = dashboard_snapshot(r_dir, st_data)

            wallet = acc_snap.get("wallet", sum_info.get("wallet"))
            acc_wallet_num = parse_coins(wallet)
            acc_income_num = parse_coins(acc_snap.get("today_income"))
            acc_trips = acc_snap.get("today_count", sum_info.get("trips", 0))
            try:
                acc_trips = int(acc_trips)
            except (ValueError, TypeError):
                acc_trips = 0

            is_active = bool(sum_info.get("active", False))
            is_online = bool(sum_info.get("online", False))
            total_wallet += acc_wallet_num
            total_income += acc_income_num
            total_trips += acc_trips
            active_workers += int(is_active)
            online_accounts += int(is_online or is_active)

            accounts_payload.append(
                {
                    "id": acc["id"],
                    "name": acc["name"],
                    "archived": bool(acc["archived"]),
                    "legacy": bool(acc["legacy"]),
                    "is_selected": bool(selected and acc["id"] == selected["id"]),
                    "has_cookie": sum_info.get("has_cookie", False),
                    "is_running": is_active,
                    "is_online": is_online,
                    "icon": sum_info.get("icon", "⚪"),
                    "phase": sum_info.get("phase", "idle"),
                    "status_text": sum_info.get("status_text", "Standby"),
                    "wallet": format_coins(acc_wallet_num) if wallet is not None else None,
                    "wallet_num": float(acc_wallet_num),
                    "today_income": format_coins(acc_income_num),
                    "today_income_num": float(acc_income_num),
                    "trips": acc_trips,
                    "fuel": acc_snap.get("fuel", sum_info.get("fuel")),
                    "condition": acc_snap.get("condition", sum_info.get("condition")),
                    "data": acc_snap.get("data", sum_info.get("data")),
                }
            )

        all_accounts_summary = {
            "total_accounts": len(accounts_payload),
            "active_workers": active_workers,
            "online_accounts": online_accounts,
            "total_wallet": format_coins(total_wallet),
            "total_wallet_num": float(total_wallet),
            "total_income": format_coins(total_income),
            "total_income_num": float(total_income),
            "total_trips": total_trips,
        }

        fleet_dirs, _ = get_all_fleet_directories()
        from .svg_captcha_solver import get_all_pending_reviews

        if not selected:
            return {
                "account": None,
                "accounts": accounts_payload,
                "all_accounts_summary": all_accounts_summary,
                "summary": {},
                "snapshot": {},
                "auto_flags": {},
                "study_subject": "dagang",
                "ojol_mode": "otomatis",
                "limit_reached": False,
                "hours_left": None,
                "logs": [],
                "notifications": [],
                "pending_bank_reviews_count": len(get_all_pending_reviews(fleet_dirs)),
            }

        cur_service = resolve_account_service(request, selected["id"])
        summary = cur_service.summary() if cur_service else {}
        directory = cur_service.settings.runtime_dir

        # Read state & sync
        data, _ = status_record(directory / "status.json")
        state = dashboard_snapshot(directory, data)

        flags = auto_flags(directory)
        subj_dict = subjects(directory)
        cur_subj = subj_dict.get("perpus") or subj_dict.get("kuliah") or "dagang"

        from .control import NEEDS

        enabled_needs_count = sum(1 for k in NEEDS if flags.get(k))

        flags_payload = dict(flags)
        flags_payload["study"] = bool(flags.get("perpus") or flags.get("kuliah"))
        flags_payload["garden"] = bool(flags.get("kebun"))
        flags_payload["auto_subject"] = cur_subj == "auto"
        flags_payload["needs_active"] = enabled_needs_count > 0
        flags_payload["needs_count"] = enabled_needs_count
        flags_payload["total_needs"] = len(NEEDS)

        # Read last logs from history or journal or status
        logs = []
        from datetime import datetime
        from .finance import WIB

        def format_log_time(t_raw):
            if not t_raw:
                return "Terkini"
            try:
                dt = datetime.fromisoformat(str(t_raw).replace("Z", "+00:00")).astimezone(WIB)
                return dt.strftime("%H:%M:%S WIB")
            except Exception:
                return str(t_raw)

        if data.get("event"):
            ev = data.get("event")
            raw_stage = data.get("stage") or ""
            stage_desc = {
                "worker.reconcile": "Rekonsiliasi Transaksi Game",
                "order.search": "Mencari Order",
                "order.take": "Menerima Order",
                "order.complete": "Menyelesaikan Order",
                "purchase.fuel": "Isi Bensin (SPBU)",
                "sleeping": "Istirahat / Tidur di game",
                "wait.countdown": "Menunggu Countdown Antar Order",
            }.get(raw_stage, raw_stage)

            time_str = format_log_time(data.get("time"))

            if ev == "gagal":
                reason = data.get("reason") or "Bot menemui kendala pada aksi."
                logs.append(f"[{time_str}] ❌ Worker GAGAL saat {stage_desc}")
                logs.append(f"   Alasan: {reason}")
                if data.get("category"):
                    logs.append(f"   Kategori: {data.get('category')}")
                if data.get("reconciliation_pending"):
                    logs.append(f"   Aksi tertahan: {data.get('reconciliation_pending')} transaksi game belum terkonfirmasi")
                if data.get("last_action"):
                    la = data["last_action"]
                    logs.append(f"   Aksi terakhir: #{la.get('action_id', '?')} {la.get('kind', '?')}")
            elif ev in {"rekonsiliasi", "rekonsiliasi_otomatis"}:
                attempt = data.get("reconciliation_attempt", 1)
                limit = data.get("reconciliation_limit", 6)
                pending_cnt = data.get("reconciliation_pending", "?")
                logs.append(f"[{time_str}] 🔄 Rekonsiliasi Otomatis ({attempt}/{limit})")
                logs.append(f"   Sedang mencocokkan {pending_cnt} aksi transaksi tertahan dengan game...")
            elif ev == "mulai":
                logs.append(f"[{time_str}] ▶️ Worker Mulai ({stage_desc})")
            elif ev == "berhenti":
                reason = data.get("reason") or "Dihentikan oleh pengguna."
                logs.append(f"[{time_str}] ⏹️ Worker Berhenti: {reason}")
            elif ev == "tidur":
                logs.append(f"[{time_str}] 💤 Istirahat / Tidur di game")
            else:
                logs.append(f"[{time_str}] Status: {ev} ({stage_desc})")

        # Muat detail aksi tertahan dari game-sync.json jika ada
        sync_file = directory / "game-sync.json"
        if sync_file.is_file():
            try:
                sync_data = json.loads(sync_file.read_text())
                for action in sync_data.get("reconciliation", []):
                    if action.get("status_after") in {"pending", "uncertain"}:
                        desc = action.get("description") or action.get("kind", "Aksi")
                        reason = action.get("reason", "")
                        logs.append(f"⏳ Aksi tertahan: #{action.get('action_id')} {desc} ({reason})")
            except Exception:
                pass

        # Muat error terakhir dari last-error.json jika ada
        last_err_file = directory / "last-error.json"
        if last_err_file.is_file():
            try:
                err_data = json.loads(last_err_file.read_text())
                err_ctx = err_data.get("context", err_data)
                err_id = err_ctx.get("error_id")
                err_msg = err_ctx.get("message") or err_data.get("message")
                err_tindakan = err_ctx.get("tindakan") or err_data.get("tindakan")
                if err_id and err_msg:
                    logs.append(f"🚨 Error Terakhir [{err_id}]: {err_msg[:120]}")
                    if err_tindakan:
                        logs.append(f"   💡 Solusi: {err_tindakan}")
            except Exception:
                pass

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
        from .svg_captcha_solver import get_all_pending_reviews

        notices = list_notifications(cur_service.settings, limit=10)
        fleet_dirs, _ = get_all_fleet_directories()
        pending_bank_count = len(get_all_pending_reviews(fleet_dirs))

        limit_reached = bool(
            summary.get("shift_done")
            or state.get("ojol_shift_done")
            or (state.get("ojol_hours_left") is not None and state.get("ojol_hours_left") <= 0)
            or "Batas narik" in str(summary.get("status_text") or "")
        )

        return {
            "account": {
                "id": selected["id"],
                "name": selected["name"],
                "has_cookie": summary.get("has_cookie", False),
            },
            "accounts": accounts_payload,
            "all_accounts_summary": all_accounts_summary,
            "summary": summary,
            "snapshot": state,
            "auto_flags": flags_payload,
            "study_subject": cur_subj,
            "ojol_mode": getattr(cur_service.settings, "ojol_mode", "otomatis"),
            "limit_reached": limit_reached,
            "hours_left": summary.get("hours_left") or state.get("ojol_hours_left"),
            "logs": logs,
            "notifications": notices,
            "pending_bank_reviews_count": pending_bank_count,
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
                    current = get_current_user(request)
                    if not current or current["status"] != "approved":
                        break
                    payload = await build_dashboard_payload(request, current)
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
            if acc["archived"]:
                scoped = registry.scoped_settings(acc)
                sum_info = {"has_cookie": (scoped.runtime_dir / "http-session.json").is_file()}
            else:
                acc_service = resolve_account_service(request, acc["id"])
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
            async with manager.lock if manager else nullcontext():
                if archived and manager:
                    registry.get(account_id, owner=owner)
                    scoped = manager.service(account_id)
                    async with scoped.lock:
                        scoped.access.revoke()
                        await scoped.close()
                        registry.archive(owner, account_id)
                        manager.services.pop(account_id, None)
                else:
                    registry.archive(owner, account_id, archived=archived)
            return {"success": True}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))

    # ==================== WORKER & GAMEPLAY CONTROL ====================

    @app.post("/api/control/run")
    async def run_ojol(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        mode = getattr(cur_service.settings, "ojol_mode", "otomatis")
        try:
            res = await cur_service.command("run", mode=mode)
            return {"success": True, "message": res}
        except Exception as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/control/stop")
    async def stop_ojol(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        try:
            res = await cur_service.command("stop_ojol")
            return {"success": True, "message": res}
        except Exception as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/control/skip")
    async def skip_actions(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        try:
            res = await cur_service.command("skip")
            return {"success": True, "message": res}
        except Exception as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/control/run-needs")
    async def run_needs(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        try:
            res = await cur_service.command("run_kebutuhan")
            return {"success": True, "message": res}
        except Exception as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/control/stop-needs")
    async def stop_needs(request: Request, user: dict = Depends(require_user)):
        cur_service = resolve_account_service(request)
        if not cur_service:
            raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
        try:
            res = await cur_service.command("stop_kebutuhan")
            return {"success": True, "message": res}
        except Exception as exc:
            raise HTTPException(400, str(exc))

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
                        set_subject(
                            cur_service.settings.runtime_dir, m, "auto" if enabled else "dagang"
                        )
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
        from .study import STUDY_LABELS

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

        account_id = (body.get("account_id") or "").strip()
        async with manager.lock if manager else nullcontext():
            try:
                if registry and account_id:
                    registry.get(account_id, owner=owner)
                elif registry:
                    account = registry.selected(owner)
                    if not account:
                        accounts = registry.list(owner)
                        if accounts:
                            account = accounts[0]
                            registry.select(owner, account["id"])
                        else:
                            account = registry.create(owner, account_name)
                    account_id = account["id"]
                cur_service = manager.service(account_id) if manager else service
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            if not cur_service:
                raise HTTPException(500, "Layanan akun tidak dapat diinisialisasi")

            async with cur_service.lock:
                if maintenance := held_window(cur_service.maintenance_file):
                    raise HTTPException(503, maintenance.message())
                try:
                    digest = registry.check_cookie(account_id, payload) if registry else None
                except ValueError as exc:
                    raise HTTPException(409, str(exc))
                try:
                    await cur_service.stop_worker()
                    profile = await import_session(cur_service.settings, json.dumps(payload))
                    if digest:
                        registry.bind_cookie(account_id, digest)
                    cur_service.access.revoke()
                except Exception as exc:
                    raise HTTPException(400, f"Verifikasi sesi gagal: {exc}")

        nickname = profile["nickname"]
        return {
            "success": True,
            "message": f"Cookie berhasil diimpor! Akun terhubung sebagai '{nickname}'.",
            "nickname": nickname,
        }

    # ==================== NOTIFICATIONS ====================

    @app.get("/api/notifications")
    async def get_notifications(request: Request, user: dict = Depends(require_user)):
        from .notifications import list_notifications

        cur_service = resolve_account_service(request)
        if not cur_service and user.get("role") != "admin":
            return {"notifications": []}
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
        if not cur_service and user.get("role") != "admin":
            return {"success": True, "marked_count": 0}
        target_settings = cur_service.settings if cur_service else settings
        count = mark_notifications_read(target_settings, notice_ids)
        return {"success": True, "marked_count": count}

    # ==================== ADMIN APIS ====================

    @app.get("/api/admin/notifications")
    async def admin_notifications(
        request: Request,
        limit: int = 200,
        user: dict = Depends(require_admin),
    ):
        from .notifications import list_all_admin_notifications

        notices = list_all_admin_notifications(settings, registry=registry, limit=limit)
        return {"notifications": notices}

    @app.post("/api/admin/notifications/read")
    async def admin_notifications_mark_read(
        request: Request,
        user: dict = Depends(require_admin),
    ):
        from .notifications import mark_all_admin_notifications_read

        count = mark_all_admin_notifications_read(settings, registry=registry)
        return {"success": True, "marked_count": count}

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

    @app.get("/api/admin/settings")
    async def admin_get_settings(user: dict = Depends(require_admin)):
        return registry.get_all_settings()

    @app.post("/api/admin/settings")
    async def admin_update_settings(body: dict, user: dict = Depends(require_admin)):
        try:
            fields = body.keys() & registry.get_all_settings().keys()
            if "telegram_bot_token" in fields and body["telegram_bot_token"] is None:
                body["telegram_bot_token"] = ""
            candidate = Settings.model_validate(
                {
                    **{key: getattr(settings, key) for key in Settings.model_fields},
                    **{key: body[key] for key in fields},
                }
            )
            updates = {key: getattr(candidate, key) for key in fields}
            if "telegram_bot_token" in fields:
                updates["telegram_bot_token"] = candidate.telegram_bot_token.get_secret_value()
            updated = registry.update_settings(updates)
            if manager:
                manager.settings = registry.settings
            return {"success": True, "settings": updated}
        except ValidationError as exc:
            error = exc.errors(include_input=False, include_context=False)[0]
            field = ".".join(map(str, error["loc"]))
            message = (field + ": " if field else "") + error["msg"]
            raise HTTPException(400, message)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/bank-angka")
    async def get_bank_angka(request: Request, user: dict = Depends(require_user)):
        fleet_dirs, acc_names = get_all_fleet_directories()
        from .svg_captcha_solver import get_bank_templates, get_all_pending_reviews

        raw_templates = get_bank_templates(settings.runtime_dir)
        formatted_templates = {}
        total_variants = 0
        total_contributions = 0

        for digit, variants in raw_templates.items():
            formatted_templates[digit] = []
            for v in variants:
                total_variants += 1
                if isinstance(v, dict):
                    if v.get("by"):
                        total_contributions += 1
                    formatted_templates[digit].append({
                        "glyph": v.get("glyph", []),
                        "by": v.get("by"),
                        "at": v.get("at"),
                    })
                else:
                    formatted_templates[digit].append({
                        "glyph": v,
                        "by": None,
                        "at": None,
                    })

        pending = get_all_pending_reviews(fleet_dirs, acc_names)

        return {
            "templates": formatted_templates,
            "pending": pending,
            "total_templates": total_variants,
            "pending_count": len(pending),
            "total_contributions": total_contributions,
        }

    @app.post("/api/bank-angka/save")
    async def save_bank_angka(request: Request, user: dict = Depends(require_user)):
        body, _ = await parse_body(request)
        digit = str(body.get("digit", "")).strip()
        glyph = body.get("glyph")
        review_id = body.get("review_id")
        error_id = body.get("error_id")

        if not digit or len(digit) != 1 or not digit.isdigit():
            raise HTTPException(400, "Digit harus berupa angka 0-9 tunggal")
        if not glyph or not isinstance(glyph, list):
            raise HTTPException(400, "Data glyph tidak valid")

        fleet_dirs, _ = get_all_fleet_directories()
        user_name = user.get("name") or user.get("username") or "Pengguna"

        from .svg_captcha_solver import resolve_review, save_template_to_bank

        save_template_to_bank(fleet_dirs, digit, glyph, contributed_by=user_name)

        if review_id:
            resolve_review(fleet_dirs, review_id, digit=digit, glyph=glyph, resolved_by=user_name)
        if error_id:
            resolve_review(fleet_dirs, error_id, digit=digit, glyph=glyph, resolved_by=user_name)

        return {"ok": True, "digit": digit, "by": user_name}

    @app.post("/api/bank-angka/delete")
    async def delete_bank_angka(request: Request, user: dict = Depends(require_user)):
        body, _ = await parse_body(request)
        digit = str(body.get("digit", "")).strip()
        index = body.get("index")

        if not digit or len(digit) != 1 or not digit.isdigit():
            raise HTTPException(400, "Digit harus berupa angka 0-9 tunggal")
        if index is None or not isinstance(index, int):
            raise HTTPException(400, "Index varian tidak valid")

        fleet_dirs, _ = get_all_fleet_directories()
        from .svg_captcha_solver import delete_template_from_bank

        delete_template_from_bank(fleet_dirs, digit, index)
        return {"ok": True, "digit": digit, "deleted_index": index}

    @app.post("/api/bank-angka/dismiss")
    async def dismiss_bank_angka(request: Request, user: dict = Depends(require_user)):
        body, _ = await parse_body(request)
        review_id = body.get("review_id")
        error_id = body.get("error_id")
        if not review_id and not error_id:
            raise HTTPException(400, "Review ID atau Error ID diperlukan")

        fleet_dirs, _ = get_all_fleet_directories()
        from .svg_captcha_solver import dismiss_review

        if review_id:
            dismiss_review(fleet_dirs, review_id)
        if error_id:
            dismiss_review(fleet_dirs, error_id)

        return {"ok": True}
