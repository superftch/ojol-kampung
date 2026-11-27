from typing import Any
from unittest.mock import AsyncMock

from starlette.testclient import TestClient

from app.integrations.kampung.http_api import OjolHttpApi
from app.main import create_app
from app.modules.worker.fleet import MultiAccountService


def _setup_authenticated_client(settings):
    manager = MultiAccountService(settings)
    admin = manager.registry.web.register("web_admin", "admin-password")
    token = manager.registry.web.issue_session(admin["id"])
    owner = manager.registry.owner_for_user(admin)
    acc = manager.registry.create(owner, "Akun Test")
    manager.registry.select(owner, acc["id"])
    manager.start = AsyncMock()
    manager.close = AsyncMock()
    app = create_app(settings, service=manager)
    return app, token


def test_jobs_web_routes_and_dashboard_tab(settings, monkeypatch):
    sample_me = {
        "balanceMilli": 5000,
        "home": {"plotId": "K40-R04", "desa": "desa-utara", "desaName": "Desa Utara"},
        "ekonomi": {"bonusBps": 10000, "remBps": 0},
        "skill": {
            "level": 0,
            "bonusBps": 0,
            "tracks": [
                {
                    "id": "kesehatan",
                    "name": "Kesehatan",
                    "icon": "🩺",
                    "level": 3,
                    "bonusBps": 4500,
                    "professions": ["Dokter"],
                }
            ],
        },
        "job": None,
        "catalog": {
            "contractDays": 7,
            "vacancies": [
                {
                    "facilityId": "fac-rs",
                    "facility": "Rumah Sakit",
                    "item": "rs",
                    "profession": "Dokter",
                    "slots": 2,
                    "filled": 0,
                    "wageMilliDay": 5000,
                    "minSkillLevel": 2,
                    "feeMilli": 0,
                    "bumdes": False,
                    "desa": "desa-utara",
                    "desaName": "Desa Utara",
                }
            ],
            "bizVacancies": [],
        },
    }

    async def fake_aenter(self):
        return self

    async def fake_aexit(self, *args):
        return None

    monkeypatch.setattr(OjolHttpApi, "__aenter__", fake_aenter)
    monkeypatch.setattr(OjolHttpApi, "__aexit__", fake_aexit)
    monkeypatch.setattr(OjolHttpApi, "fetch_game_me", AsyncMock(return_value=sample_me))
    monkeypatch.setattr(
        OjolHttpApi,
        "fetch_biz_vacancies",
        AsyncMock(
            return_value=[
                {
                    "id": "biz-1",
                    "businessId": "b-1",
                    "name": "Warung Kopi",
                    "profession": "Penjaga warung",
                    "slots": 1,
                    "hired": 0,
                    "rate": 2500,
                    "days": 7,
                    "desa": "desa-utara",
                    "desaName": "Desa Utara",
                    "block": "A01",
                }
            ]
        ),
    )
    apply_fac_mock = AsyncMock(return_value={"ok": True})
    apply_biz_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(OjolHttpApi, "apply_facility_job", apply_fac_mock)
    monkeypatch.setattr(OjolHttpApi, "apply_biz_vacancy", apply_biz_mock)

    app, token = _setup_authenticated_client(settings)
    with TestClient(app, base_url="http://localhost:6080") as client:
        client.cookies.set("ojol_web_session", token)

        # Dashboard HTML has Lowongan Pekerjaan tab and Job Sniper panel
        dash = client.get("/")
        assert dash.status_code == 200
        assert "tab-jobs" in dash.text
        assert "Lowongan Pekerjaan" in dash.text
        assert "Job Sniper" in dash.text

        # GET vacancies (first call fetches live, second call uses cache, ?refresh=1 bypasses cache)
        fetch_me_mock: Any = OjolHttpApi.fetch_game_me
        res = client.get("/api/jobs/vacancies")
        assert res.status_code == 200
        data = res.json()
        assert data["cached"] is False
        assert data["summary"]["total_count"] == 2
        assert data["vacancies"][0]["profession"] == "Dokter"
        assert data["vacancies"][0]["salary"]["net_milli"] == 14500
        assert fetch_me_mock.await_count == 1

        res_cached = client.get("/api/jobs/vacancies")
        assert res_cached.status_code == 200
        assert res_cached.json()["cached"] is True
        assert fetch_me_mock.await_count == 1

        res_refresh = client.get("/api/jobs/vacancies?refresh=1")
        assert res_refresh.status_code == 200
        assert res_refresh.json()["cached"] is False
        assert fetch_me_mock.await_count == 2

        # Apply facility job
        apply_res = client.post(
            "/api/jobs/apply",
            json={
                "kind": "facility",
                "profession": "Dokter",
                "facility_id": "fac-rs",
                "switch_job": False,
            },
        )
        assert apply_res.status_code == 200
        assert apply_res.json()["success"] is True
        apply_fac_mock.assert_awaited_once_with("Dokter", "fac-rs", switch_job=False)

        # Apply business job with switch_job=True
        apply_biz_res = client.post(
            "/api/jobs/apply",
            json={
                "kind": "business",
                "profession": "Penjaga warung",
                "vacancy_id": "biz-1",
                "switch_job": True,
            },
        )
        assert apply_biz_res.status_code == 200
        assert apply_biz_res.json()["success"] is True
        apply_biz_mock.assert_awaited_once_with("biz-1", switch_job=True)

        # GET & POST Job Sniper config
        sniper_get = client.get("/api/jobs/sniper")
        assert sniper_get.status_code == 200
        assert sniper_get.json()["config"]["enabled"] is False

        # Reject when min_salary_milli has no matching vacancy
        sniper_reject = client.post(
            "/api/jobs/sniper",
            json={
                "enabled": True,
                "target_mode": "highest",
                "min_salary_milli": 999999,
            },
        )
        assert sniper_reject.status_code == 400

        # When an open eligible vacancy exists, activating sniper immediately snipes it
        apply_fac_mock.reset_mock()
        sniper_immediate = client.post(
            "/api/jobs/sniper",
            json={
                "enabled": True,
                "target_mode": "highest",
                "min_salary_milli": 5000,
            },
        )
        assert sniper_immediate.status_code == 200
        imm_data = sniper_immediate.json()
        assert imm_data["sniped"] is True
        assert imm_data["config"]["enabled"] is False
        apply_fac_mock.assert_awaited_once_with("Dokter", "fac-rs", switch_job=False)

        # When best matching vacancy is full with kosongAt, sniper activates and returns target_preview
        sample_me["catalog"]["vacancies"][0]["filled"] = 2
        sample_me["catalog"]["vacancies"][0]["kosongAt"] = "2026-12-03T03:27:00.000Z"
        client.get("/api/jobs/vacancies?refresh=1")
        sniper_wait = client.post(
            "/api/jobs/sniper",
            json={
                "enabled": True,
                "target_mode": "highest",
                "min_salary_milli": 10000,
            },
        )
        assert sniper_wait.status_code == 200
        wait_data = sniper_wait.json()
        assert wait_data["sniped"] is False
        assert wait_data["config"]["enabled"] is True
        assert wait_data["target_preview"]["profession"] == "Dokter"
        assert wait_data["target_preview"]["kosong_at"] == "2026-12-03T03:27:00.000Z"
