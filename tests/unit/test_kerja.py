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


@pytest.mark.asyncio
async def test_run_kerja_kantor_caps_status_to_max_and_adds_jitter(tmp_path, monkeypatch):
    import json
    import time

    set_auto_flag(tmp_path, "ojol", False)
    set_auto_flag(tmp_path, "kerja", True)

    sleeps = []
    jitter_calls = []

    async def record_sleep(seconds):
        sleeps.append(seconds)

    def fake_jitter(low=2.0, high=4.0):
        jitter_calls.append((low, high))
        assert low >= 2.0
        return low

    monkeypatch.setattr("app.modules.gameplay.kerja.asyncio.sleep", record_sleep)
    monkeypatch.setattr("app.modules.gameplay.kerja._jitter", fake_jitter)

    class FakeUi:
        async def kantor_action(self, action, **fields):
            if action == "detak":
                return {
                    "kantor": {
                        "buka": True,
                        "libur": False,
                        "sekarang": "2026-11-25T05:00:00.000Z",
                        "kerja": {"status": "penuh", "poin": 29, "target": 30},
                        "paket": {"berbayar": True, "lunas": 3, "perHari": 3, "menuju": 2, "perPaket": 5},
                        "bersama": [],
                        "kejadian": [],
                        "urusan": None,
                        "jedaUrusanDetik": 3,
                    }
                }
            if action == "urusan-mulai":
                return {"id": "u1", "judul": "Tinjau", "langkah": [{"aksi": "sapa"}]}
            if action == "urusan-selesai":
                return {"ok": True, "poin": 3, "paket": None}
            raise AssertionError(f"Unexpected action: {action}")

    c = SimpleNamespace(
        ui=FakeUi(),
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(),
        record_event=lambda kind, msg: None,
    )

    assert await run_kerja(c) is True
    assert sleeps and sleeps[0] >= 3.7  # base 1.7 + jitter >= 2.0
    assert jitter_calls
    saved = json.loads((tmp_path / "kerja-status.json").read_text())
    assert saved["poin"] == 30
    assert saved["target"] == 30
    assert saved["lunas"] == 3
    assert saved["menuju"] == 0
    assert saved["state"] == "Selesai hari ini"
    assert saved["completed_date"] == "2026-11-25"
    # Remains armed for tomorrow, but paused until next WIB day
    assert auto_flags(tmp_path)["kerja"] is True
    assert c.kerja_retry_at > time.monotonic() + 3600


@pytest.mark.asyncio
async def test_run_kerja_kantor_pauses_until_tomorrow_and_resumes_next_day(tmp_path):
    import json
    import time

    set_auto_flag(tmp_path, "ojol", False)
    set_auto_flag(tmp_path, "kerja", True)

    calls = []

    class FakeUi:
        async def kantor_action(self, action, **fields):
            calls.append(action)
            if action == "detak":
                return {
                    "kantor": {
                        "buka": True,
                        "libur": False,
                        "sekarang": "2026-11-25T05:00:00.000Z",
                        "kerja": {"status": "tercapai", "poin": 30, "target": 30},
                        "paket": {"berbayar": True, "lunas": 3, "perHari": 3, "menuju": 0, "perPaket": 5},
                        "bersama": [{"id": "b1", "dari": 0, "sampai": 1440, "ikut": False}],
                        "kejadian": [{"idx": 0, "dari": 0, "sampai": 1440, "oleh": None}],
                        "urusan": None,
                    }
                }
            raise AssertionError(f"Should not call {action} when already max")

    c = SimpleNamespace(
        ui=FakeUi(),
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(),
        record_event=lambda kind, msg: None,
    )

    assert await run_kerja(c) is False
    assert calls == ["detak"]
    assert auto_flags(tmp_path)["kerja"] is True
    assert c.kerja_retry_at > time.monotonic() + 3600

    # Even if retry_at is cleared (e.g. worker restart) on the same day, detak is not called again
    c.kerja_retry_at = 0
    saved = json.loads((tmp_path / "kerja-status.json").read_text())
    saved["completed_date"] = datetime.now().astimezone().date().isoformat()
    (tmp_path / "kerja-status.json").write_text(json.dumps(saved))
    assert await run_kerja(c) is False
    assert calls == ["detak"]

    # Next day (completed_date is yesterday) -> resumes calling detak
    c.kerja_retry_at = 0
    saved["completed_date"] = "2020-01-01"
    (tmp_path / "kerja-status.json").write_text(json.dumps(saved))
    assert await run_kerja(c) is False
    assert calls == ["detak", "detak"]


