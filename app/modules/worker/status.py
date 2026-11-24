"""Shared runtime status inspection and web summary formatting."""

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from math import ceil
from pathlib import Path
from typing import Any

from app.core.formatting import format_koin as koin
from app.core.locks import running
from app.core.models import AUTO_SUBJECT, NEEDS, STUDY_LABELS, SUBJECTS, Settings, now
from app.core.storage import status_record, status_timestamp
from app.integrations.kampung.http_api import coin, display
from app.integrations.kampung.identity import cached_profile
from app.integrations.kampung.session_transfer import parse_cookie_input, session_expired
from app.modules.gameplay.study import subjects
from app.modules.ledger.finance import WIB
from app.modules.ledger.repository import Journal, unresolved_action
from app.modules.notifications.service import redact
from app.modules.worker.maintenance import held_window, read_window
from app.modules.worker.settings import AUTO_LABELS, auto_flags


@dataclass
class RuntimeStatusInfo:
    """Merged runtime status.json + game-sync.json + worker liveness view."""

    data: dict[str, Any]
    status_updated: int
    sync: dict[str, Any]
    synced_at: datetime | None
    state: dict[str, Any]
    observed: datetime | None
    busy: bool
    managed: bool
    active: bool
    starting: bool


def inspect_runtime_status(
    directory: Path, worker_proc: Any = None, *, is_running: Any = running
) -> RuntimeStatusInfo:
    """Read status/sync files and evaluate whether a worker is actively running."""
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

    busy = is_running(directory)
    managed = worker_proc is not None and worker_proc.returncode is None
    pid = data.get("pid")
    recorded_worker = (
        type(pid) is int and pid > 0 and data.get("event") not in {"berhenti", "gagal", "dry_run"}
    )
    if busy and recorded_worker:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            if not busy:
                recorded_worker = False
        except PermissionError:
            pass
    active = busy and recorded_worker and (not managed or worker_proc.pid == pid)
    starting = managed and not active
    return RuntimeStatusInfo(
        data=data,
        status_updated=status_updated,
        sync=sync,
        synced_at=synced_at,
        state=state,
        observed=observed,
        busy=busy,
        managed=managed,
        active=active,
        starting=starting,
    )


def format_age_text(seconds: int) -> str:
    """Format an integer second age into concise Indonesian units."""
    if seconds < 60:
        return f"{seconds} detik"
    if seconds < 3600:
        return f"{seconds // 60} menit"
    return f"{seconds // 3600} jam"


def _worker_badge(info: RuntimeStatusInfo, *, active_label: str = "🟢 Worker aktif") -> str:
    if info.active:
        return active_label
    if info.starting:
        return "🟡 Worker memulai"
    if info.busy:
        return "🟠 Worker lain sedang memakai akun ini"
    return "🔴 Worker berhenti" if info.data else "⚪ Worker belum dijalankan"


def _account_display_name(directory: Path, settings: Settings) -> str:
    profile = cached_profile(directory)
    return profile["nickname"] if profile else settings.account_name or "Utama"


def _read_cookie_meta(directory: Path) -> tuple[bool, bool, int | float | None]:
    try:
        cookie = parse_cookie_input((directory / "http-session.json").read_text())
        expires = cookie["cookies"][0].get("expires")
        return True, not session_expired(cookie), expires
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return False, False, None


