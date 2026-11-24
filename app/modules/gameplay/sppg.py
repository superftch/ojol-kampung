"""Satuan Pelayanan Pemenuhan Gizi (SPPG) Makan Bergizi Gratis automation & minigame solver."""

from __future__ import annotations

NAMPAN_TARGET_GROUPS = ("pokok", "lauk", "sayur", "buah", "susu")

DEFAULT_ITEM_GROUPS: dict[str, str | None] = {
    # pokok
    "nasi": "pokok",
    "jagung": "pokok",
    "kentang": "pokok",
    "ubi": "pokok",
    "singkong": "pokok",
    # lauk
    "ikan": "lauk",
    "telur": "lauk",
    "tempe": "lauk",
    "tahu": "lauk",
    "ayam": "lauk",
    "daging": "lauk",
    # sayur
    "bayam": "sayur",
    "brokoli": "sayur",
    "wortel": "sayur",
    "kangkung": "sayur",
    "sawi": "sayur",
    # buah
    "pisang": "buah",
    "jeruk": "buah",
    "apel": "buah",
    "pepaya": "buah",
    "semangka": "buah",
    # susu
    "susu": "susu",
    # junk items (tidak dihitung dalam gizi seimbang)
    "gorengan": None,
    "es-sirup": None,
    "permen": None,
    "mi-instan": None,
}


def solve_nampan_picks(items: list, pick_count: int = 5) -> list[str]:
    """Pilih makanan bergizi seimbang untuk nampan SPPG (pokok, lauk, sayur, buah, susu)."""
    item_list = []
    for it in items:
        if isinstance(it, dict):
            i_id = str(it.get("id"))
            group = it.get("group") or DEFAULT_ITEM_GROUPS.get(i_id)
        else:
            i_id = str(it)
            group = DEFAULT_ITEM_GROUPS.get(i_id)
        item_list.append((i_id, group))

    picks: list[str] = []
    # 1. Pilih 1 item dari masing-masing 5 kelompok gizi target
    for target in NAMPAN_TARGET_GROUPS:
        if len(picks) >= pick_count:
            break
        for i_id, group in item_list:
            if group == target and i_id not in picks:
                picks.append(i_id)
                break

    # 2. Jika masih ada sisa slot, ambil item sehat lain (non-junk)
    if len(picks) < pick_count:
        for i_id, group in item_list:
            if len(picks) >= pick_count:
                break
            if group is not None and i_id not in picks:
                picks.append(i_id)

    # 3. Fallback ambil item apa saja yang tersisa hingga pick_count
    if len(picks) < pick_count:
        for i_id, _ in item_list:
            if len(picks) >= pick_count:
                break
            if i_id not in picks:
                picks.append(i_id)

    return picks
