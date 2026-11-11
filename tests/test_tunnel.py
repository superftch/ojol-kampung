import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from ojol.control import ControlService


def tunnel_service(settings):
    settings = settings.model_copy(
        update={
            "env": "local",
            "tunnel_enabled": True,
            "runtime_dir": settings.runtime_dir / "runtime",
        }
    )
    settings.runtime_dir.mkdir()
    return ControlService(settings)


def test_testing_config_rejects_live_tunnel(settings):
    values = settings.model_dump()
    with pytest.raises(ValidationError):
        type(settings)(**{**values, "tunnel_enabled": True})


async def test_tunnel_secret_file_and_single_owned_process(settings, monkeypatch):
    service = tunnel_service(settings)
    token_file = service.settings.runtime_dir.parent / "cloudflared-token"
    token_file.write_text("isolated-fake-token")
    token_file.chmod(0o600)
    is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path: path == Path("/.dockerenv") or is_file(path))
    monkeypatch.setattr("ojol.control.shutil.which", lambda binary: "/bin/cloudflared")
    child = SimpleNamespace(returncode=None, terminate=Mock(), wait=AsyncMock())
    spawn = AsyncMock(return_value=child)
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await service.start_tunnel()
    await service.start_tunnel()
    spawn.assert_awaited_once()
    args = spawn.call_args.args
    assert args[-2:] == ("--token-file", str(token_file))
    assert "isolated-fake-token" not in str(spawn.call_args)
    assert "127.0.0.1:2000" in args and service.tunnel_alive()
    await service.close()
    child.terminate.assert_called_once()
    assert not service.tunnel_alive()


async def test_disabled_tunnel_never_spawns(settings, monkeypatch):
    service = ControlService(settings)
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    await service.start_tunnel()
    spawn.assert_not_awaited()


async def test_missing_tunnel_secret_reports_error_without_spawn(settings, monkeypatch):
    service = tunnel_service(settings)
    monkeypatch.setattr(Path, "is_file", lambda path: path == Path("/.dockerenv"))
    monkeypatch.setattr("ojol.control.shutil.which", lambda binary: "/bin/cloudflared")
    spawn = AsyncMock()
    monkeypatch.setattr("ojol.control.asyncio.create_subprocess_exec", spawn)
    with pytest.raises(RuntimeError, match="secret cloudflared_token"):
        await service.start_tunnel()
    spawn.assert_not_awaited()


async def test_tunnel_exit_stops_worker_once_and_reports_stage(settings, monkeypatch):
    service = tunnel_service(settings)
    service.tunnel_process = SimpleNamespace(returncode=1)
    service.stop_worker = AsyncMock()
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())
    iterations = 0

    async def wait(seconds):
        nonlocal iterations
        iterations += 1
        if iterations == 2:
            service.closing = True

    monkeypatch.setattr("ojol.control.asyncio.sleep", wait)
    await service.supervise()
    service.stop_worker.assert_awaited_once()
    error = json.loads((service.settings.runtime_dir / "last-error.json").read_text())
    assert error["stage"] == "tunnel.process_exit"
    assert (service.settings.runtime_dir / "STOP").exists()
    assert len(list((service.settings.runtime_dir / "notifications").glob("*.json"))) == 1


async def test_shutdown_cleans_tunnel_even_when_worker_stop_fails(settings):
    service = tunnel_service(settings)
    child = service.tunnel_process = SimpleNamespace(
        returncode=None, terminate=Mock(), wait=AsyncMock()
    )
    service.stop_worker = AsyncMock(side_effect=RuntimeError("Worker fixture stuck"))
    with pytest.raises(RuntimeError, match="Worker fixture stuck"):
        await service.close()
    child.terminate.assert_called_once()
