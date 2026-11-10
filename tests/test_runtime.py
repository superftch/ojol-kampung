import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ojol.cli import exclusive_lock, main, running
from ojol.config import load_settings
from ojol.controller import Controller, StopRequested
from ojol.journal import Journal
from ojol.mcp_browser import TOOLS, BrowserError, McpBrowser
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


async def test_purchase_verified_by_wallet_and_resource(settings, state):
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    after = state.model_copy(update={"wallet": state.wallet - Decimal("0.5"), "data": 86})
    ui = SimpleNamespace(
        open_shop=AsyncMock(return_value=("Konter fixture", [product])),
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


async def test_timeout_does_not_repeat_purchase(settings, state):
    product = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    ui = SimpleNamespace(
        open_shop=AsyncMock(return_value=("Konter fixture", [product])),
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


async def test_real_harness_mcp_tool_discovery_no_chrome(settings):
    command = str(Path(sys.executable).parent / "browser-harness-mcp")
    async with McpBrowser(settings.runtime_dir / "harness", None, command=command) as browser:
        assert set(browser.tools) == set(TOOLS)
        assert "browser_click" not in browser.tools
        assert "browser_http_get" not in browser.tools


async def test_focus_emulation_only_raw_cdp_allowed(settings):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    with pytest.raises(BrowserError):
        await browser.call(
            "browser_cdp", method="Target.activateTarget", params={"targetId": "fixture"}
        )


async def test_target_scoped_js_never_acts_on_current_user_tab(settings):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.tab_id = "owned-fixture"
    browser.session_id = "owned-session"
    browser.session_tab = browser.tab_id
    browser.call = AsyncMock(return_value={"result": {"value": True}})
    await browser.js("true")
    assert browser.call.call_args.kwargs["params"]["session_id"] == "owned-session"
    assert "location.origin" in browser.call.call_args.kwargs["params"]["expression"]


def test_cli_live_and_browser_blocked_in_testing(settings, monkeypatch, capsys):
    monkeypatch.setenv("OJOL_RUNTIME_DIR", str(settings.runtime_dir))
    assert main(["--env-file", str(ROOT / ".env.testing"), "run", "--live"]) == 2
    assert "izin operator" in capsys.readouterr().err
    assert main(["--env-file", str(ROOT / ".env.testing"), "inspect"]) == 2
    assert "diblokir" in capsys.readouterr().err


async def test_complete_loop_maintains_searches_waits_and_claims(settings, state):
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
        open_shop=AsyncMock(return_value=("Konter fixture", [product])),
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


async def test_cancel_before_purchase_sends_nothing(settings, state):
    ui = SimpleNamespace(open_shop=AsyncMock(), buy=AsyncMock())
    journal = Journal(settings.runtime_dir)
    cancel = asyncio.Event()
    cancel.set()
    controller = Controller(ui, settings, journal, journal.start(settings), cancel)
    with pytest.raises(StopRequested):
        await controller.purchase(state, "data")
    ui.open_shop.assert_not_awaited()
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


async def test_mcp_rejects_other_user_tabs(settings):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.tab_id = "owned-fixture"
    for name, args in [
        ("browser_js", {"expression": "true", "target_id": "user-tab"}),
        ("browser_switch_tab", {"target": "user-tab"}),
        ("browser_close_tab", {"target": "user-tab"}),
    ]:
        with pytest.raises(BrowserError):
            await browser.call(name, **args)


async def test_shop_eye_click_evidence_and_panel_identity():
    from ojol.ui import GameUI

    evidence = {
        "method": "eye_preview",
        "label": "Lihat SPBU Utara 1 di peta tanpa pergi",
        "button": "👀",
    }
    browser = SimpleNamespace(
        tab_id="owned-fixture",
        js=AsyncMock(
            side_effect=[
                True,
                False,
                [
                    {
                        "name": "SPBU Utara 1",
                        "text": "SPBU Pertamina SPBU Utara 1",
                        "hours": "🟢 Buka 24 jam",
                    }
                ],
                evidence,
                False,
                False,
                True,
            ]
        ),
    )
    ui = GameUI(browser)
    ui.close_views = AsyncMock()
    ui.click_selector = AsyncMock()
    ui.pause = AsyncMock()
    product = Product(
        name="Isi Pertalite", price="1", effects={"fuel": 60}, row_text="fixture", enabled=True
    )
    ui.products = AsyncMock(side_effect=[[], [], [product]])
    name, _ = await ui.open_shop("fuel")
    assert name == "SPBU Utara 1"
    assert ui.last_navigation["method"] == "eye_preview"
    assert ui.last_navigation["tab_id"] == "owned-fixture" and ui.last_navigation["panel_verified"]
    assert ui.products.await_count == 3
    eye_script = browser.js.call_args_list[3].args[0]
    assert "Lihat di peta" in eye_script and "eye.click()" in eye_script
    assert "tujuan-pergi" not in eye_script


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


async def test_owned_tab_loading_retries_only_readiness_without_replaying_navigation(
    settings, monkeypatch
):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.call = AsyncMock(
        side_effect=[[], {"targetId": "owned-new"}, {"sessionId": "owned-session"}, {}, {}, {}]
    )
    browser.js = AsyncMock(
        side_effect=[BrowserError("Runtime.evaluate timed out", operation="browser_js"), True]
    )
    monkeypatch.setattr("ojol.mcp_browser.asyncio.sleep", AsyncMock())
    assert await browser.open_owned_tab() == "owned-new"
    names = [c.args[0] for c in browser.call.await_args_list]
    assert names.count("browser_new_tab") == names.count("browser_goto") == 1
    assert browser.call.await_args_list[-1].kwargs["params"] == {"enabled": False}


async def test_cookie_import_prepares_blank_owned_tab_before_loading_game(settings):
    home = settings.runtime_dir / "harness"
    home.mkdir()
    (home / "owned-tab.json").write_text(json.dumps({"target_id": "owned-old"}))
    browser = McpBrowser(home, None)
    browser.call = AsyncMock(
        side_effect=[
            [
                {"targetId": "owned-old", "url": "https://www.kampungsebelah.com/kampung"},
                {"targetId": "user-other", "url": "https://example.com"},
            ],
            {},
            {"targetId": "owned-new"},
            {"sessionId": "owned-session"},
        ]
    )
    assert await browser.open_owned_tab(prepare_session=True) == "owned-new"
    assert [c.args[0] for c in browser.call.await_args_list] == [
        "browser_list_tabs",
        "browser_close_tab",
        "browser_new_tab",
        "browser_switch_tab",
    ]
    assert browser.call.await_args_list[1].kwargs["target"] == "owned-old"


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


async def test_runtime_evaluation_rejects_foreign_sessions_and_never_replays_timeout(settings):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.tab_id = "owned"
    browser.session_tab = "owned"
    browser.session_id = "owned-session"
    params = {
        "session_id": "foreign-session",
        "expression": "true",
        "returnByValue": True,
        "awaitPromise": False,
        "_response_timeout": 15,
    }
    with pytest.raises(BrowserError):
        await browser.call("browser_cdp", method="Runtime.evaluate", params=params)
    tool = SimpleNamespace(run_async=AsyncMock(side_effect=TimeoutError))
    browser.tools = {"browser_cdp": tool}
    with pytest.raises(BrowserError):
        await browser.js("document.querySelector('button').click()")
    assert tool.run_async.await_count == 1
    args = tool.run_async.call_args.kwargs["args"]["params"]
    assert (
        args["session_id"] == "owned-session"
        and args["_response_timeout"] == 15
        and args["awaitPromise"] is False
    )


async def test_runtime_timeout_does_not_expose_javascript_expression(settings):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.tab_id = "owned"
    browser.session_tab = "owned"
    browser.session_id = "owned-session"
    tool = SimpleNamespace(
        run_async=AsyncMock(
            return_value={
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"error": "Runtime.evaluate timed out; expression: private script body"}
                        ),
                    }
                ]
            }
        )
    )
    browser.tools = {"browser_cdp": tool}
    with pytest.raises(BrowserError) as error:
        await browser.js("true")
    assert str(error.value) == "Runtime.evaluate timed out"


