import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.models import Settings, Snapshot
from app.integrations.kampung.cookies import COOKIE_NAME, DOMAIN
from app.modules.ledger.repository import Journal
from app.modules.notifications.service import event_text
from app.modules.worker.controller import Controller
from app.modules.worker.fleet_supervision import FleetSupervisor
from app.modules.worker.ojol_jitter import (
    OJOL_JITTER_FILE,
    WIB,
    finish_ojol_jitter,
    is_ojol_jitter_active,
    load_ojol_jitter_state,
    mark_account_offline_for_jitter,
    maybe_start_ojol_jitter,
)
from app.modules.worker.settings import set_auto_flag
from app.modules.worker.status import build_account_summary, format_ojol_status


def _make_settings(tmp_path: Path) -> Settings:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return Settings(env="testing", runtime_dir=runtime, operator_authorized=False)


def _idle_snapshot() -> Snapshot:
    return Snapshot(
        wallet=Decimal("100.00"),
        fuel=90,
        condition=90,
        data=90,
        phase="idle",
        buttons=["Cari order"],
        ojol_vehicle="motor",
    )


def test_ojol_jitter_daily_limits_and_midnight_reset(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    rng = random.Random(42)  # noqa: S311 - deterministic test RNG
    t0 = datetime(2026, 11, 25, 8, 0, tzinfo=WIB)

    # First call schedules next_trigger_at in the future and returns None
    assert maybe_start_ojol_jitter(runtime, current_time=t0, rng=rng) is None
    state = load_ojol_jitter_state(runtime, current_time=t0)
    assert state["next_trigger_at"] is not None
    assert state["count_60m"] == 0
    assert state["count_30m"] == 0

    # Before trigger time, does not start
    assert maybe_start_ojol_jitter(runtime, current_time=t0 + timedelta(minutes=10), rng=rng) is None

    # Simulate 4 breaks over the day -> max 2x 60m + 2x 30m
    kinds: list[str] = []
    cur = t0
    for _ in range(4):
        state = load_ojol_jitter_state(runtime, current_time=cur)
        trigger = datetime.fromisoformat(state["next_trigger_at"])
        started = maybe_start_ojol_jitter(runtime, current_time=trigger, rng=rng)
        assert started is not None
        kinds.append(started["kind"])
        assert is_ojol_jitter_active(runtime, current_time=trigger + timedelta(seconds=10))
        cur = started["until"] + timedelta(seconds=1)
        finish_ojol_jitter(runtime, current_time=cur, rng=rng)

    assert kinds.count("60m") == 2
    assert kinds.count("30m") == 2

    # 5th attempt on the same day must not trigger
    final_state = load_ojol_jitter_state(runtime, current_time=cur)
    assert final_state["next_trigger_at"] is None
    assert maybe_start_ojol_jitter(runtime, current_time=cur + timedelta(hours=2), rng=rng) is None

    # Next WIB day resets quota
    next_day = datetime(2026, 11, 26, 7, 0, tzinfo=WIB)
    assert maybe_start_ojol_jitter(runtime, current_time=next_day, rng=rng) is None
    reset_state = load_ojol_jitter_state(runtime, current_time=next_day)
    assert reset_state["date"] == "2026-11-26"
    assert reset_state["count_60m"] == 0
    assert reset_state["count_30m"] == 0


def test_account_summary_and_status_during_jitter_offline(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    runtime = settings.runtime_dir
    (runtime / "http-session.json").write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": COOKIE_NAME,
                        "value": "test-val",
                        "domain": DOMAIN,
                        "path": "/",
                        "secure": True,
                        "httpOnly": True,
                        "expires": 9999999999,
                    }
                ]
            }
        )
    )
    t0 = datetime(2026, 11, 25, 10, 0, tzinfo=WIB)
    until = t0 + timedelta(minutes=30)

    # Write active jitter & offline marker, with worker lock held (worker active!)
    (runtime / OJOL_JITTER_FILE).write_text(
        json.dumps(
            {
                "date": "2026-11-25",
                "count_60m": 0,
                "count_30m": 1,
                "next_trigger_at": None,
                "active_kind": "30m",
                "active_started_at": t0.isoformat(),
                "active_until": until.isoformat(),
            }
        )
    )
    mark_account_offline_for_jitter(runtime, kind="30m", until=until, current_time=t0)
    (runtime / "status.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "event": "ojol_jitter_mulai",
                "stage": "ojol.jitter_offline",
                "wait_until": until.isoformat(),
                "snapshot": _idle_snapshot().model_dump(mode="json"),
                "snapshot_received_at": t0.isoformat(),
            }
        )
    )

    summary = build_account_summary(
        settings,
        is_running=lambda _: True,
        current_time=lambda: t0 + timedelta(minutes=5),
    )
    assert summary["active"] is True
    assert summary["online"] is False
    assert "Jitter Ojol" in summary["status_text"]
    assert "30 menit" in summary["status_text"]

    report = format_ojol_status(
        settings,
        worker_proc=None,
        expected_stop=False,
        auto_start_pending=False,
        maintenance_file=runtime / "maintenance.json",
        tunnel_alive=True,
        is_running=lambda _: True,
        current_time=lambda: t0 + timedelta(minutes=5),
    )
    assert "Jitter Offline Ojol" in report
    assert "worker tetap aktif" in report


