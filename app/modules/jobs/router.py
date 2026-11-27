"""Web API routes for browsing job vacancies and applying directly."""

import asyncio
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.exceptions import HttpCoreError
from app.integrations.kampung.http_api import OjolHttpApi
from app.modules.jobs.schemas import JobApplyRequest, JobSniperConfigRequest
from app.modules.jobs.service import (
    build_job_vacancies_payload,
    invalidate_vacancies_cache,
    load_vacancies_cache,
    save_vacancies_cache,
)
from app.modules.jobs.sniper import (
    load_sniper_config,
    load_sniper_state,
    run_job_sniper_once,
    save_sniper_config,
    save_sniper_state,
)
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
    """Fetch job vacancies (cached per account; pass ?refresh=1 to force live fetch)."""
    cur_service = _require_account_service(ctx, user, request)
    directory = cur_service.settings.runtime_dir
    force_refresh = request.query_params.get("refresh", "").lower() in {"1", "true", "yes"}
    if not force_refresh:
        cached = load_vacancies_cache(directory)
        if cached is not None:
            return cached
    try:
        async with asyncio.timeout(15), OjolHttpApi(directory) as api:
            me = await api.fetch_game_me()
            biz_items: list[dict] | None = None
            with suppress(HttpCoreError):
                biz_items = await api.fetch_biz_vacancies()
    except HttpCoreError as exc:
        raise HTTPException(_http_status_for_error(exc), str(exc)) from None
    except TimeoutError:
        raise HTTPException(504, "Permintaan daftar lowongan ke server game timeout.") from None

    payload = build_job_vacancies_payload(me, biz_items=biz_items)
    return save_vacancies_cache(directory, payload)


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
        invalidate_vacancies_cache(cur_service.settings.runtime_dir)
    except HttpCoreError as exc:
        raise HTTPException(_http_status_for_error(exc), str(exc)) from None
    except TimeoutError:
        raise HTTPException(504, "Permintaan lamaran ke server game timeout.") from None

    tidur = result.get("tidur") if isinstance(result, dict) else None
    msg = f"Kontrak {body.profession} berhasil dimulai."
    if tidur:
        msg += f" Jam tidur otomatis pindah ke {tidur}."
    return {"success": True, "message": msg, "result": result}


@router.get("/api/jobs/sniper")
async def get_job_sniper(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    """Return Job Sniper configuration and runtime state for the selected account."""
    cur_service = _require_account_service(ctx, user, request)
    directory = cur_service.settings.runtime_dir
    return {
        "config": load_sniper_config(directory),
        "state": load_sniper_state(directory),
    }


@router.post("/api/jobs/sniper")
async def update_job_sniper(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    """Update Job Sniper configuration for the selected account."""
    body = await read_json(request, JobSniperConfigRequest)
    cur_service = _require_account_service(ctx, user, request)
    directory = cur_service.settings.runtime_dir
    config = save_sniper_config(directory, body.model_dump())
    # Clear next_check_at so a newly enabled or reconfigured sniper checks immediately once.
    state = save_sniper_state(directory, {**load_sniper_state(directory), "next_check_at": None})
    supervisor = getattr(getattr(ctx, "manager", None), "supervisor", None)
    if supervisor is not None and hasattr(supervisor, "_sniper_next_check_ts"):
        supervisor._sniper_next_check_ts.pop(cur_service.account_id, None)
    return {
        "success": True,
        "message": "Pengaturan Job Sniper disimpan.",
        "config": config,
        "state": state,
    }


@router.post("/api/jobs/sniper/run")
async def run_job_sniper_now(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    """Run one immediate Job Sniper check and apply if an eligible job is found."""
    cur_service = _require_account_service(ctx, user, request)
    directory = cur_service.settings.runtime_dir
    try:
        async with asyncio.timeout(20):
            res = await run_job_sniper_once(
                directory,
                settings=cur_service.settings,
                force=True,
            )
    except TimeoutError:
        raise HTTPException(504, "Permintaan Job Sniper ke server game timeout.") from None

    if res.get("error"):
        raise HTTPException(502, res["error"])
    return {
        "success": True,
        "sniped": bool(res.get("sniped")),
        "message": res.get("message") or "",
        "config": res.get("config"),
        "state": res.get("state"),
    }
