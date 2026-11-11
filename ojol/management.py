"""One Telegram poller, per-account HTTP workers, admin-managed whitelist."""

import asyncio
import re

from .accounts import Accounts
from .auto_settings import AUTO_LABELS, auto_flags, set_auto_flag
from .cli import running
from .control import WORKER_SHUTDOWN, ControlService
from .healing import write_private
from .maintenance import GAME_COMMANDS, SCHEDULE_FILE, MaintenanceWindow, held_window, read_window
from .telegram import (
    BUTTON_COMMANDS,
    KEYBOARD,
    TelegramClient,
    TelegramError,
    flush_notices,
    queue_error,
    queue_notice,
)

HELP = (
    "🏠 Menu utama\n\n"
    "Akun baru? Tekan Tambah Akun, beri nama, lalu Import Cookie.\n"
    "Sudah siap? Tekan Jalankan Ojol.\n\n"
    "Auto untuk memilih aktivitas yang berjalan.\n"
    "Status untuk melihat kondisi akun.\n"
    "Laba Bersih untuk melihat hasil dan pengeluaran.\n\n"
    "Akun Saya untuk memilih atau mengelola akun."
)
CANCEL = {"inline_keyboard": [[{"text": "Batal", "callback_data": "cancel"}]]}
PAGE_SIZE = 8
ACCESS_REQUEST = {
    "inline_keyboard": [[{"text": "Ajukan Akses", "callback_data": "access:request"}]]
}
ACCESS_STATUS = {
    "inline_keyboard": [[{"text": "Cek Status Pengajuan", "callback_data": "access:status"}]]
}


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
        notice = queue_notice(settings, text, reply_markup=markup)
        await flush_notices(settings)
        return notice.with_suffix(".sent").is_file()

    def service(self, identifier):
        account = self.registry.get(identifier)
        if identifier not in self.services:
            service = ControlService(self.registry.scoped_settings(account))
            service.maintenance_file = self.maintenance_file
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

    async def home(self, owner):
        self.pending.pop(owner, None)
        account = self.registry.selected(owner)
        selected = f"\n\nAkun terpilih • {account['name']}" if account else ""
        await self.reply(owner, HELP + selected, KEYBOARD)

    async def prompt(self, owner, state, text):
        self.pending[owner] = state
        await self.reply(owner, text, CANCEL)

    async def accounts(self, owner, page=0):
        selected = self.registry.selected(owner)
        active = self.registry.list(owner)
        rows = active + self.registry.list(owner, archived=True)
        page = min(max(0, page), max(0, (len(rows) - 1) // PAGE_SIZE))
        lines = [
            "👤 Akun Saya",
            f"{len(active)} dari {self.registry.quota(owner)} slot akun terpakai.",
            "",
        ]
        buttons = []
        for row in rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
            if row["archived"]:
                lines.append(f"📁 {row['name']} • diarsipkan")
                label, action = f"Pulihkan {row['name']}", "restore:"
            else:
                service = self.service(row["id"])
                running_now = bool(
                    (service.worker and service.worker.returncode is None)
                    or running(service.settings.runtime_dir)
                )
                mark = "✓" if selected and selected["id"] == row["id"] else "•"
                lines.append(f"{mark} {row['name']} • {'berjalan' if running_now else 'berhenti'}")
                label, action = f"Pilih {row['name']}", "select:"
            buttons.append([{"text": label, "callback_data": action + row["id"]}])
        navigation = []
        if page:
            navigation.append({"text": "◀ Sebelumnya", "callback_data": f"accounts:{page - 1}"})
        if (page + 1) * PAGE_SIZE < len(rows):
            navigation.append({"text": "Berikutnya ▶", "callback_data": f"accounts:{page + 1}"})
        if navigation:
            buttons.append(navigation)
        buttons.extend(
            [
                [{"text": "Tambah Akun", "callback_data": "add_account"}],
                [{"text": "Menu Utama", "callback_data": "home"}],
            ]
        )
        await self.reply(owner, "\n".join(lines), {"inline_keyboard": buttons})

    async def account_menu(self, owner, identifier):
        row = self.registry.get(identifier, owner)
        selected = self.registry.selected(owner)
        buttons = [
            [{"text": "Auto", "callback_data": f"acct:{identifier}:auto"}],
            [
                {"text": "Ubah Nama", "callback_data": "rename:" + identifier},
                {"text": "Arsipkan Akun", "callback_data": "archive:" + identifier},
            ],
            [
                {"text": "Akun Saya", "callback_data": "accounts:0"},
                {"text": "Menu Utama", "callback_data": "home"},
            ],
        ]
        if not selected or selected["id"] != identifier:
            buttons.insert(0, [{"text": "Pilih Akun Ini", "callback_data": "select:" + identifier}])
        await self.reply(
            owner,
            f"👤 {row['name']}\n\n"
            f"Akun terpilih • {selected['name'] if selected else 'belum ada'}\n"
            "Pilih pengaturan akun di bawah.",
            {"inline_keyboard": buttons},
        )

    async def auto_menu(self, owner, account, action="auto"):
        directory = self.registry.scoped_settings(account).runtime_dir
        parts = action.split(":")
        if len(parts) == 3 and parts[1] in AUTO_LABELS and parts[2] in {"0", "1"}:
            set_auto_flag(directory, parts[1], parts[2] == "1")
        elif action != "auto":
            return
        flags = auto_flags(directory)
        identifier = account["id"]
        buttons = [
            {
                "text": f"{label} {'ON' if flags[key] else 'OFF'}",
                "callback_data": f"acct:{identifier}:auto:{key}:{int(not flags[key])}",
            }
            for key, label in AUTO_LABELS.items()
        ]
        await self.reply(
            owner,
            f"⚙️ Auto · {account['name']}\n\n"
            "Auto Ojol mengurus trip, kondisi mesin, bensin, dan kuota.\n"
            "Kebutuhan lain bisa diatur satu per satu.\n\n"
            "ON berarti aktif. Tekan tombol untuk mengubahnya.\n"
            "Pilihan tersimpan dan berlaku saat bot berjalan.",
            {
                "inline_keyboard": [
                    [buttons[0]],
                    buttons[1:3],
                    buttons[3:5],
                    buttons[5:],
                    [{"text": "Akun Saya", "callback_data": "accounts:0"}],
                ]
            },
        )

    async def admin_menu(self, owner):
        await self.reply(
            owner,
            "🛠 Management\n\n"
            f"Batas awal per pengguna • {self.registry.value('max_accounts_per_user')} akun\n"
            f"Akun berjalan • {self.active_workers()} dari {self.registry.value('max_active_workers')}\n\n"
            "Kelola akses, batas akun, dan jadwal maintenance.",
            {
                "inline_keyboard": [
                    [
                        {"text": "Daftar User", "callback_data": "admin:users:0"},
                        {"text": "Tambah User", "callback_data": "admin:add_user"},
                    ],
                    [{"text": "Pengajuan Akses", "callback_data": "admin:requests:0"}],
                    [{"text": "Batas Akun Default", "callback_data": "admin:default_limit"}],
                    [{"text": "Batas Worker", "callback_data": "admin:worker_limit"}],
                    [{"text": "Maintenance", "callback_data": "admin:maintenance"}],
                    [{"text": "Menu Utama", "callback_data": "home"}],
                ]
            },
        )

    async def maintenance_menu(self, owner):
        window = read_window(self.maintenance_file)
        status = window.description() if window else "Belum ada jadwal."
        await self.reply(
            owner,
            f"🛠 Maintenance game\n\n{status}\n\n"
            "Atur waktu mulai dan selesai dalam WIB. Bot akan menjeda aktivitas dua menit sebelumnya.",
            {
                "inline_keyboard": [
                    [{"text": "Atur Jadwal", "callback_data": "admin:maintenance:set"}],
                    [{"text": "Hapus / Akhiri", "callback_data": "admin:maintenance:clear"}],
                    [{"text": "Management", "callback_data": "admin:menu"}],
                ]
            },
        )

    def user(self, identifier):
        identifier = self.registry.owner_id(identifier)
        row = next((u for u in self.registry.users() if u["telegram_id"] == identifier), None)
        if row is None:
            raise ValueError("User tidak tersedia. Tambahkan melalui Tambah User.")
        return row

    async def users_menu(self, owner, page=0):
        users = self.registry.users()
        page = min(max(0, page), max(0, (len(users) - 1) // PAGE_SIZE))
        buttons = []
        for user in users[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
            uid = user["telegram_id"]
            status = (
                "admin" if uid == self.registry.admin else "aktif" if user["enabled"] else "dicabut"
            )
            buttons.append([{"text": f"{uid} · {status}", "callback_data": f"user:{uid}"}])
        navigation = []
        if page:
            navigation.append({"text": "◀ Sebelumnya", "callback_data": f"admin:users:{page - 1}"})
        if (page + 1) * PAGE_SIZE < len(users):
            navigation.append({"text": "Berikutnya ▶", "callback_data": f"admin:users:{page + 1}"})
        if navigation:
            buttons.append(navigation)
        buttons.append([{"text": "Kembali ke Management", "callback_data": "admin:menu"}])
        await self.reply(
            owner,
            f"👥 Daftar User • halaman {page + 1}\n\nPilih pengguna untuk mengatur akses dan batas akun.",
            {"inline_keyboard": buttons},
        )

    async def user_menu(self, owner, identifier):
        user = self.user(identifier)
        uid = user["telegram_id"]
        enabled = self.registry.allowed(uid)
        buttons = [[{"text": "Ubah Batas Akun", "callback_data": f"user_limit:{uid}"}]]
        if enabled:
            buttons.append([{"text": "Kirim Menu", "callback_data": f"send_menu:{uid}"}])
        if uid != self.registry.admin:
            buttons.append(
                [
                    {
                        "text": "Cabut Akses" if enabled else "Aktifkan Akses",
                        "callback_data": f"revoke:{uid}" if enabled else f"enable:{uid}",
                    }
                ]
            )
        buttons.append([{"text": "Daftar User", "callback_data": "admin:users:0"}])
        await self.reply(
            owner,
            f"👤 Pengguna {uid}\n\n"
            f"Akses • {'admin' if uid == self.registry.admin else 'aktif' if enabled else 'dicabut'}\n"
            f"Akun • {len(self.registry.list(uid))} dari {self.registry.quota(uid)} slot terpakai\n\n"
            "Pilih tindakan di bawah.",
            {"inline_keyboard": buttons},
        )

    async def public_access(self, owner, text, callback, profile):
        if not (
            (not callback and text.split(maxsplit=1)[0:1] == ["/start"])
            or (callback and text in {"access:request", "access:status"})
        ):
            return
        request = self.registry.access_request(owner)
        created = False
        if callback and text == "access:request" and request is None:
            if not self.registry.admin:
                await self.reply(
                    owner, "Pengajuan belum tersedia. Hubungi pengelola bot.", ACCESS_STATUS
                )
                return
            profile = profile if profile.get("id") == owner else {}
            name = " ".join(str(profile.get(key) or "") for key in ("first_name", "last_name"))
            request, created = self.registry.request_access(
                owner, name, str(profile.get("username") or "")
            )
        if request is None:
            await self.reply(
                owner,
                "👋 Selamat datang\n\nAkun Telegram ini belum punya akses. "
                "Tekan Ajukan Akses untuk meminta persetujuan admin.",
                ACCESS_REQUEST,
            )
        elif request["status"] == "pending":
            await self.reply(
                owner,
                "⏳ Pengajuan sudah diterima\n\nPengajuan Anda menunggu persetujuan admin. "
                "Tekan Cek Status Pengajuan untuk melihat perkembangannya.",
                ACCESS_STATUS,
            )
        else:
            await self.reply(
                owner,
                "🔒 Akses belum aktif\n\nPengajuan ditolak atau akses dicabut. "
                "Hubungi admin jika ingin mengaktifkan akses.",
                ACCESS_STATUS,
            )
        if created:
            await self.request_menu(self.registry.admin, request["id"])

    async def requests_menu(self, owner, page=0):
        rows = self.registry.access_requests()
        page = min(max(0, page), max(0, (len(rows) - 1) // PAGE_SIZE))
        buttons = [
            [
                {
                    "text": f"{r['name'][:30]} · {r['telegram_id']}",
                    "callback_data": "request:" + r["id"],
                }
            ]
            for r in rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
        ]
        navigation = []
        if page:
            navigation.append(
                {"text": "◀ Sebelumnya", "callback_data": f"admin:requests:{page - 1}"}
            )
        if (page + 1) * PAGE_SIZE < len(rows):
            navigation.append(
                {"text": "Berikutnya ▶", "callback_data": f"admin:requests:{page + 1}"}
            )
        if navigation:
            buttons.append(navigation)
        buttons.append([{"text": "Kembali ke Management", "callback_data": "admin:menu"}])
        await self.reply(
            owner,
            f"📩 Pengajuan Akses • halaman {page + 1}\n\n"
            f"{len(rows)} pengajuan menunggu persetujuan. Pilih nama untuk meninjau.",
            {"inline_keyboard": buttons},
        )

    async def request_menu(self, owner, identifier):
        row = self.registry.request_by_id(identifier)
        buttons = []
        if row["status"] == "pending":
            buttons.append(
                [
                    {"text": "Setujui", "callback_data": "approve_request:" + identifier},
                    {"text": "Tolak", "callback_data": "reject_request:" + identifier},
                ]
            )
        buttons.append([{"text": "Daftar Pengajuan", "callback_data": "admin:requests:0"}])
        status = {"pending": "menunggu", "approved": "disetujui", "rejected": "ditolak"}[
            row["status"]
        ]
        await self.reply(
            owner,
            f"📩 Pengajuan Akses\n\n{row['name']}\n"
            f"Username • {'@' + row['username'] if row['username'] else 'belum diisi'}\n"
            f"Telegram ID • {row['telegram_id']}\n"
            f"Status • {status}",
            {"inline_keyboard": buttons},
        )

    async def send_user_menu(self, owner, uid):
        if not self.registry.allowed(uid):
            raise ValueError("Aktifkan akses user dahulu.")
        delivered = await self.reply(
            uid,
            "✅ Akses Anda sudah diaktifkan\n\n" + HELP,
            KEYBOARD,
        )
        await self.reply(
            owner,
            f"Menu utama dikirim ke {uid}."
            if delivered
            else f"Akses untuk {uid} sudah aktif, tetapi menu belum terkirim.\n\n"
            "Minta pengguna membuka chat pribadi bot dan menekan Start. "
            "Pastikan ID Telegram sesuai. Bot akan mencoba mengirim menu lagi.",
        )

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
                "Akses sudah dicabut, tetapi beberapa aktivitas belum dipastikan berhenti. "
                "Minta admin memeriksa akun yang masih berjalan."
            )

    async def dispatch(self, owner, text, callback=False, profile=None):
        if type(owner) is not int or owner <= 0:
            return
        async with self.lock:
            try:
                if not self.registry.allowed(owner):
                    await self.public_access(owner, text.strip(), callback, profile or {})
                    return
                await self._dispatch(owner, text.strip(), callback)
            except (ValueError, OverflowError) as exc:
                await self.reply(
                    owner,
                    str(exc) if not isinstance(exc, OverflowError) else "Tanggal tidak valid",
                    (CANCEL if owner in self.pending else KEYBOARD)
                    if self.registry.allowed(owner)
                    else ACCESS_STATUS,
                )
            except Exception as exc:
                queue_error(self.hub.settings, exc, "management.command")
                await self.reply(
                    owner,
                    "⚠️ Permintaan belum berhasil\n\nTekan Status untuk memeriksa akun. "
                    "Hubungi admin jika kendala berulang.",
                )

    async def admin_action(self, owner, text):
        if owner != self.registry.admin:
            raise ValueError("Management hanya tersedia untuk admin bot.")
        if text.startswith("revoke_confirm:"):
            uid = self.registry.owner_id(text.split(":", 1)[1])
            if self.pending.get(owner) != {"kind": "revoke", "user": uid}:
                raise ValueError("Konfirmasi kedaluwarsa. Pilih user lagi.")
            self.pending.pop(owner)
            await self.revoke(uid)
            await self.reply(
                owner,
                "🔒 Akses sudah dicabut\n\nSemua aktivitas pengguna dihentikan dan tautan "
                "Import Cookie ditutup. Riwayat akun tetap bisa ditinjau admin.",
            )
            await self.user_menu(owner, uid)
            return
        self.pending.pop(owner, None)
        if text in {"Management", "admin:menu"}:
            await self.admin_menu(owner)
        elif text == "admin:maintenance":
            await self.maintenance_menu(owner)
        elif text == "admin:maintenance:set":
            await self.prompt(
                owner,
                {"kind": "maintenance"},
                "📅 Kapan maintenance berlangsung?\n\n"
                "Kirim waktu mulai dan selesai dalam WIB.\n"
                "Format\nYYYY-MM-DD HH:MM / YYYY-MM-DD HH:MM\n\n"
                "Bot mulai menjeda aktivitas dua menit sebelumnya.",
            )
        elif text == "admin:maintenance:clear":
            self.maintenance_file.unlink(missing_ok=True)
            await self.maintenance_menu(owner)
        elif text.startswith("admin:requests:"):
            await self.requests_menu(owner, int(text.rsplit(":", 1)[1]))
        elif text.startswith("request:"):
            await self.request_menu(owner, text.split(":", 1)[1])
        elif text.startswith(("approve_request:", "reject_request:")):
            action, identifier = text.split(":", 1)
            row = self.registry.review_request(
                identifier, owner, approve=action == "approve_request"
            )
            if row["status"] == "approved":
                await self.send_user_menu(owner, row["telegram_id"])
            else:
                await self.reply(
                    row["telegram_id"],
                    "Pengajuan akses Anda ditolak oleh admin. Hubungi admin jika perlu peninjauan.",
                    ACCESS_STATUS,
                )
            await self.request_menu(owner, identifier)
        elif text.startswith("admin:users:"):
            await self.users_menu(owner, int(text.rsplit(":", 1)[1]))
        elif text == "admin:add_user":
            await self.prompt(
                owner,
                {"kind": "add_user"},
                "👤 Siapa yang ingin diberi akses?\n\nKirim ID Telegram pengguna berupa angka positif.",
            )
        elif text in {"admin:default_limit", "admin:worker_limit"}:
            name = (
                "max_accounts_per_user" if text == "admin:default_limit" else "max_active_workers"
            )
            await self.prompt(
                owner,
                {"kind": "limit", "setting": name},
                "🔢 Berapa batas barunya?\n\nKirim angka dari 1 sampai 100. "
                "Batas ini berlaku saat akun ditambahkan atau mulai berjalan berikutnya.",
            )
        elif text.startswith("user:"):
            await self.user_menu(owner, text.split(":", 1)[1])
        elif text.startswith("user_limit:"):
            user = self.user(text.split(":", 1)[1])
            if not self.registry.allowed(user["telegram_id"]):
                raise ValueError("Aktifkan akses user dahulu.")
            await self.prompt(
                owner,
                {"kind": "user_limit", "user": user["telegram_id"]},
                f"🔢 Atur batas akun untuk {user['telegram_id']}\n\nKirim angka dari 1 sampai 100.",
            )
        elif text.startswith("revoke:"):
            uid = self.user(text.split(":", 1)[1])["telegram_id"]
            if uid == self.registry.admin:
                raise ValueError("Akses admin utama tidak bisa dicabut lewat bot.")
            self.pending[owner] = {"kind": "revoke", "user": uid}
            await self.reply(
                owner,
                f"🔒 Cabut akses pengguna {uid}?\n\n"
                "Semua aktivitasnya akan dihentikan dan tautan Import Cookie ditutup. "
                "Riwayat akun tetap disimpan.\n\nPilih Ya, Cabut Akses untuk melanjutkan.",
                {
                    "inline_keyboard": [
                        [{"text": "Ya, Cabut Akses", "callback_data": f"revoke_confirm:{uid}"}],
                        [{"text": "Batal", "callback_data": "cancel"}],
                    ]
                },
            )
        elif text.startswith("send_menu:"):
            uid = self.user(text.split(":", 1)[1])["telegram_id"]
            await self.send_user_menu(owner, uid)
            await self.user_menu(owner, uid)
        elif text.startswith("enable:"):
            uid = self.user(text.split(":", 1)[1])["telegram_id"]
            self.registry.whitelist(uid)
            await self.send_user_menu(owner, uid)
            await self.user_menu(owner, uid)

    async def input(self, owner, text):
        state = self.pending[owner]
        kind = state["kind"]
        if (
            kind in {"add_user", "limit", "user_limit", "maintenance"}
            and owner != self.registry.admin
        ):
            raise ValueError("Management hanya tersedia untuk admin bot.")
        if kind == "name":
            row = self.registry.create(owner, text)
            self.pending.pop(owner)
            await self.reply(
                owner,
                f"✅ Akun {row['name']} sudah dibuat\n\nAkun ini sekarang terpilih. "
                "Tekan Import Cookie untuk menghubungkannya ke game.",
            )
            await self.account_menu(owner, row["id"])
        elif kind == "rename":
            self.registry.rename(owner, state["account"], text)
            self.service(state["account"])
            self.pending.pop(owner)
            await self.account_menu(owner, state["account"])
        elif kind == "add_user":
            uid = self.registry.owner_id(text)
            self.registry.whitelist(uid)
            self.pending.pop(owner)
            await self.send_user_menu(owner, uid)
            await self.user_menu(owner, uid)
        elif kind == "limit":
            self.registry.set_limit(state["setting"], text)
            self.pending.pop(owner)
            await self.admin_menu(owner)
        elif kind == "maintenance":
            window = MaintenanceWindow.parse(text)
            write_private(self.maintenance_file, window.payload())
            self.pending.pop(owner)
            await self.maintenance_menu(owner)
        elif kind == "user_limit":
            uid = state["user"]
            if not self.registry.allowed(uid):
                raise ValueError("Akses pengguna belum aktif. Aktifkan akses dahulu.")
            self.registry.whitelist(uid, maximum=text)
            self.pending.pop(owner)
            await self.user_menu(owner, uid)
        elif kind == "date":
            self.registry.get(state["account"], owner)
            service = self.service(state["account"])
            service.profit_buttons(text)  # Validate before clearing the date prompt.
            self.pending.pop(owner)
            await self.ensure_started(service)
            await service.execute("profit:" + text)
        else:
            await self.reply(owner, "Gunakan tombol konfirmasi atau Batal.", CANCEL)

    async def _dispatch(self, owner, text, callback):
        if callback and text.startswith("access:"):
            await self.home(owner)
            return
        if text == "Auto" and not callback:
            self.pending.pop(owner, None)
            account = self.registry.selected(owner)
            if account is None:
                await self.reply(
                    owner, "Belum ada akun terpilih. Tekan Tambah Akun atau Akun Saya."
                )
            else:
                await self.auto_menu(owner, account)
            return
        # Telegram sends /start when Start is pressed; users never need to type a command.
        if (not callback and text in {"/start", "Bantuan", "Menu Utama", "Batal"}) or (
            callback and text in {"home", "cancel"}
        ):
            await self.home(owner)
            return
        if (
            text == "Management"
            and not callback
            or callback
            and text.startswith(
                (
                    "admin:",
                    "user:",
                    "user_limit:",
                    "revoke:",
                    "revoke_confirm:",
                    "enable:",
                    "send_menu:",
                    "request:",
                    "approve_request:",
                    "reject_request:",
                )
            )
        ):
            await self.admin_action(owner, text)
            return
        if text == "Akun Saya" and not callback or callback and text.startswith("accounts:"):
            self.pending.pop(owner, None)
            await self.accounts(owner, int(text.split(":", 1)[1]) if callback else 0)
            return
        if text == "Tambah Akun" and not callback or callback and text == "add_account":
            await self.prompt(
                owner,
                {"kind": "name"},
                "👤 Beri nama akun baru\n\nKirim nama sepanjang 1 sampai 40 karakter.",
            )
            return
        if callback and text.startswith(
            ("select:", "rename:", "archive:", "archive_confirm:", "restore:")
        ):
            action, identifier = text.split(":", 1)
            row = self.registry.get(identifier, owner, archived=action == "restore")
            if action == "archive_confirm":
                if self.pending.get(owner) != {"kind": "archive", "account": identifier}:
                    raise ValueError("Konfirmasi kedaluwarsa. Pilih akun lagi.")
                self.pending.pop(owner)
                service = self.service(identifier)
                async with service.lock:
                    service.access.revoke()
                    await service.close()
                    self.registry.archive(owner, identifier)
                    self.services.pop(identifier, None)
                await self.accounts(owner)
            else:
                self.pending.pop(owner, None)
                if action in {"select", "restore"}:
                    if action == "restore":
                        self.registry.archive(owner, identifier, archived=False)
                    self.registry.select(owner, identifier)
                    await self.account_menu(owner, identifier)
                elif action == "rename":
                    await self.prompt(
                        owner,
                        {"kind": "rename", "account": identifier},
                        f"✏️ Ganti nama {row['name']}\n\nKirim nama baru sepanjang 1 sampai 40 karakter.",
                    )
                elif action == "archive":
                    self.pending[owner] = {"kind": "archive", "account": identifier}
                    await self.reply(
                        owner,
                        f"📁 Arsipkan {row['name']}?\n\nAktivitas akun akan dihentikan dan tautan "
                        "Import Cookie ditutup. Akun bisa dipulihkan lagi dari Akun Saya.",
                        {
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "Ya, Arsipkan",
                                        "callback_data": "archive_confirm:" + identifier,
                                    }
                                ],
                                [{"text": "Batal", "callback_data": "cancel"}],
                            ]
                        },
                    )
            return
        account = None
        command = None
        if callback:
            if not text.startswith("acct:"):
                return
            _, identifier, action = text.split(":", 2)
            account = self.registry.get(identifier, owner)
            if action == "auto" or action.startswith("auto:"):
                self.pending.pop(owner, None)
                await self.auto_menu(owner, account, action)
                return
            if action == "choose_date":
                await self.prompt(
                    owner,
                    {"kind": "date", "account": identifier},
                    f"📅 Laporan {account['name']} tanggal berapa?\n\n"
                    "Kirim tanggal dengan format YYYY-MM-DD atau DD-MM-YYYY.",
                )
                return
            if action != "import_cookie" and not re.fullmatch(r"profit:\d{4}-\d{2}-\d{2}", action):
                return
            command = action
        else:
            command = BUTTON_COMMANDS.get(text)
            if text.startswith("/"):
                await self.home(owner)
                return
            if command is None:
                if owner in self.pending:
                    await self.input(owner, text)
                else:
                    await self.home(owner)
                return
        self.pending.pop(owner, None)
        if command in GAME_COMMANDS and (maintenance := held_window(self.maintenance_file)):
            await self.reply(owner, maintenance.message())
            return
        account = account or self.registry.selected(owner)
        if account is None:
            await self.reply(owner, "Belum ada akun terpilih. Tekan Tambah Akun atau Akun Saya.")
            return
        service = self.service(account["id"])
        if command != "cleanup_scan":
            await self.ensure_started(service)
        if command in {"run", "import_cookie"}:
            if command == "run" and not (
                (service.worker and service.worker.returncode is None)
                or running(service.settings.runtime_dir)
            ):
                if self.active_workers() >= self.registry.value("max_active_workers"):
                    raise ValueError(
                        "Slot akun berjalan sedang penuh. Hentikan aktivitas salah satu akun "
                        "atau minta admin menambah batasnya."
                    )
            await self.start_tunnel()
        await service.execute(command)

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
                        profile = callback.get("from", {}) if callback else message.get("from", {})
                        sender = profile.get("id")
                        chat = message.get("chat", {})
                        if (
                            chat.get("type") == "private"
                            and chat.get("id") == sender
                            and type(sender) is int
                            and sender > 0
                        ):
                            if callback:
                                await api.call(
                                    "answerCallbackQuery", callback_query_id=callback["id"]
                                )
                            await self.dispatch(
                                sender,
                                callback.get("data", "") if callback else message.get("text", ""),
                                bool(callback),
                                profile=profile,
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
            for service in list(self.services.values()):
                if not service.auto_start_pending:
                    continue
                if (
                    not self.registry.allowed(service.settings.telegram_chat_id)
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
                    from .session_transfer import parse_cookie_input

                    parse_cookie_input(
                        (service.settings.runtime_dir / "http-session.json").read_text()
                    )
                    action = "Minta admin memeriksa izin operator dan status server, lalu tekan Jalankan Ojol."
                    await service.command("run", auto_start=True)
                except Exception as exc:
                    queue_error(
                        service.settings,
                        exc,
                        "worker.auto_start",
                        {"tindakan": action, "account_id": service.account_id},
                    )

    async def supervise(self):
        while not self.closing:
            await self.resume_workers()
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
                service = self.service(row["id"])
                await self.ensure_started(service)
                if self.settings.env == "testing":
                    continue
                directory = service.settings.runtime_dir
                marker = directory / WORKER_SHUTDOWN
                has_session = (directory / "http-session.json").is_file()
                if self.settings.auto_start and has_session:
                    # A new boot deliberately starts all eligible accounts, including previously stopped ones.
                    service.auto_start_pending = True
                    (directory / "STOP").unlink(missing_ok=True)
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
            *(
                s.close(notify_restart=self.registry.allowed(s.settings.telegram_chat_id))
                for s in self.services.values()
            ),
            self.hub.close(),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                raise result
