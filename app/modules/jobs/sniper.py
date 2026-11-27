"""Scheduled Job Sniper: automatically picks and applies to the highest-paying eligible job."""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.exceptions import HttpCoreError
from app.core.models import now
from app.core.storage import write_private
from app.integrations.kampung.http_api import OjolHttpApi
from app.modules.jobs.service import (
    build_job_vacancies_payload,
    invalidate_vacancies_cache,
    save_vacancies_cache,
)
from app.modules.notifications.service import queue_notice

logger = logging.getLogger(__name__)

WIB = ZoneInfo("Asia/Jakarta")
SNIPER_CONFIG_FILE = "job-sniper.json"
SNIPER_STATE_FILE = "job-sniper-state.json"

DEFAULT_SNIPER_CONFIG: dict[str, Any] = {
    "enabled": False,
    "mode": "wait_kosong",
    "target_mode": "highest",
    "target_job_id": "",
    "interval_seconds": 30,
    "schedule_enabled": False,
    "start_time": "00:00",
    "end_time": "23:59",
    "source_filter": "all",
    "skill_track_id": "",
    "min_salary_milli": 0,
    "allow_switch_job": True,
    "allow_fee": False,
    "auto_stop_on_success": True,
}

DEFAULT_SNIPER_STATE: dict[str, Any] = {
    "last_check_at": None,
    "last_result": None,
    "last_error": None,
    "next_check_at": None,
    "next_kosong_at": None,
    "next_kosong_profession": None,
    "last_sniped_job": None,
    "checks_count": 0,
    "snipes_count": 0,
}


def _parse_hhmm(value: Any, default: str) -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        return default
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return default
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return default


def _hhmm_to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def normalize_sniper_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize and clamp Job Sniper configuration values."""
    data = raw if isinstance(raw, dict) else {}
    try:
        interval = int(data.get("interval_seconds", DEFAULT_SNIPER_CONFIG["interval_seconds"]))
    except (TypeError, ValueError):
        interval = DEFAULT_SNIPER_CONFIG["interval_seconds"]
    interval = max(10, min(3600, interval))

    try:
        min_salary = int(data.get("min_salary_milli", 0) or 0)
    except (TypeError, ValueError):
        min_salary = 0
    min_salary = max(0, min_salary)

    source_filter = str(data.get("source_filter") or "all").strip().lower()
    if source_filter not in {"all", "facility", "business"}:
        source_filter = "all"

    mode = str(data.get("mode") or DEFAULT_SNIPER_CONFIG["mode"]).strip().lower()
    if mode not in {"wait_kosong", "interval"}:
        mode = "wait_kosong"

    target_mode = str(data.get("target_mode") or "highest").strip().lower()
    if target_mode not in {"highest", "specific"}:
        target_mode = "highest"

    return {
        "enabled": bool(data.get("enabled", False)),
        "mode": mode,
        "target_mode": target_mode,
        "target_job_id": str(data.get("target_job_id") or "").strip(),
        "interval_seconds": interval,
        "schedule_enabled": bool(data.get("schedule_enabled", False)),
        "start_time": _parse_hhmm(data.get("start_time"), "00:00"),
        "end_time": _parse_hhmm(data.get("end_time"), "23:59"),
        "source_filter": source_filter,
        "skill_track_id": str(data.get("skill_track_id") or "").strip(),
        "min_salary_milli": min_salary,
        "allow_switch_job": bool(data.get("allow_switch_job", True)),
        "allow_fee": bool(data.get("allow_fee", False)),
        "auto_stop_on_success": bool(data.get("auto_stop_on_success", True)),
    }


def load_sniper_config(directory: Path) -> dict[str, Any]:
    """Load Job Sniper config from account runtime directory."""
    path = directory / SNIPER_CONFIG_FILE
    try:
        saved = json.loads(path.read_text())
    except (FileNotFoundError, OSError, ValueError):
        saved = {}
    return normalize_sniper_config(saved)


def save_sniper_config(directory: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist Job Sniper config privately."""
    normalized = normalize_sniper_config(config)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / SNIPER_CONFIG_FILE, normalized)
    return normalized