def test_seconds_until_next_open_respects_jam_kerja():
    from app.modules.gameplay.kerja import _seconds_until_next_open

    jam = {"from": "08:00", "to": "16:00", "istirahat": {"from": "11:30", "to": "12:30"}}

    # 06:30 WIB (23:30 UTC prev day) -> 1.5h until 08:00 WIB
    assert _seconds_until_next_open(jam, "2026-11-24T23:30:00.000Z") == pytest.approx(5400.0)

    # 12:00 WIB (05:00 UTC) during break -> 30m until 12:30 WIB
    assert _seconds_until_next_open(jam, "2026-11-25T05:00:00.000Z") == pytest.approx(1800.0)

    # 17:00 WIB (10:00 UTC) after close -> 15h until 08:00 WIB tomorrow
    assert _seconds_until_next_open(jam, "2026-11-25T10:00:00.000Z") == pytest.approx(54000.0)

    # 12:00 WIB (05:00 UTC) with force_tomorrow -> 20h until 08:00 WIB tomorrow (not midnight)
    assert _seconds_until_next_open(
        jam, "2026-11-25T05:00:00.000Z", force_tomorrow=True
    ) == pytest.approx(72000.0)


@pytest.mark.asyncio
async def test_controller_record_event_with_run_kerja(tmp_path):
    import json

    from app.modules.worker.controller import Controller

    set_auto_flag(tmp_path, "ojol", False)
    set_auto_flag(tmp_path, "kerja", True)

    recorded = []

    class FakeJournal:
        def event(self, run_id, name, data):
            recorded.append((run_id, name, data))

        def profit(self, run_id=None):
            return "0"

    class FakeUi:
        async def kantor_action(self, action, **fields):
            assert action == "detak"
            return {
                "kantor": {
                    "nama": "Puskesmas",
                    "buka": True,
                    "libur": False,
                    "sekarang": "2026-11-25T02:00:00.000Z",
                    "jam": {"from": "08:00", "to": "16:00"},
                    "saya": {"profesi": "Dokter"},
                    "kerja": {"poin": 30, "target": 30, "status": "tercapai"},
                    "kegiatan": [],
                    "kejadian": None,
                    "urusan": {"tersedia": False},
                }
            }

    c = Controller(
        ui=FakeUi(),
        settings=SimpleNamespace(runtime_dir=tmp_path, max_minutes=None),
        journal=FakeJournal(),
        run_id="run-1",
    )
    c.state = _snapshot()
    c.stage = "study.preview.kuliah"

    assert await run_kerja(c) is False
    assert c.stage == "kerja.kantor"
    assert recorded and recorded[0][1] == "kerja"
    assert "Target kantor hari ini maksimal" in recorded[0][2]["message"]
    notices = list((tmp_path / "notifications").glob("*.json"))
    assert len(notices) == 1
    assert "Target kantor hari ini maksimal" in json.loads(notices[0].read_text())["text"]


