"""HTTP adapter for the controller. Reads may retry; transactions are never replayed."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from .http_api import HttpCoreError, OjolHttpApi
from .identity import save_profile, verified_profile
from .models import Product, ShopPreview, Snapshot

HTTP_TOOLS = {"ojol_snapshot", "ojol_preview_shop", "ojol_purchase", "ojol_job_action"}


class HttpUI:
    def __init__(self, settings, api=None, session_file=None):
        self.settings = settings
        self.session_file = session_file or settings.runtime_dir / "http-session.json"
        self.api = api or OjolHttpApi(settings.runtime_dir, self.session_file)
        self.check_cancel = lambda: None
        self.on_recovery = lambda event, **data: None
        self.request_id = None
        self.tools = {
            "ojol_snapshot": SimpleNamespace(run_async=self._run_snapshot),
            "ojol_preview_shop": SimpleNamespace(run_async=self._run_preview),
            "ojol_purchase": SimpleNamespace(run_async=self._run_purchase),
            "ojol_job_action": SimpleNamespace(run_async=self._run_job_action),
        }

    async def __aenter__(self):
        # Sesi dibuka malas: error env testing/auth harus muncul sebelum HTTP dibuka.
        if self.api.client is None and self.session_file.exists():
            await self.api.__aenter__()
        return self

    async def __aexit__(self, *args):
        return None

    async def call_tool(self, name, **args):
        """Route a tool name to the adapter method, honouring stop between steps."""
        self.check_cancel()
        task = asyncio.create_task(self._call_tool(name, **args))
        try:
            while not task.done():
                self.check_cancel()
                await asyncio.wait({task}, timeout=0.25)
            return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def _call_tool(self, name, **args):
        runner = self.tools.get(name)
        if runner is None:
            raise HttpCoreError(f"Tool Ojol tidak dikenal: {name}", category="blocked")
        return await runner.run_async(**args)

    async def _run_snapshot(self):
        if getattr(self.api, "client", "missing") is None:
            if self.settings.env == "testing" and isinstance(self.api, OjolHttpApi):
                raise HttpCoreError("Snapshot testing tidak membuka HTTP live")
            await self.api.__aenter__()
        return await self.api.snapshot()

    async def _run_preview(self, resource):
        return await self.api.preview(resource)

    async def _run_purchase(self, **args):
        self.request_id = args.pop("request_id", self.request_id)
        return await self.buy(
            Product.model_validate(args["product"]),
            args["expected_wallet"],
            args["expected_resource"],
            args["min_balance"],
        )

    async def _run_job_action(self, kind, mode=None):
        mode = mode or getattr(self.settings, "ojol_mode", "kendara")
        return await self.api.job_action(kind, mode=mode)

    async def snapshot(self):
        state = Snapshot.model_validate(await self.call_tool("ojol_snapshot"))
        # The HTTP server used to persist the verified nickname; keep it per read.
        me = getattr(self.api, "me", None)
        if isinstance(me, dict) and (me.get("profile") or {}).get("nickname") is not None:
            save_profile(self.settings.runtime_dir, verified_profile(me))
        return state

    async def daily_wallet(self, day):
        return await self.api.daily_wallet(day.isoformat())

    async def ensure_bpjs(self):
        return await self.api.ensure_bpjs()

    async def garden_status(self):
        return await self.api.garden_status()

    async def garden_action(self, garden_id: str, action: str):
        return await self.api.garden_action(garden_id, action)

    async def study_status(self, mode):
        return await self.api.study_status(mode)

    async def study_start(self, mode, track, expected_price, expected_wallet, min_balance):
        return await self.api.study_start(
            mode,
            track,
            str(expected_price),
            str(expected_wallet),
            str(min_balance),
            self.request_id,
        )

    async def study_quiz(self, mode, visit_id, track):
        return await self.api.study_quiz(mode, visit_id, track)

    async def preview_shops(self, resource):
        data = await self.api.preview(resource)
        self.last_navigation = data["navigation"]
        return [ShopPreview.model_validate(shop) for shop in data["shops"]]

    def prepare_action(self, kind):
        self.request_id = str(uuid4())
        return {"request_id": self.request_id}

    async def buy(self, product, expected_wallet, expected_resource, min_balance=5):
        return await self.api.purchase(
            product.model_dump(mode="json"),
            str(expected_wallet),
            expected_resource,
            str(min_balance),
            self.request_id,
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
        mode = getattr(self.settings, "ojol_mode", "kendara")
        return await self.call_tool("ojol_job_action", kind=kind, mode=mode)
