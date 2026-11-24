"""Atomic private runtime JSON storage and status file readers."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def write_private(path: Path, data: Any) -> None:
    """Atomically write JSON data to ``path`` with 0600 permissions."""
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(data, handle, ensure_ascii=False)
    temporary.replace(path)


def status_record(path: Path) -> tuple[dict[str, Any], int]:
    """Read a JSON dict file and its mtime_ns, returning ({}, 0) on error."""
    try:
        value = json.loads(path.read_text())
        return (value, path.stat().st_mtime_ns) if isinstance(value, dict) else ({}, 0)
    except (OSError, ValueError):
        return {}, 0


def status_timestamp(value: Any) -> datetime | None:
    """Parse a timezone-aware ISO-8601 timestamp string, or return None."""
    try:
        stamp = datetime.fromisoformat(value)
        return stamp if stamp.tzinfo is not None else None
    except (TypeError, ValueError):
        return None
