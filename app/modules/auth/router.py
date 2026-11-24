"""HTML auth pages and web session routes."""

from typing import Annotated
from urllib.parse import quote_plus, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.web.deps import (
    WebContext,
    get_ctx,
    get_current_user,
    parse_body,
    public_user,
    require_user,
)
from app.web.html import dashboard_html, login_html, register_html, setup_password_html

router = APIRouter()


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    is_secure = urlsplit(str(request.base_url)).scheme == "https"
    response.set_cookie(
        "ojol_web_session",
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
    if not user.get("has_password", 1):
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
        updated = ctx.registry.web.setup_password(user["id"], username, password)
        if is_json:
            return {"success": True, "user": public_user(updated), "redirect": "/"}
        return RedirectResponse("/", status_code=303)
    except ValueError as exc:
        if is_json:
            raise HTTPException(400, str(exc)) from None
        return RedirectResponse("/setup-password?error=" + quote_plus(str(exc)), status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    error: str = "",
    success: str = "",
    *,
    user: Annotated[dict | None, Depends(get_current_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    if user and user.get("status") == "approved":
        return RedirectResponse("/", status_code=303)
    return login_html(error=error, success=success)


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
    token = request.cookies.get("ojol_web_session")
    if token and ctx.registry:
        ctx.registry.web.revoke_session(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("ojol_web_session", path="/")
    return response


@router.post("/api/auth/register")
async def register_api(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    if not ctx.registry:
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
        user = ctx.registry.web.register(username, password, name)
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
    username = body.get("username", "")
    password = body.get("password", "")

    try:
        user = ctx.registry.web.authenticate_password(username, password)
        token = ctx.registry.web.issue_session(user["id"])
        res: Response = (
            JSONResponse({"success": True, "user": public_user(user)})
            if is_json
            else RedirectResponse("/", status_code=303)
        )
        _set_session_cookie(res, request, token)
        return res
    except ValueError as exc:
        if is_json:
            raise HTTPException(400, str(exc)) from None
        return RedirectResponse("/login?error=" + quote_plus(str(exc)), status_code=303)


@router.post("/api/auth/logout")
async def logout_post(request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]):
    token = request.cookies.get("ojol_web_session")
    if token and ctx.registry:
        ctx.registry.web.revoke_session(token)
    res = JSONResponse({"success": True})
    res.delete_cookie("ojol_web_session", path="/")
    return res


@router.get("/api/auth/me")
async def get_me(user: Annotated[dict, Depends(require_user)]):
    return {"logged_in": True, "user": user}
