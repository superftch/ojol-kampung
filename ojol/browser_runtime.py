"""Own Chromium processes inside Docker. Automation still uses Harness MCP only."""

import asyncio
import fcntl
import json
import os
import shutil
import signal
from pathlib import Path


class BrowserRuntime:
    def __init__(self, settings):
        if not settings.managed_browser or not Path("/.dockerenv").is_file():
            raise RuntimeError("Browser terkelola hanya boleh dijalankan dalam container Docker")
        self.directory = settings.runtime_dir
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lease = (self.directory / "browser-runtime.lock").open("a")
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lease.close()
            raise RuntimeError(
                "Browser Docker untuk volume ini sudah dikelola proses lain"
            ) from None
        self.profile = self.directory / "chrome-profile"
        self.mode = None
        self.process = None

    async def spawn(self, *args, env=None):
        return await asyncio.create_subprocess_exec(
            *args,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )

    async def terminate(self, process):
        if process and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(process.wait(), 10)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()

    async def close(self):
        await self.terminate(self.process)
        self.process = None
        self.mode = None

    def alive(self):
        return bool(self.process and self.process.returncode is None)

    async def switch(self, mode):
        if mode != "headless":
            raise ValueError("Mode browser tidak dikenal")
        if self.mode == mode and self.alive():
            return
        await self.close()
        self.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Exclusive volume lease and stopped owned process make crash/recreate locks safe to remove.
        for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            (self.profile / name).unlink(missing_ok=True)
        preferences = self.profile / "Default/Preferences"
        if not preferences.exists():
            preferences.parent.mkdir(parents=True, exist_ok=True)
            preferences.write_text(
                json.dumps(
                    {
                        "credentials_enable_service": False,
                        "profile": {"password_manager_enabled": False},
                    }
                )
            )
        chrome = shutil.which("chromium")
        if not chrome:
            raise RuntimeError("Chromium tidak terpasang dalam image")
        args = [
            chrome,
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=9222",
            f"--user-data-dir={self.profile}",
            "--window-size=960,640",
            "--use-gl=angle",
            "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader",
        ]
        args.append("--headless=new")
        # Harness owns the game tab; a second 3D world wastes CPU and can stall DOM reads.
        self.process = await self.spawn(*args, "about:blank")
        self.mode = mode
        for _ in range(60):
            if self.process.returncode is not None:
                raise RuntimeError("Chromium berhenti saat startup")
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", 9222)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.25)
        raise RuntimeError("Port Chrome belum siap setelah 15 detik")
