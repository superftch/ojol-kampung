"""Test kalkulasi dan controller otomasi diving."""

from unittest.mock import AsyncMock

import pytest

from app.modules.gameplay.diving import (
    KERANG_CONFIG,
    DivingController,
    calculate_travel_seconds,
    generate_kerang_for_day,
    get_sea_depth,
)


def test_generate_kerang_count_and_determinism():
    day = "2026-11-23"
    kerang1 = generate_kerang_for_day(day)
    kerang2 = generate_kerang_for_day(day)

    assert len(kerang1) == KERANG_CONFIG["jumlah"]
    assert len(kerang1) == 48

    # Harus deterministik
    assert kerang1 == kerang2

    # Kerang pertama harus sesuai sampel ekstraksi client
    first = kerang1[0]
    assert first.i == 0
    assert first.x == -119.6
    assert first.z == -411.7
    assert first.d == 31.8
    assert first.putar == 3.43
    assert first.besar == 1.2


def test_sea_depth_bounds():
    # Kedalaman di titik pantai dan palung
    d_pantai = get_sea_depth(0, -26)
    assert d_pantai >= 0.9

    d_dalam = get_sea_depth(0, -400)
    assert d_dalam > d_pantai


def test_calculate_travel_seconds():
    # Jarak dekat
    t1 = calculate_travel_seconds(0, -26, 0.9, 10, -26, 0.9)
    assert t1 >= KERANG_CONFIG["buka_detik"]

    # Jarak jauh lebih lama
    t2 = calculate_travel_seconds(0, -26, 0.9, 200, -400, 30.0)
    assert t2 > t1


@pytest.mark.asyncio
async def test_diving_controller_methods():
    api = AsyncMock()
    api.request.side_effect = [
        {"aktif": True, "bisaBeli": True, "diPulau": True, "sesi": None},
        {"id": "sesi-123", "mulai": 1000, "hangus": 2800, "buka": []},
        {"isi": "mutiara", "hargaMilli": 100000},
        {"hargaMilli": 100000, "sisa": 0},
        {"rekreasi": 30},
    ]

    controller = DivingController(api)

    status = await controller.get_status()
    assert status["bisaBeli"] is True

    session = await controller.enter_or_resume_session()
    assert session["id"] == "sesi-123"

    opened = await controller.open_shell("sesi-123", 0)
    assert opened["isi"] == "mutiara"

    sold = await controller.sell_pearls()
    assert sold["hargaMilli"] == 100000

    done = await controller.finish_session("sesi-123")
    assert done["rekreasi"] == 30


def test_plan_shell_tour():
    kerang_list = generate_kerang_for_day("2026-11-23")
    controller = DivingController(AsyncMock())

    # Jika kerang 0 sudah dibuka
    tour = controller.plan_shell_tour(kerang_list, already_opened={0})
    assert len(tour) == 47
    assert all(k.i != 0 for k, _ in tour)
