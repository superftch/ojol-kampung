"""Kampung shop operations using the active game session."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import NAMESPACE_DNS, UUID, uuid5

from app.core.exceptions import HttpCoreError
from app.core.models import (
    NEEDS,
    Product,
    ShopPreview,
    Snapshot,
)
from app.core.storage import write_private
from app.integrations.kampung.game_parsers import (
    CAR_SERVICE,
    CATEGORIES,
    EV_CHARGE,
    ITEMS,
    KAMAR_MANDI_ID,
    ShopClosed,
    coin,
    extract_effects,
    extract_need_effects,
)
from app.integrations.kampung.shop_locations import (
    GYM_FACILITIES_BY_VILLAGE,
    HEALTH_FACILITIES_BY_VILLAGE,
    NEED_SHOP_CATEGORIES,
    NEED_SHOPS_BY_VILLAGE,
    RECREATION_FACILITIES_BY_VILLAGE,
    SHOPS_BY_VILLAGE,
    SPPG_FACILITIES_BY_VILLAGE,
    NeedShop,
    ShopLocation,
)
from app.modules.worker.settings import auto_flags

if TYPE_CHECKING:
    from app.integrations.kampung.http_api import OjolHttpApi


logger = logging.getLogger(__name__)

OJOL_DIRECTORY_RESOURCES = {"condition", "data"}


class ShopWorkflows:
    def __init__(self, api: OjolHttpApi) -> None:
        self.api = api

    async def resource_items(self, resource):
        if self.api.vehicle == "mobil" and resource == "condition":
            return ITEMS[resource] | {CAR_SERVICE}
        if resource == "fuel" and self.api.vehicle == "mobil":
            garage = (await self.api.request("/api/kendaraan")).get("items")
            cars = (
                [row for row in garage if isinstance(row, dict) and row.get("family") == "mobil"]
                if isinstance(garage, list)
                else []
            )
            power = [row.get("listrik") for row in cars]
            if not power or any(type(value) is not bool for value in power) or len(set(power)) != 1:
                raise HttpCoreError(
                    "Jenis tenaga mobil Ojol belum terverifikasi", category="rejected"
                )
            return {EV_CHARGE} if power[0] else ITEMS[resource]
        return ITEMS[resource]

    def ojol_shop_locations(self, resource):
        shops = SHOPS_BY_VILLAGE.get((self.api.home or {}).get("desa"), {})
        locations = tuple(shops.get(resource, ()))
        if resource == "condition" and self.api.vehicle == "mobil":
            locations += tuple(shops.get("fuel", ()))
        return tuple(dict.fromkeys(locations))

    async def effects(self, *, for_needs=False, required_items=()):
        version = getattr(self.api, "config_version", None)
        if version is None:
            await self.api.snapshot()
            version = self.api.config_version
        cache = self.api.directory / "http-effects.json"
        key = "needs_effects" if for_needs else "effects"
        required = set.union(*ITEMS.values()) | {
            item for item in required_items if item != EV_CHARGE
        }
        if cache.is_file():
            data = json.loads(cache.read_text())
            if (
                data.get("version") == version
                and data.get(key)
                and (not for_needs or data.get("needs_schema") == 2)
            ) and (for_needs or required <= data[key].keys()):
                return data[key]
        html = await self.api.request("/kampung", text=True)
        effects = {}
        needs_effects = {}
        for path in re.findall(r"<script[^>]+src=[\"\x27]([^\"\x27]+)", html):
            if not path.startswith("/_next/static/"):
                continue
            source = await self.api.request(path, text=True)
            found = extract_effects(source)
            if any(item in effects and effects[item] != value for item, value in found.items()):
                raise HttpCoreError("Efek produk antar bundle berbeda", recoverable=True)
            effects.update(found)
            found_needs = extract_need_effects(source)
            found_needs.update(extract_need_effects(source, "fasum"))
            if found_needs:
                if any(
                    item in needs_effects and needs_effects[item] != value
                    for item, value in found_needs.items()
                ):
                    raise HttpCoreError("Efek kebutuhan antar bundle berbeda", recoverable=True)
                needs_effects.update(found_needs)
            if required <= effects.keys() and (needs_effects or not for_needs):
                break
        if not required <= effects.keys():
            raise HttpCoreError("Efek produk client belum dapat diverifikasi", recoverable=True)
        write_private(
            cache,
            {
                "version": version,
                "effects": effects,
                "needs_effects": needs_effects,
                "needs_schema": 2,
            },
        )
        if for_needs and not needs_effects:
            raise HttpCoreError("Efek barang kebutuhan belum dapat diverifikasi", recoverable=True)
        return needs_effects if for_needs else effects

    async def products(self, shop_id, resource, effects, allowed_items=None):
        catalog = await self.api.request("/api/shops/" + shop_id)
        if type(catalog.get("mine")) is not bool or type(catalog.get("open")) is not bool:
            raise HttpCoreError("Status atau kepemilikan toko belum dapat diverifikasi")
        if catalog["mine"] or not catalog["open"]:
            return catalog, []
        if resource == "fuel" and isinstance(catalog.get("spbu"), dict):
            return catalog, []
        products = []
        for row in catalog["menu"]:
            item = row["item"]
            sold_out = row.get("habis")
            if resource in NEEDS:
                effect = effects.get(item, {})
                taste = row.get("rasa")
                if isinstance(taste, dict) and "isi" in taste:
                    effect = taste["isi"]
                    if (
                        not isinstance(effect, dict)
                        or not effect
                        or any(
                            key not in NEEDS or type(value) is not int or not 0 <= value <= 100
                            for key, value in effect.items()
                        )
                    ):
                        raise HttpCoreError("Efek selera makanan belum terverifikasi")
                # The shop applies services and consumables with these effects immediately.
                if not effect.get(resource) or not (
                    row.get("service") is True
                    or any(effect.get(need) for need in ("makan", "kesehatan", "rumah"))
                ):
                    continue
                if sold_out is not None and not isinstance(sold_out, (str, bool)):
                    raise HttpCoreError("Status stok produk kebutuhan belum terverifikasi")
                if isinstance(sold_out, str) and sold_out and not sold_out.strip():
                    raise HttpCoreError("Status stok produk kebutuhan belum terverifikasi")
            else:
                if item not in (ITEMS[resource] if allowed_items is None else allowed_items):
                    continue
                effect = effects[item]
                if resource not in effect:
                    raise HttpCoreError("Efek produk tidak sesuai resource", recoverable=True)
            row_data = {"shop": shop_id, "item": item, "resource": resource}
            if (
                resource == "makan"
                and isinstance(row.get("rasa"), dict)
                and row["rasa"].get("bosan") is True
            ):
                row_data["bosan"] = True
            product = Product(
                name=row["name"],
                price=coin(row["priceMilli"]),
                effects=effect,
                row_text=json.dumps(row_data, sort_keys=True),
                enabled=not bool(sold_out),
            )
            products.append(product)
        return catalog, products

    async def preview_shop(self, location, resource, effects, allowed_items):
        try:
            catalog, products = await self.api.products(
                location.id, resource, effects, allowed_items
            )
        except ShopClosed:
            return None
        if catalog.get("plang") and catalog["plang"] != location.name:
            return None
        if not any(product.enabled and product.effects[resource] > 0 for product in products):
            return None
        return ShopPreview(
            id=location.id,
            plot_id=location.plot_id,
            name=location.name,
            category=CATEGORIES[resource],
            distance_squared=(location.x - self.api.home["x"]) ** 2
            + (location.y - self.api.home["y"]) ** 2,
            products=products,
        )

    async def need_shop(self, location, resource, effects):
        try:
            catalog, products = await self.api.products(location.id, resource, effects)
        except ShopClosed:
            return None
        if catalog.get("plang") != location.name:
            raise HttpCoreError("Identitas usaha kebutuhan belum terverifikasi", category="schema")
        if not products:
            return None
        return ShopPreview(
            id=location.id,
            plot_id=location.plot_id,
            name=location.name,
            category=location.category,
            distance_squared=0,
            products=products,
        )

    async def read_previews(self, calls, *, return_exceptions=False):
        tasks = [asyncio.create_task(call) for call in calls]
        try:
            return await asyncio.gather(*tasks, return_exceptions=return_exceptions)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def directory_business(self, row):
        plot, category = row["plotId"], row["item"]
        detail = await self.api.request(f"/api/world/plots/{plot}?t={int(time.time() * 1000)}")
        business = detail.get("business") if isinstance(detail, dict) else None
        if not isinstance(business, dict) or detail.get("id") != plot:
            raise HttpCoreError("Detail plot usaha berubah", category="schema")
        if business.get("desa") != self.api.home["desa"]:
            return None
        name = business.get("name")
        if (
            business.get("catalogId") != category
            or not isinstance(name, str)
            or name != row["name"]
        ):
            raise HttpCoreError("Identitas usaha berubah", category="schema")
        try:
            identifier = str(UUID(business["id"]))
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise HttpCoreError("ID usaha belum terverifikasi", category="schema") from exc
        return NeedShop(identifier, plot, name, category)

    async def directory_need_shop(self, row, resource, effects, distance_squared):
        location = await self.directory_business(row)
        if location is None:
            return None
        shop = await self.need_shop(location, resource, effects)
        return shop.model_copy(update={"distance_squared": distance_squared}) if shop else None

    async def directory_shop_rows(self, categories):
        directory = await self.api.request("/api/tujuan")
        rows = directory.get("usaha") if isinstance(directory, dict) else None
        if not isinstance(rows, list):
            raise HttpCoreError("Direktori usaha belum terverifikasi", category="schema")
        candidates = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            plot, name, category = row.get("plotId"), row.get("name"), row.get("item")
            if (
                not isinstance(category, str)
                or category not in categories
                or not isinstance(plot, str)
                or not re.fullmatch(r"[A-Z][0-9]{2}-U[0-9]{2}", plot)
                or not isinstance(name, str)
                or not name.strip()
                or type(row.get("x")) is not int
                or type(row.get("y")) is not int
            ):
                continue
            distance = (row["x"] - self.api.home["x"]) ** 2 + (row["y"] - self.api.home["y"]) ** 2
            candidates.append((distance, row))
        return candidates

    async def directory_ojol_shops(self, resource, effects, allowed_items, locations):
        async def read_shop(row):
            business = await self.directory_business(row)
            if business is None:
                return None
            location = ShopLocation(
                business.id, business.plot_id, business.name, row["x"], row["y"]
            )
            shop = await self.api.preview_shop(location, resource, effects, allowed_items)
            return shop.model_copy(update={"from_directory": True}) if shop else None

        candidates = await self.directory_shop_rows((CATEGORIES[resource],))
        rows = []
        seen = {loc.plot_id for loc in locations}
        for _, row in sorted(
            candidates, key=lambda candidate: (candidate[0], candidate[1]["plotId"])
        ):
            if row["plotId"] not in seen:
                seen.add(row["plotId"])
                rows.append(row)
        first_error = None
        for start in range(0, len(rows), 6):
            results = await self.read_previews(
                (read_shop(row) for row in rows[start : start + 6]), return_exceptions=True
            )
            shops = []
            for result in results:
                if isinstance(result, HttpCoreError) and result.category != "auth":
                    first_error = first_error or result
                elif isinstance(result, BaseException):
                    raise result
                elif result is not None:
                    shops.append(result)
            if shops:
                # shortcut: stop at the first stocked batch, expand if buyers need farther options.
                return shops
        if first_error is not None:
            raise first_error
        return []

    async def need_suppliers(self, resource, effects, *, preferred_only=False):
        if (
            getattr(self.api, "akademis_need_shops", None) is not None
            and self.api.akademis_need_shops != self.api.need_suppliers
        ):
            return await self.api.akademis_need_shops(
                resource, effects, preferred_only=preferred_only
            )
        village = self.api.home["desa"]
        registered = tuple(
            loc
            for loc in NEED_SHOPS_BY_VILLAGE.get(village, {}).get(resource, ())
            if "akademis.ai" in loc.name.casefold()
        )
        registered_plots = {loc.plot_id for loc in registered}
        preferred, nearby = [], []
        seen = set(registered_plots)
        for distance, row in await self.directory_shop_rows(NEED_SHOP_CATEGORIES[resource]):
            plot, name = row["plotId"], row["name"]
            if plot in seen:
                continue
            branded = "akademis.ai" in name.casefold()
            if branded or distance <= 60**2:
                seen.add(plot)
                (preferred if branded else nearby).append((distance, row))

        def available_shops(results, *, require_certain):
            errors = [item for item in results if isinstance(item, BaseException)]
            for exc in errors:
                if not isinstance(exc, HttpCoreError) or exc.category == "auth":
                    raise exc
            available = [
                shop
                for shop in results
                if isinstance(shop, ShopPreview) and any(p.enabled for p in shop.products)
            ]
            fatal_errors = [
                exc
                for exc in errors
                if isinstance(exc, HttpCoreError)
                and exc.category not in {"transport", "blocked"}
                and not getattr(exc, "recoverable", False)
            ]
            if require_certain and not available and fatal_errors:
                raise fatal_errors[0]
            return available

        shops = await self.read_previews(
            [self.need_shop(loc, resource, effects) for loc in registered]
            + [
                self.directory_need_shop(row, resource, effects, distance)
                for distance, row in preferred
            ],
            return_exceptions=True,
        )
        available = available_shops(shops, require_certain=True)
        if available or preferred_only:
            return available, False
        candidates = sorted(nearby, key=lambda candidate: (candidate[0], candidate[1]["plotId"]))
        for start in range(0, len(candidates), 6):
            fallback = await self.read_previews(
                (
                    self.directory_need_shop(row, resource, effects, distance)
                    for distance, row in candidates[start : start + 6]
                ),
                return_exceptions=True,
            )
            available = available_shops(fallback, require_certain=False)
            if available:
                return available, True
        return [], True

    async def _preview_spbu_fuel(self, current: Snapshot) -> dict:
        try:
            dest = await self.api.request("/api/tujuan")
            spbus = [
                u
                for u in dest.get("usaha", [])
                if isinstance(u, dict) and u.get("item") == "spbu-pertamina"
            ]
        except Exception:
            spbus = []
        if not spbus:
            return {
                "shops": [],
                "navigation": {"method": "spbu_visit", "travel_request_sent": False},
            }

        ref_x = (self.api.home or {}).get("x", 0)
        ref_y = (self.api.home or {}).get("y", 0)
        spbus.sort(key=lambda s: (s.get("x", 0) - ref_x) ** 2 + (s.get("y", 0) - ref_y) ** 2)
        spbu = spbus[0]
        plot_id = spbu["plotId"]
        v_type = current.ojol_vehicle or "motor"
        is_electric = False
        if v_type == "mobil":
            try:
                kd = await self.api.request("/api/kendaraan")
                items = kd.get("items", []) if isinstance(kd, dict) else []
                car = next((c for c in items if c.get("family") == "mobil"), None)
                is_electric = bool(car and car.get("listrik"))
            except (HttpCoreError, AttributeError, TypeError) as exc:
                logger.debug("Could not verify vehicle power source (%s)", type(exc).__name__)

        if is_electric:
            item_name, prod_name = "isi-daya-spklu", "Isi daya SPKLU (mobil listrik)"
        elif v_type == "mobil":
            item_name, prod_name = "isi-bensin-mobil", "Isi bensin mobil"
        else:
            item_name, prod_name = "isi-bensin-motor", "Isi bensin motor"

        missing = max(1, 100 - current.fuel)
        price = (Decimal(missing) * Decimal(20)) / Decimal(1000)
        biz_id = spbu.get("businessId")
        try:
            shop_id = str(UUID(biz_id)) if biz_id else str(uuid5(NAMESPACE_DNS, plot_id))
        except (ValueError, TypeError):
            shop_id = str(uuid5(NAMESPACE_DNS, plot_id))
        identity = json.dumps(
            {
                "shop": shop_id,
                "resource": "fuel",
                "plotId": plot_id,
                "x": spbu.get("x", 0),
                "y": spbu.get("y", 0),
                "item": item_name,
                "vehicle": v_type,
            }
        )
        dist_sq = (spbu.get("x", 0) - ref_x) ** 2 + (spbu.get("y", 0) - ref_y) ** 2
        spbu_shop = ShopPreview(
            id=shop_id,
            plot_id=plot_id,
            name=spbu.get("name") or "SPBU",
            category="spbu",
            distance_squared=dist_sq,
            products=[
                Product(
                    name=prod_name,
                    price=price,
                    effects={"fuel": missing},
                    row_text=identity,
                    enabled=True,
                )
            ],
        )
        self.api.catalog.setdefault("fuel", {})[shop_id] = spbu_shop
        return {
            "shops": [spbu_shop.model_dump()],
            "navigation": {"method": "spbu_refill", "travel_request_sent": False},
        }

    async def _preview_fisik_shops(self) -> list[ShopPreview]:
        if not self.api.physical_places:
            try:
                tempat = await self.api.request("/api/kebutuhan?tempat=fisik")
                if isinstance(tempat, dict) and isinstance(tempat.get("places"), list):
                    self.api.physical_places = [p for p in tempat["places"] if isinstance(p, dict)]
            except HttpCoreError:
                pass
        try:
            effects = await self.api.effects(for_needs=True)
        except HttpCoreError:
            effects = {}
        village = (self.api.home or {}).get("desa")
        gym_ids = list(GYM_FACILITIES_BY_VILLAGE.get(village, ()))
        gym_previews = await self.read_previews(
            self.api.gym_facility(fid, effects) for fid in gym_ids
        )
        place_previews = await self.read_previews(
            self.api.physical_facility(place, effects)
            for place in self.api.physical_places
            if place.get("id") not in set(gym_ids)
        )
        return gym_previews + place_previews

    async def _preview_kesehatan_shops(self) -> list[ShopPreview]:
        try:
            bpjs = await self.api.ensure_bpjs()
        except HttpCoreError:
            bpjs = {}
        kartu = bpjs.get("kartu") or {}
        gratis_sisa = bpjs.get("gratisSisa", 0)
        village = (self.api.home or {}).get("desa")
        facility_ids = HEALTH_FACILITIES_BY_VILLAGE.get(village, ())
        if not (kartu.get("aktif") and gratis_sisa > 0 and facility_ids):
            return []
        for fid in facility_ids:
            try:
                details = await self.api.request(f"/api/facilities/{fid}")
            except HttpCoreError:
                continue
            service = details.get("service") or {}
            if (
                details.get("state") == "DONE"
                and not details.get("nextAt")
                and not details.get("myVisitUntil")
                and service.get("open") is not False
            ):
                identity = json.dumps({"shop": fid, "item": "use", "resource": "kesehatan"})
                return [
                    ShopPreview(
                        id=fid,
                        plot_id=fid,
                        name=details.get("title", "Puskesmas"),
                        category="fasum",
                        distance_squared=0,
                        products=[
                            Product(
                                name=service.get("label", "Periksa kesehatan"),
                                price=Decimal(0),
                                effects={"kesehatan": 15},
                                row_text=identity,
                                enabled=True,
                            )
                        ],
                    )
                ]
        return []

    async def _preview_cooldown_facility(
        self,
        resource: str,
        facility_ids: tuple[str, ...],
        *,
        default_title: str,
        default_label: str,
        effects_resolver,
    ) -> list[ShopPreview]:
        now_utc = datetime.now(UTC)
        for fid in facility_ids:
            try:
                details = await self.api.request(f"/api/facilities/{fid}")
            except HttpCoreError:
                continue
            service = details.get("service") or {}
            is_cooldown = False
            for time_key in ("nextAt", "myVisitUntil"):
                val = details.get(time_key)
                if val:
                    try:
                        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                        if now_utc < dt:
                            is_cooldown = True
                    except (ValueError, TypeError):
                        is_cooldown = True
            if (
                details.get("state") == "DONE"
                and not is_cooldown
                and service.get("open") is not False
            ):
                title = details.get("title", default_title)
                label = service.get("label", default_label)
                identity = json.dumps({"shop": fid, "item": "use", "resource": resource})
                return [
                    ShopPreview(
                        id=fid,
                        plot_id=fid,
                        name=title,
                        category="fasum",
                        distance_squared=0,
                        products=[
                            Product(
                                name=label,
                                price=Decimal(0),
                                effects=effects_resolver(details, title),
                                row_text=identity,
                                enabled=True,
                            )
                        ],
                    )
                ]
        return []

    async def _preview_kebersihan_shops(self) -> list[ShopPreview]:
        plot_id = (self.api.home or {}).get("plotId", "home")
        keb_status = await self.api.request("/api/kebutuhan")
        bersih = keb_status.get("bersih") or {}
        products = []
        if bersih.get("mandi", 0) < bersih.get("mandiMaks", 2):
            products.append(
                Product(
                    name="Mandi di kamar mandi",
                    price=Decimal(0),
                    effects={"kebersihan": 65},
                    row_text=json.dumps(
                        {"shop": KAMAR_MANDI_ID, "action": "mandi", "resource": "kebersihan"}
                    ),
                    enabled=True,
                )
            )
        if bersih.get("sikat", 0) < bersih.get("sikatMaks", 3):
            products.append(
                Product(
                    name="Sikat gigi",
                    price=Decimal(0),
                    effects={"kebersihan": 35},
                    row_text=json.dumps(
                        {"shop": KAMAR_MANDI_ID, "action": "sikat", "resource": "kebersihan"}
                    ),
                    enabled=True,
                )
            )
        if not products or (
            bersih.get("mandi", 0) >= bersih.get("mandiMaks", 2)
            and bersih.get("sikat", 0) >= bersih.get("sikatMaks", 3)
        ):
            products.append(
                Product(
                    name="Cuci tangan",
                    price=Decimal(0),
                    effects={"kebersihan": 5},
                    row_text=json.dumps(
                        {"shop": KAMAR_MANDI_ID, "action": "cuci", "resource": "kebersihan"}
                    ),
                    enabled=True,
                )
            )
        return [
            ShopPreview(
                id=KAMAR_MANDI_ID,
                plot_id=plot_id,
                name="Kamar mandi rumah",
                category="kamar-mandi",
                distance_squared=0,
                products=products,
            )
        ]

    async def preview(self, resource):
        if resource not in CATEGORIES and resource not in NEEDS:
            raise HttpCoreError("Resource tidak didukung", category="blocked")
        self.api.catalog.pop(resource, None)
        fallback_allowed = False
        navigation_method = "fixed_catalog_http"
        try:
            async with asyncio.timeout(25):
                if resource in {"fuel", "condition"} or not getattr(self.api, "home", None):
                    current = await self.api.snapshot()
                    if resource == "fuel" and current.ojol_min_fuel is not None:
                        return await self._preview_spbu_fuel(current)
                if not self.api.home:
                    raise HttpCoreError("Rumah akun belum tersedia", category="blocked")
                if resource == "fisik":
                    shops = await self._preview_fisik_shops()
                elif resource in NEEDS:
                    shops = []
                    village = (self.api.home or {}).get("desa")
                    if resource == "kesehatan":
                        shops = await self._preview_kesehatan_shops()
                    elif resource == "makan":
                        shops = await self._preview_cooldown_facility(
                            "makan",
                            SPPG_FACILITIES_BY_VILLAGE.get(village, ()),
                            default_title="SPPG (dapur Makan Bergizi Gratis)",
                            default_label="Makan bergizi",
                            effects_resolver=lambda _d, _t: {"makan": 60, "kesehatan": 5},
                        )
                    elif resource == "rekreasi":
                        shops = await self._preview_cooldown_facility(
                            "rekreasi",
                            RECREATION_FACILITIES_BY_VILLAGE.get(village, ()),
                            default_title="Taman desa",
                            default_label="Bersantai di taman",
                            effects_resolver=lambda d, title: (
                                {"rekreasi": 30, "fisik": 10}
                                if "alun-alun" in d.get("item", "").lower()
                                or "alun-alun" in title.lower()
                                else {"rekreasi": 20}
                            ),
                        )
                    elif resource == "wc":
                        plot_id = (self.api.home or {}).get("plotId", "home")
                        shops = [
                            ShopPreview(
                                id=KAMAR_MANDI_ID,
                                plot_id=plot_id,
                                name="Kamar mandi rumah",
                                category="kamar-mandi",
                                distance_squared=0,
                                products=[
                                    Product(
                                        name="Buang air di kloset",
                                        price=Decimal(0),
                                        effects={"wc": 100},
                                        row_text=json.dumps(
                                            {
                                                "shop": KAMAR_MANDI_ID,
                                                "action": "wc",
                                                "resource": "wc",
                                            }
                                        ),
                                        enabled=True,
                                    )
                                ],
                            )
                        ]
                    elif resource == "kebersihan":
                        shops = await self._preview_kebersihan_shops()
                    if not shops and resource in NEED_SHOP_CATEGORIES:
                        effects = await self.api.effects(for_needs=True)
                        shops, fallback_allowed = await self.need_suppliers(resource, effects)
                else:
                    locations = self.ojol_shop_locations(resource)
                    if not locations and resource not in OJOL_DIRECTORY_RESOURCES:
                        raise HttpCoreError(
                            "Toko tetap belum dikonfigurasi untuk desa akun", category="blocked"
                        )
                    allowed_items = await self.resource_items(resource)
                    effects = await self.api.effects(required_items=allowed_items)
                    shops = await self.read_previews(
                        self.api.preview_shop(location, resource, effects, allowed_items)
                        for location in locations
                    )
                    if not any(shops) and resource in OJOL_DIRECTORY_RESOURCES:
                        navigation_method = "directory_catalog_http"
                        shops = await self.directory_ojol_shops(
                            resource, effects, allowed_items, locations
                        )
        except TimeoutError:
            raise HttpCoreError(
                "Deadline preview toko tercapai sebelum katalog terverifikasi",
                category="transport",
                recoverable=True,
            ) from None
        shops = {
            shop.id: shop
            for shop in shops
            if shop is not None and any(product.enabled for product in shop.products)
        }
        self.api.catalog[resource] = shops
        return {
            "shops": [
                shop.model_dump(mode="json")
                for shop in sorted(
                    shops.values(), key=lambda shop: (shop.distance_squared, shop.id)
                )
            ],
            "navigation": {
                "method": navigation_method,
                "panel_verified": True,
                "travel_request_sent": False,
                **(
                    {"akademis_unavailable": fallback_allowed}
                    if resource in NEEDS and resource != "fisik"
                    else {}
                ),
            },
        }

    async def purchase(self, product, expected_wallet, expected_resource, min_balance, request_id):
        request_id = str(UUID(request_id))
        product = Product.model_validate(product)
        identity = json.loads(product.row_text)
        shop_id = str(UUID(identity["shop"]))
        resource = identity["resource"]
        is_need = resource in NEEDS
        shop = self.api.catalog.get(resource, {}).get(shop_id)
        if shop is None or product not in shop.products or not product.enabled:
            raise HttpCoreError("Produk tidak berasal dari preview sesi ini", category="rejected")
        try:
            async with asyncio.timeout(15 if is_need else None):
                await self.api.validate_purchase(
                    shop, resource, product, expected_wallet, expected_resource, min_balance
                )
        except (
            HttpCoreError,
            TimeoutError,
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:
            if not is_need or (
                isinstance(exc, HttpCoreError) and exc.category in {"auth", "rejected", "sleeping"}
            ):
                raise
            raise HttpCoreError(
                "Kebutuhan dilewati karena data sebelum transaksi belum terverifikasi",
                category="rejected",
            ) from exc
        self.api.catalog.pop(resource)
        if not auto_flags(self.api.directory)[resource if is_need else "ojol"]:
            raise HttpCoreError(
                "Fitur Auto dinonaktifkan sebelum pembelian", category="auto_disabled"
            )
        if shop.category == "spbu":
            kend_res = await self.api.request("/api/kendaraan")
            items = kend_res.get("items", []) if isinstance(kend_res, dict) else []
            v_family = identity.get("vehicle", "motor")
            target_veh = next(
                (v for v in items if v.get("family") == v_family), items[0] if items else None
            )
            veh_code = (target_veh or {}).get("kode")
            if not veh_code:
                raise HttpCoreError("Kode kendaraan Ojol tidak ditemukan", category="rejected")
            plot_id = identity.get("plotId") or shop.plot_id
            pos_x = identity.get("x", 0)
            pos_y = identity.get("y", 0)
            await self.api.request(
                f"/api/spbu/{plot_id}",
                {"aksi": "datang", "kode": veh_code, "dorong": False, "x": pos_x, "y": pos_y},
            )
            receipt = await self.api.request(
                f"/api/spbu/{plot_id}",
                {"aksi": "isi", "jumlah": "penuh", "x": pos_x, "y": pos_y, "requestId": request_id},
            )
            with contextlib.suppress(Exception):
                await self.api.request(f"/api/spbu/{plot_id}", {"aksi": "pamit"})
            return receipt
        if shop.category == "fasum":
            if identity.get("item") == "minigame":
                receipt = await self.api.complete_minigame(
                    shop_id, identity.get("game", "gym"), request_id
                )
                return receipt
            receipt = await self.api.request(
                f"/api/facilities/{shop_id}/use", {"requestId": request_id}
            )
            if resource in {"kesehatan", "makan", "rekreasi"}:
                await self.api.complete_facility_kegiatan(shop_id)
            return receipt
        if shop.category == "kamar-mandi":
            action = identity.get("action", "wc")
            receipt = await self.api.request("/api/rumah/kamar-mandi", {"aksi": action})
            if action == "wc":
                with contextlib.suppress(Exception):
                    await self.api.request("/api/rumah/kamar-mandi", {"aksi": "cuci"})
            return receipt
        return await self.api.request(
            f"/api/shops/{shop_id}/buy", {"item": identity["item"], "requestId": request_id}
        )

    async def validate_purchase(
        self, shop, resource, product, expected_wallet, expected_resource, min_balance
    ):
        shop_id = shop.id
        is_need = resource in NEEDS
        is_facility = shop.category == "fasum"
        is_bathroom = shop.category == "kamar-mandi"
        is_spbu = shop.category == "spbu"
        fallback = (
            is_need and not is_facility and not is_bathroom and not is_spbu and not shop.preferred
        )
        version = self.api.config_version
        vehicle = self.api.vehicle
        allowed_items = None if is_need else await self.resource_items(resource)
        if not is_facility and not is_bathroom and not is_spbu:
            effects = await self.api.effects(for_needs=is_need, required_items=allowed_items or ())
            if not fallback:
                catalog, fresh = await self.api.products(shop_id, resource, effects, allowed_items)
                if product not in fresh or (
                    (is_need or catalog.get("plang")) and catalog.get("plang") != shop.name
                ):
                    raise HttpCoreError(
                        "Nama toko atau katalog berubah sebelum pembelian", category="rejected"
                    )
        state = await self.api.snapshot()
        if state.phase == "sleeping":
            raise HttpCoreError("Karakter sedang tidur; transaksi ditunda", category="sleeping")
        if resource == "fuel" and state.ojol_min_fuel is not None and not is_spbu:
            raise HttpCoreError(
                "Pengisian tangki memerlukan kunjungan ke SPBU", category="rejected"
            )
        identity = json.loads(product.row_text) if product.row_text else {}
        if is_bathroom:
            if not self.api.home:
                eligible = False
            elif resource == "wc":
                eligible = True
            elif resource == "kebersihan":
                action = identity.get("action")
                keb_status = await self.api.request("/api/kebutuhan")
                bersih = keb_status.get("bersih") or {}
                if action == "mandi":
                    eligible = bersih.get("mandi", 0) < bersih.get("mandiMaks", 2)
                elif action == "sikat":
                    eligible = bersih.get("sikat", 0) < bersih.get("sikatMaks", 3)
                else:
                    eligible = True
            else:
                eligible = False
        elif resource == "fisik":
            village = (self.api.home or {}).get("desa")
            gym_ids = set(GYM_FACILITIES_BY_VILLAGE.get(village, ()))
            effects = {}
            try:
                effects = await self.api.effects(for_needs=True)
            except HttpCoreError:
                effects = {}
            if shop_id in gym_ids:
                eligible = await self.api.gym_facility(shop_id, effects) == shop
            else:
                place = next((p for p in self.api.physical_places if p.get("id") == shop_id), {})
                eligible = await self.api.physical_facility(place, effects) == shop
        elif is_spbu:
            eligible = True
        elif is_facility and resource in {"kesehatan", "makan", "rekreasi"}:
            details = await self.api.request(f"/api/facilities/{shop_id}")
            service = details.get("service") or {}
            now_utc = datetime.now(UTC)
            is_cooldown = False
            for time_key in ("nextAt", "myVisitUntil"):
                val = details.get(time_key)
                if val:
                    try:
                        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                        if now_utc < dt:
                            is_cooldown = True
                    except Exception:
                        is_cooldown = True
            eligible = (
                details.get("state") == "DONE"
                and not is_cooldown
                and service.get("open") is not False
            )
        elif fallback and self.api.home:
            candidates, allowed = await self.need_suppliers(resource, effects)
            eligible = allowed and any(
                fresh.id == shop_id and fresh.name == shop.name and product in fresh.products
                for fresh in candidates
            )
        elif is_need and shop.preferred and self.api.home:
            if any(
                location.id == shop_id
                for location in NEED_SHOPS_BY_VILLAGE.get(self.api.home["desa"], {}).get(
                    resource, ()
                )
            ):
                eligible = True
            else:
                candidates, _ = await self.need_suppliers(resource, effects, preferred_only=True)
                eligible = any(
                    fresh.id == shop_id and fresh.name == shop.name and product in fresh.products
                    for fresh in candidates
                )
        elif shop.from_directory:
            location = (
                await self.directory_business(
                    {"plotId": shop.plot_id, "item": shop.category, "name": shop.name}
                )
                if self.api.home
                else None
            )
            eligible = location is not None and location.id == shop_id
        else:
            locations = (
                NEED_SHOPS_BY_VILLAGE.get((self.api.home or {}).get("desa"), {}).get(resource, ())
                if is_need
                else self.ojol_shop_locations(resource)
            )
            eligible = any(location.id == shop_id for location in locations)
        current = state.resource_value(resource)
        if (
            state.phase != "idle"
            or state.wallet != Decimal(expected_wallet)
            or current is None
            or current != expected_resource
            or self.api.config_version != version
            or (resource in {"fuel", "condition"} and state.ojol_vehicle != vehicle)
            or self.api.catalog.get(resource, {}).get(shop_id) is not shop
            or not eligible
        ):
            raise HttpCoreError(
                "Fase, saldo, resource atau katalog berubah sebelum pembelian", category="rejected"
            )
        if (
            product.price > Decimal(0)
            and (
                (is_need and resource != "makan" and state.wallet - product.price < Decimal(20))
                or state.wallet - product.price < max(Decimal(5), Decimal(min_balance))
            )
        ) or (not is_need and current + product.effects[resource] > 100):
            raise HttpCoreError("Pembelian melanggar saldo minimum/overflow", category="rejected")
