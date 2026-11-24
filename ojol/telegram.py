"""Private-chat Bot API integration; secrets never enter journal or error text."""

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from uuid import uuid4

import httpx

from .auto_settings import AUTO_LABELS
from .finance import WIB
from .healing import write_private
from .identity import cached_profile
from .models import now

BUTTON_COMMANDS = {
    "Dashboard": "dashboard",
    "Import Cookie": "import_cookie",
    "Jalankan Ojol": "choose_mode",
    "Hentikan Ojol": "stop_ojol",
    "Jalankan Kebutuhan": "run_kebutuhan",
    "Hentikan Kebutuhan": "stop_kebutuhan",
    "Lanjutkan": "resume",
    "Status": "status",
    "Status Ojol": "status",
    "Status Kebutuhan": "status_kebutuhan",
    "Auto": "auto",
    "Auto Ojol": "auto_ojol",
    "Auto Kebutuhan": "auto_kebutuhan",
    "Laba Bersih": "profit",
    "Cari Rumah Kotor": "cleanup_scan",
    "Cari Rumah Mampir": "visit_scan",
    "Notifikasi ON": "notifications_on",
    "Notifikasi OFF": "notifications_off",
}


def _kb(rows):
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}


def keyboard_main():
    """Menu utama: navigasi dan aksi umum."""
    return _kb(
        [
            [{"text": "Dashboard"}, {"text": "Status"}],
            [{"text": "Status Ojol"}, {"text": "Status Kebutuhan"}],
            [{"text": "Akun Saya"}, {"text": "Auto Kebutuhan"}],
            [{"text": "Jalankan Ojol"}, {"text": "Hentikan Ojol"}],
            [{"text": "Jalankan Kebutuhan"}, {"text": "Hentikan Kebutuhan"}],
            [{"text": "Import Cookie"}],
            [{"text": "Cari Rumah Kotor"}, {"text": "Cari Rumah Mampir"}],
            [{"text": "Pengaturan"}, {"text": "Bantuan"}],
        ]
    )


def keyboard_accounts():
    """Menu Akun Saya: kelola akun."""
    return _kb(
        [
            [{"text": "Dashboard"}, {"text": "Tambah Akun"}],
            [{"text": "Menu Utama"}, {"text": "Bantuan"}],
        ]
    )


def keyboard_status():
    """Setelah lihat status: opsi lanjutan."""
    return _kb(
        [
            [{"text": "Dashboard"}, {"text": "Laba Bersih"}],
            [{"text": "Status Ojol"}, {"text": "Status Kebutuhan"}],
            [{"text": "Jalankan Ojol"}, {"text": "Hentikan Ojol"}],
            [{"text": "Jalankan Kebutuhan"}, {"text": "Hentikan Kebutuhan"}],
            [{"text": "Auto Kebutuhan"}, {"text": "Menu Utama"}],
        ]
    )


def keyboard_settings():
    """Menu pengaturan terpusat."""
    return _kb(
        [
            [{"text": "Notifikasi ON"}, {"text": "Notifikasi OFF"}],
            [{"text": "Management"}],
            [{"text": "Menu Utama"}],
        ]
    )


# Legacy alias – used as default reply_markup when no context-specific
# keyboard is passed.  Points to the main keyboard so callers that relied
# on the old constant keep working.
KEYBOARD = keyboard_main()
MANDATORY_EVENTS = {
    "maintenance",
    "maintenance_selesai",
    "tidur_mulai",
    "bangun",
    "ojol_gagal",
}


def notifications_enabled(settings):
    path = settings.runtime_dir / "event-notifications.json"
    return path.exists() and json.loads(path.read_text()).get("enabled") is True


def set_notifications(settings, enabled):
    path = settings.runtime_dir / "event-notifications.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"enabled": bool(enabled)}))
    temporary.chmod(0o600)
    temporary.replace(path)


class TelegramError(RuntimeError):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def redact(text, settings):
    value = str(text)
    secret = settings.telegram_bot_token.get_secret_value()
    if secret:
        value = value.replace(secret, "[REDACTED]")
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


