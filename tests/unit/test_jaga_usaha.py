from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import HttpCoreError
from app.modules.gameplay import jaga_usaha
from app.modules.gameplay.jaga_usaha import JagaWorker
from app.modules.worker.jaga_planner import plan_businesses, read_business
from app.modules.worker.jaga_settings import BusinessOverride, JagaSettings, save_jaga_settings
from app.modules.worker.settings import auto_flags, set_auto_flag

FIRST = "00000000-0000-4000-8000-000000000001"
SECOND = "00000000-0000-4000-8000-000000000002"


@pytest.fixture
def game(settings, state, monkeypatch):
    clock = SimpleNamespace(at=datetime(2026, 11, 28, 8, tzinfo=UTC))
    monkeypatch.setattr(jaga_usaha, "now", lambda: clock.at)
    directory = settings.runtime_dir
    set_auto_flag(directory, "jaga", True)
    set_auto_flag(directory, "ojol", False)
    save_jaga_settings(directory, JagaSettings(target_min=3, target_max=3))
    remote = SimpleNamespace(active=False, minutes=0)
    calls = []

    async def status(_key):
        return {
            "jaga": remote.active,
            "menit": remote.minutes,
            "maksMenit": 240,
            "detakDetik": 60,
            "open": True,
        }

    async def action(key, action):
        calls.append((key, action))
        if action == "selesai":
            remote.active = False
            return {}
        remote.active = True
        remote.minutes += 1
        return await status(key)

    ui = SimpleNamespace(
        businesses_semua=AsyncMock(return_value={"usaha": [{"id": FIRST, "plang": "Kedai"}]}),
        shop_info=AsyncMock(return_value={"mine": True, "open": True, "customersYesterday": 251}),
        business_report=AsyncMock(return_value={"today": {"rivals": 3}, "week": {"netMilli": 10}}),
        jaga_status=AsyncMock(side_effect=status),
        jaga_action=AsyncMock(side_effect=action),
    )
    controller = SimpleNamespace(
        settings=settings,
        observed_state=state,
        ui=ui,
        journal=Mock(),
        run_id=1,
        check_cancel=Mock(),
        read_snapshot=AsyncMock(),
        wait=AsyncMock(),
    )
    worker = JagaWorker(directory)
    return SimpleNamespace(
        clock=clock,
        controller=controller,
        worker=worker,
        directory=directory,
        calls=calls,
        remote=remote,
        flags=lambda: auto_flags(directory),
    )


async def start(game):
    await game.worker.start_step(game.controller, game.flags())
    await game.worker.start_step(game.controller, game.flags())


async def test_jaga_server_minutes_and_interval(game):
    await start(game)
    assert game.calls == [(FIRST, "mulai")]
    game.clock.at += timedelta(seconds=59)
    await game.worker.observe(game.controller, game.flags())
    assert game.calls == [(FIRST, "mulai")]
    game.clock.at += timedelta(seconds=1)
    await game.worker.observe(game.controller, game.flags())
    game.clock.at += timedelta(seconds=60)
    await game.worker.observe(game.controller, game.flags())
    assert game.calls == [(FIRST, "mulai"), (FIRST, "detak"), (FIRST, "detak"), (FIRST, "selesai")]
    assert game.worker.data.session is None
    assert game.worker.data.used_seconds == 120
    assert game.worker.data.businesses[0].minutes == 3
    assert game.controller.journal.event.call_args.args[2]["server_minutes_end"] == 3


async def test_jaga_restart_resumes_only_confirmed_active_session(game):
    await start(game)
    game.clock.at += timedelta(seconds=30)
    game.worker = JagaWorker(game.directory)
    await game.worker.observe(game.controller, game.flags())
    assert game.calls == [(FIRST, "mulai")]
    game.clock.at += timedelta(seconds=30)
    await game.worker.observe(game.controller, game.flags())
    assert game.calls[-1] == (FIRST, "detak")


async def test_jaga_uncertain_start_does_not_claim_remote_session(game):
    async def uncertain(_key, action):
        assert action == "mulai"
        game.remote.active = True
        raise HttpCoreError("Jaringan terputus", category="uncertain")

    game.controller.ui.jaga_action.side_effect = uncertain
    await start(game)
    game.worker = JagaWorker(game.directory)
    assert await game.worker.observe(game.controller, game.flags())
    assert game.worker.data.state == "Rekonsiliasi"
    assert game.controller.ui.jaga_action.await_count == 1
    game.remote.active = False
    await game.worker.observe(game.controller, game.flags())
    assert game.worker.data.session is None


