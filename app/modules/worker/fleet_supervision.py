"""Schedules and monitors workers across authorized game accounts."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from app.core.locks import running
from app.core.storage import status_record
from app.modules.jobs.sniper import load_sniper_config, run_job_sniper_once
from app.modules.notifications.service import queue_error, queue_notice
from app.modules.worker.capacity import WorkerCapacityError, worker_capacity_error
from app.modules.worker.maintenance import held_window
from app.modules.worker.ojol_jitter import is_ojol_jitter_active
from app.modules.worker.service import WORKER_SHUTDOWN
from app.modules.worker.settings import auto_flags, should_maintain_online_presence

if TYPE_CHECKING:
    from app.modules.worker.fleet import MultiAccountService


class FleetSupervisor:
    def __init__(self, fleet: MultiAccountService) -> None:
        self.fleet = fleet
        self.closing = False
        self.tasks: list[asyncio.Task[None]] = []
        self._last_presence_mono = 0.0
        self._sniper_last_check_mono: dict[str, float] = {}
        self._sniper_next_kosong_ts: dict[str, float] = {}

    def account_running(self, account) -> bool:
        service = self.fleet.services.get(account["id"])
        process = service.worker if service else None
        directory = self.fleet.registry.runtime_directory(account)
        return bool(
            (process and process.returncode is None)
            or ((directory / "run.lock").is_file() and running(directory))
        )

    def active_workers(self, owner=None) -> int:
        return sum(self.account_running(account) for account in self.fleet.registry.list(owner))

    def capacity_error(self, owner):
        return worker_capacity_error(self.fleet.registry, owner, self.active_workers)

    async def resume_workers(self) -> None:
        if (
            self.closing
            or not self.fleet.settings.auto_start
            or self.fleet.settings.env == "testing"
            or (self.fleet.settings.tunnel_enabled and not self.fleet.tunnel.is_alive())
        ):
            return
        async with self.fleet.lock:
            if held_window(self.fleet.maintenance_file):
                return
            owners = {row["id"]: row["owner"] for row in self.fleet.registry.list()}
            for service in list(self.fleet.services.values()):
                if not service.auto_start_pending:
                    continue
                if (
                    not self.fleet.registry.allowed(owners.get(service.account_id))
                    or (service.settings.runtime_dir / "STOP").exists()
                ):
                    service.auto_start_pending = False
                    continue
                if (service.worker and service.worker.returncode is None) or running(
                    service.settings.runtime_dir
                ):
                    service.auto_start_pending = False
                    continue
                if self.capacity_error(owners[service.account_id]):
                    continue
                service.auto_start_pending = False
                action = "Tekan Import Cookie, lalu Jalankan Ojol."
                try:
                    from app.integrations.kampung.session_transfer import parse_cookie_input

                    parse_cookie_input(
                        (service.settings.runtime_dir / "http-session.json").read_text()
                    )
                    flags = auto_flags(service.settings.runtime_dir)
                    if not any(flags.values()):
                        continue
                    action = (
                        "Minta admin memeriksa izin operator dan status server, lalu tekan Jalankan Ojol."
                        if flags.get("ojol")
                        else "Minta admin memeriksa izin operator dan status server, lalu tekan Jalankan Kebutuhan."
                    )
                    await service.command("run", auto_start=True)
                except WorkerCapacityError:
                    continue
                except Exception as exc:
                    queue_error(
                        service.settings,
                        exc,
                        "worker.auto_start",
                        {"tindakan": action, "account_id": service.account_id},
                    )

    async def maintain_online_presence(self) -> None:
        """Periodically refresh online presence for every account so all accounts remain online."""
        if self.closing or self.fleet.settings.env == "testing":
            return
        now_mono = time.monotonic()
        if now_mono - self._last_presence_mono < 30:
            return
        self._last_presence_mono = now_mono
        for row in self.fleet.registry.list():
            if not self.fleet.registry.allowed(row["owner"]):
                continue
            service = self.fleet.service(row["id"])
            directory = service.settings.runtime_dir
            if not (directory / "http-session.json").is_file():
                continue
            if is_ojol_jitter_active(directory):
                continue
            try:
                flags = auto_flags(directory)
            except ValueError:
                continue
            if not should_maintain_online_presence(flags):
                continue
            _data, status_updated = status_record(directory / "status.json")
            _online_data, online_updated = status_record(directory / "online-status.json")
            latest_touch = max(
                status_updated / 1e9 if status_updated else 0,
                online_updated / 1e9 if online_updated else 0,
            )
            is_worker_active = (service.worker and service.worker.returncode is None) or running(
                directory
            )
            if is_worker_active and (time.time() - latest_touch < 35):
                continue
            with contextlib.suppress(Exception):
                await service.fetch_online_status()

    async def run_job_sniper_cycle(self) -> None:
        """Run scheduled Job Sniper checks for accounts with Job Sniper enabled."""
        if self.closing or self.fleet.settings.env == "testing":
            return
        for row in self.fleet.registry.list():
            if not self.fleet.registry.allowed(row["owner"]):
                continue
            service = self.fleet.service(row["id"])
            directory = service.settings.runtime_dir
            if not (directory / "http-session.json").is_file():
                continue
            cfg = load_sniper_config(directory)
            if not cfg.get("enabled"):
                continue
            now_mono = time.monotonic()
            last_mono = self._sniper_last_check_mono.get(row["id"], 0.0)
            next_kosong_ts = self._sniper_next_kosong_ts.get(row["id"])
            kosong_due = next_kosong_ts is not None and time.time() >= next_kosong_ts
            if not kosong_due and (now_mono - last_mono < cfg["interval_seconds"]):
                continue
            self._sniper_last_check_mono[row["id"]] = now_mono
            with contextlib.suppress(Exception):
                res = await run_job_sniper_once(directory, settings=service.settings)
                if res.get("next_kosong_epoch") is not None:
                    self._sniper_next_kosong_ts[row["id"]] = float(res["next_kosong_epoch"])
                else:
                    self._sniper_next_kosong_ts.pop(row["id"], None)

    async def supervise(self) -> None:
        while not self.closing:
            await self.resume_workers()
            await self.maintain_online_presence()
            await self.run_job_sniper_cycle()
            if self.fleet.tunnel.take_exit() is not None:
                queue_error(
                    self.fleet.control_settings,
                    RuntimeError("Cloudflared berhenti"),
                    "tunnel.process_exit",
                )
                for service in list(self.fleet.services.values()):
                    await service.stop_worker()
            await asyncio.sleep(2)

    async def guard_task(self, operation: Callable[[], Awaitable[None]], stage: str) -> None:
        try:
            await operation()
        except Exception as exc:
            queue_error(self.fleet.control_settings, exc, stage)
            await asyncio.gather(
                *(s.stop_worker() for s in self.fleet.services.values()), return_exceptions=True
            )

    async def prepare(self) -> None:
        for row in self.fleet.registry.list():
            if self.fleet.registry.allowed(row["owner"]):
                service = self.fleet.service(row["id"])
                await self.fleet.ensure_started(service)
                if self.fleet.settings.env == "testing":
                    continue
                directory = service.settings.runtime_dir
                marker = directory / WORKER_SHUTDOWN
                has_session = (directory / "http-session.json").is_file()
                if (service.worker and service.worker.returncode is None) or running(directory):
                    # Worker is already active (e.g. in separate worker container) - do not disturb it.
                    marker.unlink(missing_ok=True)
                    continue
                if self.fleet.settings.auto_start and has_session:
                    # A new boot deliberately starts all eligible accounts, including previously stopped ones.
                    service.auto_start_pending = True
                    (directory / "STOP").unlink(missing_ok=True)
                    message = (
                        "♻️ Aplikasi kembali aktif\n\nBot menyiapkan akun setelah startup/restart "
                        "Docker. Aktivitas dilanjutkan setelah sesi dan status game diperiksa."
                    )
                    if maintenance := held_window(self.fleet.maintenance_file):
                        message += "\n\n" + maintenance.message()
                    queue_notice(service.settings, message)
                elif self.fleet.settings.auto_start or marker.exists():
                    action = "Jalankan Ojol" if has_session else "Import Cookie, lalu Jalankan Ojol"
                    reason = (
                        "sesi game belum terhubung"
                        if not has_session
                        else "mulai otomatis dimatikan"
                    )
                    queue_notice(
                        service.settings,
                        f"⚠️ Akun belum berjalan karena {reason}.\n\nTekan {action}.",
                    )
                marker.unlink(missing_ok=True)

    async def start(self) -> None:
        await self.resume_workers()
        self.tasks.append(
            asyncio.create_task(self.guard_task(self.supervise, "management.supervise"))
        )

    async def close(self) -> None:
        self.closing = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