class TelegramClient:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        self.owns_client = client is None
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    async def __aenter__(self):
        if not self.client:
            self.client = httpx.AsyncClient(timeout=30, trust_env=False)
        return self

    async def __aexit__(self, *args):
        if self.owns_client and self.client:
            await self.client.aclose()

    async def call(self, method, **data):
        if method not in {
            "sendMessage",
            "getUpdates",
            "getMe",
            "getChat",
            "getWebhookInfo",
            "answerCallbackQuery",
        }:
            raise TelegramError("Metode Telegram tidak diizinkan")
        key = self.settings.telegram_bot_token.get_secret_value()
        if not key or not self.settings.telegram_chat_id:
            raise TelegramError("Token/Chat ID Telegram belum lengkap")
        response = None
        try:
            response = await self.client.post(
                f"https://api.telegram.org/bot{key}/{method}",
                json=data,
                timeout=25 if method == "getUpdates" else 5,
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Respons Telegram bukan objek JSON")
        except (httpx.HTTPError, ValueError) as exc:
            status = f", HTTP {response.status_code}" if response is not None else ""
            raise TelegramError(
                "Telegram tidak dapat dihubungi; notifikasi disimpan lokal "
                f"({method}: {type(exc).__name__}{status})",
                retryable=(
                    response is None
                    or response.status_code < 400
                    or response.status_code == 429
                    or response.status_code >= 500
                ),
            ) from None
        if response.status_code != 200 or not payload.get("ok"):
            description = redact(
                payload.get("description", "Telegram API menolak request"), self.settings
            )
            raise TelegramError(
                f"Telegram API {response.status_code} ({method}): {description}",
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        return payload["result"]

    async def send(self, message, reply_markup=None):
        profile = cached_profile(self.settings.runtime_dir)
        account_name = profile["nickname"] if profile else self.settings.account_name
        return await self.call(
            "sendMessage",
            chat_id=self.settings.telegram_chat_id,
            text=((f"👤 {account_name}\n\n" if account_name else "") + message)[:4000],
            link_preview_options={"is_disabled": True},
            protect_content=True,
            reply_markup=reply_markup or KEYBOARD,
        )


async def acknowledge_callback(api, callback_id):
    try:
        await api.call("answerCallbackQuery", callback_query_id=callback_id)
    except TelegramError as error:
        # An expired callback cannot be acknowledged again. Let the poller consume its update.
        if str(error).lower().startswith("telegram api 400: bad request: query is too old"):
            return False
        raise
    return True


def authorized_message(update, settings):
    callback = update.get("callback_query")
    message = (
        {**callback.get("message", {}), "from": callback.get("from", {})}
        if callback
        else update.get("message", {})
    )
    return (
        message.get("chat", {}).get("type") == "private"
        and message.get("chat", {}).get("id") == settings.telegram_chat_id
        and message.get("from", {}).get("id") == settings.telegram_chat_id
    )


def koin(value):
    return f"{str(value).replace('.', ',')} koin"


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
            "Setelah terdaftar, tekan Jalankan Ojol lagi di Telegram."
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
    elif stage.startswith("telegram."):
        if details.get("fatal") is False:
            return (
                "⚠️ Koneksi Telegram sempat terganggu. Bot mencoba terhubung kembali otomatis; "
                "worker akun tetap berjalan."
            )
        return "⚠️ Bot sempat kehilangan koneksi ke Telegram. Cek Status akun sebelum melanjutkan."
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
                ("telegram.", "menghubungkan Telegram"),
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


def queued_text(data):
    context = data.get("context") or {}
    if context.get("stage"):
        return error_text(context)
    message = data["text"]
    event = context.get("event")
    if context.get("routine_event") and event not in MANDATORY_EVENTS | {
        "mulai",
        "berhenti",
        "pembelian_terverifikasi",
        "pendapatan_ojol_tercatat",
        "trip_selesai_otomatis_teramati",
        "maintenance",
        "aksi_job_terverifikasi",
    }:
        return None
    if context.get("routine_event") and message.startswith(f"📣 {event} · "):
        try:
            return event_text(event, json.loads(message.split("\n", 2)[2]))
        except (IndexError, KeyError, TypeError, ValueError):
            return None
    return message


def queue_notice(settings, message, context=None, reply_markup=None):
    directory = settings.runtime_dir / "notifications"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    priority = "0-error-" if (context or {}).get("stage") else ""
    path = directory / f"{priority}{time.time_ns()}-{uuid4().hex}.json"
    path.write_text(
        json.dumps(
            {
                "text": message,
                "context": context or {},
                "reply_markup": reply_markup,
                "attempts": 0,
                "next_attempt": 0,
                "created_at": now().isoformat(),
                "read": False,
            },
            ensure_ascii=False,
        )
    )
    path.chmod(0o600)
    return path


async def flush_notices(settings, client=None):
    if not settings.telegram_bot_token.get_secret_value() or not settings.telegram_chat_id:
        return 0
    count = 0
    directory = settings.runtime_dir / "notifications"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = directory / ".pruned"
    if not marker.exists() or time.time() - marker.stat().st_mtime >= 3600:
        # Delivery copies expire after a week; authoritative events and finances stay in SQLite.
        for pattern in ("*.sent", "*.muted"):
            for archived in directory.glob(pattern):
                try:
                    if time.time() - archived.stat().st_mtime > 7 * 86400:
                        archived.unlink()
                except FileNotFoundError:
                    pass
        marker.touch()
    # Recover interrupted deliveries; Telegram has no idempotency key, so retries may duplicate a notice.
    for claimed in (settings.runtime_dir / "notifications").glob("*.sending"):
        try:
            if time.time() - claimed.stat().st_mtime > 60:
                claimed.rename(claimed.with_suffix(".json"))
        except FileNotFoundError:
            pass
    async with TelegramClient(settings, client) as api:
        for path in sorted((settings.runtime_dir / "notifications").glob("*.json"))[:5]:
            try:
                data = json.loads(path.read_text())
            except FileNotFoundError:
                continue
            if data.get("next_attempt", 0) > time.time():
                continue
            message = queued_text(data)
            context = data.get("context", {})
            if message is None or (
                context.get("routine_event")
                and not context.get("stage")
                and context.get("event") not in MANDATORY_EVENTS
                and not notifications_enabled(settings)
            ):
                path.rename(path.with_suffix(".muted"))
                continue
            claimed = path.with_suffix(".sending")
            try:
                path.rename(claimed)
            except FileNotFoundError:
                continue
            try:
                if count:
                    await asyncio.sleep(1.05)
                await api.send(
                    redact(message, settings) if message != data["text"] else message,
                    data.get("reply_markup"),
                )
            except TelegramError:
                data["attempts"] += 1
                if data.get("context", {}).get("stage") == "telegram.poll":
                    claimed.rename(path.with_suffix(".muted"))
                    break
                data["next_attempt"] = time.time() + min(300, 2 ** min(data["attempts"], 8))
                claimed.write_text(json.dumps(data, ensure_ascii=False))
                claimed.rename(path)
                break
            else:
                claimed.rename(path.with_suffix(".sent"))
                count += 1
    return count


def record_error(settings, error, stage, context=None):
    settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    details = {
        "stage": stage,
        "category": type(error).__name__,
        "http_category": getattr(error, "category", None),
        "message": redact(error, settings),
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
    markup = None
    if login_required(details):
        buttons = [
            [{"text": "Login ulang ke game", "url": "https://www.kampungsebelah.com/kampung"}]
        ]
        account_id = details.get("account_id")
        if isinstance(account_id, str) and re.fullmatch(r"[a-f0-9]{32}", account_id):
            buttons.append(
                [{"text": "Import Cookie", "callback_data": f"acct:{account_id}:import_cookie"}]
            )
        markup = {"inline_keyboard": buttons}
    path = queue_notice(settings, error_text(details), details, reply_markup=markup)
    write_private(settings.runtime_dir / "last-error.json", {"notice_id": path.stem, **details})
    return path
