"""Web and in-app notification manager for ojol-automation."""

import json
import logging
import time
from pathlib import Path
from typing import Any

from .models import Settings

logger = logging.getLogger(__name__)


def notifications_dir(settings: Settings) -> Path:
    directory = settings.runtime_dir / "notifications"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def list_notifications(settings: Settings, limit: int = 50) -> list[dict[str, Any]]:
    """List recent notifications for the given runtime directory."""
    directory = notifications_dir(settings)
    results = []

    # Check active notifications (.json) and recently sent/read (.sent, .read)
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            context = data.get("context") or {}

            # Format display item
            results.append(
                {
                    "id": path.stem,
                    "text": data.get("text", ""),
                    "time": data.get("created_at")
                    or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime)),
                    "is_error": bool(context.get("stage") or context.get("error_id")),
                    "error_id": context.get("error_id"),
                    "event": context.get("event"),
                    "read": data.get("read", False),
                }
            )
        except Exception:
            continue

    return results


def mark_notifications_read(settings: Settings, notice_ids: list[str] | None = None) -> int:
    """Mark notifications as read or move them to .read status."""
    directory = notifications_dir(settings)
    count = 0

    target_ids = set(notice_ids) if notice_ids else None
    for path in directory.glob("*.json"):
        if target_ids is not None and path.stem not in target_ids:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("read"):
                data["read"] = True
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                count += 1
        except Exception:
            continue

    return count


def get_unread_count(settings: Settings) -> int:
    """Count unread notifications."""
    directory = notifications_dir(settings)
    unread = 0
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not data.get("read"):
                unread += 1
        except Exception:
            continue
    return unread
