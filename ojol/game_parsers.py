"""Stateless KampungSebelah API response and bundle parsers."""

import json
import re
from decimal import Decimal
from math import ceil, floor
from typing import Any, cast

from .finance import WIB
from .formatting import display_coin as display
from .formatting import parse_api_timestamp as timestamp
from .models import NEEDS, GameReceipt, HttpCoreError, Need, OjolVehicle, SleepSchedule, Snapshot
from .planner import ALLOWED_ITEMS

ORIGIN = "https://www.kampungsebelah.com"
KAMAR_MANDI_ID = "00000000-0000-0000-0000-000000000001"
ITEMS: dict[str, set[str]] = {
    "fuel": {"isi-pertalite", "isi-pertamax"},
    "condition": {"servis-motor", "ganti-oli", "tambal-ban", "isi-angin", "cuci-motor"},
    "data": {"pulsa", "paket-data", "servis-hp", "casing-hp"},
}
CAR_SERVICE = "servis-mobil"
EV_CHARGE = "isi-daya"
VEHICLE_ICONS = {"motor": "🛵", "mobil": "🚗"}
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


class ShopClosed(HttpCoreError):
    """Raised when a target shop or facility is closed."""


class HouseUnavailable(HttpCoreError):
    """Raised when a house interior is closed/forbidden to visit."""


def is_unavailable_house_response(response: Any) -> bool:
    try:
        return response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
    except (KeyError, TypeError, ValueError):
        return False


def is_closed_shop_response(response: Any) -> bool:
    try:
        error = response.json()["error"]
        return (
            error["code"] == "REQUIREMENT_NOT_MET" and error["message"] == "Usaha ini belum buka."
        )
    except (KeyError, TypeError, ValueError):
        return False


def integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise HttpCoreError("Format angka API berubah", recoverable=True)
    return value


def coin(milli: int) -> Decimal:
    return Decimal(integer(milli)) / 1000


def need_rows(payload: dict[str, Any]) -> dict[Need, dict[str, Any]]:
    rows = payload.get("needs")
    if payload.get("enabled") is not True or not isinstance(rows, list):
        return {}
    return {
        cast(Need, row["id"]): row
        for row in rows
        if isinstance(row, dict)
        and row.get("id") in NEEDS
        and type(row.get("value")) is int
        and 0 <= row["value"] <= 100
    }


def ojol_vehicle(payload: dict[str, Any], trip: dict[str, Any] | None) -> OjolVehicle | None:
    if trip:
        vehicle = trip.get("vehicle", payload.get("vehicle"))
        return cast(OjolVehicle, vehicle) if vehicle in ("motor", "mobil") else None
    available = payload.get("vehicles", [payload.get("vehicle")])
    if not isinstance(available, list):
        raise HttpCoreError("Daftar kendaraan Ojol belum dapat dibaca", recoverable=True)
    selected = payload.get("vehicle")
    if (
        "bensinMin" in (payload.get("pakai") or {})
        and selected in ("motor", "mobil")
        and selected in available
    ):
        return cast(OjolVehicle, selected)
    choices: tuple[OjolVehicle, ...] = ("mobil", "motor")
    return next((vehicle for vehicle in choices if vehicle in available), None)