async def test_jaga_uncertain_close_waits_for_confirmation_without_duplicate_post(game):
    await start(game)
    game.controller.ui.jaga_action.side_effect = HttpCoreError("Timeout", category="uncertain")
    set_auto_flag(game.directory, "ojol", True)
    assert await game.worker.before_waits(game.controller, game.flags(), maintenance=False)
    assert await game.worker.before_waits(game.controller, game.flags(), maintenance=False)
    assert game.controller.ui.jaga_action.await_count == 2
    assert game.worker.data.state == "Rekonsiliasi"
    game.remote.active = False
    assert not await game.worker.before_waits(game.controller, game.flags(), maintenance=False)
    assert game.worker.data.session is None


async def test_jaga_verification_pauses_activity_until_reset(game):
    game.controller.ui.jaga_action.side_effect = HttpCoreError(
        "Verifikasi", category="verification"
    )
    await start(game)
    await game.worker.observe(game.controller, game.flags())
    assert game.worker.data.session is None
    assert game.worker.data.verification
    game.clock.at += timedelta(hours=1)
    await start(game)
    assert game.controller.ui.jaga_action.await_count == 1
    set_auto_flag(game.directory, "jaga", False)
    await game.worker.before_waits(game.controller, game.flags(), maintenance=False)
    assert not game.worker.data.verification


@pytest.mark.parametrize(
    "guard", ["ojol", "off", "sleep", "need", "maintenance", "budget", "midnight"]
)
async def test_jaga_guards_close_an_active_session(game, guard):
    if guard == "budget":
        save_jaga_settings(game.directory, JagaSettings(budget_jam=0.01))
    if guard == "midnight":
        game.clock.at = datetime(2026, 11, 28, 16, 59, 40, tzinfo=UTC)
        save_jaga_settings(game.directory, JagaSettings(active_start="06:00", active_end="01:00"))
    await start(game)
    assert game.worker.data.session is not None
    if guard == "ojol":
        set_auto_flag(game.directory, "ojol", True)
    elif guard == "off":
        set_auto_flag(game.directory, "jaga", False)
    elif guard == "sleep":
        game.controller.observed_state.phase = "sleeping"
    elif guard == "need":
        game.controller.observed_state.needs["makan"] = 1
    elif guard in {"budget", "midnight"}:
        game.clock.at += timedelta(seconds=40)
    if guard in {"ojol", "off", "maintenance"}:
        await game.worker.before_waits(
            game.controller, game.flags(), maintenance=guard == "maintenance"
        )
    else:
        await game.worker.observe(game.controller, game.flags())
    assert game.calls == [(FIRST, "mulai"), (FIRST, "selesai")]


async def test_jaga_does_not_touch_endpoints_if_ojol_is_enabled(game):
    set_auto_flag(game.directory, "ojol", True)
    await start(game)
    game.controller.ui.businesses_semua.assert_not_awaited()


async def test_jaga_honors_server_ceiling_and_does_not_switch_in_manual_single_mode(game):
    save_jaga_settings(game.directory, JagaSettings(auto_pindah=False))
    game.remote.minutes = 1
    original_status = game.controller.ui.jaga_status.side_effect

    async def limited(key):
        return {**await original_status(key), "maksMenit": 1}

    game.controller.ui.jaga_status.side_effect = limited
    game.controller.ui.businesses_semua.return_value["usaha"].append({"id": SECOND})
    await start(game)
    await game.worker.start_step(game.controller, game.flags())
    await game.worker.start_step(game.controller, game.flags())
    assert game.calls == []
    assert game.worker.data.first_business == FIRST
    assert game.worker.data.businesses[0].minutes == 1


async def test_jaga_stop_attempt_records_unresolved_end_for_restart(game):
    await start(game)
    game.controller.ui.jaga_action.side_effect = HttpCoreError("Gagal", category="uncertain")
    await game.worker.shutdown(game.controller)
    recovered = JagaWorker(game.directory)
    assert recovered.data.session is not None
    assert recovered.data.session.phase == "closing"


