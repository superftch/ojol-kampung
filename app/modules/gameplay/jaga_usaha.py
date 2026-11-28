"""Drive one Jaga Usaha session per account through the existing worker."""

import asyncio
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field

from app.core.exceptions import HttpCoreError
from app.core.models import Model, now
from app.core.storage import write_private
from app.integrations.kampung.game_parsers import ShopClosed
from app.modules.gameplay.kerja import is_work_active_now
from app.modules.ledger.finance import WIB
from app.modules.notifications.service import redact
from app.modules.worker.jaga_planner import (
    Business,
    listed_businesses,
    plan_businesses,
    read_business,
    shop_block,
    whole,
)
from app.modules.worker.jaga_settings import (
    JAGA_STATUS_FILE,
    BusinessId,
    JagaSettings,
    load_jaga_settings,
)
from app.modules.worker.planner import is_sleeping
from app.modules.worker.settings import auto_flags

RECHECK = timedelta(seconds=10)
SCAN_PAUSE_SECONDS = 2
REFRESH = timedelta(minutes=15)
SESSION_EXPIRY = timedelta(minutes=3)  # Client bundle jaga.hidup_menit


class Session(Model):
    business_id: BusinessId
    name: str
    day: date
    started_at: AwareDatetime
    target: int
    minutes: int
    initial_minutes: int
    phase: Literal["starting", "active", "closing"] = "starting"
    interval: int = 0
    next_at: AwareDatetime | None = None
    last_confirmed: AwareDatetime | None = None
    end_reason: str = ""


class ScanProgress(Model):
    checked: int = 0
    total: int | None = None
    business: str | None = None


class JagaState(Model):
    day: date | None = None
    state: str = "Menunggu"
    message: str = ""
    updated_at: AwareDatetime | None = None
    scan: ScanProgress | None = None
    session: Session | None = None
    businesses: list[Business] = Field(default_factory=list)
    used_seconds: float = 0
    budget_seconds: float = 0
    first_business: str | None = None
    last_guarded: dict[str, AwareDatetime] = Field(default_factory=dict)
    refresh_at: AwareDatetime | None = None
    retry_at: AwareDatetime | None = None
    verification: bool = False
    settings: JagaSettings | None = None


def active_window(settings: JagaSettings, at: datetime) -> bool:
    clock = at.astimezone(WIB).strftime("%H:%M")
    start, end = settings.active_start, settings.active_end
    if start < end:
        return start <= clock < end
    return clock >= start or clock < end


def status_values(payload: object) -> tuple[bool, int | None]:
    if not isinstance(payload, dict) or not isinstance(active := payload.get("jaga"), bool):
        raise ValueError("Respons status jaga belum dapat dibaca.")
    minutes = whole(payload.get("menit"))
    return active, minutes if minutes is not None and minutes >= 0 else None