def load_sniper_state(directory: Path) -> dict[str, Any]:
    """Load Job Sniper runtime state from account runtime directory."""
    path = directory / SNIPER_STATE_FILE
    try:
        saved = json.loads(path.read_text())
    except (FileNotFoundError, OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    return {**DEFAULT_SNIPER_STATE, **saved}


def save_sniper_state(directory: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Persist Job Sniper runtime state privately."""
    merged = {**DEFAULT_SNIPER_STATE, **state}
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / SNIPER_STATE_FILE, merged)
    return merged


def is_within_schedule(config: dict[str, Any], current_dt: datetime | None = None) -> bool:
    """Return True if current WIB time falls inside the configured sniper schedule."""
    if not config.get("schedule_enabled"):
        return True
    dt = (current_dt or now()).astimezone(WIB)
    cur_min = dt.hour * 60 + dt.minute
    start_min = _hhmm_to_minutes(_parse_hhmm(config.get("start_time"), "00:00"))
    end_min = _hhmm_to_minutes(_parse_hhmm(config.get("end_time"), "23:59"))
    if start_min == end_min:
        return True
    if start_min < end_min:
        return start_min <= cur_min < end_min
    return cur_min >= start_min or cur_min < end_min


def _parse_iso_epoch(iso_str: str | None) -> float | None:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _matches_sniper_filters(
    vacancy: dict[str, Any],
    config: dict[str, Any],
    current_net_milli: int | None,
) -> bool:
    if vacancy.get("is_current_job"):
        return False
    if not vacancy.get("skill_met"):
        return False
    source_filter = config.get("source_filter", "all")
    if source_filter in {"facility", "business"} and vacancy.get("kind") != source_filter:
        return False
    track_filter = config.get("skill_track_id") or ""
    if track_filter and vacancy.get("skill_track_id") != track_filter:
        return False
    net_milli = int((vacancy.get("salary") or {}).get("net_milli") or 0)
    if net_milli < int(config.get("min_salary_milli") or 0):
        return False
    if not config.get("allow_fee") and int(vacancy.get("fee_milli") or 0) > 0:
        return False
    if current_net_milli is not None:
        if not config.get("allow_switch_job", True):
            return False
        if net_milli <= current_net_milli:
            return False
    return True


def pick_best_sniper_candidate(
    payload: dict[str, Any],
    config: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (highest_salary_eligible_vacancy, earliest_matching_kosong_vacancy)."""
    vacancies = payload.get("vacancies") if isinstance(payload.get("vacancies"), list) else []
    target_mode = config.get("target_mode", "highest")
    target_job_id = str(config.get("target_job_id") or "").strip()

    if target_mode == "specific":
        if not target_job_id:
            return None, None
        target = next(
            (v for v in vacancies if isinstance(v, dict) and v.get("id") == target_job_id),
            None,
        )
        if not target:
            return None, None
        if target.get("can_apply") and not target.get("is_full"):
            return target, None
        if target.get("is_full") and target.get("kosong_at"):
            return None, target
        return None, None

    current_job = payload.get("current_job") if isinstance(payload.get("current_job"), dict) else None
    current_net_milli = int(current_job.get("net_milli") or 0) if current_job else None

    # Vacancies are already sorted descending by salary.net_milli; re-sort defensively.
    ordered = sorted(
        (v for v in vacancies if isinstance(v, dict)),
        key=lambda v: -int((v.get("salary") or {}).get("net_milli") or 0),
    )

    best_eligible: dict[str, Any] | None = None
    upcoming_full: list[tuple[float, int, dict[str, Any]]] = []

    for v in ordered:
        if not _matches_sniper_filters(v, config, current_net_milli):
            continue
        if v.get("can_apply") and not v.get("is_full"):
            if best_eligible is None:
                best_eligible = v
            continue
        if v.get("is_full") and v.get("kosong_at"):
            epoch = _parse_iso_epoch(v.get("kosong_at"))
            if epoch is not None:
                net_milli = int((v.get("salary") or {}).get("net_milli") or 0)
                upcoming_full.append((epoch, -net_milli, v))

    next_kosong = min(upcoming_full, key=lambda item: (item[0], item[1]))[2] if upcoming_full else None
    return best_eligible, next_kosong


async def run_job_sniper_once(
    directory: Path,
    *,
    api: OjolHttpApi | None = None,
    settings: Any = None,
    force: bool = False,
    current_dt: datetime | None = None,
) -> dict[str, Any]:
    """Execute one Job Sniper evaluation and apply to the highest-paying eligible job."""
    cfg = load_sniper_config(directory)
    state = load_sniper_state(directory)
    moment = (current_dt or now()).astimezone(WIB)

    if not force and not cfg["enabled"]:
        return {
            "checked": False,
            "sniped": False,
            "message": "Job Sniper tidak aktif.",
            "config": cfg,
            "state": state,
        }

    if not force and not is_within_schedule(cfg, moment):
        msg = f"Di luar jadwal aktif ({cfg['start_time']}-{cfg['end_time']} WIB)."
        state = save_sniper_state(
            directory,
            {
                **state,
                "last_check_at": moment.isoformat(),
                "last_result": msg,
                "last_error": None,
            },
        )
        return {
            "checked": False,
            "sniped": False,
            "message": msg,
            "config": cfg,
            "state": state,
        }

    async def _execute(client: OjolHttpApi) -> dict[str, Any]:
        me = await client.fetch_game_me()
        biz_items: list[dict] | None = None
        with suppress(HttpCoreError):
            biz_items = await client.fetch_biz_vacancies()
        payload = build_job_vacancies_payload(me, biz_items=biz_items)
        best, next_kosong = pick_best_sniper_candidate(payload, cfg)

        next_kosong_at = next_kosong.get("kosong_at") if next_kosong else None
        next_kosong_prof = next_kosong.get("profession") if next_kosong else None
        next_kosong_epoch = _parse_iso_epoch(next_kosong_at)
        checks_count = int(state.get("checks_count") or 0) + 1

        if best is None:
            save_vacancies_cache(directory, payload)
            current_job = payload.get("current_job")
            if cfg.get("mode", "wait_kosong") == "wait_kosong":
                if next_kosong_at and next_kosong_epoch is not None:
                    next_check_dt = datetime.fromtimestamp(next_kosong_epoch, tz=WIB)
                    next_check_at = next_check_dt.isoformat()
                    next_check_epoch = next_kosong_epoch
                    msg = (
                        f"Menunggu jadwal kosong {next_kosong_prof} "
                        f"(hemat resource, tidak polling)."
                    )
                else:
                    next_check_dt = moment + timedelta(minutes=30)
                    next_check_at = next_check_dt.isoformat()
                    next_check_epoch = next_check_dt.timestamp()
                    if current_job and not cfg["allow_switch_job"]:
                        msg = (
                            f"Sudah bekerja sebagai {current_job.get('profession')}; "
                            "pindah kerja dinonaktifkan."
                        )
                    else:
                        msg = "Belum ada slot/jadwal kosong sesuai kriteria; cek ulang 30 menit lagi."
            else:
                interval_dt = moment + timedelta(seconds=cfg["interval_seconds"])
                if next_kosong_epoch is not None and next_kosong_epoch < interval_dt.timestamp():
                    next_check_epoch = next_kosong_epoch
                    next_check_at = datetime.fromtimestamp(next_kosong_epoch, tz=WIB).isoformat()
                else:
                    next_check_epoch = interval_dt.timestamp()
                    next_check_at = interval_dt.isoformat()
                if current_job and not cfg["allow_switch_job"]:
                    msg = f"Sudah bekerja sebagai {current_job.get('profession')}; pindah kerja dinonaktifkan."
                elif next_kosong:
                    msg = (
                        f"Belum ada slot kosong sesuai kriteria. "
                        f"Slot berikutnya: {next_kosong_prof}."
                    )
                else:
                    msg = "Belum ada lowongan sesuai skill & kriteria yang tersedia."
            updated_state = save_sniper_state(
                directory,
                {
                    **state,
                    "last_check_at": moment.isoformat(),
                    "last_result": msg,
                    "last_error": None,
                    "next_check_at": next_check_at,
                    "next_kosong_at": next_kosong_at,
                    "next_kosong_profession": next_kosong_prof,
                    "checks_count": checks_count,
                },
            )
            return {
                "checked": True,
                "sniped": False,
                "message": msg,
                "next_check_epoch": next_check_epoch,
                "next_kosong_epoch": next_kosong_epoch,
                "config": cfg,
                "state": updated_state,
            }

        has_current = bool(payload.get("current_job"))
        if best["kind"] == "facility":
            result = await client.apply_facility_job(
                best["profession"],
                best["facility_id"],
                switch_job=has_current,
            )
        else:
            result = await client.apply_biz_vacancy(
                best["vacancy_id"],
                switch_job=has_current,
            )

        with suppress(HttpCoreError):
            await client.fetch_game_me()
        invalidate_vacancies_cache(directory)

        net_milli = int((best.get("salary") or {}).get("net_milli") or 0)
        net_koin = f"{net_milli / 1000:g}"
        msg = (
            f"🎯 Job Sniper berhasil melamar {best['profession']} "
            f"di {best['place_name']} ({net_koin} koin/hari)."
        )
        tidur = result.get("tidur") if isinstance(result, dict) else None
        if tidur:
            msg += f" Jam tidur pindah ke {tidur}."

        updated_cfg = cfg
        if cfg["auto_stop_on_success"] and cfg["enabled"]:
            updated_cfg = save_sniper_config(directory, {**cfg, "enabled": False})

        updated_state = save_sniper_state(
            directory,
            {
                **state,
                "last_check_at": moment.isoformat(),
                "last_result": msg,
                "last_error": None,
                "next_check_at": None,
                "next_kosong_at": next_kosong_at,
                "next_kosong_profession": next_kosong_prof,
                "last_sniped_job": {
                    "id": best["id"],
                    "profession": best["profession"],
                    "place_name": best["place_name"],
                    "net_milli": net_milli,
                    "sniped_at": moment.isoformat(),
                },
                "checks_count": checks_count,
                "snipes_count": int(state.get("snipes_count") or 0) + 1,
            },
        )
        if settings is not None:
            with suppress(Exception):
                queue_notice(settings, msg)

        return {
            "checked": True,
            "sniped": True,
            "message": msg,
            "job": best,
            "result": result,
            "next_kosong_epoch": next_kosong_epoch,
            "config": updated_cfg,
            "state": updated_state,
        }

    try:
        if api is not None:
            return await _execute(api)
        async with OjolHttpApi(directory) as client:
            return await _execute(client)
    except Exception as exc:
        err_msg = str(exc) or type(exc).__name__
        updated_state = save_sniper_state(
            directory,
            {
                **state,
                "last_check_at": moment.isoformat(),
                "last_error": err_msg,
                "checks_count": int(state.get("checks_count") or 0) + 1,
            },
        )
        return {
            "checked": True,
            "sniped": False,
            "message": f"Gagal memeriksa lowongan: {err_msg}",
            "error": err_msg,
            "config": cfg,
            "state": updated_state,
        }
