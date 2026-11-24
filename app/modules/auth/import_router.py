"""Health check and one-time ticket/CSRF HTTPS cookie import routes."""

import asyncio
import html
import json
from typing import Annotated
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.models import ROOT
from app.integrations.kampung import session_transfer
from app.modules.notifications.service import queue_error
from app.modules.worker.maintenance import held_window
from app.web.deps import WebContext, get_ctx

router = APIRouter()


def _resolve_import_service(ctx: WebContext, request: Request):
    if ctx.manager is None:
        return ctx.service
    try:
        identifier = request.path_params.get("account_id")
        scoped = ctx.manager.service(identifier) if identifier else ctx.manager.legacy()
        account = ctx.registry.get(scoped.account_id)
        if not ctx.registry.allowed(account["owner"]):
            raise ValueError("Akses pemilik akun dicabut")
        return scoped
    except ValueError:
        raise HTTPException(403, "Akun tidak tersedia / akses dicabut") from None


def _require_access(scoped, request: Request) -> None:
    if not scoped.access.expiry(request.cookies.get("ojol_import"), "session"):
        raise HTTPException(403, "Link import diperlukan / sesi kedaluwarsa")


@router.get("/health")
async def health(ctx: Annotated[WebContext, Depends(get_ctx)]):
    return {
        "service": "ok",
        "tunnel_enabled": ctx.settings.tunnel_enabled,
        "tunnel_process_alive": (
            ctx.manager.hub.tunnel_alive() if ctx.manager else ctx.service.tunnel_alive()
        ),
    }


@router.get("/a/{account_id}/access/{ticket}")
@router.get("/access/{ticket}")
async def access(
    ticket: str,
    request: Request,
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    scoped = _resolve_import_service(ctx, request)
    session = scoped.access.consume_ticket(ticket) if len(ticket) <= 100 else None
    if not session:
        raise HTTPException(403, "Link kedaluwarsa/sudah dipakai; tekan Import Cookie di bot")
    response = RedirectResponse(scoped.url_prefix + "/import-cookie", status_code=303)
    response.set_cookie(
        "ojol_import",
        session,
        max_age=900,
        httponly=True,
        secure=urlsplit(scoped.public_url()).scheme == "https",
        samesite="lax",
        path=scoped.url_prefix + "/",
    )
    return response


@router.get("/a/{account_id}/import-cookie", response_class=HTMLResponse)
@router.get("/import-cookie", response_class=HTMLResponse)
async def form(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    scoped = _resolve_import_service(ctx, request)
    _require_access(scoped, request)
    token = scoped.access.csrf_token(request.cookies.get("ojol_import"))
    if token is None:
        raise HTTPException(403, "Sesi import kedaluwarsa; minta link baru di bot")
    return (
        (ROOT / "app" / "web" / "templates" / "cookie_form.html")
        .read_text()
        .replace("{{CSRF_TOKEN}}", token)
        .replace("{{ACCOUNT_NAME}}", html.escape(scoped.settings.account_name or "Utama"))
        .replace("{{IMPORT_PATH}}", scoped.url_prefix + "/import-cookie")
    )


@router.post("/a/{account_id}/import-cookie", response_class=HTMLResponse)
@router.post("/import-cookie", response_class=HTMLResponse)
async def submit(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    scoped = _resolve_import_service(ctx, request)
    scoped_settings = scoped.settings
    _require_access(scoped, request)
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Gunakan form import cookie")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise HTTPException(413, "Cookie terlalu besar")

    try:
        fields = parse_qs(body.decode())
        if not scoped.access.valid_csrf(
            request.cookies.get("ojol_import"), fields.get("csrf", [""])[0]
        ):
            raise HTTPException(
                403, "Form kedaluwarsa/berubah. Buka ulang link Import Cookie terbaru."
            )
        payload = session_transfer.parse_cookie_input(fields.get("cookie", [""])[0])
    except (ValueError, TypeError, KeyError, UnicodeError):
        return HTMLResponse(
            "Cookie tidak valid. Kembali dan masukkan cookie sesi KampungSebelah saja.",
            status_code=400,
        )

    async with ctx.manager.lock if ctx.manager else asyncio.Lock(), scoped.lock:
        _require_access(scoped, request)
        if maintenance := held_window(scoped.maintenance_file):
            return HTMLResponse(maintenance.message(), status_code=503)
        digest = None
        if ctx.manager:
            account = ctx.manager.registry.get(scoped.account_id)
            try:
                digest = ctx.manager.registry.check_cookie(account["id"], payload)
            except ValueError:
                return HTMLResponse(
                    "Cookie sudah terhubung ke akun lain. Gunakan akun tersebut.",
                    status_code=409,
                )
        await scoped.stop_worker()
        try:
            await session_transfer.import_session(scoped_settings, json.dumps(payload))
            if ctx.manager:
                ctx.manager.registry.bind_cookie(scoped.account_id, digest)
                ctx.manager.service(scoped.account_id)
        except Exception as exc:
            queue_error(
                scoped_settings,
                RuntimeError("Import cookie gagal; sesi tidak dapat diverifikasi"),
                session_transfer.STAGE,
                {
                    "cause": type(exc).__name__,
                    "http_category": getattr(exc, "category", None),
                    "account_id": scoped.account_id,
                },
            )
            return HTMLResponse(
                "Import gagal. Periksa cookie, lalu minta link baru melalui tombol Import Cookie.",
                status_code=400,
            )
        scoped.access.revoke()

    response = HTMLResponse(
        "<html lang='id'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Import berhasil</title><h1>Cookie berhasil diimpor</h1>"
        "<p>Sesi game terverifikasi. Kembali ke dashboard dan tekan <strong>Jalankan Ojol</strong>.</p></html>"
    )
    response.delete_cookie("ojol_import", path=scoped.url_prefix + "/")
    return response
