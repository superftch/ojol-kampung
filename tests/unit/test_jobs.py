from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.modules.jobs.service import build_job_vacancies_payload
from app.modules.jobs.sniper import (
    is_within_schedule,
    load_sniper_config,
    pick_best_sniper_candidate,
    run_job_sniper_once,
    save_sniper_config,
)


def _sample_me() -> dict:
    return {
        "balanceMilli": 10000,
        "home": {"plotId": "K40-R04", "desa": "desa-utara", "desaName": "Desa Utara"},
        "profile": {"nickname": "tester", "age": 25, "gender": "laki-laki"},
        "ekonomi": {"bonusBps": 10000, "remBps": 2000},
        "skill": {
            "level": 0,
            "bonusBps": 0,
            "tracks": [
                {
                    "id": "kesehatan",
                    "name": "Kesehatan",
                    "icon": "🩺",
                    "level": 5,
                    "bonusBps": 7500,
                    "professions": ["Dokter", "Perawat"],
                },
                {
                    "id": "administrasi",
                    "name": "Administrasi",
                    "icon": "🗂",
                    "level": 1,
                    "bonusBps": 1000,
                    "professions": ["Kepala wilayah bank", "Teller bank"],
                },
            ],
        },
        "job": {
            "employerId": "fac-current",
            "profession": "Teller bank",
            "facility": "Bank Desa",
            "employerType": "PUBLIC",
            "rateMilliDay": 3300,
            "ekonomiBps": 10000,
        },
        "catalog": {
            "contractDays": 7,
            "transport": {"jenis": "koin_per_hari", "nilai": 0.2},
            "vacancies": [
                {
                    "facilityId": "fac-rs",
                    "facility": "Rumah Sakit",
                    "item": "rs",
                    "profession": "Dokter",
                    "slots": 2,
                    "filled": 1,
                    "wageMilliDay": 5000,
                    "minSkillLevel": 3,
                    "feeMilli": 0,
                    "bumdes": False,
                    "desa": "desa-utara",
                    "desaName": "Desa Utara",
                },
                {
                    "facilityId": "fac-bank",
                    "facility": "Bank Desa",
                    "item": "bank",
                    "profession": "Kepala wilayah bank",
                    "slots": 1,
                    "filled": 1,
                    "kosongAt": "2026-11-28T07:00:00.000Z",
                    "wageMilliDay": 10000,
                    "minSkillLevel": 5,
                    "feeMilli": 0,
                    "bumdes": True,
                    "desa": "kampung-sebelah",
                    "desaName": "Kampung Sebelah",
                },
                {
                    "facilityId": "fac-current",
                    "facility": "Bank Desa",
                    "item": "bank",
                    "profession": "Teller bank",
                    "slots": 3,
                    "filled": 1,
                    "wageMilliDay": 3000,
                    "minSkillLevel": 1,
                    "feeMilli": 0,
                    "bumdes": False,
                    "desa": "desa-utara",
                    "desaName": "Desa Utara",
                },
            ],
            "bizVacancies": [],
        },
    }


