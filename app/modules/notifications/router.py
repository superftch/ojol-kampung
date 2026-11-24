"""User notification listing and read-acknowledgement routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.notifications.repository import list_notifications, mark_notifications_read
from app.modules.notifications.schemas import NoticeSelection
from app.web.deps import WebContext, get_ctx, require_user, resolve_account_service
from app.web.payloads import is_json_request, read_json

router = APIRouter()


@router.get("/api/notifications")
async def get_notifications(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
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
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    notice_ids = (
        (await read_json(request, NoticeSelection)).ids if is_json_request(request) else None
    )
    cur_service = resolve_account_service(
        ctx, user, explicit_id=request.query_params.get("account_id")
    )
    if not cur_service and user.get("role") != "admin":
        return {"success": True, "marked_count": 0}
    target_settings = cur_service.settings if cur_service else ctx.settings
    count = mark_notifications_read(target_settings, notice_ids)
    return {"success": True, "marked_count": count}
