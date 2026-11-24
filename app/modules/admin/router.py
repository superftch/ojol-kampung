"""Admin user approval, fleet notifications, limits, and server settings routes."""

from contextlib import nullcontext
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.core.models import Settings
from app.core.storage import write_private
from app.modules.admin.schemas import AccountLimit, FleetLimit, MaintenanceChange, ReviewUser
from app.modules.notifications.repository import (
    list_all_admin_notifications,
    mark_all_admin_notifications_read,
)
from app.modules.worker.maintenance import SCHEDULE_FILE, MaintenanceWindow, read_window
from app.web.deps import WebContext, get_ctx, public_user, require_admin
from app.web.payloads import read_json

router = APIRouter()


@router.get("/api/admin/notifications")
async def admin_notifications(
    limit: int = 200,
    *,
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    notices = list_all_admin_notifications(ctx.settings, registry=ctx.registry, limit=limit)
    return {"notifications": notices}


@router.post("/api/admin/notifications/read")
async def admin_notifications_mark_read(
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    count = mark_all_admin_notifications_read(ctx.settings, registry=ctx.registry)
    return {"success": True, "marked_count": count}


@router.get("/api/admin/pending")
async def admin_pending(
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return [public_user(row) for row in ctx.registry.web.list_pending()]


@router.get("/api/admin/users")
async def admin_users(
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return [public_user(row) for row in ctx.registry.web.list_users()]


@router.post("/api/admin/review")
async def admin_review(
    body: ReviewUser,
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    try:
        async with ctx.manager.lock if ctx.manager else nullcontext():
            updated = ctx.registry.web.review_user(body.user_id, user["id"], body.approve)
            if not body.approve and ctx.manager:
                await ctx.manager.revoke_owner(ctx.registry.owner_for_user(updated))
        return {"success": True, "user": public_user(updated)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/admin/account-limit")
async def admin_account_limit(
    body: AccountLimit,
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    try:
        ctx.registry.web.set_account_limit(body.user_id, body.maximum)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"success": True}


@router.get("/api/admin/maintenance")
async def admin_maintenance(
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    window = read_window(ctx.settings.runtime_dir / SCHEDULE_FILE)
    return {"description": window.description() if window else None}


@router.post("/api/admin/maintenance")
async def admin_set_maintenance(
    body: MaintenanceChange,
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    path = ctx.settings.runtime_dir / SCHEDULE_FILE
    if body.mode == "off":
        path.unlink(missing_ok=True)
        return {"description": None}
    try:
        window = (
            MaintenanceWindow.create_manual(body.target)
            if body.mode == "manual"
            else MaintenanceWindow.parse(f"{body.start} / {body.end}", body.target)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    write_private(path, window.payload())
    return {"description": window.description()}


@router.post("/api/admin/set-limit")
async def admin_set_limit(
    request: Request,
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await read_json(request, FleetLimit)
    try:
        ctx.registry.set_limit(body.name, body.value)
        return {"success": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/api/admin/settings")
async def admin_get_settings(
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return ctx.registry.get_all_settings()


@router.post("/api/admin/settings")
async def admin_update_settings(
    body: dict,
    user: Annotated[dict, Depends(require_admin)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    try:
        fields = body.keys() & ctx.registry.get_all_settings().keys()
        candidate = Settings.model_validate(
            {
                **{key: getattr(ctx.settings, key) for key in Settings.model_fields},
                **{key: body[key] for key in fields},
            }
        )
        updates = {key: getattr(candidate, key) for key in fields}
        updated = ctx.registry.update_settings(updates)
        if ctx.manager:
            ctx.manager.settings = ctx.registry.settings
        return {"success": True, "settings": updated}
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_context=False)[0]
        field = ".".join(map(str, error["loc"]))
        message = (field + ": " if field else "") + error["msg"]
        raise HTTPException(400, message) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
