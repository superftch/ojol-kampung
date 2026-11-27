from app.modules.jobs.service import build_job_vacancies_payload


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
            "rateMilliDay": 3000,
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

    # Current job marker
    teller = next(v for v in vacancies if v["profession"] == "Teller bank")
    assert teller["is_current_job"] is True
    assert teller["can_apply"] is False
