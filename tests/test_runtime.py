import asyncio
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ojol.cli import exclusive_lock, main, running
from ojol.config import load_settings
from ojol.controller import Controller, StopRequested
from ojol.healing import write_private
from ojol.http_api import HttpCoreError
from ojol.journal import Journal
from ojol.maintenance import MaintenanceWindow
from ojol.models import ROOT, Product


def test_environment_and_double_runner_block(settings):
    with pytest.raises(ValueError):
        load_settings()
    assert settings.runtime_dir.is_relative_to(ROOT / ".local/testing")
    assert not settings.operator_authorized
    with exclusive_lock(settings.runtime_dir):
        assert running(settings.runtime_dir)
        with pytest.raises(RuntimeError), exclusive_lock(settings.runtime_dir):
            pass
    assert not running(settings.runtime_dir)


def test_journal_write_before_click_blocks_unknown_replay(settings, state):
    journal = Journal(settings.runtime_dir)
    run = journal.start(settings)
    action = journal.begin(run, "purchase", state, {"product": "Isi pulsa"})
    with pytest.raises(RuntimeError, match="belum terverifikasi"):
        journal.start(settings)
    journal.settle(action, False)
    with pytest.raises(RuntimeError):
        journal.start(settings)
    journal.settle(action, True, state)
    assert journal.start(settings) > run
    journal.close()


async def test_purchase_verified_by_wallet_and_resource(settings, state, shop_preview):
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    after = state.model_copy(update={"wallet": state.wallet - Decimal("0.5"), "data": 86})
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop_preview([product])]),
        buy=AsyncMock(),
        snapshot=AsyncMock(return_value=after),
    )
    journal = Journal(settings.runtime_dir)
    controller = Controller(ui, settings, journal, journal.start(settings))
    await controller.purchase(state, "data")
    assert controller.spent == Decimal("0.5")
    assert journal.history()["actions"][0]["status"] == "verified"
    ui.buy.assert_awaited_once()
    journal.close()


async def test_timeout_does_not_repeat_purchase(settings, state, shop_preview):
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop_preview([product])]),
        buy=AsyncMock(side_effect=TimeoutError),
    )
    journal = Journal(settings.runtime_dir)
    controller = Controller(ui, settings, journal, journal.start(settings))
    with pytest.raises(TimeoutError):
        await controller.purchase(state, "data")
    assert ui.buy.await_count == 1 and controller.spent == 0
    assert journal.history()["actions"][0]["status"] == "uncertain"
    journal.close()


async def test_stop_interrupts_long_countdown(settings, state):
    journal = Journal(settings.runtime_dir)
    controller = Controller(None, settings, journal, journal.start(settings))

    async def stop():
        await asyncio.sleep(0.01)
        (settings.runtime_dir / "STOP").touch()

    task = asyncio.create_task(stop())
    with pytest.raises(StopRequested):
        await asyncio.wait_for(controller.wait(100), 1)
    await task
    journal.close()


async def test_worker_pauses_before_game_calls_and_resumes(settings, state, monkeypatch):
    clock = datetime.fromisoformat("2026-11-12T00:29+07:00")
    monkeypatch.setattr("ojol.maintenance.now", lambda: clock)
    window = MaintenanceWindow.parse("2026-11-12 00:30 / 2026-11-12 01:30")
    ui = SimpleNamespace(snapshot=AsyncMock(return_value=state))
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        write_private(controller.maintenance_file, window.payload())

        async def advance(seconds):
            nonlocal clock
            ui.snapshot.assert_not_awaited()
            assert controller.stage == "maintenance"
            clock = window.end

        monkeypatch.setattr("ojol.controller.asyncio.sleep", advance)
        await controller.run(dry_run=True)
        ui.snapshot.assert_awaited_once()
        assert controller.last_event == "dry_run"
    finally:
        journal.close()


async def test_purchase_does_not_start_if_maintenance_begins_during_preview(
    settings, state, shop_preview, monkeypatch
):
    clock = datetime.fromisoformat("2026-11-12T00:27:59+07:00")
    monkeypatch.setattr("ojol.maintenance.now", lambda: clock)
    window = MaintenanceWindow.parse("2026-11-12 00:30 / 2026-11-12 01:30")
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )

    async def preview(resource):
        nonlocal clock
        clock = datetime.fromisoformat("2026-11-12T00:28:00+07:00")
        return [shop_preview([product])]

    ui = SimpleNamespace(preview_shops=preview, buy=AsyncMock())
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        write_private(controller.maintenance_file, window.payload())
        assert await controller.purchase(state, "data") is False
        ui.buy.assert_not_awaited()
        assert journal.history()["actions"] == []
    finally:
        journal.close()


