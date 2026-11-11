"""One Telegram poller, per-account HTTP workers, admin-managed whitelist."""

import asyncio
import re

from .accounts import Accounts
from .cli import running
from .control import ControlService
from .telegram import (
    BUTTON_COMMANDS,
    TelegramClient,
    TelegramError,
    flush_notices,
    queue_error,
    queue_notice,
)

HELP = (
    "Akun Saya: daftar/pilih akun. Tambah Akun: masukkan nama.\n"
    "/akun tambah Nama\n/akun pilih ID\n/akun nama ID Nama baru\n"
    "/akun arsip ID\n/akun pulihkan ID\n"
    "Tombol Import Cookie, Jalankan Ojol, Hentikan Ojol, Status, Laba Bersih berlaku untuk akun terpilih."
)
ADMIN_HELP = (
    "Admin:\n/users — whitelist dan kuota\n/whitelist tambah TELEGRAM_ID [BATAS]\n"
    "/whitelist hapus TELEGRAM_ID\n/batas default JUMLAH\n/batas worker JUMLAH\n"
    "/batas TELEGRAM_ID JUMLAH\nDefault/override tersimpan; turunkan batas tidak menghapus akun."
)


class MultiAccountService:
    def __init__(self, settings):
        self.settings = settings
        self.registry = Accounts(settings)
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
        self.pending = {}
        self.lock = asyncio.Lock()
        self.started = False

    def public_url(self):
        if self.settings.env == "production":
            return self.settings.login_public_url
        path = self.settings.runtime_dir / "public-url"
        from .models import Settings

        return (
            Settings.secure_login_origin(path.read_text().strip())
            if path.is_file()
            else self.settings.login_public_url
        )

    def notice_settings(self, owner):
        settings = self.settings.model_copy(
            update={
                "runtime_dir": self.settings.runtime_dir / "control" / "users" / str(owner),
                "telegram_chat_id": owner,
                "account_name": "",
            }
        )
        settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return settings

    async def reply(self, owner, text, markup=None):
        settings = self.notice_settings(owner)
        queue_notice(settings, text, reply_markup=markup)
        await flush_notices(settings)

    def service(self, identifier):
        account = self.registry.get(identifier)
        if identifier not in self.services:
            service = ControlService(self.registry.scoped_settings(account))
            service.url_prefix = f"/a/{identifier}"
            service.public_url = self.public_url
            # Finance buttons retain account identity even after user switches selection.
            service.account_id = identifier
            self.services[identifier] = service
        service = self.services[identifier]
        service.settings = self.registry.scoped_settings(account)
        return service

    async def ensure_started(self, service):
        if self.started and not service.tasks:
            await service.start(poll=False)

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

    async def accounts(self, owner):
        selected = self.registry.selected(owner)
        rows = self.registry.list(owner)
        lines = [f"Akun Anda: {len(rows)}/{self.registry.quota(owner)}"]
        buttons = []
        for row in rows:
            service = self.service(row["id"])
            active = bool(
                (service.worker and service.worker.returncode is None)
                or running(service.settings.runtime_dir)
            )
            lines.append(
                f"{'✓' if selected and selected['id'] == row['id'] else '•'} {row['name']} · {'aktif' if active else 'stop'}\nID: {row['id']}"
            )
            buttons.append(
                [{"text": f"Pilih {row['name']}", "callback_data": "select:" + row["id"]}]
            )
        archived = self.registry.list(owner, archived=True)
        lines.extend(f"Arsip: {a['name']} · {a['id']}" for a in archived)
        await self.reply(owner, "\n".join(lines), {"inline_keyboard": buttons} if buttons else None)

    async def revoke(self, owner):
        owner = self.registry.owner_id(owner)
        # Block new commands/imports before waiting for workers to stop.
        self.registry.whitelist(owner, False)
        self.pending.pop(owner, None)
        errors = []
        for row in self.registry.list(owner):
            service = self.services.get(row["id"])
            if service is None:
                service = ControlService(self.registry.scoped_settings(row))
            service.access.revoke()
            try:
                await service.close()
            except Exception as exc:
                errors.append(type(exc).__name__)
            for notice in (service.settings.runtime_dir / "notifications").glob("*.json"):
                notice.rename(notice.with_suffix(".revoked"))
            self.services.pop(row["id"], None)
        for notice in (self.notice_settings(owner).runtime_dir / "notifications").glob("*.json"):
            notice.rename(notice.with_suffix(".revoked"))
        if errors:
            raise RuntimeError(
                "Akses dicabut; sebagian worker belum terkonfirmasi berhenti. Periksa server."
            )

    async def dispatch(self, owner, text, callback=False):
        if not self.registry.allowed(owner):
            return
        async with self.lock:
            try:
                await self._dispatch(owner, text.strip(), callback)
            except (ValueError, OverflowError) as exc:
                await self.reply(
                    owner, str(exc) if not isinstance(exc, OverflowError) else "Tanggal tidak valid"
                )
            except Exception as exc:
                queue_error(self.hub.settings, exc, "management.command")
                await self.reply(
                    owner,
                    "Perintah gagal. Periksa status akun atau hubungi admin.",
                )

    async def _dispatch(self, owner, text, callback):
        if text in {"/admin", "Management", "/users"} or text.startswith(("/whitelist", "/batas")):
            self.pending.pop(owner, None)
            if owner != self.registry.admin:
                raise ValueError("Management hanya untuk admin dari env")
            parts = text.split()
            if parts[:2] == ["/whitelist", "tambah"] and len(parts) in {3, 4}:
                self.registry.whitelist(parts[2], maximum=parts[3] if len(parts) == 4 else None)
                await self.reply(owner, "Whitelist diperbarui.")
            elif parts[:2] == ["/whitelist", "hapus"] and len(parts) == 3:
                await self.revoke(parts[2])
                await self.reply(
                    owner,
                    "Akses dicabut; seluruh worker user berhenti, link import dicabut. Data disimpan.",
                )
            elif parts[:1] == ["/batas"] and len(parts) == 3:
                if parts[1] in {"default", "worker"}:
                    self.registry.set_limit(
                        "max_accounts_per_user" if parts[1] == "default" else "max_active_workers",
                        parts[2],
                    )
                else:
                    user = self.registry.owner_id(parts[1])
                    if not self.registry.allowed(user):
                        raise ValueError("User belum masuk whitelist")
                    self.registry.whitelist(user, maximum=parts[2])
                await self.reply(
                    owner,
                    "Batas diperbarui. Akun/worker yang sudah ada tetap; start/tambah berikutnya mengikuti batas baru.",
                )
            else:
                lines = [
                    ADMIN_HELP,
                    f"Default akun/user: {self.registry.value('max_accounts_per_user')} · Worker aktif: {self.active_workers()}/{self.registry.value('max_active_workers')}",
                ]
                for user in self.registry.users():
                    uid = user["telegram_id"]
                    lines.append(
                        f"{uid} · {'admin' if uid == self.registry.admin else 'whitelist' if user['enabled'] else 'dicabut'} · {len(self.registry.list(uid))}/{self.registry.quota(uid)} akun"
                    )
                await self.reply(owner, "\n".join(lines))
            return
        if text in {"Akun Saya", "/akun"}:
            self.pending.pop(owner, None)
            await self.accounts(owner)
            return
        if text == "Tambah Akun":
            self.pending[owner] = "name"
            await self.reply(owner, "Ketik nama akun baru (1–40 karakter), atau /batal.")
            return
        if text == "/batal":
            self.pending.pop(owner, None)
            await self.reply(owner, "Input dibatalkan.")
            return
        if (
            self.pending.get(owner) == "name"
            and not callback
            and not text.startswith("/")
            and text not in BUTTON_COMMANDS
        ):
            row = self.registry.create(owner, text)
            self.pending.pop(owner, None)
            await self.reply(owner, f"Akun {row['name']} dibuat dan dipilih. Tekan Import Cookie.")
            return
        if text.startswith("select:") and callback:
            self.pending.pop(owner, None)
            self.registry.select(owner, text.split(":", 1)[1])
            await self.accounts(owner)
            return
        if text.startswith("/akun "):
            self.pending.pop(owner, None)
            parts = text.split(maxsplit=3)
            if parts[1] == "tambah" and len(parts) >= 3:
                row = self.registry.create(owner, text.split(maxsplit=2)[2])
                await self.reply(
                    owner, f"Akun {row['name']} dibuat dan dipilih. Tekan Import Cookie."
                )
            elif parts[1] == "pilih" and len(parts) == 3:
                self.registry.select(owner, parts[2])
                await self.accounts(owner)
            elif parts[1] == "nama" and len(parts) == 4:
                self.registry.rename(owner, parts[2], parts[3])
                if parts[2] in self.services:
                    self.service(parts[2])
                await self.accounts(owner)
            elif parts[1] == "arsip" and len(parts) == 3:
                row = self.registry.get(parts[2], owner)
                service = self.service(row["id"])
                async with service.lock:
                    service.access.revoke()
                    await service.close()
                    self.registry.archive(owner, row["id"])
                    self.services.pop(row["id"], None)
                await self.accounts(owner)
            elif parts[1] == "pulihkan" and len(parts) == 3:
                self.registry.archive(owner, parts[2], archived=False)
                await self.accounts(owner)
            else:
                await self.reply(owner, HELP)
            return
        account = None
        if callback and text.startswith("acct:"):
            _, identifier, text = text.split(":", 2)
            account = self.registry.get(identifier, owner)
        elif callback:
            # Old unscoped finance buttons cannot select another account implicitly.
            return
        if text in {"/start", "/help", "Bantuan"}:
            self.pending.pop(owner, None)
            await self.reply(
                owner, HELP + ("\n" + ADMIN_HELP if owner == self.registry.admin else "")
            )
            return
        account = account or self.registry.selected(owner)
        if account is None:
            await self.reply(owner, "Belum ada akun terpilih. Tekan Tambah Akun atau Akun Saya.")
            return
        service = self.service(account["id"])
        await self.ensure_started(service)
        command = BUTTON_COMMANDS.get(text)
        if callback:
            if text == "choose_date" or re.fullmatch(r"profit:\d{4}-\d{2}-\d{2}", text):
                command = text
        elif self.pending.get(owner, "").startswith("date:") and text not in BUTTON_COMMANDS:
            identifier = self.pending.pop(owner).split(":", 1)[1]
            service = self.service(self.registry.get(identifier, owner)["id"])
            command = "profit:" + text
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}", text):
            command = "profit:" + text
        if command == "choose_date":
            self.pending[owner] = "date:" + account["id"]
        elif command:
            self.pending.pop(owner, None)
        if command in {"run", "import_cookie"}:
            if command == "run" and not (
                (service.worker and service.worker.returncode is None)
                or running(service.settings.runtime_dir)
            ):
                if self.active_workers() >= self.registry.value("max_active_workers"):
                    raise ValueError(
                        "Batas worker aktif global tercapai. Hentikan akun lain atau hubungi admin."
                    )
            await self.start_tunnel()
        await service.execute(command or "help")

    async def poll_telegram(self):
        cursor = self.settings.runtime_dir / "telegram-offset"
        offset = int(cursor.read_text()) if cursor.exists() else 0
        outage = False
        async with TelegramClient(self.settings) as api:
            while not self.closing:
                try:
                    updates = await api.call(
                        "getUpdates",
                        offset=offset,
                        timeout=20,
                        allowed_updates=["message", "callback_query"],
                    )
                    outage = False
                    for update in updates:
                        callback = update.get("callback_query")
                        message = (
                            callback.get("message", {}) if callback else update.get("message", {})
                        )
                        sender = (
                            callback.get("from", {}) if callback else message.get("from", {})
                        ).get("id")
                        chat = message.get("chat", {})
                        if (
                            chat.get("type") == "private"
                            and chat.get("id") == sender
                            and self.registry.allowed(sender)
                        ):
                            if callback:
                                await api.call(
                                    "answerCallbackQuery", callback_query_id=callback["id"]
                                )
                            await self.dispatch(
                                sender,
                                callback.get("data", "") if callback else message.get("text", ""),
                                bool(callback),
                            )
                        offset = max(offset, update["update_id"] + 1)
                        cursor.write_text(str(offset))
                except (TelegramError, OSError, ValueError) as exc:
                    if not outage:
                        queue_error(self.hub.settings, exc, "telegram.poll")
                        await asyncio.gather(
                            *(s.stop_worker() for s in self.services.values()),
                            return_exceptions=True,
                        )
                    outage = True
                    await asyncio.sleep(15)

    async def supervise(self):
        while not self.closing:
            if self.hub.tunnel_process and self.hub.tunnel_process.returncode is not None:
                self.hub.tunnel_process = None
                queue_error(
                    self.hub.settings, RuntimeError("Cloudflared berhenti"), "tunnel.process_exit"
                )
                for service in list(self.services.values()):
                    await service.stop_worker()
            await flush_notices(self.hub.settings)
            for user in self.registry.users():
                if self.registry.allowed(user["telegram_id"]):
                    await flush_notices(self.notice_settings(user["telegram_id"]))
            await asyncio.sleep(2)

    async def guard_task(self, operation, stage):
        try:
            await operation()
        except Exception as exc:
            queue_error(self.hub.settings, exc, stage)
            await asyncio.gather(
                *(s.stop_worker() for s in self.services.values()), return_exceptions=True
            )
            await flush_notices(self.hub.settings)

    async def start(self):
        self.started = True
        for row in self.registry.list():
            if self.registry.allowed(row["owner"]):
                await self.ensure_started(self.service(row["id"]))
        if self.settings.env == "testing":
            return
        try:
            await self.start_tunnel()
        except Exception as exc:
            queue_error(self.hub.settings, exc, "control.startup.tunnel")
        self.tasks.append(
            asyncio.create_task(self.guard_task(self.supervise, "management.supervise"))
        )
        if self.settings.telegram_bot_token.get_secret_value() and self.registry.admin:
            self.tasks.append(
                asyncio.create_task(self.guard_task(self.poll_telegram, "telegram.poll"))
            )

    async def close(self):
        self.closing = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        results = await asyncio.gather(
            *(s.close() for s in self.services.values()), self.hub.close(), return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                raise result
