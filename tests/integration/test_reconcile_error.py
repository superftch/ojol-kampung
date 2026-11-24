import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.storage import write_private
from app.modules.ledger.reconciliation import reconcile
from app.modules.ledger.repository import Journal
from app.modules.notifications.service import record_error


@pytest.fixture
def purchase_error(settings, state):
    journal = Journal(settings.runtime_dir)
    run = journal.start(settings)
    payload = {
        "resource": "fuel",
        "shop": "SPBU fixture",
        "product": {"name": "Bensin fixture", "price": "1"},
    }
    action = journal.begin(run, "purchase", state, payload)
    journal.settle(action, False)
    other = journal.begin(run, "take", state, {"label": "Terima"})
    details = record_error(
        settings,
        RuntimeError("Pembelian timeout fixture"),
        "purchase.verify.fuel",
        {"run_id": run, "last_action": {"action_id": action, "kind": "purchase"}},
    )
    after = state.model_copy(
        update={
            "observed_at": state.observed_at + timedelta(seconds=5),
            "wallet": state.wallet - Decimal(1),
            "fuel": state.fuel + 10,
        }
    )
    try:
        yield journal, action, other, after, details
    finally:
        journal.close()


@pytest.mark.parametrize("source", ["archive", "latest", ".json", ".sent", ".muted", ".sending"])
async def test_error_id_selects_only_related_action_and_reports_money_once(
    settings, purchase_error, source, capsys
):
    journal, action, other, after, details = purchase_error
    error_id = details["error_id"]
    archive = settings.runtime_dir / "errors" / f"{error_id}.json"
    record_error(settings, RuntimeError("Later unrelated error"), "cli.inspect")
    if source != "archive":
        archive.unlink()
        if source == "latest":
            write_private(settings.runtime_dir / "last-error.json", details)
        else:
            directory = settings.runtime_dir / "notifications"
            directory.mkdir()
            write_private(directory / f"legacy{source}", {"context": details})
    capsys.readouterr()
    ui = SimpleNamespace(snapshot=AsyncMock(return_value=after))
    await reconcile(ui, journal, error_id.lower())
    output = capsys.readouterr().out
    detail = json.loads(
        next(
            line.removeprefix("Detail rekonsiliasi: ")
            for line in output.splitlines()
            if line.startswith("Detail rekonsiliasi: ")
        )
    )
    assert error_id in output and details["message"] in output
    assert detail["action_id"] == action
    assert detail["status_before"] == "uncertain" and detail["status_after"] == "verified"
    assert detail["payload"]["product"]["name"] == "Bensin fixture"
    assert detail["before"]["fuel"] + 10 == detail["observed"]["fuel"]
    assert detail["wallet_delta"] == "-1.00" and detail["resource_delta"]["fuel"] == 10
    assert detail["evidence"]["expected_price"] == "1"
    assert detail["cashflows_added"] == [{"kind": "expense", "category": "fuel", "amount": "1"}]
    assert [row["id"] for row in journal.unresolved()] == [other]
    assert journal.profit()["pengeluaran"] == "1"
    ui.snapshot.assert_awaited_once()
    await reconcile(ui, journal, error_id)
    assert ui.snapshot.await_count == 1
    assert journal.profit()["pengeluaran"] == "1"
    repeated = capsys.readouterr().out
    assert '"cashflows_added": []' in repeated and "catatan ledger tersimpan" in repeated


async def test_error_without_action_explains_and_leaves_pending_actions(
    purchase_error, settings, capsys
):
    journal, action, other, _after, _ = purchase_error
    details = record_error(settings, RuntimeError("Worker masih aktif"), "cli.reconcile")
    ui = SimpleNamespace(snapshot=AsyncMock())
    assert await reconcile(ui, journal, details["error_id"]) is None
    ui.snapshot.assert_not_awaited()
    assert [row["id"] for row in journal.unresolved()] == [action, other]
    assert "tidak memiliki referensi aksi ledger" in capsys.readouterr().out


@pytest.mark.parametrize("error_id", ["../last-error", "OJL-000000000000"])
async def test_unknown_or_invalid_error_never_reads_game(purchase_error, error_id):
    journal, action, other, _after, _ = purchase_error
    ui = SimpleNamespace(snapshot=AsyncMock())
    with pytest.raises(ValueError, match="ID error"):
        await reconcile(ui, journal, error_id)
    ui.snapshot.assert_not_awaited()
    assert [row["id"] for row in journal.unresolved()] == [action, other]


