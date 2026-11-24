"""Write in-app events and error records for the web dashboard."""

import json
import logging
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from uuid import uuid4

from .auto_settings import AUTO_LABELS
from .finance import WIB
from .formatting import format_koin as koin
from .models import now
from .storage import write_private


def redact(text):
    value = str(text)
    value = re.sub(r"https?://api\.telegram\.org/bot[^\s/]+", "[TELEGRAM_API]", value)
    value = re.sub(r"/login/[A-Za-z0-9_-]+", "/login/[REDACTED]", value)
    value = re.sub(r"/access/[A-Za-z0-9_-]+", "/access/[REDACTED]", value)
    value = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", value)
    value = re.sub(
        r"(?im)\b(cookie|set-cookie|authorization)\s*[:=][^\r\n]+",
        r"\1: [REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)([\"']?(?:password|token|session[-_]token|__Secure-next-auth\.session-token)"
        r"[\"']?\s*[:=]\s*)(?:[\"'][^\"']*[\"']|[^\s,;]+)",
        r"\1[REDACTED]",
        value,
    )
    return value[:1000]


def event_text(event, data):
    if event == "spbu_perlu_isi":
        return (
            f"⛽ Tangki {data['vehicle']} Ojol tinggal {data['fuel']}%. "
            "Bawa kendaraan yang dipakai Ojol ke SPBU dan buka pompa. "
            "Auto Ojol memeriksa tangki lagi sebelum mengambil order."
        )
    if event == "ojol_gagal":
        reason = data.get("reason", "Terjadi kendala pada Ojol")
        return f"⚠️ Auto Ojol dinonaktifkan: {reason}.\n\nFitur auto kebutuhan tetap berjalan normal. Tekan Jalankan Ojol jika ingin mencoba lagi."
    if event == "kebun_aksi_selesai":
        action = data.get("action")
        garden = data.get("garden", "Kebun/kolam")
        if action == "panen":
            return f"🧺 {garden}: Panen berhasil! Hasil panen masuk ke tas."
        if action == "rawat":
            return f"💧 {garden}: Berhasil dirawat agar hasil panen lebih banyak."
        if action == "tanam":
            return f"🌱 {garden}: Bibit berhasil ditanam (biaya {koin(data.get('cost', '0'))})."
    if event == "belajar_dimulai":
        return f"📚 {'Perpus' if data['mode'] == 'perpus' else 'Kuliah'} · {data['track']} dimulai. Biaya {data['cost']} koin. Kuis dikerjakan otomatis."
    if event == "kuis_belajar_selesai":
        return f"📖 Kuis {data['track']}: {data['benar']}/{data['total']} benar. Bonus belajar {data['bonus']}."
    if event == "mulai" and data.get("live"):
        return "▶️ Bot sedang menyiapkan aktivitas sesuai pengaturan Auto akun ini."
    if event == "berhenti":
        reason = data.get("reason") or ""
        if "Batas jumlah trip" in reason:
            return "⏹ Batas trip sesi ini sudah tercapai. Tekan Jalankan Ojol jika ingin lanjut."
        if "Batas durasi" in reason:
            return "⏹ Waktu kerja sesi ini sudah habis. Tekan Jalankan Ojol jika ingin lanjut."
        return "⏹ Bot sudah berhenti. Tekan Jalankan Ojol jika ingin melanjutkan."
    if event == "aksi_job_terverifikasi" and data.get("action") != "complete":
        if data.get("phase") == "delivering":
            return "🛵 Order diterima. Bot sedang mengantar dan akan mengambil ongkos saat tiba."
        if data.get("phase") == "searching":
            return "🔎 Bot sedang mencari order."
    if event == "pembelian_terverifikasi":
        resource = data["resource"]
        label = {"fuel": "Bensin", "condition": "Kondisi mesin", "data": "Kuota HP"}.get(
            resource, AUTO_LABELS.get(resource, "Kebutuhan")
        )
        activity = (
            f"Aksi • {data['product']}\nTempat • {data['shop']}\nBiaya • {koin(data['cost'])}"
        )
        auto_status = (
            f"Auto {label} • {'ON' if data['auto_enabled'] else 'OFF'}\n"
            if type(data.get("auto_enabled")) is bool
            else ""
        )
        return (
            f"✅ {label} berhasil diperbarui\n\n"
            f"{label} • {data['before']}% → {data['after']}%\n"
            f"{auto_status}{activity}\nSaldo tersisa • {koin(data['wallet'])}"
        )
    if event == "pendapatan_ojol_tercatat":
        return f"🏁 Trip selesai. Ongkos {koin(data['amount'])} sudah masuk."
    if event == "trip_selesai_otomatis_teramati":
        if data.get("income") is None:
            return "🏁 Trip selesai."
        return f"🏁 Trip selesai otomatis. Ongkos {koin(data['income'])} sudah masuk."
    if event == "maintenance":
        target = data.get("target")
        if data.get("sampai") == "manual":
            if target == "ojol":
                return "🛠 Aktivitas Auto Ojol dijeda secara manual untuk maintenance. Fitur auto kebutuhan lain tetap berjalan normal."
            return "🛠 Aktivitas game dijeda secara manual untuk maintenance (ON)."
        end = datetime.fromisoformat(data["sampai"]).astimezone(WIB)
        if target == "ojol":
            return f"🛠 Aktivitas Auto Ojol dijeda untuk maintenance sampai {end:%d-%m-%Y pukul %H:%M} WIB. Fitur auto kebutuhan lain tetap berjalan normal."
        return f"🛠 Aktivitas game dijeda untuk maintenance sampai {end:%d-%m-%Y pukul %H:%M} WIB."
    if event == "maintenance_selesai":
        return "✅ Maintenance selesai. Bot memeriksa status game sebelum melanjutkan aktivitas."
    if event == "tidur_mulai":
        return (
            "😴 Karakter sedang tidur\n\nSemua Auto dijeda. Bot memeriksa status berkala "
            "dan melanjutkan otomatis setelah karakter bangun di game."
        )
    if event == "bangun":
        return "☀️ Karakter sudah bangun. Bot melanjutkan aktivitas sesuai pengaturan Auto."
    return None


