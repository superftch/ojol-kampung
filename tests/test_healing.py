import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ojol.control import ControlService
from ojol.controller import StopRequested
from ojol.healing import capture_diagnostics, request_browser_restart, write_private
from ojol.mcp_browser import BrowserError, McpBrowser
from ojol.models import Product
from ojol.ui import GameUI


def timeout():
    return BrowserError(
        "Runtime.evaluate timed out after 15s waiting for the daemon", operation="browser_cdp"
    )


@pytest.fixture
def reader(settings, monkeypatch):
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.call = AsyncMock(
        side_effect=lambda name, **kw: (
            []
            if name == "browser_list_tabs"
            else {"dialog": {"type": "alert", "message": "PRIVATE_COOKIE_DO_NOT_LOG"}}
        )
    )
    browser.refresh_owned_tab = AsyncMock()
    browser.on_recovery = Mock()
    monkeypatch.setattr("ojol.mcp_browser.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "ojol.healing.capture_diagnostics", Mock(return_value="browser-fixture.json")
    )
    return browser


async def test_read_timeout_retries_and_recovers_without_refresh_or_browser_restart(reader):
    reader.js = AsyncMock(side_effect=[timeout(), {"phase": "idle"}])
    assert await reader.read_js("pure read") == {"phase": "idle"}
    assert reader.js.await_count == 2
    reader.refresh_owned_tab.assert_not_awaited()
    events = [call.args[0] for call in reader.on_recovery.call_args_list]
    assert events == ["browser_diagnostic", "browser_read_retry", "browser_read_recovered"]
    assert "PRIVATE_COOKIE" not in str(reader.on_recovery.call_args_list)


async def test_refresh_is_attempted_only_after_bounded_read_retries(reader):
    reader.js = AsyncMock(side_effect=[timeout(), timeout(), timeout(), "fresh"])
    assert await reader.read_js("pure read") == "fresh"
    assert reader.js.await_count == 4
    reader.refresh_owned_tab.assert_awaited_once()


async def test_owned_browser_restart_then_new_owned_tab_after_refresh_fails(reader):
    reader.js = AsyncMock(side_effect=[timeout(), timeout(), timeout(), "fresh browser"])
    reader.refresh_owned_tab.side_effect = timeout()
    reader.recover_browser = AsyncMock()
    reader.open_owned_tab = AsyncMock()
    reader.tab_id = reader.session_tab = "old"
    reader.session_id = "old-session"
    assert await reader.read_js("pure read") == "fresh browser"
    reader.recover_browser.assert_awaited_once()
    reader.open_owned_tab.assert_awaited_once()
    assert reader.tab_id is None and reader.session_id is None


async def test_login_expiry_and_ui_errors_never_retry(reader):
    reader.js = AsyncMock(
        side_effect=BrowserError(
            "Sesi login berakhir. Import Cookie", stage="browser.ui", operation="browser_cdp"
        )
    )
    with pytest.raises(BrowserError, match="Import Cookie"):
        await reader.read_js("pure read")
    reader.js.assert_awaited_once()
    reader.call.assert_not_awaited()
    reader.refresh_owned_tab.assert_not_awaited()


async def test_ui_error_after_refresh_stops_without_restart(reader):
    reader.js = AsyncMock(
        side_effect=[
            timeout(),
            timeout(),
            timeout(),
            BrowserError("Dompet cash tidak tersedia", stage="browser.ui"),
        ]
    )
    reader.recover_browser = AsyncMock()
    with pytest.raises(BrowserError, match="Dompet"):
        await reader.read_js("pure read")
    reader.refresh_owned_tab.assert_awaited_once()
    reader.recover_browser.assert_not_awaited()


async def test_stop_during_retry_backoff_cancels_before_next_read(reader, monkeypatch):
    reader.js = AsyncMock(side_effect=timeout())
    stopped = False

    def check():
        if stopped:
            raise StopRequested("Stop fixture")

    async def sleep(seconds):
        nonlocal stopped
        stopped = True

    reader.check_cancel = check
    monkeypatch.setattr("ojol.mcp_browser.asyncio.sleep", sleep)
    with pytest.raises(StopRequested):
        await reader.read_js("pure read")
    reader.js.assert_awaited_once()
    reader.refresh_owned_tab.assert_not_awaited()