def test_build_job_vacancies_sorts_by_highest_salary_and_computes_multipliers():
    me = _sample_me()
    biz_items = [
        {
            "id": "biz-1",
            "businessId": "b-1",
            "name": "Warung Maju",
            "ownerNick": "budi",
            "profession": "Penjaga warung",
            "slots": 2,
            "hired": 0,
            "rate": 4000,
            "days": 5,
            "desa": "kampung-sebelah",
            "desaName": "Kampung Sebelah",
            "block": "B10",
        }
    ]
    payload = build_job_vacancies_payload(me, biz_items=biz_items)

    assert payload["summary"]["total_count"] == 4
    assert payload["summary"]["available_count"] == 3
    assert payload["summary"]["skill_match_count"] == 3
    assert payload["summary"]["biz_count"] == 1

    vacancies = payload["vacancies"]
    # Verify sorted descending by net_milli
    nets = [v["salary"]["net_milli"] for v in vacancies]
    assert nets == sorted(nets, reverse=True)

    # Kepala wilayah bank: base 10000, skill +10% -> 11000, cross-desa -200 -> 10800, ekonomi +100% -> 21600
    bank_head = next(v for v in vacancies if v["profession"] == "Kepala wilayah bank")
    assert bank_head["salary"]["base_milli"] == 10000
    assert bank_head["salary"]["skill_bonus_bps"] == 1000
    assert bank_head["salary"]["skill_bonus_milli"] == 1000
    assert bank_head["salary"]["transport_deduct_milli"] == 200
    assert bank_head["salary"]["ekonomi_bonus_bps"] == 10000
    assert bank_head["salary"]["ekonomi_bonus_milli"] == 10800
    assert bank_head["salary"]["net_milli"] == 21600
    assert bank_head["is_full"] is True
    assert bank_head["skill_met"] is False
    assert bank_head["skill_gap"] == 4
    assert bank_head["can_apply"] is False

    # Dokter: base 5000, skill +75% -> 8750, same desa -> 0 transport, ekonomi +100% -> 17500
    dokter = next(v for v in vacancies if v["profession"] == "Dokter")
    assert dokter["salary"]["net_milli"] == 17500
    assert dokter["is_full"] is False
    assert dokter["skill_met"] is True
    assert dokter["can_apply"] is True

    # Business vacancy: base 4000, cross-desa -200 -> 3800, ekonomi +100% (3800) + subsidi +20% (760) = 8360
    warung = next(v for v in vacancies if v["kind"] == "business")
    assert warung["salary"]["net_milli"] == 8360
    assert warung["salary"]["subsidi_milli"] == 760
    assert warung["can_apply"] is True

    # Current job marker & salary comparison
    teller = next(v for v in vacancies if v["profession"] == "Teller bank")
    assert teller["is_current_job"] is True
    assert teller["can_apply"] is False
    # Current job: rate 3300 + ekonomi 100% (3300) = 6600
    assert payload["current_job"]["net_milli"] == 6600
    assert teller["salary"]["comparison"]["diff_milli"] == 0
    assert teller["salary"]["comparison"]["diff_pct"] == 0.0
    # Dokter: 17500 vs 6600 -> +10900 (+165.2%)
    assert dokter["salary"]["comparison"]["diff_milli"] == 10900
    assert dokter["salary"]["comparison"]["diff_pct"] == 165.2


def test_sniper_schedule_windows_wib():
    wib = ZoneInfo("Asia/Jakarta")
    assert is_within_schedule({"schedule_enabled": False}, datetime(2026, 11, 27, 3, 0, tzinfo=wib))

    daytime = {"schedule_enabled": True, "start_time": "08:00", "end_time": "17:00"}
    assert is_within_schedule(daytime, datetime(2026, 11, 27, 8, 0, tzinfo=wib)) is True
    assert is_within_schedule(daytime, datetime(2026, 11, 27, 16, 59, tzinfo=wib)) is True
    assert is_within_schedule(daytime, datetime(2026, 11, 27, 17, 0, tzinfo=wib)) is False
    assert is_within_schedule(daytime, datetime(2026, 11, 27, 7, 59, tzinfo=wib)) is False

    overnight = {"schedule_enabled": True, "start_time": "22:00", "end_time": "06:00"}
    assert is_within_schedule(overnight, datetime(2026, 11, 27, 23, 30, tzinfo=wib)) is True
    assert is_within_schedule(overnight, datetime(2026, 11, 27, 5, 59, tzinfo=wib)) is True
    assert is_within_schedule(overnight, datetime(2026, 11, 27, 12, 0, tzinfo=wib)) is False


