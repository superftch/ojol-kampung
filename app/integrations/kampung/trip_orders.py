"""Read the current trip and select orders through an active game session."""

from __future__ import annotations

import asyncio
import contextlib
import random
from typing import TYPE_CHECKING

from app.core.exceptions import HttpCoreError
from app.core.models import Snapshot
from app.integrations.kampung.game_parsers import RESOURCES, integer
from app.modules.worker.settings import auto_flags

if TYPE_CHECKING:
    from app.integrations.kampung.http_api import OjolHttpApi


class TripOrders:
    def __init__(self, api: OjolHttpApi) -> None:
        self.api = api

    async def raw_trip(self):
        raw = await self.api.request("/api/ojol")
        return (raw.get("ojol") or {}).get("trip") or raw.get("trip")

    async def search(self, state: Snapshot, mode: str):
        if getattr(state, "ojol_resting", False):
            raise HttpCoreError("Mitra ojol sedang wajib istirahat", category="rejected")
        if not auto_flags(self.api.directory)["ojol"]:
            raise HttpCoreError(
                "Auto Ojol dinonaktifkan sebelum mencari order", category="auto_disabled"
            )
        if "📲 Cari order" not in state.buttons:
            raise HttpCoreError("Game belum mengizinkan pencarian order", category="rejected")
        usage = (
            self.api.usage
            if self.api.usage is not None
            else {"bensin": 5, "kendaraan": 2, "kuota": 4}
        )
        if not isinstance(usage, dict) or not all(key in usage for key in RESOURCES):
            raise HttpCoreError("Konsumsi order belum dapat dibaca", category="rejected")
        min_fuel = integer(usage.get("bensinMin", usage.get("bensin", 5)))
        if state.fuel < min_fuel or any(
            state.resource_value(resource) < integer(usage[key])
            for key, resource in (("kendaraan", "condition"), ("kuota", "data"))
        ):
            raise HttpCoreError("Resource kendaraan tidak cukup untuk order", category="rejected")
        effective_mode = mode or getattr(self.api, "ojol_mode", "otomatis")
        tawar_res = await self.api.request(
            "/api/ojol",
            {"action": "tawar", "vehicle": state.ojol_vehicle, "mode": effective_mode},
        )
        pilihan = tawar_res.get("pilihan") if isinstance(tawar_res, dict) else []
        if pilihan:
            wait_mult = getattr(self.api, "minigame_wait_multiplier", 1.0)
            if wait_mult > 0:
                await asyncio.sleep(random.uniform(0.9, 2.3) * wait_mult)  # noqa: S311 - timing only
            chosen = max(
                pilihan,
                key=lambda o: (
                    integer(o.get("fareMilli", 0)),
                    1 if o.get("warga") else 0,
                    -integer(o.get("distance"))
                    if type(o.get("distance")) is int and o.get("distance") >= 0
                    else 0,
                ),
            )
            ambil_payload = {
                "action": "ambil",
                "vehicle": state.ojol_vehicle,
                "pilih": chosen["id"],
            }
            if effective_mode == "kendara":
                ambil_payload["mode"] = "kendara"
            take_res = await self.api.request("/api/ojol", ambil_payload)
            if effective_mode == "kendara":
                trip = (take_res.get("trip") if isinstance(take_res, dict) else None) or chosen
                from_pos = trip.get("from") or {}
                to_pos = trip.get("to") or {}
                if "x" in from_pos and "y" in from_pos:
                    with contextlib.suppress(Exception):
                        await self.api.request(
                            "/api/ojol",
                            {"action": "lacak", "x": from_pos["x"], "y": from_pos["y"]},
                        )
                with contextlib.suppress(Exception):
                    await self.api.request("/api/ojol", {"action": "jemput"})
                if "x" in to_pos and "y" in to_pos:
                    with contextlib.suppress(Exception):
                        await self.api.request(
                            "/api/ojol",
                            {"action": "lacak", "x": to_pos["x"], "y": to_pos["y"]},
                        )
            return take_res
        return await self.api.request(
            "/api/ojol", {"action": "ambil", "vehicle": state.ojol_vehicle}
        )
