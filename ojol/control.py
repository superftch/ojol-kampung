"""Private Telegram buttons, daily reports, and one-use HTTPS cookie import."""

import asyncio
import html
import json
import os
import re
import shutil
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import ceil
from pathlib import Path
from random import choice
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .auto_settings import AUTO_LABELS, auto_flags, set_auto_flag
from .cleanup import find_unvisited, scan
from .cli import exclusive_lock, running
from .config import load_settings
from .finance import WIB, report_date
from .healing import write_private
from .http_api import HttpCoreError, OjolHttpApi
from .identity import cached_profile
from .journal import Journal, unresolved_action
from .login_access import LoginAccess
from .maintenance import GAME_COMMANDS, SCHEDULE_FILE, held_window, read_window
from .models import NEEDS, ROOT, Settings, now
from .study import AUTO_SUBJECT, STUDY_LABELS, SUBJECTS, subjects
from .telegram import (
    BUTTON_COMMANDS,
    TelegramClient,
    TelegramError,
    acknowledge_callback,
    authorized_message,
    flush_notices,
    keyboard_status,
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
        from .worker_service import send_worker_command

        try:
            await send_worker_command(
                self.settings.runtime_dir,
                {"action": "stop", "account_id": self.account_id},
                timeout=1.0,
            )
        except Exception:
            pass

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

    async def fetch_online_status(self):
        async with OjolHttpApi(self.settings.runtime_dir) as api:
            return await api.fetch_online_status()

    def status(self):
        directory = self.settings.runtime_dir
        data, status_updated = status_record(directory / "status.json")
        state = data.get("snapshot") or {}
        sync, _ = status_record(directory / "game-sync.json")
        synced_at = status_timestamp(sync.get("checked_at"))
        observed = status_timestamp(data.get("snapshot_received_at") or state.get("observed_at"))
        if (
            synced_at
            and (observed is None or synced_at > observed)
            and isinstance(sync.get("snapshot"), dict)
        ):
            state = sync["snapshot"]
            observed = synced_at
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
                if not busy:
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
        seconds = state.get("remaining_seconds")
        profile = cached_profile(directory)
        name = profile["nickname"] if profile else self.settings.account_name or "Utama"
        lines = [f"🛵 Status Ojol · {name}", "", worker]
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
        if data.get("event") in {"rekonsiliasi", "rekonsiliasi_otomatis"} and (active or starting):
            lines.append("Bot sedang mencocokkan hasil aksi terakhir dengan game.")
            if data.get("reconciliation_attempt"):
                lines.append(f"Pemeriksaan otomatis {data['reconciliation_attempt']}/3.")
            if data.get("reconciliation_pending"):
                lines.append(
                    f"{data['reconciliation_pending']} hasil aksi masih diperiksa otomatis."
                )
            for action in sync.get("reconciliation", []):
                if action.get("status_after") not in {"pending", "uncertain"}:
                    continue
                lines.append(f"⏳ Aksi #{action['action_id']} • {action['description']}")
                created = status_timestamp(action.get("created"))
                if created:
                    lines.append(f"Waktu aksi • {created.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB")
                lines.append(f"Tertahan • {action['reason']}")
                before, current = action.get("before", {}), action.get("observed", {})
                lines.append(
                    f"Saldo • {before.get('wallet', '?')} → {current.get('wallet', '?')} koin"
                )
        if state.get("village") or state.get("home_plot"):
            lines.append(
                f"🏠 Rumah • {state.get('home_plot') or '?'} • {state.get('village') or '?'}"
            )
        if state.get("trip"):
            lines.extend(["", state["trip"]])
        arrives = status_timestamp(state.get("arrive_at"))
        if arrives:
            lines.append(f"Perkiraan tiba • {arrives.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB")
        if not active and not starting:
            pending = unresolved_action(directory)
            error, error_updated = status_record(directory / "last-error.json")
            reason = None
            if (
                error_updated >= status_updated
                and error.get("http_category") == "reconciliation_failed"
            ):
                reason = error["message"]
            elif pending:
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
            if error_updated >= status_updated and error.get("error_id"):
                lines.append(f"ID error: {error['error_id']}")

        flags = auto_flags(directory)
        lines.extend(["", "Kebutuhan akun · Auto ON/OFF"])
        lines.extend(
            f"{label} • {'ON' if flags[key] else 'OFF'} • {state.get('needs', {}).get(key, '?')}%"
            for key, label in AUTO_LABELS.items()
            if key in NEEDS
        )
        lines.extend(["", "Pengaturan Auto"])
        lines.extend(
            f"{label} • {'ON' if flags[key] else 'OFF'}"
            for key, label in AUTO_LABELS.items()
            if key not in NEEDS
        )
        choices = subjects(directory)
        lines.extend(
            f"Bidang {'Perpus' if mode == 'perpus' else 'Kuliah'} • {'Auto (Pilih Otomatis)' if choices[mode] == AUTO_SUBJECT else SUBJECTS.get(choices[mode], 'belum dipilih')}"
            for mode in STUDY_LABELS
        )
        maintenance = held_window(self.maintenance_file)
        if maintenance:
            lines.append(maintenance.message())
        auto_start = "ON" if self.settings.auto_start else "OFF"
        if self.auto_start_pending:
            auto_start += " · menunggu maintenance" if maintenance else " · menunggu slot"
        vehicle = state.get("ojol_vehicle")
        if vehicle in ("motor", "mobil"):
            lines.extend(["", f"Kendaraan Ojol • {vehicle.capitalize()}"])
        if state.get("ojol_hours_left") is not None:
            lines.append(f"⏱ Sisa Jam Narik • {state.get('ojol_hours_left')} jam")
        elif state.get("ojol_shift_done"):
            lines.append("⏱ Sisa Jam Narik • Habis (Lanjut besok 00.00 WIB)")
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
        lines.extend(
            [
                "",
                "🎮 Ringkasan game terakhir",
                f"Trip selesai pada hari data game • {state.get('today_count') if state.get('today_count') is not None else '?'}",
                f"Pendapatan pada hari data game • {koin(state.get('today_income', '?'))}",
            ]
        )
        if synced_at:
            lines.append(f"Riwayat dicocokkan • {synced_at.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB")
        target_display = (
            f"Smart (Fisik {self.settings.threshold_for('fisik')}%, Bensin {self.settings.threshold_for('fuel')}%, dll.)"
            if self.settings.smart_thresholds or self.settings.need_thresholds
            else f"{self.settings.threshold}%"
        )
        lines.extend(
            [
                "",
                "🤖 Sesi bot",
                f"Trip selesai sesi ini • {data.get('completed', 0)}",
                f"Belanja sesi ini • {koin(data.get('spent', 0))}",
                f"Target isi ulang • {target_display}",
                f"Batas belanja • {koin(self.settings.max_spend) if self.settings.max_spend is not None else 'tanpa batas'}",
                f"Batas trip • {self.settings.max_jobs if self.settings.max_jobs is not None else 'tanpa batas'}",
                f"Batas waktu • {str(self.settings.max_minutes) + ' menit' if self.settings.max_minutes is not None else 'tanpa batas'}",
            ]
        )
        started = status_timestamp(data.get("run_started_at"))
        if started:
            lines.append(f"Mulai sesi • {started.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB")
        from .session_transfer import parse_cookie_input, session_expired

        try:
            cookie = parse_cookie_input((directory / "http-session.json").read_text())
            expires = cookie["cookies"][0].get("expires")
            cookie_status = "perlu login ulang" if session_expired(cookie) else "tersimpan"
            if expires is not None:
                expiry_date = datetime.fromtimestamp(expires, WIB)
                cookie_status += f" • berlaku sampai {expiry_date:%d-%m-%Y %H:%M} WIB"
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            cookie_status = "belum terhubung"
        lines.extend(["", f"🔑 Sesi game • {cookie_status}"])
        schedule = state.get("sleep_schedule")
        if schedule:
            start, end = schedule["start"], schedule["end"]
            hours = f"{start // 60:02d}.{start % 60:02d}–{end // 60:02d}.{end % 60:02d} WIB"
            lines.append(f"🌙 Tidur otomatis • {'ON' if schedule['auto'] else 'OFF'} • {hours}")
        if phase == "sleeping" and active:
            lines.append("Semua Auto dijeda sampai karakter bangun di game.")
        window = read_window(self.maintenance_file)
        if window:
            lines.append(f"Jadwal maintenance • {window.description()}")
        lines.extend(["", "🧾 Riwayat terbaru dari game"])
        receipts = state.get("game_history") or []
        if not receipts:
            lines.append("Belum ada riwayat pada data game yang dibaca.")
        for receipt in receipts[:5]:
            at = status_timestamp(receipt.get("done_at"))
            clock = at.astimezone(WIB).strftime("%d-%m %H:%M") if at else "waktu belum tersedia"
            lines.append(
                f"{clock} • {receipt.get('origin', '?')} → {receipt.get('destination', '?')}\n"
                f"Ongkos diterima {koin(receipt.get('amount', '?'))}"
            )
        return "\n".join(lines)

    def status_kebutuhan(self):
        directory = self.settings.runtime_dir
        data, status_updated = status_record(directory / "status.json")
        state = data.get("snapshot") or {}
        sync, _ = status_record(directory / "game-sync.json")
        synced_at = status_timestamp(sync.get("checked_at"))
        observed = status_timestamp(data.get("snapshot_received_at") or state.get("observed_at"))
        if (
            synced_at
            and (observed is None or synced_at > observed)
            and isinstance(sync.get("snapshot"), dict)
        ):
            state = sync["snapshot"]
            observed = synced_at
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
                if not busy:
                    recorded_worker = False
            except PermissionError:
                pass
        active = busy and recorded_worker and (not managed or self.worker.pid == pid)
        starting = managed and not active
        flags = auto_flags(directory)
        if active:
            if flags.get("ojol"):
                worker = "🟢 Worker aktif (Ojol & Kebutuhan)"
            else:
                worker = "🟢 Worker aktif (Auto Kebutuhan)"
        elif starting:
            worker = "🟡 Worker memulai"
        elif busy:
            worker = "🟠 Worker lain sedang memakai akun ini"
        else:
            worker = "🔴 Worker berhenti" if data else "⚪ Worker belum dijalankan"

        profile = cached_profile(directory)
        name = profile["nickname"] if profile else self.settings.account_name or "Utama"
        lines = [f"🍲 Status Kebutuhan · {name}", "", worker]

        wallet = state.get("wallet")
        if wallet is not None:
            lines.append(f"💰 Saldo • {koin(wallet)}")
        if state.get("village") or state.get("home_plot"):
            lines.append(
                f"🏠 Rumah • {state.get('home_plot') or '?'} • {state.get('village') or '?'}"
            )

        lines.extend(["", "📊 Bar Kebutuhan · Nilai & Target:"])
        need_icons = {
            "makan": "🍚",
            "kesehatan": "❤️",
            "fisik": "💪",
            "rekreasi": "🎡",
            "kebersihan": "🧼",
            "wc": "🚽",
            "penampilan": "💇",
            "rumah": "🏡",
        }
        needs_dict = state.get("needs") or {}
        for key in NEEDS:
            label = AUTO_LABELS.get(key, key.capitalize())
            icon = need_icons.get(key, "•")
            val = needs_dict.get(key, "?")
            on_str = "ON" if flags.get(key) else "OFF"
            thresh = self.settings.threshold_for(key)
            lines.append(f"{icon} {label} • {val}% · Auto {on_str} (target {thresh}%)")

        kondisi = state.get("kondisi") or {}
        bersih = state.get("bersih") or {}
        kondisi_lines = []
        if kondisi:
            bau_str = "Bau sekali ⚠️" if kondisi.get("bau") else "Bersih ✓"
            kebelet_str = "Kebelet sekali ⚠️" if kondisi.get("kebelet") else "Normal ✓"
            potong = (
                f"-{kondisi['upahPotongBps'] // 100}%"
                if kondisi.get("upahPotongBps")
                else "Tidak ada (0%)"
            )
            kondisi_lines.append(f"• Kebersihan badan • {bau_str}")
            kondisi_lines.append(f"• Buang air • {kebelet_str}")
            kondisi_lines.append(f"• Potongan upah ojol • {potong}")
        if bersih:
            kondisi_lines.append(
                f"• Kuota mandi hari ini • {bersih.get('mandi', 0)}/{bersih.get('mandiMaks', 2)}"
            )
            kondisi_lines.append(
                f"• Kuota sikat gigi hari ini • {bersih.get('sikat', 0)}/{bersih.get('sikatMaks', 3)}"
            )
        if kondisi_lines:
            lines.extend(["", "🚿 Kondisi Karakter:"] + kondisi_lines)

        lines.extend(["", "🌱 Aktivitas Mandiri Lainnya:"])
        kebun_on = "ON" if flags.get("kebun") else "OFF"
        lines.append(f"• Kebun & kolam • Auto {kebun_on}")
        choices = subjects(directory)
        for mode in STUDY_LABELS:
            study_on = "ON" if flags.get(mode) else "OFF"
            label_m = "Perpustakaan" if mode == "perpus" else "Kuliah"
            subj = (
                "Auto (Pilih Otomatis)"
                if choices.get(mode) == AUTO_SUBJECT
                else SUBJECTS.get(choices.get(mode), "belum dipilih")
            )
            lines.append(f"• {label_m} • Auto {study_on} ({subj})")

        moment = now()
        if observed:
            age = max(0, int((moment - observed).total_seconds()))
            age_text = (
                f"{age} detik"
                if age < 60
                else f"{age // 60} menit"
                if age < 3600
                else f"{age // 3600} jam"
            )
            stale = " · data lama, worker tidak aktif" if not active else ""
            lines.extend(
                [
                    "",
                    f"🕒 Update terakhir: {observed.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB ({age_text} lalu){stale}",
                ]
            )
        else:
            lines.extend(["", "🕒 Update terakhir: belum ada data"])

        phase = state.get("phase")
        if phase == "sleeping" and active:
            lines.append("🌙 Semua Auto dijeda sampai karakter bangun di game.")
        if not active and not starting:
            lines.append("\n💡 Tekan Jalankan Kebutuhan untuk memulai auto kebutuhan.")
        return "\n".join(lines)

    def auto_kebutuhan_summary(self):
        directory = self.settings.runtime_dir
        flags = auto_flags(directory)
        profile = cached_profile(directory)
        name = profile["nickname"] if profile else self.settings.account_name or "Utama"
        lines = [f"⚙️ Auto Kebutuhan · {name}", ""]
        lines.append("Pengaturan fitur otomatis kebutuhan karakter:")
        for key in NEEDS:
            label = AUTO_LABELS.get(key, key.capitalize())
            lines.append(
                f"• {label} • {'ON' if flags.get(key) else 'OFF'} (target {self.settings.threshold_for(key)}%)"
            )
        lines.append(f"• Kebun & kolam • {'ON' if flags.get('kebun') else 'OFF'}")
        choices = subjects(directory)
        for mode in STUDY_LABELS:
            label_m = "Perpus" if mode == "perpus" else "Kuliah"
            subj = (
                "Auto (Pilih Otomatis)"
                if choices.get(mode) == AUTO_SUBJECT
                else SUBJECTS.get(choices.get(mode), "belum dipilih")
            )
            lines.append(f"• {label_m} • {'ON' if flags.get(mode) else 'OFF'} ({subj})")
        lines.append("\nTekan tombol di bawah untuk menjalankan atau menghentikan auto kebutuhan.")
        return "\n".join(lines)

    def summary(self):
        directory = self.settings.runtime_dir
        data, status_updated = status_record(directory / "status.json")
        state = data.get("snapshot") or {}
        sync, _ = status_record(directory / "game-sync.json")
        synced_at = status_timestamp(sync.get("checked_at"))
        observed = status_timestamp(data.get("snapshot_received_at") or state.get("observed_at"))
        if (
            synced_at
            and (observed is None or synced_at > observed)
            and isinstance(sync.get("snapshot"), dict)
        ):
            state = sync["snapshot"]

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
                if not busy:
                    recorded_worker = False
            except PermissionError:
                pass
        active = busy and recorded_worker and (not managed or self.worker.pid == pid)

        from .session_transfer import parse_cookie_input, session_expired

        has_cookie = False
        cookie_valid = False
        try:
            cookie = parse_cookie_input((directory / "http-session.json").read_text())
            has_cookie = True
            cookie_valid = not session_expired(cookie)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            pass

        phase = state.get("phase")
        rem = state.get("remaining_seconds")
        if phase == "delivering" and type(rem) is int and rem > 0:
            arrive_at = state.get("arrive_at")
            if arrive_at:
                try:
                    target_time = datetime.fromisoformat(str(arrive_at).replace("Z", "+00:00"))
                    rem = max(0, int((target_time - now()).total_seconds()))
                except Exception:
                    if observed:
                        elapsed = int((now() - observed).total_seconds())
                        rem = max(0, rem - elapsed)
            elif observed:
                elapsed = int((now() - observed).total_seconds())
                rem = max(0, rem - elapsed)

        if not has_cookie:
            status_text = "Belum hubungkan cookie"
            icon = "⚪"
        elif not cookie_valid:
            status_text = "Sesi kedaluwarsa"
            icon = "⚠️"
        elif active:
            if phase == "delivering":
                time_str = f" ({rem // 60}:{rem % 60:02d})" if rem is not None else ""
                status_text = f"Mengantar order{time_str}"
                icon = "🟢"
            elif phase == "searching":
                status_text = "Mencari order"
                icon = "🟢"
            elif phase == "sleeping":
                status_text = "Tidur di game"
                icon = "💤"
            elif phase == "idle":
                flags = auto_flags(directory)
                if not flags.get("ojol") and any(flags.get(k) for k in NEEDS):
                    status_text = "Memantau Kebutuhan"
                elif (
                    flags.get("ojol") is True
                    and state.get("ojol_min_fuel") is not None
                    and (
                        state.get("ojol_fuel_blocked")
                        or state.get("fuel", 0) < state["ojol_min_fuel"]
                    )
                ):
                    status_text = "Menunggu isi SPBU"
                else:
                    status_text = "Standby"
                icon = "🟢"
            else:
                status_text = "Aktif"
                icon = "🟢"
        else:
            status_text = "Berhenti"
            icon = "⚪"

        wallet = state.get("wallet")
        trips = state.get("today_count")
        if trips is None:
            trips = data.get("completed", 0)

        fuel = state.get("fuel")
        condition = state.get("condition")
        kuota = state.get("data")

        online_data, online_updated = status_record(directory / "online-status.json")
        is_online = False
        if online_updated:
            age = time.time() - (online_updated / 1e9)
            if age <= 120 and online_data.get("online"):
                is_online = True

        return {
            "active": active,
            "has_cookie": has_cookie,
            "cookie_valid": cookie_valid,
            "phase": phase,
            "remaining_seconds": rem,
            "trip": state.get("trip"),
            "sleep_schedule": state.get("sleep_schedule"),
            "icon": icon,
            "status_text": status_text,
            "wallet": str(wallet) if wallet is not None else None,
            "trips": trips,
            "fuel": fuel,
            "condition": condition,
            "data": kuota,
            "shift_done": bool(state.get("ojol_shift_done")),
            "hours_left": state.get("ojol_hours_left"),
            "online": is_online or active,
            "online_updated": (
                datetime.fromtimestamp(online_updated / 1e9, tz=UTC).isoformat()
                if online_updated
                else None
            ),
        }

    async def account_profit(self, day):
        directory = self.settings.runtime_dir
        wallet = None
        if self.settings.env == "testing" or not (directory / "http-session.json").is_file():
            issue = "Sesi game belum tersedia"
        else:
            from .ui import HttpUI

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

    def mode_buttons(self):
        prefix = f"acct:{self.account_id}:" if self.account_id else ""
        return {
            "inline_keyboard": [
                [
                    {"text": "🚗 Berkendara", "callback_data": prefix + "mode:kendara"},
                    {"text": "🤖 Otomatis", "callback_data": prefix + "mode:otomatis"},
                ]
            ]
        }

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

    async def command(self, command, *, auto_start=False, mode=None):
        if command in GAME_COMMANDS and (maintenance := held_window(self.maintenance_file)):
            if not (
                command in {"run_kebutuhan", "stop_kebutuhan"}
                and getattr(maintenance, "target", "all") == "ojol"
            ):
                if auto_start:
                    self.auto_start_pending = True
                return maintenance.message()
        if command in {"resume", "skip"}:
            from contextlib import closing

            from .journal import Journal

            # 1. Hentikan worker jika sedang berjalan agar tidak bertabrakan dengan rekonsiliasi baru
            try:
                await self.stop_worker()
            except Exception:
                pass

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
                try:
                    sync_data = json.loads(sync_path.read_text())
                    sync_data["reconciliation"] = []
                    sync_data["unresolved"] = 0
                    write_private(sync_path, sync_data)
                except Exception:
                    pass

            status_path = self.settings.runtime_dir / "status.json"
            if status_path.is_file():
                try:
                    st_data = json.loads(status_path.read_text())
                    st_data.pop("reconciliation_pending", None)
                    st_data.pop("reconciliation_attempt", None)
                    st_data["event"] = "berhenti"
                    st_data["reason"] = f"Aksi tertahan ({len(skipped)} aksi) dilewati manual oleh pengguna."
                    write_private(status_path, st_data)
                except Exception:
                    pass

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
        if command == "choose_mode":
            return (
                "🏍️ Pilih mode Ojol\n\n"
                "🚗 Berkendara — kamu kendarai sendiri di peta: tanpa batas 12 jam, "
                "bebas istirahat wajib, bot memilih order dengan tarif tertinggi.\n"
                "🤖 Otomatis — game yang menyetir: mengikuti kuota 12 jam dan "
                "jeda istirahat wajib 30 menit.\n\nPilih di tombol di bawah."
            )
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
                else "🔕 Notifikasi rutin OFF\n\nDetail error dan ID error, maintenance, "
                "startup/restart Docker, serta kabar tidur dan bangun tetap dikirim."
            )
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
        if command == "stop":
            await self.stop_worker()
            return "⏹ Aktivitas akun sudah dihentikan.\n\nTekan Jalankan Ojol atau Jalankan Kebutuhan jika ingin melanjutkan."
        if command == "run_kebutuhan":
            async with self.lock:
                if self.closing:
                    raise RuntimeError("Akun tidak tersedia. Pilih akun lain.")
                set_auto_flag(self.settings.runtime_dir, "ojol", False)
                for key in NEEDS:
                    set_auto_flag(self.settings.runtime_dir, key, True)
                if (self.worker and self.worker.returncode is None) or running(
                    self.settings.runtime_dir
                ):
                    return (
                        "🟢 Auto kebutuhan aktif. Bot sedang memantau dan mengisi kebutuhan karakter.\n\n"
                        "Tekan Status untuk melihat perkembangannya."
                    )
                if not self.settings.operator_authorized:
                    raise RuntimeError("Akun ini belum diizinkan menjalankan bot oleh admin.")
                self.access.revoke()
                await self.ensure_backend(require_session=True)
                await self.start_tunnel()
                if maintenance := held_window(self.maintenance_file):
                    if getattr(maintenance, "target", "all") == "all":
                        if auto_start:
                            self.auto_start_pending = True
                        return maintenance.message()
                from .worker_service import send_worker_command

                worker_resp = await send_worker_command(
                    self.settings.runtime_dir,
                    {
                        "action": "start",
                        "account_id": self.account_id,
                        "mode": None,
                        "auto_start": auto_start,
                        "needs_only": True,
                    },
                )
                if worker_resp is not None:
                    if not worker_resp.get("ok"):
                        raise RuntimeError(worker_resp.get("error") or worker_resp["message"])
                    self.expected_stop = False
                    return (
                        "▶️ Bot sedang memulai (Auto Kebutuhan)\n\n"
                        "Bot akan memantau dan mengisi kebutuhan karakter secara otomatis. "
                        "Tekan Status untuk melihat perkembangannya."
                    )

                config_file = os.environ.get("OJOL_CONFIG_FILE")
                args = [sys.executable, str(ROOT / "main.py")]
                if config_file:
                    args += ["--env-file", config_file]
                args += ["run", "--live"]
                self.expected_stop = False
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
                return (
                    "▶️ Bot sedang memulai (Auto Kebutuhan)\n\n"
                    "Bot akan memantau dan mengisi kebutuhan karakter secara otomatis. "
                    "Tekan Status untuk melihat perkembangannya."
                )
        if command == "run":
            async with self.lock:
                if self.closing:
                    raise RuntimeError("Akun tidak tersedia. Pilih akun lain.")
                set_auto_flag(self.settings.runtime_dir, "ojol", True)
                label = (
                    "Berkendara" if mode == "kendara" else "Otomatis" if mode == "otomatis" else ""
                )
                if (self.worker and self.worker.returncode is None) or running(
                    self.settings.runtime_dir
                ):
                    return (
                        "🟢 Bot sudah aktif untuk akun ini. Auto Ojol diaktifkan"
                        + (f" (mode {label}).\n\n" if label else ".\n\n")
                        + "Aktivitas mengikuti pilihan di menu Auto. Tekan Status untuk melihat perkembangannya."
                    )
                if not self.settings.operator_authorized:
                    raise RuntimeError("Akun ini belum diizinkan menjalankan Ojol oleh admin.")
                self.access.revoke()
                await self.ensure_backend(require_session=True)
                await self.start_tunnel()
                if maintenance := held_window(self.maintenance_file):
                    if auto_start:
                        self.auto_start_pending = True
                    return maintenance.message()

                from .worker_service import send_worker_command

                worker_resp = await send_worker_command(
                    self.settings.runtime_dir,
                    {
                        "action": "start",
                        "account_id": self.account_id,
                        "mode": mode,
                        "auto_start": auto_start,
                    },
                )
                if worker_resp is not None:
                    if not worker_resp.get("ok"):
                        raise RuntimeError(worker_resp.get("error") or worker_resp["message"])
                    self.expected_stop = False
                    label = (
                        "Berkendara"
                        if mode == "kendara"
                        else "Otomatis"
                        if mode == "otomatis"
                        else ""
                    )
                    return (
                        "▶️ Bot sedang memulai"
                        + (f" (mode {label})\n\n" if label else "\n\n")
                        + "Aktivitas mengikuti pilihan di menu Auto. Tekan Status untuk melihat perkembangannya."
                    )

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
                        **({"OJOL_OJOL_MODE": mode} if mode in {"kendara", "otomatis"} else {}),
                    },
                )
                label = (
                    "Berkendara" if mode == "kendara" else "Otomatis" if mode == "otomatis" else ""
                )
                return (
                    "▶️ Bot sedang memulai"
                    + (f" (mode {label})\n\n" if label else "\n\n")
                    + "Aktivitas mengikuti pilihan di menu Auto. Tekan Status untuk melihat perkembangannya."
                )
        return "Pilih aktivitas lewat tombol di bawah. Buka Akun Saya untuk mengganti akun."

    async def execute(self, command, *, mode=None):
        try:
            response = await self.command(command, mode=mode)
            if command in {"status", "status_kebutuhan", "auto_kebutuhan"}:
                markup = keyboard_status()
            elif command == "profit" or command.startswith("profit:"):
                markup = self.profit_buttons(command.split(":", 1)[1] if ":" in command else None)
            elif command == "choose_mode":
                markup = self.mode_buttons()
            else:
                markup = None
            queue_notice(self.settings, response, reply_markup=markup)
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
        await flush_notices(self.settings)

    async def poll_telegram(self):
        cursor_file = self.settings.runtime_dir / "telegram-offset"
        offset = int(cursor_file.read_text()) if cursor_file.exists() else 0
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
                        offset = max(offset, update["update_id"] + 1)
                        cursor_file.write_text(str(offset))
                        if authorized_message(update, self.settings):
                            callback = update.get("callback_query")
                            if callback:
                                if not await acknowledge_callback(api, callback["id"]):
                                    continue
                                command = callback.get("data", "")
                                mode = None
                                if re.fullmatch(r"mode:(kendara|otomatis)", command):
                                    mode = command.split(":", 1)[1]
                                    command = "run"
                                if (
                                    command == "run"
                                    or command == "run_kebutuhan"
                                    or command == "stop_ojol"
                                    or command == "stop_kebutuhan"
                                    or command == "resume"
                                    or command == "choose_date"
                                    or re.fullmatch(r"profit:\d{4}-\d{2}-\d{2}", command)
                                ):
                                    await self.execute(command, mode=mode)
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
                    retryable = isinstance(exc, TelegramError) and exc.retryable
                    now_ts = time.time()
                    if (outage is None or outage != retryable) and (
                        not retryable or now_ts - last_outage_notice >= 900
                    ):
                        queue_error(
                            self.settings,
                            exc,
                            "telegram.poll",
                            stop_worker=not retryable,
                        )
                        last_outage_notice = now_ts
                    outage = retryable
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
            and self.settings.telegram_enabled
            and self.settings.telegram_bot_token.get_secret_value()
            and self.settings.telegram_chat_id
        ):
            self.tasks.append(
                asyncio.create_task(self.guard_task(self.poll_telegram, "telegram.poll"))
            )
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

    if isinstance(service, MultiAccountService):
        manager = service
        service = None
    else:
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
    app.mount("/ui", StaticFiles(directory=ROOT / "ojol" / "ui_assets"), name="ui")
    app.state.manager = manager
    app.state.service = service

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
                "Content-Security-Policy": (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://telegram.org https://oauth.telegram.org; "
                    "frame-src https://oauth.telegram.org; "
                    "style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: https://telegram.org https://*.telegram.org; "
                    "connect-src 'self'; "
                    "form-action 'self'; "
                    "frame-ancestors 'none'"
                ),
            }
        )
        return response

    @app.get("/health")
    async def health():
        return {
            "service": "ok",
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
                    manager.service(service.account_id)
            except Exception as exc:
                from .session_transfer import STAGE

                queue_error(
                    settings,
                    RuntimeError("Import cookie gagal; sesi tidak dapat diverifikasi"),
                    STAGE,
                    {
                        "cause": type(exc).__name__,
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

    from .web_api import register_web_routes

    register_web_routes(app, settings, manager=manager, service=service)

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