def login_required(details):
    return (
        details.get("http_category") == "auth"
        or details["stage"] == "http.auth"
        or "import cookie" in (details.get("tindakan") or "").casefold()
    )


def _error_guidance(details):
    stage = details["stage"]
    diagnostic = (details.get("message") or "").casefold()
    action = details.get("tindakan")
    if login_required(details):
        return (
            "🔑 Login ulang diperlukan\n\n"
            "Sesi game sudah tidak bisa digunakan. Buka KampungSebelah dan login ulang.\n\n"
            "Setelah masuk, tekan Import Cookie untuk menghubungkan cookie baru, "
            "lalu Jalankan Ojol."
        )
    elif details.get("http_category") == "reconciliation_failed":
        return (
            "❌ Auto rekonsiliasi gagal setelah 6 percobaan. Bot dihentikan.\n\n"
            "Game mungkin sedang terbuka di perangkat lain. Keluar dari game, lalu tekan "
            "tombol Lanjutkan (atau Jalankan Ojol) untuk melanjutkan."
        )
    elif (
        details.get("http_category") == "uncertain"
        or (
            ("hasil belum pasti" in diagnostic or "belum terverifikasi" in diagnostic)
            and (stage.startswith(("purchase.", "job.", "worker.auto_start", "worker.reconcile")))
        )
        or stage.startswith("purchase.verify.")
        or stage.startswith("job.")
        and ".verify" in stage
    ):
        reason = "Hasil aksi terakhir belum bisa dipastikan."
        action = (
            "Tekan Jalankan Ojol untuk menjalankan pemeriksaan hasil transaksi secara otomatis."
        )
    elif "akun belum menjadi mitra ojol" in diagnostic:
        reason = "Akun game terhubung, tetapi Ojol Desa belum aktif untuk akun ini."
        action = (
            "Di game, buka Kerja → Ojol desa dan pilih Daftar jadi mitra. "
            "Setelah terdaftar, tekan Jalankan Ojol lagi di dashboard."
        )
    elif "sedang tidur" in diagnostic:
        reason = "Karakter sedang tidur."
        action = "Bangunkan karakter di game, lalu tekan Jalankan Ojol."
    elif "automation sudah berjalan" in diagnostic:
        reason = "Akun masih digunakan worker yang sedang berjalan."
        action = (
            "Tekan Status untuk memeriksa akun. Untuk inspeksi atau rekonsiliasi manual, "
            "tekan Hentikan Ojol dan tunggu worker berhenti sebelum mencoba lagi."
        )
    elif "tidak ada pembelian" in diagnostic:
        reason = "Tidak ada barang isi ulang yang memenuhi syarat."
        action = (
            "Cek stok toko dan kapasitas resource di game, lalu saldo dan anggaran lewat Status. "
            "Setelah tersedia, tekan Jalankan Ojol."
        )
    elif "saldo minimum" in diagnostic:
        reason = "Pembelian tidak bisa dilanjutkan dengan saldo atau anggaran saat ini."
        action = "Cek saldo lewat Status sebelum melanjutkan."
    elif stage.startswith("control.command.profit") and details.get("category") in {
        "ValueError",
        "OverflowError",
    }:
        return "❌ Tanggal tidak valid\n\nFormat: YYYY-MM-DD atau DD-MM-YYYY\nContoh: 2026-11-10"
    elif stage.startswith("session.import"):
        return "⚠️ Cookie belum berhasil diverifikasi. Tekan Import Cookie untuk mencoba lagi."
    elif stage.startswith(("tunnel.", "control.startup.tunnel")):
        reason = "Koneksi untuk membuka halaman Import Cookie sedang bermasalah."
        action = "Hubungi admin untuk memeriksa koneksi server."
    elif details.get("http_category") == "transport" or details.get("category") in {
        "TimeoutError",
        "ConnectError",
        "ReadTimeout",
        "ConnectTimeout",
    }:
        reason = "Game belum bisa dihubungi atau responsnya terlalu lama."
        action = action or "Coba lagi beberapa saat lagi. Cek Status sebelum menekan Jalankan Ojol."
    elif details.get("http_category") == "schema":
        reason = "Respons game belum bisa dibaca dengan aman."
        action = "Hubungi admin untuk memeriksa perubahan API game sebelum menjalankan ulang."
    elif details.get("http_category") in {"rejected", "blocked"}:
        reason = "Game atau pemeriksaan keamanan bot belum mengizinkan aktivitas ini."
        action = "Cek kondisi akun, resource, dan toko di game. Tekan Status sebelum mencoba lagi."
    elif stage.endswith(("cleanup_scan", "visit_scan")):
        return "⚠️ Pencarian rumah belum bisa diperiksa. Coba lagi beberapa saat lagi."
    elif stage == "worker.auto_start":
        reason = "Bot belum bisa memulai akun ini secara otomatis."
    elif stage.startswith(("job.", "purchase.", "shop.preview.")):
        reason = "Bot menemui kendala saat menjalankan aksi di game."
    else:
        reason = "Bot menemui kendala saat menjalankan akun ini."
    return f"⚠️ {reason}\n\n{action or 'Tekan Status untuk memeriksa akun. Hubungi admin jika kendala berulang.'}"


