"""ADK -> Ojol HTTP MCP, with lazy Browser Harness fallback for reads only."""

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from uuid import uuid4

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .http_api import HttpCoreError
from .mcp_browser import McpBrowser
from .models import Product, Snapshot
from .session_transfer import parse_cookie_input
from .ui import GameUI

HTTP_TOOLS = {"ojol_snapshot", "ojol_preview_shop", "ojol_purchase", "ojol_job_action"}


async def install_browser_session(browser, session_file):
    cookies = parse_cookie_input(session_file.read_text())["cookies"]
    await browser.open_owned_tab(prepare_session=True)
    await browser.call("browser_cdp", method="Network.setCookies", params={"cookies": cookies})
    await browser.call("browser_goto", url="https://www.kampungsebelah.com/kampung")
    await browser.wait_ready()


class HttpUI:
    def __init__(self, settings, context=None, session_file=None):
        self.settings, self.context = settings, context
        self.session_file = session_file or settings.runtime_dir / "http-session.json"
        self.browser = self
        self.check_cancel = lambda: None
        self.on_recovery = lambda event, **data: None
        self.recover_browser = None
        self.fallback = None
        self.stack = AsyncExitStack()
        self.request_id = None
        self.connected = False

    @property
    def tab_id(self):
        return self.fallback.browser.tab_id if self.fallback else None

    @property
    def core_name(self):
        return "browser_fallback" if self.fallback else "http_mcp"

    async def __aenter__(self):
        env = {
            key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "LANG") if key in os.environ
        }
        env.update(
            OJOL_ENV=self.settings.env,
            OJOL_HTTP_RUNTIME_DIR=str(self.settings.runtime_dir),
            OJOL_HTTP_SESSION_FILE=str(self.session_file),
        )
        self.toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=sys.executable, args=["-m", "ojol.http_server"], env=env
                ),
                timeout=35,
            ),
            tool_filter=list(HTTP_TOOLS),
        )
        try:
            self.tools = {tool.name: tool for tool in await self.toolset.get_tools()}
            if set(self.tools) != HTTP_TOOLS:
                raise HttpCoreError("Tool MCP Ojol tidak lengkap")
            self.connected = True
            return self
        except BaseException as exc:
            await self.toolset.close()
            if not isinstance(exc, Exception):
                raise
            self.tools = {}
            return self

    async def __aexit__(self, *args):
        try:
            await self.stack.aclose()
        finally:
            if self.connected:
                await self.toolset.close()

    async def open_owned_tab(self, **kwargs):
        self.check_cancel()

    async def call_tool(self, name, **args):
        self.check_cancel()
        read = name in {"ojol_snapshot", "ojol_preview_shop"}
        if name not in self.tools:
            raise HttpCoreError(
                "Server MCP HTTP belum tersedia", category="transport", recoverable=read
            )
        try:
            task = asyncio.create_task(
                self.tools[name].run_async(args=args, tool_context=self.context)
            )
            try:
                async with asyncio.timeout(40):
                    while not task.done():
                        self.check_cancel()
                        await asyncio.wait({task}, timeout=0.25)
                    raw = await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        except TimeoutError:
            raise HttpCoreError(
                "Panggilan MCP HTTP timeout; klik transaksi tidak diulang",
                category="transport" if read else "uncertain",
                recoverable=read,
            ) from None
        self.check_cancel()
        try:
            data = json.loads(
                "".join(
                    item.get("text", "")
                    for item in raw.get("content", [])
                    if item.get("type") == "text"
                )
            )
            if data["ok"] is not True:
                raise HttpCoreError(
                    data["error"], category=data["category"], recoverable=data["recoverable"]
                )
            if data.get("read_retries"):
                self.on_recovery("http_read_recovered", retries=data["read_retries"], tool=name)
            return data["data"]
        except (ValueError, KeyError, AttributeError, TypeError):
            raise HttpCoreError("Respons MCP HTTP tidak valid", recoverable=read) from None

    async def activate_fallback(self, error):
        self.check_cancel()
        if (
            not error.recoverable
            or not self.settings.browser_fallback
            or self.recover_browser is None
        ):
            raise error
        self.on_recovery("core_browser_fallback", reason=error.category)
        await self.recover_browser()
        self.check_cancel()
        browser = await self.stack.enter_async_context(
            McpBrowser(
                self.settings.runtime_dir / "harness",
                self.context,
                self.settings.cdp_url,
                allow_session_transfer=True,
            )
        )
        browser.check_cancel = lambda: self.check_cancel()
        browser.on_recovery = lambda event, **data: self.on_recovery(event, **data)
        browser.recover_browser = self.recover_browser
        await install_browser_session(browser, self.session_file)
        await browser.call(
            "browser_cdp", method="Emulation.setFocusEmulationEnabled", params={"enabled": True}
        )
        self.fallback = GameUI(browser, lambda: self.check_cancel())

    async def snapshot(self):
        if not self.fallback:
            try:
                return Snapshot.model_validate(await self.call_tool("ojol_snapshot"))
            except HttpCoreError as exc:
                await self.activate_fallback(exc)
        return await self.fallback.snapshot()

    async def work(self):
        self.check_cancel()
        if self.fallback:
            await self.fallback.work()

    async def open_shop(self, resource):
        if not self.fallback:
            try:
                data = await self.call_tool("ojol_preview_shop", resource=resource)
                self.last_navigation = data["navigation"]
                return data["name"], [Product.model_validate(p) for p in data["products"]]
            except HttpCoreError as exc:
                await self.activate_fallback(exc)
        result = await self.fallback.open_shop(resource)
        self.last_navigation = self.fallback.last_navigation
        return result

    def prepare_action(self, kind):
        self.request_id = str(uuid4())
        return {"request_id": self.request_id, "core": self.core_name}

    async def buy(self, product, expected_wallet, min_balance=20):
        if self.fallback:
            return await self.fallback.buy(product, expected_wallet, min_balance)
        return await self.call_tool(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            expected_wallet=str(expected_wallet),
            min_balance=str(min_balance),
            request_id=self.request_id,
        )

    async def job_click(self, label):
        if self.fallback:
            return await self.fallback.job_click(label)
        kind = (
            "search"
            if label == "📲 Cari order"
            else "complete"
            if label == "✅ Sampai! Terima ongkos"
            else None
        )
        if kind is None:
            raise HttpCoreError("Aksi HTTP tidak dikenal", category="blocked")
        return await self.call_tool("ojol_job_action", kind=kind)

    async def call(self, name, **args):
        if name != "browser_cdp" or args.get("method") != "Emulation.setFocusEmulationEnabled":
            raise HttpCoreError("Operasi browser di luar izin core HTTP", category="blocked")
        if self.fallback:
            return await self.fallback.browser.call(name, **args)

    async def reset_focus(self):
        if self.fallback:
            await self.fallback.browser.reset_focus()