def snapshot_from_api(
    ojol: dict[str, Any],
    me: dict[str, Any],
    needs: dict[str, Any],
    server_now: Any,
    *,
    require_ojol: bool = True,
) -> Snapshot:
    problem_text = str(ojol.get("problem") or "")
    is_ojol_maintenance = bool(
        ojol.get("maintenance") is True
        or re.search(
            r"maintenance|pemeliharaan|perbaikan",
            problem_text or str(ojol.get("text") or ""),
            re.IGNORECASE,
        )
        or (ojol.get("enabled") is False and ojol.get("mitra") is True)
    )
    if (
        require_ojol
        and not is_ojol_maintenance
        and (ojol["enabled"] is not True or ojol["mitra"] is not True)
    ):
        raise HttpCoreError("Akun belum menjadi mitra Ojol", category="blocked")
    if type(needs["asleep"]) is not bool:
        raise HttpCoreError("Status tidur API berubah", recoverable=True)
    profile = me.get("profile") or {}
    resting = profile.get("resting", False)
    if type(resting) is not bool:
        raise HttpCoreError("Status istirahat API berubah", recoverable=True)
    schedule = profile.get("sleep")
    sleep_schedule = (
        SleepSchedule(
            auto=schedule["auto"],
            start=schedule["from"],
            end=schedule["to"],
            in_schedule=schedule["inSchedule"],
        )
        if schedule is not None
        else None
    )
    trip = ojol.get("trip") if not require_ojol and ojol.get("mitra") is False else ojol["trip"]
    vehicle = ojol_vehicle(ojol, trip) if require_ojol else None
    vehicle_icon = VEHICLE_ICONS.get(vehicle, "📍")
    phase, remaining, description = "idle", None, None
    buttons = ["📲 Cari order", "Berhenti jadi mitra ojol"]
    text = f"Narik pakai {vehicle}" if vehicle else ""

    is_ojol_resting = False
    ojol_rest_until = None
    if ojol.get("istirahatSampai"):
        try:
            until = timestamp(ojol["istirahatSampai"])
            if until > server_now:
                is_ojol_resting = True
                ojol_rest_until = until
        except (ValueError, TypeError):
            pass
    if not is_ojol_resting and (
        ojol.get("resting") is True
        or ojol.get("restUntil") is not None
        or bool(re.search(r"istirahat|rehat|3 jam", problem_text, re.IGNORECASE))
    ):
        is_ojol_resting = True
        if ojol.get("restUntil"):
            try:
                ojol_rest_until = timestamp(ojol["restUntil"])
            except (ValueError, TypeError):
                pass

    is_shift_done = False
    hours_left = None
    if "narikMenit" in ojol and "narikMaksMenit" in ojol:
        try:
            narik_menit = float(ojol["narikMenit"])
            narik_maks_menit = float(ojol["narikMaksMenit"])
            hours_left = max(0.0, (narik_maks_menit - narik_menit) / 60.0)
            if narik_menit >= narik_maks_menit:
                is_shift_done = True
        except (ValueError, TypeError):
            pass
    if hours_left is None:
        for key in (
            "sisaJam",
            "sisaJamNarik",
            "sisaNarik",
            "jamNarikSisa",
            "hoursLeft",
            "sisaWaktu",
            "dailyHoursLeft",
        ):
            if key in ojol and isinstance(ojol[key], (int, float)):
                hours_left = float(ojol[key])
                break
    if hours_left is None:
        match = re.search(
            r"(?:sisa\s*(?:jam\s*narik|waktu)?|tersisa)\s*[:]?\s*(\d+(?:[.,]\d+)?)\s*jam",
            problem_text or str(ojol.get("text") or ""),
            re.IGNORECASE,
        )
        if match:
            hours_left = float(match[1].replace(",", "."))

    if (
        bool(
            re.search(
                r"(?:8|12)\s*jam|maksimal.*(?:hari|00[.:]00)|batas.*(?:harian|narik)|lanjut\s*besok|paling\s*lama\s*(?:8|12)\s*jam",
                problem_text,
                re.IGNORECASE,
            )
        )
        or ojol.get("shiftDone") is True
        or ojol.get("dailyLimitReached") is True
        or (hours_left is not None and hours_left <= 0)
    ):
        is_shift_done = True

    order_code = None
    if trip:
        raw_cek = trip.get("cek")
        if isinstance(raw_cek, str):
            order_code = raw_cek
        elif raw_cek is not None and not isinstance(raw_cek, (bool, int)):
            raise HttpCoreError("Kode cek trip Ojol tidak valid", recoverable=True)
        icon, label = KINDS[trip["kind"]]
        is_kendara = trip.get("mode") == "kendara"
        is_arrived = trip.get("arrived") is True
        jemput_done = trip.get("jemput") is True if is_kendara else True
        if trip.get("arriveAt"):
            remaining = max(0, ceil((timestamp(trip["arriveAt"]) - server_now).total_seconds()))
        else:
            remaining = 0
        if is_kendara:
            phase = "complete" if (is_arrived or (jemput_done and remaining == 0)) else "delivering"
        else:
            phase = "complete" if remaining == 0 else "delivering"
        from_label = (
            trip["from"]["label"]
            if isinstance(trip.get("from"), dict) and "label" in trip["from"]
            else "Titik jemput"
        )
        to_label = (
            trip["to"]["label"]
            if isinstance(trip.get("to"), dict) and "label" in trip["to"]
            else "Tujuan"
        )
        description = (
            f"{icon} {label} · {vehicle_icon} {integer(trip['distance'])} petak · "
            f"ongkos {display(coin(trip['fareMilli']))} koin | 📍 {from_label}🏁 {to_label}"
        )
        buttons = [
            "✅ Sampai! Terima ongkos"
            if phase == "complete"
            else f"{vehicle_icon} Mengantar… {remaining // 60}:{remaining % 60:02}",
            "📍 Lihat di peta",
        ]
        text = description
    if needs["asleep"] or resting:
        phase, text = "sleeping", "Karakter sedang tidur. Semua Auto dijeda sampai bangun di game."
    elif is_ojol_resting:
        buttons = ["Berhenti jadi mitra ojol"]
        text = (
            problem_text or "Mitra ojol wajib istirahat 30 menit setelah 3 jam narik tanpa henti."
        )
    elif is_shift_done:
        buttons = ["Berhenti jadi mitra ojol"]
        text = (
            problem_text
            or "Mitra ojol bisa narik paling lama 8 jam per hari, lanjut besok mulai jam 00.00."
        )
    elif is_ojol_maintenance:
        buttons = ["Berhenti jadi mitra ojol"]
        text = problem_text or "Fitur Auto Ojol sedang dalam pemeliharaan (maintenance)."
    elif require_ojol and ojol.get("problem") and not trip:
        if ojol.get("fix") not in RESOURCES:
            raise HttpCoreError(
                "Game menolak Ojol: periksa kondisi akun di game", category="blocked"
            )
        buttons = ["Berhenti jadi mitra ojol"]
    if require_ojol and not is_ojol_maintenance and phase == "idle" and vehicle is None:
        raise HttpCoreError(
            "Tidak ada motor atau mobil yang tersedia untuk Ojol", category="blocked"
        )

    history: list[str] = []
    game_history: dict[str, GameReceipt] = {}
    for receipt in ojol["history"] if require_ojol else ojol.get("history", []):
        record = GameReceipt(
            id=receipt["id"],
            done_at=timestamp(receipt["doneAt"]),
            kind=receipt["kind"],
            origin=receipt["from"]["label"],
            destination=receipt["to"]["label"],
            amount=coin(receipt["netMilli"]),
        )
        if record.id in game_history:
            if game_history[record.id] != record:
                raise HttpCoreError("Receipt Ojol memiliki ID sama dengan data berbeda")
            continue
        game_history[record.id] = record
        done = timestamp(receipt["doneAt"]).astimezone(WIB)
        icon, _ = KINDS[receipt["kind"]]
        history.append(
            f"{done:%H.%M} {icon} {receipt['from']['label']} → {receipt['to']['label']} · +{display(coin(receipt['netMilli']))}"
        )

    bars = ojol["bars"] if require_ojol else (ojol.get("bars") or {})
    minimum = (ojol.get("pakai") or {}).get("bensinMin")
    min_fuel = minimum if type(minimum) is int and 1 <= minimum <= 100 else None
    fuel = bars["bensin"] if require_ojol else bars.get("bensin", 0)
    if vehicle and min_fuel is not None:
        tank = "bensinMobil" if vehicle == "mobil" else "bensin"
        rows = needs.get("needs")
        tank_value = (
            next(
                (
                    row.get("value")
                    for row in rows
                    if isinstance(row, dict) and row.get("id") == tank
                ),
                None,
            )
            if isinstance(rows, list)
            else None
        )
        if (
            isinstance(tank_value, (int, float))
            and not isinstance(tank_value, bool)
            and 0 <= tank_value <= 100
        ):
            fuel = floor(tank_value)
        elif vehicle != ojol.get("vehicle"):
            raise HttpCoreError("Tangki kendaraan Ojol belum dapat dibedakan", recoverable=True)
        elif type(fuel) in (int, float) and 0 <= fuel <= 100:
            fuel = floor(fuel)

    income = ojol["earnedTodayMilli"] if require_ojol else ojol.get("earnedTodayMilli", 0)
    return Snapshot(
        observed_at=server_now,
        wallet=coin(me["balanceMilli"]),
        fuel=integer(fuel),
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
        game_history=list(game_history.values()),
        today_count=integer(ojol["todayCount"]) if "todayCount" in ojol else None,
        trip_id=trip["id"] if trip else None,
        order_code=order_code if trip else None,
        order_verify=bool(order_code) or bool(trip and trip.get("cek") is True),
        arrive_at=timestamp(trip["arriveAt"]) if trip and trip.get("arriveAt") else None,
        home_plot=(me.get("home") or {}).get("plotId"),
        village=(me.get("home") or {}).get("desa"),
        sleep_schedule=sleep_schedule,
        ojol_vehicle=vehicle,
        ojol_min_fuel=min_fuel,
        ojol_fuel_blocked=bool(ojol.get("problem") and ojol.get("fix") == "bensin"),
        ojol_resting=is_ojol_resting,
        ojol_rest_until=ojol_rest_until,
        ojol_shift_done=is_shift_done,
        ojol_hours_left=hours_left,
        ojol_maintenance=is_ojol_maintenance,
        ojol_mode=trip.get("mode") if trip else None,
        trip_jemput=trip.get("jemput") if trip else None,
        kondisi=needs.get("kondisi") or {},
        bersih=needs.get("bersih") or {},
    )


def extract_effects(source: str) -> dict[str, dict[str, int]]:
    allowed = set.union(*ITEMS.values()) | {CAR_SERVICE, EV_CHARGE}
    result: dict[str, dict[str, int]] = {}
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


def extract_need_effects(source: str, group: str = "barang") -> dict[str, dict[str, int]]:
    for match in re.finditer(r'"' + group + r'"\s*:\s*\{', source):
        try:
            items, _ = json.JSONDecoder().raw_decode(source, match.end() - 1)
        except ValueError:
            continue
        required = (
            {"nasi-goreng", "tambal-ban", "pulsa"}
            if group == "barang"
            else {"gym-desa", "kolam-renang"}
        )
        if not required <= items.keys():
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
