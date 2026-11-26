"""Automated work flows for office/facility/business jobs (/api/kantor) and general jobs (/api/kerja-malam)."""

import asyncio
import json
import logging
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.storage import write_private
from app.integrations.kampung.http_api import HttpCoreError, timestamp
from app.modules.worker.settings import auto_flags

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
MIN_STEP_SECONDS = 1.2
KERJA_STATUS_FILE = "kerja-status.json"


def _load_kerja_status(runtime_dir) -> dict:
    try:
        raw = (runtime_dir / KERJA_STATUS_FILE).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_kerja_status(runtime_dir, payload: dict) -> None:
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_private(
            runtime_dir / KERJA_STATUS_FILE,
            {**payload, "updated_at": datetime.now(UTC).isoformat()},
        )
    except OSError:
        pass


def fnv1a_32(text: str) -> int:
    """Compute unsigned 32-bit FNV-1a hash matching KampungSebelah client module 860242."""
    value = 0x811C9DC5
    for ch in text:
        value ^= ord(ch)
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def solve_urusan_answers(urusan: dict) -> list[int | None]:
    """Resolve deterministic choice indices for each step of a /api/kantor urusan."""
    uid = str(urusan.get("id") or "")
    answers: list[int | None] = []
    for step_idx, step in enumerate(urusan.get("langkah") or []):
        if not isinstance(step, dict):
            answers.append(None)
            continue
        choices = step.get("pilihan")
        target = step.get("kunci")
        if isinstance(choices, list) and target is not None:
            matched = next(
                (
                    idx
                    for idx in range(len(choices))
                    if fnv1a_32(f"{uid}:{step_idx}:{idx}") == target
                ),
                0,
            )
            answers.append(matched)
        else:
            answers.append(None)
    return answers


def urusan_wait_seconds(urusan: dict, now_dt: datetime | None = None) -> float:
    """Calculate remaining wait seconds required before submitting urusan-selesai."""
    total = 0.0
    for step in urusan.get("langkah") or []:
        if not isinstance(step, dict):
            continue
        if step.get("aksi") == "proses":
            total += float(step.get("detik") or 2) * 0.8
        total += MIN_STEP_SECONDS
    required = total + 0.5
    mulai_raw = urusan.get("mulai")
    if isinstance(mulai_raw, str):
        try:
            started = timestamp(mulai_raw)
            current = now_dt or datetime.now(UTC)
            elapsed = max(0.0, (current - started).total_seconds())
            return max(0.0, min(required - elapsed, 20.0))
        except (ValueError, TypeError):
            pass
    return min(required, 20.0)


def _jitter(low: float = 2.0, high: float = 4.0) -> float:
    low = max(2.0, low)
    high = max(low, high)
    return random.uniform(low, high)  # noqa: S311 - timing only


def _wib_now(server_now_raw: str | None = None) -> datetime:
    if isinstance(server_now_raw, str):
        try:
            return timestamp(server_now_raw).astimezone(WIB)
        except (ValueError, TypeError):
            pass
    return datetime.now(WIB)


def _wib_minutes(server_now_raw: str | None) -> int:
    dt = _wib_now(server_now_raw)
    return dt.hour * 60 + dt.minute


def _parse_hhmm(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, str) or ":" not in raw:
        return None
    parts = raw.strip().split(":", 1)
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _at_wib_time(base_day: datetime, hhmm: tuple[int, int]) -> datetime:
    return base_day.replace(hour=hhmm[0], minute=hhmm[1], second=0, microsecond=0)


def _seconds_until_next_open(
    jam: dict | None,
    server_now_raw: str | None = None,
    *,
    force_tomorrow: bool = False,
    libur: bool = False,
) -> float | None:
    """Calculate seconds until the next office opening time in WIB based on `jam`."""
    now_wib = _wib_now(server_now_raw)
    jam = jam if isinstance(jam, dict) else {}
    open_hm = _parse_hhmm(jam.get("from"))
    close_hm = _parse_hhmm(jam.get("to"))

    if open_hm is None:
        if force_tomorrow or libur:
            next_day = (now_wib + timedelta(days=1)).replace(
                hour=0, minute=0, second=5, microsecond=0
            )
            return max(60.0, (next_day - now_wib).total_seconds())
        return None

    tomorrow = now_wib + timedelta(days=1)
    if force_tomorrow or libur:
        target = _at_wib_time(tomorrow, open_hm)
        return max(60.0, (target - now_wib).total_seconds())

    open_dt = _at_wib_time(now_wib, open_hm)
    close_dt = _at_wib_time(now_wib, close_hm) if close_hm else None

    if close_dt is not None and open_hm < close_hm:
        if now_wib < open_dt:
            return max(10.0, (open_dt - now_wib).total_seconds())
        ist = jam.get("istirahat")
        if isinstance(ist, dict):
            ist_from = _parse_hhmm(ist.get("from"))
            ist_to = _parse_hhmm(ist.get("to"))
            if ist_from and ist_to:
                ist_start = _at_wib_time(now_wib, ist_from)
                ist_end = _at_wib_time(now_wib, ist_to)
                if ist_start <= now_wib < ist_end:
                    return max(10.0, (ist_end - now_wib).total_seconds())
        if now_wib >= close_dt:
            return max(60.0, (_at_wib_time(tomorrow, open_hm) - now_wib).total_seconds())
        return None

    if close_dt is not None and open_hm > close_hm:
        if close_dt <= now_wib < open_dt:
            return max(10.0, (open_dt - now_wib).total_seconds())
        return None

    return None


