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

        # GET vacancies
        res = client.get("/api/jobs/vacancies")
        assert res.status_code == 200
        data = res.json()
        assert data["summary"]["total_count"] == 2
        assert data["vacancies"][0]["profession"] == "Dokter"
        assert data["vacancies"][0]["salary"]["net_milli"] == 14500

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

        sniper_post = client.post(
            "/api/jobs/sniper",
            json={
                "enabled": True,
                "interval_seconds": 15,
                "schedule_enabled": True,
                "start_time": "06:00",
                "end_time": "22:00",
                "source_filter": "facility",
                "skill_track_id": "kesehatan",
                "min_salary_milli": 5000,
                "allow_switch_job": True,
                "allow_fee": False,
                "auto_stop_on_success": True,
            },
        )
        assert sniper_post.status_code == 200
        assert sniper_post.json()["config"]["enabled"] is True
        assert sniper_post.json()["config"]["interval_seconds"] == 15

        # Trigger immediate sniper run
        apply_fac_mock.reset_mock()
        sniper_run = client.post("/api/jobs/sniper/run")
        assert sniper_run.status_code == 200
        run_data = sniper_run.json()
        assert run_data["sniped"] is True
        assert run_data["config"]["enabled"] is False
        apply_fac_mock.assert_awaited_once_with("Dokter", "fac-rs", switch_job=False)
