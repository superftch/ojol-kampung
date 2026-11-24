"""Automated gym minigame execution (Angkat beban 3x daily)."""

import time

from app.integrations.kampung.http_api import HttpCoreError
from app.modules.worker.planner import is_sleeping
from app.modules.worker.settings import auto_flags


async def run_gym(controller):
    c = controller
    if not hasattr(c.ui, "gym_plays_left"):
        return False
    flags = auto_flags(c.settings.runtime_dir)
    if not flags.get("fisik", True):
        return False
    if time.monotonic() < getattr(c, "gym_retry_at", 0):
        return False
    if is_sleeping(c.state):
        return False

    try:
        plays = await c.ui.gym_plays_left()
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.gym_retry_at = time.monotonic() + 300
        return False
    except Exception:
        c.gym_retry_at = time.monotonic() + 300
        return False

    if not isinstance(plays, int) or plays <= 0:
        c.gym_retry_at = time.monotonic() + 1800
        return False

    played_any = False
    while plays > 0:
        c.check_cancel()
        if is_sleeping(c.state):
            break
        success = await c.purchase(c.state, "fisik")
        if not success:
            c.gym_retry_at = time.monotonic() + 300
            break
        played_any = True
        try:
            plays = await c.ui.gym_plays_left()
            if not isinstance(plays, int):
                break
        except Exception:
            break

    if played_any:
        c.gym_retry_at = time.monotonic() + 1800
        return True
    c.gym_retry_at = time.monotonic() + 1800
    return False