def _pause_until_tomorrow(
    c, jam: dict | None = None, server_now_raw: str | None = None
) -> None:
    wait_s = _seconds_until_next_open(jam, server_now_raw, force_tomorrow=True) or 3600.0
    c.kerja_retry_at = time.monotonic() + wait_s + _jitter(5.0, 30.0)
    c.record_event(
        "kerja",
        "Target kantor hari ini maksimal; Auto Kantor dijeda dan lanjut otomatis besok saat kantor buka.",
    )


def _is_kantor_job(job: dict) -> bool:
    if job.get("kantor") is not None:
        return True
    return job.get("employerType") in {"PUBLIC", "BUSINESS"}


def can_run_kerja(c) -> bool:
    """Return True only when Auto Ojol is off, not currently ngojol, and account has a kantor job."""
    flags = auto_flags(c.settings.runtime_dir)
    if not flags.get("kerja", False):
        return False
    if flags.get("ojol"):
        return False
    state = getattr(c, "observed_state", None)
    if state is None or state.phase != "idle" or state.trip or state.trip_id:
        return False
    return isinstance(state.job, dict) and _is_kantor_job(state.job)


async def _run_kantor(c) -> bool:
    try:
        res = await c.ui.kantor_action("detak")
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.kerja_retry_at = time.monotonic() + 120 + _jitter(2.0, 15.0)
        return False
    except Exception:
        c.kerja_retry_at = time.monotonic() + 120 + _jitter(2.0, 15.0)
        return False

    kantor = (res or {}).get("kantor") if isinstance(res, dict) else None
    if not isinstance(kantor, dict):
        c.kerja_retry_at = time.monotonic() + 300 + _jitter(2.0, 20.0)
        return False

    jam = kantor.get("jam") if isinstance(kantor.get("jam"), dict) else (
        (getattr(c.observed_state, "job", None) or {}).get("jam")
    )

    if kantor.get("libur") or not kantor.get("buka"):
        is_libur = bool(kantor.get("libur"))
        _save_kerja_status(
            c.settings.runtime_dir,
            {
                "kind": "kantor",
                "facility": kantor.get("nama"),
                "profession": (kantor.get("saya") or {}).get("profesi"),
                "buka": False,
                "libur": is_libur,
                "jam": jam,
                "state": "Libur" if is_libur else "Tutup",
                "last_message": kantor.get("alasan") or "Kantor sedang tutup/libur",
            },
        )
        wait_open = _seconds_until_next_open(
            jam, kantor.get("sekarang"), libur=is_libur
        )
        c.kerja_retry_at = time.monotonic() + (wait_open if wait_open is not None else 300.0) + _jitter(2.0, 15.0)
        return False

    # 1. Check if both daily paket and full-time poin target are already complete -> auto-stop
    kerja = kantor.get("kerja") or {}
    paket = kantor.get("paket") or {}
    per_hari = int(paket.get("perHari") or 3)
    per_paket = int(paket.get("perPaket") or 5)
    target_poin = int(kerja.get("target") or 30)
    raw_lunas = int(paket.get("lunas") or 0)
    raw_poin = int(kerja.get("poin") or 0)
    lunas = min(raw_lunas, per_hari)
    poin = min(raw_poin, target_poin)
    paket_done = not paket.get("berbayar") or raw_lunas >= int(paket.get("perHari") or 0)
    poin_done = kerja.get("status") == "tercapai" or raw_poin >= target_poin
    today_wib = _wib_now(kantor.get("sekarang")).date().isoformat()
    status_snapshot = {
        "kind": "kantor",
        "facility": kantor.get("nama"),
        "profession": (kantor.get("saya") or {}).get("profesi"),
        "buka": True,
        "libur": False,
        "fase": kantor.get("fase"),
        "jam": jam,
        "lunas": lunas,
        "per_hari": per_hari,
        "menuju": 0 if paket_done else min(int(paket.get("menuju") or 0), per_paket),
        "per_paket": per_paket,
        "poin": poin,
        "target": target_poin,
        "state": "Selesai hari ini" if (paket_done and poin_done) else "Aktif",
    }
    if paket_done and poin_done:
        status_snapshot["completed_date"] = today_wib
        status_snapshot["last_message"] = "Target maksimal tercapai; lanjut otomatis besok saat kantor buka"
    _save_kerja_status(c.settings.runtime_dir, status_snapshot)
    if paket_done and poin_done:
        _pause_until_tomorrow(c, jam, kantor.get("sekarang"))
        return False

    now_min = _wib_minutes(kantor.get("sekarang"))

    # 2. Join active group activity (bersama)
    for item in kantor.get("bersama") or []:
        if not isinstance(item, dict) or item.get("ikut"):
            continue
        dari, sampai = item.get("dari"), item.get("sampai")
        if isinstance(dari, int) and isinstance(sampai, int) and dari <= now_min < sampai:
            wait_s = min(float(kantor.get("bersamaDetik") or 15), 16.0) + _jitter(2.0, 4.0)
            await asyncio.sleep(wait_s)
            try:
                out = await c.ui.kantor_action("bersama", id=item["id"])
                if isinstance(out, dict) and out.get("ok"):
                    c.record_event("kerja", f"Ikut {item.get('nama', 'kegiatan kantor')} (+{out.get('poin', 0)} poin)")
                c.kerja_retry_at = time.monotonic() + 3 + _jitter(2.0, 4.0)
                return True
            except HttpCoreError as exc:
                if exc.category == "auth":
                    raise
                break

    # 3. Handle active office incident (kejadian)
    for item in kantor.get("kejadian") or []:
        if not isinstance(item, dict) or item.get("oleh") is not None:
            continue
        dari, sampai = item.get("dari"), item.get("sampai")
        if isinstance(dari, int) and isinstance(sampai, int) and dari <= now_min < sampai:
            wait_s = min(float(item.get("detik") or 3), 6.0) + _jitter(2.0, 3.5)
            await asyncio.sleep(wait_s)
            try:
                out = await c.ui.kantor_action("kejadian", idx=item["idx"])
                if isinstance(out, dict) and out.get("ok"):
                    c.record_event("kerja", f"{item.get('judul', 'Kejadian kantor')} (+{out.get('poin', 0)} poin)")
                c.kerja_retry_at = time.monotonic() + 3 + _jitter(2.0, 4.0)
                return True
            except HttpCoreError as exc:
                if exc.category == "auth":
                    raise
                break

    # 4. Serve active or new urusan
    urusan = kantor.get("urusan")
    if not isinstance(urusan, dict):
        try:
            urusan = await c.ui.kantor_action("urusan-mulai", requestId=str(uuid4()))
        except HttpCoreError as exc:
            if exc.category == "auth":
                raise
            if "428" in str(exc):
                # request() sudah mencoba memecahkan gambar angka via bank; sampai di sini
                # berarti gagal (atau server minta Turnstile) -> manusia di game.
                status_snapshot["state"] = "Perlu verifikasi"
                status_snapshot["last_message"] = (
                    "Cek manusia otomatis gagal; selesaikan verifikasi di game"
                )
                _save_kerja_status(c.settings.runtime_dir, status_snapshot)
                c.record_event("kerja", "Kerja tertahan: verifikasi manusia belum terpecahkan")
                c.kerja_retry_at = time.monotonic() + 300 + _jitter(2.0, 25.0)
                return False
            c.kerja_retry_at = time.monotonic() + 60 + _jitter(2.0, 15.0)
            return False

    if not isinstance(urusan, dict) or not urusan.get("id"):
        c.kerja_retry_at = time.monotonic() + 60 + _jitter(2.0, 15.0)
        return False

    answers = solve_urusan_answers(urusan)
    wait_s = urusan_wait_seconds(urusan)
    if wait_s > 0:
        await asyncio.sleep(min(wait_s + _jitter(2.0, 3.8), 24.0))

    try:
        done = await c.ui.kantor_action("urusan-selesai", id=urusan["id"], jawab=answers)
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.kerja_retry_at = time.monotonic() + 15 + _jitter(2.0, 5.0)
        return False

    if isinstance(done, dict) and done.get("ok"):
        paket_res = done.get("paket")
        if isinstance(paket_res, dict):
            msg = (
                f"Tugas kantor ke-{paket_res.get('nomor', '?')} lunas "
                f"(+{int(paket_res.get('rewardMilli') or 0) / 1000:g} koin)"
            )
            c.record_event("kerja", msg)
            status_snapshot["lunas"] = min(
                int(paket_res.get("nomor") or status_snapshot["lunas"]), per_hari
            )
            status_snapshot["menuju"] = 0
        else:
            msg = f"Urusan selesai: {urusan.get('judul', 'Tugas')} (+{done.get('poin', 0)} poin)"
            c.record_event("kerja", msg)
            status_snapshot["menuju"] = (
                0
                if status_snapshot["lunas"] >= per_hari
                else min(status_snapshot["menuju"] + 1, per_paket)
            )
        status_snapshot["poin"] = min(
            status_snapshot["poin"] + int(done.get("poin") or 0), target_poin
        )
        reached_max = status_snapshot["poin"] >= target_poin and (
            not paket.get("berbayar") or status_snapshot["lunas"] >= per_hari
        )
        if reached_max:
            status_snapshot["state"] = "Selesai hari ini"
            status_snapshot["completed_date"] = today_wib
            status_snapshot["last_message"] = "Target maksimal tercapai; lanjut otomatis besok saat kantor buka"
        else:
            status_snapshot["last_message"] = msg
        _save_kerja_status(c.settings.runtime_dir, status_snapshot)
        if reached_max:
            _pause_until_tomorrow(c, jam, kantor.get("sekarang"))
            return True
    jeda = float(kantor.get("jedaUrusanDetik") or 3) + _jitter(2.0, 4.5)
    c.kerja_retry_at = time.monotonic() + jeda
    return True