class JagaWorker:
    def __init__(self, directory: Path):
        self.path = directory / JAGA_STATUS_FILE
        try:
            self.data = JagaState.model_validate_json(self.path.read_text())
        except FileNotFoundError:
            self.data = JagaState()
        self.recover = self.data.session is not None
        self.scan_pending: dict[str, dict] | None = None
        self.scanned: list[Business] = []

    def update(self, state: str, message: str = "") -> None:
        self.data.state = state
        self.data.message = redact(message)
        self.save()

    def save(self) -> None:
        self.data.updated_at = now()
        write_private(self.path, self.data.model_dump(mode="json"))

    def reason(self, c, flags: dict, settings: JagaSettings, at: datetime) -> str:
        if not flags["jaga"]:
            return "Auto Jaga nonaktif."
        if flags["ojol"] is not False:
            return "Menunggu Auto Ojol dinonaktifkan."
        snap = c.observed_state
        if is_sleeping(snap):
            return "Karakter sedang tidur."
        if snap.phase != "idle" or snap.trip or snap.trip_id:
            return "Menunggu aktivitas akun selesai."
        if is_work_active_now(c.settings.runtime_dir, snap, flags=flags):
            return "Menunggu jam kerja selesai."
        if any(
            flags.get(need) and level < c.settings.threshold_for(need)
            for need, level in snap.needs.items()
        ):
            return "Menunggu kebutuhan karakter terpenuhi."
        if not active_window(settings, at):
            return "Di luar jam aktif Jaga Usaha."
        return ""

    async def before_waits(self, c, flags: dict, *, maintenance: bool) -> bool:
        """Handle stop conditions that precede the normal snapshot and feature dispatch."""
        if not flags["jaga"] and self.data.verification and self.data.session is None:
            self.data.verification = False
            self.update("Nonaktif")
        if maintenance:
            reason = "Game sedang dalam pemeliharaan."
        elif not flags["jaga"]:
            reason = "Auto Jaga nonaktif."
        elif flags["ojol"] is not False:
            reason = "Menunggu Auto Ojol dinonaktifkan."
        else:
            return False
        if self.data.session:
            await self.close(c, reason)
            if self.data.session:
                await c.wait(RECHECK.total_seconds())
                return True
        elif flags["jaga"] and not self.data.verification and self.data.message != reason:
            self.update("Menunggu", reason)
        return False

    async def observe(self, c, flags: dict) -> bool:
        """Keep an active or unresolved session ahead of other game activities."""
        if not self.data.session:
            if flags["jaga"] and not self.data.verification:
                try:
                    settings = load_jaga_settings(self.path.parent)
                    reason = self.reason(c, flags, settings, now())
                except ValueError:
                    reason = "Pengaturan Auto Jaga tidak valid."
                if reason and self.data.message != reason:
                    self.update("Menunggu", reason)
            return False
        at = now()
        try:
            settings = load_jaga_settings(self.path.parent)
            reason = self.reason(c, flags, settings, at)
        except ValueError:
            reason = "Pengaturan Auto Jaga tidak valid."
            settings = self.data.settings or JagaSettings()
        session = self.data.session
        if session.day != at.astimezone(WIB).date():
            reason = "Hari WIB berganti."
        elapsed = max(0, (at - session.started_at).total_seconds())
        if self.data.used_seconds + elapsed >= settings.budget_jam * 3600:
            reason = reason or "Anggaran harian tercapai."
        if self.data.settings != settings:
            reason = reason or "Pengaturan Auto Jaga berubah."
        if reason:
            await self.close(c, reason)
        elif (
            self.recover
            or session.phase != "active"
            or session.last_confirmed is None
            or at - session.last_confirmed >= SESSION_EXPIRY
        ):
            await self.reconcile(c, resume=True)
        elif session.next_at is not None and at >= session.next_at:
            await self.heartbeat(c)
        if self.data.session:
            midnight = datetime.combine(session.day + timedelta(days=1), time.min, tzinfo=WIB)
            wait = RECHECK.total_seconds()
            if self.data.session.phase == "active" and self.data.session.next_at:
                wait = min(
                    wait,
                    max(0, (self.data.session.next_at - now()).total_seconds()),
                    max(0, settings.budget_jam * 3600 - self.data.used_seconds - elapsed),
                    max(0, (midnight - now()).total_seconds()),
                )
            await c.wait(wait)
        return True

    async def start_step(self, c, flags: dict) -> bool:
        at = now()
        try:
            settings = load_jaga_settings(self.path.parent)
        except ValueError:
            self.update("Gangguan", "Pengaturan Auto Jaga tidak valid.")
            return False
        if self.data.verification:
            return False
        reason = self.reason(c, flags, settings, at)
        if reason:
            if self.data.message != reason:
                self.update("Menunggu", reason)
            return False
        day = at.astimezone(WIB).date()
        if self.data.day != day:
            self.data.day = day
            self.data.used_seconds = 0
            self.data.first_business = None
            for business in self.data.businesses:
                business.minutes = None
            self.data.retry_at = None
            self.data.refresh_at = None
            self.scan_pending = None
            self.data.last_guarded = {
                key: value
                for key, value in self.data.last_guarded.items()
                if at - value < timedelta(days=30)
            }
        settings_changed = self.data.settings != settings
        if settings_changed:
            self.data.settings = settings
            self.data.retry_at = None
            self.data.refresh_at = None
            self.scan_pending = None
        self.data.budget_seconds = settings.budget_jam * 3600
        if self.data.used_seconds >= self.data.budget_seconds:
            if self.data.state != "Selesai hari ini" or settings_changed:
                self.update("Selesai hari ini", "Anggaran harian tercapai.")
            return False
        if self.data.retry_at and at < self.data.retry_at:
            return False
        try:
            if self.data.refresh_at is None or at >= self.data.refresh_at:
                await self.scan_one(c, settings, day)
                return True
            await self.start_next(c, settings, day)
        except (HttpCoreError, ValueError) as exc:
            if isinstance(exc, HttpCoreError) and exc.category == "auth":
                raise
            self.scan_pending = None
            self.data.scan = None
            self.data.retry_at = now() + REFRESH
            self.update("Gangguan", str(exc))
        return False

    async def scan_one(self, c, settings: JagaSettings, day: date) -> None:
        if self.scan_pending is None:
            self.data.scan = ScanProgress()
            self.update("Menyusun rencana", "Mengambil daftar usaha dari game.")
            self.scan_pending = listed_businesses(await c.ui.businesses_semua())
            self.scanned = []
        if self.scan_pending:
            key = next(iter(self.scan_pending))
            item = self.scan_pending.pop(key)
            name = item.get("plang") or item.get("jenis")
            progress = ScanProgress(
                checked=len(self.scanned),
                total=len(self.scanned) + len(self.scan_pending) + 1,
                business=redact(name[:120]) if isinstance(name, str) else None,
            )
            self.data.scan = progress
            self.update("Menyusun rencana", "Membaca detail usaha.")
            try:
                shop = await c.ui.shop_info(key)
            except HttpCoreError as exc:
                if exc.category == "auth":
                    raise
                business = read_business(item, None, None)
                business.unavailable = (
                    "Usaha tutup."
                    if isinstance(exc, ShopClosed)
                    else "Detail usaha tidak tersedia."
                )
            else:
                c.check_cancel()
                self.update("Menyusun rencana", "Membaca laporan usaha.")
                try:
                    report = await c.ui.business_report(key)
                except HttpCoreError as exc:
                    if exc.category == "auth":
                        raise
                    report = None
                business = read_business(item, shop, report)
            self.scanned.append(business)
            progress.checked = len(self.scanned)
            progress.business = None
            if self.scan_pending:
                self.update("Menyusun rencana", "Menunggu pemeriksaan usaha berikutnya.")
                return
        if not self.scan_pending:
            previous = {business.id: business.minutes for business in self.data.businesses}
            self.data.businesses = plan_businesses(
                self.scanned, settings, day, self.data.last_guarded, str(self.path.parent)
            )
            for business in self.data.businesses:
                business.minutes = previous.get(business.id)
            self.data.refresh_at = now() + REFRESH
            self.scan_pending = None
            self.data.scan = None
            if self.data.businesses:
                ready = sum(not business.reason for business in self.data.businesses)
                self.update(
                    "Menunggu", f"{ready} dari {len(self.data.businesses)} usaha layak dijaga."
                )
            else:
                self.update("Menunggu", "Game mengembalikan daftar usaha kosong.")

    async def start_next(self, c, settings: JagaSettings, day: date) -> None:
        for item in self.data.businesses:
            if item.guarded_in_game:
                active, _ = status_values(await c.ui.jaga_status(item.id))
                if active:
                    self.data.retry_at = now() + RECHECK
                    self.update("Menunggu", "Usaha sedang dijaga di game.")
                    return
                item.guarded_in_game = False
                self.save()
        first = None if settings.auto_pindah else self.data.first_business
        eligible = [
            item
            for item in self.data.businesses
            if not item.reason and (first is None or first == item.id)
        ]
        ready = [item for item in eligible if item.minutes is None or item.minutes < item.target]
        if settings.mode == "rotasi":
            ready.sort(
                key=lambda item: self.data.last_guarded.get(
                    item.id, datetime.min.replace(tzinfo=WIB)
                )
            )
        if not ready:
            message = (
                "Target usaha hari ini tercapai."
                if eligible
                else "Tidak ada usaha yang siap dijaga."
            )
            if self.data.message != message:
                self.update("Selesai hari ini" if eligible else "Menunggu", message)
            return
        business = ready[0]
        listed = listed_businesses(await c.ui.businesses_semua())
        try:
            shop = await c.ui.shop_info(business.id) if business.id in listed else None
        except ShopClosed:
            shop = {"mine": True, "open": False}
        reason = shop_block(listed.get(business.id, {}), shop)
        if reason:
            business.reason = reason
            self.update("Menunggu", reason)
            return
        raw = await c.ui.jaga_status(business.id)
        active, minutes = status_values(raw)
        if active:
            business.guarded_in_game = True
            self.data.retry_at = now() + RECHECK
            self.update("Menunggu", "Usaha sedang dijaga di game.")
            return
        maximum = whole(raw.get("maksMenit"))
        interval = whole(raw.get("detakDetik"))
        if minutes is None or maximum is None or maximum < 0 or not valid_interval(interval):
            business.reason = "Batas atau interval jaga belum tersedia."
            self.update("Menunggu", business.reason)
            return
        if raw.get("open") is not True:
            business.reason = "Usaha tutup menurut status jaga."
            self.update("Menunggu", business.reason)
            return
        target = min(business.target, maximum)
        business.minutes = minutes
        business.target = target
        if not settings.auto_pindah and self.data.first_business is None:
            self.data.first_business = business.id
        if minutes >= target:
            self.update("Menunggu", "Salah satu usaha sudah mencapai target.")
            return
        c.check_cancel()
        await c.read_snapshot()
        c.check_cancel()
        at = now()
        if (
            day != at.astimezone(WIB).date()
            or self.reason(c, auto_flags(c.settings.runtime_dir), settings, at)
            or settings != load_jaga_settings(self.path.parent)
        ):
            return
        session = Session(
            business_id=business.id,
            name=business.name,
            day=day,
            started_at=at,
            target=target,
            minutes=minutes,
            initial_minutes=minutes,
        )
        self.data.session = session
        self.update("Memulai", business.name)
        try:
            response = await c.ui.jaga_action(business.id, "mulai")
            active, count = status_values(response)
        except (HttpCoreError, ValueError) as exc:
            await self.action_error(c, exc)
            return
        if not active:
            self.finish(c, "Server tidak mengaktifkan sesi.", count, backoff=True)
            return
        interval = whole(response.get("detakDetik"))
        if count is None or count < minutes or interval is None or not valid_interval(interval):
            self.update("Rekonsiliasi", "Respons mulai belum dapat dikonfirmasi.")
            return
        maximum = whole(response.get("maksMenit"))
        if maximum is not None and maximum >= 0:
            session.target = min(session.target, maximum)
        session.phase = "active"
        session.interval = interval
        self.data.first_business = self.data.first_business or business.id
        self.confirm_heartbeat(session, count)
        if count >= session.target or response.get("open") is False:
            await self.close(
                c, "Target menit tercapai." if count >= session.target else "Usaha tutup."
            )

    def confirm_heartbeat(self, session: Session, minutes: int) -> None:
        session.minutes = minutes
        session.last_confirmed = now()
        session.next_at = session.last_confirmed + timedelta(seconds=session.interval)
        self.update("Jaga", session.name)

    async def heartbeat(self, c) -> None:
        session = self.data.session
        if session is None:
            return
        c.check_cancel()
        flags = auto_flags(c.settings.runtime_dir)
        if not flags["jaga"] or flags["ojol"] is not False:
            await self.close(c, "Pengaturan aktivitas akun berubah.")
            return
        session.next_at = now() + timedelta(seconds=session.interval)
        self.save()
        try:
            raw = await c.ui.jaga_action(session.business_id, "detak")
            active, count = status_values(raw)
        except (HttpCoreError, ValueError) as exc:
            await self.action_error(c, exc)
            return
        if not active:
            reason = raw.get("alasan")
            self.finish(
                c,
                reason if isinstance(reason, str) else "Sesi berakhir di server.",
                count,
                backoff=True,
            )
            return
        if count is None or count < session.minutes:
            self.recover = True
            self.update("Rekonsiliasi", "Menit dari server belum dapat dikonfirmasi.")
            return
        self.confirm_heartbeat(session, count)
        if count >= session.target:
            await self.close(c, "Target menit tercapai.")

    async def action_error(self, c, error: HttpCoreError | ValueError) -> None:
        category = getattr(error, "category", None)
        self.recover = True
        if category == "auth":
            raise error
        if category == "verification":
            self.data.verification = True
            self.update("Verifikasi diperlukan", str(error))
        elif category == "rejected" and self.data.session and self.data.session.phase == "starting":
            self.finish(c, str(error), None, backoff=True)
        elif category == "rejected":
            await self.close(c, str(error))
        else:
            self.update("Rekonsiliasi", str(error))

    async def reconcile(self, c, *, resume: bool, end_reason: str = "") -> None:
        session = self.data.session
        if session is None:
            return
        try:
            raw = await c.ui.jaga_status(session.business_id)
            active, count = status_values(raw)
        except (HttpCoreError, ValueError) as exc:
            if getattr(exc, "category", None) == "auth":
                raise
            self.update("Rekonsiliasi", "Status sesi belum terkonfirmasi.")
            return
        if not active:
            self.finish(
                c,
                session.end_reason or end_reason or "Server mengonfirmasi sesi sudah berakhir.",
                count,
                backoff=session.phase != "closing",
            )
            return
        at = now()
        matches = (
            session.phase == "active"
            and session.last_confirmed is not None
            and at - session.last_confirmed < SESSION_EXPIRY
            and count is not None
            and count >= session.minutes
        )
        if self.data.verification:
            self.update("Verifikasi diperlukan", "Selesaikan verifikasi dan sesi jaga di game.")
        elif (
            matches
            and count is not None
            and (not resume or count >= session.target or raw.get("open") is False)
        ):
            self.recover = False
            session.minutes = count
            await self.close(
                c,
                end_reason
                or ("Target menit tercapai." if count >= session.target else "Usaha tutup."),
            )
        elif matches and count is not None:
            self.recover = False
            session.minutes = count
            session.next_at = max(session.next_at or at, at)
            self.update("Jaga", session.name)
        else:
            self.update("Rekonsiliasi", "Menunggu server mengonfirmasi sesi berakhir.")

    async def close(self, c, reason: str) -> None:
        session = self.data.session
        if session is None:
            return
        if (
            self.recover
            or session.phase != "active"
            or self.data.verification
            or session.last_confirmed is None
            or now() - session.last_confirmed >= SESSION_EXPIRY
        ):
            await self.reconcile(c, resume=False, end_reason=reason)
            return
        session.phase = "closing"
        session.end_reason = reason
        self.update("Menutup sesi", reason)
        try:
            await c.ui.jaga_action(session.business_id, "selesai")
        except HttpCoreError as exc:
            if exc.category == "verification":
                self.data.verification = True
                self.update("Verifikasi diperlukan", str(exc))
                return
            if exc.category == "auth":
                raise
            self.update("Rekonsiliasi", f"Penutupan belum terkonfirmasi. {exc}")
            return
        await self.reconcile(c, resume=False)

    def finish(self, c, reason: str, minutes: int | None, *, backoff: bool = False) -> None:
        session = self.data.session
        if session is None:
            return
        at = now()
        midnight = datetime.combine(session.day + timedelta(days=1), time.min, tzinfo=WIB)
        end = min(at, midnight, (session.last_confirmed or session.started_at) + SESSION_EXPIRY)
        elapsed = max(0, (end - session.started_at).total_seconds())
        if at >= midnight or minutes is None:
            minutes = session.minutes
        if session.day == self.data.day:
            self.data.used_seconds += elapsed
        if session.last_confirmed is not None:
            self.data.last_guarded[session.business_id] = end
        for business in self.data.businesses:
            if business.id == session.business_id:
                business.minutes = minutes
                business.target = session.target
        self.data.session = None
        self.recover = False
        self.data.retry_at = at + (REFRESH if backoff else RECHECK)
        self.update("Verifikasi diperlukan" if self.data.verification else "Menunggu", reason)
        c.journal.event(
            c.run_id,
            "jaga_sesi",
            {
                "business_id": session.business_id,
                "day": session.day.isoformat(),
                "server_minutes_start": session.initial_minutes,
                "server_minutes_end": minutes,
                "duration_seconds": round(elapsed),
                "reason": redact(reason),
            },
        )

    async def shutdown(self, c) -> None:
        if self.data.session:
            try:
                async with asyncio.timeout(8):
                    await self.close(c, "Worker dihentikan.")
            except (TimeoutError, HttpCoreError, OSError, ValueError):
                # The session record is retained for reconciliation on the next run.
                pass


def valid_interval(value: int | None) -> bool:
    return value is not None and 0 < value < SESSION_EXPIRY.total_seconds()
