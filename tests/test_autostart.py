import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ojol.cli import main
from ojol.healing import write_private
from ojol.journal import Journal
from ojol.management import MultiAccountService
from ojol.session_transfer import parse_cookie_input
from ojol.telegram import queue_error


def manager_with_accounts(settings):
    settings = settings.model_copy(
        update={
            "env": "local",
            "operator_authorized": True,
            "telegram_chat_id": 111,
            "max_spend": None,
            "max_jobs": None,
            "max_minutes": None,
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


async def test_clean_deploy_restores_previously_running_accounts_and_never_duplicates(
    settings, monkeypatch
):
    manager = manager_with_accounts(settings)
    monkeypatch.setattr(
        "ojol.control.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=lambda *a, **kw: worker()),
    )
    for service in manager.services.values():
        await service.command("run")
        assert not service.restart_ready() and service.restart_file.exists()
    await manager.close()
    assert all(
        s.restart_ready() and not (s.settings.runtime_dir / "STOP").exists()
        for s in manager.services.values()
    )
    restored = MultiAccountService(manager.settings)
    for row in restored.registry.list():
        restored.service(row["id"])
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await restored.start()
    await restored.resume_workers()
    assert spawn.await_count == 2
    assert restored.active_workers() == 2
    assert all(not s.restart_ready() for s in restored.services.values())
    await restored.close()


async def test_stopped_account_stays_stopped_after_deploy(settings, monkeypatch):
    manager = manager_with_accounts(settings)
    monkeypatch.setattr(
        "ojol.control.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=lambda *a, **kw: worker()),
    )
    a, b = manager.services.values()
    await a.command("run")
    await b.command("run")
    await b.command("stop")
    assert not b.restart_file.exists()
    await manager.close()
    assert a.restart_ready() and not b.restart_file.exists()
    restored = MultiAccountService(manager.settings)
    for row in restored.registry.list():
        restored.service(row["id"])
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await restored.resume_workers()
    spawn.assert_awaited_once()
    await restored.close()


async def test_auto_start_waits_for_global_capacity_then_starts_remaining_account(
    settings, monkeypatch
):
    manager = manager_with_accounts(settings)
    services = list(manager.services.values())
    for service in services:
        write_private(service.restart_file, {"ready": True})
    manager.registry.set_limit("max_active_workers", 1)
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.resume_workers()
    assert spawn.await_count == 1 and services[1].restart_ready()
    await services[0].command("stop")
    await manager.resume_workers()
    assert spawn.await_count == 2 and not services[1].restart_ready()
    await manager.close()


@pytest.mark.parametrize(
    "blocked", ["pending", "uncertain", "stop", "revoked", "session", "limited"]
)
async def test_auto_start_blocks_unsafe_account_and_continues_healthy_account(
    settings, state, monkeypatch, blocked
):
    manager = manager_with_accounts(settings)
    bad, good = manager.services.values()
    for service in (bad, good):
        write_private(service.restart_file, {"ready": True})
    if blocked in {"pending", "uncertain"}:
        journal = Journal(bad.settings.runtime_dir)
        run = journal.start(bad.settings)
        action = journal.begin(run, "purchase", state, {})
        if blocked == "uncertain":
            journal.settle(action, False)
        journal.close()
    elif blocked == "stop":
        (bad.settings.runtime_dir / "STOP").touch()
    elif blocked == "revoked":
        bad, good = good, bad
        manager.registry.whitelist(bad.settings.telegram_chat_id, False)
    elif blocked == "session":
        (bad.settings.runtime_dir / "http-session.json").unlink()
    else:
        bad.settings = bad.settings.model_copy(update={"max_spend": 10})
    spawn = AsyncMock(side_effect=lambda *a, **kw: worker())
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.resume_workers()
    spawn.assert_awaited_once()
    assert str(good.settings.runtime_dir) == spawn.call_args.kwargs["env"]["OJOL_RUNTIME_DIR"]
    assert not bad.restart_file.exists()
    if blocked in {"pending", "uncertain"}:
        journal = Journal(bad.settings.runtime_dir)
        assert journal.history()["actions"][0]["status"] == blocked
        assert journal.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        journal.close()
    await manager.close()


async def test_terminal_error_manual_cli_stop_and_import_revoke_restart_intent(
    settings, monkeypatch
):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    write_private(service.restart_file, {"ready": False})
    queue_error(service.settings, RuntimeError("fixture"), "fixture.error")
    assert not service.restart_file.exists()
    write_private(settings.runtime_dir / "worker-restart.json", {"ready": True})
    monkeypatch.setenv("OJOL_RUNTIME_DIR", str(settings.runtime_dir))
    from ojol.models import ROOT

    assert main(["--env-file", str(ROOT / ".env.testing"), "stop"]) == 0
    assert not (settings.runtime_dir / "worker-restart.json").exists()
    write_private(service.restart_file, {"ready": True})
    service.settings = service.settings.model_copy(
        update={"login_public_url": "http://localhost:6080"}
    )
    await service.cookie_link()
    assert not service.restart_file.exists()


@pytest.mark.parametrize("content", ['{"ready":false}', "{invalid"])
async def test_abrupt_restart_never_auto_starts_and_reports_interruption(
    settings, monkeypatch, content
):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    service.restart_file.write_text(content)
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())
    await service.start(poll=False)
    try:
        assert not service.restart_file.exists()
        error = json.loads((service.settings.runtime_dir / "last-error.json").read_text())
        assert error["stage"] == "worker.interrupted"
        assert service.worker is None
    finally:
        await service.close()


async def test_shutdown_error_never_leaves_ready_marker(settings):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    write_private(service.restart_file, {"ready": True})
    service.stop_worker = AsyncMock(side_effect=RuntimeError("fixture stuck"))
    with pytest.raises(RuntimeError, match="fixture stuck"):
        await service.close(preserve_restart=True)
    assert not service.restart_file.exists()


async def test_real_sigterm_shutdown_of_isolated_dummy_worker_saves_resume_intent(settings):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import signal,sys,time; signal.signal(signal.SIGTERM,lambda *_: sys.exit(0)); print('ready',flush=True); time.sleep(60)",
        stdout=asyncio.subprocess.PIPE,
    )
    service.worker = child
    try:
        assert await asyncio.wait_for(child.stdout.readline(), 3) == b"ready\n"
        write_private(service.restart_file, {"ready": False})
        await service.close(preserve_restart=True)
        assert child.returncode == 0
        assert service.restart_ready()
        assert not (service.settings.runtime_dir / "STOP").exists()
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()


