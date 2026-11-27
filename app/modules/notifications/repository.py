"""Web and in-app notification manager for ojol-automation."""

import heapq
import json
import logging
import os
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.models import Settings
from app.modules.accounts.repository import Accounts

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
        except (OSError, ValueError, AttributeError):
            continue

    return results


def mark_notifications_read(settings: Settings, notice_ids: list[str] | None = None) -> int:
    """Mark notifications as read or move them to .read status."""
    return _mark_read(notifications_dir(settings), notice_ids)


def _mark_read(directory: Path, notice_ids: list[str] | None = None) -> int:
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
        except (OSError, ValueError, AttributeError):
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
        except (OSError, ValueError, AttributeError):
            continue
    return unread


@dataclass(frozen=True)
class _NotificationScope:
    directory: Path
    account_id: str
    account_name: str
    owner: int | None = None
    archived: bool = False


def _notification_scopes(
    settings: Settings, registry: Accounts | None
) -> Iterator[_NotificationScope]:
    if registry is not None:
        try:
            accounts = registry.list(archived=None)
        except sqlite3.Error as exc:
            logger.warning("Could not list notification accounts (%s)", type(exc).__name__)
            accounts = []
        for account in accounts:
            try:
                scoped = registry.scoped_settings(account)
            except (sqlite3.Error, OSError, ValueError) as exc:
                logger.warning("Could not resolve account notifications (%s)", type(exc).__name__)
                continue
            yield _NotificationScope(
                scoped.runtime_dir / "notifications",
                account["id"],
                account["name"],
                account["owner"],
                bool(account["archived"]),
            )

    accounts_dir = settings.runtime_dir / "accounts"
    if accounts_dir.is_dir():
        for directory in accounts_dir.iterdir():
            if directory.is_dir():
                yield _NotificationScope(
                    directory / "notifications",
                    directory.name,
                    f"Akun {directory.name[:8]}",
                )
    users_dir = settings.runtime_dir / "control" / "users"
    if users_dir.is_dir():
        for directory in users_dir.iterdir():
            if not directory.is_dir():
                continue
            try:
                owner = int(directory.name)
            except ValueError:
                owner = None
            yield _NotificationScope(
                directory / "notifications",
                f"ctrl_{directory.name}",
                "Kontrol User / Bot",
                owner,
            )
    yield _NotificationScope(
        settings.runtime_dir / "notifications",
        "system",
        "Sistem / Default",
    )


def _fleet_notification_dirs(
    settings: Settings, registry: Accounts | None
) -> Iterator[_NotificationScope]:
    scanned: set[Path] = set()
    for scope in _notification_scopes(settings, registry):
        if not scope.directory.is_dir():
            continue
        resolved = scope.directory.resolve()
        if resolved not in scanned:
            scanned.add(resolved)
            yield scope


def _notification_users(registry: Accounts | None) -> dict[int, dict[str, Any]]:
    users: dict[int, dict[str, Any]] = {}
    if registry is None:
        return users
    try:
        for user in registry.users():
            if tg_id := user.get("owner"):
                users[int(tg_id)] = {
                    "user_id": tg_id,
                    "username": user.get("username") or "",
                    "name": user.get("name") or "",
                }
    except (sqlite3.Error, TypeError, ValueError) as exc:
        logger.warning("Could not read legacy notification users (%s)", type(exc).__name__)

    try:
        if hasattr(registry, "web"):
            for user in registry.web.list_users():
                entry = {
                    "user_id": user["id"],
                    "username": user.get("username") or "",
                    "name": user.get("name") or "",
                    "role": user.get("role", "user"),
                }
                users[10_000_000_000 + int(user["id"])] = entry
                if tg_id := user.get("telegram_id"):
                    users[int(tg_id)] = entry
    except (sqlite3.Error, TypeError, ValueError) as exc:
        logger.warning("Could not read web notification users (%s)", type(exc).__name__)
    return users


def _notification_user(
    scope: _NotificationScope, users: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    owner = scope.owner
    if scope.account_id == "system":
        return {
            "user_id": 0,
            "username": "system",
            "name": "Sistem Utama",
        }
    if owner is not None and owner in users:
        return users[owner]
    return {
        "user_id": owner,
        "username": f"user_{owner}" if owner else "system",
        "name": f"User #{owner}" if owner else "System",
    }


def list_all_admin_notifications(
    settings: Settings,
    registry: Accounts | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List recent notifications across all users, accounts, and system runtime directories."""
    if limit <= 0:
        return []
    users = _notification_users(registry)
    # Scan directory metadata first so we only read and parse the newest `limit` JSON files.
    candidates: dict[tuple[str, str], tuple[float, str, _NotificationScope]] = {}
    for scope in _fleet_notification_dirs(settings, registry):
        try:
            with os.scandir(scope.directory) as entries:
                for entry in entries:
                    if not entry.name.endswith(".json") or not entry.is_file(follow_symlinks=False):
                        continue
                    try:
                        mtime = entry.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        continue
                    stem = entry.name[:-5]
                    key = (scope.account_id, stem)
                    prev = candidates.get(key)
                    if prev is None or mtime > prev[0]:
                        candidates[key] = (mtime, entry.path, scope)
        except OSError:
            continue

    top_entries = heapq.nlargest(limit, candidates.items(), key=lambda item: item[1][0])
    results: list[dict[str, Any]] = []
    for (account_id, stem), (mtime, path_str, scope) in top_entries:
        try:
            with open(path_str, encoding="utf-8") as fh:
                data = json.load(fh)
            context = data.get("context") or {}
            results.append(
                {
                    "id": stem,
                    "text": data.get("text", ""),
                    "time": data.get("created_at")
                    or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
                    "timestamp": mtime,
                    "is_error": bool(context.get("stage") or context.get("error_id")),
                    "error_id": context.get("error_id"),
                    "event": context.get("event"),
                    "read": bool(data.get("read", False)),
                    "account_id": account_id,
                    "account_name": scope.account_name,
                    "account_archived": scope.archived,
                    "owner": scope.owner,
                    "user": _notification_user(scope, users),
                }
            )
        except (OSError, ValueError, AttributeError):
            continue

    return results


def mark_all_admin_notifications_read(
    settings: Settings,
    registry: Accounts | None = None,
) -> int:
    """Mark all notifications across all accounts and runtime directories as read."""
    return sum(
        _mark_read(scope.directory) for scope in _fleet_notification_dirs(settings, registry)
    )
