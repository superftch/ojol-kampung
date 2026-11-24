import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.kampung.session_transfer import parse_cookie_input
from app.modules.worker.supervisor import (
    WorkerService,
    get_commands_dir,
    get_socket_path,
    root_runtime_dir,
    send_worker_command,
)


def test_runtime_dir_resolution(settings):
    short_base = pytest.importorskip("pathlib").Path("/data/runtime")
    account_dir = short_base / "accounts" / "abc123"
    control_dir = short_base / "control" / "users" / "123"

    assert root_runtime_dir(short_base) == short_base
    assert root_runtime_dir(account_dir) == short_base
    assert root_runtime_dir(control_dir) == short_base

    assert get_socket_path(account_dir) == short_base / "worker.sock"
    assert get_commands_dir(account_dir) == short_base / "worker-commands"

    # For long paths (like in pytest sandbox), it safely returns the deterministic short path
    assert get_socket_path(settings.runtime_dir).name.startswith("ojol_")


@pytest.mark.asyncio
async def test_worker_service_ping_and_ipc(settings):
    service = WorkerService(settings)
    await service.start()
    try:
        # Test IPC ping via Unix domain socket
        resp = await send_worker_command(settings.runtime_dir, {"action": "ping"})
        assert resp is not None
        assert resp["ok"] is True
        assert resp["pong"] is True

        # Test IPC status
        status_resp = await send_worker_command(settings.runtime_dir, {"action": "status"})
        assert status_resp is not None
        assert status_resp["ok"] is True
        assert "workers" in status_resp

        # Test unknown action
        err_resp = await send_worker_command(settings.runtime_dir, {"action": "invalid"})
        assert err_resp is not None
        assert err_resp["ok"] is False
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_worker_service_file_fallback(settings):
    service = WorkerService(settings)
    cmds_dir = get_commands_dir(settings.runtime_dir)
    cmds_dir.mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(service._supervise_loop())
    try:
        resp = await send_worker_command(settings.runtime_dir, {"action": "ping"}, timeout=2.0)
        assert resp == {"ok": True, "pong": True, "active_workers": 0}
        assert list(cmds_dir.iterdir()) == []
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_worker_service_start_validations(settings):
    service = WorkerService(settings)
    # Start without authorization
    resp = await service.start_account_worker(account_id=None)
    assert resp["ok"] is False
    assert "belum diizinkan" in resp["error"]


@pytest.mark.asyncio
async def test_worker_starts_additional_account_from_root_registry(settings, monkeypatch):
    settings = settings.model_copy(update={"operator_authorized": True})
    service = WorkerService(settings)
    owner = 1002
    service.registry.set_owner_access(owner)
    account_id = service.registry.create(owner, "Akun tambahan")["id"]
    scoped, _ = service.scoped_account_settings(account_id)
    scoped.runtime_dir.mkdir(parents=True)
    (scoped.runtime_dir / "http-session.json").write_text(
        json.dumps(parse_cookie_input("fixture-session"))
    )
    spawn = AsyncMock(return_value=SimpleNamespace(pid=1234))
    monkeypatch.setattr("app.modules.worker.supervisor.asyncio.create_subprocess_exec", spawn)

    assert (await service.start_account_worker(account_id))["ok"]
    assert spawn.await_args is not None
    args, kwargs = spawn.await_args
    assert args[-4:] == ("--account", account_id, "run", "--live")
    assert kwargs["env"]["OJOL_RUNTIME_DIR"] == str(settings.runtime_dir)
    assert kwargs["env"].get("OJOL_ACCOUNT_ID") == account_id
