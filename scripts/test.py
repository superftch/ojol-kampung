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
        print(
            "Test: .env.testing eksplisit, env shell dibuang, HOME/tmp/cache/SQLite terisolasi, tanpa game/model live.",
            flush=True,
        )
        return subprocess.call(
            [sys.executable, "-m", "pytest", "-p", "pytest_asyncio.plugin", *sys.argv[1:]],
            cwd=ROOT,
            env=env,
        )


if __name__ == "__main__":
    raise SystemExit(main())