async def test_trip_completion_verified_only_after_history_change(settings, state):
    before = state.model_copy(update={"phase": "complete", "buttons": ["✅ Sampai! Terima ongkos"]})
    after = state.model_copy(update={"history": ["17.30 trip fixture · +0,72", *state.history]})
    ui = SimpleNamespace(job_click=AsyncMock(), snapshot=AsyncMock(return_value=after))
    journal = Journal(settings.runtime_dir)
    controller = Controller(ui, settings, journal, journal.start(settings))
    await controller.job_action(before, "complete")
    assert controller.completed == 1
    assert journal.history()["actions"][0]["status"] == "verified"
    journal.close()


async def test_sleeping_worker_stops_before_any_purchase_or_search(settings, state):
    asleep = state.model_copy(
        update={"phase": "sleeping", "raw_text": "Kamu sedang tidur. Tekan ☀ Bangun dulu."}
    )
    ui = SimpleNamespace(
        snapshot=AsyncMock(return_value=asleep), job_click=AsyncMock(), buy=AsyncMock()
    )
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        with pytest.raises(RuntimeError, match="Bangun"):
            await controller.run()
        assert not journal.history()["actions"]
        ui.job_click.assert_not_awaited()
        ui.buy.assert_not_awaited()
    finally:
        journal.close()


async def test_verification_reports_sleeping_instead_of_stale_before_state(settings, state):
    asleep = state.model_copy(
        update={"phase": "sleeping", "raw_text": "Kamu sedang tidur. Tekan ☀ Bangun dulu."}
    )
    ui = SimpleNamespace(snapshot=AsyncMock(return_value=asleep))
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        with pytest.raises(RuntimeError, match="Bangun"):
            await controller.verify(lambda snapshot: False)
        assert controller.state is asleep
        ui.snapshot.assert_awaited_once()
    finally:
        journal.close()


async def test_search_accepts_in_progress_once_without_repeating_click(settings, state):
    before = state.model_copy(update={"buttons": ["📲 Cari order"]})
    searching = before.model_copy(update={"phase": "searching", "buttons": ["⏳ Mencari…"]})
    ui = SimpleNamespace(snapshot=AsyncMock(return_value=searching), job_click=AsyncMock())
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        await controller.job_action(before, "search")
        ui.job_click.assert_awaited_once_with("📲 Cari order")
        ui.snapshot.assert_awaited_once()
        assert journal.history()["actions"][0]["status"] == "verified"
        assert controller.state.phase == "searching"
    finally:
        journal.close()


async def test_dry_run_never_performs_gameplay(settings, state):
    ui = SimpleNamespace(
        snapshot=AsyncMock(return_value=state), buy=AsyncMock(), job_click=AsyncMock()
    )
    journal = Journal(settings.runtime_dir)
    controller = Controller(ui, settings, journal, journal.start(settings))
    await controller.run(dry_run=True)
    ui.buy.assert_not_called()
    ui.job_click.assert_not_called()
    assert journal.history()["actions"] == []
    journal.close()


def test_cli_live_and_http_blocked_in_testing(settings, monkeypatch, capsys):
    monkeypatch.setenv("OJOL_RUNTIME_DIR", str(settings.runtime_dir))
    assert main(["--env-file", str(ROOT / ".env.testing"), "run", "--live"]) == 2
    assert "izin operator" in capsys.readouterr().err
    assert main(["--env-file", str(ROOT / ".env.testing"), "inspect"]) == 2
    assert "diblokir" in capsys.readouterr().err


