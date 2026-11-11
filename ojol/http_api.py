"""Observed Ojol endpoints only. GETs may retry; writes are always one attempt."""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from decimal import Decimal
from math import ceil
from pathlib import Path
from uuid import UUID

import httpx

from .auto_settings import auto_flags
from .finance import WIB
from .healing import write_private
from .models import NEEDS, Product, ShopPreview, Snapshot
from .session_transfer import DOMAIN, parse_cookie_input, session_expired
from .shop_locations import NEED_FALLBACK_PLOTS, NEED_SHOPS_BY_VILLAGE, SHOPS_BY_VILLAGE, NeedShop

ORIGIN = "https://www.kampungsebelah.com"
ITEMS = {
    "fuel": {"isi-pertalite", "isi-pertamax"},
    "condition": {"servis-motor", "ganti-oli", "tambal-ban", "isi-angin", "cuci-motor"},
    "data": {"pulsa", "paket-data", "servis-hp", "casing-hp"},
}
CATEGORIES = {"fuel": "spbu-pertamina", "condition": "bengkel-motor", "data": "konter-pulsa"}
RESOURCES = {"bensin": "fuel", "kendaraan": "condition", "kuota": "data"}
KINDS = {
    "PENUMPANG": ("🧍", "Antar penumpang"),
    "MAKANAN": ("🍱", "Antar makanan"),
    "BELANJA": ("🛍️", "Antar belanjaan"),
}


class HttpCoreError(RuntimeError):
    def __init__(self, message, category="schema", recoverable=False):
        super().__init__(message)
        self.category, self.recoverable = category, recoverable
        self.stage, self.operation = "http." + category, "ojol_http"


def integer(value):
    if type(value) is not int or value < 0:
        raise HttpCoreError("Format angka API berubah", recoverable=True)
    return value


def coin(milli):
    return Decimal(integer(milli)) / 1000


def display(value):
    return (
        format(value, "f").rstrip("0").rstrip(".").replace(".", ",")
        if value % 1
        else str(int(value))
    )


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Missing timezone")
    return parsed


def need_rows(payload):
    rows = payload.get("needs")
    if payload.get("enabled") is not True or not isinstance(rows, list):
        return {}
    return {
        row["id"]: row
        for row in rows
        if isinstance(row, dict)
        and row.get("id") in NEEDS
        and type(row.get("value")) is int
        and 0 <= row["value"] <= 100
    }


def snapshot_from_api(ojol, me, needs, server_now, *, require_ojol=True):
    if require_ojol and (ojol["enabled"] is not True or ojol["mitra"] is not True):
        raise HttpCoreError("Akun belum menjadi mitra Ojol", category="blocked")
    if type(needs["asleep"]) is not bool:
        raise HttpCoreError("Status tidur API berubah", recoverable=True)
    trip = ojol.get("trip") if not require_ojol and ojol.get("mitra") is False else ojol["trip"]
    phase, remaining, description = "idle", None, None
    buttons, text = ["📲 Cari order", "Berhenti jadi mitra ojol"], "Narik pakai motor"
    if trip:
        icon, label = KINDS[trip["kind"]]
        remaining = max(0, ceil((timestamp(trip["arriveAt"]) - server_now).total_seconds()))
        phase = "complete" if remaining == 0 else "delivering"
        description = f"{icon} {label} · 🛵 {integer(trip['distance'])} petak · ongkos {display(coin(trip['fareMilli']))} koin | 📍 {trip['from']['label']}🏁 {trip['to']['label']}"
        buttons = [
            "✅ Sampai! Terima ongkos"
            if phase == "complete"
            else f"🛵 Mengantar… {remaining // 60}:{remaining % 60:02}",
            "📍 Lihat di peta",
        ]
        text = description
    if needs["asleep"]:
        phase, text = "sleeping", "Kamu sedang tidur. Tekan ☀ Bangun dulu."
    elif require_ojol and ojol.get("problem") and not trip:
        raise HttpCoreError("Game menolak Ojol: periksa kondisi akun di game", category="blocked")
    history = []
    for receipt in ojol["history"] if require_ojol else ojol.get("history", []):
        done = timestamp(receipt["doneAt"]).astimezone(WIB)
        icon, _ = KINDS[receipt["kind"]]
        history.append(
            f"{done:%H.%M} {icon} {receipt['from']['label']} → {receipt['to']['label']} · +{display(coin(receipt['netMilli']))}"
        )
    bars = ojol["bars"] if require_ojol else (ojol.get("bars") or {})
    income = ojol["earnedTodayMilli"] if require_ojol else ojol.get("earnedTodayMilli", 0)
    return Snapshot(
        observed_at=server_now,
        wallet=coin(me["balanceMilli"]),
        fuel=integer(bars["bensin"] if require_ojol else bars.get("bensin", 0)),
        condition=integer(bars["kendaraan"] if require_ojol else bars.get("kendaraan", 0)),
        data=integer(bars["kuota"] if require_ojol else bars.get("kuota", 0)),
        phase=phase,
        remaining_seconds=remaining,
        trip=description,
        today_income=coin(income),
        history=history,
        buttons=buttons,
        raw_text=text,
        needs={key: row["value"] for key, row in need_rows(needs).items()},
    )


