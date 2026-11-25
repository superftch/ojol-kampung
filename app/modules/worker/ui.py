"""HTTP adapter for the controller. Reads may retry; transactions are never replayed."""

import asyncio
from collections.abc import Coroutine
from decimal import Decimal
from typing import Any, TypeVar
from uuid import uuid4

from app.core.models import Product, Settings, ShopPreview, Snapshot
from app.integrations.kampung.http_api import HttpCoreError, OjolHttpApi
from app.integrations.kampung.identity import save_profile, verified_profile

T = TypeVar("T")


class HttpUI:
    def __init__(self, settings: Settings, api=None, session_file=None):
        self.settings = settings
        self.session_file = session_file or settings.runtime_dir / "http-session.json"
        self.api = api or OjolHttpApi(settings.runtime_dir, self.session_file)
        self.check_cancel = lambda: None
        self.on_recovery = lambda event, **data: None
        self.request_id = None

    async def __aenter__(self):
        # Sesi dibuka malas: error env testing/auth harus muncul sebelum HTTP dibuka.
        if self.api.client is None and self.session_file.exists():
            await self.api.__aenter__()
        return self

    async def __aexit__(self, *args):
        return None

    async def _wait_for_stop(self, operation: Coroutine[Any, Any, T]) -> T:
        """Cancel an in-flight operation when the worker is stopped."""
        task = asyncio.create_task(operation)
        try:
            while not task.done():
                self.check_cancel()
                await asyncio.wait({task}, timeout=0.25)
            return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def _run_snapshot(self):
        if getattr(self.api, "client", "missing") is None:
            if self.settings.env == "testing" and isinstance(self.api, OjolHttpApi):
                raise HttpCoreError("Snapshot testing tidak membuka HTTP live")
            await self.api.__aenter__()
        return await self.api.snapshot()

    async def snapshot(self) -> Snapshot:
        self.check_cancel()
        state = Snapshot.model_validate(await self._wait_for_stop(self._run_snapshot()))
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

    async def kantor_action(self, action, **fields):
        return await self.api.kantor_action(action, **fields)

    async def kerja_malam_status(self):
        return await self.api.kerja_malam_status()

    async def kerja_malam_action(self, action, **fields):
        return await self.api.kerja_malam_action(action, **fields)

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

    async def preview_shops(self, resource: str) -> list[ShopPreview]:
        data = await self.api.preview(resource)
        self.last_navigation = data["navigation"]
        return [ShopPreview.model_validate(shop) for shop in data["shops"]]

    def prepare_action(self, kind):
        self.request_id = str(uuid4())
        return {"request_id": self.request_id}

    async def buy(
        self,
        product: Product,
        expected_wallet: Decimal,
        expected_resource: int,
        min_balance: Decimal | int = 5,
    ):
        return await self.api.purchase(
            product.model_dump(mode="json"),
            str(expected_wallet),
            expected_resource,
            str(min_balance),
            self.request_id,
        )

    async def job_click(self, label: str):
        kind = (
            "search"
            if label == "📲 Cari order"
            else "complete"
            if label == "✅ Sampai! Terima ongkos"
            else None
        )
        if kind is None:
            raise HttpCoreError("Aksi HTTP tidak dikenal", category="blocked")
        mode = getattr(self.settings, "ojol_mode", "otomatis")
        self.check_cancel()
        return await self._wait_for_stop(self.api.job_action(kind, mode=mode))
