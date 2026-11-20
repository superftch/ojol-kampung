import json
from pathlib import Path

import httpx

from ojol.healing import write_private
from ojol.http_api import ORIGIN, OjolHttpApi, ensure_browser_identity


def test_browser_identity_creation_and_persistence(tmp_path):
    account_dir = tmp_path / "account_1"
    identity_file = account_dir / "browser-identity.json"

    assert not identity_file.exists()
    api1 = OjolHttpApi(account_dir)
    assert identity_file.is_file()

    saved_data = json.loads(identity_file.read_text())
    assert saved_data["user_agent"] == api1.browser_identity["user_agent"]
    assert "sec_ch_ua" in saved_data
    assert "sec_ch_ua_platform" in saved_data
    assert "sec_ch_ua_mobile" in saved_data

    # Re-instantiating must load the exact same identity
    api2 = OjolHttpApi(account_dir)
    assert api2.browser_identity == api1.browser_identity


def test_browser_identity_custom_profile_honored(tmp_path):
    account_dir = tmp_path / "account_custom"
    account_dir.mkdir(parents=True)
    custom_profile = {
        "user_agent": "Mozilla/5.0 (CustomBrowser/1.0)",
        "sec_ch_ua": '"CustomBrowser";v="1"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"CustomOS"',
    }
    write_private(account_dir / "browser-identity.json", custom_profile)

    api = OjolHttpApi(account_dir)
    assert api.browser_identity["user_agent"] == "Mozilla/5.0 (CustomBrowser/1.0)"
    assert api.browser_identity["sec_ch_ua_platform"] == '"CustomOS"'


def test_ensure_browser_identity_deterministic_fallback():
    # If a path cannot be written, deterministic fallback still returns consistent identity
    path = Path("/nonexistent/readonly/path/test_account")
    ident1 = ensure_browser_identity(path)
    ident2 = ensure_browser_identity(path)
    assert ident1 == ident2
    assert "user_agent" in ident1


def test_browser_headers_static_and_dynamic_variation(tmp_path):
    account_dir = tmp_path / "account_headers"
    api = OjolHttpApi(account_dir)

    static_ua = api.browser_identity["user_agent"]
    static_ch_ua = api.browser_identity["sec_ch_ua"]
    static_platform = api.browser_identity["sec_ch_ua_platform"]

    accept_headers = set()
    lang_headers = set()

    for _ in range(50):
        headers = api.browser_headers("/api/ojol")
        # Static identity MUST NEVER change
        assert headers["User-Agent"] == static_ua
        assert headers["sec-ch-ua"] == static_ch_ua
        assert headers["sec-ch-ua-platform"] == static_platform
        assert headers["Origin"] == ORIGIN
        assert headers["Referer"] == f"{ORIGIN}/kampung"

        accept_headers.add(headers["Accept"])
        lang_headers.add(headers["Accept-Language"])

    # Headers must stay consistent across requests within the same session
    assert len(accept_headers) == 1
    assert len(lang_headers) == 1


def test_browser_headers_endpoint_specific(tmp_path):
    api = OjolHttpApi(tmp_path / "account_endpoints")

    html_headers = api.browser_headers("/kampung")
    assert "text/html" in html_headers["Accept"]
    assert html_headers["Sec-Fetch-Dest"] == "document"
    assert html_headers["Sec-Fetch-Mode"] == "navigate"
    assert "Priority" not in html_headers

    script_headers = api.browser_headers("/_next/static/chunks/app.js")
    assert script_headers["Accept"] == "*/*"
    assert script_headers["Sec-Fetch-Dest"] == "script"
    assert script_headers["Sec-Fetch-Mode"] == "no-cors"
    assert "Priority" not in script_headers

    api_headers = api.browser_headers("/api/game/me")
    assert api_headers["Sec-Fetch-Dest"] == "empty"
    assert api_headers["Sec-Fetch-Mode"] == "cors"
    assert "Priority" in api_headers


async def test_request_sends_browser_headers_and_keeps_static_ua(tmp_path):
    account_dir = tmp_path / "account_req"
    requests_captured = []

    def handle(request):
        requests_captured.append(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(base_url=ORIGIN, transport=httpx.MockTransport(handle))
    api = OjolHttpApi(account_dir, client=client)

    # Perform multiple requests to allowed endpoints
    await api.request("/api/time")
    await api.request("/api/realtime/token")
    await api.request("/api/time")

    assert len(requests_captured) == 3

    static_ua = api.browser_identity["user_agent"]
    static_ch = api.browser_identity["sec_ch_ua"]

    for req in requests_captured:
        assert req.headers["User-Agent"] == static_ua
        assert req.headers["sec-ch-ua"] == static_ch
        assert req.headers["Sec-Fetch-Site"] == "same-origin"
        assert req.headers["Origin"] == ORIGIN
        assert req.headers["Referer"] == f"{ORIGIN}/kampung"
        assert "Accept" in req.headers
        assert "Accept-Language" in req.headers
        assert "Priority" in req.headers
