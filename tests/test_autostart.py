import asyncio
import json
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from ojol.config import load_settings
from ojol.control import WORKER_SHUTDOWN
from ojol.controller import Controller, StopRequested
from ojol.healing import write_private
from ojol.http_api import HttpCoreError
from ojol.journal import Journal
from ojol.maintenance import MaintenanceWindow
from ojol.management import MultiAccountService
from ojol.models import ROOT, Settings
from ojol.session_transfer import parse_cookie_input
from ojol.telegram import queue_error


def manager_with_accounts(settings, **changes):
    settings = settings.model_copy(
        update={
            "env": "local",
            "operator_authorized": True,
            "telegram_chat_id": 111,
            "max_spend": None,
            "max_jobs": None,
            "max_minutes": None,
            **changes,
        }
    )
    manager = MultiAccountService(settings)
    manager.registry.whitelist(222)
    manager.registry.create(222, "Friend")
    for row in manager.registry.list():
        service = manager.service(row["id"])
        write_private(
            service.settings.runtime_dir / "http-session.json",
            parse_cookie_input("fixture-" + row["id"]),
        )
    return manager


def worker():
    child = SimpleNamespace(returncode=None, pid=12345)
    child.terminate = Mock(side_effect=lambda: setattr(child, "returncode", 0))
    return child


def notices(settings):
    return [
        json.loads(path.read_text())["text"]
        for path in (settings.runtime_dir / "notifications").glob("*.json")
    ]


async def test_boot_defers_worker_during_maintenance_until_end(settings, monkeypatch):
    clock = datetime.fromisoformat("2026-11-12T00:28+07:00")
    monkeypatch.setattr("ojol.maintenance.now", lambda: clock)
    manager = manager_with_accounts(settings)
    window = MaintenanceWindow.parse("2026-11-12 00:30 / 2026-11-12 01:30")
    write_private(manager.maintenance_file, window.payload())
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    assert not window.held(datetime.fromisoformat("2026-11-12T00:27:59+07:00"))
    try:
        await manager.start()
        spawn.assert_not_awaited()
        assert all(service.auto_start_pending for service in manager.services.values())
        clock = window.end
        await manager.resume_workers()
        assert spawn.await_count == 2
        assert all(
            call.kwargs["env"]["OJOL_MAINTENANCE_FILE"] == str(manager.maintenance_file)
            for call in spawn.await_args_list
        )
    finally:
        await manager.close()


def test_auto_start_defaults_true_and_env_can_disable_it(monkeypatch):
    assert Settings().auto_start is True
    monkeypatch.setenv("OJOL_AUTO_START", "false")
    assert load_settings(ROOT / ".env.testing").auto_start is False
    monkeypatch.setenv("OJOL_AUTO_START", "true")
    assert load_settings(ROOT / ".env.testing").auto_start is True
    monkeypatch.setenv("OJOL_AUTO_START", "invalid")
    with pytest.raises(ValidationError):
        load_settings(ROOT / ".env.testing")


async def test_boot_starts_all_saved_accounts_including_previously_stopped_and_no_duplicates(
    settings, monkeypatch
):
    manager = manager_with_accounts(settings)
    for service in manager.services.values():
        (service.settings.runtime_dir / "STOP").touch()
        write_private(service.settings.runtime_dir / "status.json", {"pid": 9, "event": "gagal"})
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    await manager.resume_workers()
    assert spawn.await_count == 2 and manager.active_workers() == 2
    assert all(
        call.kwargs["env"]["OJOL_WORKER_AUTO_START"] == "1" for call in spawn.await_args_list
    )
    assert all(not s.auto_start_pending for s in manager.services.values())
    assert all(not notices(s.settings) for s in manager.services.values())
    await manager.close()
    for service in manager.services.values():
        assert (service.settings.runtime_dir / "STOP").exists()
        assert (service.settings.runtime_dir / WORKER_SHUTDOWN).exists()
        assert len(notices(service.settings)) == 1
        assert "Aplikasi sedang ditutup" in notices(service.settings)[0]
    restored = MultiAccountService(manager.settings)
    await restored.start()
    assert spawn.await_count == 4 and restored.active_workers() == 2
    assert all(
        not (s.settings.runtime_dir / WORKER_SHUTDOWN).exists() for s in restored.services.values()
    )
    await restored.close()


async def test_env_false_disables_all_auto_start_even_with_old_resume_markers(
    settings, monkeypatch
):
    manager = manager_with_accounts(settings, auto_start=False)
    previously_active, idle = manager.services.values()
    for service in manager.services.values():
        write_private(service.settings.runtime_dir / "worker-restart.json", {"ready": True})
    (previously_active.settings.runtime_dir / WORKER_SHUTDOWN).touch()
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    await manager.resume_workers()
    spawn.assert_not_awaited()
    assert not any(s.auto_start_pending for s in manager.services.values())
    assert not notices(idle.settings)
    assert "mulai otomatis dimatikan" in notices(previously_active.settings)[0]
    assert "Tekan Jalankan Ojol" in notices(previously_active.settings)[0]
    await manager.close()


async def test_capacity_queue_drains_but_manual_stop_cancels_pending_account(settings, monkeypatch):
    manager = manager_with_accounts(settings)
    manager.registry.set_limit("max_active_workers", 1)
    a, b = manager.services.values()
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    assert spawn.await_count == 1 and b.auto_start_pending
    await b.command("stop")
    await a.command("stop")
    await manager.resume_workers()
    assert spawn.await_count == 1 and manager.active_workers() == 0
    await manager.close()


