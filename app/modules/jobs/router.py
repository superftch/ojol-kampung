"""Web API routes for browsing job vacancies and applying directly."""

import asyncio
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.exceptions import HttpCoreError
from app.integrations.kampung.http_api import OjolHttpApi
from app.modules.jobs.schemas import JobApplyRequest
from app.modules.jobs.service import build_job_vacancies_payload
from app.web.deps import WebContext, get_ctx, require_user, resolve_account_service
from app.web.payloads import read_json

router = APIRouter()


def _require_account_service(ctx: WebContext, user: dict, request: Request):
    explicit_id = request.query_params.get("account_id")
    cur_service = resolve_account_service(ctx, user, explicit_id=explicit_id)
    if not cur_service:
        raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
    return cur_service


def _http_status_for_error(exc: HttpCoreError) -> int:
    if exc.category == "auth":
        return 401
    if exc.category == "blocked":
        return 403
    return 502


@router.get("/api/jobs/vacancies")
async def get_job_vacancies(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    """Fetch live job vacancies and skill/salary breakdown for the selected account."""
    cur_service = _require_account_service(ctx, user, request)
    try:
        async with asyncio.timeout(15), OjolHttpApi(cur_service.settings.runtime_dir) as api:
            me = await api.fetch_game_me()
            biz_items: list[dict] | None = None
            with suppress(HttpCoreError):
                biz_items = await api.fetch_biz_vacancies()
    except HttpCoreError as exc:
        raise HTTPException(_http_status_for_error(exc), str(exc)) from None
    except TimeoutError:
        raise HTTPException(504, "Permintaan daftar lowongan ke server game timeout.") from None

    return build_job_vacancies_payload(me, biz_items=biz_items)


@router.post("/api/jobs/apply")
async def apply_job_vacancy(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    """Apply directly to a facility or business job vacancy for the selected account."""
    body = await read_json(request, JobApplyRequest)
    cur_service = _require_account_service(ctx, user, request)

    if body.kind == "facility" and not body.facility_id:
        raise HTTPException(400, "facility_id wajib diisi untuk lowongan fasilitas.")
    if body.kind == "business" and not body.vacancy_id:
        raise HTTPException(400, "vacancy_id wajib diisi untuk lowongan usaha.")

    try:
        async with asyncio.timeout(15), OjolHttpApi(cur_service.settings.runtime_dir) as api:
            if body.kind == "facility":
                result = await api.apply_facility_job(
                    body.profession,
                    body.facility_id or "",
                    switch_job=body.switch_job,
                )
            else:
                result = await api.apply_biz_vacancy(
                    body.vacancy_id or "",
                    switch_job=body.switch_job,
                )
            with suppress(HttpCoreError):
                await api.fetch_game_me()
    except HttpCoreError as exc:
        raise HTTPException(_http_status_for_error(exc), str(exc)) from None
    except TimeoutError:
        raise HTTPException(504, "Permintaan lamaran ke server game timeout.") from None

    tidur = result.get("tidur") if isinstance(result, dict) else None
    msg = f"Kontrak {body.profession} berhasil dimulai."
    if tidur:
        msg += f" Jam tidur otomatis pindah ke {tidur}."
    return {"success": True, "message": msg, "result": result}
