"""Private recovery IPC and resource evidence; never collect page bodies or credentials."""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4


def write_private(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False))
    temporary.chmod(0o600)
    temporary.replace(path)


def capture_diagnostics(directory, stage, browser_probe=None):
    data = {"time": time.time(), "stage": stage, "browser_probe": browser_probe}
    for name in (
        "cpu.stat",
        "cpu.max",
        "memory.current",
        "memory.max",
        "memory.events",
        "pids.current",
    ):
        path = Path("/sys/fs/cgroup") / name
        if path.is_file():
            data[name] = path.read_text()[:2000]
    processes = []
    for path in Path("/proc").glob("[0-9]*"):
        try:
            if path.joinpath("comm").read_text().strip() != "chromium":
                continue
            stat = path.joinpath("stat").read_text().rsplit(")", 1)[1].split()
            args = path.joinpath("cmdline").read_bytes()
            match = re.search(rb"--type=([a-z-]+)", args)
            kind = match[1].decode() if match else "unknown"
            processes.append(
                {
                    "pid": int(path.name),
                    "state": stat[0],
                    "type": kind
                    if kind in {"renderer", "gpu-process", "zygote", "utility"}
                    else "other",
                    "cpu_ticks": int(stat[11]) + int(stat[12]),
                    "start_ticks": int(stat[19]),
                    "rss_pages": int(stat[21]),
                }
            )
        except (OSError, ValueError, IndexError):
            continue
    data["chromium_processes"] = processes
    target = directory / "diagnostics"
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = target / f"browser-{time.time_ns()}.json"
    write_private(path, data)
    for old in sorted(target.glob("browser-*.json"))[:-20]:
        old.unlink(missing_ok=True)
    return path.name


async def request_browser_restart(settings, check_cancel):
    from .mcp_browser import BrowserError

    if settings.env == "testing" or not settings.managed_browser:
        raise BrowserError(
            "Restart otomatis hanya untuk browser Docker terkelola",
            stage="browser.self_heal",
            operation="browser_cdp",
        )
    request = settings.runtime_dir / "browser-recovery-request.json"
    reply = settings.runtime_dir / "browser-recovery-reply.json"
    identifier = uuid4().hex
    write_private(
        request,
        {"id": identifier, "pid": os.getpid(), "parent_pid": os.getppid(), "created": time.time()},
    )
    try:
        async with asyncio.timeout(45):
            while True:
                check_cancel()
                if reply.is_file():
                    result = json.loads(reply.read_text())
                    if result.get("id") == identifier:
                        reply.unlink(missing_ok=True)
                        if result.get("ok"):
                            return
                        raise BrowserError(
                            "Restart browser ditolak/gagal oleh controller",
                            stage="browser.self_heal",
                            operation="browser_cdp",
                        )
                await asyncio.sleep(0.25)
    except TimeoutError:
        raise BrowserError(
            "Controller tidak membalas recovery dalam 45 detik",
            stage="browser.self_heal",
            operation="browser_cdp",
        ) from None
    finally:
        try:
            if json.loads(request.read_text()).get("id") == identifier:
                request.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
