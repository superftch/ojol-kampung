from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.models import Snapshot
from app.modules.gameplay.kerja import (
    can_run_kerja,
    fnv1a_32,
    run_kerja,
    solve_urusan_answers,
    urusan_wait_seconds,
)
from app.modules.worker.settings import auto_flags, set_auto_flag


def _snapshot(**overrides):
    defaults = {
        "wallet": Decimal("10.0"),
        "fuel": 100,
        "condition": 100,
        "data": 100,
        "phase": "idle",
        "job": {
            "id": "job-1",
            "profession": "Kepala wilayah bank",
            "employerType": "PUBLIC",
            "facility": "Bank desa",
        },
    }
    defaults.update(overrides)
    return Snapshot(**defaults)


def test_fnv1a_and_solve_urusan_matches_live_sample():
    urusan = {
        "id": "0c9df466-c6e2-4b1d-8757-f24041ca1e7d",
        "langkah": [
            {"aksi": "oper", "pos": "kursi"},
            {"aksi": "proses", "pos": "titik", "detik": 2},
            {
                "aksi": "label",
                "pos": "papan-jadwal",
                "pilihan": ["Biru", "Kuning", "Merah", "Ungu"],
                "kunci": 3213239223,
            },
        ],
    }
    assert fnv1a_32("0c9df466-c6e2-4b1d-8757-f24041ca1e7d:2:2") == 3213239223
    assert solve_urusan_answers(urusan) == [None, None, 2]
    assert urusan_wait_seconds(urusan, datetime.now(UTC)) == pytest.approx(5.7, rel=0.01)


def test_can_run_kerja_enforces_all_guards(tmp_path):
    c = SimpleNamespace(
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(),
    )
    # Default: kerja is False
    assert auto_flags(tmp_path)["kerja"] is False
    assert can_run_kerja(c) is False

    # Enable kerja, but ojol is True by default
    set_auto_flag(tmp_path, "kerja", True)
    assert can_run_kerja(c) is False

    # Turn off ojol -> now eligible
    set_auto_flag(tmp_path, "ojol", False)
    assert can_run_kerja(c) is True

    # Currently ngojol (delivering / trip active) -> blocked
    c.observed_state = _snapshot(phase="delivering", trip="Trip aktif")
    assert can_run_kerja(c) is False

    # Idle but no job -> blocked
    c.observed_state = _snapshot(phase="idle", trip=None, job=None)
    assert can_run_kerja(c) is False


@pytest.mark.asyncio
async def test_run_kerja_kantor_solves_urusan(tmp_path, monkeypatch):
    set_auto_flag(tmp_path, "ojol", False)
    set_auto_flag(tmp_path, "kerja", True)

    calls = []
    events = []

    class FakeUi:
        async def kantor_action(self, action, **fields):
            calls.append((action, fields))
            if action == "detak":
                return {
                    "kantor": {
                        "buka": True,
                        "libur": False,
                        "sekarang": "2026-11-25T05:00:00.000Z",
                        "kerja": {"status": "penuh", "poin": 0, "target": 30},
                        "paket": {"berbayar": True, "lunas": 0, "perHari": 3},
                        "bersama": [],
                        "kejadian": [],
                        "urusan": None,
                        "jedaUrusanDetik": 3,
                    }
                }
            if action == "urusan-mulai":
                return {
                    "id": "0c9df466-c6e2-4b1d-8757-f24041ca1e7d",
                    "judul": "Tinjau pekerjaan",
                    "langkah": [
                        {"aksi": "sapa"},
                        {"aksi": "proses", "detik": 2},
                        {
                            "aksi": "label",
                            "pilihan": ["Biru", "Kuning", "Merah", "Ungu"],
                            "kunci": 3213239223,
                        },
                    ],
                }
            if action == "urusan-selesai":
                return {"ok": True, "poin": 2, "paket": None}
            raise AssertionError(f"Unexpected action: {action}")

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr("app.modules.gameplay.kerja.asyncio.sleep", fast_sleep)

    c = SimpleNamespace(
        ui=FakeUi(),
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(),
        record_event=lambda kind, msg: events.append((kind, msg)),
    )

    did_work = await run_kerja(c)
    assert did_work is True
    assert [name for name, _ in calls] == ["detak", "urusan-mulai", "urusan-selesai"]
    assert calls[2][1]["jawab"] == [None, None, 2]
    assert events and events[0][0] == "kerja"


@pytest.mark.asyncio
async def test_run_kerja_skips_non_kantor_job(tmp_path):
    set_auto_flag(tmp_path, "ojol", False)
    set_auto_flag(tmp_path, "kerja", True)

    class FakeUi:
        async def kantor_action(self, action, **fields):
            raise AssertionError("Should not call kantor_action for non-kantor job")

        async def kerja_malam_status(self):
            raise AssertionError("Should not call kerja_malam_status when focused on kantor only")

    c = SimpleNamespace(
        ui=FakeUi(),
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(
            job={"id": "gen-1", "profession": "Penjaga pos ronda", "employerType": "GENERAL"}
        ),
        record_event=lambda kind, msg: None,
    )

    assert can_run_kerja(c) is False
    assert await run_kerja(c) is False
