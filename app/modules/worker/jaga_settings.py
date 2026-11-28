"""Per-account settings and persisted dashboard state for Auto Jaga Usaha."""

import re
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from app.core.models import Model
from app.core.storage import write_private

BUSINESS_ID_PATTERN = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"
BUSINESS_ID = re.compile(BUSINESS_ID_PATTERN)
JAGA_SETTINGS_FILE = "jaga-settings.json"
JAGA_STATUS_FILE = "jaga-status.json"
JAGA_PRESETS = {"hemat": 4, "seimbang": 6, "agresif": 8}

BusinessId = Annotated[str, Field(pattern=f"^{BUSINESS_ID_PATTERN}$")]
MinuteLimit = Annotated[int, Field(strict=True, ge=1, le=240)]
Clock = Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]


class BusinessOverride(Model):
    aktif: StrictBool = True
    prioritas: int = Field(default=0, strict=True, ge=0, le=999)
    target_min: MinuteLimit | None = None
    target_max: MinuteLimit | None = None
    maks_menit: MinuteLimit | None = None


class JagaSettings(Model):
    mode: Literal["terbaik", "rotasi", "manual"] = "terbaik"
    budget_jam: float = Field(default=6, strict=True, gt=0, le=10, allow_inf_nan=False)
    target_min: MinuteLimit = 60
    target_max: MinuteLimit = 75
    active_start: Clock = "06:00"
    active_end: Clock = "23:00"
    auto_pindah: StrictBool = True
    min_pelanggan: int = Field(default=20, strict=True, ge=0)
    min_skor: float | None = Field(default=None, strict=True, ge=0, allow_inf_nan=False)
    override: dict[BusinessId, BusinessOverride] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ranges_are_valid(self) -> Self:
        if self.target_min > self.target_max or self.active_start == self.active_end:
            raise ValueError("Rentang target atau jam aktif tidak valid.")
        for item in self.override.values():
            if (item.target_min or self.target_min) > (item.target_max or self.target_max):
                raise ValueError("Rentang target per usaha tidak valid.")
        return self


def load_jaga_settings(directory: Path) -> JagaSettings:
    try:
        return JagaSettings.model_validate_json((directory / JAGA_SETTINGS_FILE).read_text())
    except FileNotFoundError:
        return JagaSettings()


def save_jaga_settings(directory: Path, settings: JagaSettings) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / JAGA_SETTINGS_FILE, settings.model_dump(mode="json"))


def wake_jaga_worker(directory: Path) -> None:
    (directory / "WAKE").touch(mode=0o600)
