"""Standalone worker container daemon and IPC for Kampung Ojol.

Runs in a separate container from the web/control app so that app updates
do not restart or terminate background workers.
"""

import asyncio
import hashlib
import json
import logging
import os
import signal
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from .accounts import Accounts
from .auto_settings import auto_flags
from .config import load_settings
from .locks import running
from .maintenance import SCHEDULE_FILE, held_window
from .models import ROOT, Settings
from .storage import write_private

logger = logging.getLogger("ojol.worker")
SOCKET_NAME = "worker.sock"
COMMANDS_DIR_NAME = "worker-commands"


def root_runtime_dir(runtime_dir: Path) -> Path:
    """Resolve base runtime directory if called from an account-scoped directory."""
    cur = runtime_dir
    if cur.parent.name == "accounts":
        return cur.parent.parent
    while cur.name in {"control", "users"} or cur.parent.name in {"control", "users"}:
        cur = cur.parent
    return cur


def get_socket_path(runtime_dir: Path) -> Path:
    base = root_runtime_dir(runtime_dir)
    target = base / SOCKET_NAME
    # AF_UNIX limit is 104 bytes on macOS and 108 bytes on Linux.
    # If the path is too long (e.g. deeply nested pytest directory), use a deterministic short path in tmp.
    if len(str(target).encode("utf-8")) >= 95:
        digest = hashlib.sha256(str(base).encode()).hexdigest()[:12]
        return Path(tempfile.gettempdir()) / f"ojol_{digest}.sock"
    return target


def get_commands_dir(runtime_dir: Path) -> Path:
    return root_runtime_dir(runtime_dir) / COMMANDS_DIR_NAME


async def send_worker_command(
    runtime_dir: Path, command: dict, timeout: float = 5.0
) -> dict | None:
    """Send command to worker service via Unix socket, falling back to command file.

    Returns response dict on success, or None if worker service is unavailable.
    """
    sock_path = get_socket_path(runtime_dir)
    # 1. Try Unix domain socket first
    if sock_path.exists():
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(sock_path)), timeout=timeout
            )
            try:
                payload = json.dumps(command) + "\n"
                writer.write(payload.encode())
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), timeout=timeout)
                if line:
                    return json.loads(line.decode().strip())
            finally:
                writer.close()
                await writer.wait_closed()
        except (OSError, asyncio.TimeoutError, json.JSONDecodeError):
            pass

    # 2. Fallback to file-based command queue if commands dir exists
    cmds_dir = get_commands_dir(runtime_dir)
    if cmds_dir.is_dir():
        cmd_id = uuid4().hex
        req_file = cmds_dir / f"{cmd_id}.json"
        res_file = cmds_dir / f"{cmd_id}.done"
        try:
            write_private(req_file, command)
            for _ in range(int(timeout * 10)):
                if res_file.is_file():
                    try:
                        data = json.loads(res_file.read_text())
                        res_file.unlink(missing_ok=True)
                        return data
                    except (OSError, json.JSONDecodeError):
                        return {"ok": True}
                await asyncio.sleep(0.1)
        except OSError:
            pass
        finally:
            req_file.unlink(missing_ok=True)

    return None


class WorkerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = Accounts(settings)
        self.runtime_dir = settings.runtime_dir
        self.maintenance_file = self.runtime_dir / SCHEDULE_FILE
        self.workers: dict[str, asyncio.subprocess.Process] = {}
        self.closing = False
        self.server: asyncio.Server | None = None
        self.tasks: list[asyncio.Task] = []
        self.lock = asyncio.Lock()

    def scoped_account_settings(self, account_id: str | None = None):
        if not account_id:
            account = next((row for row in self.registry.list() if row["legacy"]), None)
            if not account:
                return self.settings, ""
            return self.registry.scoped_settings(account), account["id"]
        account = self.registry.get(account_id)
        if not account:
            raise ValueError(f"Akun {account_id} tidak ditemukan")
        return self.registry.scoped_settings(account), account["id"]

    async def handle_request(self, data: dict) -> dict:
        action = data.get("action")
        account_id = data.get("account_id")
        mode = data.get("mode")
        auto_start = bool(data.get("auto_start", False))

        if action == "ping":
            return {
                "ok": True,
                "pong": True,
                "active_workers": self.active_worker_count(),
            }

        if action == "status":
            return {
                "ok": True,
                "workers": {
                    acc_key: (proc.returncode is None) for acc_key, proc in self.workers.items()
                },
            }

        if action == "start":
            return await self.start_account_worker(
                account_id=account_id,
                mode=mode,
                auto_start=auto_start,
                needs_only=data.get("needs_only") is True,
            )

        if action == "stop":
            return await self.stop_account_worker(account_id=account_id)

        return {"ok": False, "error": f"Aksi '{action}' tidak dikenal"}

    async def start_account_worker(
        self,
        account_id: str | None = None,
        mode: str | None = None,
        auto_start: bool = False,
        *,
        needs_only: bool = False,
    ) -> dict:
        async with self.lock:
            try:
                acc_settings, acc_id = self.scoped_account_settings(account_id)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}

            directory = acc_settings.runtime_dir
            acc_key = acc_id or "default"

            # Check if running
            existing = self.workers.get(acc_key)
            if (existing and existing.returncode is None) or running(directory):
                return {
                    "ok": True,
                    "already_running": True,
                    "message": "Worker sudah aktif untuk akun ini",
                }

            if not acc_settings.operator_authorized:
                return {
                    "ok": False,
                    "error": "Akun ini belum diizinkan menjalankan bot oleh admin.",
                }

            session_file = directory / "http-session.json"
            if not session_file.is_file():
                return {
                    "ok": False,
                    "error": "Sesi game belum tersedia. Gunakan Import Cookie terlebih dahulu.",
                }

            if maintenance := held_window(self.maintenance_file):
                if not (needs_only and maintenance.target == "ojol"):
                    if auto_start:
                        return {"ok": False, "maintenance": True, "message": maintenance.message()}
                    return {"ok": False, "error": maintenance.message()}

            if self.active_worker_count() >= self.registry.value("max_active_workers"):
                return {"ok": False, "error": "Slot worker penuh. Hentikan salah satu akun dulu."}

            # Unlink STOP file if present
            (directory / "STOP").unlink(missing_ok=True)

            config_file = os.environ.get("OJOL_CONFIG_FILE")
            args = [sys.executable, str(ROOT / "main.py")]
            if config_file and Path(config_file).is_file():
                args += ["--env-file", config_file]
            if acc_id:
                args += ["--account", acc_id]
            args += ["run", "--live"]

            env = {
                **os.environ,
                # The CLI resolves --account against the root registry before scoping settings.
                "OJOL_RUNTIME_DIR": str(self.runtime_dir),
                "OJOL_ACCOUNT_ID": acc_id,
                "OJOL_WORKER_AUTO_START": "1" if auto_start else "0",
                "OJOL_MAINTENANCE_FILE": str(self.maintenance_file),
                **({"OJOL_OJOL_MODE": mode} if mode in {"kendara", "otomatis"} else {}),
            }

            try:
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                    env=env,
                )
                self.workers[acc_key] = proc
                return {"ok": True, "pid": proc.pid, "message": "Worker berhasil dimulai"}
            except Exception as exc:
                return {"ok": False, "error": f"Gagal memulai worker: {exc}"}

    async def stop_account_worker(self, account_id: str | None = None) -> dict:
        try:
            acc_settings, acc_id = self.scoped_account_settings(account_id)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        directory = acc_settings.runtime_dir
        acc_key = acc_id or "default"

        (directory / "STOP").touch(mode=0o600)

        proc = self.workers.get(acc_key)
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

        # Wait up to 5 seconds
        for _ in range(20):
            if not running(directory) and not (proc and proc.returncode is None):
                break
            await asyncio.sleep(0.25)

        return {"ok": True, "message": "Worker dihentikan"}

    def active_worker_count(self) -> int:
        count = 0
        for acc in self.registry.list():
            if not self.registry.allowed(acc["owner"]):
                continue
            scoped = self.registry.scoped_settings(acc)
            acc_key = acc["id"]
            proc = self.workers.get(acc_key)
            if (proc and proc.returncode is None) or running(scoped.runtime_dir):
                count += 1
        return count

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not line:
                return
            data = json.loads(line.decode().strip())
            response = await self.handle_request(data)
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
        except Exception as exc:
            try:
                err_resp = {"ok": False, "error": str(exc)}
                writer.write((json.dumps(err_resp) + "\n").encode())
                await writer.drain()
            except OSError as write_error:
                logger.debug("Could not send worker IPC error (%s)", type(write_error).__name__)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError as close_error:
                logger.debug("Could not close worker IPC socket (%s)", type(close_error).__name__)

    async def _supervise_loop(self):
        commands_dir = get_commands_dir(self.runtime_dir)
        commands_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        while not self.closing:
            # 1. Process file-based commands if any
            for path in sorted(commands_dir.glob("*.json")):
                try:
                    raw = path.read_text()
                    path.unlink()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    logger.warning(
                        "Could not consume file-based worker command (%s)", type(exc).__name__
                    )
                    continue
                try:
                    response = await self.handle_request(json.loads(raw))
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)}
                try:
                    write_private(path.with_suffix(".done"), response)
                except OSError as exc:
                    logger.warning(
                        "Could not finish file-based worker command (%s)", type(exc).__name__
                    )

            # 2. Clean finished worker references
            for acc_key, proc in list(self.workers.items()):
                if proc.returncode is not None:
                    del self.workers[acc_key]

            # 3. Auto-start check if configured
            if self.settings.auto_start and not held_window(self.maintenance_file):
                max_active = self.registry.value("max_active_workers") or 3
                for row in self.registry.list():
                    if not self.registry.allowed(row["owner"]):
                        continue
                    if self.active_worker_count() >= max_active:
                        break
                    scoped = self.registry.scoped_settings(row)
                    directory = scoped.runtime_dir
                    acc_key = row["id"]
                    if (directory / "STOP").exists():
                        continue
                    if (directory / "http-session.json").is_file():
                        proc = self.workers.get(acc_key)
                        if not ((proc and proc.returncode is None) or running(directory)):
                            flags = auto_flags(directory)
                            if not any(flags.values()):
                                continue
                            mode = getattr(scoped, "ojol_mode", "otomatis")
                            await self.start_account_worker(
                                account_id=acc_key,
                                mode=mode if flags.get("ojol") else None,
                                auto_start=True,
                                needs_only=not flags.get("ojol"),
                            )

            await asyncio.sleep(2.0)

    async def start(self):
        sock_path = get_socket_path(self.runtime_dir)
        sock_path.unlink(missing_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        self.server = await asyncio.start_unix_server(self._handle_client, path=str(sock_path))
        sock_path.chmod(0o600)
        self.tasks.append(asyncio.create_task(self._supervise_loop()))
        print(f"🚀 Worker service running on Unix socket: {sock_path}", flush=True)

    async def close(self):
        self.closing = True
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            get_socket_path(self.runtime_dir).unlink(missing_ok=True)

        # On worker container shutdown, stop child workers cleanly
        for acc_key, proc in list(self.workers.items()):
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()


def main():
    try:
        settings = load_settings()
    except ValueError:
        raise SystemExit("Konfigurasi tidak valid; periksa file env.") from None

    service = WorkerService(settings)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(service.close()))
        except NotImplementedError:
            pass

    async def run():
        await service.start()
        try:
            while not service.closing:
                await asyncio.sleep(1.0)
        finally:
            await service.close()

    try:
        loop.run_until_complete(run())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
