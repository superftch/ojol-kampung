"""Verified game identity shared by import, workers and Telegram account names."""

import json
from uuid import uuid4

from .healing import write_private
from .models import now


def verified_profile(account):
    nickname = (account.get("profile") or {}).get("nickname")
    balance = account.get("balanceMilli")
    if (
        not isinstance(nickname, str)
        or not 1 <= len(nickname.strip()) <= 40
        or any(ord(char) < 32 or ord(char) == 127 for char in nickname)
        or type(balance) is not int
        or balance < 0
    ):
        raise ValueError("Nickname atau saldo profil game tidak dapat diverifikasi")
    return {"nickname": nickname.strip(), "balanceMilli": balance, "checked_at": now().isoformat()}


def save_profile(directory, profile):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # The worker and a read-only account refresh may finish at the same time.
    temporary = directory / f"game-profile-{uuid4().hex}.json"
    try:
        write_private(temporary, profile)
        temporary.replace(directory / "game-profile.json")
    finally:
        temporary.unlink(missing_ok=True)


def cached_profile(directory):
    try:
        profile = json.loads((directory / "game-profile.json").read_text())
        verified_profile(
            {"profile": {"nickname": profile["nickname"]}, "balanceMilli": profile["balanceMilli"]}
        )
        return profile
    except (OSError, KeyError, TypeError, ValueError, AttributeError):
        return None