def extract_effects(source):
    allowed = set.union(*ITEMS.values())
    result = {}
    for match in re.finditer(r'"([a-z-]+)":(\{[^{}]{1,220}\})', source):
        if match[1] not in allowed:
            continue
        effect = json.loads(match[2])
        if not any(key in effect for key in RESOURCES):
            continue
        selected = {
            RESOURCES[key]: integer(value) for key, value in effect.items() if key in RESOURCES
        }
        if not selected or any(value > 100 for value in selected.values()):
            raise HttpCoreError("Konfigurasi efek produk tidak valid", recoverable=True)
        if match[1] in result and result[match[1]] != selected:
            raise HttpCoreError("Konfigurasi efek produk ambigu", recoverable=True)
        result[match[1]] = selected
    return result


def extract_need_effects(source):
    for match in re.finditer(r'"barang"\s*:\s*\{', source):
        try:
            items, _ = json.JSONDecoder().raw_decode(source, match.end() - 1)
        except ValueError:
            continue
        if not {"nasi-goreng", "tambal-ban", "pulsa"} <= items.keys():
            continue
        return {
            item: {key: value for key, value in effects.items() if key in NEEDS}
            for item, effects in items.items()
            if isinstance(effects, dict)
            and re.fullmatch(r"[a-z0-9-]+", item)
            and any(key in NEEDS for key in effects)
            and all(type(value) is int and 0 <= value <= 100 for value in effects.values())
        }
    return {}