@pytest.mark.asyncio
async def test_run_kerja_auto_sesi_absen_after_urusan_and_from_detak(tmp_path, monkeypatch):
    set_auto_flag(tmp_path, "ojol", False)
    set_auto_flag(tmp_path, "kerja", True)

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr("app.modules.gameplay.kerja.asyncio.sleep", fast_sleep)

    calls = []
    events = []

    class FakeUiAfterUrusan:
        async def kantor_action(self, action, **fields):
            calls.append(action)
            if action == "detak":
                return {
                    "kantor": {
                        "nama": "Bank desa",
                        "buka": True,
                        "libur": False,
                        "sekarang": "2026-11-26T02:00:00.000Z",
                        "jam": {"from": "08:00", "to": "16:00"},
                        "kerja": {"poin": 0, "target": 30, "status": "penuh"},
                        "paket": {"berbayar": False},
                        "sesi": {
                            "ke": 1,
                            "jumlah": 6,
                            "urusan": 3,
                            "absen": True,
                            "absenSetelah": 1,
                            "jadwal": [{"ke": 1, "u": 0, "absen": False, "beres": False}],
                        },
                        "kegiatan": [],
                        "kejadian": None,
                        "urusan": None,
                    }
                }
            if action == "urusan-mulai":
                return {
                    "id": "u-sesi-1",
                    "mulai": "2026-11-26T02:00:00.000Z",
                    "langkah": [{"aksi": "proses", "detik": 0}],
                }
            if action == "urusan-selesai":
                return {
                    "ok": True,
                    "poin": 2,
                    "sesi": {"ke": 1, "u": 1, "absen": False, "beres": False, "baru": False},
                }
            if action == "sesi-absen":
                return {
                    "sesi": {"ke": 1, "u": 1, "absen": True, "beres": False, "baru": False}
                }
            raise AssertionError(f"Unexpected action: {action}")

    c = SimpleNamespace(
        ui=FakeUiAfterUrusan(),
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(),
        record_event=lambda kind, msg: events.append((kind, msg)),
    )
    assert await run_kerja(c) is True
    assert calls == ["detak", "urusan-mulai", "urusan-selesai", "sesi-absen"]
    assert any("Absen sesi 1 tercatat" in msg for _, msg in events)

    # Also test when detak already shows u >= absenSetelah and absen=False -> calls sesi-absen directly
    detak_calls = []

    class FakeUiFromDetak:
        async def kantor_action(self, action, **fields):
            detak_calls.append(action)
            if action == "detak":
                return {
                    "kantor": {
                        "nama": "Bank desa",
                        "buka": True,
                        "libur": False,
                        "sekarang": "2026-11-26T02:05:00.000Z",
                        "jam": {"from": "08:00", "to": "16:00"},
                        "kerja": {"poin": 6, "target": 30, "status": "penuh"},
                        "paket": {"berbayar": False},
                        "sesi": {
                            "ke": 1,
                            "jumlah": 6,
                            "urusan": 3,
                            "absen": True,
                            "absenSetelah": 1,
                            "jadwal": [{"ke": 1, "u": 3, "absen": False, "beres": False}],
                        },
                        "kegiatan": [],
                        "kejadian": None,
                        "urusan": None,
                    }
                }
            if action == "sesi-absen":
                return {
                    "sesi": {
                        "ke": 1,
                        "u": 3,
                        "absen": True,
                        "beres": True,
                        "baru": True,
                        "jumlahBeres": 1,
                        "bonusMilli": 2200,
                    }
                }
            raise AssertionError(f"Should not call {action}")

    events2 = []
    c2 = SimpleNamespace(
        ui=FakeUiFromDetak(),
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(),
        record_event=lambda kind, msg: events2.append((kind, msg)),
    )
    assert await run_kerja(c2) is True
    assert detak_calls == ["detak", "sesi-absen"]
    assert any("Sesi 1 beres! (1/6 sesi)" in msg for _, msg in events2)


@pytest.mark.asyncio
async def test_run_kerja_custom_target_poin_and_sesi_status_fields(tmp_path, monkeypatch):
    import json

    from app.modules.gameplay.kerja import set_kerja_target_poin

    set_auto_flag(tmp_path, "ojol", False)
    set_auto_flag(tmp_path, "kerja", True)
    set_kerja_target_poin(tmp_path, 45)

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr("app.modules.gameplay.kerja.asyncio.sleep", fast_sleep)

    calls = []

    class FakeUi:
        async def kantor_action(self, action, **fields):
            calls.append(action)
            if action == "detak":
                return {
                    "kantor": {
                        "nama": "Bank desa",
                        "buka": True,
                        "libur": False,
                        "sekarang": "2026-11-26T02:00:00.000Z",
                        "jam": {"from": "08:00", "to": "16:00"},
                        "kerja": {"poin": 30, "target": 30, "status": "tercapai"},
                        "paket": {"berbayar": True, "perHari": 3, "lunas": 3},
                        "sesi": {
                            "ke": 6,
                            "jumlah": 6,
                            "urusan": 3,
                            "absen": True,
                            "absenSetelah": 1,
                            "beres": 5,
                            "jadwal": [
                                *({"ke": i, "u": 3, "absen": True, "beres": True} for i in range(1, 6)),
                                {"ke": 6, "u": 2, "absen": False, "beres": False},
                            ],
                        },
                        "kegiatan": [],
                        "kejadian": None,
                        "urusan": None,
                    }
                }
            if action == "sesi-absen":
                return {
                    "sesi": {
                        "ke": 6,
                        "u": 2,
                        "absen": True,
                        "beres": False,
                        "baru": False,
                    }
                }
            raise AssertionError(f"Unexpected action: {action}")

    c = SimpleNamespace(
        ui=FakeUi(),
        settings=SimpleNamespace(runtime_dir=tmp_path),
        observed_state=_snapshot(),
        record_event=lambda kind, msg: None,
    )
    # Even though server status is "tercapai" at 30/30, custom target is 45 and session 6 needs absen
    assert await run_kerja(c) is True
    assert calls == ["detak", "sesi-absen"]
    saved = json.loads((tmp_path / "kerja-status.json").read_text())
    assert saved["sesi_absen"] == 6
    assert saved["sesi_jumlah"] == 6
    assert saved["target"] == 45
    assert saved["poin"] == 30
    assert saved["state"] == "Aktif"
