"""Observed Ojol endpoints only. GETs may retry; writes are always one attempt."""

import asyncio
import hashlib
import json
import logging
import random
import re
import secrets
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

import httpx

from .auto_settings import auto_flags
from .cookies import DOMAIN, parse_cookie_input, session_expired
from .formatting import display_coin as display
from .formatting import parse_api_timestamp as timestamp
from .game_parsers import (
    CAR_SERVICE,
    CATEGORIES,
    EV_CHARGE,
    ITEMS,
    KAMAR_MANDI_ID,
    KINDS,
    ORIGIN,
    RESOURCES,
    VEHICLE_ICONS,
    WALLET_PRODUCT_CATEGORIES,
    HouseUnavailable,
    ShopClosed,
    coin,
    extract_effects,
    extract_need_effects,
    integer,
    is_closed_shop_response,
    is_unavailable_house_response,
    need_rows,
    ojol_vehicle,
    snapshot_from_api,
)
from .game_wallet import WalletReport, read_daily_wallet, valid_cursor
from .identity import save_profile, verified_profile
from .models import (
    AUTO_SUBJECT,
    NEEDS,
    STUDY_LABELS,
    SUBJECTS,
    HttpCoreError,
    Need,
    Product,
    Resource,
    ShopPreview,
    Snapshot,
    now,
)
from .recreation import solve_foto_shots
from .shop_locations import (
    BPJS_KANTOR_BY_VILLAGE,
    GYM_FACILITIES_BY_VILLAGE,
    HEALTH_FACILITIES_BY_VILLAGE,
    NEED_SHOP_CATEGORIES,
    NEED_SHOPS_BY_VILLAGE,
    RECREATION_FACILITIES_BY_VILLAGE,
    SHOPS_BY_VILLAGE,
    SPPG_FACILITIES_BY_VILLAGE,
    STUDY_FACILITIES_BY_VILLAGE,
    NeedShop,
    ShopLocation,
)
from .sppg import solve_nampan_picks
from .storage import write_private
from .study import (
    extract_quiz_bank,
    is_track_max,
    quiz_answers,
    save_skills,
    subjects,
)

__all__ = [
    "AUTO_SUBJECT",
    "CAR_SERVICE",
    "CATEGORIES",
    "DOMAIN",
    "EV_CHARGE",
    "ITEMS",
    "KAMAR_MANDI_ID",
    "KINDS",
    "ORIGIN",
    "RESOURCES",
    "STUDY_LABELS",
    "SUBJECTS",
    "VEHICLE_ICONS",
    "WALLET_PRODUCT_CATEGORIES",
    "HouseUnavailable",
    "HttpCoreError",
    "OjolHttpApi",
    "ShopClosed",
    "coin",
    "display",
    "ensure_browser_identity",
    "extract_effects",
    "extract_need_effects",
    "integer",
    "is_closed_shop_response",
    "is_unavailable_house_response",
    "need_rows",
    "ojol_vehicle",
    "parse_cookie_input",
    "session_expired",
    "snapshot_from_api",
    "timestamp",
]

OJOL_DIRECTORY_RESOURCES = {"condition", "data"}

BROWSER_PROFILES = [
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"macOS"',
    },
    {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"macOS"',
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        "sec_ch_ua": '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
    },
    {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
    },
]

ACCEPT_VARIANTS = [
    "application/json, text/plain, */*",
    "*/*",
    "application/json",
    "application/json, text/javascript, */*; q=0.01",
]

ACCEPT_LANGUAGE_VARIANTS = [
    "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "id-ID,id;q=0.9,en;q=0.8",
    "id,en-US;q=0.9,en;q=0.8",
    "id-ID,id;q=0.8,en-US;q=0.6,en;q=0.4",
    "en-US,en;q=0.9,id;q=0.8",
]

PRIORITY_VARIANTS = [
    "u=1, i",
    "u=1",
]

CACHE_CONTROL_VARIANTS = [
    "no-cache",
    "max-age=0",
    "no-cache, no-store, max-age=0",
]


def ensure_browser_identity(directory: Path) -> dict:
    identity_file = directory / "browser-identity.json"
    if identity_file.is_file():
        try:
            data = json.loads(identity_file.read_text())
            if isinstance(data, dict) and data.get("user_agent"):
                return data
        except (OSError, ValueError):
            pass

    index = int(hashlib.sha256(str(directory).encode()).hexdigest(), 16) % len(BROWSER_PROFILES)
    identity = dict(BROWSER_PROFILES[index])
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_private(identity_file, identity)
    except OSError:
        pass
    return identity


