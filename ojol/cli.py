import argparse
import asyncio
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing, contextmanager
from datetime import datetime
from math import ceil
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_settings
from .finance import report_date
from .journal import Journal
from .models import ROOT, Settings, now


@contextmanager
def exclusive_lock(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Automation sudah berjalan. Gunakan status/stop; tidak membuka controller kedua."
            ) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def running(directory):
    try:
        with exclusive_lock(directory):
            return False
    except RuntimeError:
        return True


def parser():
    result = argparse.ArgumentParser(
        description="Ojol background melalui HTTP MCP. Default dry-run."
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
    for name in ("doctor", "status", "stop", "history", "reconcile"):
        commands.add_parser(name)
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
    try:
        settings = load_settings(args.env_file)
        if args.command == "list-accounts":
            if args.account:
                raise ValueError("Jalankan list-accounts tanpa --account")
            path = settings.runtime_dir / "accounts.sqlite3"
            if not path.is_file():
                raise ValueError("Registry akun belum tersedia")
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                print("NAMA\tACCOUNT_ID")
                for name, identifier in db.execute(
                    "SELECT name, id FROM accounts WHERE archived=0 ORDER BY name, id"
                ):
                    print(f"{name}\t{identifier}")
            return 0
        if args.account:
            from .accounts import Accounts

            registry = Accounts(settings)
            settings = registry.scoped_settings(registry.get(args.account))
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
            from .cleanup import scan
            from .http_api import OjolHttpApi

            async def read_cleanup():
                async with OjolHttpApi(directory) as api:
                    return await scan(api, args.blocks, args.limit)

            print(json.dumps(asyncio.run(read_cleanup()), ensure_ascii=False, indent=2))
        elif args.command == "status":
            path = directory / "status.json"
            data = json.loads(path.read_text()) if path.is_file() else {"event": "belum dijalankan"}
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
                process = subprocess.Popen(
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
            from .app import run_app

            with exclusive_lock(directory):
                if args.command == "run":
                    (directory / "STOP").unlink(missing_ok=True)
                asyncio.run(run_app(settings, args.command, live, getattr(args, "shop", None)))
        return 0
    except KeyboardInterrupt:
        print("Dihentikan pengguna.", file=sys.stderr)
        return 130
    except Exception as exc:
        from pydantic import ValidationError

        message = "Konfigurasi/state tidak valid" if isinstance(exc, ValidationError) else str(exc)
        if "settings" in locals() and settings.env != "testing":
            from .telegram import flush_notices, queue_error, redact

            status_path = settings.runtime_dir / "status.json"
            try:
                status = json.loads(status_path.read_text()) if status_path.is_file() else {}
            except (OSError, ValueError):
                status = {}
            context = {key: status.get(key) for key in ("run_id", "last_action", "tab_id")}
            context["pid"] = os.getpid()
            context["account_id"] = os.environ.get("OJOL_ACCOUNT_ID")
            context["mcp_tool"] = getattr(exc, "operation", None)
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
                stop_worker=args.command not in {"cleanup-scan", "list-accounts"},
            )
            try:
                asyncio.run(flush_notices(settings))
            except Exception:
                pass
            message = redact(message, settings)
        print(f"Gagal: {message}", file=sys.stderr)
        return 2
