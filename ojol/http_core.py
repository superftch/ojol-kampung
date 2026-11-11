"""ADK -> Ojol HTTP MCP. Reads may retry; transactions are never replayed."""

import asyncio
import json
import os
import sys
from uuid import uuid4

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .http_api import HttpCoreError
from .models import ShopPreview, Snapshot

HTTP_TOOLS = {"ojol_snapshot", "ojol_preview_shop", "ojol_purchase", "ojol_job_action"}


class HttpUI:
    def __init__(self, settings, context=None, session_file=None):
        self.settings, self.context = settings, context
        self.session_file = session_file or settings.runtime_dir / "http-session.json"
        self.check_cancel = lambda: None
        self.on_recovery = lambda event, **data: None
        self.request_id = None
        self.connected = False

    @property
    def core_name(self):
        return "http_mcp"

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
        except BaseException:
            await self.toolset.close()
            raise

    async def __aexit__(self, *args):
        if self.connected:
            await self.toolset.close()

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

    async def snapshot(self):
        return Snapshot.model_validate(await self.call_tool("ojol_snapshot"))

    async def preview_shops(self, resource):
        data = await self.call_tool("ojol_preview_shop", resource=resource)
        self.last_navigation = data["navigation"]
        return [ShopPreview.model_validate(shop) for shop in data["shops"]]

    def prepare_action(self, kind):
        self.request_id = str(uuid4())
        return {"request_id": self.request_id, "core": self.core_name}

    async def buy(self, product, expected_wallet, expected_resource, min_balance=20):
        return await self.call_tool(
            "ojol_purchase",
            product=product.model_dump(mode="json"),
            expected_wallet=str(expected_wallet),
            expected_resource=expected_resource,
            min_balance=str(min_balance),
            request_id=self.request_id,
        )

    async def job_click(self, label):
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