async def test_repeated_unhealthy_episodes_stop_at_recovery_budget(reader):
    reader.js = AsyncMock(side_effect=timeout())
    reader.heal_times = [time.monotonic()] * 3
    with pytest.raises(BrowserError, match="Batas self-healing"):
        await reader.read_js("pure read")
    assert reader.js.await_count == 3
    reader.refresh_owned_tab.assert_not_awaited()


async def test_mutating_ui_calls_never_opt_into_retry():
    browser = SimpleNamespace(js=AsyncMock(return_value={"clicked": True}))
    ui = GameUI(browser)
    item = Product(
        name="Isi pulsa", price="0.5", effects={"data": 40}, row_text="fixture", enabled=True
    )
    await ui.buy(item, 30, 20)
    await ui.job_click("✅ Sampai! Terima ongkos")
    await ui.click_selector('[data-tour="nav-kerja"]')
    assert all(not call.kwargs.get("read_only") for call in browser.js.call_args_list)


async def test_snapshot_uses_one_read_when_panel_is_ready_and_reopens_only_when_needed():
    data = {
        "text": "Narik",
        "tiles": {"Bensin": "48%", "Kondisi": "71%", "Kuota HP": "97%"},
        "wallet": "45,09 koin",
        "buttons": [{"text": "📲 Cari order"}],
    }
    browser = SimpleNamespace(js=AsyncMock(return_value=data))
    ui = GameUI(browser)
    ui.work = AsyncMock()
    assert (await ui.snapshot()).fuel == 48
    browser.js.assert_awaited_once()
    assert browser.js.call_args.kwargs["read_only"] is True
    ui.work.assert_not_awaited()
    browser.js.reset_mock()
    browser.js.side_effect = [{"needs_work": True}, data]
    assert (await ui.snapshot()).data == 97
    ui.work.assert_awaited_once()
    assert browser.js.await_count == 2


def payload(worker=42):
    return {"id": "a" * 32, "pid": worker, "parent_pid": os.getpid(), "created": time.time()}


@pytest.fixture
def service(settings):
    settings = settings.model_copy(update={"managed_browser": True})
    browser = SimpleNamespace(close=AsyncMock(), switch=AsyncMock(), mode="headless")
    control = ControlService(settings, browser=browser)
    control.worker = SimpleNamespace(pid=42, returncode=None)
    return control


async def test_parent_restarts_only_owned_chromium_and_preserves_worker(service):
    write_private(service.settings.runtime_dir / "browser-recovery-request.json", payload())
    worker = service.worker
    await service.handle_browser_recovery()
    service.browser.close.assert_awaited_once()
    service.browser.switch.assert_awaited_once_with("headless")
    assert service.worker is worker and worker.returncode is None
    reply = json.loads((service.settings.runtime_dir / "browser-recovery-reply.json").read_text())
    assert reply == {"id": "a" * 32, "ok": True}


@pytest.mark.parametrize("case", ["foreign_worker", "wrong_parent", "expired", "stopped", "budget"])
async def test_parent_rejects_foreign_stale_stopped_or_excessive_restart_requests(service, case):
    request = payload()
    if case == "foreign_worker":
        request["pid"] = 99
    if case == "wrong_parent":
        request["parent_pid"] = -1
    if case == "expired":
        request["created"] -= 120
    if case == "stopped":
        (service.settings.runtime_dir / "STOP").touch()
    if case == "budget":
        service.browser_restarts = [time.monotonic()] * 3
    write_private(service.settings.runtime_dir / "browser-recovery-request.json", request)
    await service.handle_browser_recovery()
    service.browser.close.assert_not_awaited()
    service.browser.switch.assert_not_awaited()
    assert not json.loads(
        (service.settings.runtime_dir / "browser-recovery-reply.json").read_text()
    )["ok"]


