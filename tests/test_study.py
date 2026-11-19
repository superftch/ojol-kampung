import json
from contextlib import closing
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ojol.auto_settings import AUTO_LABELS, auto_flags, set_auto_flag
from ojol.controller import Controller, StopRequested
from ojol.http_api import HttpCoreError
from ojol.journal import Journal
from ojol.reconciliation import reconcile
from ojol.study import extract_quiz_bank, run_learning, set_subject, subjects


def study_ui(state, mode="kuliah", *, quiz_available=False):
    identifier, visit_id = str(uuid4()), str(uuid4())
    request_id = str(uuid4())
    price = Decimal(0 if mode == "perpus" else 4)
    status = {
        "facility": {
            "id": identifier,
            "title": "Fasilitas uji",
            "nextAt": None,
            "service": {
                "label": "Belajar",
                "priceMilli": int(price * 1000),
                "open": True,
                "studyTracks": None,
            },
        },
        "quiz": (
            {"available": True, "visitId": visit_id, "track": {"id": "administrasi"}}
            if quiz_available
            else {"available": False, "reason": "belum"}
        ),
        "tracks": [{"id": "administrasi", "next": {"library": True}, "pending": None}],
    }
    receipt = {
        "id": visit_id,
        "requestId": request_id,
        "projectId": identifier,
        "priceMilli": int(price * 1000),
    }
    ui = SimpleNamespace(
        study_status=AsyncMock(return_value=status),
        prepare_action=lambda kind: {"request_id": request_id},
        study_start=AsyncMock(return_value=receipt),
        study_quiz=AsyncMock(return_value={"benar": 3, "total": 3, "bonus": 1}),
        snapshot=AsyncMock(return_value=state.model_copy(update={"wallet": state.wallet - price})),
    )
    return ui, status, receipt


def test_learning_defaults_off_and_choices_are_separate(settings):
    assert not auto_flags(settings.runtime_dir)["perpus"]
    assert not auto_flags(settings.runtime_dir)["kuliah"]
    set_subject(settings.runtime_dir, "perpus", "administrasi")
    set_subject(settings.runtime_dir, "kuliah", "boga")
    assert subjects(settings.runtime_dir) == {"perpus": "administrasi", "kuliah": "boga"}
    assert not auto_flags(settings.runtime_dir)["kuliah"]
    with pytest.raises(ValueError):
        set_subject(settings.runtime_dir, "kuliah", "unknown")


@pytest.mark.parametrize("mode", ["perpus", "kuliah"])
async def test_study_books_only_paid_receipt_and_survives_restart_cooldown(settings, state, mode):
    set_subject(settings.runtime_dir, mode, "administrasi")
    set_auto_flag(settings.runtime_dir, mode, True)
    ui, status, _ = study_ui(state, mode)
    with closing(Journal(settings.runtime_dir)) as journal:
        run = journal.start(settings)
        c = Controller(ui, settings, journal, run)
        c.state = state
        assert await run_learning(c)
        ui.study_start.assert_awaited_once()
        assert Decimal(journal.profit()["pengeluaran"]) == (0 if mode == "perpus" else 4)
        status["facility"]["nextAt"] = (state.observed_at + timedelta(days=1)).isoformat()
        restarted = Controller(ui, settings, journal, journal.start(settings))
        restarted.state = c.state
        assert not await run_learning(restarted)
        ui.study_start.assert_awaited_once()
        assert not journal.unresolved()


async def test_quiz_resumes_after_restart_and_never_rebuys_or_submits_twice(
    settings, state, monkeypatch
):
    set_subject(settings.runtime_dir, "perpus", "administrasi")
    set_auto_flag(settings.runtime_dir, "perpus", True)
    ui, status, _ = study_ui(state, "perpus", quiz_available=True)
    status["facility"]["nextAt"] = (state.observed_at + timedelta(days=1)).isoformat()
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        c.wait = AsyncMock()
        assert await run_learning(c)
        c.wait.assert_awaited_once_with(6)
        ui.study_start.assert_not_awaited()
        ui.study_quiz.assert_awaited_once()
        restarted = Controller(ui, settings, journal, journal.start(settings))
        restarted.state = state
        assert not await run_learning(restarted)
        ui.study_start.assert_not_awaited()
        ui.study_quiz.assert_awaited_once()


@pytest.mark.parametrize("reason", ["off", "budget", "pending", "advanced", "closed", "floor"])
async def test_learning_respects_opt_in_budget_and_skill_guards(settings, state, reason):
    set_subject(settings.runtime_dir, "kuliah", "administrasi")
    set_auto_flag(settings.runtime_dir, "kuliah", reason != "off")
    ui, status, receipt = study_ui(state)
    if reason == "budget":
        settings = settings.model_copy(update={"max_spend": Decimal(3)})
    elif reason == "pending":
        status["tracks"][0]["pending"] = {"level": 3}
    elif reason == "advanced":
        status["tracks"][0]["next"]["library"] = False
    elif reason == "closed":
        status["facility"]["service"]["open"] = False
    elif reason == "floor":
        state = state.model_copy(update={"wallet": Decimal(23)})
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        assert not await run_learning(c)
        assert not journal.history()["actions"]
        ui.study_start.assert_not_awaited()
        ui.study_quiz.assert_not_awaited()


