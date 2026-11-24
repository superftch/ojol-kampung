"""Per-account study choices and one daily study/quiz attempt per facility mode."""

import ast
import json
import re
import time
from datetime import timedelta
from uuid import uuid4

from .models import AUTO_SUBJECT, STUDY_LABELS, SUBJECTS, StopRequested, now
from .storage import write_private


def pick_auto_track(tracks, mode, study_tracks=None):
    if not isinstance(tracks, list):
        return None
    candidates = []
    for t in tracks:
        if not isinstance(t, dict):
            continue
        track_id = t.get("id")
        if track_id not in SUBJECTS:
            continue
        if study_tracks is not None and track_id not in study_tracks:
            continue
        if is_track_max(t, mode):
            continue
        if t.get("pending"):
            continue
        candidates.append(t)
    if not candidates:
        return None
    subject_order = list(SUBJECTS.keys())
    candidates.sort(
        key=lambda x: (
            -(x.get("level", 0) if isinstance(x.get("level"), (int, float)) else 0),
            subject_order.index(x["id"]) if x["id"] in subject_order else 999,
        )
    )
    return candidates[0]["id"]


def is_track_max(track_data, mode):
    if not isinstance(track_data, dict):
        return False
    level = track_data.get("level", 0)
    if isinstance(level, (int, float)) and level >= 5:
        return True
    next_info = track_data.get("next")
    if not next_info:
        return True
    next_level = next_info.get("level")
    if isinstance(next_level, (int, float)) and next_level > 5:
        return True
    if next_info.get("library") is False:
        return True
    return False


def save_skills(directory, tracks):
    if not isinstance(tracks, list):
        return
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = directory / f"game-skills-{uuid4().hex}.json"
    try:
        write_private(temporary, tracks)
        temporary.replace(directory / "game-skills.json")
    finally:
        temporary.unlink(missing_ok=True)


def cached_skills(directory):
    try:
        data = json.loads((directory / "game-skills.json").read_text())
        if isinstance(data, list):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return []


def subjects(directory):
    path = directory / "study-settings.json"
    saved = json.loads(path.read_text()) if path.is_file() else {}
    if not isinstance(saved, dict) or any(
        mode not in STUDY_LABELS or (track not in SUBJECTS and track != AUTO_SUBJECT)
        for mode, track in saved.items()
    ):
        raise ValueError("Pilihan bidang belajar akun tidak valid.")
    return {mode: saved.get(mode) for mode in STUDY_LABELS}


def set_subject(directory, mode, track, skills=None):
    if mode not in STUDY_LABELS or (track not in SUBJECTS and track != AUTO_SUBJECT):
        raise ValueError("Pilihan bidang belajar tidak valid.")
    if track != AUTO_SUBJECT:
        if skills is None:
            skills = cached_skills(directory)
        if skills:
            track_info = next(
                (t for t in skills if isinstance(t, dict) and t.get("id") == track), None
            )
            if track_info and is_track_max(track_info, mode):
                raise ValueError("Bidang belajar sudah mencapai batas maksimal.")
    saved = {key: value for key, value in subjects(directory).items() if value is not None}
    saved[mode] = track
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / "study-settings.json", saved)


def extract_quiz_bank(source):
    for match in re.finditer(r"JSON\.parse\(\s*('(?:\\.|[^'\\])*')\s*\)", source):
        if '"bonus_sessions"' not in match[1] or '"tracks"' not in match[1]:
            continue
        data = json.loads(ast.literal_eval(match[1]))
        if isinstance(data.get("tracks"), dict) and isinstance(data.get("facilities"), dict):
            return data["tracks"]
    return {}


def quiz_answers(quiz, bank):
    track = quiz["track"]["id"]
    rows = bank.get(track, [])
    known = {}
    for row in rows:
        question, answer = row["q"], row["a"]
        if not isinstance(question, str) or not isinstance(answer, str):
            raise ValueError("Bank soal belajar tidak valid")
        if question in known and known[question] != answer:
            raise ValueError("Jawaban bank soal belajar ambigu")
        known[question] = answer
    questions = quiz["soal"]
    if not isinstance(questions, list) or not 1 <= len(questions) <= 10:
        raise ValueError("Jumlah soal belajar tidak valid")
    answers = []
    for row in questions:
        options = row["options"]
        answer = known.get(row["q"])
        if (
            answer is None
            or not isinstance(options, list)
            or not 2 <= len(options) <= 4
            or any(not isinstance(option, str) for option in options)
            or options.count(answer) != 1
        ):
            raise ValueError("Soal belajar belum cocok dengan bacaan client; jawaban tidak ditebak")
        answers.append(options.index(answer))
    return answers


