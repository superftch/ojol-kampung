"""HTML auth pages and web session routes."""

import logging
from typing import Annotated
from urllib.parse import quote_plus, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.modules.admin.schemas import ImpersonateUser
from app.modules.auth.schemas import Credentials, PasswordConfirmation, Registration
from app.web.deps import (
    WebContext,
    get_ctx,
    get_current_user,
    public_user,
    require_admin,
    require_user,
)
from app.web.html import dashboard_html, login_html, register_html, setup_password_html
from app.web.payloads import parse_body, validate_payload

router = APIRouter()
logger = logging.getLogger(__name__)
ADMIN_RETURN_COOKIE = "ojol_admin_return"


def _set_session_cookie(
    response: Response, request: Request, token: str, key="ojol_web_session"
) -> None:
    is_secure = urlsplit(str(request.base_url)).scheme == "https"
    response.set_cookie(
        key,
        token,
        max_age=604800,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )


@router.get("/", response_class=HTMLResponse)
async def index(
    user: Annotated[dict | None, Depends(get_current_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("status") != "approved":
        return RedirectResponse(
            "/login?error=" + quote_plus("Akun Anda sedang menunggu persetujuan admin."),
            status_code=303,
        )
    if not user.get("has_password", 1) and not user.get("impersonating"):
        return RedirectResponse("/setup-password", status_code=303)
    return dashboard_html(public_user(user))


@router.get("/setup-password", response_class=HTMLResponse)
async def setup_password_page(
    error: str = "",
    *,
    user: Annotated[dict | None, Depends(get_current_user)],
):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.get("has_password", 1):
        return RedirectResponse("/", status_code=303)
    return setup_password_html(user, error=error)


@router.post("/api/auth/setup-password")
async def setup_password_api(
    request: Request,
    user: Annotated[dict | None, Depends(get_current_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    if not ctx.registry:
        raise HTTPException(500, "Registry belum siap")
    if not user:
        raise HTTPException(401, "Sesi belum aktif")
    if user.get("impersonating"):
        raise HTTPException(403, "Pengaturan kredensial hanya tersedia untuk pemilik akun.")
    body, is_json = await parse_body(request)
    try:
        form = validate_payload(PasswordConfirmation, body)
        if form.password != form.confirm_password:
            raise ValueError("Konfirmasi password tidak cocok.")
        updated = ctx.registry.web.setup_password(user["id"], form.username, form.password)
        if is_json:
            return {"success": True, "user": public_user(updated), "redirect": "/"}
        return RedirectResponse("/", status_code=303)
    except ValueError as exc:
        if is_json:
            raise HTTPException(400, str(exc)) from None
        return RedirectResponse("/setup-password?error=" + quote_plus(str(exc)), status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: str = "",
    success: str = "",
    *,
    user: Annotated[dict | None, Depends(get_current_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    if user and user.get("status") == "approved":
        return RedirectResponse("/", status_code=303)
    return login_html(
        error=error,
        success=success,
        can_return_to_admin=bool(request.cookies.get(ADMIN_RETURN_COOKIE)),
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    error: str = "",
    success: str = "",
    *,
    user: Annotated[dict | None, Depends(get_current_user)],
):
    if user and user.get("status") == "approved":
        return RedirectResponse("/", status_code=303)
    return register_html(error=error, success=success)


@router.get("/logout")
async def logout_get(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    response = RedirectResponse("/login", status_code=303)
    _clear_session(request, ctx, response)
    return response


@router.post("/api/auth/register")
async def register_api(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    if not ctx.registry:
        raise HTTPException(500, "Registry belum siap")
    body, is_json = await parse_body(request)
    try:
        form = validate_payload(Registration, body)
        if not is_json and form.confirm_password and form.password != form.confirm_password:
            raise ValueError("Konfirmasi password tidak cocok.")
        user = ctx.registry.web.register(form.username, form.password, form.name)
        if user.get("status") == "approved":
            msg = "Pendaftaran berhasil! Akun Anda aktif sebagai admin. Silakan masuk."
        else:
            msg = "Pendaftaran berhasil! Akun Anda sedang menunggu persetujuan admin."
        if is_json:
            return {"success": True, "message": msg, "user": public_user(user)}
        return RedirectResponse("/login?success=" + quote_plus(msg), status_code=303)
    except ValueError as exc:
        if is_json:
            raise HTTPException(400, str(exc)) from None
        return RedirectResponse("/register?error=" + quote_plus(str(exc)), status_code=303)


@router.post("/api/auth/login")
async def login_api(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    if not ctx.registry:
        raise HTTPException(500, "Registry belum siap")
    body, is_json = await parse_body(request)
    try:
        form = validate_payload(Credentials, body)
        user = ctx.registry.web.authenticate_password(form.username, form.password)
        token = ctx.registry.web.issue_session(user["id"])
        res: Response = (
            JSONResponse({"success": True, "user": public_user(user)})
            if is_json
            else RedirectResponse("/", status_code=303)
        )
        _set_session_cookie(res, request, token)
        res.delete_cookie(ADMIN_RETURN_COOKIE)
        return res
    except ValueError as exc:
        if is_json:
            raise HTTPException(400, str(exc)) from None
        return RedirectResponse("/login?error=" + quote_plus(str(exc)), status_code=303)


@router.post("/api/auth/logout")
async def logout_post(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    res = JSONResponse({"success": True})
    _clear_session(request, ctx, res)
    return res


def _clear_session(request: Request, ctx: WebContext, response: Response) -> None:
    for key in ("ojol_web_session", ADMIN_RETURN_COOKIE):
        if ctx.registry and (token := request.cookies.get(key)):
            ctx.registry.web.revoke_session(token)
        response.delete_cookie(key)


@router.post("/api/admin/impersonate")
def start_impersonation(
    request: Request,
    body: ImpersonateUser,
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    parent_token = request.cookies["ojol_web_session"]
    try:
        token = ctx.registry.web.issue_impersonation(parent_token, body.user_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    logger.info("Admin %s entered web session for user %s", user["id"], body.user_id)
    response = JSONResponse({"success": True})
    _set_session_cookie(response, request, token)
    _set_session_cookie(response, request, parent_token, ADMIN_RETURN_COOKIE)
    return response


@router.post("/auth/impersonation/stop")
def stop_impersonation(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    token = request.cookies.get("ojol_web_session")
    parent_token = request.cookies.get(ADMIN_RETURN_COOKIE)
    response = RedirectResponse("/", status_code=303)
    if parent_token and ctx.registry.web.end_impersonation(token, parent_token):
        _set_session_cookie(response, request, parent_token)
    else:
        response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(ADMIN_RETURN_COOKIE)
    return response


@router.get("/api/auth/me")
async def get_me(user: Annotated[dict, Depends(require_user)]):
    return {"logged_in": True, "user": user}