class OjolHttpApi:
    def __init__(self, directory: Path, session_file=None, client=None):
        self.directory = directory
        self.session_file = session_file or directory / "http-session.json"
        self.client = client
        self.owns_client = client is None
        self.catalog = {}
        self.retries = 0
        self.expires_at = None

    async def __aenter__(self):
        logging.getLogger("httpx").setLevel(logging.WARNING)
        if self.client is None:
            try:
                payload = parse_cookie_input(self.session_file.read_text())
            except (OSError, ValueError, TypeError, KeyError):
                raise HttpCoreError(
                    "Sesi HTTP belum tersedia. Gunakan Import Cookie.", category="auth"
                ) from None
            cookies = httpx.Cookies()
            if session_expired(payload):
                raise HttpCoreError("Cookie sesi game sudah kedaluwarsa.", category="auth")
            self.expires_at = payload["cookies"][0].get("expires")
            for cookie in payload["cookies"]:
                cookies.set(cookie["name"], cookie["value"], domain=DOMAIN, path="/")
            self.client = httpx.AsyncClient(
                base_url=ORIGIN,
                cookies=cookies,
                trust_env=False,
                follow_redirects=False,
                timeout=5,
                headers={
                    "Origin": ORIGIN,
                    "Referer": ORIGIN + "/kampung",
                    "Cache-Control": "no-cache",
                },
            )
        return self

    async def __aexit__(self, *args):
        if self.owns_client and self.client:
            await self.client.aclose()

    async def request(self, path, payload=None, text=False):
        # No caller-provided URLs, redirects, or generic HTTP MCP tool.
        allowed = (
            path
            in {
                "/api/ojol",
                "/api/game/me",
                "/api/kebutuhan",
                "/api/time",
                "/kampung",
            }
            or re.fullmatch(
                r"/api/world/plots\?v=2&blocks=[A-Z][0-9]{2}(?:,[A-Z][0-9]{2}){0,23}", path
            )
            or re.fullmatch(r"/api/shops/[a-f0-9-]{36}(?:/buy)?", path)
            or re.fullmatch(r"/api/world/plots/[A-Z][0-9]{2}-U[0-9]{2}\?t=[0-9]{1,15}", path)
            or re.fullmatch(r"/api/facilities/[a-f0-9-]{36}(?:/use)?", path)
            or re.fullmatch(r"/_next/static/[a-zA-Z0-9_./-]+\.js", path)
        )
        if (
            not allowed
            or ".." in path.split("/")
            or "//" in path
            or (payload is not None and path != "/api/ojol" and not path.endswith(("/buy", "/use")))
        ):
            raise HttpCoreError("Endpoint di luar izin Ojol", category="blocked")
        if self.expires_at is not None and self.expires_at <= time.time():
            raise HttpCoreError("Cookie sesi game sudah kedaluwarsa.", category="auth")
        for attempt in range(3 if payload is None else 1):
            try:
                response = await self.client.request(
                    "GET" if payload is None else "POST", path, json=payload
                )
            except httpx.TransportError:
                if payload is not None:
                    raise HttpCoreError(
                        "Request transaksi terputus; hasil belum pasti, tidak diulang",
                        category="uncertain",
                    ) from None
                response = None
            if response is not None:
                if response.status_code in {401, 403} or 300 <= response.status_code < 400:
                    raise HttpCoreError(
                        "Sesi ditolak/kedaluwarsa. Gunakan Import Cookie.", category="auth"
                    )
                if response.is_success:
                    try:
                        return response.text if text else response.json()
                    except ValueError:
                        raise HttpCoreError(
                            "Respons API bukan JSON valid", recoverable=payload is None
                        ) from None
                if payload is not None:
                    raise HttpCoreError(
                        f"Transaksi ditolak HTTP{response.status_code}; tidak diulang",
                        category="uncertain",
                    )
                if response.status_code not in {408, 429, 500, 502, 503, 504}:
                    raise HttpCoreError(
                        f"Endpoint Ojol HTTP{response.status_code}", recoverable=True
                    )
            if attempt < 2:
                self.retries += 1
                await asyncio.sleep(attempt + 1)
        raise HttpCoreError(
            "Pembacaan HTTP gagal setelah 3 percobaan", category="transport", recoverable=True
        )

    async def snapshot(self):
        ojol, me, needs, clock = await asyncio.gather(
            *(
                self.request(path)
                for path in ("/api/ojol", "/api/game/me", "/api/kebutuhan", "/api/time")
            )
        )
        self.config_version = me["configVersion"]
        self.home = me["home"]
        self.vehicle = ojol.get("vehicle")
        places = need_rows(needs).get("fisik", {}).get("places")
        self.physical_places = (
            [place for place in places if isinstance(place, dict)]
            if isinstance(places, list)
            else []
        )
        # The server clock, not the machine's timezone/clock, gates completion.
        require_ojol = auto_flags(self.directory)["ojol"] or bool(ojol.get("trip"))
        state = snapshot_from_api(
            ojol, me, needs, timestamp(clock["now"]), require_ojol=require_ojol
        )
        if require_ojol and self.vehicle != "motor":
            raise HttpCoreError("Core HTTP hanya untuk Ojol motor", category="blocked")
        return state

    async def effects(self, *, for_needs=False):
        version = getattr(self, "config_version", None)
        if version is None:
            await self.snapshot()
            version = self.config_version
        cache = self.directory / "http-effects.json"
        key = "needs_effects" if for_needs else "effects"
        if cache.is_file():
            data = json.loads(cache.read_text())
            if data.get("version") == version and data.get(key):
                return data[key]
        html = await self.request("/kampung", text=True)
        effects = {}
        needs_effects = {}
        for path in re.findall(r"<script[^>]+src=[\"\x27]([^\"\x27]+)", html):
            if not path.startswith("/_next/static/"):
                continue
            source = await self.request(path, text=True)
            found = extract_effects(source)
            if any(item in effects and effects[item] != value for item, value in found.items()):
                raise HttpCoreError("Efek produk antar bundle berbeda", recoverable=True)
            effects.update(found)
            found_needs = extract_need_effects(source)
            if found_needs:
                if needs_effects and found_needs != needs_effects:
                    raise HttpCoreError("Efek kebutuhan antar bundle berbeda", recoverable=True)
                needs_effects.update(found_needs)
            if set.union(*ITEMS.values()) <= effects.keys() and (needs_effects or not for_needs):
                break
        if not set.union(*ITEMS.values()) <= effects.keys():
            raise HttpCoreError("Efek produk client belum dapat diverifikasi", recoverable=True)
        write_private(
            cache, {"version": version, "effects": effects, "needs_effects": needs_effects}
        )
        if for_needs and not needs_effects:
            raise HttpCoreError("Efek barang kebutuhan belum dapat diverifikasi", recoverable=True)
        return needs_effects if for_needs else effects

    async def products(self, shop_id, resource, effects):
        catalog = await self.request("/api/shops/" + shop_id)
        if type(catalog.get("mine")) is not bool or type(catalog.get("open")) is not bool:
            raise HttpCoreError("Status atau kepemilikan toko belum dapat diverifikasi")
        if catalog["mine"] or not catalog["open"]:
            return catalog, []
        products = []
        for row in catalog["menu"]:
            item = row["item"]
            sold_out = row.get("habis")
            if resource in NEEDS:
                effect = effects.get(item, {})
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
                if item not in ITEMS[resource]:
                    continue
                effect = effects[item]
                if resource not in effect:
                    raise HttpCoreError("Efek produk tidak sesuai resource", recoverable=True)
            product = Product(
                name=row["name"],
                price=coin(row["priceMilli"]),
                effects=effect,
                row_text=json.dumps(
                    {"shop": shop_id, "item": item, "resource": resource}, sort_keys=True
                ),
                enabled=not bool(sold_out),
            )
            products.append(product)
        return catalog, products

    async def preview_shop(self, location, resource, effects):
        catalog, products = await self.products(location.id, resource, effects)
        if catalog.get("plang") and catalog["plang"] != location.name:
            return None
        if not any(product.enabled and product.effects[resource] > 0 for product in products):
            return None
        return ShopPreview(
            id=location.id,
            plot_id=location.plot_id,
            name=location.name,
            category=CATEGORIES[resource],
            distance_squared=(location.x - self.home["x"]) ** 2
            + (location.y - self.home["y"]) ** 2,
            products=products,
        )

    async def need_shop(self, location, resource, effects):
        catalog, products = await self.products(location.id, resource, effects)
        if catalog.get("plang") != location.name or not products:
            return None
        return ShopPreview(
            id=location.id,
            plot_id=location.plot_id,
            name=location.name,
            category=location.category,
            distance_squared=0,
            products=products,
        )

    async def read_previews(self, calls):
        tasks = [asyncio.create_task(call) for call in calls]
        try:
            return await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def akademis_need_shops(self, resource, effects):
        locations = NEED_SHOPS_BY_VILLAGE.get(self.home["desa"], {}).get(resource, ())
        shops = await self.read_previews(
            self.need_shop(location, resource, effects)
            for location in locations
            if "akademis.ai" in location.name.casefold()
        )
        sold_out = (
            bool(locations)
            and len(shops) == len(locations)
            and all(
                shop is not None and all(not product.enabled for product in shop.products)
                for shop in shops
            )
        )
        return shops, sold_out

    async def fallback_need_shop(self, resource, effects):
        village = self.home["desa"]
        fallback = NEED_FALLBACK_PLOTS.get(village, {}).get(resource)
        if fallback is None:
            return None
        plot, category = fallback
        detail = await self.request(f"/api/world/plots/{plot}?t={int(time.time() * 1000)}")
        business = detail.get("business") or {}
        name = business.get("name")
        if (
            detail.get("id") != plot
            or business.get("desa") != village
            or business.get("catalogId") != category
            or not isinstance(name, str)
            or not name.strip()
            or "akademis.ai" in name.casefold()
        ):
            return None
        identifier = str(UUID(business["id"]))
        return await self.need_shop(NeedShop(identifier, plot, name, category), resource, effects)

    async def physical_facility(self, place):
        identifier = place.get("id")
        gain = place.get("gain")
        if (
            place.get("kind") != "fasum"
            or place.get("open") is not True
            or type(place.get("priceMilli")) is not int
            or place["priceMilli"] != 0
            or type(gain) is not int
            or not 0 < gain <= 100
            or not isinstance(identifier, str)
            or not re.fullmatch(r"[a-f0-9-]{36}", identifier)
        ):
            return None
        details = await self.request(f"/api/facilities/{identifier}")
        service = details.get("service")
        if (
            details.get("id") != identifier
            or details.get("state") != "DONE"
            or details.get("nextAt")
            or details.get("myVisitUntil")
            or not isinstance(service, dict)
            or service.get("studySessions")
            or type(service.get("priceMilli")) is not int
            or service["priceMilli"] != 0
        ):
            return None
        return ShopPreview(
            id=identifier,
            plot_id=identifier,
            name=place["name"],
            category="fasum",
            distance_squared=0,
            products=[
                Product(
                    name=service["label"],
                    price=0,
                    effects={"fisik": gain},
                    row_text=json.dumps({"shop": identifier, "item": "use", "resource": "fisik"}),
                    enabled=True,
                )
            ],
        )

    async def preview(self, resource):
        if resource not in CATEGORIES and resource not in NEEDS:
            raise HttpCoreError("Resource tidak didukung", category="blocked")
        self.catalog.pop(resource, None)
        sold_out = False
        try:
            async with asyncio.timeout(25):
                if not getattr(self, "home", None):
                    await self.snapshot()
                if not self.home:
                    raise HttpCoreError("Rumah akun belum tersedia", category="blocked")
                if resource == "fisik":
                    shops = await self.read_previews(
                        self.physical_facility(place) for place in self.physical_places
                    )
                elif resource in NEEDS:
                    shops = []
                    if NEED_SHOPS_BY_VILLAGE.get(self.home["desa"], {}).get(resource):
                        effects = await self.effects(for_needs=True)
                        shops, sold_out = await self.akademis_need_shops(resource, effects)
                        if sold_out:
                            shops = [await self.fallback_need_shop(resource, effects)]
                else:
                    locations = SHOPS_BY_VILLAGE.get(self.home["desa"], {}).get(resource, ())
                    if not locations:
                        raise HttpCoreError(
                            "Toko tetap belum dikonfigurasi untuk desa akun", category="blocked"
                        )
                    effects = await self.effects()
                    shops = await self.read_previews(
                        self.preview_shop(location, resource, effects) for location in locations
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
        self.catalog[resource] = shops
        return {
            "shops": [
                shop.model_dump(mode="json")
                for shop in sorted(
                    shops.values(), key=lambda shop: (shop.distance_squared, shop.id)
                )
            ],
            "navigation": {
                "method": "fixed_catalog_http",
                "panel_verified": True,
                "travel_request_sent": False,
                **(
                    {"akademis_sold_out": sold_out}
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
        shop = self.catalog.get(resource, {}).get(shop_id)
        if (
            shop is None
            or (not is_need and identity["item"] not in ITEMS.get(resource, ()))
            or product not in shop.products
            or not product.enabled
        ):
            raise HttpCoreError("Produk tidak berasal dari preview sesi ini", category="rejected")
        try:
            async with asyncio.timeout(15 if is_need else None):
                await self.validate_purchase(
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
                isinstance(exc, HttpCoreError) and exc.category in {"auth", "rejected"}
            ):
                raise
            raise HttpCoreError(
                "Kebutuhan dilewati karena data sebelum transaksi belum terverifikasi",
                category="rejected",
            ) from exc
        self.catalog.pop(resource)
        if not auto_flags(self.directory)[resource if is_need else "ojol"]:
            raise HttpCoreError(
                "Fitur Auto dinonaktifkan sebelum pembelian", category="auto_disabled"
            )
        if resource == "fisik":
            return await self.request(f"/api/facilities/{shop_id}/use", {"requestId": request_id})
        return await self.request(
            f"/api/shops/{shop_id}/buy", {"item": identity["item"], "requestId": request_id}
        )

    async def validate_purchase(
        self, shop, resource, product, expected_wallet, expected_resource, min_balance
    ):
        shop_id = shop.id
        is_need = resource in NEEDS
        fallback = is_need and resource != "fisik" and not shop.preferred
        version = self.config_version
        if resource != "fisik":
            effects = await self.effects(for_needs=is_need)
        if resource != "fisik" and not fallback:
            catalog, fresh = await self.products(shop_id, resource, effects)
            if product not in fresh or (
                (is_need or catalog.get("plang")) and catalog.get("plang") != shop.name
            ):
                raise HttpCoreError(
                    "Nama toko atau katalog berubah sebelum pembelian", category="rejected"
                )
        state = await self.snapshot()
        if resource == "fisik":
            place = next(
                (place for place in self.physical_places if place.get("id") == shop_id), {}
            )
            eligible = await self.physical_facility(place) == shop
        elif fallback and self.home:
            _, sold_out = await self.akademis_need_shops(resource, effects)
            fresh_shop = await self.fallback_need_shop(resource, effects) if sold_out else None
            eligible = (
                fresh_shop is not None
                and fresh_shop.id == shop_id
                and fresh_shop.name == shop.name
                and product in fresh_shop.products
            )
        else:
            registry = NEED_SHOPS_BY_VILLAGE if is_need else SHOPS_BY_VILLAGE
            locations = registry.get((self.home or {}).get("desa"), {}).get(resource, ())
            eligible = any(location.id == shop_id for location in locations)
        current = state.resource_value(resource)
        if (
            state.phase != "idle"
            or state.wallet != Decimal(expected_wallet)
            or current is None
            or current != expected_resource
            or self.config_version != version
            or self.catalog.get(resource, {}).get(shop_id) is not shop
            or not eligible
        ):
            raise HttpCoreError(
                "Fase, saldo, resource atau katalog berubah sebelum pembelian", category="rejected"
            )
        if state.wallet - product.price < max(Decimal(20), Decimal(min_balance)) or (
            not is_need and current + product.effects[resource] > 100
        ):
            raise HttpCoreError("Pembelian melanggar saldo minimum/overflow", category="rejected")

    async def job_action(self, kind):
        state = await self.snapshot()
        if kind == "search" and state.phase == "idle":
            if not auto_flags(self.directory)["ojol"]:
                raise HttpCoreError(
                    "Auto Ojol dinonaktifkan sebelum mencari order", category="auto_disabled"
                )
            return await self.request("/api/ojol", {"action": "ambil", "vehicle": "motor"})
        if kind == "complete" and state.phase == "complete":
            return await self.request("/api/ojol", {"action": "selesai"})
        raise HttpCoreError("Aksi Ojol tidak sesuai state/waktu server", category="blocked")
