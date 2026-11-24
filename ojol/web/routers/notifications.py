"""User notification listing and read-acknowledgement routes."""

from fastapi import APIRouter, Depends, Request

from ...notifications import list_notifications, mark_notifications_read
from ..deps import WebContext, get_ctx, require_user, resolve_account_service

router = APIRouter()


@router.get("/api/notifications")
async def get_notifications(
    request: Request,
    user: dict = Depends(require_user),
    ctx: WebContext = Depends(get_ctx),
):
    cur_service = resolve_account_service(
        ctx, user, explicit_id=request.query_params.get("account_id")
    )
    if not cur_service and user.get("role") != "admin":
        return {"notifications": []}
    target_settings = cur_service.settings if cur_service else ctx.settings
    return {"notifications": list_notifications(target_settings)}


@router.post("/api/notifications/read")
async def mark_read(
    request: Request,
    user: dict = Depends(require_user),
    ctx: WebContext = Depends(get_ctx),
):
    body = (
        await request.json()
        if request.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    notice_ids = body.get("ids")
    cur_service = resolve_account_service(
        ctx, user, explicit_id=request.query_params.get("account_id")
    )
    if not cur_service and user.get("role") != "admin":
        return {"success": True, "marked_count": 0}
    target_settings = cur_service.settings if cur_service else ctx.settings
    count = mark_notifications_read(target_settings, notice_ids)
    return {"success": True, "marked_count": count}
