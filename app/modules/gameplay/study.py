"""Per-account study choices and one daily study/quiz attempt per facility mode."""

import ast
import contextlib
import json
import random
import re
import time
from datetime import timedelta
from uuid import uuid4

from app.core.exceptions import StopRequested
from app.core.models import AUTO_SUBJECT, STUDY_LABELS, SUBJECTS, now
from app.core.storage import write_private
from app.integrations.kampung.http_api import HttpCoreError, timestamp
from app.modules.worker.settings import auto_flags, set_auto_flag


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
    return next_info.get("library") is False


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

    from app.core.exceptions import HttpCoreError
    from app.core.formatting import parse_api_timestamp as timestamp
    from app.modules.ledger.reconciliation import wait_until_resolved
    from app.modules.notifications.service import queue_error
    from app.modules.worker.settings import auto_flags

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
                skill = next(
                    (t for t in status["tracks"] if isinstance(t, dict) and t.get("id") == track),
                    None,
                )
                payload = {
                    "mode": mode,
                    "track": track,
                    "facility_id": facility["id"],
                    "visit_id": visit_id,
                    "shop": facility.get("title"),
                    "resource": mode,
                    "next_at": facility.get("nextAt"),
                    **(
                        {"skill_level": skill["level"]}
                        if skill and isinstance(skill.get("level"), int)
                        else {}
                    ),
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
                    **(
                        {"skill_level": skill["level"]}
                        if isinstance(skill.get("level"), int)
                        else {}
                    ),
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
            after_skill = next(
                (
                    t
                    for t in cached_skills(c.settings.runtime_dir)
                    if isinstance(t, dict) and t.get("id") == track
                ),
                None,
            )
            if (
                after_skill
                and isinstance(after_skill.get("level"), int)
                and after_skill["level"] != payload.get("skill_level")
            ):
                payload["skill_level"] = after_skill["level"]
                with c.journal.db:
                    c.journal.db.execute(
                        "UPDATE actions SET payload=? WHERE id=?", (json.dumps(payload), action)
                    )
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
            **({"skill_level": payload["skill_level"]} if "skill_level" in payload else {}),
            **(
                {key: result[key] for key in ("benar", "total", "bonus")}
                if kind == "study_quiz"
                else {}
            ),
        )
        return True
    return False


KURSUS_SETTINGS_FILE = "kursus-settings.json"
KURSUS_STATUS_FILE = "kursus-status.json"


def kursus_subject(directory) -> str | None:
    path = directory / KURSUS_SETTINGS_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return None
    track = data.get("track") if isinstance(data, dict) else None
    return track if track in SUBJECTS else None


def set_kursus_subject(directory, track: str) -> None:
    if track not in SUBJECTS:
        raise ValueError("Pilih bidang kursus yang valid (wajib memilih salah satu bidang).")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / KURSUS_SETTINGS_FILE, {"track": track})


def kursus_cost_info(skills: list, track: str | None) -> dict | None:
    if not track or track not in SUBJECTS:
        return None
    info = next((t for t in (skills or []) if isinstance(t, dict) and t.get("id") == track), None)
    if not isinstance(info, dict):
        return {"track": track, "label": SUBJECTS[track], "cost_milli": None}
    next_info = info.get("next") if isinstance(info.get("next"), dict) else None
    pending = info.get("pending") if isinstance(info.get("pending"), dict) else None
    return {
        "track": track,
        "label": SUBJECTS[track],
        "level": info.get("level"),
        "next_level": next_info.get("level") if next_info else None,
        "cost_milli": int(next_info["courseMilli"]) if next_info and next_info.get("courseMilli") is not None else None,
        "hours": next_info.get("hours") if next_info else None,
        "pending": bool(pending),
        "ready_at": pending.get("readyAt") if pending else None,
        "rush_milli": pending.get("rushMilli") if pending else None,
        "is_max": next_info is None,
    }


def _save_kursus_status(directory, payload: dict) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_private(directory / KURSUS_STATUS_FILE, {**payload, "updated_at": now().isoformat()})
    except OSError:
        pass