class OjolHttpApi:
    def __init__(self, directory: Path, session_file=None, client=None):
        self.directory = Path(directory)
        self.session_file = session_file or self.directory / "http-session.json"
        self.client = client
        self.owns_client = client is None
        self.catalog = {}
        self.vehicle = None
        self.usage = None
        self.retries = 0
        self.expires_at = None
        self.browser_identity = ensure_browser_identity(self.directory)

    def _session_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise HttpCoreError("Sesi game belum dibuka. Gunakan Import Cookie.", category="auth")
        return self.client

    def browser_headers(self, path: str, method: str = "GET") -> dict:
        is_html = path == "/kampung"
        is_script = path.endswith(".js")
        headers = {
            "User-Agent": self.browser_identity["user_agent"],
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                if is_html
                else ("*/*" if is_script else secrets.choice(ACCEPT_VARIANTS))
            ),
            "Accept-Language": secrets.choice(ACCEPT_LANGUAGE_VARIANTS),
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate" if is_html else ("no-cors" if is_script else "cors"),
            "Sec-Fetch-Dest": "document" if is_html else ("script" if is_script else "empty"),
            "Origin": ORIGIN,
            "Referer": f"{ORIGIN}/kampung",
            "Cache-Control": secrets.choice(CACHE_CONTROL_VARIANTS),
        }
        if "sec_ch_ua" in self.browser_identity:
            headers["sec-ch-ua"] = self.browser_identity["sec_ch_ua"]
        if "sec_ch_ua_mobile" in self.browser_identity:
            headers["sec-ch-ua-mobile"] = self.browser_identity["sec_ch_ua_mobile"]
        if "sec_ch_ua_platform" in self.browser_identity:
            headers["sec-ch-ua-platform"] = self.browser_identity["sec_ch_ua_platform"]
        if not is_html and not is_script:
            headers["Priority"] = secrets.choice(PRIORITY_VARIANTS)
        return headers

    async def __aenter__(self):
        logging.getLogger("httpx").setLevel(logging.WARNING)
        if self.client is None:
            try:
                payload = parse_cookie_input(self.session_file.read_text())
            except (OSError, ValueError, TypeError, KeyError):
                raise HttpCoreError(
                    "Sesi game belum ada. Tekan Import Cookie dulu.", category="auth"
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
                timeout=10,
                headers={
                    "User-Agent": self.browser_identity["user_agent"],
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
        # No caller-provided URLs, redirects, or generic HTTP tool.
        house_view = re.fullmatch(
            r"/api/rumah/interior/lihat\?plotId=[A-Z][0-9]{2}-[A-Z][0-9]{2}", path
        )
        minigame_view = bool(
            re.fullmatch(r"/api/minigame\?projectId=[a-f0-9-]{36}&game=[a-zA-Z0-9_-]+", path)
        )
        garden_action = bool(re.fullmatch(r"/api/daily/garden/[a-zA-Z0-9_-]+", path))
        ojol_cek_image = bool(
            re.fullmatch(r"/api/ojol/cek\?t=[A-Za-z0-9-]{1,64}&a=[0-9TZ:.+-]+&m=[0-9]{1,3}", path)
        )
        allowed = (
            ojol_cek_image
            or path
            in {
                "/api/ojol",
                "/api/kendaraan",
                "/api/game/me",
                "/api/me/koin",
                "/api/kebutuhan",
                "/api/kebutuhan?tempat=fisik",
                "/api/minigame",
                "/api/time",
                "/api/tujuan",
                "/kampung",
                "/api/bpjs",
                "/api/bpjs/bayar",
                "/api/daily/garden",
                "/api/realtime/token",
                "/api/rumah/kamar-mandi",
                "/api/rumah/interior",
                "/api/diving",
                "/api/diving/realtime",
            }
            or re.fullmatch(
                r"/api/world/plots\?v=2&blocks=[A-Z][0-9]{2}(?:,[A-Z][0-9]{2}){0,23}", path
            )
            or re.fullmatch(r"/api/shops/[a-f0-9-]{36}(?:/buy)?", path)
            or re.fullmatch(r"/api/daily/house\?plotId=[A-Z][0-9]{2}-[A-Z][0-9]{2}", path)
            or house_view
            or minigame_view
            or re.fullmatch(r"/api/world/plots/[A-Z][0-9]{2}-U[0-9]{2}\?t=[0-9]{1,15}", path)
            or re.fullmatch(r"/api/facilities/[a-f0-9-]{36}(?:/(?:use|kuis|kegiatan))?", path)
            or re.fullmatch(r"/api/spbu/[A-Z0-9-]+", path)
            or garden_action
            or re.fullmatch(r"/_next/static/[a-zA-Z0-9_./-]+\.js", path)
        )
        if (
            not allowed
            or (after is not None and (path != "/api/me/koin" or not self.valid_cursor(after)))
            or ".." in path.split("/")
            or "//" in path
            or (
                payload is not None
                and path not in {"/api/ojol", "/api/rumah/kamar-mandi", "/api/diving"}
                and not garden_action
                and not re.fullmatch(r"/api/spbu/[A-Z0-9-]+", path)
                and not path.endswith(("/buy", "/use", "/kuis", "/bayar", "/kegiatan", "/minigame"))
            )
        ):
            raise HttpCoreError("Endpoint di luar izin Ojol", category="blocked")
        if self.expires_at is not None and self.expires_at <= time.time():
            raise HttpCoreError("Cookie sesi game sudah kedaluwarsa.", category="auth")
        for attempt in range(3 if payload is None else 1):
            headers = self.browser_headers(path, "GET" if payload is None else "POST")
            try:
                response = await self._session_client().request(
                    "GET" if payload is None else "POST",
                    path,
                    json=payload,
                    headers=headers,
                    params={"after": after} if after is not None else None,
                )
            except httpx.TransportError:
                if payload is not None:
                    raise HttpCoreError(
                        "Request transaksi terputus; hasil belum pasti, tidak diulang",
                        category="uncertain",
                    ) from None
                response = None
            if response is not None:
                if house_view and is_unavailable_house_response(response):
                    raise HouseUnavailable(
                        "Rumah belum menerima tamu untuk akun ini", category="blocked"
                    )
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
                await asyncio.sleep((attempt + 1) * 1.5)
        raise HttpCoreError(
            "Pembacaan HTTP gagal setelah 3 percobaan", category="transport", recoverable=True
        )

    valid_cursor = staticmethod(valid_cursor)

    async def daily_wallet(self, day: date | str) -> WalletReport:
        return await read_daily_wallet(self.request, day, now())

    async def snapshot(self):
        flags = auto_flags(self.directory)
        has_kebutuhan = any(flags.get(k) for k in flags if k != "ojol")
        ojol = None
        ojol_error = None
        try:
            ojol = await self.request("/api/ojol")
        except HttpCoreError as exc:
            if has_kebutuhan:
                ojol_error = exc
                ojol = {"enabled": False, "mitra": False, "bars": {}, "pakai": {}}
            else:
                raise
        me, needs, clock = await asyncio.gather(
            *(self.request(path) for path in ("/api/game/me", "/api/kebutuhan", "/api/time"))
        )
        self.config_version = me["configVersion"]
        self.home = me["home"]
        self.me = me
        if (me.get("profile") or {}).get("nickname") is not None:
            save_profile(self.directory, verified_profile(me))
        if isinstance(me.get("skill"), dict) and isinstance(me["skill"].get("tracks"), list):
            save_skills(self.directory, me["skill"]["tracks"])
        places = need_rows(needs).get("fisik", {}).get("places")
        self.physical_places = (
            [place for place in places if isinstance(place, dict)]
            if isinstance(places, list)
            else []
        )
        # The server clock, not the machine's timezone/clock, gates completion.
        require_ojol = (flags["ojol"] or bool((ojol or {}).get("trip"))) and not (
            has_kebutuhan and ojol_error is not None
        )
        try:
            state = snapshot_from_api(
                ojol, me, needs, timestamp(clock["now"]), require_ojol=require_ojol
            )
        except HttpCoreError as exc:
            if has_kebutuhan and "mitra Ojol" in str(exc):
                self.ojol_failure_error = exc
                state = snapshot_from_api(
                    ojol, me, needs, timestamp(clock["now"]), require_ojol=False
                )
            else:
                raise
        if ojol_error is not None:
            self.ojol_failure_error = ojol_error
        self.vehicle = state.ojol_vehicle
        self.usage = ojol.get("pakai")
        self.last_ojol_data = ojol
        status_file = self.directory / "online-status.json"
        write_private(
            status_file,
            {
                "online": True,
                "nickname": (me.get("profile") or {}).get("nickname"),
                "server_time": clock.get("now"),
                "balance_milli": me.get("balanceMilli"),
                "resting": (me.get("profile") or {}).get("resting", False),
                "sleep": (me.get("profile") or {}).get("sleep"),
                "fetched_at": now().isoformat(),
            },
        )
        return state

    async def fetch_online_status(self):
        """Fetch online presence endpoints (/api/game/me, /api/time, /api/realtime/token).

        Touches the session on KampungSebelah, keeping the player within the
        online window (120s) and writing online status to online-status.json.
        """
        me, clock = await asyncio.gather(
            self.request("/api/game/me"),
            self.request("/api/time"),
        )
        rt = None
        try:
            rt = await self.request("/api/realtime/token")
        except Exception:
            pass

        self.config_version = me.get("configVersion")
        self.home = me.get("home")
        profile = me.get("profile") or {}
        if profile.get("nickname") is not None:
            save_profile(self.directory, verified_profile(me))

        status_info = {
            "online": True,
            "nickname": profile.get("nickname"),
            "server_time": clock.get("now"),
            "balance_milli": me.get("balanceMilli"),
            "resting": profile.get("resting", False),
            "sleep": profile.get("sleep"),
            "realtime_connected": bool(rt and isinstance(rt, dict) and rt.get("url")),
            "fetched_at": now().isoformat(),
        }
        status_file = self.directory / "online-status.json"
        write_private(status_file, status_info)
        return status_info

    async def resource_items(self, resource):
        if self.vehicle == "mobil" and resource == "condition":
            return ITEMS[resource] | {CAR_SERVICE}
        if resource == "fuel" and self.vehicle == "mobil":
            garage = (await self.request("/api/kendaraan")).get("items")
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
        shops = SHOPS_BY_VILLAGE.get((self.home or {}).get("desa"), {})
        locations = tuple(shops.get(resource, ()))
        if resource == "condition" and self.vehicle == "mobil":
            locations += tuple(shops.get("fuel", ()))
        return tuple(dict.fromkeys(locations))

    async def effects(self, *, for_needs=False, required_items=()):
        version = getattr(self, "config_version", None)
        if version is None:
            await self.snapshot()
            version = self.config_version
        cache = self.directory / "http-effects.json"
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
            ):
                if for_needs or required <= data[key].keys():
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
        catalog = await self.request("/api/shops/" + shop_id)
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
            catalog, products = await self.products(location.id, resource, effects, allowed_items)
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
            distance_squared=(location.x - self.home["x"]) ** 2
            + (location.y - self.home["y"]) ** 2,
            products=products,
        )

    async def need_shop(self, location, resource, effects):
        try:
            catalog, products = await self.products(location.id, resource, effects)
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
        detail = await self.request(f"/api/world/plots/{plot}?t={int(time.time() * 1000)}")
        business = detail.get("business") if isinstance(detail, dict) else None
        if not isinstance(business, dict) or detail.get("id") != plot:
            raise HttpCoreError("Detail plot usaha berubah", category="schema")
        if business.get("desa") != self.home["desa"]:
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
        directory = await self.request("/api/tujuan")
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
            distance = (row["x"] - self.home["x"]) ** 2 + (row["y"] - self.home["y"]) ** 2
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
            shop = await self.preview_shop(location, resource, effects, allowed_items)
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
            getattr(self, "akademis_need_shops", None) is not None
            and self.akademis_need_shops != self.need_suppliers
        ):
            return await self.akademis_need_shops(resource, effects, preferred_only=preferred_only)
        village = self.home["desa"]
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

    akademis_need_shops = need_suppliers

    minigame_wait_multiplier: float = 1.0

    async def _minigame_wait(self, seconds: float) -> None:
        wait_time = seconds * getattr(self, "minigame_wait_multiplier", 1.0)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

    async def complete_minigame(self, facility_id, game, request_id):
        start_payload = {
            "action": "start",
            "projectId": facility_id,
            "requestId": request_id,
            "game": game,
        }
        started = await self.request("/api/minigame", start_payload)
        if not isinstance(started, dict):
            raise HttpCoreError("Respons start minigame tidak valid", category="rejected")
        play_id = started.get("playId")
        if not play_id:
            raise HttpCoreError("Play ID minigame tidak ditemukan", category="rejected")

        if game == "gym":
            plan = started.get("plan")
            reps = plan.get("reps") if isinstance(plan, dict) else plan
            if not isinstance(reps, list) or not reps:
                raise HttpCoreError("Plan minigame gym tidak valid", category="rejected")

            holds = []
            for rep in reps:
                fill = rep.get("fill", 1400)
                center = rep.get("center", 0.7)
                hold = round(fill * center)
                holds.append(hold)

            total_hold_seconds = sum(holds) / 1000.0
            pause_seconds = (len(holds) - 1) * 1.1 if len(holds) > 1 else 0.0
            total_wait = total_hold_seconds + pause_seconds
            await self._minigame_wait(total_wait)

            finish_payload = {
                "action": "finish",
                "playId": play_id,
                "holds": holds,
            }
            result = await self.request("/api/minigame", finish_payload)
            if not isinstance(result, dict):
                raise HttpCoreError("Respons finish minigame tidak valid", category="rejected")
            detail = result.get("detail") or {}
            if detail.get("invalid"):
                raise HttpCoreError("Minigame tidak sah (terlalu cepat)", category="rejected")
            if detail.get("expired"):
                raise HttpCoreError("Minigame kedaluwarsa", category="rejected")
            return result

        raise HttpCoreError(f"Minigame {game} belum didukung", category="blocked")

    async def gym_facility(self, identifier, effects=None):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9-]{36}", identifier):
            return None
        try:
            details = await self.request(f"/api/facilities/{identifier}")
        except HttpCoreError:
            return None
        service = details.get("service")
        if (
            details.get("id") != identifier
            or details.get("state") != "DONE"
            or not isinstance(service, dict)
            or service.get("open") is not True
        ):
            return None
        item = re.sub(r"-t[0-9]+$", "", details.get("item", ""))
        products = []
        if item in {"gym-desa", "gym-mini-desa"}:
            try:
                minigame = await self.request(f"/api/minigame?projectId={identifier}&game=gym")
            except HttpCoreError:
                minigame = None
            if isinstance(minigame, dict) and minigame.get("playsLeft", 0) > 0:
                mg_name = minigame.get("name") or "Angkat beban"
                mg_gain = (minigame.get("kebutuhan") or {}).get("fisik", 15)
                products.append(
                    Product(
                        name=mg_name,
                        price=Decimal(0),
                        effects={"fisik": mg_gain},
                        row_text=json.dumps(
                            {
                                "shop": identifier,
                                "item": "minigame",
                                "game": "gym",
                                "resource": "fisik",
                            }
                        ),
                        enabled=True,
                    )
                )
        if (
            not details.get("nextAt")
            and not details.get("myVisitUntil")
            and type(service.get("priceMilli")) is int
        ):
            effect = (effects or {}).get(item, {})
            gain = effect.get("fisik", 55)
            products.append(
                Product(
                    name=service["label"],
                    price=coin(service["priceMilli"]),
                    effects=effect or {"fisik": gain},
                    row_text=json.dumps({"shop": identifier, "item": "use", "resource": "fisik"}),
                    enabled=True,
                )
            )
        if not products:
            return None
        return ShopPreview(
            id=identifier,
            plot_id=identifier,
            name=details.get("title", "Gym desa"),
            category="fasum",
            distance_squared=0,
            products=products,
        )

    async def gym_plays_left(self) -> int:
        village = (self.home or {}).get("desa")
        gym_ids = list(GYM_FACILITIES_BY_VILLAGE.get(village, ()))
        for fid in gym_ids:
            try:
                minigame = await self.request(f"/api/minigame?projectId={fid}&game=gym")
                if isinstance(minigame, dict) and "playsLeft" in minigame:
                    return int(minigame.get("playsLeft", 0))
            except HttpCoreError:
                continue
        if not self.physical_places:
            try:
                tempat = await self.request("/api/kebutuhan?tempat=fisik")
                self.physical_places = [
                    p for p in tempat.get("places", []) if p.get("kind") == "fasum"
                ]
            except HttpCoreError:
                self.physical_places = []
        for place in self.physical_places:
            fid = place.get("id")
            if fid:
                try:
                    minigame = await self.request(f"/api/minigame?projectId={fid}&game=gym")
                    if isinstance(minigame, dict) and "playsLeft" in minigame:
                        return int(minigame.get("playsLeft", 0))
                except HttpCoreError:
                    continue
        return 0

    async def physical_facility(self, place, effects=None):
        identifier = place.get("id")
        gain = place.get("gain")
        if (
            place.get("kind") != "fasum"
            or place.get("open") is not True
            or type(place.get("priceMilli")) is not int
            or place["priceMilli"] < 0
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
            or not isinstance(service, dict)
            or service.get("studySessions")
            or service.get("open") is not True
        ):
            return None
        item = re.sub(r"-t[0-9]+$", "", details.get("item", ""))
        products = []
        if item in {"gym-desa", "gym-mini-desa"}:
            try:
                minigame = await self.request(f"/api/minigame?projectId={identifier}&game=gym")
            except HttpCoreError:
                minigame = None
            if isinstance(minigame, dict) and minigame.get("playsLeft", 0) > 0:
                mg_name = minigame.get("name") or "Angkat beban"
                mg_gain = (minigame.get("kebutuhan") or {}).get("fisik", 15)
                products.append(
                    Product(
                        name=mg_name,
                        price=Decimal(0),
                        effects={"fisik": mg_gain},
                        row_text=json.dumps(
                            {
                                "shop": identifier,
                                "item": "minigame",
                                "game": "gym",
                                "resource": "fisik",
                            }
                        ),
                        enabled=True,
                    )
                )
        if (
            not details.get("nextAt")
            and not details.get("myVisitUntil")
            and type(service.get("priceMilli")) is int
            and service["priceMilli"] == place["priceMilli"]
        ):
            effect: dict[Need | Resource, int] = (effects or {}).get(item, {})
            if effect.get("fisik") != gain:
                effect = {"fisik": gain}
            products.append(
                Product(
                    name=service["label"],
                    price=coin(service["priceMilli"]),
                    effects=effect,
                    row_text=json.dumps({"shop": identifier, "item": "use", "resource": "fisik"}),
                    enabled=True,
                )
            )
        if not products:
            return None
        return ShopPreview(
            id=identifier,
            plot_id=identifier,
            name=place["name"],
            category="fasum",
            distance_squared=0,
            products=products,
        )

    async def study_status(self, mode):
        if mode not in STUDY_LABELS:
            raise HttpCoreError("Type belajar tidak didukung", category="blocked")
        me = await self.request("/api/game/me")
        self.config_version = me["configVersion"]
        identifier = STUDY_FACILITIES_BY_VILLAGE.get((me.get("home") or {}).get("desa"), {}).get(
            mode
        )
        if identifier is None:
            raise HttpCoreError(
                "Fasilitas belajar desa akun belum terverifikasi", category="blocked"
            )
        facility, quiz = await asyncio.gather(
            self.request(f"/api/facilities/{identifier}"),
            self.request(f"/api/facilities/{identifier}/kuis"),
        )
        service = facility.get("service") or {}
        expected_item = "perpustakaan-desa" if mode == "perpus" else "universitas"
        if (
            facility.get("id") != identifier
            or re.sub(r"-t[0-9]+$", "", facility.get("item", "")) != expected_item
            or facility.get("state") != "DONE"
            or type(service.get("priceMilli")) is not int
            or service["priceMilli"] < 0
            or (mode == "perpus" and service["priceMilli"] != 0)
            or (mode == "kuliah" and service["priceMilli"] == 0)
            or type(service.get("studySessions")) is not int
            or service["studySessions"] <= 0
            or type(quiz.get("available")) is not bool
        ):
            raise HttpCoreError("Fasilitas/tarif belajar belum terverifikasi", category="schema")
        if isinstance(me.get("skill"), dict) and isinstance(me["skill"].get("tracks"), list):
            save_skills(self.directory, me["skill"]["tracks"])
        return {"facility": facility, "quiz": quiz, "tracks": me["skill"]["tracks"]}

    async def quiz_bank(self):
        cache = self.directory / "http-quiz-bank.json"
        version = self.config_version
        if cache.is_file():
            saved = json.loads(cache.read_text())
            if saved.get("version") == version and saved.get("tracks"):
                return saved["tracks"]
        html = await self.request("/kampung", text=True)
        for path in re.findall(r"<script[^>]+src=[\"\x27]([^\"\x27]+)", html):
            if not path.startswith("/_next/static/"):
                continue
            bank = extract_quiz_bank(await self.request(path, text=True))
            if bank:
                write_private(cache, {"version": version, "tracks": bank})
                return bank
        raise HttpCoreError("Bacaan dan bank soal client belum terverifikasi", category="schema")

    async def study_start(
        self, mode, track, expected_price, expected_wallet, min_balance, request_id
    ):
        request_id = str(UUID(request_id))
        if track not in SUBJECTS or subjects(self.directory).get(mode) not in (
            track,
            AUTO_SUBJECT,
        ):
            raise HttpCoreError("Pilihan bidang belajar berubah", category="rejected")
        status = await self.study_status(mode)
        facility = status["facility"]
        service = facility["service"]
        skill = next((row for row in status["tracks"] if row["id"] == track), None)
        price = coin(service["priceMilli"])
        if (
            not skill
            or is_track_max(skill, mode)
            or skill.get("pending")
            or facility.get("nextAt")
            or facility.get("myVisitUntil")
            or service.get("open") is not True
            or (service.get("studyTracks") is not None and track not in service["studyTracks"])
            or price != Decimal(expected_price)
        ):
            raise HttpCoreError(
                "Bidang, tarif, jadwal, atau cooldown belajar berubah", category="rejected"
            )
        state = await self.snapshot()
        if state.phase == "sleeping":
            raise HttpCoreError("Karakter sedang tidur", category="sleeping")
        if (
            state.phase != "idle"
            or state.wallet != Decimal(expected_wallet)
            or (
                price > Decimal(0) and state.wallet - price < max(Decimal(20), Decimal(min_balance))
            )
        ):
            raise HttpCoreError("Fase atau saldo berubah sebelum belajar", category="rejected")
        if not auto_flags(self.directory)[mode]:
            raise HttpCoreError("Auto belajar dinonaktifkan", category="auto_disabled")
        result = await self.request(
            f"/api/facilities/{facility['id']}/use", {"requestId": request_id, "track": track}
        )
        if (
            not isinstance(result, dict)
            or result.get("requestId") != request_id
            or result.get("projectId") != facility["id"]
            or type(result.get("priceMilli")) is not int
            or result.get("priceMilli") != service["priceMilli"]
            or not isinstance(result.get("id"), str)
        ):
            raise HttpCoreError(
                "Receipt belajar belum cocok; transaksi tidak diulang", category="uncertain"
            )
        return result

    async def study_quiz(self, mode, visit_id, track):
        visit_id = str(UUID(visit_id))
        status = await self.study_status(mode)
        quiz = status["quiz"]
        if (
            quiz.get("available") is not True
            or quiz.get("visitId") != visit_id
            or quiz.get("track", {}).get("id") != track
        ):
            raise HttpCoreError("Kunjungan/kuis belajar berubah", category="rejected")
        try:
            answers = quiz_answers(quiz, await self.quiz_bank())
        except (KeyError, TypeError, ValueError) as exc:
            raise HttpCoreError(
                "Soal belum cocok dengan bacaan client; jawaban tidak ditebak", category="rejected"
            ) from exc
        state = await self.snapshot()
        if state.phase == "sleeping":
            raise HttpCoreError("Karakter sedang tidur", category="sleeping")
        if state.phase != "idle" or not auto_flags(self.directory)[mode]:
            raise HttpCoreError(
                "Auto belajar nonaktif atau akun tidak idle", category="auto_disabled"
            )
        result = await self.request(
            f"/api/facilities/{status['facility']['id']}/kuis",
            {"visitId": visit_id, "answers": answers},
        )
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("track"), dict)
            or result.get("track", {}).get("id") != track
            or type(result.get("benar")) is not int
            or type(result.get("total")) is not int
            or result.get("total") != len(answers)
            or not 0 <= result["benar"] <= len(answers)
            or type(result.get("bonus")) is not int
            or not 0 <= result["bonus"] <= 1
        ):
            raise HttpCoreError(
                "Hasil kuis belum terverifikasi; submit tidak diulang", category="uncertain"
            )
        return result

    async def bpjs_status(self):
        return await self.request("/api/bpjs")

    async def ensure_bpjs(self):
        if not getattr(self, "home", None):
            await self.snapshot()
        try:
            status = await self.bpjs_status()
        except HttpCoreError:
            return {}
        kartu = status.get("kartu")
        rules = status.get("rules", {})
        wallet_milli = status.get("walletMilli", 0)
        iuran_milli = rules.get("iuranMilli", 5000)
        village = (self.home or {}).get("desa")
        kantor_id = BPJS_KANTOR_BY_VILLAGE.get(village)
        if (not kartu or not kartu.get("aktif") or kartu.get("sisaHari", 0) <= 0) and kantor_id:
            if wallet_milli >= iuran_milli:
                await self.request(
                    "/api/bpjs/bayar",
                    {"projectId": kantor_id, "requestId": str(uuid4())},
                )
                status = await self.bpjs_status()
        return status

    async def complete_facility_kegiatan(self, facility_id):
        try:
            kegiatan = await self.request(f"/api/facilities/{facility_id}/kegiatan")
        except HttpCoreError:
            return None
        if not isinstance(kegiatan, dict) or not kegiatan.get("available"):
            return None
        visit_id = kegiatan.get("visitId")
        kind = kegiatan.get("kind")
        plan = kegiatan.get("plan") or {}
        if kind == "tensi":
            periods = plan.get("periods") or []
            stops = [round(p * 0.25) for p in periods]
            return await self.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "stops": stops},
            )
        if kind == "detak":
            beats = plan.get("beats") or []
            taps = [int(b) for b in beats]
            return await self.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "taps": taps},
            )
        if kind == "nampan":
            items = plan.get("items") or []
            picks = solve_nampan_picks(items)
            return await self.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "picks": picks},
            )
        if kind == "foto":
            periods = plan.get("periods") or []
            shots = solve_foto_shots(periods)
            return await self.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "shots": shots},
            )
        return None

    async def _preview_spbu_fuel(self, current: Snapshot) -> dict:
        try:
            dest = await self.request("/api/tujuan")
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

        ref_x = (self.home or {}).get("x", 0)
        ref_y = (self.home or {}).get("y", 0)
        spbus.sort(key=lambda s: (s.get("x", 0) - ref_x) ** 2 + (s.get("y", 0) - ref_y) ** 2)
        spbu = spbus[0]
        plot_id = spbu["plotId"]
        v_type = current.ojol_vehicle or "motor"
        is_electric = False
        if v_type == "mobil":
            try:
                kd = await self.request("/api/kendaraan")
                items = kd.get("items", []) if isinstance(kd, dict) else []
                car = next((c for c in items if c.get("family") == "mobil"), None)
                is_electric = bool(car and car.get("listrik"))
            except Exception:
                pass

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
        self.catalog.setdefault("fuel", {})[shop_id] = spbu_shop
        return {
            "shops": [spbu_shop.model_dump()],
            "navigation": {"method": "spbu_refill", "travel_request_sent": False},
        }

    async def _preview_fisik_shops(self) -> list[ShopPreview]:
        if not self.physical_places:
            try:
                tempat = await self.request("/api/kebutuhan?tempat=fisik")
                if isinstance(tempat, dict) and isinstance(tempat.get("places"), list):
                    self.physical_places = [p for p in tempat["places"] if isinstance(p, dict)]
            except HttpCoreError:
                pass
        try:
            effects = await self.effects(for_needs=True)
        except HttpCoreError:
            effects = {}
        village = (self.home or {}).get("desa")
        gym_ids = list(GYM_FACILITIES_BY_VILLAGE.get(village, ()))
        gym_previews = await self.read_previews(self.gym_facility(fid, effects) for fid in gym_ids)
        place_previews = await self.read_previews(
            self.physical_facility(place, effects)
            for place in self.physical_places
            if place.get("id") not in set(gym_ids)
        )
        return gym_previews + place_previews

    async def _preview_kesehatan_shops(self) -> list[ShopPreview]:
        try:
            bpjs = await self.ensure_bpjs()
        except HttpCoreError:
            bpjs = {}
        kartu = bpjs.get("kartu") or {}
        gratis_sisa = bpjs.get("gratisSisa", 0)
        village = (self.home or {}).get("desa")
        facility_ids = HEALTH_FACILITIES_BY_VILLAGE.get(village, ())
        if not (kartu.get("aktif") and gratis_sisa > 0 and facility_ids):
            return []
        for fid in facility_ids:
            try:
                details = await self.request(f"/api/facilities/{fid}")
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
        now_utc = datetime.now(timezone.utc)
        for fid in facility_ids:
            try:
                details = await self.request(f"/api/facilities/{fid}")
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
        plot_id = (self.home or {}).get("plotId", "home")
        keb_status = await self.request("/api/kebutuhan")
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
        self.catalog.pop(resource, None)
        fallback_allowed = False
        navigation_method = "fixed_catalog_http"
        try:
            async with asyncio.timeout(25):
                if resource in {"fuel", "condition"} or not getattr(self, "home", None):
                    current = await self.snapshot()
                    if resource == "fuel" and current.ojol_min_fuel is not None:
                        return await self._preview_spbu_fuel(current)
                if not self.home:
                    raise HttpCoreError("Rumah akun belum tersedia", category="blocked")
                if resource == "fisik":
                    shops = await self._preview_fisik_shops()
                elif resource in NEEDS:
                    shops = []
                    village = (self.home or {}).get("desa")
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
                        plot_id = (self.home or {}).get("plotId", "home")
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
                        effects = await self.effects(for_needs=True)
                        shops, fallback_allowed = await self.need_suppliers(resource, effects)
                else:
                    locations = self.ojol_shop_locations(resource)
                    if not locations and resource not in OJOL_DIRECTORY_RESOURCES:
                        raise HttpCoreError(
                            "Toko tetap belum dikonfigurasi untuk desa akun", category="blocked"
                        )
                    allowed_items = await self.resource_items(resource)
                    effects = await self.effects(required_items=allowed_items)
                    shops = await self.read_previews(
                        self.preview_shop(location, resource, effects, allowed_items)
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
        self.catalog[resource] = shops
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
        shop = self.catalog.get(resource, {}).get(shop_id)
        if shop is None or product not in shop.products or not product.enabled:
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
                isinstance(exc, HttpCoreError) and exc.category in {"auth", "rejected", "sleeping"}
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
        if shop.category == "spbu":
            kend_res = await self.request("/api/kendaraan")
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
            await self.request(
                f"/api/spbu/{plot_id}",
                {"aksi": "datang", "kode": veh_code, "dorong": False, "x": pos_x, "y": pos_y},
            )
            receipt = await self.request(
                f"/api/spbu/{plot_id}",
                {"aksi": "isi", "jumlah": "penuh", "x": pos_x, "y": pos_y, "requestId": request_id},
            )
            try:
                await self.request(f"/api/spbu/{plot_id}", {"aksi": "pamit"})
            except Exception:
                pass
            return receipt
        if shop.category == "fasum":
            if identity.get("item") == "minigame":
                receipt = await self.complete_minigame(
                    shop_id, identity.get("game", "gym"), request_id
                )
                return receipt
            receipt = await self.request(
                f"/api/facilities/{shop_id}/use", {"requestId": request_id}
            )
            if resource in {"kesehatan", "makan", "rekreasi"}:
                await self.complete_facility_kegiatan(shop_id)
            return receipt
        if shop.category == "kamar-mandi":
            action = identity.get("action", "wc")
            receipt = await self.request("/api/rumah/kamar-mandi", {"aksi": action})
            if action == "wc":
                try:
                    await self.request("/api/rumah/kamar-mandi", {"aksi": "cuci"})
                except Exception:
                    pass
            return receipt
        return await self.request(
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
        version = self.config_version
        vehicle = self.vehicle
        allowed_items = None if is_need else await self.resource_items(resource)
        if not is_facility and not is_bathroom and not is_spbu:
            effects = await self.effects(for_needs=is_need, required_items=allowed_items or ())
            if not fallback:
                catalog, fresh = await self.products(shop_id, resource, effects, allowed_items)
                if product not in fresh or (
                    (is_need or catalog.get("plang")) and catalog.get("plang") != shop.name
                ):
                    raise HttpCoreError(
                        "Nama toko atau katalog berubah sebelum pembelian", category="rejected"
                    )
        state = await self.snapshot()
        if state.phase == "sleeping":
            raise HttpCoreError("Karakter sedang tidur; transaksi ditunda", category="sleeping")
        if resource == "fuel" and state.ojol_min_fuel is not None and not is_spbu:
            raise HttpCoreError(
                "Pengisian tangki memerlukan kunjungan ke SPBU", category="rejected"
            )
        identity = json.loads(product.row_text) if product.row_text else {}
        if is_bathroom:
            if not self.home:
                eligible = False
            elif resource == "wc":
                eligible = True
            elif resource == "kebersihan":
                action = identity.get("action")
                keb_status = await self.request("/api/kebutuhan")
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
            village = (self.home or {}).get("desa")
            gym_ids = set(GYM_FACILITIES_BY_VILLAGE.get(village, ()))
            effects = {}
            try:
                effects = await self.effects(for_needs=True)
            except HttpCoreError:
                effects = {}
            if shop_id in gym_ids:
                eligible = await self.gym_facility(shop_id, effects) == shop
            else:
                place = next((p for p in self.physical_places if p.get("id") == shop_id), {})
                eligible = await self.physical_facility(place, effects) == shop
        elif is_spbu:
            eligible = True
        elif is_facility and resource in {"kesehatan", "makan", "rekreasi"}:
            details = await self.request(f"/api/facilities/{shop_id}")
            service = details.get("service") or {}
            now_utc = datetime.now(timezone.utc)
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
        elif fallback and self.home:
            candidates, allowed = await self.need_suppliers(resource, effects)
            eligible = allowed and any(
                fresh.id == shop_id and fresh.name == shop.name and product in fresh.products
                for fresh in candidates
            )
        elif is_need and shop.preferred and self.home:
            if any(
                location.id == shop_id
                for location in NEED_SHOPS_BY_VILLAGE.get(self.home["desa"], {}).get(resource, ())
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
                if self.home
                else None
            )
            eligible = location is not None and location.id == shop_id
        else:
            locations = (
                NEED_SHOPS_BY_VILLAGE.get((self.home or {}).get("desa"), {}).get(resource, ())
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
            or self.config_version != version
            or (resource in {"fuel", "condition"} and state.ojol_vehicle != vehicle)
            or self.catalog.get(resource, {}).get(shop_id) is not shop
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

    async def drive_to_destination(self, to_pos, *, max_seconds=420):
        """Mode kendara: lacak berkelanjutan ke tujuan sampai arrived (server bergerak
        laju_kali x laju_maks; lacak basi 45 detik menghentikan perjalanan)."""
        if "x" not in to_pos or "y" not in to_pos:
            return
        try:
            await self.request("/api/ojol", {"action": "lacak", "x": to_pos["x"], "y": to_pos["y"]})
        except Exception:
            pass
        for _ in range(max_seconds // 2):
            trip = (await self.raw_trip()) or {}
            if not trip or trip.get("arrived"):
                # Klaim harus segera setelah arrived; jeda memasuki jendela turun (409).
                return
            try:
                await self.request(
                    "/api/ojol", {"action": "lacak", "x": to_pos["x"], "y": to_pos["y"]}
                )
            except Exception:
                pass
            # ponytail: jitter kecil (client kirim tiap 5 dtk; lacak basi 45 dtk).
            await asyncio.sleep(random.uniform(1.6, 2.6))

    async def raw_trip(self):
        raw = await self.request("/api/ojol")
        return (raw.get("ojol") or {}).get("trip") or raw.get("trip")

    async def solve_cek_captcha(self, attempts=3):
        """Ambil gambar cek SVG dan pecahkan; kembalikan 2 digit untuk payload selesai."""
        from .svg_captcha_solver import (
            SvgCaptchaSolverError,
            solve_polyline_captcha,
            solve_svg_captcha,
        )

        trip = await self.raw_trip()
        trip_id, arrive_at = (trip or {}).get("id"), (trip or {}).get("arriveAt")
        if not trip_id or not arrive_at:
            raise HttpCoreError("Trip cek pengemudi tidak dapat dibaca", recoverable=True)
        for attempt in range(1, attempts + 1):
            path = f"/api/ojol/cek?t={trip_id}&a={arrive_at}&m={attempt}"
            image = await self.request(path, text=True)
            text = image.strip() if isinstance(image, str) else ""
            if not text.startswith("<"):
                continue
            try:
                (self.directory / "cek-samples").mkdir(parents=True, exist_ok=True)
                (self.directory / "cek-samples" / f"{trip_id}.svg").write_text(text)
            except OSError:
                pass
            try:
                if "<polyline" in text:
                    kode = solve_polyline_captcha(text, self.directory, trip_id=trip_id)
                else:
                    kode = solve_svg_captcha(text)
            except Exception as exc:
                raise SvgCaptchaSolverError(f"Gagal memecahkan gambar cek: {exc}") from exc
            if len(kode) == 2 and kode.isdigit():
                return kode
            raise SvgCaptchaSolverError(f"Hasil cek tidak berupa 2 angka: {kode!r}")
        raise HttpCoreError("Gambar cek pengemudi bukan SVG", recoverable=True)

    async def job_action(self, kind, *, mode="otomatis"):
        state = await self.snapshot()
        if state.phase == "sleeping":
            raise HttpCoreError("Karakter sedang tidur; aksi Ojol ditunda", category="sleeping")
        if kind == "search" and state.phase == "idle":
            if getattr(state, "ojol_resting", False):
                raise HttpCoreError("Mitra ojol sedang wajib istirahat", category="rejected")
            if not auto_flags(self.directory)["ojol"]:
                raise HttpCoreError(
                    "Auto Ojol dinonaktifkan sebelum mencari order", category="auto_disabled"
                )
            if "📲 Cari order" not in state.buttons:
                raise HttpCoreError("Game belum mengizinkan pencarian order", category="rejected")
            usage = (
                self.usage if self.usage is not None else {"bensin": 5, "kendaraan": 2, "kuota": 4}
            )
            if not isinstance(usage, dict) or not all(key in usage for key in RESOURCES):
                raise HttpCoreError("Konsumsi order belum dapat dibaca", category="rejected")
            min_fuel = integer(usage.get("bensinMin", usage.get("bensin", 5)))
            if state.fuel < min_fuel or any(
                state.resource_value(resource) < integer(usage[key])
                for key, resource in (("kendaraan", "condition"), ("kuota", "data"))
            ):
                raise HttpCoreError(
                    "Resource kendaraan tidak cukup untuk order", category="rejected"
                )
            effective_mode = mode or getattr(self, "ojol_mode", "otomatis")
            tawar_res = await self.request(
                "/api/ojol",
                {"action": "tawar", "vehicle": state.ojol_vehicle, "mode": effective_mode},
            )
            pilihan = tawar_res.get("pilihan") if isinstance(tawar_res, dict) else []
            if pilihan:
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
                take_res = await self.request("/api/ojol", ambil_payload)
                if effective_mode == "kendara":
                    trip = (take_res.get("trip") if isinstance(take_res, dict) else None) or chosen
                    from_pos = trip.get("from") or {}
                    to_pos = trip.get("to") or {}
                    if "x" in from_pos and "y" in from_pos:
                        try:
                            await self.request(
                                "/api/ojol",
                                {"action": "lacak", "x": from_pos["x"], "y": from_pos["y"]},
                            )
                        except Exception:
                            pass
                    try:
                        await self.request("/api/ojol", {"action": "jemput"})
                    except Exception:
                        pass
                    if "x" in to_pos and "y" in to_pos:
                        try:
                            await self.request(
                                "/api/ojol",
                                {"action": "lacak", "x": to_pos["x"], "y": to_pos["y"]},
                            )
                        except Exception:
                            pass
                return take_res
            return await self.request(
                "/api/ojol", {"action": "ambil", "vehicle": state.ojol_vehicle}
            )
        if kind == "complete" and state.phase == "complete":
            trip_data = (getattr(self, "last_ojol_data", None) or {}).get("trip")
            if isinstance(trip_data, dict) and trip_data.get("mode") == "kendara":
                to_pos = trip_data.get("to") or {}
                await self.drive_to_destination(to_pos)
            payload = {"action": "selesai"}
            if state.order_code is not None:
                payload["kode"] = state.order_code
            elif state.order_verify:
                payload["kode"] = await self.solve_cek_captcha()
            for attempt in range(5):
                try:
                    result = await self.request("/api/ojol", payload)
                    if isinstance(result, dict) and result.get("ok") and payload.get("kode"):
                        from .svg_captcha_solver import learn_polyline

                        sample = self.directory / "cek-samples" / f"{state.trip_id}.svg"
                        try:
                            learn_polyline(self.directory, sample.read_text(), payload["kode"])
                        except (OSError, ValueError):
                            pass
                    return result
                except HttpCoreError as exc:
                    # 409 "Penumpang sedang turun" (turun_detik 8): ulang dengan jeda penuh;
                    # tiap 409 bisa mereset jendela turun, dan bila kedatangan ikut ter-reset,
                    # kendarai ulang sampai arrived sebelum mencoba lagi.
                    if attempt == 4 or "409" not in str(exc):
                        raise
                    await asyncio.sleep(10)
                    trip = (await self.raw_trip()) or {}
                    if trip and not trip.get("arrived") and isinstance(trip.get("to"), dict):
                        await self.drive_to_destination(trip["to"], max_seconds=240)
                        continue
                    # 409 terakhir dengan jejak invalid: server minta batal; ikuti dan lanjut
                    # ke order baru agar worker tidak mati.
                    raw = await self._session_client().request(
                        "POST",
                        "/api/ojol",
                        json={"action": "selesai"},
                        headers=self.browser_headers("/api/ojol", "POST"),
                    )
                    if "REQUIREMENT_NOT_MET" in raw.text:
                        await self.request("/api/ojol", {"action": "batal"})
                        raise HttpCoreError(
                            "Order dibatalkan otomatis: jejak perjalanan tidak lewat jalan. "
                            "Mencari order baru.",
                            category="rejected",
                        )
                    raise
        raise HttpCoreError("Aksi Ojol tidak sesuai state/waktu server", category="blocked")

    async def garden_status(self):
        result = await self.request("/api/daily/garden")
        if not isinstance(result, dict) or "gardens" not in result:
            raise HttpCoreError("Format status kebun & kolam tidak valid", recoverable=True)
        return result

    async def garden_action(self, garden_id: str, action: str):
        if action not in {"panen", "rawat", "tanam"}:
            raise ValueError(f"Aksi kebun tidak valid: {action}")
        return await self.request(f"/api/daily/garden/{garden_id}", payload={"action": action})
