"""Observed Ojol endpoints only. GETs may retry; writes are always one attempt."""

import asyncio
import contextlib
import hashlib
import json
import logging
import random
import re
import secrets
import time
from datetime import date
from pathlib import Path

import httpx

from app.core.exceptions import HttpCoreError
from app.core.formatting import display_coin as display
from app.core.formatting import parse_api_timestamp as timestamp
from app.core.models import (
    AUTO_SUBJECT,
    STUDY_LABELS,
    SUBJECTS,
    now,
)
from app.core.storage import write_private
from app.integrations.kampung.cookies import DOMAIN, parse_cookie_input, session_expired
from app.integrations.kampung.facility_workflows import FacilityWorkflows
from app.integrations.kampung.game_parsers import (
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
from app.integrations.kampung.game_wallet import WalletReport, read_daily_wallet, valid_cursor
from app.integrations.kampung.identity import save_profile, verified_profile
from app.integrations.kampung.shop_workflows import ShopWorkflows
from app.integrations.kampung.trip_orders import TripOrders
from app.modules.gameplay.study import (
    save_skills,
)
from app.modules.worker.settings import auto_flags

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

logger = logging.getLogger(__name__)

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
    minigame_wait_multiplier: float = 1.0

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
        self._shops = ShopWorkflows(self)
        self._facilities = FacilityWorkflows(self)
        self._trips = TripOrders(self)

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
        manusia_cek_image = bool(
            re.fullmatch(r"/api/cek-manusia\?k=[A-Za-z0-9_%.~:-]{1,160}&m=[0-9]{1,3}", path)
        )
        allowed = (
            ojol_cek_image
            or manusia_cek_image
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
                "/api/kantor",
                "/api/kerja-malam",
                "/api/skills",
                "/api/chat?toa=0",
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
                and path
                not in {
                    "/api/ojol",
                    "/api/rumah/kamar-mandi",
                    "/api/diving",
                    "/api/kantor",
                    "/api/kerja-malam",
                    "/api/skills",
                }
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
                    if response.status_code == 428:
                        answered = await self._answer_manusia(response, path, payload)
                        if answered is not None:
                            return answered
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

    async def _answer_manusia(self, response, path, payload):
        """428 CEK_MANUSIA: pecahkan gambar 2 angka lalu ulangi POST sekali dengan cekManusia.

        None berarti bukan CEK_MANUSIA atau tidak terpecahkan; pemanggil melaporkan status asli.
        """
        from app.modules.captcha import (
            learn_polyline,
            record_captcha_review,
            solve_polyline_captcha,
            solve_svg_captcha,
        )

        try:
            error = (response.json() or {}).get("error") or {}
        except ValueError:
            return None
        if error.get("code") != "CEK_MANUSIA":
            return None
        cek = error.get("cek") or {}
        kunci = cek.get("kunci") if isinstance(cek.get("kunci"), str) else ""
        if cek.get("siteKey") and not kunci:
            return None  # Turnstile: harus diselesaikan manusia di game
        last_svg, last_polyline = "", False
        for _ in range(3):
            # Angka per kunci tetap; gambar cuma digambar ulang. Baca 3 gambar lalu
            # kirim suara terbanyak supaya salah baca tidak dikirim 3x berturut-turut.
            votes: dict[str, tuple[str, bool]] = {}
            for attempt in range(1, 4):
                image = await self.request(f"/api/cek-manusia?k={kunci}&m={attempt}", text=True)
                svg = image.strip() if isinstance(image, str) else ""
                if not svg.startswith("<"):
                    continue
                polyline = "<polyline" in svg
                last_svg, last_polyline = svg, polyline
                try:
                    kode = (
                        solve_polyline_captcha(svg, self.directory)
                        if polyline
                        else solve_svg_captcha(svg)
                    )
                except Exception as exc:  # gambar muat ulang
                    logger.debug("Gagal pecahkan gambar cek manusia: %s", exc)
                    continue
                if not (len(kode) == 2 and kode.isdigit()):
                    continue
                votes[kode] = ((votes[kode][0] + 1) if kode in votes else 1, svg)
            if not votes:
                continue
            kode = max(votes, key=lambda k: votes[k][0])
            svg, polyline = votes[kode][1], "<polyline" in votes[kode][1]
            retry = await self._session_client().request(
                "POST",
                path,
                json={**payload, "cekManusia": {"kode": kode}},
                headers=self.browser_headers(path, "POST"),
            )
            if retry.is_success:
                if polyline:
                    with contextlib.suppress(OSError, ValueError):
                        learn_polyline(self.directory, svg, kode)
                with contextlib.suppress(ValueError):
                    return retry.json()
                return None
            if retry.status_code != 428:
                return None
            # 428 lagi: kunci baru dari respons, ulangi dengan gambar lain
            with contextlib.suppress(ValueError):
                cek = ((retry.json() or {}).get("error") or {}).get("cek") or {}
                kunci = cek.get("kunci") if isinstance(cek.get("kunci"), str) else ""
        # Gagal total: antrekan gambar terakhir ke Bank Angka supaya bisa dikontribusi operator.
        if last_polyline:
            with contextlib.suppress(OSError, ValueError):
                (self.directory / "cek-samples").mkdir(parents=True, exist_ok=True)
                (self.directory / "cek-samples" / f"{kunci or 'cek'}.svg").write_text(last_svg)
            with contextlib.suppress(OSError, ValueError):
                record_captcha_review(self.directory, last_svg, trip_id=kunci)
        return None

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
        """Fetch online presence endpoints (/api/game/me, /api/time, /api/realtime/token, /api/chat?toa=0).

        Touches the session on KampungSebelah, keeping the player within the
        online window (120s) and writing online status to online-status.json.
        """
        me, clock = await asyncio.gather(
            self.request("/api/game/me"),
            self.request("/api/time"),
        )
        rt = None
        with contextlib.suppress(Exception):
            rt = await self.request("/api/realtime/token")
        with contextlib.suppress(Exception):
            await self.request("/api/chat?toa=0")

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
        return await self._shops.resource_items(resource)

    def ojol_shop_locations(self, resource):
        return self._shops.ojol_shop_locations(resource)

    async def effects(self, *, for_needs=False, required_items=()):
        return await self._shops.effects(for_needs=for_needs, required_items=required_items)

    async def products(self, shop_id, resource, effects, allowed_items=None):
        return await self._shops.products(shop_id, resource, effects, allowed_items)

    async def preview_shop(self, location, resource, effects, allowed_items):
        return await self._shops.preview_shop(location, resource, effects, allowed_items)

    async def need_suppliers(self, resource, effects, *, preferred_only=False):
        return await self._shops.need_suppliers(resource, effects, preferred_only=preferred_only)

    akademis_need_shops = need_suppliers

    async def complete_minigame(self, facility_id, game, request_id):
        return await self._facilities.complete_minigame(facility_id, game, request_id)

    async def gym_facility(self, identifier, effects=None):
        return await self._facilities.gym_facility(identifier, effects)

    async def gym_plays_left(self) -> int:
        return await self._facilities.gym_plays_left()

    async def physical_facility(self, place, effects=None):
        return await self._facilities.physical_facility(place, effects)

    async def study_status(self, mode):
        return await self._facilities.study_status(mode)

    async def study_start(
        self, mode, track, expected_price, expected_wallet, min_balance, request_id
    ):
        return await self._facilities.study_start(
            mode, track, expected_price, expected_wallet, min_balance, request_id
        )

    async def study_quiz(self, mode, visit_id, track):
        return await self._facilities.study_quiz(mode, visit_id, track)

    async def ensure_bpjs(self):
        return await self._facilities.ensure_bpjs()

    async def complete_facility_kegiatan(self, facility_id):
        return await self._facilities.complete_facility_kegiatan(facility_id)

    async def preview(self, resource):
        return await self._shops.preview(resource)

    async def purchase(self, product, expected_wallet, expected_resource, min_balance, request_id):
        return await self._shops.purchase(
            product, expected_wallet, expected_resource, min_balance, request_id
        )

    async def validate_purchase(
        self, shop, resource, product, expected_wallet, expected_resource, min_balance
    ):
        return await self._shops.validate_purchase(
            shop, resource, product, expected_wallet, expected_resource, min_balance
        )

    async def drive_to_destination(self, to_pos, *, max_seconds=420):
        """Mode kendara: lacak berkelanjutan ke tujuan sampai arrived (server bergerak
        laju_kali x laju_maks; lacak basi 45 detik menghentikan perjalanan)."""
        if "x" not in to_pos or "y" not in to_pos:
            return
        with contextlib.suppress(Exception):
            await self.request("/api/ojol", {"action": "lacak", "x": to_pos["x"], "y": to_pos["y"]})
        for _ in range(max_seconds // 2):
            trip = (await self.raw_trip()) or {}
            if not trip or trip.get("arrived"):
                # Klaim harus segera setelah arrived; jeda memasuki jendela turun (409).
                return
            with contextlib.suppress(Exception):
                await self.request(
                    "/api/ojol", {"action": "lacak", "x": to_pos["x"], "y": to_pos["y"]}
                )
            # Sesuaikan ritme lacak dengan client (lacak_detik: 5 dtk; lacak basi 45 dtk).
            await asyncio.sleep(random.uniform(4.2, 5.8))  # noqa: S311 - timing only

    async def raw_trip(self):
        return await self._trips.raw_trip()

    async def solve_cek_captcha(self, attempts=3):
        """Ambil gambar cek SVG dan pecahkan; kembalikan 2 digit untuk payload selesai."""
        from app.modules.captcha import (
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
            return await self._trips.search(state, mode)
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
                        from app.modules.captcha import learn_polyline

                        sample = self.directory / "cek-samples" / f"{state.trip_id}.svg"
                        with contextlib.suppress(OSError, ValueError):
                            learn_polyline(self.directory, sample.read_text(), payload["kode"])
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
                        ) from exc
                    raise
        raise HttpCoreError("Aksi Ojol tidak sesuai state/waktu server", category="blocked")

    async def garden_status(self):
        return await self._facilities.garden_status()

    async def garden_action(self, garden_id: str, action: str):
        return await self._facilities.garden_action(garden_id, action)

    async def kantor_action(self, action: str, **fields):
        """Send an action payload to /api/kantor."""
        return await self.request("/api/kantor", {"action": action, **fields})

    async def kerja_malam_status(self):
        """Fetch public/night job status from /api/kerja-malam."""
        return await self.request("/api/kerja-malam")

    async def kerja_malam_action(self, action: str, **fields):
        """Send an action payload to /api/kerja-malam."""
        return await self.request("/api/kerja-malam", {"action": action, **fields})

    async def game_skill_state(self) -> tuple[int, dict]:
        """Fetch current balanceMilli and skill state from /api/game/me."""
        me = await self.request("/api/game/me")
        if not isinstance(me, dict):
            return 0, {}
        return int(me.get("balanceMilli") or 0), me.get("skill") or {}

    async def take_skill_course(self, track: str):
        """Start a skill course on /api/skills for the given track."""
        from uuid import uuid4

        return await self.request("/api/skills", {"requestId": str(uuid4()), "track": track})
