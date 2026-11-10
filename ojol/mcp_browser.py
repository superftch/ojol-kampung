import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

TOOLS = [
    "browser_list_tabs",
    "browser_current_tab",
    "browser_new_tab",
    "browser_switch_tab",
    "browser_js",
    "browser_close_tab",
    "browser_cdp",
    "browser_goto",
]


class BrowserError(RuntimeError):
    def __init__(self, message, stage="browser.mcp", operation=None):
        super().__init__(message)
        self.stage, self.operation = stage, operation


class McpBrowser:
    """All Chrome operations use the official Harness MCP server, never a second CDP client."""

    def __init__(
        self,
        home: Path,
        context,
        cdp_url="http://127.0.0.1:9222",
        command=None,
        allow_session_transfer=False,
    ):
        self.context = context
        self.home = home
        self.tab_id = None
        self.session_id = None
        self.session_tab = None
        self.allow_session_transfer = allow_session_transfer
        env = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT", "LANG")
            if key in os.environ
        }
        env.update(
            {
                "BH_HOME": str(home),
                "BU_NAME": "ojol-automation",
                "BU_CDP_URL": cdp_url,
                "BH_RECORD": "0",
                "BH_TELEMETRY": "0",
                "BH_TAB_MARKER": "0",
                "BH_DOMAIN_SKILLS": "0",
            }
        )
        executable = command or shutil.which("browser-harness-mcp")
        self.toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=executable or "uvx",
                    args=[]
                    if executable
                    else ["--from", "browser-harness[mcp]==0.1.13", "browser-harness-mcp"],
                    env=env,
                ),
                timeout=15,
            ),
            tool_filter=TOOLS,
        )

    async def __aenter__(self):
        try:
            self.tools = {tool.name: tool for tool in await self.toolset.get_tools()}
            if set(self.tools) != set(TOOLS):
                raise BrowserError("Tool Browser Harness MCP tidak lengkap")
            return self
        except BaseException as exc:
            await self.toolset.close()
            if isinstance(exc, Exception):
                raise BrowserError(
                    "Inisialisasi Browser Harness MCP gagal: " + type(exc).__name__,
                    stage="mcp.connect",
                ) from None
            raise

    async def __aexit__(self, *args):
        await self.toolset.close()

    async def call(self, name, **args):
        if name not in TOOLS:
            raise BrowserError("Tool di luar allowlist")
        if name == "browser_js" and (not self.tab_id or args.get("target_id") != self.tab_id):
            raise BrowserError("Operasi DOM wajib ditujukan ke tab automation milik sendiri")
        if name in {"browser_switch_tab", "browser_close_tab"} and (
            not self.tab_id or args.get("target") != self.tab_id
        ):
            raise BrowserError("Tab pengguna lain tidak boleh dikendalikan")
        if name == "browser_cdp":
            method, params = args.get("method"), args.get("params", {})
            permitted = (
                method == "Emulation.setFocusEmulationEnabled"
                and self.session_id
                and self.session_tab == self.tab_id
                and set(params) == {"enabled"}
                and isinstance(params.get("enabled"), bool)
            )
            if permitted:
                args = {
                    **args,
                    "params": {
                        **params,
                        "session_id": self.session_id,
                        "_response_timeout": 15,
                    },
                }
            if method == "Runtime.evaluate":
                permitted = (
                    self.session_id
                    and self.session_tab == self.tab_id
                    and params.get("session_id") == self.session_id
                    and set(params)
                    == {
                        "session_id",
                        "expression",
                        "returnByValue",
                        "awaitPromise",
                        "_response_timeout",
                    }
                    and isinstance(params["expression"], str)
                    and params["returnByValue"] is True
                    and params["awaitPromise"] is False
                    and params["_response_timeout"] == 15
                )
            if method == "Page.reload":
                permitted = (
                    self.session_id
                    and self.session_tab == self.tab_id
                    and params.get("session_id") == self.session_id
                    and set(params) == {"session_id", "ignoreCache", "_response_timeout"}
                    and params["ignoreCache"] is True
                    and params["_response_timeout"] == 15
                )
            if self.allow_session_transfer:
                if method == "Network.getCookies":
                    permitted = params == {"urls": ["https://www.kampungsebelah.com/kampung"]}
                elif method == "Network.setCookies":
                    cookies = params.get("cookies", [])
                    permitted = (
                        set(params) == {"cookies"}
                        and bool(cookies)
                        and all(
                            cookie.get("domain", "").lstrip(".")
                            in {"kampungsebelah.com", "www.kampungsebelah.com"}
                            and not cookie.get("url")
                            and cookie.get("path", "/").startswith("/")
                            for cookie in cookies
                        )
                    )
            if not self.tab_id or not permitted:
                raise BrowserError("Metode CDP atau domain di luar izin tab/session transfer")
        # Mutation timeouts are ambiguous: never replay a purchase or trip click.
        try:
            raw = await asyncio.wait_for(
                self.tools[name].run_async(args=args, tool_context=self.context), 20
            )
        except TimeoutError:
            raise BrowserError(
                "MCP timeout; hasil belum pasti. Automation berhenti tanpa mengulang klik.",
                stage=f"mcp.{name}",
                operation=name,
            ) from None
        if not isinstance(raw, dict) or raw.get("isError") or raw.get("is_error"):
            raise BrowserError("MCP gagal")
        try:
            data = json.loads(
                "".join(
                    item.get("text", "")
                    for item in raw.get("content", [])
                    if item.get("type") == "text"
                )
            )
        except (ValueError, TypeError):
            raise BrowserError("Respons MCP tidak valid") from None
        if isinstance(data, dict) and data.get("error"):
            message = str(data["error"]).split("; expression:", 1)[0][:300]
            raise BrowserError(message, stage=f"mcp.{name}", operation=name)
        return data

    async def reset_focus(self):
        primary = sys.exception()
        try:
            await self.call(
                "browser_cdp",
                method="Emulation.setFocusEmulationEnabled",
                params={"enabled": False},
            )
        except Exception as cleanup:
            if primary is None:
                raise
            # Preserve the actual failed action instead of replacing it with a cleanup timeout.
            primary.add_note(f"Focus cleanup also failed: {type(cleanup).__name__}")

    async def open_owned_tab(self, prepare_session=False, refresh=False):
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = self.home / "owned-tab.json"
        tabs = await self.call("browser_list_tabs")
        if marker.is_file():
            saved = json.loads(marker.read_text())
            match = next(
                (tab for tab in tabs if tab.get("targetId") == saved.get("target_id")), None
            )
            if match and match.get("url", "").startswith("https://www.kampungsebelah.com/kampung"):
                self.tab_id = match["targetId"]
                if prepare_session:
                    await self.call("browser_close_tab", target=self.tab_id)
                else:
                    await self.bind_session()
                    if refresh:
                        await self.refresh_owned_tab()
                    return self.tab_id
        # about:blank forces Harness to create a new background target; it cannot reuse a user's blank tab.
        created = await self.call("browser_new_tab", url="about:blank")
        self.tab_id = created.get("targetId")
        if not self.tab_id or any(tab.get("targetId") == self.tab_id for tab in tabs):
            raise BrowserError("Gagal membuat tab khusus; tab pengguna tidak akan digunakan")
        marker.write_text(json.dumps({"target_id": self.tab_id}))
        marker.chmod(0o600)
        await self.bind_session()
        if prepare_session:
            return self.tab_id
        await self.call("browser_goto", url="https://www.kampungsebelah.com/kampung")
        return await self.wait_ready()

    async def refresh_owned_tab(self):
        previous_origin = await self.js("performance.timeOrigin")
        if isinstance(previous_origin, bool) or not isinstance(previous_origin, (int, float)):
            raise BrowserError("Identitas dokumen tab automation tidak terbaca")
        await self.call(
            "browser_cdp",
            method="Page.reload",
            params={
                "session_id": self.session_id,
                "ignoreCache": True,
                "_response_timeout": 15,
            },
        )
        return await self.wait_ready(previous_origin)

    async def wait_ready(self, previous_origin=None):
        ready = (
            "document.readyState === 'complete' && "
            "(!/^\\/kampung(?:\\/|$)/.test(location.pathname) || "
            "!!document.querySelector('[data-tour=\"nav-kerja\"]'))"
        )
        if previous_origin is not None:
            # A slow reload can leave the old document complete until the response arrives.
            ready = f"performance.timeOrigin !== {json.dumps(previous_origin)} && ({ready})"
        await self.call(
            "browser_cdp", method="Emulation.setFocusEmulationEnabled", params={"enabled": True}
        )
        try:
            async with asyncio.timeout(30):
                for _ in range(60):
                    await asyncio.sleep(0.5)
                    try:
                        if await self.js(ready, require_game=False):
                            return self.tab_id
                    except BrowserError as exc:
                        if (
                            exc.operation not in {"browser_js", "browser_cdp"}
                            or "timed out" not in str(exc).lower()
                        ):
                            raise
                        # Readiness is read-only; navigation and all gameplay mutations are never replayed.
        except TimeoutError:
            raise BrowserError(
                "Halaman tab automation belum siap setelah 30 detik", stage="browser.page_load"
            ) from None
        finally:
            await self.reset_focus()
        raise BrowserError("Halaman tab automation belum selesai dimuat")

    async def js(self, expression: str, require_game=True):
        if not self.tab_id or not self.session_id or self.session_tab != self.tab_id:
            raise BrowserError("Tab automation belum tersedia")
        if require_game:
            expression = (
                "(() => { if(location.origin!=='https://www.kampungsebelah.com' || !/^\\/kampung(?:\\/|$)/.test(location.pathname)) return {error:'Sesi login berakhir / halaman berubah. Gunakan tombol Import Cookie di Telegram.'}; return ("
                + expression
                + "); })()"
            )
        # Pinned Harness browser_js attaches/detaches on every call and hard-codes a 5s IPC deadline.
        # Its raw MCP tool supports a longer IPC deadline and an explicit owned CDP session.
        result = await self.call(
            "browser_cdp",
            method="Runtime.evaluate",
            params={
                "session_id": self.session_id,
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": False,
                "_response_timeout": 15,
            },
        )
        if result.get("exceptionDetails") or result.get("result", {}).get("subtype") == "error":
            raise BrowserError(
                "Evaluasi kontrol UI gagal", stage="mcp.Runtime.evaluate", operation="browser_cdp"
            )
        value = result.get("result", {}).get("value")
        if isinstance(value, dict) and value.get("error"):
            raise BrowserError(
                str(value["error"])[:300], stage="browser.ui", operation="browser_cdp"
            )
        return value

    async def bind_session(self):
        result = await self.call("browser_switch_tab", target=self.tab_id)
        self.session_id = result.get("sessionId")
        self.session_tab = self.tab_id if self.session_id else None
        if not self.session_id:
            raise BrowserError("Sesi tab automation tidak tersedia")
