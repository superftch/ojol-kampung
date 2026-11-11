"""Shared maintenance window for the control service and worker processes."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from .finance import WIB
from .models import now

SCHEDULE_FILE = "maintenance.json"
GAME_COMMANDS = {"run", "import_cookie", "cleanup_scan", "visit_scan"}
DRAIN = timedelta(minutes=2)


@dataclass(frozen=True)
class MaintenanceWindow:
    start: datetime
    end: datetime

    @classmethod
    def parse(cls, value):
        try:
            start, end = (
                datetime.strptime(part.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=WIB)
                for part in value.split("/")
            )
        except ValueError:
            raise ValueError("Gunakan format YYYY-MM-DD HH:MM / YYYY-MM-DD HH:MM (WIB).") from None
        if end <= start or end <= now():
            raise ValueError("Waktu selesai harus setelah waktu mulai dan masih di masa depan.")
        return cls(start, end)

    def payload(self):
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}

    def description(self):
        return f"{self.start:%Y-%m-%d %H:%M} sampai {self.end:%Y-%m-%d %H:%M} WIB"

    def held(self, at):
        return at + DRAIN >= self.start and at < self.end

    def message(self):
        return (
            "🛠 Game sedang dijeda untuk maintenance\n\n"
            f"Aktivitas dijeda sampai {self.end:%Y-%m-%d %H:%M} WIB. "
            "Bot akan mencoba melanjutkan setelah jadwal selesai."
        )


def read_window(path):
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    return MaintenanceWindow(
        datetime.fromisoformat(payload["start"]).astimezone(WIB),
        datetime.fromisoformat(payload["end"]).astimezone(WIB),
    )


def held_window(path):
    window = read_window(path)
    return window if window and window.held(now()) else None