@pytest.mark.parametrize("enabled", [True, False])
async def test_focus_uses_owned_persistent_session_and_15_second_daemon_deadline(settings, enabled):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.tab_id = browser.session_tab = "owned"
    browser.session_id = "owned-session"
    tool = SimpleNamespace(
        run_async=AsyncMock(return_value={"content": [{"type": "text", "text": "{}"}]})
    )
    browser.tools = {"browser_cdp": tool}
    await browser.call(
        "browser_cdp", method="Emulation.setFocusEmulationEnabled", params={"enabled": enabled}
    )
    assert tool.run_async.call_args.kwargs["args"]["params"] == {
        "enabled": enabled,
        "session_id": "owned-session",
        "_response_timeout": 15,
    }
    browser.session_tab = "foreign"
    with pytest.raises(BrowserError, match="di luar izin"):
        await browser.call(
            "browser_cdp", method="Emulation.setFocusEmulationEnabled", params={"enabled": enabled}
        )
    tool.run_async.assert_awaited_once()


async def test_focus_cleanup_timeout_preserves_primary_verification_error(settings):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.call = AsyncMock(side_effect=BrowserError("Focus daemon timed out"))
    primary = BrowserError("Runtime.evaluate timed out", operation="browser_cdp")
    with pytest.raises(BrowserError) as error:
        try:
            raise primary
        finally:
            await browser.reset_focus()
    assert error.value is primary
    assert primary.__notes__ == ["Focus cleanup also failed: BrowserError"]
    browser.call.assert_awaited_once()


async def test_focus_cleanup_failure_without_primary_is_not_swallowed(settings):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.call = AsyncMock(side_effect=BrowserError("Focus daemon timed out"))
    with pytest.raises(BrowserError, match="Focus daemon timed out"):
        await browser.reset_focus()


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