@pytest.mark.parametrize("mismatch", ["run_id", "kind", "missing_action"])
async def test_error_context_must_match_account_ledger(settings, purchase_error, mismatch):
    journal, action, other, _after, details = purchase_error
    if mismatch == "run_id":
        details["run_id"] += 1
    elif mismatch == "kind":
        details["last_action"]["kind"] = "complete"
    else:
        details["last_action"]["action_id"] = 999999
    write_private(settings.runtime_dir / "errors" / f"{details['error_id']}.json", details)
    ui = SimpleNamespace(snapshot=AsyncMock())
    with pytest.raises(ValueError, match=r"tidak cocok|tidak ditemukan"):
        await reconcile(ui, journal, details["error_id"])
    ui.snapshot.assert_not_awaited()
    assert [row["id"] for row in journal.unresolved()] == [action, other]


def test_worker_reconcile_error_saves_pending_action_references(settings, purchase_error):
    _journal, action, other, _after, _ = purchase_error
    details = record_error(settings, RuntimeError("Offline fixture"), "worker.reconcile")
    assert details["action_ids"] == [action, other]
    archive = settings.runtime_dir / "errors" / f"{details['error_id']}.json"
    assert json.loads(archive.read_text()) == details
    assert archive.stat().st_mode & 0o777 == 0o600


async def test_purchase_outside_verification_window_stays_uncertain(purchase_error, capsys):
    journal, action, other, after, details = purchase_error
    after = after.model_copy(update={"observed_at": after.observed_at + timedelta(minutes=10)})
    await reconcile(
        SimpleNamespace(snapshot=AsyncMock(return_value=after)), journal, details["error_id"]
    )
    assert [row["id"] for row in journal.unresolved()] == [action, other]
    assert journal.profit()["pengeluaran"] == "0"
    assert "di luar jendela verifikasi" in capsys.readouterr().out


def test_cli_passes_error_id_and_scoped_account(settings, monkeypatch):
    import app.cli as cli
    import app.modules.worker.runner as app
    from app.core.models import ROOT
    from app.modules.accounts.repository import Accounts

    local = settings.model_copy(update={"env": "local"})
    registry = Accounts(local)
    from tests.conftest import seed_legacy_account

    account = seed_legacy_account(registry)
    monkeypatch.setattr(cli, "load_settings", lambda path: local)
    run_app = AsyncMock()
    monkeypatch.setattr(app, "run_app", run_app)
    assert (
        cli.main(
            [
                "--env-file",
                str(ROOT / ".env.testing"),
                "--account",
                account["id"],
                "reconcile",
                "--error-id",
                "OJL-012345ABCDEF",
            ]
        )
        == 0
    )
    args, kwargs = run_app.call_args
    assert args[0].runtime_dir == registry.scoped_settings(account).runtime_dir
    assert args[1] == "reconcile" and kwargs == {"error_id": "OJL-012345ABCDEF"}


async def test_worker_error_excludes_actions_created_after_error(settings, purchase_error):
    journal, _action, _other, after, _ = purchase_error
    details = record_error(settings, RuntimeError("Offline fixture"), "worker.reconcile")
    later = journal.begin(journal.history()["runs"][0]["id"], "search", after, {})
    after = after.model_copy(update={"phase": "delivering"})
    await reconcile(
        SimpleNamespace(snapshot=AsyncMock(return_value=after)), journal, details["error_id"]
    )
    assert [row["id"] for row in journal.unresolved()] == [later]
    assert journal.profit()["pengeluaran"] == "1"


async def test_error_lookup_is_scoped_to_selected_account(settings, purchase_error):
    _, _, _, _, details = purchase_error
    journal = Journal(settings.runtime_dir / "another-account")
    ui = SimpleNamespace(snapshot=AsyncMock())
    try:
        with pytest.raises(ValueError, match="tidak ditemukan pada akun ini"):
            await reconcile(ui, journal, details["error_id"])
        ui.snapshot.assert_not_awaited()
    finally:
        journal.close()


async def test_agent_reconcile_uses_error_id(settings, purchase_error, monkeypatch, capsys):
    import app.modules.worker.runner as app

    journal, _action, other, after, details = purchase_error
    ui = SimpleNamespace(
        snapshot=AsyncMock(return_value=after), job_click=AsyncMock(), buy=AsyncMock()
    )
    context = AsyncMock()
    context.__aenter__.return_value = ui
    monkeypatch.setattr(app, "HttpUI", lambda *args: context)
    await app.run_app(
        settings.model_copy(update={"env": "local"}), "reconcile", error_id=details["error_id"]
    )
    assert [row["id"] for row in journal.unresolved()] == [other]
    assert "Total aksi belum pasti di seluruh akun ini: 1." in capsys.readouterr().out
    ui.job_click.assert_not_awaited()
    ui.buy.assert_not_awaited()


async def test_action_id_selects_legacy_action_without_error_record(purchase_error):
    journal, action, other, after, _details = purchase_error
    await reconcile(
        SimpleNamespace(snapshot=AsyncMock(return_value=after)), journal, action_id=action
    )
    assert [row["id"] for row in journal.unresolved()] == [other]
    assert journal.profit()["pengeluaran"] == "1"


