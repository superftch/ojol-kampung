"""Observed Ojol endpoints only. GETs may retry; writes are always one attempt."""

import asyncio
import json
import logging
import re
from datetime import datetime
from decimal import Decimal
from math import ceil
from pathlib import Path
from uuid import UUID

import httpx

from .finance import WIB, day_bounds, report_date
from .healing import write_private
from .models import Product, ShopPreview, Snapshot, now
from .planner import ALLOWED_ITEMS
from .session_transfer import DOMAIN, parse_cookie_input

ORIGIN = "https://www.kampungsebelah.com"
ITEMS = {
    "fuel": {"isi-pertalite", "isi-pertamax"},
    "condition": {"servis-motor", "ganti-oli", "tambal-ban", "isi-angin", "cuci-motor"},
    "data": {"pulsa", "paket-data", "servis-hp", "casing-hp"},
}
WALLET_PRODUCT_CATEGORIES = {
    " ".join(name.casefold().split()): resource
    for resource, names in ALLOWED_ITEMS.items()
    for name in names
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


class ShopClosed(HttpCoreError):
    pass


def is_closed_shop_response(response):
    try:
        error = response.json()["error"]
        return (
            error["code"] == "REQUIREMENT_NOT_MET" and error["message"] == "Usaha ini belum buka."
        )
    except (KeyError, TypeError, ValueError):
        return False


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


def snapshot_from_api(ojol, me, needs, server_now):
    if ojol["enabled"] is not True or ojol["mitra"] is not True:
        raise HttpCoreError("Akun belum menjadi mitra Ojol", category="blocked")
    if type(needs["asleep"]) is not bool:
        raise HttpCoreError("Status tidur API berubah", recoverable=True)
    trip = ojol["trip"]
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
    elif ojol.get("problem") and not trip:
        raise HttpCoreError("Game menolak Ojol: periksa kondisi akun di game", category="blocked")
    history = []
    for receipt in ojol["history"]:
        done = timestamp(receipt["doneAt"]).astimezone(WIB)
        icon, _ = KINDS[receipt["kind"]]
        history.append(
            f"{done:%H.%M} {icon} {receipt['from']['label']} → {receipt['to']['label']} · +{display(coin(receipt['netMilli']))}"
        )
    return Snapshot(
        observed_at=server_now,
        wallet=coin(me["balanceMilli"]),
        fuel=integer(ojol["bars"]["bensin"]),
        condition=integer(ojol["bars"]["kendaraan"]),
        data=integer(ojol["bars"]["kuota"]),
        phase=phase,
        remaining_seconds=remaining,
        trip=description,
        today_income=coin(ojol["earnedTodayMilli"]),
        history=history,
        buttons=buttons,
        raw_text=text,
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


class OjolHttpApi:
    def __init__(self, directory: Path, session_file=None, client=None):
        self.directory = directory
        self.session_file = session_file or directory / "http-session.json"
        self.client = client
        self.owns_client = client is None
        self.catalog = {}
        self.retries = 0

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

    async def request(self, path, payload=None, text=False, *, after=None):
        # No caller-provided URLs, redirects, or generic HTTP MCP tool.
        allowed = (
            path
            in {
                "/api/ojol",
                "/api/game/me",
                "/api/me/koin",
                "/api/kebutuhan",
                "/api/time",
                "/api/tujuan",
                "/kampung",
            }
            or re.fullmatch(r"/api/world/plots/[A-Z][0-9]{2}-[A-Z][0-9]{2}", path)
            or re.fullmatch(r"/api/shops/[a-f0-9-]{36}(?:/buy)?", path)
            or re.fullmatch(r"/_next/static/[a-zA-Z0-9_./-]+\.js", path)
        )
        if (
            not allowed
            or (after is not None and (path != "/api/me/koin" or not self.valid_cursor(after)))
            or ".." in path.split("/")
            or "//" in path
            or (payload is not None and path != "/api/ojol" and not path.endswith("/buy"))
        ):
            raise HttpCoreError("Endpoint di luar izin Ojol", category="blocked")
        for attempt in range(3 if payload is None else 1):
            try:
                response = await self.client.request(
                    "GET" if payload is None else "POST",
                    path,
                    json=payload,
                    **({"params": {"after": after}} if after is not None else {}),
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
                if (
                    response.status_code == 409
                    and re.fullmatch(r"/api/shops/[a-f0-9-]{36}", path)
                    and is_closed_shop_response(response)
                ):
                    raise ShopClosed("Toko tutup menurut game", category="blocked")
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

    @staticmethod
    def valid_cursor(value):
        return isinstance(value, str) and 0 < len(value) <= 2048

    async def daily_wallet(self, day):
        day = report_date(day)
        start, end = map(datetime.fromisoformat, day_bounds(day))
        read_at = now()
        result = {
            "income_milli": 0,
            "payout_count": 0,
            "expenses_milli": {},
            "expense_issue": None,
            "complete": False,
            "today_income_milli": None,
            "issue": "Riwayat belum mencapai awal hari",
        }
        if start > read_at:
            result["issue"] = "Tanggal tersebut belum tiba"
            return result

        cursor = None
        seen_cursors = set()
        seen_entries = {}
        previous = None
        try:
            async with asyncio.timeout(12):
                if day == read_at.astimezone(WIB).date():
                    try:
                        ojol = await self.request("/api/ojol")
                        result["today_income_milli"] = integer(ojol["earnedTodayMilli"])
                    except (HttpCoreError, KeyError, TypeError):
                        pass

                for _ in range(10):
                    page = await self.request("/api/me/koin", after=cursor)
                    items, next_cursor = page["items"], page["next"]
                    if not isinstance(items, list) or (
                        next_cursor is not None and not self.valid_cursor(next_cursor)
                    ):
                        raise ValueError("Invalid wallet page")

                    for row in items:
                        identifier, kind = row["id"], row["type"]
                        at, amount = timestamp(row["at"]), row["amountMilli"]
                        if (
                            not isinstance(identifier, str)
                            or not identifier
                            or not isinstance(kind, str)
                            or not kind
                            or type(amount) is not int
                            or (kind == "OJOL_ONGKOS" and amount < 0)
                        ):
                            raise ValueError("Invalid wallet entry")

                        in_day = start <= at < end and at <= read_at
                        purchase = in_day and kind == "SHOP_PURCHASE" and amount < 0
                        detail = row.get("detail") if purchase else None
                        product = (
                            " ".join(detail.casefold().split()) if isinstance(detail, str) else None
                        )
                        entry = (at, kind, amount, product)
                        if identifier in seen_entries:
                            if seen_entries[identifier] != entry:
                                raise ValueError("Conflicting wallet entry")
                            continue
                        if previous is not None and at > previous:
                            raise ValueError("Wallet entries out of order")
                        previous = at
                        seen_entries[identifier] = entry
                        if in_day and kind == "OJOL_ONGKOS":
                            result["income_milli"] += amount
                            result["payout_count"] += 1
                        if purchase:
                            if not product:
                                result["expense_issue"] = (
                                    "Ada belanja tanpa nama produk yang dapat dibaca"
                                )
                            elif product in WALLET_PRODUCT_CATEGORIES:
                                resource = WALLET_PRODUCT_CATEGORIES[product]
                                expenses = result["expenses_milli"]
                                expenses[resource] = expenses.get(resource, 0) - amount

                    if next_cursor is not None and next_cursor in seen_cursors:
                        result["issue"] = "Cursor riwayat berulang"
                        break
                    if previous is not None and previous < start:
                        result.update(complete=True, issue=None)
                        break
                    if next_cursor is None:
                        break
                    seen_cursors.add(next_cursor)
                    cursor = next_cursor
                else:
                    result["issue"] = "Batas 10 halaman tercapai"
        except TimeoutError:
            result["issue"] = "Batas waktu pembacaan riwayat tercapai"
        except HttpCoreError as exc:
            result["issue"] = (
                "Sesi game ditolak atau kedaluwarsa"
                if exc.category == "auth"
                else "Riwayat koin tidak dapat dibaca"
            )
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
            result["issue"] = "Format atau urutan riwayat koin belum dapat diverifikasi"
        return result

    async def snapshot(self):
        ojol, me, needs, clock = await asyncio.gather(
            *(
                self.request(path)
                for path in ("/api/ojol", "/api/game/me", "/api/kebutuhan", "/api/time")
            )
        )
        self.config_version = me["configVersion"]
        self.home = me["home"]
        self.vehicle = ojol["vehicle"]
        # The server clock, not the machine's timezone/clock, gates completion.
        state = snapshot_from_api(ojol, me, needs, timestamp(clock["now"]))
        if self.vehicle != "motor":
            raise HttpCoreError("Core HTTP hanya untuk Ojol motor", category="blocked")
        return state

    async def effects(self):
        version = getattr(self, "config_version", None)
        if version is None:
            await self.snapshot()
            version = self.config_version
        cache = self.directory / "http-effects.json"
        if cache.is_file():
            data = json.loads(cache.read_text())
            if data.get("version") == version:
                return data["effects"]
        html = await self.request("/kampung", text=True)
        effects = {}
        for path in re.findall(r"<script[^>]+src=[\"\x27]([^\"\x27]+)", html):
            if not path.startswith("/_next/static/"):
                continue
            source = await self.request(path, text=True)
            found = extract_effects(source)
            if any(item in effects and effects[item] != value for item, value in found.items()):
                raise HttpCoreError("Efek produk antar bundle berbeda", recoverable=True)
            effects.update(found)
            if set.union(*ITEMS.values()) <= effects.keys():
                break
        if not set.union(*ITEMS.values()) <= effects.keys():
            raise HttpCoreError("Efek produk client belum dapat diverifikasi", recoverable=True)
        write_private(cache, {"version": version, "effects": effects})
        return effects

    async def products(self, shop_id, resource, effects):
        catalog = await self.request("/api/shops/" + shop_id)
        if type(catalog.get("mine")) is not bool or type(catalog.get("open")) is not bool:
            raise HttpCoreError("Status atau kepemilikan toko belum dapat diverifikasi")
        if catalog["mine"] or not catalog["open"]:
            return catalog, []
        products = []
        for row in catalog["menu"]:
            item = row["item"]
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
                enabled=not bool(row.get("habis")),
            )
            products.append(product)
        return catalog, products

    async def preview_shop(self, row, resource, effects):
        plot = await self.request("/api/world/plots/" + row["plotId"])
        business = plot["business"]
        if business is None or business["desa"] != self.home["desa"]:
            return None
        category = business["catalogId"]
        if category != row["item"]:
            return None
        shop_id = str(UUID(business["id"]))
        try:
            catalog, products = await self.products(shop_id, resource, effects)
        except ShopClosed:
            return None
        if not any(product.enabled and product.effects[resource] > 0 for product in products):
            return None
        shop = ShopPreview(
            id=shop_id,
            plot_id=row["plotId"],
            name=catalog.get("plang") or business["name"],
            category=category,
            distance_squared=(row["x"] - self.home["x"]) ** 2 + (row["y"] - self.home["y"]) ** 2,
            products=products,
        )
        if category != CATEGORIES[resource] and not shop.preferred:
            return None
        return shop

    async def preview(self, resource):
        if resource not in CATEGORIES:
            raise HttpCoreError("Resource tidak didukung", category="blocked")
        self.catalog.pop(resource, None)
        categories = {CATEGORIES[resource]}
        if resource == "condition":
            categories.add(CATEGORIES["fuel"])
        shops = {}
        try:
            async with asyncio.timeout(25):
                if not getattr(self, "home", None):
                    await self.snapshot()
                if not self.home:
                    raise HttpCoreError("Rumah akun belum tersedia", category="blocked")
                places = await self.request("/api/tujuan")
                matches = [row for row in places["usaha"] if row["item"] in categories]
                if matches:
                    effects = await self.effects()
                    for offset in range(0, len(matches), 4):
                        results = await asyncio.gather(
                            *(
                                self.preview_shop(row, resource, effects)
                                for row in matches[offset : offset + 4]
                            ),
                            return_exceptions=True,
                        )
                        for shop in results:
                            if isinstance(shop, BaseException):
                                raise shop
                            if shop is not None:
                                shops[shop.id] = shop
        except TimeoutError:
            raise HttpCoreError(
                "Deadline preview toko tercapai sebelum katalog terverifikasi",
                category="transport",
                recoverable=True,
            ) from None
        self.catalog[resource] = shops
        return {
            "shops": [
                shop.model_dump(mode="json")
                for shop in sorted(
                    shops.values(), key=lambda shop: (shop.distance_squared, shop.id)
                )
            ],
            "navigation": {
                "method": "eye_preview_http",
                "panel_verified": True,
                "travel_request_sent": False,
            },
        }

    async def purchase(self, product, expected_wallet, expected_resource, min_balance, request_id):
        request_id = str(UUID(request_id))
        product = Product.model_validate(product)
        identity = json.loads(product.row_text)
        shop_id = str(UUID(identity["shop"]))
        resource = identity["resource"]
        shop = self.catalog.get(resource, {}).get(shop_id)
        if (
            shop is None
            or identity["item"] not in ITEMS[resource]
            or product not in shop.products
            or not product.enabled
        ):
            raise HttpCoreError("Produk tidak berasal dari preview sesi ini", category="blocked")
        state = await self.snapshot()
        if (
            state.phase != "idle"
            or state.wallet != Decimal(expected_wallet)
            or getattr(state, resource) != expected_resource
        ):
            raise HttpCoreError(
                "Fase, saldo atau resource berubah sebelum pembelian", category="blocked"
            )
        catalog, fresh = await self.products(shop_id, resource, await self.effects())
        if product not in fresh or (catalog.get("plang") and catalog["plang"] != shop.name):
            raise HttpCoreError(
                "Nama toko atau katalog berubah sebelum pembelian", category="blocked"
            )
        if (
            state.wallet - product.price < max(Decimal(20), Decimal(min_balance))
            or getattr(state, resource) + product.effects[resource] > 100
        ):
            raise HttpCoreError("Pembelian melanggar saldo minimum/overflow", category="blocked")
        self.catalog.pop(resource)
        return await self.request(
            f"/api/shops/{shop_id}/buy", {"item": identity["item"], "requestId": request_id}
        )

    async def job_action(self, kind):
        state = await self.snapshot()
        if kind == "search" and state.phase == "idle":
            return await self.request("/api/ojol", {"action": "ambil", "vehicle": "motor"})
        if kind == "complete" and state.phase == "complete":
            return await self.request("/api/ojol", {"action": "selesai"})
        raise HttpCoreError("Aksi Ojol tidak sesuai state/waktu server", category="blocked")
