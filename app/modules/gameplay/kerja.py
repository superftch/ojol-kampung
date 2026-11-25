"""Automated work flows for office/facility/business jobs (/api/kantor) and general jobs (/api/kerja-malam)."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.storage import write_private
from app.integrations.kampung.http_api import HttpCoreError, timestamp
from app.modules.worker.settings import auto_flags

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")
MIN_STEP_SECONDS = 1.2
KERJA_STATUS_FILE = "kerja-status.json"


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


def _wib_minutes(server_now_raw: str | None) -> int:
    if isinstance(server_now_raw, str):
        try:
            dt = timestamp(server_now_raw).astimezone(WIB)
            return dt.hour * 60 + dt.minute
        except (ValueError, TypeError):
            pass
    dt = datetime.now(WIB)
    return dt.hour * 60 + dt.minute


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
        c.kerja_retry_at = time.monotonic() + 120
        return False
    except Exception:
        c.kerja_retry_at = time.monotonic() + 120
        return False

    kantor = (res or {}).get("kantor") if isinstance(res, dict) else None
    if not isinstance(kantor, dict):
        c.kerja_retry_at = time.monotonic() + 300
        return False

    if kantor.get("libur") or not kantor.get("buka"):
        _save_kerja_status(
            c.settings.runtime_dir,
            {
                "kind": "kantor",
                "facility": kantor.get("nama"),
                "profession": (kantor.get("saya") or {}).get("profesi"),
                "buka": False,
                "libur": bool(kantor.get("libur")),
                "state": "Libur" if kantor.get("libur") else "Tutup",
                "last_message": kantor.get("alasan") or "Kantor sedang tutup/libur",
            },
        )
        c.kerja_retry_at = time.monotonic() + 300
        return False

    now_min = _wib_minutes(kantor.get("sekarang"))

    # 1. Join active group activity (bersama)
    for item in kantor.get("bersama") or []:
        if not isinstance(item, dict) or item.get("ikut"):
            continue
        dari, sampai = item.get("dari"), item.get("sampai")
        if isinstance(dari, int) and isinstance(sampai, int) and dari <= now_min < sampai:
            wait_s = min(float(kantor.get("bersamaDetik") or 15), 16.0)
            await asyncio.sleep(wait_s)
            try:
                out = await c.ui.kantor_action("bersama", id=item["id"])
                if isinstance(out, dict) and out.get("ok"):
                    c.record_event("kerja", f"Ikut {item.get('nama', 'kegiatan kantor')} (+{out.get('poin', 0)} poin)")
                c.kerja_retry_at = time.monotonic() + 3
                return True
            except HttpCoreError as exc:
                if exc.category == "auth":
                    raise
                break

    # 2. Handle active office incident (kejadian)
    for item in kantor.get("kejadian") or []:
        if not isinstance(item, dict) or item.get("oleh") is not None:
            continue
        dari, sampai = item.get("dari"), item.get("sampai")
        if isinstance(dari, int) and isinstance(sampai, int) and dari <= now_min < sampai:
            wait_s = min(float(item.get("detik") or 3), 6.0)
            await asyncio.sleep(wait_s)
            try:
                out = await c.ui.kantor_action("kejadian", idx=item["idx"])
                if isinstance(out, dict) and out.get("ok"):
                    c.record_event("kerja", f"{item.get('judul', 'Kejadian kantor')} (+{out.get('poin', 0)} poin)")
                c.kerja_retry_at = time.monotonic() + 3
                return True
            except HttpCoreError as exc:
                if exc.category == "auth":
                    raise
                break

    # 3. Check if both daily paket and full-time poin target are already complete
    kerja = kantor.get("kerja") or {}
    paket = kantor.get("paket") or {}
    paket_done = not paket.get("berbayar") or int(paket.get("lunas") or 0) >= int(paket.get("perHari") or 0)
    poin_done = kerja.get("status") == "tercapai" or int(kerja.get("poin") or 0) >= int(kerja.get("target") or 30)
    status_snapshot = {
        "kind": "kantor",
        "facility": kantor.get("nama"),
        "profession": (kantor.get("saya") or {}).get("profesi"),
        "buka": True,
        "libur": False,
        "fase": kantor.get("fase"),
        "lunas": int(paket.get("lunas") or 0),
        "per_hari": int(paket.get("perHari") or 3),
        "menuju": int(paket.get("menuju") or 0),
        "per_paket": int(paket.get("perPaket") or 5),
        "poin": int(kerja.get("poin") or 0),
        "target": int(kerja.get("target") or 30),
        "state": "Selesai hari ini" if (paket_done and poin_done) else "Aktif",
    }
    _save_kerja_status(c.settings.runtime_dir, status_snapshot)
    if paket_done and poin_done:
        c.kerja_retry_at = time.monotonic() + 1800
        return False

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
                c.kerja_retry_at = time.monotonic() + 300
                return False
            c.kerja_retry_at = time.monotonic() + 60
            return False

    if not isinstance(urusan, dict) or not urusan.get("id"):
        c.kerja_retry_at = time.monotonic() + 60
        return False

    answers = solve_urusan_answers(urusan)
    wait_s = urusan_wait_seconds(urusan)
    if wait_s > 0:
        await asyncio.sleep(wait_s)

    try:
        done = await c.ui.kantor_action("urusan-selesai", id=urusan["id"], jawab=answers)
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.kerja_retry_at = time.monotonic() + 15
        return False

    if isinstance(done, dict) and done.get("ok"):
        paket_res = done.get("paket")
        if isinstance(paket_res, dict):
            msg = (
                f"Tugas kantor ke-{paket_res.get('nomor', '?')} lunas "
                f"(+{int(paket_res.get('rewardMilli') or 0) / 1000:g} koin)"
            )
            c.record_event("kerja", msg)
            status_snapshot["lunas"] = int(paket_res.get("nomor") or status_snapshot["lunas"])
            status_snapshot["menuju"] = 0
        else:
            msg = f"Urusan selesai: {urusan.get('judul', 'Tugas')} (+{done.get('poin', 0)} poin)"
            c.record_event("kerja", msg)
            status_snapshot["menuju"] = min(
                status_snapshot["menuju"] + 1, status_snapshot["per_paket"]
            )
        status_snapshot["poin"] = status_snapshot["poin"] + int(done.get("poin") or 0)
        status_snapshot["last_message"] = msg
        _save_kerja_status(c.settings.runtime_dir, status_snapshot)
    jeda = float(kantor.get("jedaUrusanDetik") or 3)
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

    return await _run_kantor(c)
