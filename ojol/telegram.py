"""Private-chat Bot API integration; secrets never enter journal or error text."""

import asyncio
import json
import logging
import re
import time
from uuid import uuid4

import httpx

BUTTON_COMMANDS = {
    "Import Cookie": "import_cookie",
    "Jalankan Ojol": "run",
    "Hentikan Ojol": "stop",
    "Status": "status",
    "Laba Bersih": "profit",
    "Notifikasi ON": "notifications_on",
    "Notifikasi OFF": "notifications_off",
}
KEYBOARD = {
    "keyboard": [
        [{"text": "Akun Saya"}, {"text": "Tambah Akun"}],
        [{"text": "Bantuan"}, {"text": "Management"}],
        [{"text": "Import Cookie"}, {"text": "Jalankan Ojol"}],
        [{"text": "Hentikan Ojol"}, {"text": "Status"}],
        [{"text": "Laba Bersih"}, {"text": "Batal"}],
        [{"text": "Notifikasi ON"}, {"text": "Notifikasi OFF"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
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
    pass


def redact(text, settings):
    value = str(text)
    secret = settings.telegram_bot_token.get_secret_value()
    if secret:
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"https?://api\.telegram\.org/bot[^\s/]+", "[TELEGRAM_API]", value)
    value = re.sub(r"/login/[A-Za-z0-9_-]+", "/login/[REDACTED]", value)
    value = re.sub(r"/access/[A-Za-z0-9_-]+", "/access/[REDACTED]", value)
    value = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", value)
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
        try:
            response = await self.client.post(
                f"https://api.telegram.org/bot{key}/{method}",
                json=data,
                timeout=25 if method == "getUpdates" else 5,
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise TelegramError(
                "Telegram tidak dapat dihubungi; notifikasi disimpan lokal"
            ) from None
        if response.status_code != 200 or not payload.get("ok"):
            description = redact(
                payload.get("description", "Telegram API menolak request"), self.settings
            )
            raise TelegramError(f"Telegram API {response.status_code}: {description}")
        return payload["result"]

    async def send(self, message, reply_markup=None):
        return await self.call(
            "sendMessage",
            chat_id=self.settings.telegram_chat_id,
            text=(
                (f"[{self.settings.account_name}]\n" if self.settings.account_name else "")
                + message
            )[:4000],
            link_preview_options={"is_disabled": True},
            protect_content=True,
            reply_markup=reply_markup or KEYBOARD,
        )


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
            if data.get("context", {}).get("routine_event") and not notifications_enabled(settings):
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
                await api.send(data["text"], data.get("reply_markup"))
            except TelegramError:
                data["attempts"] += 1
                data["next_attempt"] = time.time() + min(300, 2 ** min(data["attempts"], 8))
                claimed.write_text(json.dumps(data, ensure_ascii=False))
                claimed.rename(path)
                break
            else:
                claimed.rename(path.with_suffix(".sent"))
                count += 1
    return count


def queue_error(settings, error, stage, context=None):
    settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    (settings.runtime_dir / "worker-restart.json").unlink(missing_ok=True)
    (settings.runtime_dir / "STOP").touch(mode=0o600)
    details = {
        "stage": stage,
        "category": type(error).__name__,
        "message": redact(error, settings),
        **(context or {}),
    }
    message = "🛑 Ojol STOP karena error\n" + "\n".join(
        f"{key}: {value}" for key, value in details.items() if value is not None
    )
    path = queue_notice(settings, message, details)
    latest = settings.runtime_dir / "last-error.json"
    latest.write_text(json.dumps({"notice_id": path.stem, **details}, ensure_ascii=False, indent=2))
    latest.chmod(0o600)
    return path