async def run_learning(controller):
    from decimal import Decimal

    from .auto_settings import auto_flags
    from .formatting import parse_api_timestamp as timestamp
    from .models import HttpCoreError
    from .notices import queue_error
    from .reconciliation import wait_until_resolved

    c = controller
    flags = auto_flags(c.settings.runtime_dir)
    choices = subjects(c.settings.runtime_dir)
    for mode in STUDY_LABELS:
        if not flags[mode] or not choices[mode] or time.monotonic() < c.study_retry_at.get(mode, 0):
            continue
        c.check_cancel()
        c.stage = f"study.preview.{mode}"
        try:
            status = await c.ui.study_status(mode)
            facility, quiz = status["facility"], status["quiz"]
            track = choices[mode]
            latest = c.journal.db.execute(
                "SELECT * FROM actions WHERE kind='study' AND status<>'rejected' "
                "AND json_extract(payload, '$.mode')=? ORDER BY id DESC LIMIT 1",
                (mode,),
            ).fetchone()
            previous = json.loads(latest["payload"]) if latest else None
            retry_after = timestamp(previous["retry_after"]) if previous else None
            recent = retry_after is not None and retry_after > c.state.observed_at
            if recent and previous is not None:
                track = previous["track"]
                if (
                    latest["status"] == "verified"
                    and quiz.get("available") is False
                    and quiz.get("reason") != "selesai"
                ):
                    c.study_retry_at[mode] = time.monotonic() + 10
                    continue
            quiz_due = quiz.get("available") is True and (
                quiz.get("track", {}).get("id") == track
                or choices[mode] == AUTO_SUBJECT
                or (previous and quiz.get("track", {}).get("id") == previous.get("track"))
            )
            if quiz_due:
                track = quiz.get("track", {}).get("id") or track
                visit_id = quiz["visitId"]
                attempted = c.journal.db.execute(
                    "SELECT id FROM actions WHERE kind='study_quiz' AND status<>'rejected' "
                    "AND json_extract(payload, '$.visit_id')=? LIMIT 1",
                    (visit_id,),
                ).fetchone()
                if attempted:
                    if recent:
                        c.study_retry_at[mode] = time.monotonic() + 300
                        continue
                    quiz_due = False
            if quiz_due:
                await c.wait(6)
                kind = "study_quiz"
                payload = {
                    "mode": mode,
                    "track": track,
                    "facility_id": facility["id"],
                    "visit_id": visit_id,
                    "shop": facility.get("title"),
                    "resource": mode,
                    "next_at": facility.get("nextAt"),
                }
                price = Decimal(0)
            else:
                next_at = timestamp(facility["nextAt"]) if facility.get("nextAt") else None
                due = max((date for date in (retry_after, next_at) if date), default=None)
                if due and due > c.state.observed_at:
                    c.study_retry_at[mode] = (
                        time.monotonic() + (due - c.state.observed_at).total_seconds()
                    )
                    continue
                service = facility["service"]
                price = Decimal(service["priceMilli"]) / 1000
                if choices[mode] == AUTO_SUBJECT:
                    track = pick_auto_track(status["tracks"], mode, service.get("studyTracks"))
                    if not track:
                        c.study_retry_at[mode] = time.monotonic() + 300
                        continue
                skill = next((t for t in status["tracks"] if t["id"] == track), None)
                if (
                    not skill
                    or is_track_max(skill, mode)
                    or skill.get("pending")
                    or service.get("open") is not True
                    or (
                        service.get("studyTracks") is not None
                        and track not in service["studyTracks"]
                    )
                    or (c.settings.max_spend is not None and c.spent + price > c.settings.max_spend)
                    or (
                        price > Decimal(0)
                        and c.state.wallet - price < max(Decimal(20), c.settings.min_balance)
                    )
                ):
                    c.study_retry_at[mode] = time.monotonic() + 300
                    continue
                kind = "study"
                payload = {
                    "mode": mode,
                    "track": track,
                    "facility_id": facility["id"],
                    "before_visit_id": quiz.get("visitId"),
                    "resource": mode,
                    "shop": facility["title"],
                    "product": {"name": service["label"], "price": str(price)},
                    "retry_after": (c.state.observed_at + timedelta(days=1)).isoformat(),
                    **c.ui.prepare_action("study"),
                }
        except HttpCoreError as exc:
            if exc.category == "auth":
                raise
            queue_error(c.settings, exc, c.stage, stop_worker=False)
            c.study_retry_at[mode] = time.monotonic() + 300
            continue
        c.check_cancel()
        action = c.journal.begin(c.run_id, kind, c.state, payload)
        c.last_action = {"action_id": action, "kind": kind, "mode": mode, "track": track}
        c.stage = f"study.{kind}.{mode}"
        c.spent += price
        try:
            if kind == "study":
                result = await c.ui.study_start(
                    mode, track, price, c.state.wallet, c.settings.min_balance
                )
            else:
                result = await c.ui.study_quiz(mode, payload["visit_id"], track)
            payload["receipt"] = result
            with c.journal.db:
                c.journal.db.execute(
                    "UPDATE actions SET payload=? WHERE id=?", (json.dumps(payload), action)
                )
            after = await c.read_snapshot()
        except (HttpCoreError, StopRequested) as exc:
            if isinstance(exc, HttpCoreError) and exc.category in {
                "rejected",
                "auto_disabled",
                "sleeping",
            }:
                c.journal.reject(action)
                c.spent -= price
                c.study_retry_at[mode] = time.monotonic() + 300
                return False
            c.journal.settle(action, False)
            if isinstance(exc, HttpCoreError) and exc.category in {"uncertain", "transport"}:
                c.state = await wait_until_resolved(c.ui, c.journal, c.settings)
                c.snapshot_received_at = now().isoformat()
                c.snapshot_read_at = time.monotonic()
                c.report("rekonsiliasi_selesai", action=kind, mode=mode)
                return True
            raise
        c.journal.settle(action, True, after)
        c.report(
            "belajar_dimulai" if kind == "study" else "kuis_belajar_selesai",
            mode=mode,
            track=SUBJECTS[track],
            cost=str(price),
            **(
                {key: result[key] for key in ("benar", "total", "bonus")}
                if kind == "study_quiz"
                else {}
            ),
        )
        return True
    return False
