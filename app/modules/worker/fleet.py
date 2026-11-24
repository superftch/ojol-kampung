"""Account-scoped web control and application lifecycle."""

import asyncio

from app.core.models import Settings
from app.integrations.cloudflared import CloudflaredTunnel
from app.integrations.kampung.http_api import HttpCoreError, OjolHttpApi
from app.integrations.kampung.identity import save_profile, verified_profile
from app.modules.accounts.repository import Accounts
from app.modules.gameplay.study import save_skills
from app.modules.notifications.service import queue_error
from app.modules.worker.fleet_supervision import FleetSupervisor
from app.modules.worker.maintenance import SCHEDULE_FILE
from app.modules.worker.service import ControlService


class MultiAccountService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = Accounts(settings)
        self.maintenance_file = settings.runtime_dir / SCHEDULE_FILE
        self.services: dict[str, ControlService] = {}
        self.control_settings = settings.model_copy(
            update={"runtime_dir": settings.runtime_dir / "control", "account_name": ""}
        )
        self.tunnel = CloudflaredTunnel()
        self.supervisor = FleetSupervisor(self)
        self.lock = asyncio.Lock()
        self.started = False

    def public_url(self):
        if self.settings.env == "production":
            return self.settings.login_public_url
        path = self.settings.runtime_dir / "public-url"
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

    async def start_tunnel(self) -> None:
        await self.tunnel.start(
            enabled=self.settings.tunnel_enabled,
            token_file=self.settings.runtime_dir.parent / "cloudflared-token",
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

    async def start(self) -> None:
        self.started = True
        await self.supervisor.prepare()
        if self.settings.env == "testing":
            return
        try:
            await self.start_tunnel()
        except Exception as exc:
            queue_error(
                self.control_settings,
                exc,
                "control.startup.tunnel",
                {"tindakan": "Periksa konfigurasi tunnel agar akun yang menunggu bisa auto-start."},
            )
        await self.supervisor.start()

    async def close(self) -> None:
        await self.supervisor.close()
        results = await asyncio.gather(
            *(s.close(stop_workers=False) for s in self.services.values()),
            self.tunnel.close(),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                raise result
