"""Worker execution, auto flags, study subject, and direct cookie-import routes."""

import json
from contextlib import nullcontext, suppress
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.models import STUDY_LABELS
from app.integrations.kampung import session_transfer
from app.modules.gameplay.kerja import set_kerja_target_poin
from app.modules.gameplay.study import set_subject
from app.modules.ledger.finance import report_date
from app.modules.worker.maintenance import held_window
from app.modules.worker.schemas import (
    AutoFlagChange,
    DirectCookieImport,
    KerjaTargetChange,
    OjolModeChange,
    StudySubjectChange,
)
from app.modules.worker.settings import set_auto_flag
from app.modules.worker.status import status_record
from app.web.dashboard_queries import dashboard_snapshot
from app.web.deps import WebContext, get_ctx, require_user, resolve_account_service
from app.web.payloads import read_json

router = APIRouter()


def _require_account_service(ctx: WebContext, user: dict, request: Request):
    explicit_id = request.query_params.get("account_id")
    cur_service = resolve_account_service(ctx, user, explicit_id=explicit_id)
    if not cur_service:
        raise HTTPException(400, "Belum ada akun game yang terhubung atau dipilih.")
    return cur_service


async def _run_worker_command(
    ctx: WebContext, user: dict, request: Request, command: str, **kwargs
) -> dict:
    cur_service = _require_account_service(ctx, user, request)
    try:
        res = await cur_service.command(command, **kwargs)
        return {"success": True, "message": res}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from None


def _account_snapshot(cur_service) -> dict:
    status_data, _ = status_record(cur_service.settings.runtime_dir / "status.json")
    return dashboard_snapshot(cur_service.settings.runtime_dir, status_data)


def _validate_ojol_eligible(cur_service) -> None:
    snap = _account_snapshot(cur_service)
    if snap.get("ojol_mitra") is False:
        raise HTTPException(
            400,
            "Akun belum menjadi mitra Ojol. Daftar mitra terlebih dahulu di game.",
        )


def _validate_kerja_eligible(cur_service, *, allow_ojol_switch: bool = False) -> None:
    snap = _account_snapshot(cur_service)
    job = snap.get("job")
    if not isinstance(job, dict) or not job:
        raise HTTPException(
            400,
            "Akun belum memiliki pekerjaan aktif. Ambil kerja kantor dulu di game.",
        )
    if job.get("kantor") is None and job.get("employerType") not in {"PUBLIC", "BUSINESS"}:
        raise HTTPException(
            400,
            "Auto Kantor hanya untuk pekerjaan kantor/fasum/usaha.",
        )
    if snap.get("phase") in {"searching", "delivering", "complete"} or snap.get("trip"):
        raise HTTPException(
            400,
            "Selesaikan order Ojol yang sedang berjalan sebelum mengaktifkan Auto Kantor.",
        )


