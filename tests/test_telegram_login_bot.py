import asyncio
from unittest.mock import AsyncMock

from ojol.telegram_login_bot import TelegramLoginBot


def test_telegram_login_bot_handles_message(settings):
    bot_settings = settings.model_copy(
        update={
            "telegram_bot_token": "fake-test-token",
            "telegram_chat_id": 999,
            "login_public_url": "http://localhost:6080",
        }
    )
    bot = TelegramLoginBot(bot_settings)

    mock_client = AsyncMock()
    message = {
        "chat": {"id": 12345},
        "from": {"id": 12345, "first_name": "Anto", "username": "anto_dev"},
        "text": "/start",
    }

    asyncio.run(bot.handle_message(mock_client, message))

    assert mock_client.call.called
    call_args = mock_client.call.call_args
    assert call_args.args[0] == "sendMessage"
    kwargs = call_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert "Kode Login:" in kwargs["text"]
    assert "http://localhost:6080/login?code=" in kwargs["text"]
    assert len(kwargs["reply_markup"]["inline_keyboard"][0]) == 1
