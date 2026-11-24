"""Service helpers for waking/restarting workers after captcha bank updates."""

import contextlib
import json
from pathlib import Path

from app.core.locks import running
from app.modules.worker.settings import set_auto_flag
from app.web.deps import WebContext


def _matches_pending_review(directory: Path, review_id: str | None, error_id: str | None) -> bool:
    if review_id and (directory / "cek-reviews" / f"{review_id}.json").is_file():
        return True
    if error_id and (
        (directory / "errors" / f"{error_id}.json").is_file()
        or (directory / "errors" / f"OJL-{error_id}.json").is_file()
    ):
        return True
    status_file = directory / "status.json"
    if status_file.is_file():
        try:
            sdata = json.loads(status_file.read_text())
            snap = sdata.get("snapshot") or {}
            if snap.get("phase") == "complete" or str(sdata.get("stage", "")).startswith(
                "job.complete"
            ):
                return True
        except (OSError, ValueError):
            pass
    return False


async def retry_pending_bank_accounts(
    ctx: WebContext,
    fleet_dirs: list[Path],
    acc_names: dict[str, str],
    review_id: str | None,
    error_id: str | None,
) -> list[str]:
    """Wake and resume accounts paused on captcha completion after bank template updates."""
    target_dirs: list[Path] = []
    for directory in fleet_dirs:
        if _matches_pending_review(directory, review_id, error_id) and directory not in target_dirs:
            target_dirs.append(directory)

    if not target_dirs:
        for directory in fleet_dirs:
            status_file = directory / "status.json"
            if status_file.is_file():
                try:
                    sdata = json.loads(status_file.read_text())
                    if (sdata.get("snapshot") or {}).get("phase") == "complete":
                        target_dirs.append(directory)
                except (OSError, ValueError):
                    pass

    retried_accounts: list[str] = []
    for directory in target_dirs:
        name = acc_names.get(str(directory)) or directory.name
        set_auto_flag(directory, "ojol", True)
        with contextlib.suppress(OSError):
            (directory / "WAKE").touch()

        acc_service = None
        if ctx.manager and ctx.registry:
            for acc in ctx.registry.list() + ctx.registry.list(archived=True):
                if str(ctx.registry.scoped_settings(acc).runtime_dir) == str(directory):
                    acc_service = ctx.manager.service(acc["id"])
                    name = acc.get("name", name)
                    break
        if acc_service is None:
            acc_service = ctx.service

        if acc_service:
            is_active = (acc_service.worker and acc_service.worker.returncode is None) or running(
                directory
            )
            if not is_active:
                with contextlib.suppress(OSError, ValueError, RuntimeError):
                    await acc_service.command("run")
        retried_accounts.append(name)

    return retried_accounts
