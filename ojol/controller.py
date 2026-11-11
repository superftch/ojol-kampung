import asyncio
import json
import os
import re
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from .auto_settings import auto_flags
from .finance import completion_evidence
from .http_api import HttpCoreError
from .maintenance import SCHEDULE_FILE, held_window
from .models import NEEDS, Step, now
from .planner import is_sleeping, next_step, select_need, select_shop
from .reconciliation import wait_until_resolved
from .telegram import queue_notice


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

    def report(self, event, **data):
        self.last_event = event
        self.journal.event(self.run_id, event, data)
        message = {"time": now().isoformat(), "event": event, **data}
        print(json.dumps(message, ensure_ascii=False, default=str), flush=True)
        status = {
            "pid": os.getpid(),
            "run_id": self.run_id,
            "run_started_at": self.started_at.isoformat(),
            "event": event,
            "stage": self.stage,
            "spent": str(self.spent),
            "last_action": self.last_action,
            "core": getattr(self.ui, "core_name", "http_mcp"),
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
        from .telegram import event_text, notifications_enabled, queue_notice, redact

        if notifications_enabled(self.settings):
            text = event_text(event, data)
            if text:
                queue_notice(
                    self.settings,
                    redact(text, self.settings),
                    {"routine_event": True, "event": event, "run_id": self.run_id},
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
        while time.monotonic() < deadline:
            self.check_cancel()
            await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
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
            return
        self.stage = "maintenance"
        self.report("maintenance", sampai=window.end.isoformat())
        self.active_trip = None
        self.busy_since = None
        while held_window(self.maintenance_file):
            self.check_cancel()
            await asyncio.sleep(1)

    async def purchase(self, before, resource):
        self.check_cancel()
        if is_sleeping(before):
            return False
        is_need = resource in NEEDS
        feature = resource if is_need else "ojol"
        if held_window(self.maintenance_file) or not auto_flags(self.settings.runtime_dir)[feature]:
            return False
        current = before.resource_value(resource)
        self.stage = f"shop.preview.{resource}"
        try:
            shops = await self.ui.preview_shops(resource)
        except HttpCoreError as exc:
            if held_window(self.maintenance_file) or (is_need and exc.category != "auth"):
                return False
            raise
        if held_window(self.maintenance_file) or not auto_flags(self.settings.runtime_dir)[feature]:
            return False
        last_purchases = (
            self.journal.last_purchases_by_shop(resource)
            if sum(shop.preferred for shop in shops) > 1
            else {}
        )
        if is_need:
            selection = select_need(
                before,
                resource,
                shops,
                self.settings,
                self.spent,
                last_purchases,
                allow_fallback=getattr(self.ui, "last_navigation", {}).get("akademis_sold_out")
                is True,
            )
            if selection is None:
                return False
            defer = False
        else:
            selection, defer = select_shop(
                before, resource, shops, self.settings, self.spent, last_purchases=last_purchases
            )
        if defer:
            self.report(
                "isi_ulang_ditunda",
                resource=resource,
                current=current,
                reason="Menunggu ruang cukup agar efek tidak terbuang",
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
                reason = "Fasilitas olahraga gratis dengan kenaikan fisik tertinggi"
            elif supplier.preferred:
                reason = "Giliran toko Akademis.ai, item dipilih dari manfaat dibanding harga"
            else:
                reason = "Seluruh stok relevan Akademis.ai terkonfirmasi habis"
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
            await self.ui.buy(plan.product, before.wallet, current, self.settings.min_balance)
            self.stage = f"purchase.verify.{resource}"
            tolerance = Decimal(0) if is_need else Decimal("0.015")
            after = await self.verify(
                lambda state: (
                    (state.resource_value(resource) or 0) > current
                    and abs((before.wallet - state.wallet) - plan.product.price) <= tolerance
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
                    return False
            else:
                self.journal.settle(action, False)
            raise
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
        )
        return True

    async def job_action(self, before, kind):
        self.check_cancel()
        if is_sleeping(before):
            return
        if held_window(self.maintenance_file) or (
            kind != "complete" and not auto_flags(self.settings.runtime_dir)["ojol"]
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
            if isinstance(exc, VerificationPending) or (
                isinstance(exc, HttpCoreError) and exc.category in {"uncertain", "transport"}
            ):
                self.state = await wait_until_resolved(self.ui, self.journal, self.settings)
                self.snapshot_received_at = now().isoformat()
                resolved = self.journal.db.execute(
                    "SELECT status FROM actions WHERE id=?", (action,)
                ).fetchone()
                if kind == "complete" and resolved["status"] == "verified":
                    self.completed += 1
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
                await self.wait(self.settings.idle_poll_seconds)
                continue
            self.stage = "observe.ojol"
            try:
                await self.read_snapshot()
            except HttpCoreError:
                if held_window(self.maintenance_file):
                    continue
                raise
            if held_window(self.maintenance_file):
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
            if not flags["ojol"] and self.state.phase in {"idle", "sleeping"}:
                step = Step(
                    action="wait",
                    reason="Auto Ojol nonaktif.",
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
            if auto_start and step.action != "stop":
                queue_notice(
                    self.settings,
                    "✅ Bot siap kembali\n\nAkun sudah terhubung ke game. Aktivitas dilanjutkan sesuai pengaturan Auto.",
                )
                auto_start = False
            if (
                flags["ojol"]
                and self.settings.max_jobs is not None
                and self.completed >= self.settings.max_jobs
            ):
                raise StopRequested("Batas jumlah trip tercapai")
            if step.action == "maintain":
                deferred = set()
                while step.action == "maintain":
                    if await self.purchase(self.state, step.resource):
                        break
                    deferred.add(step.resource)
                    step = next_step(self.state, self.settings, deferred=deferred)
                if step.action == "maintain":
                    continue
            if step.action == "stop":
                raise RuntimeError(step.reason)
            if self.state.phase == "idle" and (
                step.action in {"search", "take"} or not flags["ojol"]
            ):
                need = min(
                    (
                        need
                        for need, value in self.state.needs.items()
                        if flags[need]
                        and value < self.settings.threshold
                        and time.monotonic() >= self.need_retry_at.get(need, 0)
                    ),
                    key=self.state.needs.__getitem__,
                    default=None,
                )
                if need is not None:
                    if (
                        not await self.purchase(self.state, need)
                        and auto_flags(self.settings.runtime_dir)[need]
                    ):
                        self.need_retry_at[need] = time.monotonic() + 300
                    continue
            if step.action == "wait":
                if self.state.phase in {"idle", "sleeping"}:
                    await self.wait(step.wait_seconds)
                    continue
                if self.state.phase == "searching":
                    if self.busy_since is None:
                        self.busy_since = time.monotonic()
                    if time.monotonic() - self.busy_since > 30:
                        raise RuntimeError(
                            "Pencarian belum selesai setelah 30 detik; berhenti tanpa klik duplikat"
                        )
                    await self.wait(step.wait_seconds)
                    continue
                if self.active_trip != self.state.trip:
                    self.active_trip = self.state.trip
                    self.trip_due = time.monotonic() + step.wait_seconds
                if time.monotonic() > self.trip_due + 90:
                    raise RuntimeError(
                        "Countdown UI tidak maju di background; berhenti tanpa memalsukan waktu game"
                    )
                await self.wait(
                    max(1, min(step.wait_seconds, max(1, self.trip_due - time.monotonic())))
                )
            else:
                self.active_trip = None
                await self.job_action(self.state, step.action)
