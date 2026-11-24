import json
import re
from collections.abc import Collection
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal
from zoneinfo import ZoneInfo

from .models import Need, PurchasePlan, Resource, Settings, ShopPreview, Snapshot, Step, now

WIB = ZoneInfo("Asia/Jakarta")

SLEEPING_NOTICE = re.compile(r"(?:^|\n)\s*Kamu sedang tidur\b", re.IGNORECASE)


def is_sleeping(state: Snapshot):
    return state.phase == "sleeping" or bool(SLEEPING_NOTICE.search(state.raw_text))


def decimal_id(text: str) -> Decimal:
    text = text.strip()
    if not re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?", text):
        raise ValueError("Angka Indonesia tidak dikenal")
    return Decimal(text.replace(".", "").replace(",", "."))


def parse_snapshot(data: dict) -> Snapshot:
    text = data["text"]
    tiles = data["tiles"]
    buttons = [entry["text"].strip() for entry in data["buttons"]]
    countdown = re.search(r"Mengantar[^\d]*(\d+):([0-5]\d)", " ".join(buttons))
    if SLEEPING_NOTICE.search(text):
        phase, remaining = "sleeping", None
    elif countdown:
        phase = "delivering"
        remaining = int(countdown[1]) * 60 + int(countdown[2])
    elif any("Mencari" in button for button in buttons):
        phase, remaining = "searching", None
    elif any(re.search(r"Selesaikan|Sampai|Selesai", button, re.IGNORECASE) for button in buttons):
        phase, remaining = "complete", 0
    elif any(
        "Cari order" in button or re.search(r"Terima|Ambil|Antar sekarang", button, re.IGNORECASE)
        for button in buttons
    ):
        phase, remaining = "idle", None
    else:
        phase, remaining = "unknown", None

    def percent(label: str) -> int:
        match = re.fullmatch(r"(\d{1,3})%", tiles[label].strip())
        if match is None:
            raise ValueError(f"Persentase {label} belum terbaca")
        return int(match[1])

    wallet = re.search(r"([\d.,]+)\s*koin", data["wallet"], re.IGNORECASE)
    if not wallet:
        raise ValueError("Dompet cash belum terbaca")
    ojol_resting = bool(
        re.search(r"ojol\s*wajib\s*istirahat|istirahat\s*dulu\s*30\s*menit", text, re.IGNORECASE)
    )
    shift_done = bool(
        re.search(
            r"8\s*jam|maksimal.*(?:hari|00[.:]00)|lanjut\s*besok|paling\s*lama\s*8\s*jam",
            text,
            re.IGNORECASE,
        )
    )
    ojol_maintenance = bool(
        re.search(
            r"ojol.*(?:maintenance|pemeliharaan|perbaikan)|(?:maintenance|pemeliharaan|perbaikan).*ojol",
            text,
            re.IGNORECASE,
        )
    )
    return Snapshot(
        wallet=decimal_id(wallet[1]),
        fuel=percent("Bensin"),
        condition=percent("Kondisi"),
        data=percent("Kuota HP"),
        phase=phase,
        remaining_seconds=remaining,
        trip=data.get("trip"),
        buttons=buttons,
        history=data.get("history", []),
        today_income=decimal_id(tiles["Hasil hari ini"]) if "Hasil hari ini" in tiles else None,
        raw_text=text,
        ojol_resting=ojol_resting,
        ojol_shift_done=shift_done,
        ojol_maintenance=ojol_maintenance,
    )


