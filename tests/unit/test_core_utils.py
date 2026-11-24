"""Focused unit tests for extracted Milestone 1 core leaf modules."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.database import read_sqlite
from app.core.formatting import format_coins, format_koin, parse_coins
from app.core.locks import exclusive_lock, running
from app.core.storage import status_record, status_timestamp, write_private


def test_locks_exclusive_and_running(tmp_path):
    assert running(tmp_path) is False
    with exclusive_lock(tmp_path):
        assert running(tmp_path) is True
        with pytest.raises(RuntimeError), exclusive_lock(tmp_path):
            pass
    assert running(tmp_path) is False


def test_storage_write_private_and_status_helpers(tmp_path):
    target = tmp_path / "status.json"
    write_private(target, {"event": "mulai", "count": 2})
    assert (target.stat().st_mode & 0o777) == 0o600
    data, mtime_ns = status_record(target)
    assert data == {"event": "mulai", "count": 2}
    assert mtime_ns > 0

    assert status_record(tmp_path / "missing.json") == ({}, 0)
    bad = tmp_path / "bad.json"
    bad.write_text("not-json")
    assert status_record(bad) == ({}, 0)

    assert status_timestamp("2026-11-25T00:00:00+00:00") == datetime(2026, 11, 25, 0, 0, tzinfo=UTC)
    assert status_timestamp("2026-11-25T00:00:00") is None
    assert status_timestamp("invalid") is None


def test_formatting_coins():
    assert parse_coins("1234.50") == Decimal("1234.50")
    assert parse_coins("NaN") == Decimal(0)
    assert parse_coins("bad") == Decimal(0)
    assert format_coins(Decimal("1234.500")) == "1.234,5"
    assert format_coins(Decimal("1000")) == "1.000"
    assert format_koin("12.5") == "12,5 koin"


def test_sqlite_reader_cannot_write_or_create(tmp_path):
    path = tmp_path / "history #old.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE purchases (amount INTEGER)")
    with read_sqlite(path) as db:
        assert db.execute("SELECT COUNT(*) FROM purchases").fetchone() == (0,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("INSERT INTO purchases VALUES (1)")
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError), read_sqlite(missing):
        pass
    assert not missing.exists()