async def test_complete_loop_maintains_searches_waits_and_claims(settings, state, shop_preview):
    settings = settings.model_copy(update={"max_jobs": 1})
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    replenished = state.model_copy(update={"wallet": state.wallet - Decimal("0.5"), "data": 86})
    delivering = replenished.model_copy(
        update={
            "phase": "delivering",
            "remaining_seconds": 2,
            "trip": "Trip fixture",
            "buttons": ["🛵 Mengantar… 0:02"],
        }
    )
    complete = delivering.model_copy(
        update={
            "phase": "complete",
            "remaining_seconds": 0,
            "buttons": ["✅ Sampai! Terima ongkos"],
        }
    )
    finished = replenished.model_copy(
        update={
            "wallet": replenished.wallet + Decimal("0.72"),
            "history": ["18.01 trip fixture · +0,72", *state.history],
        }
    )
    ui = SimpleNamespace(
        preview_shops=AsyncMock(return_value=[shop_preview([product])]),
        buy=AsyncMock(),
        job_click=AsyncMock(),
        snapshot=AsyncMock(
            side_effect=[
                state,
                replenished,
                replenished,
                delivering,
                delivering,
                complete,
                finished,
                finished,
            ]
        ),
    )
    journal = Journal(settings.runtime_dir)
    controller = Controller(ui, settings, journal, journal.start(settings))
    controller.wait = AsyncMock()
    with pytest.raises(StopRequested, match="jumlah trip"):
        await controller.run()
    assert ui.buy.await_count == 1 and ui.job_click.await_count == 2
    controller.wait.assert_awaited_once()
    assert controller.wait.call_args.args[0] > 2
    assert controller.spent == Decimal("0.5") and controller.completed == 1
    assert all(row["status"] == "verified" for row in journal.history()["actions"])
    journal.close()


async def test_capacity_deferral_checks_next_resource_on_same_snapshot(
    settings, state, shop_preview
):
    state = state.model_copy(update={"fuel": 45})
    fuel = Product(
        name="Isi Pertalite", price="0.5", effects={"fuel": 60}, row_text="fuel", enabled=True
    )
    data = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="data", enabled=True
    )
    after = state.model_copy(update={"wallet": state.wallet - Decimal("0.5"), "data": 86})
    ui = SimpleNamespace(
        preview_shops=AsyncMock(side_effect=[[shop_preview([fuel])], [shop_preview([data])]]),
        buy=AsyncMock(),
        snapshot=AsyncMock(side_effect=[state, after, StopRequested("done")]),
    )
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        with pytest.raises(StopRequested, match="done"):
            await controller.run()
        assert [call.args for call in ui.preview_shops.await_args_list] == [("fuel",), ("data",)]
        ui.buy.assert_awaited_once_with(data, state.wallet, state.data, settings.min_balance)
        assert len(journal.history()["actions"]) == 1
    finally:
        journal.close()


async def test_cancel_before_purchase_sends_nothing(settings, state):
    ui = SimpleNamespace(preview_shops=AsyncMock(), buy=AsyncMock())
    journal = Journal(settings.runtime_dir)
    cancel = asyncio.Event()
    cancel.set()
    controller = Controller(ui, settings, journal, journal.start(settings), cancel)
    with pytest.raises(StopRequested):
        await controller.purchase(state, "data")
    ui.preview_shops.assert_not_awaited()
    ui.buy.assert_not_awaited()
    assert not journal.history()["actions"]
    journal.close()


