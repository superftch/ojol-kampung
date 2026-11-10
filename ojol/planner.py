import re
from decimal import ROUND_CEILING, Decimal

from .models import Product, PurchasePlan, Settings, Snapshot, Step

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
    state: Snapshot, settings: Settings, catalog: dict[str, list[Product]] | None = None
) -> Step:
    if is_sleeping(state):
        return Step(
            action="stop",
            reason="Kamu sedang tidur. Tekan ☀ Bangun di game sebelum menjalankan Ojol.",
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
        if value < settings.threshold:
            products = (catalog or {}).get(resource)
            best = best_value_product(resource, products, settings) if products else None
            ceiling = (
                min(settings.threshold, 100 - best.effects[resource])
                if best
                else settings.threshold
            )
            if value <= ceiling or value <= settings.resource_reserve_percent:
                return Step(
                    action="maintain",
                    resource=resource,
                    reason=f"{resource} {value}%: batas isi tanpa efek terbuang {ceiling}%",
                )
    if any("Cari order" in button for button in state.buttons):
        return Step(action="search", reason="Resource aman, cari order melalui UI.")
    if any(
        re.search(r"Terima|Ambil|Antar sekarang", button, re.IGNORECASE) for button in state.buttons
    ):
        return Step(action="take", reason="Order terlihat dan resource aman.")
    return Step(action="stop", reason="Tidak ada aksi Ojol yang dikenali")


ALLOWED_ITEMS = {
    "fuel": {"Isi Pertalite", "Isi Pertamax"},
    "condition": {"Servis motor", "Ganti oli", "Tambal ban", "Isi angin", "Cuci motor"},
    "data": {"Isi pulsa", "Paket data", "Servis HP", "Casing HP"},
}


def best_value_product(
    resource: str, products: list[Product], settings: Settings
) -> Product | None:
    safe = [
        item
        for item in products
        if item.name in ALLOWED_ITEMS[resource]
        and item.enabled
        and 0 < item.effects.get(resource, 0) <= 100 - settings.resource_reserve_percent
    ]
    return (
        min(safe, key=lambda item: (item.price / item.effects[resource], item.price, item.name))
        if safe
        else None
    )


def select_product(
    state: Snapshot, resource: str, products: list[Product], settings: Settings, spent: Decimal
) -> PurchasePlan | None:
    current = getattr(state, resource)
    if current >= settings.threshold:
        return None
    best = best_value_product(resource, products, settings)
    if best is None:
        return None
    candidates = []
    for product in products:
        gain = product.effects.get(resource, 0)
        if product.name not in ALLOWED_ITEMS[resource] or not product.enabled or gain <= 0:
            continue
        if product != best and current > settings.resource_reserve_percent:
            continue
        quantity = int(
            (Decimal(settings.threshold - current) / gain).to_integral_value(rounding=ROUND_CEILING)
        )
        total = product.price * quantity
        projected = current + gain * quantity
        if projected > 100:
            continue
        if (
            settings.max_spend is not None and spent + total > settings.max_spend
        ) or state.wallet - total < settings.min_balance + Decimal("0.01"):
            continue
        plan = PurchasePlan(
            resource=resource,
            product=product,
            quantity=quantity,
            total_cost=total,
            projected_percent=projected,
        )
        candidates.append(plan)
    return (
        min(
            candidates,
            key=lambda plan: (
                plan.total_cost / (plan.projected_percent - current),
                plan.total_cost,
                plan.product.name,
            ),
        )
        if candidates
        else None
    )
