"""Control server CLI and public app factory."""

import sys
from getpass import getpass

import uvicorn

from app.core.config import load_settings
from app.core.models import Settings
from app.modules.accounts.repository import Accounts
from app.modules.worker.service import WORKER_SHUTDOWN as WORKER_SHUTDOWN
from app.modules.worker.service import ControlService as ControlService
from app.web.factory import create_app as create_app


def main():
    try:
        settings = load_settings()
    except ValueError:
        raise SystemExit(
            "Konfigurasi tidak valid; periksa file env. Nilai rahasia tidak dicetak."
        ) from None
    settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if len(sys.argv) > 1:
        if sys.argv[1] == "set-url" and len(sys.argv) == 3:
            if settings.env == "production":
                raise SystemExit(
                    "Ubah OJOL_LOGIN_PUBLIC_URL pada .env lalu recreate service production."
                )
            (settings.runtime_dir / "public-url").write_text(
                Settings.secure_login_origin(sys.argv[2])
            )
            print("URL import cookie publik diperbarui; tidak mencetak link akses rahasia")
            return
        if sys.argv[1] == "set-web-password" and len(sys.argv) == 3:
            registry = Accounts(settings)
            try:
                registry.web.recover_password(sys.argv[2], getpass("Password web baru: "))
            except ValueError as exc:
                raise SystemExit(str(exc)) from None
            print("Password web disimpan. Semua sesi lama dicabut.")
            return
        raise SystemExit("Gunakan set-url URL atau set-web-password USERNAME")
    uvicorn.run(create_app(settings), host="0.0.0.0", port=6080, access_log=False)  # noqa: S104 - container listener


if __name__ == "__main__":
    main()