async def test_lost_study_response_reconciles_visit_once_without_recharging(settings, state):
    set_subject(settings.runtime_dir, "kuliah", "administrasi")
    set_auto_flag(settings.runtime_dir, "kuliah", True)
    ui, status, receipt = study_ui(state)

    async def start(*args):
        status["quiz"].update(available=True, visitId=receipt["id"], track={"id": "administrasi"})
        status["facility"]["nextAt"] = (state.observed_at + timedelta(days=1)).isoformat()
        raise HttpCoreError("fixture lost response", category="uncertain")

    ui.study_start.side_effect = start
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        assert await run_learning(c)
        ui.study_start.assert_awaited_once()
        assert not journal.unresolved()
        assert Decimal(journal.profit()["pengeluaran"]) == 4
        assert c.spent == 4
        await reconcile(ui, journal)
        assert Decimal(journal.profit()["pengeluaran"]) == 4


async def test_lost_quiz_response_reconciles_completion_without_reposting(settings, state):
    set_subject(settings.runtime_dir, "perpus", "administrasi")
    set_auto_flag(settings.runtime_dir, "perpus", True)
    ui, status, _ = study_ui(state, "perpus", quiz_available=True)
    status["facility"]["nextAt"] = (state.observed_at + timedelta(days=1)).isoformat()

    async def submit(*args):
        status["quiz"].update(available=False, reason="selesai")
        raise HttpCoreError("fixture lost response", category="uncertain")

    ui.study_quiz.side_effect = submit
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        c.wait = AsyncMock()
        assert await run_learning(c)
        assert not journal.unresolved()
        ui.study_quiz.assert_awaited_once()
        ui.study_start.assert_not_awaited()


def test_bank_extraction_reads_shipped_client_json():
    bank = {
        "facilities": {"perpustakaan-desa": {"bonus_sessions": 1}},
        "tracks": {"administrasi": [{"q": "Notulen?", "a": "Catatan"}]},
    }
    source = "exports=JSON.parse(" + repr(json.dumps(bank)) + ")"
    assert extract_quiz_bank(source) == bank["tracks"]


async def test_learning_runs_without_ojol_and_completes_visit_and_quiz(settings, state):
    for key in AUTO_LABELS:
        set_auto_flag(settings.runtime_dir, key, key == "perpus")
    set_subject(settings.runtime_dir, "perpus", "administrasi")
    ui, status, receipt = study_ui(state, "perpus")

    async def start(*args):
        status["quiz"].update(available=True, visitId=receipt["id"], track={"id": "administrasi"})
        status["facility"]["nextAt"] = (state.observed_at + timedelta(days=1)).isoformat()
        return receipt

    async def submit(*args):
        status["quiz"].update(available=False, reason="selesai")
        return {"benar": 3, "total": 3, "bonus": 1}

    ui.study_start.side_effect = start
    ui.study_quiz.side_effect = submit
    ui.snapshot.side_effect = [state, state, state, state, StopRequested("fixture done")]
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.wait = AsyncMock()
        with pytest.raises(StopRequested, match="fixture done"):
            await c.run()
        ui.study_start.assert_awaited_once()
        ui.study_quiz.assert_awaited_once()
        c.wait.assert_awaited_once_with(6)
        assert {row["kind"] for row in journal.history()["actions"]} == {"study", "study_quiz"}
        assert not journal.unresolved()


async def test_learning_can_start_next_day_after_persisted_cooldown(settings, state):
    set_subject(settings.runtime_dir, "kuliah", "administrasi")
    set_auto_flag(settings.runtime_dir, "kuliah", True)
    ui, status, _ = study_ui(state)
    with closing(Journal(settings.runtime_dir)) as journal:
        c = Controller(ui, settings, journal, journal.start(settings))
        c.state = state
        assert await run_learning(c)
        tomorrow = state.model_copy(
            update={"observed_at": state.observed_at + timedelta(days=1, seconds=1)}
        )
        ui.snapshot.return_value = tomorrow.model_copy(
            update={"wallet": tomorrow.wallet - Decimal(4)}
        )
        restarted = Controller(ui, settings, journal, journal.start(settings))
        restarted.state = tomorrow
        assert await run_learning(restarted)
        assert ui.study_start.await_count == 2
        assert Decimal(journal.profit()["pengeluaran"]) == 8
