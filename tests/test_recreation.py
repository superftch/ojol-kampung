"""Tests for recreation fasum automation (Taman desa & Alun-alun) & foto minigame."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ojol.http_api import HttpCoreError, OjolHttpApi
from ojol.models import Product, Settings, ShopPreview, Snapshot
from ojol.planner import select_need
from ojol.recreation import solve_foto_shots
from ojol.shop_locations import RECREATION_FACILITIES_BY_VILLAGE


def test_solve_foto_shots_centers_object_precisely():
    periods = [1800.0, 2100.0, 2400.0]
    lead_ms = 600
    shots = solve_foto_shots(periods, lead_ms=lead_ms)
    assert len(shots) == 3

    # Verifikasi dengan formula posisi kamera:
    # t = (shot - lead_ms) / period
    # i = t - floor(t)
    # pos = 2 * i if i < 0.5 else 2 - 2 * i
    for p, s in zip(periods, shots):
        t = (s - lead_ms) / p
        i = t - int(t)
        pos = 2 * i if i < 0.5 else 2 - 2 * i
        assert abs(pos - 0.5) <= 0.01  # Tepat di tengah bingkai kamera


def test_select_need_prioritizes_recreation_fasum_over_paid_shops():
    taman_shop = ShopPreview(
        id="taman-desa-utara",
        plot_id="taman-desa-utara",
        name="Taman desa",
        category="fasum",
        distance_squared=0,
        products=[
            Product(
                name="Bersantai di taman",
                price=Decimal(0),
                effects={"rekreasi": 20},
                row_text=json.dumps(
                    {"shop": "taman-desa-utara", "item": "use", "resource": "rekreasi"}
                ),
                enabled=True,
            )
        ],
    )
    warnet_shop = ShopPreview(
        id="warnet-icafe",
        plot_id="K40-U02",
        name="iCafe Warnet Akademis.ai",
        category="cafe",
        distance_squared=10,
        products=[
            Product(
                name="Main warnet 1 jam",
                price=Decimal("0.5"),
                effects={"rekreasi": 25},
                row_text=json.dumps({"shop": "warnet-icafe", "item": "billing-1jam"}),
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
            "makan": 80,
            "kesehatan": 80,
            "fisik": 80,
            "rekreasi": 35,
            "penampilan": 80,
            "rumah": 80,
        },
    )
    settings = Settings()

    selection = select_need(
        state,
        "rekreasi",
        [warnet_shop, taman_shop],
        settings,
        spent=Decimal(0),
        last_purchases={},
    )
    assert selection is not None
    chosen_shop, plan = selection
    # Taman fasum gratis harus diprioritaskan di atas warnet berbayar
    assert chosen_shop.id == "taman-desa-utara"
    assert plan.product.name == "Bersantai di taman"
    assert plan.total_cost == Decimal(0)


@pytest.mark.asyncio
async def test_preview_rekreasi_returns_fasum_when_available(monkeypatch, tmp_path):
    api = OjolHttpApi(tmp_path)
    api.home = {"desa": "desa-utara"}
    village_rec = RECREATION_FACILITIES_BY_VILLAGE["desa-utara"][0]

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
                needs={"rekreasi": 40},
            )
        ),
    )

    async def mock_request(path, body=None):
        if path == f"/api/facilities/{village_rec}":
            return {
                "id": village_rec,
                "title": "Alun-alun",
                "item": "alun-alun",
                "state": "DONE",
                "nextAt": None,
                "myVisitUntil": None,
                "service": {"label": "Jalan-jalan sore", "open": True},
            }
        raise HttpCoreError(f"Unexpected path: {path}")

    monkeypatch.setattr(api, "request", mock_request)

    res = await api.preview("rekreasi")
    shops = [ShopPreview.model_validate(row) for row in res["shops"]]
    assert len(shops) == 1
    assert shops[0].id == village_rec
    assert shops[0].category == "fasum"
    assert shops[0].products[0].name == "Jalan-jalan sore"
    assert shops[0].products[0].price == Decimal(0)
    assert shops[0].products[0].effects == {"rekreasi": 30, "fisik": 10}


@pytest.mark.asyncio
async def test_preview_rekreasi_skips_fasum_when_on_cooldown(monkeypatch, tmp_path):
    api = OjolHttpApi(tmp_path)
    api.home = {"desa": "desa-utara"}

    future_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

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
                needs={"rekreasi": 40},
            )
        ),
    )

    async def mock_request(path, body=None):
        if path.startswith("/api/facilities/"):
            return {
                "id": path.split("/")[-1],
                "title": "Alun-alun",
                "item": "alun-alun",
                "state": "DONE",
                "nextAt": future_time,
                "myVisitUntil": None,
                "service": {"label": "Jalan-jalan sore", "open": True},
            }
        raise HttpCoreError(f"Unexpected path: {path}")

    monkeypatch.setattr(api, "request", mock_request)

    # Mock akademis_need_shops
    akademis_shop = ShopPreview(
        id="warnet-icafe",
        plot_id="K40-U02",
        name="iCafe Warnet Akademis.ai",
        category="cafe",
        distance_squared=0,
        products=[
            Product(
                name="Main warnet 1 jam",
                price=Decimal("0.5"),
                effects={"rekreasi": 25},
                row_text=json.dumps({"shop": "warnet-icafe", "item": "billing"}),
                enabled=True,
            )
        ],
    )
    monkeypatch.setattr(
        api, "akademis_need_shops", AsyncMock(return_value=([akademis_shop], False))
    )
    monkeypatch.setattr(api, "effects", AsyncMock(return_value={}))

    res = await api.preview("rekreasi")
    shops = [ShopPreview.model_validate(row) for row in res["shops"]]
    assert len(shops) == 1
    assert shops[0].id == "warnet-icafe"
    assert shops[0].products[0].name == "Main warnet 1 jam"


@pytest.mark.asyncio
async def test_buy_recreation_fasum_executes_use_and_foto_minigame(monkeypatch, tmp_path):
    api = OjolHttpApi(tmp_path)
    village_rec = RECREATION_FACILITIES_BY_VILLAGE["desa-utara"][0]

    shop = ShopPreview(
        id=village_rec,
        plot_id=village_rec,
        name="Alun-alun",
        category="fasum",
        distance_squared=0,
        products=[
            Product(
                name="Jalan-jalan sore",
                price=Decimal(0),
                effects={"rekreasi": 30, "fisik": 10},
                row_text=json.dumps({"shop": village_rec, "item": "use", "resource": "rekreasi"}),
                enabled=True,
            )
        ],
    )
    api.catalog["rekreasi"] = {village_rec: shop}

    monkeypatch.setattr(api, "validate_purchase", AsyncMock())
    monkeypatch.setattr("ojol.http_api.auto_flags", lambda _: {"rekreasi": True})

    requests_made = []

    async def mock_request(path, body=None):
        requests_made.append((path, body))
        if path == f"/api/facilities/{village_rec}/use":
            return {"success": True, "visitId": "visit-alun-123"}
        if path == f"/api/facilities/{village_rec}/kegiatan":
            if body is None:
                # GET kegiatan
                return {
                    "available": True,
                    "visitId": "visit-alun-123",
                    "kind": "foto",
                    "plan": {
                        "periods": [1800, 2100, 2400],
                        "scene": {
                            "title": "Sore di alun-alun",
                            "subject": "🎈",
                            "props": ["🌳", "🛕", "🌳"],
                            "sky": "senja",
                            "ground": "lapangan",
                        },
                    },
                }
            # POST kegiatan
            return {
                "success": True,
                "score": 6,
                "maxScore": 6,
                "bonus": True,
                "bonusGains": {"rekreasi": 10},
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
    assert receipt == {"success": True, "visitId": "visit-alun-123"}

    paths = [p for p, _ in requests_made]
    assert f"/api/facilities/{village_rec}/use" in paths
    assert f"/api/facilities/{village_rec}/kegiatan" in paths

    kegiatan_post = next(
        b
        for p, b in requests_made
        if p == f"/api/facilities/{village_rec}/kegiatan" and b is not None
    )
    assert kegiatan_post["visitId"] == "visit-alun-123"
    assert len(kegiatan_post["shots"]) == 3
    assert kegiatan_post["shots"] == [1050, 1125, 1200]