async def test_testing_environment_and_fresh_install_never_spawn_workers(settings, monkeypatch):
    testing = MultiAccountService(settings.model_copy(update={"telegram_chat_id": 111}))
    service = testing.service(testing.registry.selected(111)["id"])
    write_private(service.restart_file, {"ready": True})
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await testing.resume_workers()
    fresh = manager_with_accounts(
        settings.model_copy(update={"runtime_dir": settings.runtime_dir / "fresh"})
    )
    await fresh.resume_workers()
    spawn.assert_not_awaited()


async def test_already_running_worker_is_not_restarted_or_reported_repeatedly(
    settings, monkeypatch
):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    write_private(service.restart_file, {"ready": True})
    service.worker = worker()
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await manager.resume_workers()
    await manager.resume_workers()
    spawn.assert_not_awaited()
    assert not list((service.settings.runtime_dir / "notifications").glob("*.json"))
    await manager.close()


async def test_bounded_session_never_arms_auto_start(settings, monkeypatch):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    service.settings = service.settings.model_copy(update={"max_jobs": 2})
    monkeypatch.setattr(
        "ojol.control.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=lambda *a, **kw: worker()),
    )
    await service.command("run")
    assert not service.restart_file.exists()
    await service.close(preserve_restart=True)
    assert not service.restart_file.exists()


async def test_error_during_shutdown_never_becomes_clean_restart(settings, monkeypatch):
    manager = manager_with_accounts(settings)
    service = next(iter(manager.services.values()))
    service.worker = worker()
    write_private(service.restart_file, {"ready": False})

    def fail_on_stop():
        queue_error(service.settings, RuntimeError("fixture shutdown failure"), "worker.shutdown")
        service.worker.returncode = 1

    service.worker.terminate = Mock(side_effect=fail_on_stop)
    await service.close(preserve_restart=True)
    assert not service.restart_file.exists()
    assert (service.settings.runtime_dir / "STOP").exists()