async def test_restart_ipc_is_private_and_waits_for_matching_ack(settings, monkeypatch):
    settings = settings.model_copy(update={"env": "local", "managed_browser": True})

    async def acknowledge(seconds):
        request = json.loads((settings.runtime_dir / "browser-recovery-request.json").read_text())
        assert request["pid"] == os.getpid() and request["parent_pid"] == os.getppid()
        assert (
            settings.runtime_dir / "browser-recovery-request.json"
        ).stat().st_mode & 0o777 == 0o600
        write_private(
            settings.runtime_dir / "browser-recovery-reply.json", {"id": request["id"], "ok": True}
        )

    monkeypatch.setattr("ojol.healing.asyncio.sleep", acknowledge)
    await request_browser_restart(settings, lambda: None)
    assert not (settings.runtime_dir / "browser-recovery-request.json").exists()
    assert not (settings.runtime_dir / "browser-recovery-reply.json").exists()


def test_diagnostic_capture_excludes_argv_secrets_and_keeps_bounded_private_history(
    settings, monkeypatch
):
    import ojol.healing as module

    proc = settings.runtime_dir / "fake-proc"
    process = proc / "58"
    process.mkdir(parents=True)
    (process / "comm").write_text("chromium\n")
    fields = ["S"] + ["0"] * 22
    fields[11], fields[12], fields[19], fields[21] = "17", "9", "12345", "1000"
    (process / "stat").write_text("58 (chromium) " + " ".join(fields))
    (process / "cmdline").write_bytes(b"chromium --type=gpu-process --cookie=PRIVATE_COOKIE\0")
    group = settings.runtime_dir / "fake-cgroup"
    group.mkdir()
    (group / "cpu.stat").write_text("nr_throttled 308\nthrottled_usec 148046\n")
    original = Path
    monkeypatch.setattr(
        module,
        "Path",
        lambda value: (
            proc if value == "/proc" else group if value == "/sys/fs/cgroup" else original(value)
        ),
    )
    for _ in range(22):
        name = capture_diagnostics(
            settings.runtime_dir, "read_timeout", {"browser_level": "responsive"}
        )
    files = list((settings.runtime_dir / "diagnostics").glob("*.json"))
    assert len(files) == 20
    raw = (settings.runtime_dir / "diagnostics" / name).read_text()
    assert "PRIVATE_COOKIE" not in raw and "--cookie" not in raw
    data = json.loads(raw)
    assert data["chromium_processes"][0]["type"] == "gpu-process"
    assert data["chromium_processes"][0]["cpu_ticks"] == 26
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in files)


async def test_verification_read_retry_after_claim_does_not_click_claim_twice(
    settings, monkeypatch
):
    from decimal import Decimal

    from ojol.controller import Controller
    from ojol.journal import Journal

    settings = settings.model_copy(update={"max_jobs": 1})
    browser = McpBrowser(settings.runtime_dir / "harness", None)
    browser.tab_id = browser.session_tab = "owned"
    browser.session_id = "owned-session"
    reads = 0
    clicks = 0

    def dom(paid):
        return {
            "text": "Narik" if paid else "Antar",
            "tiles": {
                "Bensin": "48%",
                "Kondisi": "71%",
                "Kuota HP": "97%",
                "Hasil hari ini": "0,72" if paid else "0",
            },
            "wallet": "30,72 koin" if paid else "30 koin",
            "buttons": [{"text": "📲 Cari order" if paid else "✅ Sampai! Terima ongkos"}],
            "history": ["23.00 A → B · +0,72"] if paid else [],
        }

    async def cdp(name, **args):
        nonlocal reads, clicks
        if name == "browser_list_tabs":
            return []
        if name == "browser_page_info":
            return {}
        expression = args["params"]["expression"]
        if "buttons[0].click()" in expression:
            clicks += 1
            value = {"clicked": True}
        else:
            reads += 1
            if reads == 2:
                raise timeout()
            value = dom(reads > 2)
        return {"result": {"value": value}}

    browser.call = AsyncMock(side_effect=cdp)
    monkeypatch.setattr("ojol.healing.capture_diagnostics", Mock(return_value="fixture.json"))
    monkeypatch.setattr("ojol.mcp_browser.asyncio.sleep", AsyncMock())
    ui = GameUI(browser)
    journal = Journal(settings.runtime_dir)
    try:
        controller = Controller(ui, settings, journal, journal.start(settings))
        with pytest.raises(StopRequested, match="jumlah trip"):
            await controller.run()
        assert clicks == 1 and controller.completed == 1
        assert journal.history()["actions"][0]["status"] == "verified"
        assert journal.profit()["pendapatan_ojol"] == str(Decimal("0.72"))
        assert journal.profit()["trip_tercatat"] == 1
        events = [row[0] for row in journal.db.execute("SELECT event FROM events")]
        assert "browser_read_retry" in events and "browser_read_recovered" in events
    finally:
        journal.close()


