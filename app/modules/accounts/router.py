"""Account listing, selection, creation, renaming, and archiving routes."""

from contextlib import nullcontext
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.modules.worker.settings import auto_flags
from app.web.deps import WebContext, get_ctx, require_user, resolve_account_service

router = APIRouter()


@router.get("/api/accounts")
async def list_accounts(
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    registry = ctx.registry
    owner = registry.owner_for_user(user)
    accounts_list = registry.list(owner) + registry.list(owner, archived=True)
    selected = registry.selected(owner)
    payload = []
    for acc in accounts_list:
        if acc["archived"]:
            scoped = registry.scoped_settings(acc)
            sum_info = {"has_cookie": (scoped.runtime_dir / "http-session.json").is_file()}
            acc_flags = auto_flags(scoped.runtime_dir) if scoped.runtime_dir.exists() else {}
        else:
            acc_service = resolve_account_service(ctx, user, account_id=acc["id"])
            sum_info = acc_service.summary() if acc_service else {}
            acc_flags = auto_flags(acc_service.settings.runtime_dir) if acc_service else {}
        payload.append(
            {
                "id": acc["id"],
                "name": acc["name"],
                "archived": bool(acc["archived"]),
                "legacy": bool(acc["legacy"]),
                "is_selected": bool(selected and acc["id"] == selected["id"]),
                "has_cookie": sum_info.get("has_cookie", False),
                "is_running": sum_info.get("active", False),
                "auto_ojol": bool(acc_flags.get("ojol")),
                "auto_flags": acc_flags,
            }
        )
    return {"accounts": payload, "quota": registry.quota(owner)}


@router.post("/api/accounts/select")
async def select_account_api(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await request.json()
    account_id = body.get("account_id")
    if not account_id:
        raise HTTPException(400, "ID akun diperlukan")
    owner = ctx.registry.owner_for_user(user)
    try:
        ctx.registry.select(owner, account_id)
        return {"success": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/accounts/create")
async def create_account_api(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await request.json()
    name = body.get("name")
    owner = ctx.registry.owner_for_user(user)
    try:
        acc = ctx.registry.create(owner, name) if name else ctx.registry.create(owner)
        return {"success": True, "account": acc}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/accounts/rename")
async def rename_account_api(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await request.json()
    account_id = body.get("account_id")
    name = body.get("name")
    if not account_id or not name:
        raise HTTPException(400, "ID akun dan nama baru diperlukan")
    owner = ctx.registry.owner_for_user(user)
    try:
        ctx.registry.rename(owner, account_id, name)
        return {"success": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/accounts/archive")
async def archive_account_api(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await request.json()
    account_id = body.get("account_id")
    archived = bool(body.get("archived", True))
    if not account_id:
        raise HTTPException(400, "ID akun diperlukan")
    owner = ctx.registry.owner_for_user(user)
    try:
        async with ctx.manager.lock if ctx.manager else nullcontext():
            if archived and ctx.manager:
                ctx.registry.get(account_id, owner=owner)
                scoped = ctx.manager.service(account_id)
                async with scoped.lock:
                    scoped.access.revoke()
                    await scoped.close()
                    ctx.registry.archive(owner, account_id)
                    ctx.manager.services.pop(account_id, None)
            else:
                ctx.registry.archive(owner, account_id, archived=archived)
        return {"success": True}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from None
