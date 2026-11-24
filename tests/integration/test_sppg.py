"""Tests for SPPG Makan Bergizi Gratis (MBG) automation & minigame."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.models import Product, Settings, ShopPreview, Snapshot
from app.integrations.kampung.http_api import HttpCoreError, OjolHttpApi
from app.integrations.kampung.shop_locations import SPPG_FACILITIES_BY_VILLAGE
from app.modules.gameplay.sppg import solve_nampan_picks
from app.modules.worker.planner import select_need


def test_solve_nampan_picks_selects_balanced_5_groups():
    items = [
        "nasi",
        "jagung",
        "ikan",
        "telur",
        "bayam",
        "brokoli",
        "pisang",
        "jeruk",
        "susu",
        "gorengan",
        "es-sirup",
    ]
    picks = solve_nampan_picks(items, pick_count=5)
    assert len(picks) == 5
    # Cek bahwa tidak ada junk items yang dipilih
    assert "gorengan" not in picks
    assert "es-sirup" not in picks

    # Cek representasi dari 5 kelompok gizi
    assert "nasi" in picks or "jagung" in picks  # pokok
    assert "ikan" in picks or "telur" in picks  # lauk
    assert "bayam" in picks or "brokoli" in picks  # sayur
    assert "pisang" in picks or "jeruk" in picks  # buah
    assert "susu" in picks  # susu


def test_solve_nampan_picks_with_dict_items_and_fallbacks():
    items = [
        {"id": "singkong", "group": "pokok"},
        {"id": "tahu", "group": "lauk"},
        {"id": "wortel", "group": "sayur"},
        {"id": "apel", "group": "buah"},
        {"id": "susu", "group": "susu"},
        {"id": "permen", "group": None},
    ]
    picks = solve_nampan_picks(items, pick_count=5)
    assert picks == ["singkong", "tahu", "wortel", "apel", "susu"]


def test_select_need_prioritizes_sppg_over_paid_shops():
    sppg_shop = ShopPreview(
        id="sppg-desa-utara",
        plot_id="sppg-desa-utara",
        name="SPPG (dapur Makan Bergizi Gratis)",
        category="fasum",
        distance_squared=0,
        products=[
            Product(
                name="Makan bergizi",
                price=Decimal(0),
                effects={"makan": 60, "kesehatan": 5},
                row_text=json.dumps(
                    {"shop": "sppg-desa-utara", "item": "use", "resource": "makan"}
                ),
                enabled=True,
            )
        ],
    )
    akademis_shop = ShopPreview(
        id="warung-akademis",
        plot_id="K40-U01",
        name="Warung Makan Akademis.ai",
        category="warung",
        distance_squared=10,
        products=[
            Product(
                name="Nasi Ayam Goreng",
                price=Decimal("1.5"),
                effects={"makan": 45},
                row_text=json.dumps({"shop": "warung-akademis", "item": "nasi-ayam"}),
                enabled=True,
            )
        ],
    )

    state = Snapshot(
        wallet=Decimal("10.0"),
        fuel=100,
        condition=100,
        data=100,
        phase="idle",
        needs={
            "makan": 30,
            "kesehatan": 80,
            "fisik": 80,
            "rekreasi": 80,
            "penampilan": 80,
            "rumah": 80,
        },
    )
    settings = Settings()

    # Evaluasi dengan kedua toko tersedia
    selection = select_need(
        state,
        "makan",
        [akademis_shop, sppg_shop],
        settings,
        spent=Decimal(0),
        last_purchases={},
    )
    assert selection is not None
    chosen_shop, plan = selection
    # SPPG harus terpilih sebagai prioritas utama
    assert chosen_shop.id == "sppg-desa-utara"
    assert plan.product.name == "Makan bergizi"
    assert plan.total_cost == Decimal(0)


def test_select_need_sppg_bypasses_streak_boredom():
    sppg_shop = ShopPreview(
        id="sppg-desa-utara",
        plot_id="sppg-desa-utara",
        name="SPPG (dapur Makan Bergizi Gratis)",
        category="fasum",
        distance_squared=0,
        products=[
            Product(
                name="Makan bergizi",
                price=Decimal(0),
                effects={"makan": 60, "kesehatan": 5},
                row_text=json.dumps(
                    {"shop": "sppg-desa-utara", "item": "use", "resource": "makan"}
                ),
                enabled=True,
            )
        ],
    )

    state = Snapshot(
        wallet=Decimal("10.0"),
        fuel=100,
        condition=100,
        data=100,
        phase="idle",
        needs={
            "makan": 35,
            "kesehatan": 80,
            "fisik": 80,
            "rekreasi": 80,
            "penampilan": 80,
            "rumah": 80,
        },
    )
    settings = Settings()

    # Bahkan jika streak_product sama dan streak_count >= 3
    selection = select_need(
        state,
        "makan",
        [sppg_shop],
        settings,
        spent=Decimal(0),
        last_purchases={},
        streak_product="Makan bergizi",
        streak_count=5,
    )
    assert selection is not None
    chosen_shop, _ = selection
    assert chosen_shop.id == "sppg-desa-utara"


@pytest.mark.asyncio
async def test_preview_makan_returns_sppg_when_available(monkeypatch, tmp_path):
    api = OjolHttpApi(tmp_path)
    api.home = {"desa": "desa-utara"}
    village_sppg = SPPG_FACILITIES_BY_VILLAGE["desa-utara"][0]

    # Mock snapshot
    monkeypatch.setattr(
        api,
        "snapshot",
        AsyncMock(
            return_value=Snapshot(
                wallet=Decimal("50.0"),
                fuel=100,
                condition=100,
                data=100,
                phase="idle",
                needs={"makan": 40},
            )
        ),
    )

    async def mock_request(path, body=None):
        if path == f"/api/facilities/{village_sppg}":
            return {
                "id": village_sppg,
                "title": "SPPG (dapur Makan Bergizi Gratis)",
                "state": "DONE",
                "nextAt": None,
                "myVisitUntil": None,
                "service": {"label": "Makan bergizi", "open": True},
            }
        raise HttpCoreError(f"Unexpected path: {path}")

    monkeypatch.setattr(api, "request", mock_request)

    res = await api.preview("makan")
    shops = [ShopPreview.model_validate(row) for row in res["shops"]]
    assert len(shops) == 1
    assert shops[0].id == village_sppg
    assert shops[0].category == "fasum"
    assert shops[0].products[0].name == "Makan bergizi"
    assert shops[0].products[0].price == Decimal(0)


@pytest.mark.asyncio
async def test_preview_makan_skips_sppg_when_on_cooldown(monkeypatch, tmp_path):
    api = OjolHttpApi(tmp_path)
    api.home = {"desa": "desa-utara"}

    future_time = (datetime.now(UTC) + timedelta(hours=12)).isoformat()

    # Mock snapshot
    monkeypatch.setattr(
        api,
        "snapshot",
        AsyncMock(
            return_value=Snapshot(
                wallet=Decimal("50.0"),
                fuel=100,
                condition=100,
                data=100,
                phase="idle",
                needs={"makan": 40},
            )
        ),
    )

    async def mock_request(path, body=None):
        if path.startswith("/api/facilities/"):
            # Semua SPPG di desa sedang cooldown
            return {
                "id": path.split("/")[-1],
                "title": "SPPG (dapur Makan Bergizi Gratis)",
                "state": "DONE",
                "nextAt": future_time,
                "myVisitUntil": None,
                "service": {"label": "Makan bergizi", "open": True},
            }
        raise HttpCoreError(f"Unexpected path: {path}")

    monkeypatch.setattr(api, "request", mock_request)

    # Mock akademis_need_shops
    akademis_shop = ShopPreview(
        id="warung-makan",
        plot_id="K40-U01",
        name="Warung Makan Akademis.ai",
        category="warung",
        distance_squared=0,
        products=[
            Product(
                name="Nasi Rames",
                price=Decimal("1.2"),
                effects={"makan": 40},
                row_text=json.dumps({"shop": "warung-makan", "item": "nasi-rames"}),
                enabled=True,
            )
        ],
    )
    monkeypatch.setattr(
        api, "akademis_need_shops", AsyncMock(return_value=([akademis_shop], False))
    )
    monkeypatch.setattr(api, "effects", AsyncMock(return_value={}))

    res = await api.preview("makan")
    shops = [ShopPreview.model_validate(row) for row in res["shops"]]
    # SPPG di-skip karena cooldown, harus fallback ke warung makan akademis
    assert len(shops) == 1
    assert shops[0].id == "warung-makan"
    assert shops[0].products[0].name == "Nasi Rames"


@pytest.mark.asyncio
async def test_buy_sppg_executes_use_and_nampan_minigame(monkeypatch, tmp_path):
    api = OjolHttpApi(tmp_path)
    village_sppg = SPPG_FACILITIES_BY_VILLAGE["desa-utara"][0]

    shop = ShopPreview(
        id=village_sppg,
        plot_id=village_sppg,
        name="SPPG (dapur Makan Bergizi Gratis)",
        category="fasum",
        distance_squared=0,
        products=[
            Product(
                name="Makan bergizi",
                price=Decimal(0),
                effects={"makan": 60, "kesehatan": 5},
                row_text=json.dumps({"shop": village_sppg, "item": "use", "resource": "makan"}),
                enabled=True,
            )
        ],
    )
    api.catalog["makan"] = {village_sppg: shop}

    # Mock validate_purchase
    monkeypatch.setattr(api, "validate_purchase", AsyncMock())
    # Mock auto_flags
    monkeypatch.setattr(
        "app.integrations.kampung.shop_workflows.auto_flags", lambda _: {"makan": True}
    )

    requests_made = []

    async def mock_request(path, body=None):
        requests_made.append((path, body))
        if path == f"/api/facilities/{village_sppg}/use":
            return {"success": True, "visitId": "visit-mbg-123"}
        if path == f"/api/facilities/{village_sppg}/kegiatan":
            if body is None:
                # GET kegiatan
                return {
                    "available": True,
                    "visitId": "visit-mbg-123",
                    "kind": "nampan",
                    "plan": {
                        "items": [
                            "nasi",
                            "ikan",
                            "bayam",
                            "pisang",
                            "susu",
                            "gorengan",
                        ]
                    },
                }
            # POST kegiatan
            return {
                "success": True,
                "score": 5,
                "maxScore": 5,
                "bonus": True,
                "bonusGains": {"makan": 10, "kesehatan": 5},
            }
        raise HttpCoreError(f"Unexpected path: {path}")

    monkeypatch.setattr(api, "request", mock_request)

    receipt = await api.purchase(
        product=shop.products[0],
        expected_wallet=Decimal("10.0"),
        expected_resource=40,
        min_balance=Decimal(0),
        request_id=str(uuid4()),
    )
    assert receipt == {"success": True, "visitId": "visit-mbg-123"}

    # Pastikan request mencakup use dan kegiatan nampan
    paths = [p for p, _ in requests_made]
    assert f"/api/facilities/{village_sppg}/use" in paths
    assert f"/api/facilities/{village_sppg}/kegiatan" in paths

    # Cek payload post kegiatan
    kegiatan_post = next(
        b
        for p, b in requests_made
        if p == f"/api/facilities/{village_sppg}/kegiatan" and b is not None
    )
    assert kegiatan_post["visitId"] == "visit-mbg-123"
    assert len(kegiatan_post["picks"]) == 5
    assert set(kegiatan_post["picks"]) == {"nasi", "ikan", "bayam", "pisang", "susu"}