def error_text(details):
    stage = details["stage"]
    activity = next(
        (
            label
            for prefix, label in (
                ("shop.preview.", "memeriksa toko isi ulang"),
                ("purchase.", "membeli atau memverifikasi isi ulang"),
                ("study.", "belajar atau mengerjakan kuis"),
                ("job.", "menjalankan atau memverifikasi order"),
                ("session.import", "menghubungkan cookie game"),
                ("worker.reconcile", "memeriksa hasil transaksi sebelumnya"),
                ("worker.", "menjalankan worker akun"),
                ("tunnel.", "menghubungkan halaman Import Cookie"),
                ("control.command.cleanup_scan", "mencari rumah kotor"),
                ("control.command.visit_scan", "mencari rumah untuk mampir"),
            )
            if stage.startswith(prefix)
        ),
        "memproses aktivitas akun",
    )
    resource = stage.rsplit(".", 1)[-1]
    label = {"fuel": "bensin", "condition": "kondisi mesin", "data": "kuota HP"}.get(
        resource, AUTO_LABELS.get(resource)
    )
    if label:
        activity += f" ({label})"
    reference = details.get("error_id")
    diagnostic = details.get("message") or details.get("category") or "Detail belum tersedia"
    return (
        (f"ID error: {reference}\n" if reference else "")
        + _error_guidance(details)
        + f"\n\nSaat: {activity}.\nDetail: {diagnostic[:300]}"
        + ("…" if len(diagnostic) > 300 else "")
        + "\nSampaikan ID error ke admin jika perlu bantuan."
    )


def queue_notice(settings, message, context=None):
    directory = settings.runtime_dir / "notifications"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    priority = "0-error-" if (context or {}).get("stage") else ""
    path = directory / f"{priority}{time.time_ns()}-{uuid4().hex}.json"
    write_private(
        path,
        {
            "text": message,
            "context": context or {},
            "created_at": now().isoformat(),
            "read": False,
        },
    )
    return path


def record_error(settings, error, stage, context=None):
    settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    details = {
        "stage": stage,
        "category": type(error).__name__,
        "http_category": getattr(error, "category", None),
        "message": redact(error),
        "pid": os.getpid(),
        **(context or {}),
        "error_id": "OJL-" + uuid4().hex[:12].upper(),
        "time": now().isoformat(),
    }
    if stage == "worker.reconcile":
        history = settings.runtime_dir / "history.sqlite3"
        if history.is_file():
            try:
                with closing(
                    sqlite3.connect(history.resolve().as_uri() + "?mode=ro", uri=True)
                ) as db:
                    details["action_ids"] = [
                        row[0]
                        for row in db.execute(
                            "SELECT id FROM actions WHERE status IN ('pending','uncertain') ORDER BY id"
                        )
                    ]
            except sqlite3.Error:
                logging.exception("Gagal membaca referensi aksi untuk catatan error")
    directory = settings.runtime_dir / "errors"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / f"{details['error_id']}.json", details)
    write_private(settings.runtime_dir / "last-error.json", details)
    print(json.dumps({"event": "error", **details}, ensure_ascii=False, default=str), flush=True)
    return details


def queue_error(settings, error, stage, context=None, *, stop_worker=True):
    if stop_worker:
        settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (settings.runtime_dir / "STOP").touch(mode=0o600)
    details = record_error(settings, error, stage, {**(context or {}), "fatal": stop_worker})
    path = queue_notice(settings, error_text(details), details)
    write_private(settings.runtime_dir / "last-error.json", {"notice_id": path.stem, **details})
    return path