async def test_failed_controller_restart_does_not_continue_read(reader):
    reader.js = AsyncMock(side_effect=[timeout(), timeout(), timeout()])
    reader.refresh_owned_tab.side_effect = timeout()
    reader.recover_browser = AsyncMock(
        side_effect=BrowserError(
            "Restart ditolak", stage="browser.self_heal", operation="browser_cdp"
        )
    )
    with pytest.raises(BrowserError, match="Restart ditolak"):
        await reader.read_js("pure read")
    assert reader.js.await_count == 3
    reader.recover_browser.assert_awaited_once()


async def test_parent_reports_restart_failure_and_honors_stop_received_during_restart(service):
    service.browser.switch.side_effect = RuntimeError("Fixture startup failure")
    write_private(service.settings.runtime_dir / "browser-recovery-request.json", payload())
    await service.handle_browser_recovery()
    assert not json.loads(
        (service.settings.runtime_dir / "browser-recovery-reply.json").read_text()
    )["ok"]
    service.browser.switch.side_effect = None

    async def stop_while_closing():
        service.expected_stop = True

    service.browser.close.side_effect = stop_while_closing
    write_private(service.settings.runtime_dir / "browser-recovery-request.json", payload())
    await service.handle_browser_recovery()
    assert not json.loads(
        (service.settings.runtime_dir / "browser-recovery-reply.json").read_text()
    )["ok"]


async def test_ipc_abort_on_user_stop_removes_only_own_request(settings):
    settings = settings.model_copy(update={"env": "local", "managed_browser": True})

    def stop():
        raise StopRequested("Fixture stopped")

    with pytest.raises(StopRequested):
        await request_browser_restart(settings, stop)
    assert not (settings.runtime_dir / "browser-recovery-request.json").exists()


async def test_restart_ipc_timeout_is_bounded_and_removes_request(settings, monkeypatch):
    settings = settings.model_copy(update={"env": "local", "managed_browser": True})

    class Deadline:
        async def __aenter__(self):
            raise TimeoutError

        async def __aexit__(self, *args):
            pass

    deadline = Mock(return_value=Deadline())
    monkeypatch.setattr("ojol.healing.asyncio.timeout", deadline)
    with pytest.raises(BrowserError, match="45 detik"):
        await request_browser_restart(settings, lambda: None)
    deadline.assert_called_once_with(45)
    assert not (settings.runtime_dir / "browser-recovery-request.json").exists()


async def test_dead_browser_allows_active_worker_to_request_recovery(service, monkeypatch):
    service.browser.alive = lambda: False
    service.stop_worker = AsyncMock()
    monkeypatch.setattr("ojol.control.flush_notices", AsyncMock())

    async def end_iteration(seconds):
        service.closing = True

    monkeypatch.setattr("ojol.control.asyncio.sleep", end_iteration)
    await service.supervise()
    service.stop_worker.assert_not_awaited()
    assert not (service.settings.runtime_dir / "STOP").exists()


async def test_readiness_checks_user_stop_before_evaluating_page(reader):
    def stopped():
        raise StopRequested("Startup stopped")

    reader.check_cancel = stopped
    reader.js = AsyncMock()
    reader.reset_focus = AsyncMock()
    with pytest.raises(StopRequested, match="Startup stopped"):
        await reader.wait_ready()
    reader.js.assert_not_awaited()


def test_diagnostics_cli_reads_only_latest_five_files(settings, monkeypatch, capsys):
    from ojol import cli

    directory = settings.runtime_dir / "diagnostics"
    directory.mkdir()
    for index in range(7):
        write_private(directory / f"browser-{index:02}.json", {"fixture": index})
    monkeypatch.setenv("OJOL_RUNTIME_DIR", str(settings.runtime_dir))
    assert cli.main(["--env-file", str(cli.ROOT / ".env.testing"), "diagnostics"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"fixture": index} for index in range(2, 7)]