def format_ojol_status(
    settings: Settings,
    *,
    worker_proc: Any,
    expected_stop: bool,
    auto_start_pending: bool,
    maintenance_file: Path,
    tunnel_alive: bool,
    is_running: Any = running,
    current_time: Any = now,
) -> str:
    """Render the detailed Status Ojol report."""
    directory = settings.runtime_dir
    info = inspect_runtime_status(directory, worker_proc, is_running=is_running)
    data, state, sync = info.data, info.state, info.sync
    observed, synced_at = info.observed, info.synced_at
    active, starting = info.active, info.starting

    phases = {
        "idle": "menunggu order",
        "searching": "mencari order",
        "delivering": "dalam perjalanan",
        "complete": "siap klaim ongkos",
        "sleeping": "karakter tidur",
        "unknown": "tidak diketahui",
    }
    phase = state.get("phase")
    moment = current_time()
    seconds = state.get("remaining_seconds")
    name = _account_display_name(directory, settings)
    lines = [f"🛵 Status Ojol · {name}", "", _worker_badge(info)]

    trip = f"📍 Trip: {phases.get(phase, 'belum terbaca')}"
    if observed:
        age = max(0, int((moment - observed).total_seconds()))
        if active and phase == "delivering" and type(seconds) is int and seconds > 0:
            remaining = max(0, ceil(seconds - (moment - observed).total_seconds()))
            trip += f" · sisa trip ±{remaining // 60}:{remaining % 60:02d}"
        lines.append(trip)
        stale = " · data lama, worker tidak aktif" if not active else ""
        lines.append(
            f"🕒 Update terakhir: {observed.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB "
            f"({format_age_text(age)} lalu){stale}"
        )
    else:
        lines.extend([trip, "🕒 Update terakhir: belum ada data"])

    if data.get("event") in {"rekonsiliasi", "rekonsiliasi_otomatis"} and (active or starting):
        lines.append("Bot sedang mencocokkan hasil aksi terakhir dengan game.")
        if data.get("reconciliation_attempt"):
            lines.append(f"Pemeriksaan otomatis {data['reconciliation_attempt']}/3.")
        if data.get("reconciliation_pending"):
            lines.append(f"{data['reconciliation_pending']} hasil aksi masih diperiksa otomatis.")
        for action in sync.get("reconciliation", []):
            if action.get("status_after") not in {"pending", "uncertain"}:
                continue
            lines.append(f"⏳ Aksi #{action['action_id']} • {action['description']}")
            created = status_timestamp(action.get("created"))
            if created:
                lines.append(f"Waktu aksi • {created.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB")
            lines.append(f"Tertahan • {action['reason']}")
            before, current = action.get("before", {}), action.get("observed", {})
            lines.append(f"Saldo • {before.get('wallet', '?')} → {current.get('wallet', '?')} koin")

    if state.get("village") or state.get("home_plot"):
        lines.append(f"🏠 Rumah • {state.get('home_plot') or '?'} • {state.get('village') or '?'}")
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
            error_updated >= info.status_updated
            and error.get("http_category") == "reconciliation_failed"
        ):
            reason = error["message"]
        elif pending:
            reason = (
                f"Aksi #{pending[0]} ({pending[1]}) menunggu rekonsiliasi "
                "(hasil klik terakhir belum pasti, dicek dulu sebelum lanjut)"
            )
        elif error_updated >= info.status_updated and error.get("message"):
            reason = error["message"]
        elif data.get("event") in {"berhenti", "gagal"}:
            reason = data.get("reason")
        elif expected_stop and data:
            reason = "Dihentikan pengguna"
        if reason:
            lines.append(f"⚠️ Alasan berhenti: {redact(reason)}")
        if error_updated >= info.status_updated and error.get("error_id"):
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
        f"Bidang {'Perpus' if mode == 'perpus' else 'Kuliah'} • "
        f"{'Auto (Pilih Otomatis)' if choices[mode] == AUTO_SUBJECT else SUBJECTS.get(choices[mode], 'belum dipilih')}"
        for mode in STUDY_LABELS
    )
    maintenance = held_window(maintenance_file)
    if maintenance:
        lines.append(maintenance.message())
    auto_start = "ON" if settings.auto_start else "OFF"
    if auto_start_pending:
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
            f"💰 Saldo utama {state.get('wallet', '?')} koin (minimum {settings.min_balance} koin)",
            "",
            f"🔁 Auto-start saat boot: {auto_start}",
        ]
    )
    if settings.tunnel_enabled:
        lines.append(f"🌐 Tunnel: {'aktif' if tunnel_alive else 'berhenti'}")

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
        f"Smart (Fisik {settings.threshold_for('fisik')}%, Bensin {settings.threshold_for('fuel')}%, dll.)"
        if settings.smart_thresholds or settings.need_thresholds
        else f"{settings.threshold}%"
    )
    lines.extend(
        [
            "",
            "🤖 Sesi bot",
            f"Trip selesai sesi ini • {data.get('completed', 0)}",
            f"Belanja sesi ini • {koin(data.get('spent', 0))}",
            f"Target isi ulang • {target_display}",
            f"Batas belanja • {koin(settings.max_spend) if settings.max_spend is not None else 'tanpa batas'}",
            f"Batas trip • {settings.max_jobs if settings.max_jobs is not None else 'tanpa batas'}",
            f"Batas waktu • {str(settings.max_minutes) + ' menit' if settings.max_minutes is not None else 'tanpa batas'}",
        ]
    )
    started = status_timestamp(data.get("run_started_at"))
    if started:
        lines.append(f"Mulai sesi • {started.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB")

    has_cookie, cookie_valid, expires = _read_cookie_meta(directory)
    if has_cookie:
        cookie_status = "tersimpan" if cookie_valid else "perlu login ulang"
        if expires is not None:
            expiry_date = datetime.fromtimestamp(expires, WIB)
            cookie_status += f" • berlaku sampai {expiry_date:%d-%m-%Y %H:%M} WIB"
    else:
        cookie_status = "belum terhubung"
    lines.extend(["", f"🔑 Sesi game • {cookie_status}"])

    schedule = state.get("sleep_schedule")
    if schedule:
        start, end = schedule["start"], schedule["end"]
        hours = f"{start // 60:02d}.{start % 60:02d}\N{EN DASH}{end // 60:02d}.{end % 60:02d} WIB"
        lines.append(f"🌙 Tidur otomatis • {'ON' if schedule['auto'] else 'OFF'} • {hours}")
    if phase == "sleeping" and active:
        lines.append("Semua Auto dijeda sampai karakter bangun di game.")
    window = read_window(maintenance_file)
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


