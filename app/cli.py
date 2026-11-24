import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import load_settings
from app.core.database import read_sqlite
from app.core.locks import exclusive_lock, running
from app.core.models import ROOT, Settings, now
from app.modules.ledger.finance import report_date
from app.modules.ledger.repository import Journal


def parser():
    result = argparse.ArgumentParser(
        description="Ojol background melalui adapter HTTP. Default dry-run."
    )
    result.add_argument("--env-file", type=Path)
    result.add_argument("--account", help="ID dari list-accounts; default akun lama")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("list-accounts", help="Tampilkan nama dan ID akun yang belum diarsipkan")
    for name in ("run", "start"):
        command = commands.add_parser(name)
        command.add_argument(
            "--live",
            action="store_true",
            help="Jalankan aksi game sesuai izin operator dan batas .env",
        )
        command.add_argument("--max-jobs", type=int)
        command.add_argument("--max-minutes", type=int)
    inspect = commands.add_parser(
        "inspect", help="Baca status melalui API tanpa pembelian atau order"
    )
    inspect.add_argument(
        "--shop",
        choices=["fuel", "condition", "data"],
        help="Tampilkan katalog kandidat untuk resource melalui API",
    )
    cleanup = commands.add_parser("cleanup-scan", help="Baca kandidat rumah kotor melalui API")
    cleanup.add_argument("--blocks", nargs="+", help="Kode blok, default blok rumah sendiri")
    cleanup.add_argument("--limit", type=int, choices=range(1, 11), default=1)
    for name in ("doctor", "status", "stop", "history", "dashboard"):
        commands.add_parser(name)
    online_cmd = commands.add_parser(
        "online", help="Fetch API status online untuk memastikan akun presence online"
    )
    online_cmd.add_argument(
        "--all", action="store_true", help="Fetch online status untuk semua akun"
    )
    reconcile = commands.add_parser("reconcile", help="Periksa hasil aksi dari bukti game")
    target = reconcile.add_mutually_exclusive_group()
    target.add_argument("--error-id", help="Periksa hanya aksi terkait ID error OJL-...")
    target.add_argument("--action-id", type=int, help="Periksa ID aksi ledger, misalnya 3095")
    reconcile.add_argument(
        "--skip",
        action="store_true",
        help="Lewati --action-id atas keputusan operator; hasil lama tetap belum terverifikasi",
    )
    profit = commands.add_parser("profit")
    period = profit.add_mutually_exclusive_group()
    period.add_argument(
        "--date",
        type=report_date,
        help="Tanggal laporan WIB, YYYY-MM-DD atau DD-MM-YYYY; default hari ini",
    )
    period.add_argument("--all-time", action="store_true")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    account = None
    owns_live_run = False
    try:
        settings = load_settings(args.env_file)
        if args.command == "list-accounts":
            if args.account:
                raise ValueError("Jalankan list-accounts tanpa --account")
            path = settings.runtime_dir / "accounts.sqlite3"
            if not path.is_file():
                raise ValueError("Registry akun belum tersedia")
            with read_sqlite(path) as db:
                print("NAMA\tACCOUNT_ID")
                for name, identifier in db.execute(
                    "SELECT name, id FROM accounts WHERE archived=0 ORDER BY name, id"
                ):
                    print(f"{name}\t{identifier}")
            return 0
        if args.account:
            from app.modules.accounts.repository import Accounts

            registry = Accounts(settings)
            account = registry.get(args.account)
            settings = registry.scoped_settings(account)
        changes = {
            key: getattr(args, key)
            for key in ("max_jobs", "max_minutes")
            if getattr(args, key, None) is not None
        }
        settings = Settings.model_validate(
            {**{key: getattr(settings, key) for key in Settings.model_fields}, **changes}
        )
        live = getattr(args, "live", False)
        if live and (not settings.operator_authorized or settings.env == "testing"):
            raise ValueError(
                "Mode live memerlukan izin operator pada .env lokal; testing tidak pernah live"
            )
        directory = settings.runtime_dir
        if args.command == "cleanup-scan":
            if settings.env == "testing":
                raise ValueError("HTTP live diblokir dalam test environment")
            from app.integrations.kampung.http_api import OjolHttpApi
            from app.modules.gameplay.cleanup import scan

            async def read_cleanup():
                async with OjolHttpApi(directory) as api:
                    return await scan(api, args.blocks, args.limit)

            print(json.dumps(asyncio.run(read_cleanup()), ensure_ascii=False, indent=2))
        elif args.command == "status":
            path = directory / "status.json"
            data: dict[str, Any] = (
                json.loads(path.read_text()) if path.is_file() else {"event": "belum dijalankan"}
            )
            data["running"] = running(directory)
            journal = Journal(directory)
            try:
                data["profit_total"] = journal.profit()
                data["profit"] = journal.profit(data["run_id"]) if data.get("run_id") else None
            finally:
                journal.close()
            if data.get("wait_until"):
                deadline = datetime.fromisoformat(data["wait_until"])
                data["wait_until_wib"] = deadline.astimezone(ZoneInfo("Asia/Jakarta")).isoformat()
                remaining = (
                    max(0, ceil((deadline - now()).total_seconds())) if data["running"] else None
                )
                data["countdown_estimate"] = (
                    f"{remaining // 60}:{remaining % 60:02}" if remaining is not None else None
                )
                data["countdown_source"] = (
                    "Estimasi dari countdown DOM terakhir; snapshot tetap memuat waktu observasi aslinya."
                )
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "dashboard":
            from app.main import ControlService

            service = ControlService(settings)
            print(asyncio.run(service.command("dashboard")))
        elif args.command == "online":
            if getattr(args, "all", False):
                from app.modules.worker.fleet import MultiAccountService

                manager = MultiAccountService(settings)
                res = asyncio.run(manager.fetch_all_online_status())
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                from app.integrations.kampung.http_api import OjolHttpApi

                async def fetch_one():
                    async with OjolHttpApi(directory) as api:
                        return await api.fetch_online_status()

                print(json.dumps(asyncio.run(fetch_one()), ensure_ascii=False, indent=2))
        elif args.command == "stop":
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            (directory / "STOP").touch(mode=0o600)
            print(
                "Stop diminta. Tidak ada klik baru setelah permintaan terbaca; transaksi yang sudah terkirim diverifikasi saat tersedia."
            )
        elif args.command in {"history", "profit"}:
            journal = Journal(directory)
            try:
                print(
                    json.dumps(
                        journal.history()
                        if args.command == "history"
                        else journal.financial_report(args.date, args.all_time),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            finally:
                journal.close()
        elif args.command == "reconcile" and args.skip:
            if args.action_id is None:
                raise ValueError("--skip memerlukan --action-id agar aksi yang dilewati jelas")
            with exclusive_lock(directory), closing(Journal(directory)) as journal:
                action = journal.skip(args.action_id)
                print(
                    f"Aksi #{action['id']} ({action['kind']}): {action['status']} → skipped. "
                    "Hasil lama tetap belum terverifikasi; payout/biaya tidak ditambahkan."
                )
                print(f"Sisa aksi belum pasti: {len(journal.unresolved())}.")
                if not journal.unresolved():
                    print(
                        "Ledger siap dilanjutkan. Tekan Jalankan Ojol untuk memulai dari kondisi game terbaru."
                    )
        elif args.command == "start":
            if not live:
                raise ValueError(
                    "start background memerlukan --live eksplisit; gunakan run untuk dry-run"
                )
            with exclusive_lock(directory):
                pass
            command = [sys.executable, str(ROOT / "main.py")]
            if args.env_file:
                command += ["--env-file", str(args.env_file.resolve())]
            if args.account:
                command += ["--account", args.account]
            command += ["run", "--live"]
            for option, value in (
                ("--max-jobs", settings.max_jobs),
                ("--max-minutes", settings.max_minutes),
            ):
                if value is not None:
                    command += [option, str(value)]
            with (directory / "automation.log").open("a") as output:
                # Fixed Python entry point and CLI arguments, with no shell.
                process = subprocess.Popen(  # noqa: S603
                    command,
                    cwd=ROOT,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            time.sleep(1)
            if process.poll() is not None:
                raise RuntimeError("Worker berhenti saat startup. Periksa .local/automation.log")
            print(
                f"Worker background dimulai: PID {process.pid}. Cek status; hentikan dengan stop."
            )
        else:
            if settings.env == "testing":
                raise ValueError("HTTP live diblokir dalam test environment")
            from app.modules.worker.runner import run_app

            with exclusive_lock(directory):
                if args.command == "run":
                    owns_live_run = live
                    (directory / "STOP").unlink(missing_ok=True)
                options = (
                    {
                        key: getattr(args, key)
                        for key in ("error_id", "action_id")
                        if getattr(args, key) is not None
                    }
                    if args.command == "reconcile"
                    else {}
                )
                asyncio.run(
                    run_app(settings, args.command, live, getattr(args, "shop", None), **options)
                )
        return 0
    except KeyboardInterrupt:
        print("Dihentikan pengguna.", file=sys.stderr)
        return 130
    except Exception as exc:
        from pydantic import ValidationError

        message = "Konfigurasi/state tidak valid" if isinstance(exc, ValidationError) else str(exc)
        if "settings" in locals() and settings.env != "testing":
            from app.modules.notifications.service import queue_error, redact

            status_path = settings.runtime_dir / "status.json"
            try:
                status = json.loads(status_path.read_text()) if status_path.is_file() else {}
            except (OSError, ValueError):
                status = {}
            context = (
                {key: status.get(key) for key in ("run_id", "last_action", "tab_id")}
                if status.get("pid") == os.getpid()
                else {}
            )
            context["pid"] = os.getpid()
            context["account_id"] = account["id"] if account else os.environ.get("OJOL_ACCOUNT_ID")
            if args.command == "run" and os.environ.get("OJOL_WORKER_AUTO_START") == "1":
                context["tindakan"] = (
                    "Tekan Import Cookie, lalu Jalankan Ojol."
                    if getattr(exc, "category", None) == "auth"
                    else "Tekan Status untuk memeriksa kondisi akun sebelum mencoba Jalankan Ojol."
                )
            stage = (
                status.get("stage")
                if args.command == "run"
                and status.get("event") in {"gagal", "rekonsiliasi", "rekonsiliasi_otomatis"}
                and status.get("pid") == os.getpid()
                else getattr(exc, "stage", f"cli.{args.command}")
            )
            queue_error(
                settings,
                exc,
                stage or f"cli.{args.command}",
                context,
                stop_worker=owns_live_run,
            )
            message = redact(message)
        print(f"Gagal: {message}", file=sys.stderr)
        return 2