@pytest.mark.parametrize("action_id", [0, -1, 999999])
async def test_invalid_action_id_leaves_ledger_unchanged(purchase_error, action_id):
    journal, action, other, _after, _details = purchase_error
    ui = SimpleNamespace(snapshot=AsyncMock())
    with pytest.raises(ValueError, match=r"ID aksi|tidak ditemukan"):
        await reconcile(ui, journal, action_id=action_id)
    ui.snapshot.assert_not_awaited()
    assert [row["id"] for row in journal.unresolved()] == [action, other]


def test_cli_passes_action_id_and_rejects_two_selectors(settings, monkeypatch):
    import app.cli as cli
    import app.modules.worker.runner as app

    monkeypatch.setattr(
        cli, "load_settings", lambda path: settings.model_copy(update={"env": "local"})
    )
    run_app = AsyncMock()
    monkeypatch.setattr(app, "run_app", run_app)
    assert cli.main(["reconcile", "--action-id", "3095"]) == 0
    assert run_app.call_args.kwargs == {"action_id": 3095}
    with pytest.raises(SystemExit):
        cli.parser().parse_args(
            ["reconcile", "--action-id", "3095", "--error-id", "OJL-012345ABCDEF"]
        )


@pytest.mark.parametrize("original_status", ["pending", "uncertain"])
def test_cli_skip_preserves_evidence_and_other_actions_without_game_requests(
    settings, state, monkeypatch, capsys, original_status
):
    import app.cli as cli
    import app.modules.worker.runner as app
    from app.core.models import ROOT

    monkeypatch.setattr(cli, "load_settings", lambda path: settings)
    run_app = AsyncMock()
    monkeypatch.setattr(app, "run_app", run_app)
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        before = state.model_copy(update={"phase": "complete", "trip_id": "old-trip"})
        action = journal.begin(run, "complete", before, {"label": "Sampai! Terima ongkos"})
        if original_status == "uncertain":
            journal.settle(action, False)
        other = journal.begin(run, "purchase", state, {"resource": "fuel"})
        saved = dict(journal.db.execute("SELECT * FROM actions WHERE id=?", (action,)).fetchone())
        args = [
            "--env-file",
            str(ROOT / ".env.testing"),
            "reconcile",
            "--action-id",
            str(action),
            "--skip",
        ]
        assert cli.main(args) == 0
        result = dict(journal.db.execute("SELECT * FROM actions WHERE id=?", (action,)).fetchone())
        assert result == {**saved, "status": "skipped"}
        assert [row["id"] for row in journal.unresolved()] == [other]
        assert journal.profit()["pendapatan_ojol"] == "0"
        assert journal.profit()["pengeluaran"] == "0"
        assert cli.main(args) == 0
        events = journal.db.execute(
            "SELECT data FROM events WHERE event='aksi_dilewati_operator'"
        ).fetchall()
        assert len(events) == 1
        assert json.loads(events[0][0])["original_status"] == original_status
        assert "Sisa aksi belum pasti: 1." in capsys.readouterr().out
        run_app.assert_not_awaited()
        assert not (settings.runtime_dir / "STOP").exists()
    finally:
        journal.close()


def test_skipped_claim_unblocks_next_run_without_fabricating_payout(settings, state):
    journal = Journal(settings.runtime_dir)
    try:
        run = journal.start(settings)
        action = journal.begin(run, "complete", state, {})
        journal.settle(action, False)
        journal.skip(action)
        assert journal.start(settings) > run
        assert journal.profit()["pendapatan_ojol"] == "0"
    finally:
        journal.close()


@pytest.mark.parametrize("status", ["verified", "handed_off", "closed_idle", "rejected"])
def test_skip_cannot_rewrite_previously_resolved_action(settings, state, status):
    journal = Journal(settings.runtime_dir)
    try:
        action = journal.begin(journal.start(settings), "search", state, {})
        with journal.db:
            journal.db.execute("UPDATE actions SET status=? WHERE id=?", (status, action))
        with pytest.raises(ValueError, match="sudah berstatus"):
            journal.skip(action)
        assert journal.history()["actions"][0]["status"] == status
    finally:
        journal.close()


def test_skip_requires_action_id_and_respects_worker_lock(settings, state, monkeypatch, capsys):
    import app.cli as cli
    from app.core.models import ROOT

    monkeypatch.setattr(cli, "load_settings", lambda path: settings)
    base = ["--env-file", str(ROOT / ".env.testing"), "reconcile"]
    assert cli.main([*base, "--skip"]) == 2
    assert "--skip memerlukan --action-id" in capsys.readouterr().err
    journal = Journal(settings.runtime_dir)
    try:
        action = journal.begin(journal.start(settings), "complete", state, {})
        with cli.exclusive_lock(settings.runtime_dir):
            assert cli.main([*base, "--action-id", str(action), "--skip"]) == 2
        assert journal.unresolved()[0]["id"] == action
        assert not (settings.runtime_dir / "STOP").exists()
    finally:
        journal.close()
