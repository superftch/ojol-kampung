"""One Telegram poller, per-account HTTP workers, admin-managed whitelist."""

import asyncio
import json
import re
import time

from .accounts import DRAFT_NAME, Accounts
from .auto_settings import AUTO_LABELS, auto_flags, set_auto_flag
from .cli import running
from .control import WORKER_SHUTDOWN, ControlService, status_record
from .healing import write_private
from .http_api import HttpCoreError, OjolHttpApi
from .identity import save_profile, verified_profile
from .maintenance import GAME_COMMANDS, SCHEDULE_FILE, MaintenanceWindow, held_window, read_window
from .models import NEEDS
from .study import (
    AUTO_SUBJECT,
    STUDY_LABELS,
    SUBJECTS,
    cached_skills,
    is_track_max,
    save_skills,
    set_subject,
    subjects,
)
from .telegram import (
    BUTTON_COMMANDS,
    TelegramClient,
    TelegramError,
    acknowledge_callback,
    flush_notices,
    keyboard_accounts,
    keyboard_main,
    keyboard_settings,
    koin,
    queue_error,
    queue_notice,
    record_error,
    redact,
)

HELP = (
    "🏠 Menu utama\n\n"
    "Akun baru? Buka Akun Saya → Tambah Akun untuk langsung Import Cookie.\n"
    "Nama otomatis mengikuti nickname game.\n"
    "Sudah siap? Tekan Jalankan Ojol.\n\n"
    "Auto untuk memilih aktivitas yang berjalan.\n"
    "Status untuk melihat kondisi akun.\n\n"
    "Akun Saya untuk memilih atau mengelola akun.\n"
    "Pengaturan untuk notifikasi dan management."
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
        await self.reply(owner, HELP + selected, keyboard_main())

    async def dashboard(self, owner):
        self.pending.pop(owner, None)
        accounts = self.registry.list(owner)
        if not accounts:
            await self.reply(
                owner,
                "📊 Dashboard Akun\n\nBelum ada akun terdaftar.\nTekan Tambah Akun di menu Akun Saya untuk memulai.",
                keyboard_accounts(),
            )
            return

        selected_account = self.registry.selected(owner)
        selected_id = selected_account["id"] if selected_account else None

        active_count = 0
        sleeping_count = 0
        stopped_count = 0

        account_lines = []
        for i, row in enumerate(accounts, 1):
            service = self.service(row["id"])
            summary = service.summary()

            if summary["active"]:
                if summary["phase"] == "sleeping":
                    sleeping_count += 1
                else:
                    active_count += 1
            else:
                stopped_count += 1

            is_selected = row["id"] == selected_id
            tag = " [Dipilih]" if is_selected else ""
            name = row["name"]
            icon = summary["icon"]
            status_desc = summary["status_text"]

            lines = [f"{i}. {icon} {name}{tag}", f"   • Status: {status_desc}"]

            wallet_part = (
                f"Saldo {koin(summary['wallet'])}" if summary["wallet"] is not None else None
            )
            trips_part = f"{summary['trips']} trip" if summary["trips"] is not None else None
            if wallet_part and trips_part:
                lines.append(f"   • {wallet_part} · {trips_part}")
            elif wallet_part:
                lines.append(f"   • {wallet_part}")
            elif trips_part:
                lines.append(f"   • {trips_part}")

            if any(summary[k] is not None for k in ("fuel", "condition", "data")):
                f_str = f"⛽ {summary['fuel']}%" if summary["fuel"] is not None else "⛽ -%"
                c_str = (
                    f"🔧 {summary['condition']}%" if summary["condition"] is not None else "🔧 -%"
                )
                d_str = f"📶 {summary['data']}%" if summary["data"] is not None else "📶 -%"
                lines.append(f"   • Resource: {f_str} · {c_str} · {d_str}")

            account_lines.append("\n".join(lines))

        header = (
            f"📊 Dashboard Akun ({len(accounts)} Akun)\n"
            f"🟢 Berjalan: {active_count} · 💤 Tidur: {sleeping_count} · ⚪ Berhenti: {stopped_count}\n\n"
        )
        body = "\n\n".join(account_lines)

        buttons = []
        row_buttons = []
        for i, acc in enumerate(accounts, 1):
            btn_text = f"Pilih {i}. {acc['name'][:10]}"
            row_buttons.append({"text": btn_text, "callback_data": f"select:{acc['id']}"})
            if len(row_buttons) == 2:
                buttons.append(row_buttons)
                row_buttons = []
        if row_buttons:
            buttons.append(row_buttons)

        buttons.append([{"text": "🔄 Refresh", "callback_data": "dashboard"}])

        await self.reply(
            owner,
            header + body,
            {"inline_keyboard": buttons},
        )

    async def prompt(self, owner, state, text):
        self.pending[owner] = state
        await self.reply(owner, text, CANCEL)

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

    async def accounts(self, owner, page=0):
        rows = self.registry.list(owner) + self.registry.list(owner, archived=True)
        page = min(max(0, page), max(0, (len(rows) - 1) // PAGE_SIZE))
        await asyncio.gather(
            *(
                self.refresh_account_profile(row)
                for row in rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
                if not row["archived"]
            )
        )
        selected = self.registry.selected(owner)
        active = self.registry.list(owner)
        rows = active + self.registry.list(owner, archived=True)
        page = min(max(0, page), max(0, (len(rows) - 1) // PAGE_SIZE))
        lines = [
            "👤 Akun Saya",
            f"{len(active)} dari {self.registry.quota(owner)} slot akun terpakai.",
            "Nama mengikuti nickname game terakhir terverifikasi.",
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
            [
                {"text": "Auto Ojol", "callback_data": f"acct:{identifier}:auto_ojol"},
                {"text": "Auto Kebutuhan", "callback_data": f"acct:{identifier}:auto_kebutuhan"},
            ],
            [
                {"text": "Status Ojol", "callback_data": f"acct:{identifier}:status_ojol"},
                {
                    "text": "Status Kebutuhan",
                    "callback_data": f"acct:{identifier}:status_kebutuhan",
                },
            ],
            [{"text": "Semua Auto", "callback_data": f"acct:{identifier}:auto"}],
            [
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

    async def auto_ojol_toggle(self, owner, account):
        directory = self.registry.scoped_settings(account).runtime_dir
        flags = auto_flags(directory)
        new_val = not flags.get("ojol")
        set_auto_flag(directory, "ojol", new_val)
        status_str = "ON" if new_val else "OFF"
        icon = "✅" if new_val else "⏹"
        msg = f"{icon} Auto Ojol · {account['name']} • {status_str}\n\n"
        if new_val:
            msg += "Auto Ojol diaktifkan (mengurus trip, kondisi mesin, bensin, dan kuota)."
        else:
            msg += "Auto Ojol dinonaktifkan. Fitur auto kebutuhan tetap berjalan sesuai pengaturan."
        await self.reply(
            owner,
            msg,
            {
                "inline_keyboard": [
                    [
                        {
                            "text": "Auto Kebutuhan",
                            "callback_data": f"acct:{account['id']}:auto_kebutuhan",
                        },
                        {
                            "text": "Status Ojol",
                            "callback_data": f"acct:{account['id']}:status_ojol",
                        },
                    ],
                    [{"text": "Akun Saya", "callback_data": "accounts:0"}],
                ]
            },
        )

    async def auto_keb_all(self, owner, account, action):
        directory = self.registry.scoped_settings(account).runtime_dir
        val = action.split(":", 1)[1] == "1"
        for key in NEEDS:
            set_auto_flag(directory, key, val)
        await self.auto_kebutuhan_menu(owner, account)

    async def auto_kebutuhan_menu(self, owner, account, action="auto_kebutuhan"):
        directory = self.registry.scoped_settings(account).runtime_dir
        parts = action.split(":")
        confirmation = ""
        if len(parts) == 3 and parts[1] in AUTO_LABELS and parts[2] in {"0", "1"}:
            if parts[1] in STUDY_LABELS and parts[2] == "1" and not subjects(directory)[parts[1]]:
                await self.study_menu(owner, account, f"study:{parts[1]}")
                return
            set_auto_flag(directory, parts[1], parts[2] == "1")
            enabled = parts[2] == "1"
            confirmation = f"✅ {AUTO_LABELS[parts[1]]} • {'ON' if enabled else 'OFF'}\n\n"
        flags = auto_flags(directory)
        identifier = account["id"]
        choices = subjects(directory)
        skills = cached_skills(directory)
        skills_by_id = {t["id"]: t for t in skills if isinstance(t, dict)} if skills else {}

        need_keys = [k for k in NEEDS if k in AUTO_LABELS]
        need_buttons = [
            {
                "text": f"{AUTO_LABELS[k]} {'ON' if flags[k] else 'OFF'}",
                "callback_data": f"acct:{identifier}:auto_kebutuhan:{k}:{int(not flags[k])}",
            }
            for k in need_keys
        ]
        grid = []
        for i in range(0, len(need_buttons), 2):
            grid.append(need_buttons[i : i + 2])
        grid.append(
            [
                {
                    "text": f"Kebun & kolam {'ON' if flags.get('kebun') else 'OFF'}",
                    "callback_data": f"acct:{identifier}:auto_kebutuhan:kebun:{int(not flags.get('kebun'))}",
                }
            ]
        )
        for mode in STUDY_LABELS:
            subj_name = (
                "Auto (Pilih Otomatis)"
                if choices[mode] == AUTO_SUBJECT
                else SUBJECTS.get(choices[mode], "belum dipilih")
            )
            is_max = (
                choices[mode]
                and choices[mode] != AUTO_SUBJECT
                and is_track_max(skills_by_id.get(choices[mode]), mode)
            )
            grid.append(
                [
                    {
                        "text": f"Bidang {'Perpus' if mode == 'perpus' else 'Kuliah'}: {subj_name}{' (Maks)' if is_max else ''}",
                        "callback_data": f"acct:{identifier}:study:{mode}",
                    }
                ]
            )
        grid.append(
            [
                {"text": "Semua ON", "callback_data": f"acct:{identifier}:auto_keb_all:1"},
                {"text": "Semua OFF", "callback_data": f"acct:{identifier}:auto_keb_all:0"},
            ]
        )
        grid.append(
            [
                {
                    "text": "Status Kebutuhan",
                    "callback_data": f"acct:{identifier}:status_kebutuhan",
                },
                {"text": "Akun Saya", "callback_data": "accounts:0"},
            ]
        )
        summary = "\n".join(
            f"{AUTO_LABELS[k]} • {'ON' if flags[k] else 'OFF'} (target {self.settings.threshold_for(k)}%)"
            for k in need_keys
        )
        await self.reply(
            owner,
            f"🍲 Auto Kebutuhan · {account['name']}\n\n"
            + confirmation
            + summary
            + "\n\n"
            + "Kebutuhan otomatis diisi saat nilai di bawah target.\n"
            + "Tekan tombol untuk mengubah status per kebutuhan.",
            {"inline_keyboard": grid},
        )

    async def auto_menu(self, owner, account, action="auto"):
        directory = self.registry.scoped_settings(account).runtime_dir
        parts = action.split(":")
        confirmation = ""
        if len(parts) == 3 and parts[1] in AUTO_LABELS and parts[2] in {"0", "1"}:
            if parts[1] in STUDY_LABELS and parts[2] == "1" and not subjects(directory)[parts[1]]:
                await self.study_menu(owner, account, f"study:{parts[1]}")
                return
            set_auto_flag(directory, parts[1], parts[2] == "1")
            enabled = parts[2] == "1"
            confirmation = f"✅ {AUTO_LABELS[parts[1]]} • {'ON' if enabled else 'OFF'}\n"
            if not enabled:
                confirmation += "Aksi otomatis baru untuk fitur ini dinonaktifkan. Hasil aksi yang sudah terkirim tetap diperiksa.\n\n"
            elif parts[1] in NEEDS:
                confirmation += f"Saat worker berjalan, bot mengisi kebutuhan ini jika di bawah {self.settings.threshold_for(parts[1])}%, mengikuti anggaran dan saldo minimum.\n\n"
            else:
                confirmation += "Pengaturan tersimpan. Fitur aktif saat worker berjalan.\n\n"
        elif action != "auto":
            return
        flags = auto_flags(directory)
        identifier = account["id"]
        choices = subjects(directory)
        skills = cached_skills(directory)
        skills_by_id = {t["id"]: t for t in skills if isinstance(t, dict)} if skills else {}
        summary = "\n".join(
            f"{label} • {'ON' if flags[key] else 'OFF'}" for key, label in AUTO_LABELS.items()
        )
        buttons = [
            {
                "text": f"{label} {'ON' if flags[key] else 'OFF'}",
                "callback_data": f"acct:{identifier}:auto:{key}:{int(not flags[key])}",
            }
            for key, label in AUTO_LABELS.items()
        ]
        await self.reply(
            owner,
            f"⚙️ Auto · {account['name']}\n\n" + confirmation + summary + "\n\n"
            "Auto Ojol mengurus trip, kondisi mesin, bensin, dan kuota.\n"
            "Kebutuhan lain bisa diatur satu per satu.\n"
            "Perpus gratis dan kuliah berbayar terpisah, awalnya OFF.\n"
            "Belajar dan kuis maksimal sekali sehari per jenis; kuliah mengikuti batas belanja.\n\n"
            "ON berarti aktif. Tekan tombol untuk mengubahnya.\n"
            "Pilihan tersimpan dan berlaku saat bot berjalan.",
            {
                "inline_keyboard": [
                    [buttons[0]],
                    buttons[1:3],
                    buttons[3:5],
                    buttons[5:7],
                    buttons[7:],
                    *[
                        [
                            {
                                "text": f"Bidang {'Perpus' if mode == 'perpus' else 'Kuliah'}: {'Auto (Pilih Otomatis)' if choices[mode] == AUTO_SUBJECT else SUBJECTS.get(choices[mode], 'belum dipilih')}{' (Maks)' if choices[mode] and choices[mode] != AUTO_SUBJECT and is_track_max(skills_by_id.get(choices[mode]), mode) else ''}",
                                "callback_data": f"acct:{identifier}:study:{mode}",
                            }
                        ]
                        for mode in STUDY_LABELS
                    ],
                    [{"text": "Akun Saya", "callback_data": "accounts:0"}],
                ]
            },
        )

    async def study_menu(self, owner, account, action):
        parts = action.split(":")
        if len(parts) not in {2, 3} or parts[1] not in STUDY_LABELS:
            raise ValueError("Pilihan belajar tidak valid.")
        mode = parts[1]
        directory = self.registry.scoped_settings(account).runtime_dir
        if len(parts) == 2:
            await self.refresh_account_profile(account)
        skills = cached_skills(directory)
        skills_by_id = {t["id"]: t for t in skills if isinstance(t, dict)} if skills else {}
        if len(parts) == 3:
            track = parts[2]
            if track == AUTO_SUBJECT:
                set_subject(directory, mode, AUTO_SUBJECT)
                await self.auto_menu(owner, account)
                return
            track_info = skills_by_id.get(track)
            if track_info and is_track_max(track_info, mode):
                reason = (
                    "sudah mencapai batas maksimal (keahlian 5)"
                    if (
                        track_info.get("level", 0) >= 5
                        or (track_info.get("next") or {}).get("level", 0) > 5
                    )
                    else "sudah maksimal di perpustakaan"
                    if mode == "perpus"
                    else "sudah mencapai level maksimal"
                )
                await self.reply(
                    owner,
                    f"⚠️ Bidang {SUBJECTS.get(track, track)} {reason} dan tidak dapat dipilih untuk {STUDY_LABELS[mode]}.",
                    {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "Kembali ke Pilihan Belajar",
                                    "callback_data": f"acct:{account['id']}:study:{mode}",
                                }
                            ],
                            [
                                {
                                    "text": "Kembali ke Auto",
                                    "callback_data": f"acct:{account['id']}:auto",
                                }
                            ],
                        ]
                    },
                )
                return
            set_subject(directory, mode, track, skills=skills)
            await self.auto_menu(owner, account)
            return
        selected = subjects(directory)[mode]
        auto_check = "✓ " if selected == AUTO_SUBJECT else ""
        auto_button = [
            {
                "text": f"{auto_check}🔄 Auto (Pilih Otomatis)",
                "callback_data": f"acct:{account['id']}:study:{mode}:{AUTO_SUBJECT}",
            }
        ]
        buttons = []
        for key, label in SUBJECTS.items():
            track_info = skills_by_id.get(key)
            is_max = is_track_max(track_info, mode) if track_info else False
            lvl_text = (
                f" Lv {track_info.get('level')}" if track_info and "level" in track_info else ""
            )
            tag = f" (Maks{lvl_text})" if is_max else (f" ({lvl_text.strip()})" if lvl_text else "")
            check = "✓ " if selected == key else ""
            callback_data = (
                f"acct:{account['id']}:s_max:{key}"
                if is_max
                else f"acct:{account['id']}:study:{mode}:{key}"
            )
            buttons.append(
                {
                    "text": f"{check}{label}{tag}",
                    "callback_data": callback_data,
                }
            )
        await self.reply(
            owner,
            f"📚 {STUDY_LABELS[mode]} · {account['name']}\n\n"
            "Pilih bidang untuk sesi belajar berikutnya. Kuis bacaan dikerjakan otomatis.\n"
            "Pilihan disimpan per akun; aktifkan ON dari menu Auto setelah memilih.\n"
            "Mode Auto Otomatis akan memilih bidang belajar yang belum maksimal secara otomatis.\n"
            "Bidang yang sudah maksimal tidak dapat dipilih.",
            {
                "inline_keyboard": [
                    auto_button,
                    *[buttons[index : index + 2] for index in range(0, len(buttons), 2)],
                    [{"text": "Kembali ke Auto", "callback_data": f"acct:{account['id']}:auto"}],
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
        if window and getattr(window, "manual", False):
            status = "🔴 Status: Aktif (Manual ON tanpa jadwal)"
        elif window:
            status = f"🟡 Status: Terjadwal ({window.description()})"
        else:
            status = "⚪ Status: Nonaktif (OFF / Belum ada jadwal)"
        await self.reply(
            owner,
            f"🛠 Maintenance game\n\n{status}\n\n"
            "Gunakan tombol ON / OFF untuk mengaktifkan maintenance langsung tanpa jadwal, "
            "atau Atur Jadwal untuk menjeda aktivitas otomatis berdasarkan waktu WIB.",
            {
                "inline_keyboard": [
                    [
                        {"text": "🟢 ON", "callback_data": "admin:maintenance:on"},
                        {"text": "🔴 OFF", "callback_data": "admin:maintenance:off"},
                    ],
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
            name = (user.get("name") or "").strip()
            username = (user.get("username") or "").strip()
            display_name = (
                f"@{username}"
                if (not name or name == "Tanpa nama") and username
                else name
                if name and name != "Tanpa nama"
                else (f"@{username}" if username else "")
            )
            if display_name:
                short_name = display_name[:24] + ("…" if len(display_name) > 24 else "")
                label = f"{short_name} ({uid}) · {status}"
            else:
                label = f"{uid} · {status}"
            buttons.append([{"text": label, "callback_data": f"user:{uid}"}])
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
        name = user.get("name") if user.get("name") and user.get("name") != "Tanpa nama" else "-"
        username = f"@{user['username']}" if user.get("username") else "-"
        await self.reply(
            owner,
            f"👤 Pengguna {uid}\n\n"
            f"Nama • {name}\n"
            f"Username • {username}\n"
            f"Akses • {'admin' if uid == self.registry.admin else 'aktif' if enabled else 'dicabut'}\n"
            f"Akun • {len(self.registry.list(uid))} dari {self.registry.quota(uid)} slot terpakai\n\n"
            "Pilih tindakan di bawah.",
            {"inline_keyboard": buttons},
        )

    async def public_access(self, owner, text, callback, profile):
        if not callback and (text.startswith("/connect") or text.startswith("connect")):
            parts = text.split()
            if len(parts) >= 2:
                code = parts[1].strip()
                try:
                    name = " ".join(
                        str(profile.get(key) or "") for key in ("first_name", "last_name")
                    ).strip()
                    web_user = self.registry.web.consume_telegram_link_code(
                        code, owner, name=name, username=str(profile.get("username") or "")
                    )
                    await self.reply(
                        owner,
                        f"✅ Akun web '{web_user['username']}' berhasil dihubungkan ke Telegram!\n\n"
                        "Akses bot Anda kini aktif. Kirim /start untuk membuka menu utama.",
                    )
                    return
                except ValueError as exc:
                    await self.reply(owner, f"❌ Gagal menghubungkan: {exc}")
                    return

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
            keyboard_main(),
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
                if profile and profile.get("id") == owner:
                    name = " ".join(
                        str(profile.get(key) or "") for key in ("first_name", "last_name")
                    ).strip()
                    username = str(profile.get("username") or "").strip()
                    if name or username:
                        self.registry.update_user_profile(owner, name=name, username=username)
                if not self.registry.allowed(owner):
                    await self.public_access(owner, text.strip(), callback, profile or {})
                    return
                await self._dispatch(owner, text.strip(), callback)
            except (ValueError, OverflowError) as exc:
                details = record_error(
                    self.notice_settings(owner), exc, "management.validation", {"fatal": False}
                )
                await self.reply(
                    owner,
                    f"ID error: {details['error_id']}\n"
                    + (
                        redact(exc, self.settings)
                        if not isinstance(exc, OverflowError)
                        else "Tanggal tidak valid"
                    ),
                    (CANCEL if owner in self.pending else keyboard_main())
                    if self.registry.allowed(owner)
                    else ACCESS_STATUS,
                )
            except Exception as exc:
                notice = queue_error(self.hub.settings, exc, "management.command")
                await self.reply(
                    owner,
                    json.loads(notice.read_text())["text"],
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
        elif text == "admin:maintenance:on":
            window = MaintenanceWindow.create_manual()
            write_private(self.maintenance_file, window.payload())
            await self.maintenance_menu(owner)
        elif text in {"admin:maintenance:off", "admin:maintenance:clear"}:
            self.maintenance_file.unlink(missing_ok=True)
            await self.maintenance_menu(owner)
        elif text == "admin:maintenance:toggle":
            if held_window(self.maintenance_file):
                self.maintenance_file.unlink(missing_ok=True)
            else:
                window = MaintenanceWindow.create_manual()
                write_private(self.maintenance_file, window.payload())
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
        elif text.startswith(("web_appr:", "web_rejc:")):
            action, user_id_str = text.split(":", 1)
            uid = int(user_id_str)
            approve = action == "web_appr"
            updated = self.registry.web.review_user(uid, owner, approve=approve)
            await self.reply(
                owner,
                f"✅ Pendaftaran akun web '{updated['username']}' telah {'disetujui' if approve else 'ditolak'}.",
            )
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
        if kind == "add_user":
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
        if (text in {"Dashboard", "/dashboard"} and not callback) or (
            callback and text == "dashboard"
        ):
            self.pending.pop(owner, None)
            await self.dashboard(owner)
            return
        if text in {"Auto", "Semua Auto"} and not callback:
            self.pending.pop(owner, None)
            account = self.registry.selected(owner)
            if account is None:
                await self.reply(
                    owner, "Belum ada akun terpilih. Tekan Tambah Akun atau Akun Saya."
                )
            else:
                await self.auto_menu(owner, account)
            return
        if text == "Auto Kebutuhan" and not callback:
            self.pending.pop(owner, None)
            account = self.registry.selected(owner)
            if account is None:
                await self.reply(
                    owner, "Belum ada akun terpilih. Tekan Tambah Akun atau Akun Saya."
                )
            else:
                await self.auto_kebutuhan_menu(owner, account)
            return
        if text == "Auto Ojol" and not callback:
            self.pending.pop(owner, None)
            account = self.registry.selected(owner)
            if account is None:
                await self.reply(
                    owner, "Belum ada akun terpilih. Tekan Tambah Akun atau Akun Saya."
                )
            else:
                await self.auto_ojol_toggle(owner, account)
            return
        # Telegram sends /start when Start is pressed; users never need to type a command.
        if (not callback and text in {"/start", "Bantuan", "Menu Utama", "Batal"}) or (
            callback and text in {"home", "cancel"}
        ):
            await self.home(owner)
            return
        if not callback and text in {"/web", "/login", "Web", "Login Web"}:
            self.pending.pop(owner, None)
            code = self.registry.web.issue_telegram_login_code(owner)
            url = self.public_url()
            await self.reply(
                owner,
                "🌐 Login Web Kampung Ojol\n\n"
                f"Kode login Anda:\n`{code}`\n\n"
                f"Buka browser dan masukkan kode di atas:\n"
                f"{url}/login?code={code}\n\n"
                "⏳ Kode berlaku selama 10 menit.",
            )
            return
        if not callback and (text.startswith("/connect") or text.startswith("connect")):
            self.pending.pop(owner, None)
            parts = text.split()
            if len(parts) < 2:
                await self.reply(
                    owner,
                    "⚠️ Format: `/connect <KODE>`\n\n"
                    "Dapatkan 6-digit kode penghubung dari menu Hubungkan Telegram di dashboard web.",
                )
                return
            code = parts[1].strip()
            try:
                web_user = self.registry.web.consume_telegram_link_code(code, owner)
                await self.reply(
                    owner,
                    f"✅ Akun Telegram berhasil dihubungkan ke akun web '{web_user['username']}'!\n\n"
                    "Sekarang Anda dapat mengelola akun game secara bersamaan lewat web dan Telegram.",
                )
            except ValueError as exc:
                await self.reply(owner, f"❌ Gagal: {exc}")
            return
        if not callback and text == "Pengaturan":
            self.pending.pop(owner, None)
            if owner == self.registry.admin:
                await self.admin_menu(owner)
            else:
                from .telegram import notifications_enabled

                enabled = notifications_enabled(self.notice_settings(owner))
                await self.reply(
                    owner,
                    "⚙️ Pengaturan\n\n"
                    f"Notifikasi • {'ON' if enabled else 'OFF'}\n\n"
                    "Tekan tombol di bawah untuk mengubah notifikasi.",
                    keyboard_settings(),
                )
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
            self.pending.pop(owner, None)
            draft = next(
                (
                    row
                    for row in self.registry.list(owner)
                    if row["name"] == DRAFT_NAME
                    and not self.registry.get(row["id"])["cookie_hash"]
                    and not (
                        self.registry.scoped_settings(row).runtime_dir / "http-session.json"
                    ).is_file()
                ),
                None,
            )
            account = draft or self.registry.create(owner)
            self.registry.select(owner, account["id"])
            await self._dispatch(owner, "Import Cookie", False)
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
                    await self.reply(
                        owner,
                        "Nama akun otomatis mengikuti nickname game. Buka Akun Saya atau impor ulang cookie untuk memperbarui profil.",
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
        mode_arg = None
        if callback:
            if not text.startswith("acct:"):
                return
            _, identifier, action = text.split(":", 2)
            account = self.registry.get(identifier, owner)
            if action.startswith("study:"):
                self.pending.pop(owner, None)
                await self.study_menu(owner, account, action)
                return
            if action.startswith("s_max:"):
                self.pending.pop(owner, None)
                key = action.split(":", 1)[1]
                label = SUBJECTS.get(key, key)
                await self.reply(
                    owner,
                    f"⚠️ Bidang {label} sudah mencapai level maksimal (5) dan tidak dapat dipilih lagi.",
                )
                return
            if action == "auto" or action.startswith("auto:"):
                self.pending.pop(owner, None)
                await self.auto_menu(owner, account, action)
                return
            if action == "auto_kebutuhan" or action.startswith("auto_kebutuhan:"):
                self.pending.pop(owner, None)
                await self.auto_kebutuhan_menu(owner, account, action)
                return
            if action.startswith("auto_keb_all:"):
                self.pending.pop(owner, None)
                await self.auto_keb_all(owner, account, action)
                return
            if action == "auto_ojol":
                self.pending.pop(owner, None)
                await self.auto_ojol_toggle(owner, account)
                return
            if action in {"status_kebutuhan", "status_ojol"}:
                command = "status_kebutuhan" if action == "status_kebutuhan" else "status"
            elif action.startswith("mode:"):
                mode = action.split(":", 1)[1]
                if mode not in {"kendara", "otomatis"}:
                    return
                command, mode_arg = "run", mode
            elif action == "choose_date":
                await self.prompt(
                    owner,
                    {"kind": "date", "account": identifier},
                    f"📅 Laporan {account['name']} tanggal berapa?\n\n"
                    "Kirim tanggal dengan format YYYY-MM-DD atau DD-MM-YYYY.",
                )
                return
            if (
                action not in {"import_cookie", "status_kebutuhan", "status_ojol"}
                and not re.fullmatch(r"profit:\d{4}-\d{2}-\d{2}", action)
                and command is None
            ):
                return
            if command is None:
                command = action
        else:
            if text.lower() in {"online", "/online"}:
                command = "online"
            else:
                command = BUTTON_COMMANDS.get(text)
            if text.startswith("/") and command != "online":
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
            if not (
                command in {"run_kebutuhan", "stop_kebutuhan"}
                and getattr(maintenance, "target", "all") == "ojol"
            ):
                await self.reply(owner, maintenance.message())
                return
        account = account or self.registry.selected(owner)
        if account is None:
            await self.reply(owner, "Belum ada akun terpilih. Tekan Tambah Akun atau Akun Saya.")
            return
        service = self.service(account["id"])
        if command not in {"cleanup_scan", "visit_scan"}:
            await self.ensure_started(service)
        if command in {"run", "run_kebutuhan", "import_cookie"}:
            if command in {"run", "run_kebutuhan"} and not (
                (service.worker and service.worker.returncode is None)
                or running(service.settings.runtime_dir)
            ):
                if self.active_workers() >= self.registry.value("max_active_workers"):
                    raise ValueError(
                        "Slot akun berjalan sedang penuh. Hentikan aktivitas salah satu akun "
                        "atau minta admin menambah batasnya."
                    )
            await self.start_tunnel()
        await service.execute(
            command, **({"mode": mode_arg} if command == "run" and mode_arg else {})
        )

    async def poll_telegram(self):
        cursor = self.settings.runtime_dir / "telegram-offset"
        offset = int(cursor.read_text()) if cursor.exists() else 0
        outage = None
        last_outage_notice = 0
        async with TelegramClient(self.settings) as api:
            while not self.closing:
                try:
                    updates = await api.call(
                        "getUpdates",
                        offset=offset,
                        timeout=20,
                        allowed_updates=["message", "callback_query"],
                    )
                    outage = None
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
                            if not callback or await acknowledge_callback(api, callback["id"]):
                                await self.dispatch(
                                    sender,
                                    callback.get("data", "")
                                    if callback
                                    else message.get("text", ""),
                                    bool(callback),
                                    profile=profile,
                                )
                        offset = max(offset, update["update_id"] + 1)
                        cursor.write_text(str(offset))
                except (TelegramError, OSError, ValueError) as exc:
                    retryable = isinstance(exc, TelegramError) and exc.retryable
                    now_ts = time.time()
                    if (outage is None or outage != retryable) and (
                        not retryable or now_ts - last_outage_notice >= 900
                    ):
                        queue_error(
                            self.hub.settings, exc, "telegram.poll", stop_worker=not retryable
                        )
                        last_outage_notice = now_ts
                        if not retryable:
                            await asyncio.gather(
                                *(s.stop_worker() for s in self.services.values()),
                                return_exceptions=True,
                            )
                    outage = retryable
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
            data, status_updated = status_record(directory / "status.json")
            online_data, online_updated = status_record(directory / "online-status.json")
            latest_touch = max(
                status_updated / 1e9 if status_updated else 0,
                online_updated / 1e9 if online_updated else 0,
            )
            is_worker_active = (service.worker and service.worker.returncode is None) or running(
                directory
            )
            if is_worker_active and (time.time() - latest_touch < 35):
                continue
            try:
                await service.fetch_online_status()
            except Exception:
                pass

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
        if (
            self.settings.telegram_enabled
            and self.settings.telegram_bot_token.get_secret_value()
            and self.registry.admin
        ):
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
                s.close(
                    notify_restart=self.registry.allowed(s.settings.telegram_chat_id),
                    stop_workers=False,
                )
                for s in self.services.values()
            ),
            self.hub.close(stop_workers=False),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                raise result
