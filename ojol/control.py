"""Private Telegram buttons, daily reports, and one-use HTTPS cookie import."""

import asyncio
import html
import json
import os
import re
import shutil
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil
from pathlib import Path
from random import choice
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .auto_settings import AUTO_LABELS, auto_flags
from .cleanup import scan
from .cli import exclusive_lock, running
from .config import load_settings
from .finance import WIB, report_date
from .http_api import HttpCoreError, OjolHttpApi
from .journal import Journal, unresolved_action
from .login_access import LoginAccess
from .maintenance import GAME_COMMANDS, SCHEDULE_FILE, held_window
from .models import ROOT, Settings, now
from .telegram import (
    BUTTON_COMMANDS,
    TelegramClient,
    TelegramError,
    authorized_message,
    flush_notices,
    koin,
    notifications_enabled,
    queue_error,
    queue_notice,
    redact,
    set_notifications,
)

WORKER_SHUTDOWN = "worker-shutdown"


def status_record(path):
    try:
        value = json.loads(path.read_text())
        return (value, path.stat().st_mtime_ns) if isinstance(value, dict) else ({}, 0)
    except (OSError, ValueError):
        return {}, 0


def status_timestamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp if stamp.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


class ControlService:
    def __init__(self, settings):
        self.settings = settings
        self.access = LoginAccess(settings.runtime_dir)
        self.worker = None
        self.tunnel_process = None
        self.expected_stop = False
        self.awaiting_date = False
        self.closing = False
        self.tasks = []
        self.lock = asyncio.Lock()
        self.url_prefix = ""
        self.account_id = None
        self.auto_start_pending = False
        self.maintenance_file = settings.runtime_dir / SCHEDULE_FILE

    async def ensure_backend(self, require_session=False):
        if require_session:
            from .session_transfer import parse_cookie_input, session_expired

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

    def tunnel_alive(self):
        return bool(self.tunnel_process and self.tunnel_process.returncode is None)

    async def start_tunnel(self, token_file=None):
        if not self.settings.tunnel_enabled or self.tunnel_alive():
            return
        if not Path("/.dockerenv").is_file():
            raise RuntimeError("Tunnel terkelola hanya boleh dijalankan dalam container Docker")
        token_file = token_file or self.settings.runtime_dir.parent / "cloudflared-token"
        binary = shutil.which("cloudflared")
        if not binary or not token_file.is_file() or not token_file.stat().st_size:
            raise RuntimeError("Binary cloudflared atau secret cloudflared_token tidak tersedia")
        # Keep credentials out of argv/environment; Docker rotates connector stdout.
        self.tunnel_process = await asyncio.create_subprocess_exec(
            binary,
            "tunnel",
            "--no-autoupdate",
            "--metrics",
            "127.0.0.1:2000",
            "run",
            "--token-file",
            str(token_file),
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
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
        if self.worker and self.worker.returncode is None:
            try:
                self.worker.terminate()
            except ProcessLookupError:
                pass
        for _ in range(120):
            if not running(self.settings.runtime_dir) and not (
                self.worker and self.worker.returncode is None
            ):
                return
            await asyncio.sleep(0.25)
        raise RuntimeError("Worker belum berhenti setelah 30 detik. Sesi game tidak diganti.")

    def status(self):
        directory = self.settings.runtime_dir
        data, status_updated = status_record(directory / "status.json")
        state = data.get("snapshot") or {}
        busy = running(directory)
        managed = self.worker is not None and self.worker.returncode is None
        pid = data.get("pid")
        recorded_worker = (
            type(pid) is int
            and pid > 0
            and data.get("event") not in {"berhenti", "gagal", "dry_run"}
        )
        if busy and recorded_worker:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                recorded_worker = False
            except PermissionError:
                pass
        active = busy and recorded_worker and (not managed or self.worker.pid == pid)
        starting = managed and not active
        if active:
            worker = "🟢 Worker aktif"
        elif starting:
            worker = "🟡 Worker memulai"
        elif busy:
            worker = "🟠 Worker lain sedang memakai akun ini"
        else:
            worker = "🔴 Worker berhenti" if data else "⚪ Worker belum dijalankan"
        phase = state.get("phase")
        phases = {
            "idle": "menunggu order",
            "searching": "mencari order",
            "delivering": "dalam perjalanan",
            "complete": "siap klaim ongkos",
            "sleeping": "karakter tidur",
            "unknown": "tidak diketahui",
        }
        moment = now()
        observed = status_timestamp(data.get("snapshot_received_at") or state.get("observed_at"))
        seconds = state.get("remaining_seconds")
        lines = [f"🛵 Status Ojol · {self.settings.account_name or 'Utama'}", "", worker]
        trip = f"📍 Trip: {phases.get(phase, 'belum terbaca')}"
        if observed:
            age = max(0, int((moment - observed).total_seconds()))
            age_text = (
                f"{age} detik"
                if age < 60
                else f"{age // 60} menit"
                if age < 3600
                else f"{age // 3600} jam"
            )
            if active and phase == "delivering" and type(seconds) is int and seconds > 0:
                remaining = max(0, ceil(seconds - (moment - observed).total_seconds()))
                trip += f" · sisa trip ±{remaining // 60}:{remaining % 60:02d}"
            lines.append(trip)
            stale = " · data lama, worker tidak aktif" if not active else ""
            lines.append(
                f"🕒 Update terakhir: {observed.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB "
                f"({age_text} lalu){stale}"
            )
        else:
            lines.extend([trip, "🕒 Update terakhir: belum ada data"])
        if not active and not starting:
            pending = unresolved_action(directory)
            error, error_updated = status_record(directory / "last-error.json")
            reason = None
            if pending:
                reason = (
                    f"Aksi #{pending[0]} ({pending[1]}) menunggu rekonsiliasi "
                    "(hasil klik terakhir belum pasti, dicek dulu sebelum lanjut)"
                )
            elif error_updated >= status_updated and error.get("message"):
                reason = error["message"]
            elif data.get("event") in {"berhenti", "gagal"}:
                reason = data.get("reason")
            elif self.expected_stop and data:
                reason = "Dihentikan pengguna"
            if reason:
                lines.append(f"⚠️ Alasan berhenti: {redact(reason, self.settings)}")

        lines.extend(
            f"{AUTO_LABELS[key]} {value}%"
            for key, value in state.get("needs", {}).items()
            if key in AUTO_LABELS
        )
        flags = auto_flags(directory)
        enabled = ", ".join(label for key, label in AUTO_LABELS.items() if flags[key])
        lines.append(f"Auto aktif • {enabled or 'semua dimatikan'}")
        maintenance = held_window(self.maintenance_file)
        if maintenance:
            lines.append(maintenance.message())
        auto_start = "ON" if self.settings.auto_start else "OFF"
        if self.auto_start_pending:
            auto_start += " · menunggu maintenance" if maintenance else " · menunggu slot"
        lines.extend(
            [
                "",
                f"⛽ Bensin {state.get('fuel', '?')}%",
                f"🔧 Kondisi {state.get('condition', '?')}%",
                f"📶 Kuota {state.get('data', '?')}%",
                f"💰 Saldo utama {state.get('wallet', '?')} koin "
                f"(minimum {self.settings.min_balance} koin)",
                "",
                f"Notifikasi • {'ON' if notifications_enabled(self.settings) else 'OFF'}",
                f"🔁 Auto-start saat boot: {auto_start}",
            ]
        )
        if self.settings.tunnel_enabled:
            lines.append(f"🌐 Tunnel: {'aktif' if self.tunnel_alive() else 'berhenti'}")
        return "\n".join(lines)

    async def account_profit(self, day):
        directory = self.settings.runtime_dir
        wallet = None
        if self.settings.env == "testing" or not (directory / "http-session.json").is_file():
            issue = "Sesi game belum tersedia"
        else:
            from .http_core import HttpUI

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
        journal = Journal(self.settings.runtime_dir)
        try:
            report = journal.financial_report(day)
        finally:
            journal.close()
        total = report["total"]
        money = lambda value: str(value).replace(".", ",")
        from .http_api import coin, display

        names = {"fuel": "⛽ Bensin", "condition": "🔧 Bengkel", "data": "📶 Kuota"}
        lines = [f"📒 Laba Bersih · {report['tanggal']} (WIB)", "", "🎮 Menurut riwayat game"]
        if wallet:
            expenses = wallet["expenses_milli"]
            cost = sum(expenses.values())
            expense_issue = wallet["expense_issue"]
            complete = wallet["complete"] and expense_issue is None
            if complete:
                net = Decimal(wallet["income_milli"] - cost) / 1000
                lines.append(f"✅ Estimasi laba Ojol {display(net)} koin")
        if wallet and wallet["complete"]:
            lines.append(
                f"💵 Pendapatan Ojol seluruh akun {display(coin(wallet['income_milli']))} koin · "
                f"{wallet['payout_count']} payout"
            )
        else:
            lines.append(f"⚠️ Pendapatan belum lengkap: {issue or 'belum diperiksa'}")
            if wallet and wallet["payout_count"]:
                lines.append(
                    f"💵 Payout ditemukan {display(coin(wallet['income_milli']))} koin (parsial)"
                )
        if wallet:
            if complete or expenses:
                label = (
                    "Belanja produk Ojol" if complete else "Belanja produk Ojol ditemukan (parsial)"
                )
                lines.append(f"🛒 {label} {display(coin(cost))} koin")
                lines.append(
                    "   "
                    + " · ".join(
                        f"{name} {display(coin(expenses.get(key, 0)))} koin"
                        for key, name in names.items()
                    )
                )
            if expense_issue:
                lines.append(f"⚠️ Data biaya belum lengkap: {expense_issue}")
        if wallet and wallet["today_income_milli"] is not None:
            lines.append(
                f"📊 Hasil hari ini menurut game {display(coin(wallet['today_income_milli']))} koin"
            )
        if wallet and (complete or expenses):
            lines.append(
                "ℹ️ Semua pembelian bensin, bengkel, dan kuota dihitung sebagai biaya Ojol."
            )
        if not wallet or not complete:
            lines.append("ℹ️ Laba belum dihitung karena data game belum lengkap.")
        lines.extend(
            [
                "",
                "🤖 Catatan worker",
                f"✅ Laba bersih worker {money(total['laba_bersih'])} koin",
                f"💵 Pendapatan Ojol {money(total['pendapatan_ojol'])} koin · "
                f"{total['trip_tercatat']} trip",
                f"🛒 Biaya worker terverifikasi {money(total['pengeluaran'])} koin · "
                f"{total['pembelian_tercatat']} pembelian",
            ]
        )
        if total["biaya_per_kategori"]:
            lines.append(
                "   "
                + " · ".join(
                    f"{names.get(key, AUTO_LABELS.get(key, key))} {money(value)} koin"
                    for key, value in total["biaya_per_kategori"].items()
                )
            )
        if report["transaksi_terakhir"]:
            lines.extend(["", "🧾 Transaksi worker terakhir"])
        for row in report["transaksi_terakhir"][:8]:
            clock = datetime.fromisoformat(row["created"]).astimezone(WIB).strftime("%H:%M")
            detail = json.loads(row["detail"])
            label = detail.get("product", "Ongkos Ojol")
            lines.append(
                f"{clock} {'+' if row['kind'] == 'income' else '−'}{koin(row['amount'])} · {label}"
            )
        return "\n".join(lines)

    def profit_buttons(self, day=None):
        day = report_date(day)
        prefix = f"acct:{self.account_id}:" if self.account_id else ""
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "◀ Hari sebelumnya",
                        "callback_data": prefix + f"profit:{day - timedelta(days=1)}",
                    },
                    {
                        "text": "Hari berikutnya ▶",
                        "callback_data": prefix + f"profit:{day + timedelta(days=1)}",
                    },
                ],
                [
                    {"text": "Hari ini", "callback_data": prefix + f"profit:{report_date()}"},
                    {"text": "Pilih tanggal", "callback_data": prefix + "choose_date"},
                ],
            ]
        }

    async def cookie_link(self):
        async with self.lock:
            await self.stop_worker()
            await self.start_tunnel()
            self.access.revoke()
            ticket = self.access.issue("ticket")
            return f"{self.public_url()}{self.url_prefix}/access/{ticket}"

    async def command(self, command, *, auto_start=False):
        if command in GAME_COMMANDS and (maintenance := held_window(self.maintenance_file)):
            if auto_start:
                self.auto_start_pending = True
            return maintenance.message()
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
        if command == "cleanup_scan":
            if self.settings.env == "testing":
                return "HTTP live diblokir dalam test environment."
            try:
                async with asyncio.timeout(12), OjolHttpApi(self.settings.runtime_dir) as api:
                    result = await scan(api, None, None, include_neighbors=True)
            except TimeoutError:
                return "Pencarian rumah kotor kehabisan waktu. Coba lagi."
            except (HttpCoreError, ValueError):
                return "⚠️ Rumah kotor belum bisa diperiksa. Coba lagi beberapa saat lagi."
            if not result["candidates"]:
                return "🧹 Belum terlihat rumah kotor di sekitar rumahmu. Coba cek lagi nanti."
            plot = choice(result["candidates"])
            return (
                f"🧹 Rumah kotor ditemukan\n\n"
                f"Rumah • {plot['plot_id']}\nPosisi • {plot['x']}, {plot['y']}\n\n"
                "Rumah ini terlihat kotor saat diperiksa. Ketersediaan pekerjaan bisa berubah."
            )
        if command == "profit" or command.startswith("profit:"):
            day = report_date(command.split(":", 1)[1] if ":" in command else None)
            return await self.account_profit(day)
        if command == "choose_date":
            self.awaiting_date = True
            return "📅 Laporan tanggal berapa?\n\nKirim tanggal dengan format YYYY-MM-DD atau DD-MM-YYYY."
        if command in {"notifications_on", "notifications_off"}:
            enabled = command == "notifications_on"
            set_notifications(self.settings, enabled)
            return (
                "🔔 Notifikasi ON\n\nBot akan mengabarkan hasil trip, pembelian, dan jeda maintenance."
                if enabled
                else "🔕 Notifikasi OFF\n\nBot tetap memberi tahu jika berhenti karena masalah atau perlu tindakan."
            )
        if command == "stop":
            await self.stop_worker()
            return (
                "⏹ Aktivitas akun sudah dihentikan.\n\nTekan Jalankan Ojol jika ingin melanjutkan."
            )
        if command == "run":
            async with self.lock:
                if (self.worker and self.worker.returncode is None) or running(
                    self.settings.runtime_dir
                ):
                    return "🟢 Bot sudah aktif untuk akun ini. Tekan Status untuk melihat perkembangannya."
                if not self.settings.operator_authorized:
                    raise RuntimeError("Akun ini belum diizinkan menjalankan Ojol oleh admin.")
                self.access.revoke()
                await self.ensure_backend(require_session=True)
                await self.start_tunnel()
                if maintenance := held_window(self.maintenance_file):
                    if auto_start:
                        self.auto_start_pending = True
                    return maintenance.message()
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
                        "OJOL_TELEGRAM_CHAT_ID": str(self.settings.telegram_chat_id or ""),
                        "OJOL_ACCOUNT_NAME": self.settings.account_name,
                        "OJOL_ACCOUNT_ID": self.account_id or "",
                        "OJOL_WORKER_AUTO_START": "1" if auto_start else "0",
                        "OJOL_MAINTENANCE_FILE": str(self.maintenance_file),
                    },
                )
                return "▶️ Bot sedang memulai\n\nAktivitas mengikuti pilihan di menu Auto. Tekan Status untuk melihat perkembangannya."
        return "Pilih aktivitas lewat tombol di bawah. Buka Akun Saya untuk mengganti akun."

    async def execute(self, command):
        try:
            response = await self.command(command)
            markup = (
                self.profit_buttons(command.split(":", 1)[1] if ":" in command else None)
                if command == "profit" or command.startswith("profit:")
                else None
            )
            queue_notice(self.settings, response, reply_markup=markup)
        except (ValueError, OverflowError):
            if command.startswith("profit"):
                queue_notice(
                    self.settings,
                    "❌ Tanggal tidak valid\n\nFormat: YYYY-MM-DD atau DD-MM-YYYY\nContoh: 2026-11-10",
                )
            else:
                queue_error(
                    self.settings,
                    RuntimeError("Perintah tidak dikenal."),
                    f"control.command.{command}",
                )
        except Exception as exc:
            if command == "cleanup_scan":
                queue_notice(self.settings, "Pencarian rumah kotor gagal. Coba lagi.")
            else:
                queue_error(
                    self.settings,
                    exc,
                    f"control.command.{command}",
                    {"account_id": self.account_id},
                )
        await flush_notices(self.settings)

    async def poll_telegram(self):
        cursor_file = self.settings.runtime_dir / "telegram-offset"
        offset = int(cursor_file.read_text()) if cursor_file.exists() else 0
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
                        offset = max(offset, update["update_id"] + 1)
                        cursor_file.write_text(str(offset))
                        if authorized_message(update, self.settings):
                            callback = update.get("callback_query")
                            if callback:
                                await api.call(
                                    "answerCallbackQuery", callback_query_id=callback["id"]
                                )
                                command = callback.get("data", "")
                                if command == "choose_date" or re.fullmatch(
                                    r"profit:\d{4}-\d{2}-\d{2}", command
                                ):
                                    await self.execute(command)
                            else:
                                text = update["message"].get("text", "").strip()
                                if text in BUTTON_COMMANDS:
                                    self.awaiting_date = False
                                    await self.execute(BUTTON_COMMANDS[text])
                                elif self.awaiting_date or re.fullmatch(
                                    r"\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}", text
                                ):
                                    self.awaiting_date = False
                                    await self.execute("profit:" + text)
                                else:
                                    await self.execute("help")
                except (TelegramError, OSError, ValueError) as exc:
                    if not outage:
                        queue_error(self.settings, exc, "telegram.poll")
                    outage = True
                    await flush_notices(self.settings)
                    await asyncio.sleep(15)

    async def supervise(self):
        while not self.closing:
            if (
                self.tunnel_process
                and self.tunnel_process.returncode is not None
                and not self.lock.locked()
            ):
                code = self.tunnel_process.returncode
                self.tunnel_process = None
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
                    if previous_error.get("pid") != pid:
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
            await flush_notices(self.settings)
            await asyncio.sleep(2)

    async def guard_task(self, operation, stage):
        try:
            await operation()
        except Exception as exc:
            queue_error(self.settings, exc, stage)
            try:
                await self.stop_worker()
            finally:
                await flush_notices(self.settings)

    async def start(self, poll=True):
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
            await flush_notices(self.settings)
        if (
            poll
            and self.settings.telegram_bot_token.get_secret_value()
            and self.settings.telegram_chat_id
        ):
            self.tasks.append(
                asyncio.create_task(self.guard_task(self.poll_telegram, "telegram.poll"))
            )
        self.tasks.append(asyncio.create_task(self.guard_task(self.supervise, "control.supervise")))

    async def close(self, *, notify_restart=False):
        self.closing = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        try:
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
                try:
                    await asyncio.wait_for(flush_notices(self.settings), timeout=3)
                except TimeoutError:
                    pass
        finally:
            if self.tunnel_process:
                process = self.tunnel_process
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 10)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                self.tunnel_process = None


