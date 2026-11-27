"""Random daily offline jitter breaks (1h & 30m, max 2x each per day) for Auto Ojol."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.models import now
from app.core.storage import status_record, status_timestamp, write_private

WIB = ZoneInfo("Asia/Jakarta")
OJOL_JITTER_FILE = "ojol-jitter.json"

MAX_60M_PER_DAY = 2
MAX_30M_PER_DAY = 2
JITTER_DURATIONS: dict[str, int] = {
    "60m": 3600,
    "30m": 1800,
}
MIN_WORK_INTERVAL_SECONDS = 45 * 60
MAX_WORK_INTERVAL_SECONDS = 120 * 60


def jitter_label(kind: str) -> str:
    """Return human-readable Indonesian duration label for a jitter kind."""
    return "1 jam" if kind == "60m" else "30 menit"


def _empty_state(today: str) -> dict[str, Any]:
    return {
        "date": today,
        "count_60m": 0,
        "count_30m": 0,
        "next_trigger_at": None,
        "active_kind": None,
        "active_started_at": None,
        "active_until": None,
    }


def _schedule_next_trigger(moment_wib: datetime, rng: random.Random | random.Random) -> str:
    delay = rng.uniform(MIN_WORK_INTERVAL_SECONDS, MAX_WORK_INTERVAL_SECONDS)
    return (moment_wib + timedelta(seconds=delay)).isoformat()


def _remaining_choices(state: dict[str, Any]) -> list[str]:
    rem_60 = max(0, MAX_60M_PER_DAY - int(state.get("count_60m") or 0))
    rem_30 = max(0, MAX_30M_PER_DAY - int(state.get("count_30m") or 0))
    return ["60m"] * rem_60 + ["30m"] * rem_30


def load_ojol_jitter_state(
    directory: Path, *, current_time: datetime | None = None
) -> dict[str, Any]:
    """Load today's (WIB) ojol jitter state, resetting counters on a new day."""
    moment_wib = (current_time or now()).astimezone(WIB)
    today = moment_wib.date().isoformat()
    raw, _ = status_record(directory / OJOL_JITTER_FILE)
    if not raw:
        return _empty_state(today)

    active_until = status_timestamp(raw.get("active_until"))
    is_still_active = active_until is not None and active_until > moment_wib

    if raw.get("date") != today:
        fresh = _empty_state(today)
        if is_still_active and raw.get("active_kind") in JITTER_DURATIONS:
            fresh["active_kind"] = raw["active_kind"]
            fresh["active_started_at"] = raw.get("active_started_at")
            fresh["active_until"] = raw.get("active_until")
        return fresh

    return {
        "date": today,
        "count_60m": max(0, int(raw.get("count_60m") or 0)),
        "count_30m": max(0, int(raw.get("count_30m") or 0)),
        "next_trigger_at": raw.get("next_trigger_at"),
        "active_kind": raw.get("active_kind") if is_still_active else None,
        "active_started_at": raw.get("active_started_at") if is_still_active else None,
        "active_until": raw.get("active_until") if is_still_active else None,
    }


def save_ojol_jitter_state(directory: Path, state: dict[str, Any]) -> None:
    """Persist ojol jitter state privately to runtime_dir."""
    directory.mkdir(parents=True, exist_ok=True)
    write_private(directory / OJOL_JITTER_FILE, state)


def active_ojol_jitter(
    directory: Path, *, current_time: datetime | None = None
) -> dict[str, Any] | None:
    """Return active jitter break info if currently in an offline jitter window, else None."""
    moment_wib = (current_time or now()).astimezone(WIB)
    state = load_ojol_jitter_state(directory, current_time=moment_wib)
    kind = state.get("active_kind")
    until = status_timestamp(state.get("active_until"))
    if kind in JITTER_DURATIONS and until is not None and until > moment_wib:
        remaining = max(0.0, (until - moment_wib).total_seconds())
        return {
            "kind": kind,
            "label": jitter_label(kind),
            "started_at": state.get("active_started_at"),
            "until": until,
            "remaining_seconds": remaining,
            "count_60m": state["count_60m"],
            "count_30m": state["count_30m"],
        }
    return None


def is_ojol_jitter_active(directory: Path, *, current_time: datetime | None = None) -> bool:
    """Return True if the account is currently in an ojol offline jitter break."""
    return active_ojol_jitter(directory, current_time=current_time) is not None


def maybe_start_ojol_jitter(
    directory: Path,
    *,
    current_time: datetime | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Schedule or start a random ojol jitter break if due and daily quota remains."""
    moment_wib = (current_time or now()).astimezone(WIB)
    gen = rng or random.SystemRandom()
    state = load_ojol_jitter_state(directory, current_time=moment_wib)

    # Already in an active break
    existing = active_ojol_jitter(directory, current_time=moment_wib)
    if existing is not None:
        return existing

    choices = _remaining_choices(state)
    if not choices:
        if state.get("next_trigger_at") is not None or state.get("active_until") is not None:
            state["next_trigger_at"] = None
            state["active_kind"] = None
            state["active_started_at"] = None
            state["active_until"] = None
            save_ojol_jitter_state(directory, state)
        return None

    trigger_at = status_timestamp(state.get("next_trigger_at"))
    if trigger_at is None:
        state["next_trigger_at"] = _schedule_next_trigger(moment_wib, gen)
        save_ojol_jitter_state(directory, state)
        return None

    if moment_wib < trigger_at:
        return None

    kind = gen.choice(choices)
    duration = JITTER_DURATIONS[kind]
    until = moment_wib + timedelta(seconds=duration)
    if kind == "60m":
        state["count_60m"] = int(state.get("count_60m") or 0) + 1
    else:
        state["count_30m"] = int(state.get("count_30m") or 0) + 1
    state["active_kind"] = kind
    state["active_started_at"] = moment_wib.isoformat()
    state["active_until"] = until.isoformat()
    state["next_trigger_at"] = None
    save_ojol_jitter_state(directory, state)

    return {
        "kind": kind,
        "label": jitter_label(kind),
        "started_at": state["active_started_at"],
        "until": until,
        "remaining_seconds": float(duration),
        "count_60m": state["count_60m"],
        "count_30m": state["count_30m"],
    }


def finish_ojol_jitter(
    directory: Path,
    *,
    current_time: datetime | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Clear the active jitter break and schedule the next one if daily quota remains."""
    moment_wib = (current_time or now()).astimezone(WIB)
    gen = rng or random.SystemRandom()
    state = load_ojol_jitter_state(directory, current_time=moment_wib)
    state["active_kind"] = None
    state["active_started_at"] = None
    state["active_until"] = None
    if _remaining_choices(state):
        state["next_trigger_at"] = _schedule_next_trigger(moment_wib, gen)
    else:
        state["next_trigger_at"] = None
    save_ojol_jitter_state(directory, state)
    return state


def mark_account_offline_for_jitter(
    directory: Path,
    *,
    kind: str,
    until: datetime,
    current_time: datetime | None = None,
) -> None:
    """Update online-status.json to mark the account offline while worker stays active."""
    moment = (current_time or now()).astimezone(WIB)
    status_file = directory / "online-status.json"
    existing, _ = status_record(status_file)
    payload = {
        **existing,
        "online": False,
        "reason": "ojol_jitter",
        "jitter_kind": kind,
        "jitter_until": until.isoformat(),
        "fetched_at": moment.isoformat(),
    }
    write_private(status_file, payload)
