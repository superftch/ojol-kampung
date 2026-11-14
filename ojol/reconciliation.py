"""Reconcile observed results before starting another worker session."""

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path

from .finance import completion_evidence
from .healing import write_private
from .http_api import HttpCoreError
from .journal import load_journal_snapshot
from .maintenance import SCHEDULE_FILE, held_window
from .models import NEEDS, now
from .telegram import queue_error, queue_notice


async def reconcile(ui, journal):
    maintenance_file = Path(
        os.environ.get("OJOL_MAINTENANCE_FILE", str(journal.directory / SCHEDULE_FILE))
    )
    while held_window(maintenance_file):
        ui.check_cancel()
        await asyncio.sleep(1)
    resolved = []
    claimed = {
        row[0]
        for row in journal.db.execute(
            "SELECT json_extract(before_state, '$.trip_id') FROM actions "
            "WHERE kind='complete' AND status='verified'"
        )
        if row[0]
    }
    state = None
    for action in journal.unresolved():
        before = load_journal_snapshot(action["before_state"])
        state = await ui.snapshot()
        evidence = None
        if action["kind"] == "search":
            observed = state
            await asyncio.sleep(1)
            state = await ui.snapshot()
            evidence = journal.resolve_search(action["id"], observed, state)
            if evidence:
                resolved.append(action["id"])
                print(f"Aksi #{action['id']}: {evidence['status']} menurut status game terbaru.")
                print(
                    f"Selisih resource {evidence['resource_delta']} dicatat tanpa atribusi penyebab."
                )
                if state.wallet != before.wallet:
                    print(
                        f"Selisih saldo {evidence['wallet_delta']} koin dicatat tanpa atribusi penyebab."
                    )
                continue
            fields = {
                "observed_at",
                "phase",
                "wallet",
                "fuel",
                "condition",
                "data",
                "today_income",
                "trip",
                "buttons",
            }
            print(
                "Bukti pencarian: "
                + json.dumps(
                    {
                        "before": before.model_dump(mode="json", include=fields),
                        "current": state.model_dump(mode="json", include=fields),
                        "history_changed": before.history != state.history,
                        "observations_stable": observed.model_dump(exclude={"observed_at"})
                        == state.model_dump(exclude={"observed_at"}),
                    },
                    ensure_ascii=False,
                )
            )
        payload = json.loads(action["payload"])
        valid = False
        if action["kind"] == "purchase":
            resource = payload["resource"]
            previous, current = before.resource_value(resource), state.resource_value(resource)
            tolerance = Decimal(0) if resource in NEEDS else Decimal("0.015")
            valid = (
                previous is not None
                and current is not None
                and current > previous
                and abs(before.wallet - state.wallet - Decimal(payload["product"]["price"]))
                <= tolerance
            )
        elif action["kind"] == "take":
            valid = state.phase == "delivering"
        elif action["kind"] == "complete":
            evidence = None if before.trip_id in claimed else completion_evidence(before, state)
            valid = evidence is not None
            if not valid:
                observed = state
                await asyncio.sleep(1)
                state = await ui.snapshot()
                evidence = None if before.trip_id in claimed else completion_evidence(before, state)
                valid = evidence is not None
                if not valid and journal.handoff_complete(action["id"], observed, state):
                    resolved.append(action["id"])
                    continue
        age = (state.observed_at - before.observed_at).total_seconds()
        if age < 0 or (age > 300 and not evidence):
            valid = False
        if valid:
            journal.settle(action["id"], True, state)
            if action["kind"] == "complete" and before.trip_id:
                claimed.add(before.trip_id)
            journal.event(
                action["run_id"],
                "aksi_dipulihkan_dari_bukti",
                {"action_id": action["id"], "evidence": evidence},
            )
            resolved.append(action["id"])
        print(f"Aksi #{action['id']}: {'terverifikasi' if valid else 'belum dapat dipastikan'}.")
    if state is None:
        state = await ui.snapshot()
    journal.sync_game(state, resolved)
    return state


async def wait_until_resolved(ui, journal, settings):
    waiting = False
    transport_outage = False
    while True:
        ui.check_cancel()
        try:
            state = await reconcile(ui, journal)
            transport_outage = False
        except HttpCoreError as exc:
            if exc.category != "transport":
                raise
            state = None
            if not transport_outage:
                queue_error(
                    settings,
                    exc,
                    "worker.reconcile",
                    {
                        "tindakan": "Bot mencoba terhubung kembali otomatis setiap 10 detik. "
                        "Tidak perlu menjalankan ulang. Cek Status untuk memantau."
                    },
                    stop_worker=False,
                )
                transport_outage = True
        pending = journal.unresolved()
        if state is not None and not pending:
            if waiting:
                queue_notice(
                    settings,
                    "✅ Riwayat sudah diperiksa. Bot melanjutkan aktivitas dari status game terbaru.",
                )
            return state
        path = settings.runtime_dir / "status.json"
        try:
            status = json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            status = {}
        status.update(
            pid=os.getpid(),
            event="rekonsiliasi_otomatis",
            stage="worker.reconcile",
            reconciliation_pending=len(pending),
        )
        if state is not None:
            status.update(
                snapshot=state.model_dump(mode="json"), snapshot_received_at=now().isoformat()
            )
        write_private(path, status)
        if not waiting and state is not None:
            queue_notice(
                settings,
                "⏳ Bot sedang memastikan hasil aksi terakhir. Pemeriksaan berjalan otomatis. "
                + "Status akan diperiksa lagi dalam 10 detik.",
            )
        waiting = True
        for _ in range(40):
            ui.check_cancel()
            await asyncio.sleep(0.25)
