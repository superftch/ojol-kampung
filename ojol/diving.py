"""Modul otomatisasi Diving Laut Seberang KampungSebelah.

Menghitung koordinat kerang, jalur renang aman, dan interaksi API diving.
Berdasarkan aturan game dirilis 22 November 2026.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable

from .http_api import OjolHttpApi

LOGGER = logging.getLogger(__name__)

# Batas dan konfigurasi diving KampungSebelah
LAUT_BOUNDS = {
    "x0": -320.0,
    "x1": 320.0,
    "z0": -640.0,
    "z1": -6.0,
    "masuk": {"x": 0.0, "z": -26.0},
}

GERAK_CONFIG = {
    "laju": 3.4,
    "laju_dalam": 0.55,
    "dalam_penuh": 60.0,
    "naik": 2.4,
    "turun": 2.0,
}

KERANG_CONFIG = {
    "jumlah": 48,
    "jarak_min": 18.0,
    "dalam_min": 4.0,
    "jangkau_m": 3.2,
    "buka_detik": 3.0,
}

HIU_CONFIG = {
    "selang_menit": 8,
    "peluang": 0.5,
    "lama_detik": [70, 100],
    "peringatan_detik": 8,
    "aman_m": 6.0,
    "lihat_m": 45.0,
    "laju": 2.5,
    "rawat_jam": 12,
}

U_BUMPS = [
    {"x": -150.0, "z": -170.0, "r": 46.0, "t": 7.0},
    {"x": 120.0, "z": -235.0, "r": 52.0, "t": 11.0},
    {"x": -40.0, "z": -345.0, "r": 40.0, "t": 13.0},
    {"x": 225.0, "z": -120.0, "r": 38.0, "t": 5.0},
]


def _make_rng(seed_str: str) -> Callable[[], float]:
    """FNV-1a + SplitMix32 PRNG identik dengan engine game KampungSebelah."""
    e = 0x811C9DC5
    for ch in seed_str:
        e = ((e ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
    e = e or 1

    def rng() -> float:
        nonlocal e
        e = (e + 0x6D2B79F5) & 0xFFFFFFFF
        e_signed = e if e < 0x80000000 else e - 0x100000000
        part1 = e ^ (e >> 15)
        part1_signed = part1 if part1 < 0x80000000 else part1 - 0x100000000
        a = (part1_signed * (1 | e_signed)) & 0xFFFFFFFF
        a_signed = a if a < 0x80000000 else a - 0x100000000

        part2 = a ^ (a >> 7)
        part2_signed = part2 if part2 < 0x80000000 else part2 - 0x100000000
        term2 = (part2_signed * (61 | a_signed)) & 0xFFFFFFFF
        term2_signed = term2 if term2 < 0x80000000 else term2 - 0x100000000

        a = (a_signed + term2_signed) & 0xFFFFFFFF
        a = (a ^ a_signed) & 0xFFFFFFFF
        res_u32 = (a ^ (a >> 14)) & 0xFFFFFFFF
        return res_u32 / 0x100000000

    return rng


def _clamp(val: float, low: float, high: float) -> float:
    return min(high, max(low, val))


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = _clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _o_palung(x: float) -> float:
    return -505.0 + 44.0 * math.sin(0.0105 * x + 0.6)


def get_sea_depth(x: float, z: float) -> float:
    """Menghitung kedalaman laut di titik (x, z)."""
    t = _clamp((-z - 4.0) / 620.0, 0.0, 1.0)
    n = 1.2 + 5.5 * _smoothstep(0.0, 0.2, t) + 28.0 * _smoothstep(0.18, 0.74, t)
    n += (
        math.sin(0.031 * x + 1.7) * math.cos(0.027 * z) * 1.5 * _smoothstep(0.04, 0.3, t)
        + 2.2 * math.sin(0.011 * x - 0.013 * z) * t
    )
    for bump in U_BUMPS:
        n -= bump["t"] * math.exp(-((x - bump["x"]) ** 2 + (z - bump["z"]) ** 2) / (bump["r"] ** 2))
    i_val = _smoothstep(-305.0, -235.0, x) * (1.0 - _smoothstep(235.0, 305.0, x))
    s_val = (z - _o_palung(x)) / (34.0 + 9.0 * math.sin(0.021 * x + 2.0))
    n += 31.0 * math.exp(-s_val * s_val) * i_val
    return max(0.9, n)


@dataclass(frozen=True)
class Kerang:
    i: int
    x: float
    z: float
    d: float
    putar: float
    besar: float


def generate_kerang_for_day(day_str: str) -> list[Kerang]:
    """Menghasilkan 48 letak kerang untuk tanggal hari tertentu (WIB)."""
    rng = _make_rng(f"diving:kerang:{day_str}")
    kerang_list: list[Kerang] = []
    attempts = 0
    x0, x1 = LAUT_BOUNDS["x0"], LAUT_BOUNDS["x1"]
    z0, z1 = LAUT_BOUNDS["z0"], LAUT_BOUNDS["z1"]
    masuk_x = LAUT_BOUNDS["masuk"]["x"]
    masuk_z = LAUT_BOUNDS["masuk"]["z"]

    while len(kerang_list) < KERANG_CONFIG["jumlah"] and attempts < 6000:
        attempts += 1
        a = x0 + 22.0 + rng() * (x1 - x0 - 44.0)
        e = z0 + 22.0 + rng() * (z1 - z0 - 60.0)
        depth = get_sea_depth(a, e)
        n_rand = rng()
        if depth < KERANG_CONFIG["dalam_min"]:
            continue
        if n_rand > 0.3 + 0.7 * min(1.0, depth / 36.0):
            continue
        if math.hypot(a - masuk_x, e - masuk_z) < 40.0:
            continue
        if any(math.hypot(k.x - a, k.z - e) < KERANG_CONFIG["jarak_min"] for k in kerang_list):
            continue

        idx = len(kerang_list)
        kerang_list.append(
            Kerang(
                i=idx,
                x=round(a * 10.0) / 10.0,
                z=round(e * 10.0) / 10.0,
                d=round(depth * 10.0) / 10.0,
                putar=round(628.0 * rng()) / 100.0,
                besar=round((0.85 + 0.5 * rng()) * 100.0) / 100.0,
            )
        )
    return kerang_list


def calculate_travel_seconds(
    x1: float, z1: float, d1: float, x2: float, z2: float, d2: float
) -> float:
    """Menghitung durasi renang aman (detik) antara dua titik di laut."""
    dist_xz = math.hypot(x2 - x1, z2 - z1)
    avg_depth = (d1 + d2) / 2.0
    factor = 1.0 - (1.0 - GERAK_CONFIG["laju_dalam"]) * _clamp(
        avg_depth / GERAK_CONFIG["dalam_penuh"], 0.0, 1.0
    )
    speed_xz = GERAK_CONFIG["laju"] * factor
    time_xz = dist_xz / max(0.1, speed_xz)

    # Waktu vertikal
    delta_d = d2 - d1
    if delta_d > 0:
        time_y = delta_d / GERAK_CONFIG["turun"]
    else:
        time_y = abs(delta_d) / GERAK_CONFIG["naik"]

    # Server membutuhkan waktu renang yang masuk akal + waktu buka kerang 3 detik
    time_travel = max(time_xz, time_y)
    return time_travel + KERANG_CONFIG["buka_detik"]


class DivingController:
    """Controller untuk otomatisasi sesi diving di KampungSebelah."""

    def __init__(self, api: OjolHttpApi):
        self.api = api

    async def get_status(self) -> dict[str, Any]:
        """Mengambil status diving akun saat ini."""
        res = await self.api.request("/api/diving")
        return res if isinstance(res, dict) else {}

    async def enter_or_resume_session(self) -> dict[str, Any]:
        """Beli tiket diving (10 koin) atau lanjutkan sesi yang ada."""
        res = await self.api.request("/api/diving", payload={"aksi": "masuk"})
        return res if isinstance(res, dict) else {}

    async def open_shell(self, session_id: str, kerang_index: int) -> dict[str, Any]:
        """Membuka kerang nomor kerang_index pada sesi session_id."""
        res = await self.api.request(
            "/api/diving", payload={"aksi": "kerang", "id": session_id, "kerang": kerang_index}
        )
        return res if isinstance(res, dict) else {}

    async def finish_session(self, session_id: str) -> dict[str, Any]:
        """Mengakhiri sesi diving secara rapi (menerima rekreasi +30)."""
        res = await self.api.request("/api/diving", payload={"aksi": "selesai", "id": session_id})
        return res if isinstance(res, dict) else {}

    async def sell_pearls(self) -> dict[str, Any]:
        """Menjual semua mutiara yang dipegang ke kas desa."""
        res = await self.api.request("/api/diving", payload={"aksi": "jual"})
        return res if isinstance(res, dict) else {}

    def plan_shell_tour(
        self, kerang_list: list[Kerang], already_opened: set[int]
    ) -> list[tuple[Kerang, float]]:
        """Merencanakan rute buka kerang terdekat (Greedy TSP) dari titik masuk."""
        remaining = [k for k in kerang_list if k.i not in already_opened]
        route: list[tuple[Kerang, float]] = []

        curr_x = LAUT_BOUNDS["masuk"]["x"]
        curr_z = LAUT_BOUNDS["masuk"]["z"]
        curr_d = 0.0

        while remaining:
            best_idx = 0
            best_time = float("inf")
            for idx, k in enumerate(remaining):
                t = calculate_travel_seconds(curr_x, curr_z, curr_d, k.x, k.z, k.d)
                if t < best_time:
                    best_time = t
                    best_idx = idx

            chosen = remaining.pop(best_idx)
            route.append((chosen, best_time))
            curr_x, curr_z, curr_d = chosen.x, chosen.z, chosen.d

        return route

    async def run_session(
        self,
        *,
        max_shells: int | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
        safety_buffer: float = 2.0,
    ) -> dict[str, Any]:
        """Jalankan siklus diving otomatis hingga tabung habis atau target selesai."""
        import asyncio

        status = await self.get_status()
        if not status.get("aktif"):
            return {"status": "inactive", "message": "Fitur diving sedang tidak aktif."}
        if not status.get("diPulau"):
            return {"status": "not_in_island", "message": "Akun tidak sedang berada di Pulau Seberang."}

        # Masuk atau lanjutkan sesi
        session_data = await self.enter_or_resume_session()
        session_id = session_data.get("id")
        if not session_id:
            return {"status": "failed", "message": "Gagal memulai sesi diving.", "raw": session_data}

        opened: set[int] = set(session_data.get("buka") or [])
        hari = status.get("hari", "2026-11-23")
        all_kerang = generate_kerang_for_day(hari)
        tour = self.plan_shell_tour(all_kerang, already_opened=opened)

        pearls_found = 0
        pearls_value_milli = 0
        shells_opened_count = 0

        for kerang, travel_time in tour:
            if max_shells is not None and shells_opened_count >= max_shells:
                break

            total_wait = max(0.5, travel_time + safety_buffer)
            if on_progress:
                on_progress({
                    "event": "swimming",
                    "kerang": kerang.i,
                    "x": kerang.x,
                    "z": kerang.z,
                    "depth": kerang.d,
                    "wait_seconds": total_wait,
                })

            await asyncio.sleep(total_wait)

            res = await self.open_shell(session_id, kerang.i)
            shells_opened_count += 1
            opened.add(kerang.i)

            is_pearl = res.get("isi") == "mutiara"
            val = int(res.get("hargaMilli") or 0) if is_pearl else 0
            if is_pearl:
                pearls_found += 1
                pearls_value_milli += val

            if on_progress:
                on_progress({
                    "event": "opened",
                    "kerang": kerang.i,
                    "result": res.get("isi", "kosong"),
                    "value_milli": val,
                    "pearls_found": pearls_found,
                    "shells_opened_count": shells_opened_count,
                })

        # Jika ada mutiara, jual ke kas desa
        sell_result = None
        if pearls_found > 0:
            sell_result = await self.sell_pearls()
            if on_progress:
                on_progress({"event": "sold", "result": sell_result})

        # Selesaikan sesi untuk mendapatkan +30 rekreasi
        finish_result = await self.finish_session(session_id)
        if on_progress:
            on_progress({"event": "finished", "result": finish_result})

        return {
            "status": "success",
            "session_id": session_id,
            "shells_opened": shells_opened_count,
            "pearls_found": pearls_found,
            "pearls_value_milli": pearls_value_milli,
            "sell_result": sell_result,
            "finish_result": finish_result,
        }