def next_step(
    state: Snapshot, settings: Settings, *, deferred: Collection[Resource] | None = None
) -> Step:
    if is_sleeping(state):
        return Step(
            action="wait",
            reason="Karakter sedang tidur. Semua Auto dijeda sampai bangun di game.",
            wait_seconds=settings.idle_poll_seconds,
        )
    if state.phase == "searching":
        return Step(
            action="wait",
            reason="Pencarian sedang diproses; jangan mengirim klik duplikat.",
            wait_seconds=2,
        )
    if state.phase == "delivering":
        if state.remaining_seconds is None:
            return Step(action="stop", reason="Countdown tidak terbaca")
        return Step(
            action="wait",
            reason="Tunggu perjalanan yang sedang berjalan, tanpa klik lebih awal.",
            wait_seconds=max(1, state.remaining_seconds + 1),
        )
    if state.phase == "complete":
        return Step(action="complete", reason="UI menampilkan perjalanan siap diselesaikan.")
    if state.phase != "idle":
        return Step(action="stop", reason="Status Ojol tidak dikenal; tidak menebak tombol.")
    if state.ojol_resting:
        wait_seconds = settings.idle_poll_seconds
        if state.ojol_rest_until and state.observed_at:
            diff = (state.ojol_rest_until - state.observed_at).total_seconds()
            if diff > 0:
                wait_seconds = max(5, min(int(diff) + 1, 1800))
        return Step(
            action="wait",
            reason="Mitra ojol sedang dalam masa wajib istirahat (30 menit setelah narik 3 jam).",
            wait_seconds=wait_seconds,
        )
    if state.ojol_shift_done:
        now_wib = (state.observed_at or now()).astimezone(WIB)
        tomorrow_midnight = (now_wib + timedelta(days=1)).replace(
            hour=0, minute=0, second=5, microsecond=0
        )
        diff = max(1, int((tomorrow_midnight - now_wib).total_seconds()))
        wait_seconds = min(diff, max(settings.idle_poll_seconds, 60))
        return Step(
            action="wait",
            reason="Batas narik 8 jam hari ini tercapai. Lanjut besok mulai jam 00.00 WIB.",
            wait_seconds=wait_seconds,
        )
    if getattr(state, "ojol_maintenance", False):
        return Step(
            action="wait",
            reason="Fitur Auto Ojol sedang maintenance.",
            wait_seconds=settings.idle_poll_seconds,
        )
    keys: tuple[Resource, ...] = ("fuel", "condition", "data")
    resources = sorted((getattr(state, key), key) for key in keys)
    for value, resource in resources:
        thresh = settings.threshold_for(resource)
        if value < thresh and resource not in (deferred or ()):
            return Step(
                action="maintain", resource=resource, reason=f"{resource} {value}% di bawah target"
            )
    if state.ojol_min_fuel is not None and (
        state.ojol_fuel_blocked or state.fuel < state.ojol_min_fuel
    ):
        return Step(
            action="wait",
            resource="fuel",
            reason="Bawa kendaraan Ojol ke SPBU untuk isi ulang.",
            wait_seconds=settings.idle_poll_seconds,
        )
    if any("Cari order" in button for button in state.buttons):
        return Step(action="search", reason="Resource aman, cari order melalui UI.")
    if any(
        re.search(r"Terima|Ambil|Antar sekarang", button, re.IGNORECASE) for button in state.buttons
    ):
        return Step(action="take", reason="Order terlihat dan resource aman.")
    return Step(action="stop", reason="Tidak ada aksi Ojol yang dikenali")


ALLOWED_ITEMS = {
    "fuel": {
        "Isi Pertalite",
        "Isi Pertamax",
        "Isi daya SPKLU (mobil listrik)",
        "Isi bensin motor",
        "Isi bensin mobil",
    },
    "condition": {
        "Servis motor",
        "Ganti oli",
        "Tambal ban",
        "Isi angin",
        "Cuci motor",
        "Servis mobil",
    },
    "data": {"Isi pulsa", "Paket data", "Servis HP", "Casing HP"},
}


def select_shop(
    state: Snapshot,
    resource: Resource,
    shops: list[ShopPreview],
    settings: Settings,
    spent: Decimal,
    *,
    last_purchases: dict[str, int] | None = None,
) -> tuple[tuple[ShopPreview, PurchasePlan] | None, bool]:
    current = getattr(state, resource)
    thresh = settings.threshold_for(resource)
    if current >= thresh:
        return None, False
    above_reserve = current > settings.resource_reserve_percent
    candidates = []
    capacity_blocked = False
    for shop in shops:
        for product in shop.products:
            gain = product.effects.get(resource, 0)
            if product.name not in ALLOWED_ITEMS[resource] or not product.enabled or gain <= 0:
                continue
            if (
                resource == "fuel"
                and product.name in {"Isi daya SPKLU (mobil listrik)", "Isi bensin mobil"}
                and state.ojol_vehicle is not None
                and state.ojol_vehicle != "mobil"
            ):
                continue
            if (
                resource == "fuel"
                and product.name == "Isi bensin motor"
                and state.ojol_vehicle is not None
                and state.ojol_vehicle != "motor"
            ):
                continue
            if (
                resource == "condition"
                and product.name == "Servis mobil"
                and state.ojol_vehicle != "mobil"
            ):
                continue
            quantity = int(
                (Decimal(thresh - current) / gain).to_integral_value(rounding=ROUND_CEILING)
            )
            total = product.price * quantity
            if (
                settings.max_spend is not None and spent + total > settings.max_spend
            ) or state.wallet - total < max(Decimal(5), settings.min_balance + Decimal("0.01")):
                continue
            projected = current + gain * quantity
            if projected > 100:
                capacity_blocked = True
                continue
            candidates.append(
                (
                    shop,
                    PurchasePlan(
                        resource=resource,
                        product=product,
                        quantity=quantity,
                        total_cost=total,
                        projected_percent=projected,
                    ),
                )
            )
    last_purchases = last_purchases or {}
    value_first = resource == "condition" and state.ojol_vehicle == "mobil"
    selection = min(
        candidates,
        key=lambda choice: (
            choice[1].total_cost / (choice[1].projected_percent - current) if value_first else 0,
            choice[1].total_cost if value_first else 0,
            not choice[0].preferred,
            last_purchases.get(choice[0].id, 0) if choice[0].preferred else 0,
            choice[1].total_cost / (choice[1].projected_percent - current),
            choice[1].total_cost,
            choice[0].distance_squared,
            choice[0].id,
            choice[1].product.row_text,
        ),
        default=None,
    )
    return selection, selection is None and above_reserve and capacity_blocked


