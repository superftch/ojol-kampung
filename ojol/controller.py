import asyncio
import json
import os
import random
import re
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from .auto_settings import auto_flags, set_auto_flag
from .finance import completion_evidence
from .garden import run_garden
from .gym import run_gym
from .http_api import HttpCoreError
from .journal import load_journal_snapshot
from .maintenance import SCHEDULE_FILE, held_window
from .models import NEEDS, Step, now
from .planner import is_sleeping, next_step, select_need, select_shop
from .reconciliation import reconcile, wait_until_resolved
from .study import run_learning
from .telegram import queue_error, queue_notice


class StopRequested(Exception):
    pass


class VerificationPending(RuntimeError):
    pass


class Controller:
    def __init__(self, ui, settings, journal, run_id, cancel=None):
        self.ui, self.settings, self.journal, self.run_id = ui, settings, journal, run_id
        self.cancel = cancel or asyncio.Event()
        self.spent = Decimal(0)
        self.completed = 0
        self.started = time.monotonic()
        self.sleep_started = None
        self.started_at = now()
        self.state = None
        self.snapshot_received_at = None
        self.snapshot_read_at = None
        self.last_event = None
        self.wait_until = None
        self.trip_due = None
        self.active_trip = None
        self.stage = "controller.start"
        self.last_action = None
        self.busy_since = None
        self.need_retry_at = {}
        self.study_retry_at = {}
        self.garden_retry_at = 0
        self.gym_retry_at = 0
        self.spbu_reminded_vehicle = None
        self.claim_failures = {}
        self.claim_errors = {}
        self.maintenance_file = Path(
            os.environ.get("OJOL_MAINTENANCE_FILE", str(settings.runtime_dir / SCHEDULE_FILE))
        )
        if ui is not None:
            ui.check_cancel = self.check_cancel
            ui.on_recovery = self.report

    def check_cancel(self):
        if self.cancel.is_set() or (self.settings.runtime_dir / "STOP").exists():
            raise StopRequested("Dihentikan pengguna")
        if (
            self.settings.max_minutes is not None
            and (self.sleep_started if self.sleep_started is not None else time.monotonic())
            - self.started
            >= self.settings.max_minutes * 60
        ):
            raise StopRequested("Batas durasi sesi tercapai")

    async def human_pause(self, low=0.4, high=1.6):
        """Jeda acak sebelum klik agar ritme mirip manusia.
        ponytail: konstanta tetap; jadikan setting bila pola bot terdeteksi."""
        self.check_cancel()
        try:
            await asyncio.wait_for(self.cancel.wait(), timeout=random.uniform(low, high))
        except asyncio.TimeoutError:
            pass
        self.check_cancel()

    def handle_ojol_failure(self, exc_or_reason, stage=None, tindakan=None):
        flags = auto_flags(self.settings.runtime_dir)
        has_kebutuhan = any(flags[k] for k in flags if k != "ojol")
        reason = str(exc_or_reason)
        if has_kebutuhan:
            set_auto_flag(self.settings.runtime_dir, "ojol", False)
            self.active_trip = None
            self.busy_since = None
            self.report("ojol_gagal", reason=reason)
            exc = exc_or_reason if isinstance(exc_or_reason, Exception) else RuntimeError(reason)
            queue_error(
                self.settings,
                exc,
                stage or self.stage,
                {
                    "tindakan": tindakan
                    or "Auto Ojol dinonaktifkan karena gagal. Fitur auto kebutuhan tetap berjalan normal. Tekan Jalankan Ojol jika ingin mencoba lagi."
                },
                stop_worker=False,
            )
            return True
        return False

    def _format_claim_error(self, exc):
        text = str(exc)
        low = text.lower()
        if "409" in text or "turun" in low:
            return "409 penumpang belum turun"
        if "captcha" in low or "bank angka" in low or "glyph" in low or "angka" in low:
            return "verifikasi captcha angka gagal"
        if isinstance(exc, VerificationPending) or "receipt" in low or "bukti" in low:
            return "bukti pembayaran belum muncul di game"
        return text[:45]

    def _diagnose_claim_failure(self, exc, state):
        text = str(exc)
        low = text.lower()
        if "captcha" in low or "bank angka" in low or "glyph" in low or "angka" in low:
            return {
                "alasan": "Verifikasi kode captcha angka gagal dipecahkan atau tidak cocok.",
                "solusi": "Periksa atau kontribusikan angka verifikasi di menu Bank Angka lalu tekan Jalankan Ojol.",
            }
        if "409" in text or "turun" in low or "conflict" in low:
            return {
                "alasan": "Server game merespons status 409 (penumpang sedang turun atau transit order belum tuntas).",
                "solusi": "Tunggu beberapa detik di game agar status penumpang selesai turun, lalu tekan Jalankan Ojol.",
            }
        if isinstance(exc, VerificationPending) or "receipt" in low or "bukti" in low or "history" in low:
            return {
                "alasan": "Server game tidak memunculkan bukti payout/receipt order di riwayat transaksi game setelah 3x percobaan klaim.",
                "solusi": "Periksa saldo atau riwayat order langsung di game Kampung Sebelah. Jika order sudah selesai, tekan Jalankan Ojol.",
            }
        if "transport" in low or "connection" in low or "timeout" in low or "50" in text:
            return {
                "alasan": f"Koneksi ke server game bermasalah saat mengirim klaim ({text}).",
                "solusi": "Periksa koneksi jaringan atau server game Kampung Sebelah, lalu tekan Jalankan Ojol.",
            }
        return {
            "alasan": f"Klaim ongkos ditolak atau gagal diverifikasi: {text}",
            "solusi": "Periksa status akun dan order langsung di game Kampung Sebelah, lalu tekan Jalankan Ojol.",
        }

    def report(self, event, **data):
        self.last_event = event
        self.journal.event(self.run_id, event, data)
        status = {
            "pid": os.getpid(),
            "run_id": self.run_id,
            "run_started_at": self.started_at.isoformat(),
            "event": event,
            "stage": self.stage,
            "spent": str(self.spent),
            "last_action": self.last_action,
            "completed": self.completed,
            "wait_until": self.wait_until,
            "profit": self.journal.profit(self.run_id),
            "profit_total": self.journal.profit(),
            "snapshot": self.state.model_dump(mode="json") if self.state else None,
            "snapshot_received_at": self.snapshot_received_at,
            **data,
        }
        output = self.settings.runtime_dir / "status.json"
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(status, ensure_ascii=False, default=str, indent=2))
        temporary.chmod(0o600)
        temporary.replace(output)
        from .telegram import (
            MANDATORY_EVENTS,
            event_text,
            notifications_enabled,
            queue_notice,
            redact,
        )

        if event in MANDATORY_EVENTS or notifications_enabled(self.settings):
            text = event_text(event, data)
            if text:
                queue_notice(
                    self.settings,
                    redact(text, self.settings),
                    {
                        "routine_event": event not in MANDATORY_EVENTS,
                        "event": event,
                        "run_id": self.run_id,
                    },
                )

    async def wait(self, seconds):
        if self.state and self.state.sleep_schedule and self.snapshot_read_at is not None:
            boundary = self.state.sleep_schedule.next_transition(self.state.observed_at)
            if boundary is not None:
                remaining = (boundary - self.state.observed_at).total_seconds()
                remaining -= time.monotonic() - self.snapshot_read_at
                seconds = min(seconds, max(0.25, remaining))
        sleeping = self.sleep_started is not None
        self.stage = "sleeping" if sleeping else "wait.countdown"
        self.wait_until = (now() + timedelta(seconds=seconds)).isoformat()
        self.report("tidur" if sleeping else "menunggu", seconds=round(seconds, 3))
        deadline = time.monotonic() + seconds
        last_presence = time.monotonic()
        wake_file = self.settings.runtime_dir / "WAKE"
        while time.monotonic() < deadline:
            self.check_cancel()
            if wake_file.is_file():
                try:
                    wake_file.unlink(missing_ok=True)
                except OSError:
                    pass
                break
            await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
            if time.monotonic() - last_presence >= 35:
                if hasattr(self.ui, "fetch_online_status"):
                    try:
                        await self.ui.fetch_online_status()
                    except Exception:
                        pass
                last_presence = time.monotonic()
        self.wait_until = None

    async def read_snapshot(self):
        self.state = await self.ui.snapshot()
        self.snapshot_received_at = now().isoformat()
        self.snapshot_read_at = time.monotonic()
        self.journal.sync_game(self.state)
        return self.state

    async def wait_for_wake(self):
        if not is_sleeping(self.state):
            return 0
        self.sleep_started = time.monotonic()
        try:
            self.report("tidur_mulai")
            while is_sleeping(self.state):
                await self.wait(self.settings.idle_poll_seconds)
                await self.wait_for_maintenance()
                self.check_cancel()
                await self.read_snapshot()
        finally:
            paused = time.monotonic() - self.sleep_started
            for field in ("started", "trip_due", "busy_since"):
                value = getattr(self, field)
                if value is not None:
                    setattr(self, field, value + paused)
            self.need_retry_at = {key: value + paused for key, value in self.need_retry_at.items()}
            if hasattr(self, "gym_retry_at") and self.gym_retry_at > 0:
                self.gym_retry_at += paused
            self.sleep_started = None
        self.report("bangun", phase=self.state.phase)
        return paused

    async def verify(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check_cancel()
            state = await self.read_snapshot()
            if is_sleeping(state):
                deadline += await self.wait_for_wake()
                state = self.state
            if predicate(state):
                return state
            await asyncio.sleep(0.75)
        raise VerificationPending("Perubahan status belum terbukti; memeriksa ulang hasil aksi")

    async def wait_for_maintenance(self):
        window = held_window(self.maintenance_file)
        if window is None:
            if getattr(self, "in_maintenance", False):
                self.in_maintenance = False
                self.report("maintenance_selesai")
            return
        if getattr(window, "target", "all") == "all":
            self.stage = "maintenance"
            self.report("maintenance", sampai=window.end.isoformat() if window.end else "manual")
            self.active_trip = None
            self.busy_since = None
            while held_window(self.maintenance_file):
                self.check_cancel()
                await asyncio.sleep(1)
            self.report("maintenance_selesai")
            return
        if not getattr(self, "in_maintenance", False):
            self.in_maintenance = True
            self.stage = "maintenance"
            self.report(
                "maintenance",
                sampai=window.end.isoformat() if window.end else "manual",
                target="ojol",
            )
            self.active_trip = None
            self.busy_since = None

    async def purchase(self, before, resource):
        self.check_cancel()
        if is_sleeping(before):
            return False
        is_need = resource in NEEDS
        feature = resource if is_need else "ojol"
        window = held_window(self.maintenance_file)
        is_global_maint = window is not None and getattr(window, "target", "all") == "all"
        is_ojol_maint = (
            getattr(before, "ojol_maintenance", False)
            or auto_flags(self.settings.runtime_dir).get("ojol") == "maintenance"
            or bool(window)
        )
        if is_need:
            if is_global_maint or not auto_flags(self.settings.runtime_dir)[feature]:
                return False
        else:
            if (
                is_global_maint
                or is_ojol_maint
                or not auto_flags(self.settings.runtime_dir)["ojol"]
            ):
                return False
        current = before.resource_value(resource)
        self.stage = f"shop.preview.{resource}"
        try:
            shops = await self.ui.preview_shops(resource)
        except HttpCoreError as exc:
            window = held_window(self.maintenance_file)
            if window and (getattr(window, "target", "all") == "all" or not is_need):
                return False
            if is_need and exc.category != "auth":
                queue_error(self.settings, exc, self.stage, stop_worker=False)
                return False
            raise
        window = held_window(self.maintenance_file)
        if is_need:
            if (window and getattr(window, "target", "all") == "all") or not auto_flags(
                self.settings.runtime_dir
            )[feature]:
                return False
        else:
            if bool(window) or is_ojol_maint or not auto_flags(self.settings.runtime_dir)["ojol"]:
                return False
        last_purchases = (
            self.journal.last_purchases_by_shop(resource)
            if sum(shop.preferred for shop in shops) > 1
            else {}
        )
        streak_product, streak_count = (
            self.journal.recent_product_streak(resource)
            if resource == "makan" and hasattr(self.journal, "recent_product_streak")
            else (None, 0)
        )
        if is_need:
            selection = select_need(
                before,
                resource,
                shops,
                self.settings,
                self.spent,
                last_purchases,
                allow_fallback=getattr(self.ui, "last_navigation", {}).get("akademis_unavailable")
                is True,
                streak_product=streak_product,
                streak_count=streak_count,
            )
            if selection is None:
                self.report(
                    "kebutuhan_ditunda",
                    resource=resource,
                    reason="Tidak ada produk/fasilitas yang memenuhi stok, kapasitas, saldo, dan anggaran.",
                )
                return False
            defer = False
        else:
            selection, defer = select_shop(
                before, resource, shops, self.settings, self.spent, last_purchases=last_purchases
            )
        if defer or (selection is None and current > self.settings.resource_reserve_percent):
            self.report(
                "isi_ulang_ditunda",
                resource=resource,
                current=current,
                reason=(
                    "Menunggu ruang cukup agar efek tidak terbuang"
                    if defer
                    else "Tidak ada pembelian layak; resource masih di atas batas cadangan"
                ),
            )
            return False
        if selection is None:
            raise RuntimeError("Tidak ada pembelian sesuai resource, anggaran, dan saldo minimum")
        supplier, plan = selection
        shop = supplier.name
        navigation = {
            **getattr(self.ui, "last_navigation", {}),
            "shop": shop,
            "plot_id": supplier.plot_id,
        }
        self.report("toko_dibuka", shop=shop, navigation=navigation)
        source = "akademis" if supplier.preferred else "cadangan"
        reason = (
            "Akademis.ai dipilih sesuai giliran dan kelayakan pembelian"
            if supplier.preferred
            else "Tidak ada toko Akademis.ai yang memenuhi syarat"
        )
        if is_need:
            if supplier.category == "fasum":
                source = "fasum"
                reason = "Fasilitas dengan manfaat terpakai per koin terbaik"
            elif supplier.preferred:
                reason = "Giliran toko Akademis.ai; item dipilih berdasarkan manfaat dan harga"
            else:
                reason = "Tidak ada produk relevan yang tersedia dari Akademis.ai"
        self.report(
            "rencana_beli",
            shop=shop,
            source=source,
            reason=reason,
            resource=resource,
            product=plan.product.name,
            quantity=plan.quantity,
            cost=str(plan.total_cost),
        )
        self.check_cancel()
        # A multi-unit plan budgets the refill; the next unit needs a fresh preview.
        action = self.journal.begin(
            self.run_id,
            "purchase",
            before,
            {
                "resource": resource,
                "shop": shop,
                "shop_id": supplier.id,
                "source": source,
                "reason": reason,
                "navigation": navigation,
                "product": plan.product.model_dump(mode="json"),
                **(
                    self.ui.prepare_action("purchase") if hasattr(self.ui, "prepare_action") else {}
                ),
            },
        )
        self.last_action = {
            "action_id": action,
            "kind": "purchase",
            "resource": resource,
            "shop": shop,
            "product": plan.product.name,
        }
        try:
            self.check_cancel()
            self.stage = f"purchase.click.{resource}"
            await self.human_pause()
            await self.ui.buy(plan.product, before.wallet, current, self.settings.min_balance)
            self.stage = f"purchase.verify.{resource}"
            tolerance = Decimal("0.02")
            price = plan.product.price
            after = await self.verify(
                lambda state: (
                    (
                        (state.resource_value(resource) or 0) > current
                        or (current == 100 and (state.resource_value(resource) or 0) >= 100)
                    )
                    and (
                        abs((before.wallet - state.wallet) - price) <= tolerance
                        or (
                            price == Decimal(0)
                            and (
                                state.wallet >= before.wallet - tolerance
                                or (state.resource_value(resource) or 0) > current
                            )
                        )
                    )
                )
            )
        except BaseException as exc:
            if isinstance(exc, HttpCoreError) and exc.category in {
                "rejected",
                "auto_disabled",
                "sleeping",
            }:
                self.journal.reject(action)
                if exc.category == "sleeping":
                    await self.read_snapshot()
                    await self.wait_for_wake()
                    return False
                if is_need or exc.category == "auto_disabled":
                    if is_need and exc.category == "rejected":
                        queue_error(self.settings, exc, self.stage, stop_worker=False)
                    return False
            else:
                self.journal.settle(action, False)
            if isinstance(exc, VerificationPending) or (
                isinstance(exc, HttpCoreError) and exc.category in {"uncertain", "transport"}
            ):
                # Reserve the attempted cost even if recovery cannot attribute the purchase.
                self.spent += plan.product.price
                self.state = await wait_until_resolved(self.ui, self.journal, self.settings)
                self.snapshot_received_at = now().isoformat()
                self.snapshot_read_at = time.monotonic()
                self.report("rekonsiliasi_selesai", action="purchase", resource=resource)
                resolved = self.journal.db.execute(
                    "SELECT status,after_state FROM actions WHERE id=?", (action,)
                ).fetchone()
                if resolved["status"] != "verified":
                    return True
                after = load_journal_snapshot(resolved["after_state"])
            else:
                raise
        else:
            self.journal.settle(action, True, after)
            self.spent += plan.product.price
        self.report(
            "pembelian_terverifikasi",
            shop=shop,
            product=plan.product.name,
            cost=str(plan.product.price),
            resource=resource,
            before=current,
            after=after.resource_value(resource),
            wallet=str(after.wallet),
            navigation=navigation,
            advertised_gain=plan.product.effects[resource],
            observed_gain=after.resource_value(resource) - current,
            overflow_points=max(0, current + plan.product.effects[resource] - 100),
            auto_enabled=auto_flags(self.settings.runtime_dir)[resource if is_need else "ojol"],
        )
        return True

    async def job_action(self, before, kind):
        self.check_cancel()
        if is_sleeping(before):
            return
        window = held_window(self.maintenance_file)
        is_ojol_maint = (
            getattr(before, "ojol_maintenance", False)
            or auto_flags(self.settings.runtime_dir).get("ojol") == "maintenance"
            or bool(window)
        )
        if (window and getattr(window, "target", "all") == "all") or (
            kind != "complete"
            and (not auto_flags(self.settings.runtime_dir)["ojol"] or is_ojol_maint)
        ):
            return
        patterns = {
            "search": r"Cari order",
            "take": r"Terima|Ambil|Antar sekarang",
            "complete": r"Selesaikan|Sampai|Selesai",
        }
        labels = [
            button for button in before.buttons if re.search(patterns[kind], button, re.IGNORECASE)
        ]
        if len(labels) != 1:
            raise RuntimeError("Tombol Ojol ambigu; tidak memilih sembarang order")
        action = self.journal.begin(
            self.run_id,
            kind,
            before,
            {
                "label": labels[0],
                **(self.ui.prepare_action(kind) if hasattr(self.ui, "prepare_action") else {}),
            },
        )
        self.last_action = {"action_id": action, "kind": kind, "label": labels[0]}
        try:
            self.check_cancel()
            self.stage = f"job.{kind}.click"
            # Update #53 (20 Nov 2026): tunggu sebentar di tujuan; klaim < 2 detik
            # dianggap bot oleh server. Retry 409 turun di adapter sudah menangani jendela 8 dtk.
            await self.human_pause(3.0, 6.0)
            await self.ui.job_click(labels[0])
            self.stage = f"job.{kind}.verify"
            if kind == "complete":
                after = await self.verify(
                    lambda state: (
                        completion_evidence(before, state) is not None
                        if before.trip_id
                        else state.phase != "complete" and state.history != before.history
                    )
                )
                self.completed += 1
                trip_key = before.trip_id or before.trip or "active_trip"
                self.claim_failures.pop(trip_key, None)
                self.claim_errors.pop(trip_key, None)
            elif kind == "take":
                after = await self.verify(
                    lambda state: (
                        state.phase == "delivering" and state.remaining_seconds is not None
                    )
                )
            else:
                after = await self.verify(
                    lambda state: (
                        state.phase in {"searching", "delivering"}
                        or any(
                            re.search(r"Terima|Ambil|Antar sekarang", b, re.IGNORECASE)
                            for b in state.buttons
                        )
                        or bool(
                            re.search(
                                r"belum ada|tidak ada|coba lagi", state.raw_text, re.IGNORECASE
                            )
                        )
                    )
                )
        except BaseException as exc:
            if isinstance(exc, HttpCoreError) and exc.category in {"auto_disabled", "sleeping"}:
                self.journal.reject(action)
                if exc.category == "sleeping":
                    await self.read_snapshot()
                    await self.wait_for_wake()
                return
            self.journal.settle(action, False)
            if kind == "complete":
                trip_key = before.trip_id or before.trip or "active_trip"
                is_verified = False
                if isinstance(exc, (VerificationPending, HttpCoreError)):
                    try:
                        self.state = await reconcile(self.ui, self.journal)
                        self.snapshot_received_at = now().isoformat()
                        resolved = self.journal.db.execute(
                            "SELECT status FROM actions WHERE id=?", (action,)
                        ).fetchone()
                        if resolved and resolved["status"] == "verified":
                            is_verified = True
                            self.completed += 1
                            self.claim_failures.pop(trip_key, None)
                            self.claim_errors.pop(trip_key, None)
                            self.report("rekonsiliasi_selesai", action=kind)
                            return
                    except Exception:
                        pass
                if not is_verified:
                    try:
                        self.journal.skip(action)
                    except Exception:
                        pass
                    fail_count = self.claim_failures.get(trip_key, 0) + 1
                    self.claim_failures[trip_key] = fail_count
                    self.claim_errors[trip_key] = exc
                    if fail_count < 3:
                        queue_notice(
                            self.settings,
                            f"⏳ Percobaan klaim ongkos ({fail_count}/3) belum berhasil ({self._format_claim_error(exc)}). Aksi dilewati di rekonsiliasi dan akan dicoba lagi otomatis.",
                        )
                        self.report("klaim_ongkos_dicoba_lagi", trip=trip_key, attempt=fail_count)
                        await self.human_pause(2.0, 4.0)
                        return
                    else:
                        diag = self._diagnose_claim_failure(exc, self.state)
                        defined_reason = (
                            f"Gagal klaim ongkos trip {trip_key} setelah 3 percobaan: {diag['alasan']}"
                        )
                        self.claim_failures.pop(trip_key, None)
                        self.claim_errors.pop(trip_key, None)
                        claim_exc = RuntimeError(defined_reason)
                        if self.handle_ojol_failure(
                            claim_exc, stage="job.complete", tindakan=diag["solusi"]
                        ):
                            return
                        raise claim_exc
            if isinstance(exc, VerificationPending) or (
                isinstance(exc, HttpCoreError) and exc.category in {"uncertain", "transport"}
            ):
                self.state = await wait_until_resolved(self.ui, self.journal, self.settings)
                self.snapshot_received_at = now().isoformat()
                self.report("rekonsiliasi_selesai", action=kind)
                return
            raise
        cashflow = self.journal.settle(action, True, after)
        if cashflow and cashflow["kind"] == "income":
            self.report(
                "pendapatan_ojol_tercatat",
                amount=cashflow["amount"],
                profit=self.journal.profit(self.run_id),
            )
        self.report(
            "aksi_job_terverifikasi",
            action=kind,
            phase=after.phase,
            remaining_seconds=after.remaining_seconds,
        )
        if (
            kind == "search"
            and after.phase == "idle"
            and not any(
                re.search(r"Terima|Ambil|Antar sekarang", b, re.IGNORECASE) for b in after.buttons
            )
        ):
            await self.wait(self.settings.idle_poll_seconds)

    async def run(self, dry_run=False, *, auto_start=False):
        while True:
            self.check_cancel()
            await self.wait_for_maintenance()
            self.check_cancel()
            flags = auto_flags(self.settings.runtime_dir)
            previous = self.state
            previous_received_at = self.snapshot_received_at
            if not any(flags.values()) and (
                previous is None or previous.phase not in {"searching", "delivering", "complete"}
            ):
                if dry_run:
                    self.report("dry_run", reason="Semua fitur Auto nonaktif.")
                    return
                if hasattr(self.ui, "fetch_online_status"):
                    try:
                        await self.ui.fetch_online_status()
                    except Exception:
                        pass
                await self.wait(self.settings.idle_poll_seconds)
                continue
            self.stage = "observe.ojol"
            window = held_window(self.maintenance_file)
            is_global_maint = window is not None and getattr(window, "target", "all") == "all"
            try:
                await self.read_snapshot()
            except HttpCoreError as exc:
                if is_global_maint:
                    continue
                if (
                    flags.get("ojol")
                    and (
                        "mitra Ojol" in str(exc)
                        or "ojol" in str(getattr(exc, "path", "")).lower()
                        or "ojol" in str(exc).lower()
                    )
                    and self.handle_ojol_failure(exc)
                ):
                    continue
                raise
            ojol_err = getattr(self.ui, "ojol_failure_error", None) or getattr(
                getattr(self.ui, "api", None), "ojol_failure_error", None
            )
            if ojol_err and flags.get("ojol"):
                if hasattr(self.ui, "ojol_failure_error"):
                    self.ui.ojol_failure_error = None
                if hasattr(getattr(self.ui, "api", None), "ojol_failure_error"):
                    self.ui.api.ojol_failure_error = None
                if self.handle_ojol_failure(ojol_err):
                    flags = auto_flags(self.settings.runtime_dir)
            if is_global_maint:
                self.state = previous
                self.snapshot_received_at = previous_received_at
                continue
            if (
                previous
                and previous.phase == "delivering"
                and self.state.phase in {"idle", "sleeping"}
                and self.state.history != previous.history
            ):
                self.completed += 1
                amount = self.journal.observed_income(self.run_id, previous, self.state)
                self.report(
                    "trip_selesai_otomatis_teramati",
                    income=amount,
                    today_income=str(self.state.today_income),
                    wallet=str(self.state.wallet),
                )
                continue
            is_ojol_maint = (
                getattr(self.state, "ojol_maintenance", False)
                or flags.get("ojol") == "maintenance"
                or bool(window)
            )
            if (
                not flags["ojol"] or flags.get("ojol") == "maintenance" or is_ojol_maint
            ) and self.state.phase in {"idle", "sleeping"}:
                step = Step(
                    action="wait",
                    reason="Fitur Auto Ojol sedang maintenance."
                    if (flags.get("ojol") == "maintenance" or is_ojol_maint)
                    else "Auto Ojol nonaktif.",
                    wait_seconds=self.settings.idle_poll_seconds,
                )
            else:
                step = next_step(self.state, self.settings)
            if self.state.phase != "searching":
                self.busy_since = None
            self.report(
                "observasi",
                phase=self.state.phase,
                fuel=self.state.fuel,
                condition=self.state.condition,
                data=self.state.data,
                needs=self.state.needs,
                wallet=str(self.state.wallet),
                next=step.action,
            )
            if dry_run:
                self.report("dry_run", plan=step.model_dump(mode="json"))
                return
            if is_sleeping(self.state):
                await self.wait_for_wake()
                continue
            if (
                flags["ojol"] is True
                and self.state.phase == "idle"
                and self.state.ojol_min_fuel is not None
                and self.state.fuel < self.settings.threshold_for("fuel")
            ):
                vehicle = self.state.ojol_vehicle
                if vehicle and self.spbu_reminded_vehicle != vehicle:
                    self.spbu_reminded_vehicle = vehicle
                    self.report("spbu_perlu_isi", vehicle=vehicle, fuel=self.state.fuel)
            elif self.state.fuel >= self.settings.threshold_for("fuel") or not flags["ojol"]:
                self.spbu_reminded_vehicle = None
            if auto_start and step.action != "stop":
                queue_notice(
                    self.settings,
                    "✅ Bot siap kembali\n\nAkun sudah terhubung ke game. Aktivitas dilanjutkan sesuai pengaturan Auto.",
                )
                auto_start = False
            if (
                flags["ojol"]
                and not is_ojol_maint
                and self.settings.max_jobs is not None
                and self.completed >= self.settings.max_jobs
            ):
                raise StopRequested("Batas jumlah trip tercapai")
            if step.action == "maintain":
                if is_ojol_maint:
                    step = Step(
                        action="wait",
                        reason="Fitur Auto Ojol sedang maintenance.",
                        wait_seconds=self.settings.idle_poll_seconds,
                    )
                else:
                    deferred = set()
                    while step.action == "maintain":
                        try:
                            if await self.purchase(self.state, step.resource):
                                break
                        except RuntimeError as exc:
                            if flags.get("ojol") and self.handle_ojol_failure(exc):
                                break
                            raise
                        deferred.add(step.resource)
                        step = next_step(self.state, self.settings, deferred=deferred)
                    if step.action == "maintain":
                        continue
            if step.action == "stop":
                if flags.get("ojol") and self.handle_ojol_failure(step.reason):
                    continue
                raise RuntimeError(step.reason)
            if self.state.phase == "idle" and (
                step.action in {"search", "take"}
                or (step.action == "wait" and step.resource == "fuel")
                or not flags["ojol"]
                or flags.get("ojol") == "maintenance"
                or is_ojol_maint
                or getattr(self.state, "ojol_resting", False)
                or getattr(self.state, "ojol_shift_done", False)
                or getattr(self.state, "ojol_maintenance", False)
            ):
                if flags.get("kesehatan") and hasattr(self.ui, "ensure_bpjs"):
                    try:
                        await self.ui.ensure_bpjs()
                    except Exception:
                        pass
                if await run_gym(self):
                    continue
                need = min(
                    (
                        need
                        for need, value in self.state.needs.items()
                        if flags[need]
                        and value < self.settings.threshold_for(need)
                        and time.monotonic() >= self.need_retry_at.get(need, 0)
                        and (
                            not flags["ojol"]
                            or self.state.wallet >= Decimal(20)
                            or need
                            in {"fisik", "kesehatan", "makan", "kebersihan", "wc", "penampilan"}
                        )
                    ),
                    key=self.state.needs.__getitem__,
                    default=None,
                )
                if need is not None:
                    try:
                        purchased = await self.purchase(self.state, need)
                    except RuntimeError:
                        purchased = False
                    if not purchased and auto_flags(self.settings.runtime_dir)[need]:
                        self.need_retry_at[need] = time.monotonic() + 300
                    continue
            if self.state.phase == "idle" and await run_gym(self):
                continue
            if self.state.phase == "idle" and await run_learning(self):
                continue
            if self.state.phase == "idle" and await run_garden(self):
                continue
            if step.action == "wait":
                if self.state.phase in {"idle", "sleeping"}:
                    await self.wait(step.wait_seconds)
                    continue
                if self.state.phase == "searching":
                    if self.busy_since is None:
                        self.busy_since = time.monotonic()
                    if time.monotonic() - self.busy_since > 30:
                        exc = RuntimeError(
                            "Pencarian belum selesai setelah 30 detik; berhenti tanpa klik duplikat"
                        )
                        if flags.get("ojol") and self.handle_ojol_failure(exc):
                            continue
                        raise exc
                    await self.wait(step.wait_seconds)
                    continue
                if self.active_trip != self.state.trip:
                    self.active_trip = self.state.trip
                    self.trip_due = time.monotonic() + step.wait_seconds
                if time.monotonic() > self.trip_due + 90:
                    exc = RuntimeError(
                        "Countdown UI tidak maju di background; berhenti tanpa memalsukan waktu game"
                    )
                    if flags.get("ojol") and self.handle_ojol_failure(exc):
                        continue
                    raise exc
                await self.wait(
                    max(1, min(step.wait_seconds, max(1, self.trip_due - time.monotonic())))
                )
            else:
                self.active_trip = None
                try:
                    await self.job_action(self.state, step.action)
                except Exception as exc:
                    if isinstance(exc, StopRequested):
                        raise
                    if flags.get("ojol") and self.handle_ojol_failure(exc):
                        continue
                    raise
