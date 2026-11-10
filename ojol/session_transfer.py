"""Explicit local-only transfer of the game's session cookie via Harness MCP."""

import asyncio
import json
import sys
from pathlib import Path

from .cli import exclusive_lock
from .config import load_settings
from .mcp_browser import McpBrowser
from .telegram import flush_notices, queue_notice
from .ui import GameUI

COOKIE_NAME = "__Secure-better-auth.session_token"
DOMAIN = "www.kampungsebelah.com"
STAGE = "session.start"


def parse_cookie_input(value):
    value = value.strip()
    if not value or len(value) > 12000:
        raise ValueError("Cookie tidak valid")
    if value.startswith(("[", "{")):
        data = json.loads(value)
        cookies = data.get("cookies", [data]) if isinstance(data, dict) else data
        selected = [
            item for item in cookies if isinstance(item, dict) and item.get("name") == COOKIE_NAME
        ]
        if len(selected) != 1:
            raise ValueError("Hanya satu cookie sesi game diizinkan")
        cookie = session_cookie(selected[0])
    else:
        value = value.removeprefix(COOKIE_NAME + "=")
        if any(char.isspace() or char in ";<>" for char in value):
            raise ValueError("Masukkan nilai cookie sesi saja")
        cookie = session_cookie(
            {
                "name": COOKIE_NAME,
                "value": value,
                "domain": DOMAIN,
                "path": "/",
                "secure": True,
                "httpOnly": True,
            }
        )
    return {"cookies": [cookie]}


def session_cookie(cookie):
    if (
        cookie.get("name") != COOKIE_NAME
        or cookie.get("domain") != DOMAIN
        or cookie.get("path") != "/"
        or cookie.get("secure") is not True
        or cookie.get("httpOnly") is not True
        or not isinstance(cookie.get("value"), str)
        or not cookie["value"]
        or len(cookie["value"]) > 8192
    ):
        raise ValueError("Cookie sesi game tidak valid")
    result = {key: cookie[key] for key in ("name", "value", "domain", "path", "secure", "httpOnly")}
    if cookie.get("sameSite") in {"Strict", "Lax", "None"}:
        result["sameSite"] = cookie["sameSite"]
    if isinstance(cookie.get("expires"), (int, float)) and cookie["expires"] > 0:
        result["expires"] = cookie["expires"]
    return result


async def transfer_to_docker(settings):
    global STAGE
    STAGE = "session.export"
    with exclusive_lock(settings.runtime_dir):
        async with McpBrowser(
            settings.runtime_dir / "harness", None, settings.cdp_url, allow_session_transfer=True
        ) as browser:
            await browser.open_owned_tab()
            data = await browser.call(
                "browser_cdp",
                method="Network.getCookies",
                params={"urls": ["https://www.kampungsebelah.com/kampung"]},
            )
            cookies = [
                session_cookie(item)
                for item in data.get("cookies", [])
                if item.get("name") == COOKIE_NAME
            ]
        if len(cookies) != 1:
            raise ValueError("Sesi game Chrome belum tersedia")
        # Only an anonymous pipe carries credentials; never argv, stdout, file, or Telegram.
        process = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "exec",
            "-T",
            "-u",
            "app",
            "app",
            "python",
            "-m",
            "ojol.session_transfer",
            "import",
            cwd=Path(__file__).resolve().parent.parent,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        STAGE = "session.docker_import"
        output, diagnostic = await process.communicate(json.dumps({"cookies": cookies}).encode())
        if process.returncode:
            # Importer emits only a fixed stage and exception class, never provider text.
            for line in diagnostic.decode().splitlines():
                if line.startswith("Session transfer stage="):
                    print(line[:200], file=sys.stderr)
            raise RuntimeError(
                "Import sesi Docker gagal; tidak mencetak payload atau error provider"
            )
        print(output.decode().strip())


async def import_session(settings, payload):
    global STAGE
    STAGE = "session.import.validate"
    if not settings.managed_browser or not Path("/.dockerenv").is_file():
        raise ValueError("Import hanya dalam browser Docker terkelola")
    data = json.loads(payload)
    if set(data) != {"cookies"} or len(data["cookies"]) != 1:
        raise ValueError("Hanya satu cookie sesi game diizinkan")
    cookies = [session_cookie(item) for item in data["cookies"]]
    with exclusive_lock(settings.runtime_dir):
        async with McpBrowser(
            settings.runtime_dir / "harness", None, settings.cdp_url, allow_session_transfer=True
        ) as browser:
            STAGE = "session.import.open_tab"
            # Install the new session before loading the expensive game world, and never reload an old session.
            await browser.open_owned_tab(prepare_session=True)
            await browser.call(
                "browser_cdp", method="Emulation.setFocusEmulationEnabled", params={"enabled": True}
            )
            try:
                STAGE = "session.import.set_cookie"
                await browser.call(
                    "browser_cdp", method="Network.setCookies", params={"cookies": cookies}
                )
                STAGE = "session.import.reload"
                await browser.call("browser_goto", url="https://www.kampungsebelah.com/kampung")
                STAGE = "session.import.verify_login"
                async with asyncio.timeout(30):
                    for _ in range(40):
                        try:
                            ready = await browser.js(
                                "!!document.querySelector('[data-tour=\"nav-kerja\"]')",
                                require_game=False,
                            )
                        except Exception as exc:
                            if (
                                getattr(exc, "operation", None) not in {"browser_js", "browser_cdp"}
                                or "timed out" not in str(exc).lower()
                            ):
                                raise
                            ready = False
                        if ready:
                            break
                        await asyncio.sleep(0.5)
                    else:
                        raise RuntimeError(
                            "Sesi tidak diterima situs; import cookie sesi yang masih valid"
                        )
                STAGE = "session.import.snapshot"
                snapshot = await GameUI(browser).snapshot()
            finally:
                await browser.call(
                    "browser_cdp",
                    method="Emulation.setFocusEmulationEnabled",
                    params={"enabled": False},
                )
        print(
            json.dumps(
                {
                    "session_imported": True,
                    "phase": snapshot.phase,
                    "fuel": snapshot.fuel,
                    "condition": snapshot.condition,
                    "data": snapshot.data,
                    "wallet": str(snapshot.wallet),
                }
            )
        )
    queue_notice(
        settings,
        "✅ Cookie sesi game berhasil diimpor dan diverifikasi pada browser headless. Tekan Jalankan Ojol untuk melanjutkan.",
    )
    await flush_notices(settings)


def main():
    try:
        settings = load_settings()
        if settings.env == "testing":
            raise ValueError("Transfer sesi live dilarang dalam testing")
        if sys.argv[1:] == ["to-docker"]:
            asyncio.run(transfer_to_docker(settings))
        elif sys.argv[1:] == ["import"]:
            payload = sys.stdin.buffer.read(16385)
            if len(payload) > 16384:
                raise ValueError("Payload terlalu besar")
            asyncio.run(import_session(settings, payload))
        else:
            raise ValueError("Gunakan to-docker pada host; import menerima stdin lokal")
    except Exception as exc:
        print(f"Session transfer stage={STAGE} category={type(exc).__name__}", file=sys.stderr)
        print(
            "Transfer sesi gagal; payload/credential tidak dicetak. Periksa browser, login, dan worker yang masih aktif.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