@pytest.mark.asyncio
async def test_fleet_supervisor_skips_presence_ping_during_jitter(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    runtime = settings.runtime_dir
    (runtime / "http-session.json").write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": COOKIE_NAME,
                        "value": "test-val",
                        "domain": DOMAIN,
                        "path": "/",
                        "secure": True,
                        "httpOnly": True,
                        "expires": 9999999999,
                    }
                ]
            }
        )
    )
    t0 = datetime.now(WIB)
    (runtime / OJOL_JITTER_FILE).write_text(
        json.dumps(
            {
                "date": t0.date().isoformat(),
                "count_60m": 1,
                "count_30m": 0,
                "next_trigger_at": None,
                "active_kind": "60m",
                "active_started_at": t0.isoformat(),
                "active_until": (t0 + timedelta(minutes=60)).isoformat(),
            }
        )
    )

    service = MagicMock()
    service.settings = settings
    service.worker = None
    service.fetch_online_status = AsyncMock()

    fleet = MagicMock()
    fleet.settings = Settings(env="local", runtime_dir=runtime, operator_authorized=False)
    fleet.registry.list.return_value = [{"id": "acc1", "owner": "u1"}]
    fleet.registry.allowed.return_value = True
    fleet.service.return_value = service

    supervisor = FleetSupervisor(fleet)
    await supervisor.maintain_online_presence()
    service.fetch_online_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_runs_jitter_offline_without_server_pings(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    runtime = settings.runtime_dir
    set_auto_flag(runtime, "ojol", True)

    # Pre-seed an active 0.4s jitter break so Controller resumes it without waiting 30m
    t0 = datetime.now(WIB)
    until = t0 + timedelta(milliseconds=400)
    (runtime / OJOL_JITTER_FILE).write_text(
        json.dumps(
            {
                "date": t0.date().isoformat(),
                "count_60m": 0,
                "count_30m": 1,
                "next_trigger_at": None,
                "active_kind": "30m",
                "active_started_at": t0.isoformat(),
                "active_until": until.isoformat(),
            }
        )
    )

    class _FakeUI:
        def __init__(self) -> None:
            self.fetch_online_status = AsyncMock()
            self.snapshot = AsyncMock(return_value=_idle_snapshot())
            self.job_click = AsyncMock()

    ui = _FakeUI()

    journal = Journal(runtime)
    cancel = asyncio.Event()
    controller = Controller(ui, settings, journal, journal.start(settings), cancel=cancel)

    # Stop shortly after jitter finishes
    async def stop_after_jitter() -> None:
        await asyncio.sleep(0.6)
        cancel.set()

    stopper = asyncio.create_task(stop_after_jitter())
    try:
        with pytest.raises(Exception, match="Dihentikan pengguna"):
            await controller.run()
    finally:
        await stopper
        journal.close()

    # During jitter break, online-status.json was marked offline and fetch_online_status was not called
    ui.fetch_online_status.assert_not_awaited()
    assert not is_ojol_jitter_active(runtime)
    # After jitter finished, snapshot was called to resume normal ojol loop
    ui.snapshot.assert_awaited()


def test_jitter_notification_text() -> None:
    msg_start = event_text(
        "ojol_jitter_mulai",
        {"label": "1 jam", "until": "2026-11-25T16:30:00+07:00"},
    )
    assert msg_start is not None
    assert "1 jam" in msg_start
    assert "offline" in msg_start.lower()
    assert "worker tetap berjalan" in msg_start.lower()

    msg_end = event_text("ojol_jitter_selesai", {"label": "1 jam"})
    assert msg_end is not None
    assert "selesai" in msg_end.lower()