async def run_kursus(c) -> bool:
    """Take one paid skill course (/api/skills) when Auto Kursus is enabled and eligible."""
    if not hasattr(c.ui, "take_skill_course") or not hasattr(c.ui, "game_skill_state"):
        return False
    flags = auto_flags(c.settings.runtime_dir)
    if not flags.get("kursus"):
        return False
    track = kursus_subject(c.settings.runtime_dir)
    if not track:
        return False
    if time.monotonic() < getattr(c, "kursus_retry_at", 0):
        return False

    c.stage = "study.kursus"
    try:
        balance_milli, skill = await c.ui.game_skill_state()
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.kursus_retry_at = time.monotonic() + 120
        return False

    tracks = skill.get("tracks") or []
    if isinstance(tracks, list) and tracks:
        save_skills(c.settings.runtime_dir, tracks)

    track_info = next((t for t in tracks if isinstance(t, dict) and t.get("id") == track), None)
    if not isinstance(track_info, dict) or not isinstance(track_info.get("next"), dict):
        _save_kursus_status(
            c.settings.runtime_dir,
            {"track": track, "label": SUBJECTS[track], "state": "Maksimal"},
        )
        set_auto_flag(c.settings.runtime_dir, "kursus", False)
        c.record_event("kursus", f"Kursus {SUBJECTS[track]} sudah level maksimal; Auto Kursus dimatikan.")
        return False

    pending = track_info.get("pending")
    if isinstance(pending, dict):
        wait_s = 300.0
        if isinstance(pending.get("readyAt"), str):
            with contextlib.suppress(ValueError, TypeError):
                wait_s = max(10.0, (timestamp(pending["readyAt"]) - now()).total_seconds())
        _save_kursus_status(
            c.settings.runtime_dir,
            {
                "track": track,
                "label": SUBJECTS[track],
                "state": "Pending",
                "ready_at": pending.get("readyAt"),
            },
        )
        c.kursus_retry_at = time.monotonic() + min(wait_s, 3600.0) + random.uniform(2.0, 10.0)  # noqa: S311
        return False

    course = skill.get("course") or {}
    used = int(course.get("usedToday") or 0)
    daily_max = int(course.get("dailyMax") or 3)
    if used >= daily_max:
        _save_kursus_status(
            c.settings.runtime_dir,
            {"track": track, "label": SUBJECTS[track], "state": f"Kuota habis ({used}/{daily_max})"},
        )
        c.kursus_retry_at = time.monotonic() + 1800 + random.uniform(5.0, 30.0)  # noqa: S311
        return False

    next_info = track_info["next"]
    cost_milli = int(next_info.get("courseMilli") or course.get("priceMilli") or 5000)
    if int(balance_milli or 0) < cost_milli:
        _save_kursus_status(
            c.settings.runtime_dir,
            {
                "track": track,
                "label": SUBJECTS[track],
                "state": f"Saldo kurang (butuh {cost_milli / 1000:g} koin)",
                "cost_milli": cost_milli,
            },
        )
        c.kursus_retry_at = time.monotonic() + 300
        return False

    try:
        res = await c.ui.take_skill_course(track)
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.kursus_retry_at = time.monotonic() + 120
        return False

    ready_at = res.get("readyAt") if isinstance(res, dict) else None
    _save_kursus_status(
        c.settings.runtime_dir,
        {
            "track": track,
            "label": SUBJECTS[track],
            "state": "Berjalan",
            "level": track_info.get("level"),
            "next_level": next_info.get("level"),
            "cost_milli": cost_milli,
            "ready_at": ready_at,
        },
    )
    c.record_event(
        "kursus",
        f"🎓 Kursus {SUBJECTS[track]} (Lv {next_info.get('level')}) dimulai · Biaya {cost_milli / 1000:g} koin",
    )
    c.kursus_retry_at = time.monotonic() + 5 + random.uniform(2.0, 5.0)  # noqa: S311
    return True
