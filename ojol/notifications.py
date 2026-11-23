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


def list_all_admin_notifications(
    settings: Settings,
    registry: Any = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List recent notifications across all users, accounts, and system runtime directories."""
    user_map: dict[int, dict[str, Any]] = {}
    if registry is not None:
        try:
            for u in registry.users():
                tg_id = u.get("telegram_id")
                if tg_id:
                    user_map[int(tg_id)] = {
                        "user_id": tg_id,
                        "username": u.get("username") or "",
                        "name": u.get("name") or "",
                        "telegram_id": tg_id,
                    }
        except Exception:
            pass

        try:
            if hasattr(registry, "web"):
                for wu in registry.web.list_users():
                    w_id = wu["id"]
                    synthetic_owner = 10_000_000_000 + int(w_id)
                    user_entry = {
                        "user_id": w_id,
                        "username": wu.get("username") or "",
                        "name": wu.get("name") or "",
                        "telegram_id": wu.get("telegram_id"),
                        "role": wu.get("role", "user"),
                    }
                    user_map[synthetic_owner] = user_entry
                    if wu.get("telegram_id"):
                        user_map[int(wu["telegram_id"])] = user_entry
        except Exception:
            pass

    def parse_notice(
        path: Path,
        account_id: str | None = None,
        account_name: str | None = None,
        account_archived: bool = False,
        owner: int | None = None,
        u_info: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            context = data.get("context") or {}
            mtime = path.stat().st_mtime
            created_at = data.get("created_at") or time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(mtime)
            )
            resolved_user = (
                u_info
                or user_map.get(owner)
                or {
                    "user_id": owner,
                    "username": f"user_{owner}" if owner else "system",
                    "name": f"User #{owner}" if owner else "System",
                    "telegram_id": owner if (owner and owner < 10_000_000_000) else None,
                }
            )
            return {
                "id": path.stem,
                "text": data.get("text", ""),
                "time": created_at,
                "timestamp": mtime,
                "is_error": bool(context.get("stage") or context.get("error_id")),
                "error_id": context.get("error_id"),
                "event": context.get("event"),
                "read": bool(data.get("read", False)),
                "account_id": account_id or "system",
                "account_name": account_name or "Sistem",
                "account_archived": account_archived,
                "owner": owner,
                "user": resolved_user,
            }
        except Exception:
            return None

    results: list[dict[str, Any]] = []
    scanned_dirs: set[Path] = set()

    # 1. Accounts in registry
    if registry is not None:
        try:
            all_accounts = registry.list(archived=False) + registry.list(archived=True)
            for acc in all_accounts:
                try:
                    scoped = registry.scoped_settings(acc)
                    d = notifications_dir(scoped)
                    resolved = d.resolve()
                    if resolved in scanned_dirs:
                        continue
                    scanned_dirs.add(resolved)
                    owner = acc.get("owner")
                    u_info = user_map.get(owner)
                    for p in d.glob("*.json"):
                        item = parse_notice(
                            p,
                            account_id=acc.get("id"),
                            account_name=acc.get("name"),
                            account_archived=bool(acc.get("archived")),
                            owner=owner,
                            u_info=u_info,
                        )
                        if item:
                            results.append(item)
                except Exception:
                    continue
        except Exception:
            pass

    # 2. Subdirectories in runtime_dir / accounts (on disk)
    accounts_disk = settings.runtime_dir / "accounts"
    if accounts_disk.is_dir():
        for acc_dir in accounts_disk.iterdir():
            if not acc_dir.is_dir():
                continue
            d = acc_dir / "notifications"
            resolved = d.resolve()
            if resolved in scanned_dirs or not d.is_dir():
                continue
            scanned_dirs.add(resolved)
            for p in d.glob("*.json"):
                item = parse_notice(
                    p,
                    account_id=acc_dir.name,
                    account_name=f"Akun {acc_dir.name[:8]}",
                    account_archived=False,
                    owner=None,
                )
                if item:
                    results.append(item)

    # 3. Control / users runtime directories
    control_users = settings.runtime_dir / "control" / "users"
    if control_users.is_dir():
        for u_dir in control_users.iterdir():
            if not u_dir.is_dir():
                continue
            d = u_dir / "notifications"
            resolved = d.resolve()
            if resolved in scanned_dirs or not d.is_dir():
                continue
            scanned_dirs.add(resolved)
            try:
                owner_val = int(u_dir.name)
            except ValueError:
                owner_val = None
            u_info = user_map.get(owner_val)
            for p in d.glob("*.json"):
                item = parse_notice(
                    p,
                    account_id=f"ctrl_{u_dir.name}",
                    account_name="Kontrol User / Bot",
                    account_archived=False,
                    owner=owner_val,
                    u_info=u_info,
                )
                if item:
                    results.append(item)

    # 4. Root / default notifications
    root_d = settings.runtime_dir / "notifications"
    resolved_root = root_d.resolve()
    if resolved_root not in scanned_dirs and root_d.is_dir():
        scanned_dirs.add(resolved_root)
        for p in root_d.glob("*.json"):
            item = parse_notice(
                p,
                account_id="system",
                account_name="Sistem / Default",
                account_archived=False,
                owner=getattr(settings, "telegram_chat_id", None),
                u_info={
                    "user_id": 0,
                    "username": "system",
                    "name": "Sistem Utama",
                    "telegram_id": getattr(settings, "telegram_chat_id", None),
                },
            )
            if item:
                results.append(item)

    # Deduplicate by (account_id, id)
    seen_keys = set()
    deduped = []
    for item in results:
        key = (item["account_id"], item["id"])
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(item)

    deduped.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return deduped[:limit]


def mark_all_admin_notifications_read(
    settings: Settings,
    registry: Any = None,
) -> int:
    """Mark all notifications across all accounts and runtime directories as read."""
    scanned_dirs: set[Path] = set()
    total_marked = 0

    if registry is not None:
        try:
            all_accounts = registry.list(archived=False) + registry.list(archived=True)
            for acc in all_accounts:
                try:
                    scoped = registry.scoped_settings(acc)
                    d = notifications_dir(scoped)
                    resolved = d.resolve()
                    if resolved in scanned_dirs:
                        continue
                    scanned_dirs.add(resolved)
                    total_marked += mark_notifications_read(scoped)
                except Exception:
                    continue
        except Exception:
            pass

    # Root notifications
    root_d = notifications_dir(settings)
    if root_d.resolve() not in scanned_dirs:
        scanned_dirs.add(root_d.resolve())
        total_marked += mark_notifications_read(settings)

    # Accounts on disk
    accounts_disk = settings.runtime_dir / "accounts"
    if accounts_disk.is_dir():
        for acc_dir in accounts_disk.iterdir():
            d = acc_dir / "notifications"
            resolved = d.resolve()
            if resolved in scanned_dirs or not d.is_dir():
                continue
            scanned_dirs.add(resolved)
            dummy_settings = settings.model_copy(update={"runtime_dir": acc_dir})
            total_marked += mark_notifications_read(dummy_settings)

    # Control users
    control_users = settings.runtime_dir / "control" / "users"
    if control_users.is_dir():
        for u_dir in control_users.iterdir():
            d = u_dir / "notifications"
            resolved = d.resolve()
            if resolved in scanned_dirs or not d.is_dir():
                continue
            scanned_dirs.add(resolved)
            dummy_settings = settings.model_copy(update={"runtime_dir": u_dir})
            total_marked += mark_notifications_read(dummy_settings)

    return total_marked