async def test_waiting_accounts_start_when_capacity_becomes_available(settings, monkeypatch):
    manager = manager_with_accounts(settings)
    manager.registry.set_limit("max_active_workers", 1)
    a, b = manager.services.values()
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    assert spawn.await_count == 1 and b.auto_start_pending
    await a.command("stop")
    await manager.resume_workers()
    assert spawn.await_count == 2 and not b.auto_start_pending
    await manager.close()


@pytest.mark.parametrize(
    "blocked", ["pending", "uncertain", "revoked", "archived", "no_cookie", "invalid_cookie"]
)
async def test_auto_start_preserves_guards_and_other_accounts_can_start(
    settings, state, monkeypatch, blocked
):
    manager = manager_with_accounts(settings)
    bad, good = manager.services.values()
    if blocked in {"pending", "uncertain"}:
        journal = Journal(bad.settings.runtime_dir)
        run = journal.start(bad.settings)
        action = journal.begin(run, "purchase", state, {})
        if blocked == "uncertain":
            journal.settle(action, False)
        journal.close()
    elif blocked == "revoked":
        bad, good = good, bad
        manager.registry.whitelist(bad.settings.telegram_chat_id, False)
    elif blocked == "archived":
        manager.registry.archive(bad.settings.telegram_chat_id, bad.account_id)
    elif blocked == "no_cookie":
        (bad.settings.runtime_dir / "http-session.json").unlink()
    else:
        (bad.settings.runtime_dir / "http-session.json").write_text("invalid cookie payload")
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    await manager.resume_workers()
    assert spawn.await_count == (2 if blocked in {"pending", "uncertain"} else 1)
    assert any(
        call.kwargs["env"]["OJOL_RUNTIME_DIR"] == str(good.settings.runtime_dir)
        for call in spawn.await_args_list
    )
    assert not bad.auto_start_pending
    if blocked in {"pending", "uncertain"}:
        assert not notices(bad.settings)
        journal = Journal(bad.settings.runtime_dir)
        assert journal.history()["actions"][0]["status"] == blocked
        assert journal.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        journal.close()
    elif blocked in {"no_cookie", "invalid_cookie"}:
        assert "Import Cookie" in notices(bad.settings)[0]
        if blocked == "invalid_cookie":
            assert "Login ulang diperlukan" in notices(bad.settings)[0]
    else:
        assert not notices(bad.settings)
    await manager.close()


@pytest.mark.parametrize("mode", ["ready", "expired", "sleeping", "manual"])
async def test_restart_success_notice_requires_usable_game_state(settings, state, mode):
    state = state.model_copy(
        update={"phase": "delivering", "remaining_seconds": 10, "trip": "fixture A ke B"}
    )
    end = StopRequested("fixture stop")
    if mode == "expired":
        snapshots = [HttpCoreError("fixture expired", "auth")]
        error = HttpCoreError
    elif mode == "sleeping":
        snapshots = [state.model_copy(update={"phase": "sleeping"})]
        error = RuntimeError
    else:
        snapshots = [state, state, end]
        error = StopRequested
    ui = SimpleNamespace(snapshot=AsyncMock(side_effect=snapshots))
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        controller.wait = AsyncMock()
        with pytest.raises(error):
            await controller.run(auto_start=mode != "manual")
    finally:
        journal.close()
    successes = [text for text in notices(settings) if "Bot siap kembali" in text]
    assert len(successes) == int(mode == "ready")


async def test_worker_error_does_not_trigger_an_auto_restart_loop(settings, monkeypatch):
    manager = manager_with_accounts(settings)
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    service = next(iter(manager.services.values()))
    queue_error(service.settings, RuntimeError("fixture HTTP failure"), "http.auth")
    service.worker.returncode = 2
    await manager.resume_workers()
    await manager.resume_workers()
    assert spawn.await_count == 2
    assert (service.settings.runtime_dir / "STOP").exists()
    await manager.close()


async def test_auto_start_uses_new_sessions_with_configured_session_limits(settings, monkeypatch):
    manager = manager_with_accounts(settings, max_jobs=2, max_minutes=1, max_spend=10)
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    assert spawn.await_count == 2
    assert all(
        s.settings.max_jobs == 2 and s.settings.max_spend == 10 and s.settings.max_minutes == 1
        for s in manager.services.values()
    )
    await manager.close()


async def test_operator_authorization_still_required(settings, monkeypatch):
    manager = manager_with_accounts(settings, operator_authorized=False)
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    await manager.resume_workers()
    spawn.assert_not_awaited()
    assert not any(s.auto_start_pending for s in manager.services.values())
    assert all("izin operator" in notices(s.settings)[0] for s in manager.services.values())
    await manager.close()


async def test_testing_environment_never_auto_starts(settings, monkeypatch):
    manager = MultiAccountService(settings.model_copy(update={"telegram_chat_id": 111}))
    service = manager.service(manager.registry.selected(111)["id"])
    write_private(
        service.settings.runtime_dir / "http-session.json", parse_cookie_input("fixture-testing")
    )
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.start()
    await manager.resume_workers()
    spawn.assert_not_awaited()
    assert not service.auto_start_pending
    await manager.close()


async def test_real_sigterm_stops_isolated_dummy_worker(settings):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import signal,sys,time; signal.signal(signal.SIGTERM,lambda *_:sys.exit(0)); print('ready',flush=True); time.sleep(60)",
        stdout=asyncio.subprocess.PIPE,
    )
    service.worker = child
    try:
        assert await asyncio.wait_for(child.stdout.readline(), 3) == b"ready\n"
        await manager.close()
        assert child.returncode == 0
        assert not service.auto_start_pending
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
