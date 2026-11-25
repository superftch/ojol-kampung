"""Account worker control, status, reports, and one-use cookie import."""

import asyncio
import contextlib
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from random import choice
from urllib.parse import urlsplit

from app.core.formatting import format_koin as koin
from app.core.locks import running
from app.core.models import NEEDS, ROOT, Settings, now
from app.core.storage import write_private
from app.integrations.cloudflared import CloudflaredTunnel
from app.integrations.kampung.http_api import HttpCoreError, OjolHttpApi
from app.modules.auth.import_access import LoginAccess
from app.modules.gameplay.cleanup import find_unvisited, scan
from app.modules.ledger.finance import WIB, report_date
from app.modules.notifications.service import queue_error, queue_notice
from app.modules.worker.capacity import WorkerCapacityError
from app.modules.worker.maintenance import GAME_COMMANDS, SCHEDULE_FILE, held_window
from app.modules.worker.settings import auto_flags, set_auto_flag
from app.modules.worker.status import (
    build_account_summary,
    format_auto_needs_summary,
    format_needs_status,
    format_ojol_status,
    format_profit_report,
)

WORKER_SHUTDOWN = "worker-shutdown"


class ControlService:
    def __init__(self, settings):
        self.settings = settings
        self.access = LoginAccess(settings.runtime_dir)
        self.worker = None
        self.tunnel = CloudflaredTunnel()
        self.expected_stop = False
        self.closing = False
        self.tasks = []
        self.lock = asyncio.Lock()
        self.worker_start_lock = asyncio.Lock()
        self.worker_capacity_error = None
        self.url_prefix = ""
        self.account_id = None
        self.auto_start_pending = False
        self.maintenance_file = settings.runtime_dir / SCHEDULE_FILE

    async def ensure_backend(self, require_session=False):
        if require_session:
            from app.integrations.kampung.session_transfer import (
                parse_cookie_input,
                session_expired,
            )

            try:
                payload = parse_cookie_input(
                    (self.settings.runtime_dir / "http-session.json").read_text()
                )
            except (OSError, ValueError, KeyError, TypeError):
                raise HttpCoreError(
                    "Sesi game belum tersedia. Gunakan Import Cookie.", category="auth"
                ) from None
            if session_expired(payload):
                raise HttpCoreError("Cookie sesi game sudah kedaluwarsa.", category="auth")

    def tunnel_alive(self) -> bool:
        return self.tunnel.is_alive()

    async def start_tunnel(self, token_file: Path | None = None) -> None:
        await self.tunnel.start(
            enabled=self.settings.tunnel_enabled,
            token_file=token_file or self.settings.runtime_dir.parent / "cloudflared-token",
        )

    def public_url(self):
        if self.settings.env == "production":
            return self.settings.login_public_url
        path = self.settings.runtime_dir / "public-url"
        candidate = path.read_text().strip() if path.is_file() else self.settings.login_public_url
        return Settings.secure_login_origin(candidate)

    async def stop_worker(self):
        self.auto_start_pending = False
        self.expected_stop = True
        (self.settings.runtime_dir / "STOP").touch(mode=0o600)
        from app.modules.worker.supervisor import send_worker_command

        with contextlib.suppress(Exception):
            await send_worker_command(
                self.settings.runtime_dir,
                {"action": "stop", "account_id": self.account_id},
                timeout=1.0,
            )

        if self.worker and self.worker.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.worker.terminate()
        for _ in range(120):
            if not running(self.settings.runtime_dir) and not (
                self.worker and self.worker.returncode is None
            ):
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("Worker belum berhenti setelah 30 detik. Sesi game tidak diganti.")

    async def fetch_online_status(self):
        async with OjolHttpApi(self.settings.runtime_dir) as api:
            return await api.fetch_online_status()

    def status(self):
        return format_ojol_status(
            self.settings,
            worker_proc=self.worker,
            expected_stop=self.expected_stop,
            auto_start_pending=self.auto_start_pending,
            maintenance_file=self.maintenance_file,
            tunnel_alive=self.tunnel_alive(),
            is_running=running,
            current_time=now,
        )

    def status_kebutuhan(self):
        return format_needs_status(
            self.settings,
            worker_proc=self.worker,
            is_running=running,
            current_time=now,
        )

    def auto_kebutuhan_summary(self):
        return format_auto_needs_summary(self.settings)

    def summary(self):
        return build_account_summary(
            self.settings,
            worker_proc=self.worker,
            is_running=running,
            current_time=now,
        )

    async def account_profit(self, day):
        directory = self.settings.runtime_dir
        wallet = None
        if self.settings.env == "testing" or not (directory / "http-session.json").is_file():
            issue = "Sesi game belum tersedia"
        else:
            from app.modules.worker.ui import HttpUI

            try:
                async with asyncio.timeout(18):
                    async with HttpUI(self.settings) as core:
                        wallet = await core.daily_wallet(day)
                issue = wallet["issue"]
            except Exception:
                wallet = None
                issue = "Riwayat game tidak dapat dibaca"
        return self.profit(day, wallet, issue)

    def profit(self, day=None, wallet=None, issue=None):
        return format_profit_report(self.settings, day, wallet, issue)

    async def cookie_link(self):
        async with self.lock:
            await self.stop_worker()
            await self.start_tunnel()
            self.access.revoke()
            ticket = self.access.issue("ticket")
            return f"{self.public_url()}{self.url_prefix}/access/{ticket}"

    async def command(self, command, *, auto_start=False, mode=None):
        if (
            command in GAME_COMMANDS
            and (maintenance := held_window(self.maintenance_file))
            and not (
                command in {"run_kebutuhan", "stop_kebutuhan"} and maintenance.target == "ojol"
            )
        ):
            if auto_start:
                self.auto_start_pending = True
            return maintenance.message()
        if command in {"resume", "skip"}:
            from contextlib import closing

            from app.modules.ledger.repository import Journal

            # 1. Hentikan worker jika sedang berjalan agar tidak bertabrakan dengan rekonsiliasi baru
            with contextlib.suppress(Exception):
                await self.stop_worker()

            # 2. Hapus file STOP agar bisa mulai baru
            (self.settings.runtime_dir / "STOP").unlink(missing_ok=True)

            skipped = []
            with closing(Journal(self.settings.runtime_dir)) as journal:
                for row in journal.unresolved():
                    journal.skip(row["id"])
                    skipped.append(row["id"])

            # 3. Bersihkan status rekonsiliasi lama dari game-sync.json dan status.json
            sync_path = self.settings.runtime_dir / "game-sync.json"
            if sync_path.is_file():
                with contextlib.suppress(OSError, ValueError, TypeError):
                    sync_data = json.loads(sync_path.read_text())
                    sync_data["reconciliation"] = []
                    sync_data["unresolved"] = 0
                    write_private(sync_path, sync_data)

            status_path = self.settings.runtime_dir / "status.json"
            if status_path.is_file():
                with contextlib.suppress(OSError, ValueError, TypeError, AttributeError):
                    st_data = json.loads(status_path.read_text())
                    st_data.pop("reconciliation_pending", None)
                    st_data.pop("reconciliation_attempt", None)
                    st_data["event"] = "berhenti"
                    st_data["reason"] = (
                        f"Aksi tertahan ({len(skipped)} aksi) dilewati manual oleh pengguna."
                    )
                    write_private(status_path, st_data)

            text = (
                "⏩ Aksi belum pasti dilewati: " + ", ".join(f"#{row}" for row in skipped) + ".\n\n"
                if skipped
                else "✅ Tidak ada aksi tertahan.\n\n"
            )
            try:
                run_msg = await self.command("run")
                return text + run_msg
            except Exception:
                return text
        if command == "import_cookie":
            url = await self.cookie_link()
            browser_hint = (
                "\n💻 Buka link ini di browser komputer yang menjalankan Docker."
                if urlsplit(url).scheme == "http"
                else ""
            )
            return (
                "🔐 Hubungkan akun game\n\n"
                + url
                + browser_hint
                + "\n\nBuka tautan, lalu tempel cookie sesi KampungSebelah pada formulir.\n"
                "Tautan berlaku 15 menit dan bisa dipakai satu kali.\n\n"
                "Setelah berhasil, kembali ke sini dan tekan Jalankan Ojol."
            )
        if command == "status":
            return self.status()
        if command == "status_kebutuhan":
            return self.status_kebutuhan()
        if command == "auto_kebutuhan":
            return self.auto_kebutuhan_summary()
        if command == "online":
            status = await self.fetch_online_status()
            nick = status.get("nickname") or self.settings.account_name or "Akun"
            bal = status.get("balance_milli")
            bal_str = f" · Saldo {Decimal(bal) / 1000} koin" if bal is not None else ""
            return (
                f"🟢 Presence Online · {nick}\n\n"
                f"Akun aktif di game (presence online terkonfirmasi){bal_str}.\n"
                f"Waktu server: {status.get('server_time')}\n"
                f"Terakhir diperbarui: {now().astimezone(WIB):%H:%M:%S} WIB"
            )
        if command == "dashboard":
            s = self.summary()
            wallet_str = f" · Saldo {koin(s['wallet'])}" if s["wallet"] is not None else ""
            trips_str = f" · {s['trips']} trip" if s["trips"] is not None else ""
            res_str = ""
            if any(s[k] is not None for k in ("fuel", "condition", "data")):
                f_val = f"{s['fuel']}%" if s["fuel"] is not None else "-%"
                c_val = f"{s['condition']}%" if s["condition"] is not None else "-%"
                d_val = f"{s['data']}%" if s["data"] is not None else "-%"
                res_str = f"\nResource • ⛽ {f_val} · 🔧 {c_val} · 📶 {d_val}"
            return (
                f"📊 Dashboard Akun\n\n"
                f"{s['icon']} Status • {s['status_text']}"
                f"{wallet_str}{trips_str}"
                f"{res_str}"
            )
        if command == "visit_scan":
            if self.settings.env == "testing":
                return "HTTP live diblokir dalam test environment."
            async with asyncio.timeout(12), OjolHttpApi(self.settings.runtime_dir) as api:
                house = await find_unvisited(api)
            if house is None:
                return (
                    "👋 Belum ditemukan rumah yang sedang menerima tamu dan belum kamu kunjungi "
                    "hari ini di sekitar rumahmu."
                )
            return (
                "👋 Rumah untuk mampir ditemukan\n\n"
                f"Pemilik • {house['nickname']}\nRumah • {house['plot_id']}\n"
                f"Posisi • {house['x']}, {house['y']}\n\n"
                "🟢 Menerima tamu sekarang dan belum kamu kunjungi hari ini saat diperiksa. "
                "Buka rumah ini di game untuk mampir."
            )
        if command == "cleanup_scan":
            if self.settings.env == "testing":
                return "HTTP live diblokir dalam test environment."
            async with asyncio.timeout(12), OjolHttpApi(self.settings.runtime_dir) as api:
                result = await scan(api, None, None, include_neighbors=True)
            if not result["candidates"]:
                return "🧹 Belum terlihat rumah kotor di sekitar rumahmu. Coba cek lagi nanti."
            plot = choice(result["candidates"])  # noqa: S311 - shuffle display candidates
            return (
                f"🧹 Rumah kotor ditemukan\n\n"
                f"Rumah • {plot['plot_id']}\nPosisi • {plot['x']}, {plot['y']}\n\n"
                "Rumah ini terlihat kotor saat diperiksa. Ketersediaan pekerjaan bisa berubah."
            )
        if command == "profit" or command.startswith("profit:"):
            day = report_date(command.split(":", 1)[1] if ":" in command else None)
            return await self.account_profit(day)
        if command == "stop_ojol":
            set_auto_flag(self.settings.runtime_dir, "ojol", False)
            flags = auto_flags(self.settings.runtime_dir)
            active = (self.worker and self.worker.returncode is None) or running(
                self.settings.runtime_dir
            )
            has_kebutuhan = any(flags[k] for k in flags if k != "ojol")
            if active and has_kebutuhan:
                return (
                    "⏹ Auto Ojol dihentikan.\n\n"
                    "Fitur auto kebutuhan tetap berjalan normal. Tekan Jalankan Ojol jika ingin melanjutkan Ojol."
                )
            await self.stop_worker()
            return "⏹ Aktivitas akun sudah dihentikan.\n\nTekan Jalankan Ojol atau Jalankan Kebutuhan jika ingin melanjutkan."
        if command == "stop_kebutuhan":
            for key in NEEDS:
                set_auto_flag(self.settings.runtime_dir, key, False)
            flags = auto_flags(self.settings.runtime_dir)
            active = (self.worker and self.worker.returncode is None) or running(
                self.settings.runtime_dir
            )
            if active and flags["ojol"]:
                return (
                    "⏹ Auto kebutuhan dihentikan.\n\n"
                    "Auto Ojol tetap berjalan normal. Tekan Jalankan Kebutuhan jika ingin mengaktifkan kembali."
                )
            await self.stop_worker()
            return "⏹ Aktivitas akun sudah dihentikan.\n\nTekan Jalankan Ojol atau Jalankan Kebutuhan jika ingin melanjutkan."
        if command == "stop_kerja":
            set_auto_flag(self.settings.runtime_dir, "kerja", False)
            flags = auto_flags(self.settings.runtime_dir)
            active = (self.worker and self.worker.returncode is None) or running(
                self.settings.runtime_dir
            )
            if active and (flags.get("ojol") or any(flags.get(k) for k in NEEDS)):
                return "⏹ Auto Kantor dihentikan. Aktivitas auto lain tetap berjalan."
            await self.stop_worker()
            return "⏹ Auto Kantor dan worker dihentikan."
        if command == "run_kerja":
            set_auto_flag(self.settings.runtime_dir, "ojol", False)
            set_auto_flag(self.settings.runtime_dir, "kerja", True)
            if (self.worker and self.worker.returncode is None) or running(
                self.settings.runtime_dir
            ):
                return "🟢 Auto Kantor aktif. Bot sedang menjalankan pekerjaan kantor."
            return await self._start_worker(auto_start=True, needs_only=False)
        if command == "stop":
            await self.stop_worker()
            return "⏹ Aktivitas akun sudah dihentikan.\n\nTekan Jalankan Ojol atau Jalankan Kebutuhan jika ingin melanjutkan."
        if command == "run_kebutuhan":
            return await self._start_worker(auto_start=auto_start, needs_only=True)
        if command == "run":
            return await self._start_worker(auto_start=auto_start, needs_only=False, mode=mode)
        return "Pilih aktivitas lewat tombol di bawah. Buka Akun Saya untuk mengganti akun."

    async def _start_worker(
        self, *, auto_start: bool, needs_only: bool, mode: str | None = None
    ) -> str:
        async with self.lock:
            if self.closing:
                raise RuntimeError("Akun tidak tersedia. Pilih akun lain.")
            if needs_only:
                set_auto_flag(self.settings.runtime_dir, "ojol", False)
                for key in NEEDS:
                    set_auto_flag(self.settings.runtime_dir, key, True)
            elif not auto_start:
                set_auto_flag(self.settings.runtime_dir, "ojol", True)
                set_auto_flag(self.settings.runtime_dir, "kerja", False)

            flags = auto_flags(self.settings.runtime_dir)
            is_ojol = False if needs_only else bool(flags.get("ojol"))
            label = "Berkendara" if mode == "kendara" else "Otomatis" if mode == "otomatis" else ""

            if (self.worker and self.worker.returncode is None) or running(
                self.settings.runtime_dir
            ):
                if not is_ojol:
                    return (
                        "🟢 Auto kebutuhan aktif. Bot sedang memantau dan mengisi kebutuhan karakter.\n\n"
                        "Tekan Status untuk melihat perkembangannya."
                    )
                return (
                    "🟢 Bot sudah aktif untuk akun ini. Auto Ojol diaktifkan"
                    + (f" (mode {label}).\n\n" if label else ".\n\n")
                    + "Aktivitas mengikuti pilihan di menu Auto. Tekan Status untuk melihat perkembangannya."
                )

            if not self.settings.operator_authorized:
                msg = (
                    "Akun ini belum diizinkan menjalankan bot oleh admin."
                    if needs_only
                    else "Akun ini belum diizinkan menjalankan Ojol oleh admin."
                )
                raise RuntimeError(msg)

            self.access.revoke()
            await self.ensure_backend(require_session=True)
            await self.start_tunnel()

            if maintenance := held_window(self.maintenance_file):
                target = getattr(maintenance, "target", "all")
                blocked = (target == "all") if needs_only else (is_ojol or target == "all")
                if blocked:
                    if auto_start:
                        self.auto_start_pending = True
                    return maintenance.message()

            from app.modules.worker.supervisor import send_worker_command

            worker_resp = await send_worker_command(
                self.settings.runtime_dir,
                {
                    "action": "start",
                    "account_id": self.account_id,
                    "mode": mode if is_ojol else None,
                    "auto_start": auto_start,
                    "needs_only": not is_ojol,
                },
            )
            if worker_resp is not None:
                if not worker_resp.get("ok"):
                    if worker_resp.get("capacity"):
                        if auto_start:
                            self.auto_start_pending = True
                        raise WorkerCapacityError(worker_resp["error"])
                    raise RuntimeError(worker_resp.get("error") or worker_resp["message"])
                self.expected_stop = False
                return self._started_message(is_ojol=is_ojol, label=label)

            async with self.worker_start_lock:
                if self.worker_capacity_error and (error := self.worker_capacity_error()):
                    if auto_start:
                        self.auto_start_pending = True
                    raise WorkerCapacityError(error)
                await self._spawn_local_worker(auto_start, is_ojol, mode)
            return self._started_message(is_ojol=is_ojol, label=label)

    async def _spawn_local_worker(self, auto_start, is_ojol, mode):
        config_file = os.environ.get("OJOL_CONFIG_FILE")
        args = [sys.executable, str(ROOT / "main.py")]
        if config_file:
            args += ["--env-file", config_file]
        args += ["run", "--live"]
        self.expected_stop = False
        # Docker owns stdout rotation; journal and status remain persistent in the volume.
        self.worker = await asyncio.create_subprocess_exec(
            *args,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
            env={
                **os.environ,
                "OJOL_RUNTIME_DIR": str(self.settings.runtime_dir),
                "OJOL_ACCOUNT_NAME": self.settings.account_name,
                "OJOL_ACCOUNT_ID": self.account_id or "",
                "OJOL_WORKER_AUTO_START": "1" if auto_start else "0",
                "OJOL_MAINTENANCE_FILE": str(self.maintenance_file),
                **(
                    {"OJOL_OJOL_MODE": mode}
                    if (is_ojol and mode in {"kendara", "otomatis"})
                    else {}
                ),
            },
        )

    @staticmethod
    def _started_message(*, is_ojol: bool, label: str) -> str:
        if not is_ojol:
            return (
                "▶️ Bot sedang memulai (Auto Kebutuhan)\n\n"
                "Bot akan memantau dan mengisi kebutuhan karakter secara otomatis. "
                "Tekan Status untuk melihat perkembangannya."
            )
        return (
            "▶️ Bot sedang memulai"
            + (f" (mode {label})\n\n" if label else "\n\n")
            + "Aktivitas mengikuti pilihan di menu Auto. Tekan Status untuk melihat perkembangannya."
        )

    async def execute(self, command, *, mode=None):
        try:
            response = await self.command(command, mode=mode)
            queue_notice(self.settings, response)
        except (ValueError, OverflowError) as exc:
            queue_error(
                self.settings,
                exc,
                f"control.command.{command}",
                {"account_id": self.account_id},
                stop_worker=not command.startswith("profit")
                and command
                not in {
                    "cleanup_scan",
                    "visit_scan",
                    "stop_ojol",
                    "stop_kebutuhan",
                },
            )
        except Exception as exc:
            queue_error(
                self.settings,
                exc,
                f"control.command.{command}",
                {"account_id": self.account_id},
                stop_worker=command
                not in {
                    "cleanup_scan",
                    "visit_scan",
                    "stop_ojol",
                    "stop_kebutuhan",
                },
            )

    async def supervise(self):
        while not self.closing:
            if not self.lock.locked() and (code := self.tunnel.take_exit()) is not None:
                queue_error(
                    self.settings,
                    RuntimeError(f"Tunnel berhenti tiba-tiba (exit code {code})."),
                    "tunnel.process_exit",
                )
                await self.stop_worker()
            if self.worker and self.worker.returncode is not None:
                code, pid = self.worker.returncode, self.worker.pid
                self.worker = None
                if code != 0 and not self.expected_stop:
                    error_file = self.settings.runtime_dir / "last-error.json"
                    previous_error = (
                        json.loads(error_file.read_text()) if error_file.exists() else {}
                    )
                    if previous_error.get("pid") != pid or previous_error.get("fatal") is False:
                        queue_error(
                            self.settings,
                            RuntimeError(f"Worker mati tiba-tiba (exit code {code})."),
                            "worker.process_exit",
                        )
                else:
                    queue_notice(
                        self.settings,
                        "⏹ Bot sudah berhenti. Tekan Status untuk melihat kondisi akun.",
                    )
            commands = self.settings.runtime_dir / "control-commands"
            for path in sorted(commands.glob("*.json")):
                payload = json.loads(path.read_text())
                path.rename(path.with_suffix(".done"))
                await self.execute(payload["command"])
            await asyncio.sleep(2)

    async def guard_task(self, operation, stage):
        try:
            await operation()
        except Exception as exc:
            queue_error(self.settings, exc, stage)
            await self.stop_worker()

    async def start(self):
        if self.settings.env == "testing":
            return
        status_file = self.settings.runtime_dir / "status.json"
        if (
            not self.settings.auto_start
            and status_file.exists()
            and not running(self.settings.runtime_dir)
        ):
            previous = json.loads(status_file.read_text())
            if previous.get("pid") and previous.get("event") not in {
                "berhenti",
                "gagal",
                "dry_run",
            }:
                queue_error(
                    self.settings,
                    RuntimeError("Ojol terputus saat server mati. Tidak dilanjutkan otomatis."),
                    "worker.interrupted",
                    {
                        "run_id": previous.get("run_id"),
                        "last_stage": previous.get("stage"),
                        "last_action": previous.get("last_action"),
                    },
                )
        try:
            await self.start_tunnel()
        except Exception as exc:
            queue_error(self.settings, exc, "control.startup.tunnel")
        self.tasks.append(asyncio.create_task(self.guard_task(self.supervise, "control.supervise")))

    async def close(self, *, notify_restart=False, stop_workers=True):
        self.closing = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        try:
            if stop_workers:
                was_active = (
                    notify_restart
                    and self.settings.env != "testing"
                    and not self.expected_stop
                    and (
                        (self.worker and self.worker.returncode is None)
                        or running(self.settings.runtime_dir)
                    )
                )
                await self.stop_worker()
                if was_active:
                    marker = self.settings.runtime_dir / WORKER_SHUTDOWN
                    marker.touch(mode=0o600)
                    queue_notice(
                        self.settings,
                        "♻️ Aplikasi sedang ditutup\n\nAktivitas akun dijeda. Kabar berikutnya dikirim saat bot kembali siap.",
                    )
        finally:
            await self.tunnel.close()