def test_rank_uses_comparable_estimates_and_mode_specific_eligibility():
    first = read_business(
        {"id": FIRST},
        {"mine": True, "open": True, "customersYesterday": 251},
        {"today": {"rivals": 3}, "week": {"netMilli": -100_000}},
    )
    second = read_business(
        {"id": SECOND},
        {"mine": True, "open": True, "customersYesterday": 26},
        {},
    )
    day = datetime(2026, 11, 28).date()
    ranked = plan_businesses([second, first], JagaSettings(), day, {}, "test")
    assert ranked[0].id == FIRST
    assert ranked[0].score == pytest.approx(35.86, abs=0.01)
    assert ranked[1].reason == "Data pelanggan atau pesaing belum lengkap."
    manual = JagaSettings(
        mode="manual", override={SECOND: BusinessOverride(prioritas=10, maks_menit=25)}
    )
    ranked = plan_businesses([first, second], manual, day, {}, "test")
    assert ranked[0].id == SECOND and ranked[0].target == 25 and not ranked[0].reason
    assert ranked[1].reason == "Usaha tidak dipilih."


async def test_jaga_resets_previous_day_completion_and_budget(game):
    await start(game)
    game.remote.minutes = 3
    await game.worker.close(game.controller, "Target menit tercapai.")
    assert game.worker.data.businesses[0].minutes == 3
    game.clock.at += timedelta(days=1)
    game.remote.minutes = 0
    await start(game)
    assert game.worker.data.day.day == 29
    assert game.worker.data.used_seconds == 0
    assert game.calls[-1] == (FIRST, "mulai")


async def test_controller_stops_recorded_jaga_before_dispatching_other_work(game):
    from app.modules.worker.controller import Controller, StopRequested

    await start(game)
    controller = Controller(
        game.controller.ui,
        game.controller.settings,
        game.controller.journal,
        game.controller.run_id,
    )
    controller.state = game.controller.observed_state
    controller.wait_for_maintenance = AsyncMock(side_effect=StopRequested("test selesai"))
    controller.read_snapshot = AsyncMock()
    set_auto_flag(game.directory, "ojol", True)
    with pytest.raises(StopRequested):
        await controller.run()
    assert game.calls == [(FIRST, "mulai"), (FIRST, "selesai")]
    controller.read_snapshot.assert_not_awaited()


async def test_jaga_leaves_other_business_guarded_in_game_alone(game):
    game.controller.ui.businesses_semua.return_value["usaha"].append({"id": SECOND})
    original_shop = game.controller.ui.shop_info.return_value

    async def shop(key):
        return {**original_shop, "dijaga": key == SECOND}

    game.controller.ui.shop_info.side_effect = shop
    game.remote.active = True
    await start(game)
    await game.worker.start_step(game.controller, game.flags())
    assert game.calls == []
    assert game.worker.data.message == "Usaha sedang dijaga di game."
    game.controller.ui.jaga_status.assert_awaited_once_with(SECOND)


async def test_jaga_publishes_scan_progress_before_all_businesses_are_read(game):
    import json

    game.controller.ui.businesses_semua.return_value["usaha"].append(
        {"id": SECOND, "plang": "Usaha kedua"}
    )
    path = game.directory / "jaga-status.json"

    async def report(key):
        status = json.loads(path.read_text())
        assert status["message"] == "Membaca laporan usaha."
        assert status["scan"]["total"] == 2
        assert status["scan"]["checked"] == (0 if key == FIRST else 1)
        assert status["scan"]["business"] == ("Kedai" if key == FIRST else "Usaha kedua")
        return {"today": {"rivals": 3}}

    game.controller.ui.business_report.side_effect = report
    assert await game.worker.start_step(game.controller, game.flags())
    first = json.loads(path.read_text())
    assert first["state"] == "Menyusun rencana"
    assert first["scan"] == {"checked": 1, "total": 2, "business": None}
    assert first["updated_at"]
    assert await game.worker.start_step(game.controller, game.flags())
    done = json.loads(path.read_text())
    assert done["scan"] is None
    assert done["message"] == "2 dari 2 usaha layak dijaga."
    assert not game.calls


async def test_controller_uses_scan_pause_instead_of_normal_idle_poll(game):
    from app.modules.gameplay.jaga_usaha import SCAN_PAUSE_SECONDS
    from app.modules.worker.controller import Controller, StopRequested

    for key, enabled in game.flags().items():
        if enabled and key != "jaga":
            set_auto_flag(game.directory, key, False)
    game.controller.ui.businesses_semua.return_value["usaha"].append({"id": SECOND})
    controller = Controller(
        game.controller.ui,
        game.controller.settings,
        game.controller.journal,
        game.controller.run_id,
    )
    controller.state = game.controller.observed_state
    controller.read_snapshot = AsyncMock()
    controller.report = Mock()
    controller.wait = AsyncMock(side_effect=StopRequested("test selesai"))
    with pytest.raises(StopRequested):
        await controller.run()
    controller.wait.assert_awaited_once_with(SCAN_PAUSE_SECONDS)
    assert game.calls == []