@router.post("/api/control/run")
async def run_ojol(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    cur_service = _require_account_service(ctx, user, request)
    _validate_ojol_eligible(cur_service)
    mode = getattr(cur_service.settings, "ojol_mode", "otomatis")
    try:
        res = await cur_service.command("run", mode=mode)
        return {"success": True, "message": res}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/control/stop")
async def stop_ojol(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return await _run_worker_command(ctx, user, request, "stop_ojol")


@router.get("/api/control/report")
async def account_report(
    request: Request,
    day: str | None = None,
    *,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    service = _require_account_service(ctx, user, request)
    try:
        return {"message": await service.account_profit(report_date(day or None))}
    except (ValueError, OverflowError) as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/control/house-scan")
async def house_scan(
    request: Request,
    kind: Literal["cleanup", "visit"],
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return await _run_worker_command(ctx, user, request, f"{kind}_scan")


@router.post("/api/control/skip")
async def skip_actions(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return await _run_worker_command(ctx, user, request, "skip")


@router.post("/api/control/run-needs")
async def run_needs(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return await _run_worker_command(ctx, user, request, "run_kebutuhan")


@router.post("/api/control/stop-needs")
async def stop_needs(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return await _run_worker_command(ctx, user, request, "stop_kebutuhan")


@router.post("/api/control/run-kerja")
async def run_kerja_cmd(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    cur_service = _require_account_service(ctx, user, request)
    _validate_kerja_eligible(cur_service, allow_ojol_switch=True)
    return await _run_worker_command(ctx, user, request, "run_kerja")


@router.post("/api/control/stop-kerja")
async def stop_kerja_cmd(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    return await _run_worker_command(ctx, user, request, "stop_kerja")


@router.post("/api/control/toggle-auto")
async def toggle_auto_api(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await read_json(request, AutoFlagChange)
    flag = body.flag
    enabled = body.enabled
    if not flag:
        raise HTTPException(400, "Nama flag diperlukan")
    cur_service = _require_account_service(ctx, user, request)
    try:
        if flag == "study":
            set_auto_flag(cur_service.settings.runtime_dir, "perpus", enabled)
            set_auto_flag(cur_service.settings.runtime_dir, "kuliah", enabled)
        elif flag == "garden":
            set_auto_flag(cur_service.settings.runtime_dir, "kebun", enabled)
        elif flag == "auto_subject":
            for mode in STUDY_LABELS:
                with suppress(ValueError):
                    set_subject(
                        cur_service.settings.runtime_dir, mode, "auto" if enabled else "dagang"
                    )
        elif flag == "kerja":
            if enabled:
                _validate_kerja_eligible(cur_service)
            set_auto_flag(cur_service.settings.runtime_dir, "kerja", enabled)
        elif flag == "kursus":
            if enabled:
                raise HTTPException(
                    400,
                    "Fitur Auto Kursus sedang dinonaktifkan.",
                )
            set_auto_flag(cur_service.settings.runtime_dir, "kursus", False)
        else:
            if flag == "ojol" and enabled:
                _validate_ojol_eligible(cur_service)
            set_auto_flag(cur_service.settings.runtime_dir, flag, enabled)
        return {"success": True, "flag": flag, "enabled": enabled}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/control/kerja-target")
async def set_kerja_target_api(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await read_json(request, KerjaTargetChange)
    cur_service = _require_account_service(ctx, user, request)
    try:
        set_kerja_target_poin(cur_service.settings.runtime_dir, body.target_poin)
        return {"success": True, "target_poin": body.target_poin}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/control/mode-ojol")
async def set_mode_ojol(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await read_json(request, OjolModeChange)
    mode = body.mode
    cur_service = _require_account_service(ctx, user, request)
    cur_service.settings.ojol_mode = mode
    return {"success": True, "mode": mode}


@router.post("/api/control/study-subject")
async def set_study_subject_api(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await read_json(request, StudySubjectChange)
    subject = body.subject
    mode = body.mode
    if not subject:
        raise HTTPException(400, "Bidang belajar diperlukan")
    cur_service = _require_account_service(ctx, user, request)
    try:
        if mode == "kursus":
            raise HTTPException(400, "Fitur Auto Kursus sedang dinonaktifkan.")
        elif mode and mode in STUDY_LABELS:
            set_subject(cur_service.settings.runtime_dir, mode, subject)
        else:
            errors = []
            for study_mode in STUDY_LABELS:
                try:
                    set_subject(cur_service.settings.runtime_dir, study_mode, subject)
                except ValueError as exc:
                    errors.append(f"{study_mode}: {exc}")
            if len(errors) == len(STUDY_LABELS):
                raise ValueError(errors[0])
        return {"success": True, "subject": subject}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/control/import-cookie")
async def import_cookie_direct(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    ctx: Annotated[WebContext, Depends(get_ctx)],
):
    body = await read_json(request, DirectCookieImport)
    cookie_raw = body.cookie
    if not cookie_raw.strip():
        raise HTTPException(400, "Cookie tidak boleh kosong")

    try:
        payload = session_transfer.parse_cookie_input(cookie_raw)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, f"Format cookie tidak valid: {exc}") from None

    registry = ctx.registry
    owner = registry.owner_for_user(user) if registry else 0
    custom_name = (body.name or "").strip()
    account_name = custom_name or "Akun Utama"
    account_id = (body.account_id or "").strip()

    async with ctx.manager.lock if ctx.manager else nullcontext():
        try:
            if registry and account_id:
                registry.get(account_id, owner=owner)
            elif registry:
                account = registry.selected(owner)
                if not account:
                    accounts = registry.list(owner)
                    if accounts:
                        account = accounts[0]
                        registry.select(owner, account["id"])
                    else:
                        account = registry.create(owner, account_name)
                account_id = account["id"]
            cur_service = ctx.manager.service(account_id) if ctx.manager else ctx.service
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        if not cur_service:
            raise HTTPException(500, "Layanan akun tidak dapat diinisialisasi")

        async with cur_service.lock:
            if maintenance := held_window(cur_service.maintenance_file):
                raise HTTPException(503, maintenance.message())
            try:
                digest = registry.check_cookie(account_id, payload) if registry else None
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            try:
                await cur_service.stop_worker()
                profile = await session_transfer.import_session(
                    cur_service.settings, json.dumps(payload)
                )
                if digest:
                    registry.bind_cookie(account_id, digest)
                cur_service.access.revoke()
            except Exception as exc:
                raise HTTPException(400, f"Verifikasi sesi gagal: {exc}") from None

    nickname = profile["nickname"]
    return {
        "success": True,
        "message": f"Cookie berhasil diimpor! Akun terhubung sebagai '{nickname}'.",
        "nickname": nickname,
    }