async def _run_kerja_malam(c) -> bool:
    try:
        status = await c.ui.kerja_malam_status()
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.kerja_retry_at = time.monotonic() + 120
        return False
    except Exception:
        c.kerja_retry_at = time.monotonic() + 120
        return False

    if not isinstance(status, dict):
        c.kerja_retry_at = time.monotonic() + 300
        return False

    # Complete pending cleaning chore if ready
    bersihku = status.get("bersihku")
    if isinstance(bersihku, dict) and bersihku.get("selesaiAt"):
        try:
            selesai_at = timestamp(bersihku["selesaiAt"])
            now_dt = datetime.now(UTC)
            if selesai_at <= now_dt:
                res = await c.ui.kerja_malam_action("bersih-selesai", tangkap=5)
                if isinstance(res, dict) and not res.get("gagal"):
                    c.record_event("kerja", "Selesai membersihkan rumah warga")
                c.kerja_retry_at = time.monotonic() + 5
                return True
            remaining = min((selesai_at - now_dt).total_seconds(), 60.0)
            c.kerja_retry_at = time.monotonic() + max(remaining, 2.0)
            return False
        except (ValueError, TypeError, HttpCoreError) as exc:
            if isinstance(exc, HttpCoreError) and exc.category == "auth":
                raise

    # Turn on dead street lamps during night shift
    if status.get("enabled") and status.get("buka"):
        lamps = status.get("lampuMati") or []
        if lamps:
            try:
                res = await c.ui.kerja_malam_action("lampu", key=lamps[0])
                upah = int((res or {}).get("upahMilli") or 0) / 1000
                c.record_event("kerja", f"Nyalakan lampu jalan (+{upah:g} koin)")
                c.kerja_retry_at = time.monotonic() + 3
                return True
            except HttpCoreError as exc:
                if exc.category == "auth":
                    raise
                c.kerja_retry_at = time.monotonic() + 30
                return False

    c.kerja_retry_at = time.monotonic() + 300
    return False


async def run_kerja(c) -> bool:
    """Execute one automated kantor work step if eligible."""
    if not hasattr(c.ui, "kantor_action"):
        return False
    if not can_run_kerja(c):
        return False
    if time.monotonic() < getattr(c, "kerja_retry_at", 0):
        return False

    saved = _load_kerja_status(c.settings.runtime_dir)
    job = getattr(c.observed_state, "job", None) or {}
    jam = job.get("jam") if isinstance(job.get("jam"), dict) else saved.get("jam")
    if (
        saved.get("state") == "Selesai hari ini"
        and saved.get("completed_date") == _wib_now().date().isoformat()
    ):
        wait_s = _seconds_until_next_open(jam, force_tomorrow=True) or 3600.0
        c.kerja_retry_at = time.monotonic() + wait_s + _jitter(5.0, 30.0)
        return False

    wait_open = _seconds_until_next_open(jam)
    if wait_open is not None and wait_open > 5.0:
        c.kerja_retry_at = time.monotonic() + wait_open + _jitter(2.0, 10.0)
        return False

    c.stage = "kerja.kantor"
    return await _run_kantor(c)
