import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from ojol.control import ControlService
from ojol.journal import Journal
from ojol.models import Settings
from ojol.telegram import TelegramError, flush_notices


def test_production_requires_https_telegram_and_cash_floor(settings):
    values = dict(
        env="production",
        runtime_dir=settings.runtime_dir,
        telegram_bot_token="isolated-test-secret",
        telegram_chat_id=123,
        login_public_url="https://ojol.example.test",
    )
    valid = Settings(**values)
    assert valid.max_jobs is None and valid.max_minutes is None
    for change in (
        {"telegram_bot_token": ""},
        {"telegram_chat_id": None},
        {"login_public_url": "http://localhost:6080"},
        {"min_balance": "19.99"},
    ):
        with pytest.raises(ValidationError):
            Settings(**{**values, **change})


def test_ledger_uses_wal_and_daily_index(settings):
    journal = Journal(settings.runtime_dir)
    try:
        assert journal.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert "cashflows_created" in [
            row["name"] for row in journal.db.execute("PRAGMA index_list('cashflows')")
        ]
    finally:
        journal.close()


async def test_delivered_notice_retention_never_deletes_pending(settings):
    from pydantic import SecretStr

    settings = settings.model_copy(
        update={"telegram_bot_token": SecretStr("isolated-test-secret"), "telegram_chat_id": 123}
    )
    directory = settings.runtime_dir / "notifications"
    directory.mkdir()
    for name in ("old.sent", "old.muted", "recent.sent", "pending.json"):
        path = directory / name
        path.write_text(
            json.dumps({"text": "fixture", "next_attempt": time.time() + 3600, "context": {}})
        )
        if name != "recent.sent":
            os.utime(path, (time.time() - 8 * 86400,) * 2)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: pytest.fail("No network request expected"))
    ) as client:
        assert await flush_notices(settings, client) == 0
    assert not (directory / "old.sent").exists() and not (directory / "old.muted").exists()
    assert (directory / "recent.sent").exists() and (directory / "pending.json").exists()


async def test_one_error_notice_per_telegram_outage(settings, monkeypatch):
    import ojol.control as module

    service = ControlService(settings)
    count = 0

    async def fail(*args, **kwargs):
        nonlocal count
        count += 1
        raise TelegramError("Offline fixture")

    async def wait(seconds):
        if count == 2:
            service.closing = True

    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(call=AsyncMock(side_effect=fail))
    monkeypatch.setattr(module, "TelegramClient", lambda settings: context)
    monkeypatch.setattr(module, "flush_notices", AsyncMock())
    monkeypatch.setattr(module.asyncio, "sleep", wait)
    await service.poll_telegram()
    assert len(list((settings.runtime_dir / "notifications").glob("*.json"))) == 1
    assert (settings.runtime_dir / "STOP").exists()


async def test_extreme_report_date_does_not_stop_worker(settings, monkeypatch):
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())
    service = ControlService(settings)
    await service.execute("profit:9999-12-31")
    assert not (settings.runtime_dir / "STOP").exists()


def test_production_origin_ignores_stale_quick_tunnel_override(settings):
    production = Settings(
        env="production",
        runtime_dir=settings.runtime_dir,
        telegram_bot_token="isolated-test-secret",
        telegram_chat_id=123,
        login_public_url="https://ojol.example.test",
    )
    (settings.runtime_dir / "public-url").write_text("http://localhost:6080")
    service = ControlService(production)
    assert service.public_url() == "https://ojol.example.test"


def test_form_expiry_race_returns_forbidden(settings, monkeypatch):
    from starlette.testclient import TestClient

    from ojol.control import create_app

    service = ControlService(settings)
    with TestClient(
        create_app(settings, service=service), base_url="http://localhost:6080"
    ) as client:
        ticket = service.access.issue("ticket")
        client.get("/access/" + ticket, follow_redirects=False)
        monkeypatch.setattr(service.access, "csrf_token", lambda session: None)
        assert client.get("/import-cookie").status_code == 403