def test_status_shows_elapsed_countdown_in_wib(settings, monkeypatch, capsys):
    from datetime import timedelta

    from ojol import cli
    from ojol.models import now

    moment = now()
    (settings.runtime_dir / "status.json").write_text(
        json.dumps(
            {"event": "menunggu", "wait_until": (moment + timedelta(seconds=90)).isoformat()}
        )
    )
    monkeypatch.setenv("OJOL_RUNTIME_DIR", str(settings.runtime_dir))
    monkeypatch.setattr(cli, "running", lambda _: True)
    monkeypatch.setattr(cli, "now", lambda: moment)
    assert main(["--env-file", str(ROOT / ".env.testing"), "status"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["countdown_estimate"] == "1:30"
    assert output["wait_until_wib"].endswith("+07:00")


async def test_stuck_search_stops_without_clicking_again(settings, state):
    import time

    ui = SimpleNamespace(
        snapshot=AsyncMock(return_value=state.model_copy(update={"phase": "searching"})),
        job_click=AsyncMock(),
    )
    journal = Journal(settings.runtime_dir)
    controller = Controller(ui, settings, journal, journal.start(settings))
    controller.busy_since = time.monotonic() - 31
    with pytest.raises(RuntimeError, match="30 detik"):
        await controller.run()
    ui.job_click.assert_not_awaited()
    assert not journal.history()["actions"]
    journal.close()


async def test_unlimited_run_passes_old_trip_and_duration_limits_but_manual_stop_works(
    settings, state
):
    import time

    from ojol.models import Settings

    assert Settings().max_jobs is None and Settings().max_minutes is None
    assert Settings(max_jobs="", max_minutes="").max_jobs is None
    unlimited = settings.model_copy(update={"max_jobs": None, "max_minutes": None})
    ui = SimpleNamespace(
        snapshot=AsyncMock(
            return_value=state.model_copy(update={"fuel": 100, "condition": 100, "data": 100})
        )
    )
    journal = Journal(settings.runtime_dir)
    controller = Controller(ui, unlimited, journal, journal.start(unlimited))
    controller.started = time.monotonic() - 100 * 86400
    controller.completed = 100000
    controller.check_cancel()
    controller.job_action = AsyncMock(side_effect=StopRequested("reached next order"))
    with pytest.raises(StopRequested, match="reached next order"):
        await controller.run()
    controller.job_action.assert_awaited_once()
    (settings.runtime_dir / "STOP").touch()
    with pytest.raises(StopRequested, match="Dihentikan pengguna"):
        controller.check_cancel()
    journal.close()


def test_explicit_duration_limit_still_supported_for_isolated_checks(settings):
    import time

    journal = Journal(settings.runtime_dir)
    controller = Controller(
        None, settings.model_copy(update={"max_minutes": 1}), journal, journal.start(settings)
    )
    controller.started = time.monotonic() - 61
    with pytest.raises(StopRequested, match="Batas durasi"):
        controller.check_cancel()
    journal.close()


def test_background_start_omits_unlimited_flags(settings, monkeypatch):
    from unittest.mock import Mock

    from ojol import cli
    from ojol.models import ROOT

    unlimited = settings.model_copy(
        update={"env": "local", "operator_authorized": True, "max_jobs": None, "max_minutes": None}
    )
    monkeypatch.setattr(cli, "load_settings", lambda path: unlimited)
    launch = Mock(return_value=SimpleNamespace(pid=12345, poll=lambda: None))
    monkeypatch.setattr(cli.subprocess, "Popen", launch)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    assert cli.main(["--env-file", str(ROOT / ".env.testing"), "start", "--live"]) == 0
    command = launch.call_args.args[0]
    assert "--max-jobs" not in command and "--max-minutes" not in command and "None" not in command


def test_start_error_does_not_inherit_previous_process_verification_stage(settings, monkeypatch):
    import ojol.app as app
    import ojol.cli as cli

    isolated = settings.model_copy(update={"env": "local"})
    (settings.runtime_dir / "status.json").write_text(
        json.dumps({"pid": -1, "event": "gagal", "stage": "job.complete.verify", "run_id": 1})
    )
    monkeypatch.setattr(cli, "load_settings", lambda path: isolated)
    monkeypatch.setattr(
        app, "run_app", AsyncMock(side_effect=RuntimeError("Aksi belum terverifikasi"))
    )
    monkeypatch.setattr("ojol.telegram.flush_notices", AsyncMock())
    assert cli.main(["--env-file", str(ROOT / ".env.testing"), "run"]) == 2
    error = json.loads((settings.runtime_dir / "last-error.json").read_text())
    assert error["stage"] == "cli.run"


async def test_observation_failure_after_verified_claim_does_not_reopen_or_repeat_claim(
    settings, state
):
    before = state.model_copy(update={"phase": "complete", "buttons": ["✅ Sampai! Terima ongkos"]})
    paid = state.model_copy(
        update={
            "history": ["23.03 A → B · +0,401", *before.history],
            "wallet": before.wallet + Decimal("0.401"),
        }
    )
    failure = HttpCoreError("Pembacaan HTTP timeout", category="transport")
    ui = SimpleNamespace(
        job_click=AsyncMock(), snapshot=AsyncMock(side_effect=[before, paid, failure])
    )
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        with pytest.raises(HttpCoreError):
            await controller.run()
        ui.job_click.assert_awaited_once()
        assert journal.history()["actions"][0]["status"] == "verified"
        assert journal.profit()["pendapatan_ojol"] == "0.401"
        assert journal.profit()["trip_tercatat"] == 1
        assert journal.start(settings) > controller.run_id
    finally:
        journal.close()
