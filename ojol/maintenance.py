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
    end: datetime | None = None
    manual: bool = False

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
        return cls(start, end, manual=False)

    @classmethod
    def create_manual(cls):
        return cls(start=now(), end=None, manual=True)

    def payload(self):
        data = {"start": self.start.isoformat(), "manual": self.manual}
        if self.end is not None:
            data["end"] = self.end.isoformat()
        return data

    def description(self):
        if self.manual:
            return "Manual ON (tanpa jadwal)"
        return f"{self.start:%Y-%m-%d %H:%M} sampai {self.end:%Y-%m-%d %H:%M} WIB"

    def held(self, at):
        if self.manual:
            return True
        return self.end is not None and at + DRAIN >= self.start and at < self.end

    def message(self):
        if self.manual:
            return (
                "🛠 Game sedang dijeda untuk maintenance\n\n"
                "Aktivitas akun dijeda secara manual (ON). "
                "Matikan maintenance (OFF) dari menu admin untuk melanjutkan aktivitas."
            )
        return (
            "🛠 Game sedang dijeda untuk maintenance\n\n"
            f"Aktivitas dijeda sampai {self.end:%Y-%m-%d %H:%M} WIB. "
            "Bot akan mencoba melanjutkan setelah jadwal selesai."
        )


def read_window(path):
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, KeyError, ValueError, TypeError, OSError):
        return None
    if payload.get("manual"):
        start = (
            datetime.fromisoformat(payload["start"]).astimezone(WIB)
            if "start" in payload
            else now()
        )
        return MaintenanceWindow(start, None, manual=True)
    if not payload.get("start") or not payload.get("end"):
        return None
    return MaintenanceWindow(
        datetime.fromisoformat(payload["start"]).astimezone(WIB),
        datetime.fromisoformat(payload["end"]).astimezone(WIB),
        manual=False,
    )


def held_window(path):
    window = read_window(path)
    return window if window and window.held(now()) else None
