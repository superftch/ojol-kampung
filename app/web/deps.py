"""Shared FastAPI dependencies and request context for the web layer."""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.core.models import Settings


@dataclass
class WebContext:
    """Container for runtime services exposed to FastAPI route handlers."""

    settings: Settings
    registry: Any = None
    manager: Any = None
    service: Any = None


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    """Return user fields safe to serialize to clients."""
    return {
        key: value
        for key, value in user.items()
        if key not in {"password_hash", "salt", "telegram_id"}
    }


def get_ctx(request: Request) -> WebContext:
    """Resolve the active WebContext from FastAPI application state."""
    return request.app.state.web_ctx


def get_current_user(
    request: Request, ctx: Annotated[WebContext, Depends(get_ctx)]
) -> dict[str, Any] | None:
    """Return the authenticated web user for the session cookie, or None."""
    if not ctx.registry:
        return None
    session_token = request.cookies.get("ojol_web_session")
    if not session_token:
        return None
    return ctx.registry.web.get_user_by_session(session_token)


def require_user(
    user: Annotated[dict[str, Any] | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Require an authenticated and admin-approved web user."""
    if not user:
        raise HTTPException(401, "Sesi kedaluwarsa atau belum login")
    if user.get("status") != "approved":
        raise HTTPException(403, "Akun belum disetujui admin")
    return user


def require_admin(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
    """Require an approved web user with admin role."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Akses ditolak: Hanya admin yang diizinkan")
    return user


def resolve_account_service(
    ctx: WebContext,
    user: dict[str, Any],
    account_id: str | None = None,
    explicit_id: str | None = None,
):
    """Resolve the ControlService for the requested or currently selected account."""
    if ctx.manager is None:
        return ctx.service
    if account_id:
        return ctx.manager.service(account_id)
    owner = ctx.registry.owner_for_user(user)
    if explicit_id:
        try:
            ctx.registry.get(explicit_id, owner=owner)
            return ctx.manager.service(explicit_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    selected = ctx.registry.selected(owner)
    if not selected:
        active = ctx.registry.list(owner)
        if active:
            ctx.registry.select(owner, active[0]["id"])
            selected = active[0]
    if selected:
        return ctx.manager.service(selected["id"])
    return None


def get_all_fleet_directories(ctx: WebContext) -> tuple[list[Path], dict[str, str]]:
    """Collect runtime directories and display names across all registered accounts."""
    dirs = [ctx.settings.runtime_dir]
    acc_names: dict[str, str] = {}
    if ctx.registry:
        for acc in ctx.registry.list() + ctx.registry.list(archived=True):
            scoped = ctx.registry.scoped_settings(acc)
            dirs.append(scoped.runtime_dir)
            acc_names[str(scoped.runtime_dir)] = acc.get("name", "Akun")
            acc_names[acc["id"]] = acc.get("name", "Akun")
    return dirs, acc_names
