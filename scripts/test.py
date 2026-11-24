"""Tests never inherit .env, Chrome endpoints, model keys, or development state."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values

from ojol.models import Settings


# Cakupan pengujian fitur web (UI dashboard, API, autentikasi, kontrol, supervisor worker, bank angka)
WEB_TEST_FILES = [
    "tests/test_web.py",
    "tests/test_control.py",
    "tests/test_accounts.py",
    "tests/test_worker_service.py",
    "tests/test_autostart.py",
    "tests/test_thresholds.py",
    "tests/test_captcha.py",
    "tests/test_study.py",
    "tests/test_browser_headers.py",
    "tests/test_telegram_login_bot.py",
]


def resolve_pytest_args(raw_args: list[str]) -> tuple[list[str], str]:
    if "--all" in raw_args or "--full" in raw_args:
        filtered = [arg for arg in raw_args if arg not in {"--all", "--full"}]
        has_target = any(
            not arg.startswith("-") and (arg.startswith("tests") or Path(arg).exists())
            for arg in filtered
        )
        banner = "Test: .env.testing eksplisit, seluruh rangkaian test (full suite), tanpa game live."
        return (filtered if has_target else [*filtered, "tests"]), banner

    if "--web" in raw_args:
        filtered = [arg for arg in raw_args if arg != "--web"]
        banner = "Test: .env.testing eksplisit, cakupan fitur web cepat, tanpa game live."
        return [*filtered, *WEB_TEST_FILES], banner

    # Cek apakah ada file/target test eksplisit yang diberikan pemanggil
    has_target = any(
        not arg.startswith("-") and (arg.startswith("tests") or Path(arg).exists())
        for arg in raw_args
    )
    if has_target:
        banner = "Test: .env.testing eksplisit, target spesifik, tanpa game live."
        return raw_args, banner

    # Default optimasi cepat: hanya uji modul yang meng-cover fitur web dashboard
    banner = "Test: .env.testing eksplisit, cakupan fitur web cepat, tanpa game live."
    return [*raw_args, *WEB_TEST_FILES], banner


def main():
    file = ROOT / ".env.testing"
    if sys.argv[1:] == ["--prepare"]:
        if not file.exists():
            file.write_text(
                "OJOL_ENV=testing\nOJOL_OPERATOR_AUTHORIZED=false\nOJOL_RUNTIME_DIR=.local/testing/runtime\nOJOL_MAX_JOBS=2\nOJOL_MAX_MINUTES=1\n"
            )
            file.chmod(0o600)
        print(".env.testing lokal siap; .env tidak dibaca")
        return 0
    if not file.is_file():
        raise SystemExit("BLOCKED: jalankan scripts/test.py --prepare; tidak ada fallback .env")
    values = dotenv_values(file)
    if values.get("OJOL_ENV") != "testing" or any(not key.startswith("OJOL_") for key in values):
        raise SystemExit("BLOCKED: .env.testing wajib khusus testing, tanpa kredensial")
    effective = Settings.model_validate(
        {key.removeprefix("OJOL_").lower(): value for key, value in values.items()}
    )
    if effective.env != "testing":
        raise SystemExit("BLOCKED: test environment bukan testing")
    root = ROOT / ".local/testing"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG") if key in os.environ}
        env.update({key: value for key, value in values.items() if value is not None})
        env.update(
            {
                "HOME": temporary,
                "TMPDIR": temporary,
                "XDG_CONFIG_HOME": temporary + "/config",
                "XDG_CACHE_HOME": temporary + "/cache",
                "PYTHONPATH": str(ROOT),
                "PYTHONNOUSERSITE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "OTEL_SDK_DISABLED": "true",
                "OJOL_TEST_ISOLATED": "1",
                "OJOL_TEST_ENV_FILE": str(file),
                "UV_OFFLINE": "1",
            }
        )
        pytest_args, banner = resolve_pytest_args(sys.argv[1:])
        print(banner, flush=True)
        return subprocess.call(
            [sys.executable, "-m", "pytest", "-p", "pytest_asyncio.plugin", *pytest_args],
            cwd=ROOT,
            env=env,
        )


if __name__ == "__main__":
    raise SystemExit(main())
