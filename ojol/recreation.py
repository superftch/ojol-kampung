"""Recreation fasum automation & foto minigame solver."""

from __future__ import annotations


def solve_foto_shots(periods: list[int | float], lead_ms: int = 600) -> list[int]:
    """Hitung waktu jepretan kamera ideal (pas di tengah bingkai kamera, p = 0.5)."""
    return [round(lead_ms + p * 0.25) for p in periods]
