"""Dashboard summary, SSE live stream, and extension archive download routes."""

import asyncio
import io
import json
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ...models import ROOT
from ..dashboard_queries import build_dashboard_payload
from ..deps import WebContext, get_ctx, get_current_user, require_user

router = APIRouter()

_EXTENSION_FILES = (
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
)


@router.get("/api/extension/download")
@router.get("/download/extension.zip")
async def download_extension_zip():
    extension_dir = ROOT / "tools" / "chrome-diving-radar"
    if not extension_dir.is_dir():
        raise HTTPException(404, "Direktori ekstensi tidak ditemukan")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in _EXTENSION_FILES:
            fpath = extension_dir / fname
            if fpath.is_file():
                zf.writestr(f"kampungsebelah-extension/{fname}", fpath.read_bytes())

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="kampungsebelah-extension.zip"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/dashboard")
async def get_dashboard(
    user: dict = Depends(require_user),
    ctx: WebContext = Depends(get_ctx),
):
    return await asyncio.to_thread(build_dashboard_payload, ctx, user)


@router.get("/api/dashboard/stream")
async def get_dashboard_stream(
    request: Request,
    user: dict = Depends(require_user),
    ctx: WebContext = Depends(get_ctx),
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
