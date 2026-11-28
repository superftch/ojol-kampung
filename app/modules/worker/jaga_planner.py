"""Read the evidenced business fields and rank today's Jaga candidates."""

import random
from datetime import date, datetime

from app.core.models import Model
from app.modules.worker.jaga_settings import BUSINESS_ID, JagaSettings


class Business(Model):
    id: str
    name: str
    customers: int | None = None
    rivals: int | None = None
    net_week_milli: int | None = None
    score: float | None = None
    unavailable: str = ""
    reason: str = ""
    target: int = 0
    minutes: int | None = None
    guarded_in_game: bool = False


def whole(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def listed_businesses(payload: object) -> dict[str, dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("usaha"), list):
        raise ValueError("Daftar usaha tidak tersedia untuk akun ini.")
    listed = {}
    for item in payload["usaha"]:
        if (
            isinstance(item, dict)
            and isinstance(key := item.get("id"), str)
            and BUSINESS_ID.fullmatch(key)
        ):
            listed[key] = item
    if payload["usaha"] and not listed:
        raise ValueError("Daftar usaha tidak berisi ID usaha yang dapat dibaca.")
    return listed


def shop_block(item: dict, shop: object) -> str:
    stock = item.get("bahan")
    if stock is not None:
        count = whole(stock.get("habis")) if isinstance(stock, dict) else None
        if count is None or count < 0:
            return "Data bahan tidak tersedia."
        if count:
            return "Ada bahan habis."
    if not isinstance(shop, dict) or shop.get("mine") is not True or shop.get("village"):
        return "Kepemilikan usaha belum terkonfirmasi."
    if shop.get("open") is not True:
        return "Usaha tutup atau jam buka belum tersedia."
    return ""


def read_business(item: dict, shop: object, report: object) -> Business:
    name = item.get("plang") or item.get("jenis")
    today = report.get("today") if isinstance(report, dict) else None
    week = report.get("week") if isinstance(report, dict) else None
    customers = whole(shop.get("customersYesterday")) if isinstance(shop, dict) else None
    rivals = whole(today.get("rivals")) if isinstance(today, dict) else None
    customers = customers if customers is not None and customers >= 0 else None
    rivals = rivals if rivals is not None and rivals >= 0 else None
    return Business(
        id=item["id"],
        name=name[:120] if isinstance(name, str) else item["id"],
        customers=customers,
        rivals=rivals,
        net_week_milli=whole(week.get("netMilli")) if isinstance(week, dict) else None,
        score=customers * 0.2 * rivals / (rivals + 1.2)
        if customers is not None and rivals is not None
        else None,
        unavailable=shop_block(item, shop),
        guarded_in_game=isinstance(shop, dict) and shop.get("dijaga") is True,
    )


def plan_businesses(
    businesses: list[Business],
    settings: JagaSettings,
    day: date,
    last_guarded: dict[str, datetime],
    account_seed: str,
) -> list[Business]:
    def prepare(business: Business) -> Business:
        override = settings.override.get(business.id)
        low = (override.target_min if override else None) or settings.target_min
        high = (override.target_max if override else None) or settings.target_max
        if override and override.maks_menit is not None:
            high = min(high, override.maks_menit)
            low = min(low, high)
        rng = random.Random(f"{account_seed}:{day}:{business.id}")  # noqa: S311 - target allocation
        reason = business.unavailable
        if (override and not override.aktif) or (settings.mode == "manual" and override is None):
            reason = "Usaha tidak dipilih."
        if not reason and settings.mode == "terbaik":
            if business.score is None or business.customers is None:
                reason = "Data pelanggan atau pesaing belum lengkap."
            elif not business.rivals:
                reason = "Tidak ada pesaing sejenis."
            elif business.customers < settings.min_pelanggan:
                reason = "Pelanggan kemarin di bawah batas."
            elif settings.min_skor is not None and business.score < settings.min_skor:
                reason = "Estimasi tambahan pembeli di bawah batas."
        return business.model_copy(update={"reason": reason, "target": rng.randint(low, high)})

    def rank(business: Business):
        override = settings.override.get(business.id)
        priority = -(override.prioritas if override else 0)
        if settings.mode == "rotasi":
            last = last_guarded.get(business.id)
            metric = last.timestamp() if last else float("-inf")
        else:
            metric = -(business.score or 0) if settings.mode == "terbaik" else 0
        return bool(business.reason), metric, priority, business.id

    return sorted(map(prepare, businesses), key=rank)