def is_minigame_product(product, resource):
    if resource != "fisik" or product.price != Decimal(0) or not product.enabled:
        return False
    if not product.row_text or not product.row_text.startswith("{"):
        return False
    try:
        return json.loads(product.row_text).get("item") == "minigame"
    except Exception:
        return False


def select_need(
    state: Snapshot,
    resource: Need,
    shops: list[ShopPreview],
    settings: Settings,
    spent: Decimal,
    last_purchases: dict[str, int],
    *,
    allow_fallback=False,
    streak_product: str | None = None,
    streak_count: int = 0,
) -> tuple[ShopPreview, PurchasePlan] | None:
    current = state.needs.get(resource)
    thresh = settings.threshold_for(resource)
    has_free_minigame = resource == "fisik" and any(
        any(is_minigame_product(p, resource) for p in s.products) for s in shops
    )
    if current is None or (current >= thresh and not has_free_minigame):
        return None

    def value_key(choice):
        shop, plan = choice
        points = max(
            1,
            sum(
                min(100 - value, plan.product.effects.get(need, 0))
                for need, value in state.needs.items()
            ),
        )
        is_minigame = False
        is_bored = False
        try:
            data = json.loads(plan.product.row_text)
            is_minigame = data.get("item") == "minigame" or (
                resource == "kesehatan" and shop.category == "fasum"
            )
            is_bored = bool(data.get("bosan"))
        except Exception:
            pass
        is_health_fasum = resource == "kesehatan" and shop.category == "fasum"
        is_sppg_fasum = resource == "makan" and shop.category == "fasum"
        is_rec_fasum = resource == "rekreasi" and shop.category == "fasum"
        is_streak_exhausted = (
            resource == "makan"
            and not is_sppg_fasum
            and (
                is_bored
                or (
                    streak_product is not None
                    and plan.product.name == streak_product
                    and streak_count >= 3
                )
            )
        )
        is_preferred = shop.preferred
        return (
            not is_minigame,
            not is_health_fasum,
            not is_sppg_fasum,
            not is_rec_fasum,
            not is_preferred,
            last_purchases.get(shop.id, 0) if is_preferred else 0,
            is_streak_exhausted,
            0 if is_preferred else shop.distance_squared,
            plan.total_cost / points,
            plan.projected_percent < thresh,
            plan.total_cost,
            -points,
            shop.distance_squared,
            shop.id,
            plan.product.row_text,
        )

    candidates = []
    allow_fallback = allow_fallback and not any(shop.preferred for shop in shops)
    for shop in shops:
        if resource == "fisik":
            if shop.category != "fasum":
                continue
        elif shop.category == "fasum" and resource in {"kesehatan", "makan", "rekreasi"}:
            pass
        elif shop.category == "kamar-mandi" and resource in {"kebersihan", "wc"}:
            pass
        elif not shop.preferred and not allow_fallback:
            continue
        for product in shop.products:
            gain = min(100 - current, product.effects.get(resource, 0))
            is_free_mg = is_minigame_product(product, resource)
            if not product.enabled or (gain <= 0 and not is_free_mg):
                continue
            if current >= thresh and not is_free_mg:
                continue
            if (settings.max_spend is not None and spent + product.price > settings.max_spend) or (
                product.price > Decimal(0)
                and (
                    (resource != "makan" and state.wallet - product.price < Decimal(20))
                    or state.wallet - product.price
                    < max(Decimal(5), settings.min_balance + Decimal("0.01"))
                )
            ):
                continue
            candidates.append(
                (
                    shop,
                    PurchasePlan(
                        resource=resource,
                        product=product,
                        quantity=1,
                        total_cost=product.price,
                        projected_percent=min(100, current + gain),
                    ),
                )
            )
    return min(candidates, key=value_key, default=None)