def format_needs_status(
    settings: Settings,
    *,
    worker_proc: Any,
    is_running: Any = running,
    current_time: Any = now,
) -> str:
    """Render the Status Kebutuhan report."""
    directory = settings.runtime_dir
    info = inspect_runtime_status(directory, worker_proc, is_running=is_running)
    state, observed, active, starting = info.state, info.observed, info.active, info.starting
    flags = auto_flags(directory)

    active_label = (
        "🟢 Worker aktif (Ojol & Kebutuhan)"
        if flags.get("ojol")
        else "🟢 Worker aktif (Auto Kebutuhan)"
    )
    name = _account_display_name(directory, settings)
    lines = [f"🍲 Status Kebutuhan · {name}", "", _worker_badge(info, active_label=active_label)]

    wallet = state.get("wallet")
    if wallet is not None:
        lines.append(f"💰 Saldo • {koin(wallet)}")
    if state.get("village") or state.get("home_plot"):
        lines.append(f"🏠 Rumah • {state.get('home_plot') or '?'} • {state.get('village') or '?'}")

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
        thresh = settings.threshold_for(key)
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
        kondisi_lines.extend(
            [
                f"• Kebersihan badan • {bau_str}",
                f"• Buang air • {kebelet_str}",
                f"• Potongan upah ojol • {potong}",
            ]
        )
    if bersih:
        kondisi_lines.extend(
            [
                f"• Kuota mandi hari ini • {bersih.get('mandi', 0)}/{bersih.get('mandiMaks', 2)}",
                f"• Kuota sikat gigi hari ini • {bersih.get('sikat', 0)}/{bersih.get('sikatMaks', 3)}",
            ]
        )
    if kondisi_lines:
        lines.extend(["", "🚿 Kondisi Karakter:", *kondisi_lines])

    lines.extend(["", "🌱 Aktivitas Mandiri Lainnya:"])
    lines.append(f"• Kebun & kolam • Auto {'ON' if flags.get('kebun') else 'OFF'}")
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

    if observed:
        age = max(0, int((current_time() - observed).total_seconds()))
        stale = " · data lama, worker tidak aktif" if not active else ""
        lines.extend(
            [
                "",
                f"🕒 Update terakhir: {observed.astimezone(WIB):%d-%m-%Y %H:%M:%S} WIB "
                f"({format_age_text(age)} lalu){stale}",
            ]
        )
    else:
        lines.extend(["", "🕒 Update terakhir: belum ada data"])

    if state.get("phase") == "sleeping" and active:
        lines.append("🌙 Semua Auto dijeda sampai karakter bangun di game.")
    if not active and not starting:
        lines.append("\n💡 Tekan Jalankan Kebutuhan untuk memulai auto kebutuhan.")
    return "\n".join(lines)