def test_pick_best_sniper_candidate_respects_skill_salary_and_kosong_at():
    me = _sample_me()
    # Add a lower-paying eligible job to verify highest-paying eligible is picked
    me["catalog"]["vacancies"].append(
        {
            "facilityId": "fac-puskesmas",
            "facility": "Puskesmas",
            "item": "puskesmas",
            "profession": "Perawat",
            "slots": 3,
            "filled": 0,
            "wageMilliDay": 3000,
            "minSkillLevel": 1,
            "feeMilli": 0,
            "bumdes": False,
            "desa": "desa-utara",
            "desaName": "Desa Utara",
        }
    )
    # Add a skill-met full vacancy with kosongAt
    me["catalog"]["vacancies"].append(
        {
            "facilityId": "fac-rs-vip",
            "facility": "RS Provinsi",
            "item": "rs",
            "profession": "Dokter",
            "slots": 1,
            "filled": 1,
            "kosongAt": "2026-11-28T05:00:00.000Z",
            "wageMilliDay": 9000,
            "minSkillLevel": 5,
            "feeMilli": 0,
            "bumdes": True,
            "desa": "desa-utara",
            "desaName": "Desa Utara",
        }
    )
    payload = build_job_vacancies_payload(me, biz_items=[])

    # Default config: picks Dokter (17500) over Perawat (10500), skips Kepala wilayah bank (skill_met=False)
    best, next_kosong = pick_best_sniper_candidate(
        payload,
        {"source_filter": "all", "allow_switch_job": True, "allow_fee": False, "min_salary_milli": 0},
    )
    assert best is not None
    assert best["profession"] == "Dokter"
    assert best["salary"]["net_milli"] == 17500
    assert next_kosong is not None
    assert next_kosong["facility_id"] == "fac-rs-vip"

    # When allow_switch_job=False and account already has a job, nothing is eligible
    best_no_switch, _ = pick_best_sniper_candidate(
        payload,
        {"source_filter": "all", "allow_switch_job": False, "allow_fee": False, "min_salary_milli": 0},
    )
    assert best_no_switch is None

    # When min_salary_milli is higher than Dokter (17500), nothing is eligible
    best_high_min, _ = pick_best_sniper_candidate(
        payload,
        {"source_filter": "all", "allow_switch_job": True, "allow_fee": False, "min_salary_milli": 20000},
    )
    assert best_high_min is None


async def test_run_job_sniper_once_applies_and_autostops(tmp_path):
    me = _sample_me()
    save_sniper_config(
        tmp_path,
        {
            "enabled": True,
            "interval_seconds": 30,
            "auto_stop_on_success": True,
            "allow_switch_job": True,
        },
    )
    fake_api = SimpleNamespace(
        fetch_game_me=AsyncMock(return_value=me),
        fetch_biz_vacancies=AsyncMock(return_value=[]),
        apply_facility_job=AsyncMock(return_value={"ok": True}),
        apply_biz_vacancy=AsyncMock(return_value={"ok": True}),
    )

    res = await run_job_sniper_once(tmp_path, api=fake_api)
    assert res["checked"] is True
    assert res["sniped"] is True
    assert res["job"]["profession"] == "Dokter"
    fake_api.apply_facility_job.assert_awaited_once_with("Dokter", "fac-rs", switch_job=True)
    # Auto-stopped after success
    assert load_sniper_config(tmp_path)["enabled"] is False
    assert res["state"]["snipes_count"] == 1
    assert res["state"]["last_sniped_job"]["profession"] == "Dokter"


async def test_run_job_sniper_wait_kosong_sleeps_until_kosong_at(tmp_path):
    me = _sample_me()
    # Make all skill-matched open vacancies full with a future kosongAt
    for v in me["catalog"]["vacancies"]:
        if v["profession"] == "Dokter":
            v["filled"] = v["slots"]
            v["kosongAt"] = "2026-12-03T03:27:00.000Z"
    save_sniper_config(
        tmp_path,
        {
            "enabled": True,
            "mode": "wait_kosong",
            "interval_seconds": 30,
            "allow_switch_job": True,
        },
    )
    fake_api = SimpleNamespace(
        fetch_game_me=AsyncMock(return_value=me),
        fetch_biz_vacancies=AsyncMock(return_value=[]),
        apply_facility_job=AsyncMock(),
        apply_biz_vacancy=AsyncMock(),
    )

    res = await run_job_sniper_once(tmp_path, api=fake_api)
    assert res["checked"] is True
    assert res["sniped"] is False
    assert res["next_kosong_epoch"] == datetime.fromisoformat("2026-12-03T03:27:00+00:00").timestamp()
    assert res["next_check_epoch"] == res["next_kosong_epoch"]
    assert res["state"]["next_check_at"] is not None
    fake_api.apply_facility_job.assert_not_awaited()
