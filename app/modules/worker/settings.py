import json

from app.core.models import STUDY_LABELS
from app.core.storage import write_private

AUTO_LABELS = {
    "ojol": "Auto Ojol",
    "makan": "Makan",
    "kesehatan": "Kesehatan",
    "fisik": "Fisik",
    "rekreasi": "Rekreasi",
    "kebersihan": "Kebersihan",
    "wc": "Buang air",
    "penampilan": "Penampilan",
    "rumah": "Kondisi rumah",
    "kebun": "Kebun & kolam",
    "kerja": "Auto Kerja",
    "kursus": "Auto Kursus",
    **STUDY_LABELS,
}
FILENAME = "auto-settings.json"


def valid_flag_value(key, enabled):
    if key == "ojol" and enabled == "maintenance":
        return True
    return type(enabled) is bool


def auto_flags(directory):
    try:
        saved = json.loads((directory / FILENAME).read_text())
    except FileNotFoundError:
        saved = {}
    if not isinstance(saved, dict) or any(
        key not in AUTO_LABELS or not valid_flag_value(key, enabled)
        for key, enabled in saved.items()
    ):
        raise ValueError("Pengaturan Auto akun tidak valid.")
    return {
        key: saved.get(key, key not in STUDY_LABELS and key not in {"kerja", "kursus"})
        for key in AUTO_LABELS
    }


def set_auto_flag(directory, key, enabled):
    if key not in AUTO_LABELS or not valid_flag_value(key, enabled):
        raise ValueError("Pilihan Auto tidak valid.")
    flags = auto_flags(directory)
    flags[key] = enabled
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / FILENAME, flags)


def should_maintain_online_presence(flags: dict) -> bool:
    """Return True when continuous online presence should be maintained (Auto Ojol or Auto Kerja)."""
    return flags.get("ojol") is True or bool(flags.get("kerja"))