def format_auto_needs_summary(settings: Settings) -> str:
    """Render the Auto Kebutuhan configuration summary."""
    directory = settings.runtime_dir
    flags = auto_flags(directory)
    name = _account_display_name(directory, settings)
    lines = [
        f"⚙️ Auto Kebutuhan · {name}",
        "",
        "Pengaturan fitur otomatis kebutuhan karakter:",
    ]
    for key in NEEDS:
        label = AUTO_LABELS.get(key, key.capitalize())
        lines.append(
            f"• {label} • {'ON' if flags.get(key) else 'OFF'} (target {settings.threshold_for(key)}%)"
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


def build_account_summary(
    settings: Settings,
    *,
    worker_proc: Any = None,
    is_running: Any = running,
    current_time: Any = now,
) -> dict[str, Any]:
    """Build the structured status summary dictionary used by web dashboard."""
    directory = settings.runtime_dir
    info = inspect_runtime_status(directory, worker_proc, is_running=is_running)
    data, state, observed, active = info.data, info.state, info.observed, info.active
    has_cookie, cookie_valid, _ = _read_cookie_meta(directory)

    phase = state.get("phase")
    rem = state.get("remaining_seconds")
    if phase == "delivering" and type(rem) is int and rem > 0:
        arrive_at = state.get("arrive_at")
        if arrive_at:
            try:
                target_time = datetime.fromisoformat(str(arrive_at).replace("Z", "+00:00"))
                rem = max(0, int((target_time - current_time()).total_seconds()))
            except ValueError:
                if observed:
                    rem = max(0, rem - int((current_time() - observed).total_seconds()))
        elif observed:
            rem = max(0, rem - int((current_time() - observed).total_seconds()))

    if not has_cookie:
        status_text, icon = "Belum hubungkan cookie", "⚪"
    elif not cookie_valid:
        status_text, icon = "Sesi kedaluwarsa", "⚠️"
    elif active:
        if phase == "delivering":
            time_str = f" ({rem // 60}:{rem % 60:02d})" if rem is not None else ""
            status_text = f"Mengantar order{time_str}"
        elif phase == "searching":
            status_text = "Mencari order"
        elif phase == "sleeping":
            status_text = "Tidur di game"
        elif phase == "idle":
            flags = auto_flags(directory)
            if not flags.get("ojol") and any(flags.get(k) for k in NEEDS):
                status_text = "Memantau Kebutuhan"
            elif (
                flags.get("ojol") is True
                and state.get("ojol_min_fuel") is not None
                and (
                    state.get("ojol_fuel_blocked") or state.get("fuel", 0) < state["ojol_min_fuel"]
                )
            ):
                status_text = "Menunggu isi SPBU"
            else:
                status_text = "Standby"
        else:
            status_text = "Aktif"
        icon = "💤" if phase == "sleeping" else "🟢"
    else:
        status_text, icon = "Berhenti", "⚪"

    wallet = state.get("wallet")
    trips = state.get("today_count")
    if trips is None:
        trips = data.get("completed", 0)

    online_data, online_updated = status_record(directory / "online-status.json")
    is_online = False
    if (
        online_updated
        and (time.time() - (online_updated / 1e9)) <= 120
        and online_data.get("online")
    ):
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
        "fuel": state.get("fuel"),
        "condition": state.get("condition"),
        "data": state.get("data"),
        "shift_done": bool(state.get("ojol_shift_done")),
        "hours_left": state.get("ojol_hours_left"),
        "online": is_online or active,
        "online_updated": (
            datetime.fromtimestamp(online_updated / 1e9, tz=UTC).isoformat()
            if online_updated
            else None
        ),
    }


def format_profit_report(
    settings: Settings,
    day: Any = None,
    wallet: dict[str, Any] | None = None,
    issue: str | None = None,
) -> str:
    """Format the daily profit report combining game wallet evidence and worker journal."""
    journal = Journal(settings.runtime_dir)
    try:
        report = journal.financial_report(day)
    finally:
        journal.close()
    total = report["total"]

    def money(value):
        return str(value).replace(".", ",")

    names = {"fuel": "⛽ Bensin", "condition": "🔧 Bengkel", "data": "📶 Kuota"}
    lines = [f"📒 Laba Bersih · {report['tanggal']} (WIB)", "", "🎮 Menurut riwayat game"]

    complete = False
    cost = 0
    expenses: dict[str, int] = {}
    expense_issue = None
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
            label = "Belanja produk Ojol" if complete else "Belanja produk Ojol ditemukan (parsial)"
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
            "\N{INFORMATION SOURCE}️ Semua pembelian bensin, bengkel, dan kuota dihitung sebagai biaya Ojol."
        )
    if not wallet or not complete:
        lines.append("\N{INFORMATION SOURCE}️ Laba belum dihitung karena data game belum lengkap.")

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
            f"{clock} {'+' if row['kind'] == 'income' else '\N{MINUS SIGN}'}{koin(row['amount'])} · {label}"
        )
    return "\n".join(lines)
