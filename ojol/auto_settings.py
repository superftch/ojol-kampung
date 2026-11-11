import json

from .healing import write_private

AUTO_LABELS = {
    "ojol": "Auto Ojol",
    "makan": "Makan",
    "kesehatan": "Kesehatan",
    "fisik": "Fisik",
    "rekreasi": "Rekreasi",
    "penampilan": "Penampilan",
    "rumah": "Kondisi rumah",
}
FILENAME = "auto-settings.json"


def auto_flags(directory):
    try:
        saved = json.loads((directory / FILENAME).read_text())
    except FileNotFoundError:
        saved = {}
    if not isinstance(saved, dict) or any(
        key not in AUTO_LABELS or type(enabled) is not bool for key, enabled in saved.items()
    ):
        raise ValueError("Pengaturan Auto akun tidak valid.")
    return {key: saved.get(key, True) for key in AUTO_LABELS}


def set_auto_flag(directory, key, enabled):
    if key not in AUTO_LABELS or type(enabled) is not bool:
        raise ValueError("Pilihan Auto tidak valid.")
    flags = auto_flags(directory)
    flags[key] = enabled
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_private(directory / FILENAME, flags)
