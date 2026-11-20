"""CLI entry for one worker run: inspect, reconcile, or run the controller."""

import asyncio
import json
import os
import signal

from .controller import Controller, StopRequested
from .healing import write_private
from .journal import Journal
from .models import now
from .planner import next_step
from .reconciliation import reconcile, wait_until_resolved
from .ui import HttpUI


async def run_app(settings, command, live=False, shop=None, error_id=None, action_id=None):
    if settings.env == "testing":
        raise ValueError("Agen live tidak boleh dijalankan dalam testing; gunakan mocked UI")
    cancel = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, cancel.set)
    try:

        def check_startup_cancel():
            if cancel.is_set() or (command == "run" and (settings.runtime_dir / "STOP").exists()):
                raise StopRequested("Dihentikan pengguna")

        async with HttpUI(settings) as ui:
            ui.check_cancel = check_startup_cancel
            ui.check_cancel()
            if command in {"inspect", "doctor"}:
                state = await ui.snapshot()
                output = {
                    "core": "http",
                    "snapshot": state.model_dump(mode="json"),
                    "next": next_step(state, settings).model_dump(mode="json"),
                }
                if shop:
                    shops = await ui.preview_shops(shop)
                    output["shops"] = [
                        {**item.model_dump(mode="json"), "preferred": item.preferred}
                        for item in shops
                    ]
                print(json.dumps(output, ensure_ascii=False, indent=2), flush=True)
            elif command == "reconcile":
                journal = Journal(settings.runtime_dir)
                try:
                    await reconcile(ui, journal, error_id, action_id)
                    if error_id or action_id is not None:
                        print(
                            f"Total aksi belum pasti di seluruh akun ini: {len(journal.unresolved())}."
                        )
                    elif journal.unresolved():
                        print(
                            "Masih ada hasil aksi yang belum pasti. Periksa riwayat sebelum melanjutkan."
                        )
                    else:
                        print(
                            "Riwayat yang tersedia sudah sesuai game. Tekan Jalankan Ojol untuk melanjutkan."
                        )
                finally:
                    journal.close()
            else:
                await run_worker(ui, settings, live, cancel)
    except StopRequested:
        print("Worker dihentikan sebelum startup selesai.", flush=True)
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


async def run_worker(ui, settings, live, cancel):
    journal = Journal(settings.runtime_dir)
    try:
        if live:
            write_private(
                settings.runtime_dir / "status.json",
                {
                    "pid": os.getpid(),
                    "event": "rekonsiliasi",
                    "stage": "worker.reconcile",
                    "time": now().isoformat(),
                },
            )
            reconciled = await wait_until_resolved(ui, journal, settings)
        else:
            reconciled = await ui.snapshot()
        run_id = journal.start(settings)
    except BaseException:
        journal.close()
        raise
    controller = Controller(ui, settings, journal, run_id, cancel)
    controller.state = reconciled
    controller.snapshot_received_at = now().isoformat()
    ui.check_cancel = controller.check_cancel
    try:
        controller.report(
            "mulai",
            live=live,
            max_spend=str(settings.max_spend) if settings.max_spend is not None else None,
            min_balance=str(settings.min_balance),
            max_jobs=settings.max_jobs,
            max_minutes=settings.max_minutes,
        )
        await controller.run(
            dry_run=not live,
            auto_start=live and os.environ.get("OJOL_WORKER_AUTO_START") == "1",
        )
        journal.finish(run_id, "dry_run")
    except StopRequested as exc:
        controller.report("berhenti", reason=str(exc))
        journal.finish(run_id, "stopped")
    except BaseException as exc:
        from .telegram import redact

        controller.report(
            "gagal",
            category=type(exc).__name__,
            reason=redact(exc, settings),
            stage=controller.stage,
            last_action=controller.last_action,
        )
        journal.finish(run_id, "error")
        raise
    finally:
        journal.close()
