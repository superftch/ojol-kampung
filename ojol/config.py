import os
from pathlib import Path

from dotenv import dotenv_values

from .models import ROOT, Settings


def load_settings(path: Path | None = None):
    if path is None and os.environ.get("OJOL_CONFIG_FILE"):
        path = Path(os.environ["OJOL_CONFIG_FILE"])
    if os.environ.get("OJOL_ENV") == "testing" and (
        path is None or path.resolve() != ROOT / ".env.testing"
    ):
        raise ValueError("Test wajib memuat .env.testing secara eksplisit; tidak ada fallback .env")
    path = path or ROOT / ".env"
    if not path.is_file():
        raise ValueError(f"Konfigurasi {path.name} tidak tersedia")
    values = {**dotenv_values(path), **os.environ}
    settings = Settings.model_validate(
        {
            name: values[f"OJOL_{name.upper()}"]
            for name in Settings.model_fields
            if f"OJOL_{name.upper()}" in values
        }
    )
    if settings.env == "testing" and path.resolve() != ROOT / ".env.testing":
        raise ValueError("Test tidak boleh memuat .env")
    return settings
