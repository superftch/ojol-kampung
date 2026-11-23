"""Dedicated, lightweight Telegram Bot for Web Dashboard Login.

This service only handles Telegram login code generation (/start, /login, /web, /code).
All automation, workers, and gameplay control are managed in the Web Dashboard.
"""

import asyncio
import logging
import signal
import sys

from .accounts import Accounts
from .config import load_settings
from .models import Settings
from .telegram import TelegramClient, TelegramError

logger = logging.getLogger(__name__)


class TelegramLoginBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = Accounts(settings)
        self.offset_file = settings.runtime_dir / "telegram-login-offset"
        self.running = True
        self.bot_username = ""

    def load_offset(self) -> int:
        if self.offset_file.is_file():
            try:
                return int(self.offset_file.read_text().strip())
            except ValueError:
                pass
        return 0

    def save_offset(self, offset: int):
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.offset_file.write_text(str(offset), encoding="utf-8")

    async def run(self):
        token = self.settings.telegram_bot_token.get_secret_value()
        if not token:
            logger.error("OJOL_TELEGRAM_BOT_TOKEN belum diatur. Login bot dihentikan.")
            return

        offset = self.load_offset()
        logger.info("Memulai Telegram Login Bot...")

        async with TelegramClient(self.settings) as client:
            # 1. Verify Bot Credentials
            try:
                me = await client.call("getMe")
                self.bot_username = me.get("username") or (me.get("result") or {}).get(
                    "username", ""
                )
                logger.info("Telegram Login Bot aktif sebagai @%s", self.bot_username)
            except Exception as exc:
                logger.error("Gagal menghubungkan ke Bot Telegram: %s", exc)
                return

            # 2. Polling Loop
            while self.running:
                try:
                    payload = {"timeout": 20, "allowed_updates": ["message"]}
                    if offset:
                        payload["offset"] = offset

                    res = await client.call("getUpdates", **payload)
                    updates = res.get("result", []) if isinstance(res, dict) else []

                    for update in updates:
                        update_id = update.get("update_id", 0)
                        if update_id >= offset:
                            offset = update_id + 1
                            self.save_offset(offset)

                        message = update.get("message")
                        if not message:
                            continue

                        await self.handle_message(client, message)

                except TelegramError as te:
                    if te.retryable:
                        await asyncio.sleep(3)
                    else:
                        logger.error("Telegram API error fatal: %s", te)
                        await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.exception("Error tak terduga pada polling login bot: %s", exc)
                    await asyncio.sleep(3)

    async def handle_message(self, client: TelegramClient, message: dict):
        chat = message.get("chat", {})
        sender = message.get("from", {})
        chat_id = chat.get("id")
        sender_id = sender.get("id")

        if not chat_id or not sender_id:
            return

        first_name = sender.get("first_name", "User")
        username = sender.get("username", "")

        # Generate 6-digit login code from registry
        code = self.registry.web.issue_telegram_login_code(sender_id)

        # Prepare direct login URL
        base_url = self.settings.login_public_url.rstrip("/")
        direct_url = f"{base_url}/login?code={code}"

        reply_text = (
            f"👋 Halo, *{first_name}*!\n\n"
            f"Gunakan kode login berikut untuk masuk ke *Web Dashboard*:\n\n"
            f"🔐 Kode Login: `{code}`\n\n"
            f"⏳ _Kode berlaku selama 10 menit._\n\n"
            f"👉 [Klik di sini untuk langsung login]({direct_url})\n\n"
            f"🌐 *Web Dashboard:* {base_url}\n\n"
            f"_Seluruh kontrol otomasi Ojol (Jalankan Ojol, Kebutuhan, Laporan Laba, dsb.) "
            f"kini dikelola penuh melalui Web Dashboard._"
        )

        reply_markup = {"inline_keyboard": [[{"text": "🚀 Buka Web Dashboard", "url": direct_url}]]}

        try:
            await client.call(
                "sendMessage",
                chat_id=chat_id,
                text=reply_text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            logger.info("Login code %s dikirim ke Telegram ID %s (@%s)", code, sender_id, username)
        except Exception as exc:
            logger.error("Gagal mengirim pesan login ke %s: %s", chat_id, exc)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = load_settings()
    bot = TelegramLoginBot(settings)

    loop = asyncio.get_running_loop()

    def stop_signal():
        bot.running = False
        for task in asyncio.all_tasks(loop):
            if task is not asyncio.current_task():
                task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_signal)
        except NotImplementedError:
            pass

    try:
        await bot.run()
    except asyncio.CancelledError:
        pass
    logger.info("Telegram Login Bot berhenti.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
