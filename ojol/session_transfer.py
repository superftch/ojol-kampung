"""Validate and atomically install an account session through HTTP MCP."""

import asyncio
import json
import sys

from .cli import exclusive_lock
from .config import load_settings
from .healing import write_private
from .telegram import flush_notices, queue_notice

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


async def import_session(settings, payload):
    global STAGE
    STAGE = "session.import.validate"
    if settings.env == "testing":
        raise ValueError("Import sesi live diblokir dalam testing")
    data = json.loads(payload)
    if set(data) != {"cookies"} or len(data["cookies"]) != 1:
        raise ValueError("Hanya satu cookie sesi game diizinkan")
    cookies = [session_cookie(item) for item in data["cookies"]]
    from .http_core import HttpUI

    candidate = settings.runtime_dir / "http-session.pending.json"
    with exclusive_lock(settings.runtime_dir):
        write_private(candidate, {"cookies": cookies})
        try:
            STAGE = "session.import.http_verify"
            async with HttpUI(settings, session_file=candidate) as core:
                await core.snapshot()
            candidate.replace(settings.runtime_dir / "http-session.json")
        finally:
            candidate.unlink(missing_ok=True)
    queue_notice(
        settings,
        "✅ Cookie berhasil diimpor\n\nSesi game sudah dicek dan siap dipakai.\n👉 Tekan Jalankan Ojol.",
    )
    await flush_notices(settings)


def main():
    try:
        settings = load_settings()
        if settings.env == "testing":
            raise ValueError("Transfer sesi live dilarang dalam testing")
        if sys.argv[1:] == ["import"]:
            payload = sys.stdin.buffer.read(16385)
            if len(payload) > 16384:
                raise ValueError("Payload terlalu besar")
            asyncio.run(import_session(settings, payload))
        else:
            raise ValueError("Gunakan import; cookie diterima melalui stdin lokal")
    except Exception as exc:
        print(f"Session transfer stage={STAGE} category={type(exc).__name__}", file=sys.stderr)
        print(
            "Transfer sesi gagal; payload/credential tidak dicetak. Periksa sesi HTTP dan worker yang masih aktif.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
