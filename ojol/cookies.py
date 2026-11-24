"""Game session cookie validation, parsing, and expiry checks."""

import json
import math
import time
from typing import Any

COOKIE_NAME = "__Secure-better-auth.session_token"
DOMAIN = "www.kampungsebelah.com"


def parse_cookie_input(value: str) -> dict[str, list[dict[str, Any]]]:
    """Parse raw cookie token or JSON session payload into normalized cookie dict."""
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


def session_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a single KampungSebelah session cookie dictionary."""
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
    expires = cookie.get("expires")
    valid_expiry = type(expires) is int or (type(expires) is float and math.isfinite(expires))
    if valid_expiry and expires > 0:
        result["expires"] = cookie["expires"]
    return result


def session_expired(payload: dict[str, Any]) -> bool:
    """Return True if the cookie payload includes an expiry timestamp in the past."""
    expires = payload["cookies"][0].get("expires")
    return expires is not None and expires <= time.time()
