import asyncio
import json
import os
import re
import time
from datetime import timedelta
from decimal import Decimal

from .models import now
from .planner import is_sleeping, next_step, select_shop


class StopRequested(Exception):
    pass


class Controller:
    def __init__(self, ui, settings, journal, run_id, cancel=None):
        self.ui, self.settings, self.journal, self.run_id = ui, settings, journal, run_id
        self.cancel = cancel or asyncio.Event()
        self.spent = Decimal(0)
        self.completed = 0
        self.started = time.monotonic()
        self.state = None
        self.snapshot_received_at = None
        self.last_event = None
        self.wait_until = None
        self.trip_due = None
        self.active_trip = None
        self.stage = "controller.start"
        self.last_action = None
        self.busy_since = None
        if ui is not None:
            ui.check_cancel = self.check_cancel
            ui.on_recovery = self.report

    def check_cancel(self):
        if self.cancel.is_set() or (self.settings.runtime_dir / "STOP").exists():
            raise StopRequested("Dihentikan pengguna")
        if (
            self.settings.max_minutes is not None
            and time.monotonic() - self.started >= self.settings.max_minutes * 60
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
        from .telegram import notifications_enabled, queue_notice, redact

        if notifications_enabled(self.settings):
            from .finance import WIB

            text = (
                f"📣 {event} · {now().astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB\nRun {self.run_id} · {self.stage}\n"
                + json.dumps(data, ensure_ascii=False, default=str)
            )
            queue_notice(
                self.settings,
                redact(text, self.settings),
                {"routine_event": True, "event": event, "run_id": self.run_id},
            )

    async def wait(self, seconds):
        self.stage = "wait.countdown"
        self.wait_until = (now() + timedelta(seconds=seconds)).isoformat()
        self.report("menunggu", seconds=round(seconds, 3))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.check_cancel()
            await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))
        self.wait_until = None

    async def read_snapshot(self):
        self.state = await self.ui.snapshot()
        self.snapshot_received_at = now().isoformat()
        return self.state

    async def verify(self, predicate, timeout=12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check_cancel()
            state = await self.read_snapshot()
            if is_sleeping(state):
                raise RuntimeError(next_step(state, self.settings).reason)
            if predicate(state):
                return state
            await asyncio.sleep(0.75)
        raise RuntimeError("Perubahan status belum terbukti; berhenti tanpa mengulang aksi")

    async def purchase(self, before, resource):
        self.check_cancel()
        self.stage = f"shop.preview.{resource}"
        shops = await self.ui.preview_shops(resource)
        selection, defer = select_shop(before, resource, shops, self.settings, self.spent)
        if defer:
            self.report(
                "isi_ulang_ditunda",
                resource=resource,
                current=getattr(before, resource),
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
            "Akademis.ai layak dengan biaya per poin terendah di kelompok prioritas"
            if supplier.preferred
            else "Tidak ada rencana Akademis.ai yang memenuhi syarat"
        )
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
            await self.ui.buy(
                plan.product, before.wallet, getattr(before, resource), self.settings.min_balance
            )
            self.stage = f"purchase.verify.{resource}"
            after = await self.verify(
                lambda state: (
                    getattr(state, resource) > getattr(before, resource)
                    and abs((before.wallet - state.wallet) - plan.product.price) <= Decimal("0.015")
                )
            )
        except BaseException:
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
            before=getattr(before, resource),
            after=getattr(after, resource),
            wallet=str(after.wallet),
            navigation=navigation,
            advertised_gain=plan.product.effects[resource],
            observed_gain=getattr(after, resource) - getattr(before, resource),
            overflow_points=max(
                0, getattr(before, resource) + plan.product.effects[resource] - 100
            ),
        )
        return True

    async def job_action(self, before, kind):
        self.check_cancel()
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
                    lambda state: state.phase != "complete" and state.history != before.history
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
        except BaseException:
            self.journal.settle(action, False)
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

    async def run(self, dry_run=False):
        while True:
            self.check_cancel()
            previous = self.state
            self.stage = "observe.ojol"
            await self.read_snapshot()
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
            step = next_step(self.state, self.settings)
            if self.state.phase != "searching":
                self.busy_since = None
            self.report(
                "observasi",
                phase=self.state.phase,
                fuel=self.state.fuel,
                condition=self.state.condition,
                data=self.state.data,
                wallet=str(self.state.wallet),
                next=step.action,
            )
            if dry_run:
                self.report("dry_run", plan=step.model_dump(mode="json"))
                return
            if self.settings.max_jobs is not None and self.completed >= self.settings.max_jobs:
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
            if step.action == "wait":
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
