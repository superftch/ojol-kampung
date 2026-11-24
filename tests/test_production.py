import pytest
from pydantic import ValidationError

from ojol.control import ControlService
from ojol.journal import Journal
from ojol.models import Settings


def test_production_requires_https_and_cash_floor(settings):
    values = dict(
        env="production",
        runtime_dir=settings.runtime_dir,
        login_public_url="https://ojol.example.test",
    )
    valid = Settings.model_validate(values)
    assert valid.max_jobs is None and valid.max_minutes is None
    for change in (
        {"login_public_url": "http://localhost:6080"},
        {"min_balance": "4.99"},
    ):
        with pytest.raises(ValidationError):
            Settings.model_validate({**values, **change})


def test_ledger_uses_wal_and_daily_index(settings):
    journal = Journal(settings.runtime_dir)
    try:
        assert journal.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert "cashflows_created" in [
            row["name"] for row in journal.db.execute("PRAGMA index_list('cashflows')")
        ]
    finally:
        journal.close()


async def test_extreme_report_date_does_not_stop_worker(settings, monkeypatch):
    service = ControlService(settings)
    await service.execute("profit:9999-12-31")
    assert not (settings.runtime_dir / "STOP").exists()


def test_production_origin_ignores_stale_quick_tunnel_override(settings):
    production = Settings(
        env="production",
        runtime_dir=settings.runtime_dir,
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
