"""Dashboard summary, SSE live stream, and extension distribution routes."""

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.web.dashboard_queries import build_dashboard_payload
from app.web.deps import WebContext, get_ctx, get_current_user, require_user
from app.web.extension_crx import (
    EXTENSION_DIR,
    build_extension_crx3,
    build_extension_zip,
    build_linux_policy_json,
    build_macos_mobileconfig,
    build_update_xml,
    build_windows_reg,
    get_extension_identity,
    resolve_public_origin,
)

router = APIRouter()


def _resolve_origin_for_request(request: Request, ctx: WebContext) -> str:
    configured = ""
    if ctx.manager is not None and hasattr(ctx.manager, "public_url"):
        configured = str(ctx.manager.public_url() or "")
    elif ctx.settings is not None:
        configured = str(getattr(ctx.settings, "login_public_url", "") or "")
    headers = {k.lower(): v for k, v in request.headers.items()}
    return resolve_public_origin(str(request.base_url), headers, configured)


@router.get("/api/extension/download")
@router.get("/download/extension.zip")
async def download_extension_zip():
    if not EXTENSION_DIR.is_dir():
        raise HTTPException(404, "Direktori ekstensi tidak ditemukan")

    content = await asyncio.to_thread(build_extension_zip, EXTENSION_DIR)
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="kampungsebelah-extension.zip"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/extension/download.crx")
@router.get("/download/extension.crx")
async def download_extension_crx(ctx: Annotated[WebContext, Depends(get_ctx)]):
    if not EXTENSION_DIR.is_dir():
        raise HTTPException(404, "Direktori ekstensi tidak ditemukan")

    crx_bytes, _, _ = await asyncio.to_thread(
        build_extension_crx3, ctx.settings.runtime_dir, EXTENSION_DIR
    )
    return Response(
        content=crx_bytes,
        media_type="application/x-chrome-extension",
        headers={
            "Content-Disposition": 'attachment; filename="kampungsebelah-extension.crx"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/extension/update.xml")
@router.get("/download/extension-update.xml")
async def download_extension_update_xml(
    request: Request,
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    if not EXTENSION_DIR.is_dir():
        raise HTTPException(404, "Direktori ekstensi tidak ditemukan")

    ext_id, version = await asyncio.to_thread(
        get_extension_identity, ctx.settings.runtime_dir, EXTENSION_DIR
    )
    origin = _resolve_origin_for_request(request, ctx)
    codebase_url = f"{origin}/api/extension/download.crx"
    xml_body = build_update_xml(ext_id, version, codebase_url)
    return Response(
        content=xml_body,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/api/extension/info")
async def get_extension_info(
    request: Request,
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    if not EXTENSION_DIR.is_dir():
        raise HTTPException(404, "Direktori ekstensi tidak ditemukan")

    ext_id, version = await asyncio.to_thread(
        get_extension_identity, ctx.settings.runtime_dir, EXTENSION_DIR
    )
    origin = _resolve_origin_for_request(request, ctx)
    update_url = f"{origin}/api/extension/update.xml"
    crx_url = f"{origin}/api/extension/download.crx"
    return {
        "extension_id": ext_id,
        "version": version,
        "origin": origin,
        "update_url": update_url,
        "crx_url": crx_url,
        "policy_value": f"{ext_id};{update_url}",
    }


@router.get("/api/extension/policy/windows.reg")
async def download_windows_policy(
    request: Request,
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    ext_id, _ = await asyncio.to_thread(
        get_extension_identity, ctx.settings.runtime_dir, EXTENSION_DIR
    )
    origin = _resolve_origin_for_request(request, ctx)
    reg_body = build_windows_reg(ext_id, f"{origin}/api/extension/update.xml")
    return Response(
        content=reg_body.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="kampungsebelah-chrome-policy.reg"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/extension/policy/macos.mobileconfig")
async def download_macos_policy(
    request: Request,
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    ext_id, _ = await asyncio.to_thread(
        get_extension_identity, ctx.settings.runtime_dir, EXTENSION_DIR
    )
    origin = _resolve_origin_for_request(request, ctx)
    plist_body = build_macos_mobileconfig(ext_id, f"{origin}/api/extension/update.xml")
    return Response(
        content=plist_body.encode("utf-8"),
        media_type="application/x-apple-aspen-config",
        headers={
            "Content-Disposition": 'attachment; filename="kampungsebelah-chrome-policy.mobileconfig"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/extension/policy/linux.json")
async def download_linux_policy(
    request: Request,
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    ext_id, _ = await asyncio.to_thread(
        get_extension_identity, ctx.settings.runtime_dir, EXTENSION_DIR
    )
    origin = _resolve_origin_for_request(request, ctx)
    json_body = build_linux_policy_json(ext_id, f"{origin}/api/extension/update.xml")
    return Response(
        content=json_body.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="kampungsebelah-helper.json"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/dashboard")
async def get_dashboard(
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return await asyncio.to_thread(build_dashboard_payload, ctx, user)


@router.get("/api/dashboard/stream")
async def get_dashboard_stream(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                current = get_current_user(request, ctx)
                if not current or current["status"] != "approved":
                    break
                payload = await asyncio.to_thread(build_dashboard_payload, ctx, current)
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
