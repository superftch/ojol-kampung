"""Account-scoped web control and worker supervision."""

import asyncio
import contextlib
import time

from app.core.locks import running
from app.core.storage import status_record
from app.integrations.kampung.http_api import HttpCoreError, OjolHttpApi
from app.integrations.kampung.identity import save_profile, verified_profile
from app.modules.accounts.repository import Accounts
from app.modules.gameplay.study import save_skills
from app.modules.notifications.service import queue_error, queue_notice
from app.modules.worker.maintenance import SCHEDULE_FILE, held_window
from app.modules.worker.service import WORKER_SHUTDOWN, ControlService
from app.modules.worker.settings import auto_flags


class MultiAccountService:
    def __init__(self, settings):
        self.settings = settings
        self.registry = Accounts(settings)
        self.maintenance_file = settings.runtime_dir / SCHEDULE_FILE
        self.services = {}
        self.hub = ControlService(
            settings.model_copy(
                update={
                    "runtime_dir": settings.runtime_dir / "control",
                    "account_name": "",
                }
            )
        )
        self.tasks = []
        self.closing = False
        self.lock = asyncio.Lock()
        self.started = False

    def public_url(self):
        if self.settings.env == "production":
            return self.settings.login_public_url
        path = self.settings.runtime_dir / "public-url"
        from app.core.models import Settings

        return (
            Settings.secure_login_origin(path.read_text().strip())
            if path.is_file()
            else self.settings.login_public_url
        )

    def service(self, identifier):
        account = self.registry.get(identifier)
        if identifier not in self.services:
            service = ControlService(self.registry.scoped_settings(account))
            service.maintenance_file = self.maintenance_file
            service.url_prefix = f"/a/{identifier}"
            service.public_url = self.public_url
            service.account_id = identifier
            self.services[identifier] = service
        service = self.services[identifier]
        service.settings = self.registry.scoped_settings(account)
        return service

    async def ensure_started(self, service):
        if self.started and not service.tasks:
            await service.start()

    async def revoke_owner(self, owner: int) -> None:
        for account in self.registry.list(owner):
            identifier = account["id"]
            service = self.services.get(identifier)
            if service is None:
                service = ControlService(self.registry.scoped_settings(account))
                service.account_id = identifier
            try:
                await service.stop_worker()
            finally:
                service.access.revoke()

    async def start_tunnel(self):
        await self.hub.start_tunnel(self.settings.runtime_dir.parent / "cloudflared-token")

    def active_workers(self):
        return sum(
            bool(
                (service.worker and service.worker.returncode is None)
                or running(service.settings.runtime_dir)
            )
            for service in self.services.values()
        )

    def legacy(self):
        rows = [a for a in self.registry.list() if a["legacy"]]
        if not rows:
            raise ValueError("Akun lama tidak tersedia")
        return self.service(rows[0]["id"])

    async def refresh_account_profile(self, account):
        settings = self.registry.scoped_settings(account)
        if settings.env == "testing" or not (settings.runtime_dir / "http-session.json").is_file():
            return
        try:
            async with asyncio.timeout(6), OjolHttpApi(settings.runtime_dir) as api:
                me = await api.request("/api/game/me")
                save_profile(settings.runtime_dir, verified_profile(me))
                if isinstance(me.get("skill"), dict) and isinstance(
                    me["skill"].get("tracks"), list
                ):
                    save_skills(settings.runtime_dir, me["skill"]["tracks"])
        except (HttpCoreError, OSError, ValueError, TypeError, AttributeError, TimeoutError):
            return
        self.service(account["id"])

    async def resume_workers(self):
        if (
            self.closing
            or not self.settings.auto_start
            or self.settings.env == "testing"
            or (self.settings.tunnel_enabled and not self.hub.tunnel_alive())
        ):
            return
        async with self.lock:
            if held_window(self.maintenance_file):
                return
            owners = {row["id"]: row["owner"] for row in self.registry.list()}
            for service in list(self.services.values()):
                if not service.auto_start_pending:
                    continue
                if (
                    not self.registry.allowed(owners.get(service.account_id))
                    or (service.settings.runtime_dir / "STOP").exists()
                ):
                    service.auto_start_pending = False
                    continue
                if (service.worker and service.worker.returncode is None) or running(
                    service.settings.runtime_dir
                ):
                    service.auto_start_pending = False
                    continue
                if self.active_workers() >= self.registry.value("max_active_workers"):
                    return
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
                except Exception as exc:
                    queue_error(
                        service.settings,
                        exc,
                        "worker.auto_start",
                        {"tindakan": action, "account_id": service.account_id},
                    )

    async def fetch_all_online_status(self):
        """Fetch online presence status for every registered account with a session cookie."""
        results = {}
        for row in self.registry.list():
            if not self.registry.allowed(row["owner"]):
                continue
            service = self.service(row["id"])
            session_path = service.settings.runtime_dir / "http-session.json"
            if not session_path.is_file():
                results[row["id"]] = {
                    "name": row["name"],
                    "online": False,
                    "error": "Belum ada sesi cookie",
                }
                continue
            try:
                status = await service.fetch_online_status()
                results[row["id"]] = {
                    "name": row["name"],
                    "online": True,
                    "nickname": status.get("nickname"),
                    "server_time": status.get("server_time"),
                    "status": status,
                }
            except Exception as exc:
                results[row["id"]] = {
                    "name": row["name"],
                    "online": False,
                    "error": str(exc),
                }
        return results

    async def maintain_online_presence(self):
        """Periodically refresh online presence for every account so all accounts remain online."""
        if self.closing or self.settings.env == "testing":
            return
        now_mono = time.monotonic()
        if now_mono - getattr(self, "_last_presence_mono", 0) < 30:
            return
        self._last_presence_mono = now_mono
        for row in self.registry.list():
            if not self.registry.allowed(row["owner"]):
                continue
            service = self.service(row["id"])
            directory = service.settings.runtime_dir
            if not (directory / "http-session.json").is_file():
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

    async def supervise(self):
        while not self.closing:
            await self.resume_workers()
            await self.maintain_online_presence()
            if self.hub.tunnel_process and self.hub.tunnel_process.returncode is not None:
                self.hub.tunnel_process = None
                queue_error(
                    self.hub.settings, RuntimeError("Cloudflared berhenti"), "tunnel.process_exit"
                )
                for service in list(self.services.values()):
                    await service.stop_worker()
            await asyncio.sleep(2)

    async def guard_task(self, operation, stage):
        try:
            await operation()
        except Exception as exc:
            queue_error(self.hub.settings, exc, stage)
            await asyncio.gather(
                *(s.stop_worker() for s in self.services.values()), return_exceptions=True
            )

    async def start(self):
        self.started = True
        for row in self.registry.list():
            if self.registry.allowed(row["owner"]):
                service = self.service(row["id"])
                await self.ensure_started(service)
                if self.settings.env == "testing":
                    continue
                directory = service.settings.runtime_dir
                marker = directory / WORKER_SHUTDOWN
                has_session = (directory / "http-session.json").is_file()
                if (service.worker and service.worker.returncode is None) or running(directory):
                    # Worker is already active (e.g. in separate worker container) - do not disturb it.
                    marker.unlink(missing_ok=True)
                    continue
                if self.settings.auto_start and has_session:
                    # A new boot deliberately starts all eligible accounts, including previously stopped ones.
                    service.auto_start_pending = True
                    (directory / "STOP").unlink(missing_ok=True)
                    message = (
                        "♻️ Aplikasi kembali aktif\n\nBot menyiapkan akun setelah startup/restart "
                        "Docker. Aktivitas dilanjutkan setelah sesi dan status game diperiksa."
                    )
                    if maintenance := held_window(self.maintenance_file):
                        message += "\n\n" + maintenance.message()
                    queue_notice(service.settings, message)
                elif self.settings.auto_start or marker.exists():
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
        if self.settings.env == "testing":
            return
        try:
            await self.start_tunnel()
        except Exception as exc:
            queue_error(
                self.hub.settings,
                exc,
                "control.startup.tunnel",
                {"tindakan": "Periksa konfigurasi tunnel agar akun yang menunggu bisa auto-start."},
            )
        await self.resume_workers()
        self.tasks.append(
            asyncio.create_task(self.guard_task(self.supervise, "management.supervise"))
        )

    async def close(self):
        self.closing = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        results = await asyncio.gather(
            *(s.close(stop_workers=False) for s in self.services.values()),
            self.hub.close(stop_workers=False),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                raise result
