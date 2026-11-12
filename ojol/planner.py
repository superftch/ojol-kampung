import re
from decimal import ROUND_CEILING, Decimal

from .models import Need, PurchasePlan, Resource, Settings, ShopPreview, Snapshot, Step

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
    percent = lambda label: int(re.fullmatch(r"(\d{1,3})%", tiles[label].strip())[1])
    wallet = re.search(r"([\d.,]+)\s*koin", data["wallet"], re.IGNORECASE)
    if not wallet:
        raise ValueError("Dompet cash belum terbaca")
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
    )


def next_step(
    state: Snapshot, settings: Settings, *, deferred: set[Resource] | None = None
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
    resources = sorted((getattr(state, key), key) for key in ("fuel", "condition", "data"))
    for value, resource in resources:
        if value < settings.threshold and resource not in (deferred or ()):
            return Step(
                action="maintain", resource=resource, reason=f"{resource} {value}% di bawah target"
            )
    if any("Cari order" in button for button in state.buttons):
        return Step(action="search", reason="Resource aman, cari order melalui UI.")
    if any(
        re.search(r"Terima|Ambil|Antar sekarang", button, re.IGNORECASE) for button in state.buttons
    ):
        return Step(action="take", reason="Order terlihat dan resource aman.")
    return Step(action="stop", reason="Tidak ada aksi Ojol yang dikenali")


ALLOWED_ITEMS = {
    "fuel": {"Isi Pertalite", "Isi Pertamax", "Isi daya SPKLU (mobil listrik)"},
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
    if current >= settings.threshold:
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
                resource == "condition"
                and product.name == "Servis mobil"
                and state.ojol_vehicle != "mobil"
            ):
                continue
            if (
                resource == "fuel"
                and product.name == "Isi daya SPKLU (mobil listrik)"
                and state.ojol_vehicle != "mobil"
            ):
                continue
            quantity = int(
                (Decimal(settings.threshold - current) / gain).to_integral_value(
                    rounding=ROUND_CEILING
                )
            )
            total = product.price * quantity
            if (
                settings.max_spend is not None and spent + total > settings.max_spend
            ) or state.wallet - total < max(Decimal(20), settings.min_balance + Decimal("0.01")):
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


def select_need(
    state: Snapshot,
    resource: Need,
    shops: list[ShopPreview],
    settings: Settings,
    spent: Decimal,
    last_purchases: dict[str, int],
    *,
    allow_fallback=False,
) -> tuple[ShopPreview, PurchasePlan] | None:
    current = state.needs.get(resource)
    if current is None or current >= settings.threshold:
        return None
    low_needs = {need: value for need, value in state.needs.items() if value < settings.threshold}

    def value_key(choice):
        shop, plan = choice
        gains = [
            (value, min(100 - value, plan.product.effects.get(need, 0)))
            for need, value in low_needs.items()
        ]
        points = sum(gain for _, gain in gains)
        filled = sum(value + gain >= settings.threshold for value, gain in gains)
        return (
            last_purchases.get(shop.id, 0) if shop.preferred else 0,
            plan.projected_percent < settings.threshold,
            -filled,
            plan.total_cost / points,
            -points,
            shop.id,
            plan.product.row_text,
        )

    candidates = []
    allow_fallback = allow_fallback and not any(shop.preferred for shop in shops)
    for shop in shops:
        if resource == "fisik":
            if shop.category != "fasum":
                continue
        elif not shop.preferred and not allow_fallback:
            continue
        for product in shop.products:
            gain = min(100 - current, product.effects.get(resource, 0))
            if not product.enabled or gain <= 0:
                continue
            if (
                settings.max_spend is not None and spent + product.price > settings.max_spend
            ) or state.wallet - product.price < max(
                Decimal(20), settings.min_balance + Decimal("0.01")
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
                        projected_percent=current + gain,
                    ),
                )
            )
    return min(candidates, key=value_key, default=None)