def create_app(settings, service=None):
    from .management import MultiAccountService

    manager = MultiAccountService(settings) if service is None else None
    lifecycle = manager or service

    def resolve(request):
        if manager is None:
            return service
        try:
            identifier = request.path_params.get("account_id")
            return manager.service(identifier) if identifier else manager.legacy()
        except ValueError:
            raise HTTPException(403, "Akun tidak tersedia / akses dicabut") from None

    @asynccontextmanager
    async def lifespan(app):
        with exclusive_lock(settings.runtime_dir / "control-server"):
            try:
                await lifecycle.start()
                yield
            finally:
                await lifecycle.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def require_access(request):
        scoped = resolve(request)
        if not scoped.access.expiry(request.cookies.get("ojol_import"), "session"):
            raise HTTPException(403, "Link import diperlukan / sesi kedaluwarsa")

    @app.middleware("http")
    async def protect(request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
            }
        )
        return response

    @app.get("/health")
    async def health():
        return {
            "service": "ok",
            "core": "http",
            "tunnel_enabled": settings.tunnel_enabled,
            "tunnel_process_alive": manager.hub.tunnel_alive()
            if manager
            else service.tunnel_alive(),
        }

    @app.get("/a/{account_id}/access/{ticket}")
    @app.get("/access/{ticket}")
    async def access(ticket: str, request: Request):
        service = resolve(request)
        session = service.access.consume_ticket(ticket) if len(ticket) <= 100 else None
        if not session:
            raise HTTPException(403, "Link kedaluwarsa/sudah dipakai; tekan Import Cookie di bot")
        response = RedirectResponse(service.url_prefix + "/import-cookie", status_code=303)
        response.set_cookie(
            "ojol_import",
            session,
            max_age=900,
            httponly=True,
            secure=urlsplit(service.public_url()).scheme == "https",
            samesite="lax",
            path=service.url_prefix + "/",
        )
        return response

    @app.get("/a/{account_id}/import-cookie", response_class=HTMLResponse)
    @app.get("/import-cookie", response_class=HTMLResponse)
    async def form(request: Request):
        service = resolve(request)
        require_access(request)
        token = service.access.csrf_token(request.cookies.get("ojol_import"))
        if token is None:
            raise HTTPException(403, "Sesi import kedaluwarsa; minta link baru di bot")
        return (
            (ROOT / "ojol/cookie_form.html")
            .read_text()
            .replace("{{CSRF_TOKEN}}", token)
            .replace("{{ACCOUNT_NAME}}", html.escape(service.settings.account_name or "Utama"))
            .replace("{{IMPORT_PATH}}", service.url_prefix + "/import-cookie")
        )

    @app.post("/a/{account_id}/import-cookie", response_class=HTMLResponse)
    @app.post("/import-cookie", response_class=HTMLResponse)
    async def submit(request: Request):
        service = resolve(request)
        settings = service.settings
        require_access(request)
        if (
            request.headers.get("content-type", "").split(";")[0]
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(415, "Gunakan form import cookie")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                raise HTTPException(413, "Cookie terlalu besar")
        from .session_transfer import import_session, parse_cookie_input

        try:
            fields = parse_qs(body.decode())
            if not service.access.valid_csrf(
                request.cookies.get("ojol_import"), fields.get("csrf", [""])[0]
            ):
                raise HTTPException(
                    403, "Form kedaluwarsa/berubah. Buka ulang link Import Cookie terbaru."
                )
            payload = parse_cookie_input(fields.get("cookie", [""])[0])
        except (ValueError, TypeError, KeyError, UnicodeError):
            return HTMLResponse(
                "Cookie tidak valid. Kembali dan masukkan cookie sesi KampungSebelah saja.",
                status_code=400,
            )
        # Registry mutations and imports serialize, so revocation cannot race session installation.
        async with manager.lock if manager else asyncio.Lock(), service.lock:
            require_access(request)
            if maintenance := held_window(service.maintenance_file):
                return HTMLResponse(maintenance.message(), status_code=503)
            digest = None
            if manager:
                account = manager.registry.get(service.account_id)
                try:
                    digest = manager.registry.check_cookie(account["id"], payload)
                except ValueError:
                    return HTMLResponse(
                        "Cookie sudah terhubung ke akun lain. Gunakan akun tersebut.",
                        status_code=409,
                    )
            await service.stop_worker()
            try:
                await import_session(settings, json.dumps(payload))
                if manager:
                    manager.registry.bind_cookie(service.account_id, digest)
            except Exception as exc:
                from .session_transfer import STAGE

                queue_error(
                    settings,
                    RuntimeError("Import cookie gagal; sesi tidak dapat diverifikasi"),
                    STAGE,
                    {
                        "cause": type(exc).__name__,
                        "mcp_tool": getattr(exc, "operation", None),
                        "http_category": getattr(exc, "category", None),
                        "account_id": service.account_id,
                    },
                )
                await flush_notices(settings)
                return HTMLResponse(
                    "Import gagal. Periksa cookie, lalu minta link baru melalui tombol Import Cookie.",
                    status_code=400,
                )
            service.access.revoke()
        response = HTMLResponse(
            "<html lang='id'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Import berhasil</title><h1>Cookie berhasil diimpor</h1><p>Sesi game terverifikasi. Kembali ke Telegram dan tekan <strong>Jalankan Ojol</strong>.</p></html>"
        )
        response.delete_cookie("ojol_import", path=service.url_prefix + "/")
        return response

    app.state.management = manager
    return app


def main():
    try:
        settings = load_settings()
    except ValueError:
        raise SystemExit(
            "Konfigurasi tidak valid; periksa file env. Nilai rahasia tidak dicetak."
        ) from None
    settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if len(sys.argv) > 1:
        if sys.argv[1] == "set-url" and len(sys.argv) == 3:
            if settings.env == "production":
                raise SystemExit(
                    "Ubah OJOL_LOGIN_PUBLIC_URL pada .env lalu recreate service production."
                )
            (settings.runtime_dir / "public-url").write_text(
                Settings.secure_login_origin(sys.argv[2])
            )
            print("URL import cookie publik diperbarui; tidak mencetak link akses rahasia")
            return
        if sys.argv[1] == "notify-import":
            directory = settings.runtime_dir / "control-commands"
            directory.mkdir(exist_ok=True, mode=0o700)
            (directory / f"{uuid4().hex}.json").write_text(json.dumps({"command": "import_cookie"}))
            print("Permintaan link import cookie masuk antrean bot")
            return
        raise SystemExit("Gunakan set-url URL atau notify-import")
    uvicorn.run(create_app(settings), host="0.0.0.0", port=6080, access_log=False)


if __name__ == "__main__":
    main()
