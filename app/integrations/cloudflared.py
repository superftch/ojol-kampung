"""Lifecycle of the locally owned Cloudflared connector."""

import asyncio
import shutil
from contextlib import suppress
from pathlib import Path


class CloudflaredTunnel:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def start(self, *, enabled: bool, token_file: Path) -> None:
        async with self._lock:
            if not enabled or self.is_alive():
                return
            if not Path("/.dockerenv").is_file():
                raise RuntimeError("Tunnel terkelola hanya boleh dijalankan dalam container Docker")
            binary = shutil.which("cloudflared")
            if not binary or not token_file.is_file() or not token_file.stat().st_size:
                raise RuntimeError(
                    "Binary cloudflared atau secret cloudflared_token tidak tersedia"
                )
            # Keep credentials out of argv/environment; Docker rotates connector stdout.
            self.process = await asyncio.create_subprocess_exec(
                binary,
                "tunnel",
                "--no-autoupdate",
                "--metrics",
                "127.0.0.1:2000",
                "run",
                "--token-file",
                str(token_file),
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )

    def take_exit(self) -> int | None:
        process = self.process
        if self._lock.locked() or process is None or process.returncode is None:
            return None
        self.process = None
        return process.returncode

    async def close(self) -> None:
        async with self._lock:
            process = self.process
            if process is None:
                return
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 10)
                except TimeoutError:
                    with suppress(ProcessLookupError):
                        process.kill()
                    await process.wait()
            self.process = None
