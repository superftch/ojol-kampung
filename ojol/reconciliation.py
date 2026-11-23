"""Reconcile observed results before starting another worker session."""

import asyncio
import json
import os
import re
from decimal import Decimal
from pathlib import Path

from .finance import completion_evidence
from .healing import write_private
from .http_api import HttpCoreError
from .journal import load_journal_snapshot

RESUME_BUTTON = {"inline_keyboard": [[{"text": "▶️ Lanjutkan", "callback_data": "resume"}]]}
from .maintenance import SCHEDULE_FILE, held_window
from .models import NEEDS, now
from .telegram import queue_error, queue_notice


def error_actions(journal, error_id):
    error_id = error_id.upper()
    if not re.fullmatch(r"OJL-[0-9A-F]{12}", error_id):
        raise ValueError("ID error harus berformat OJL- diikuti 12 digit heksadesimal")
    paths = [
        journal.directory / "errors" / f"{error_id}.json",
        journal.directory / "last-error.json",
        *(journal.directory / "notifications").glob("*"),
    ]
    details = None
    for path in paths:
        if not path.is_file() or path.suffix not in {".json", ".sent", ".muted", ".sending"}:
            continue
        try:
            data = json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        data = data.get("context", data)
        if isinstance(data, dict) and data.get("error_id") == error_id:
            details = data
            break
    if details is None:
        raise ValueError(f"ID error {error_id} tidak ditemukan pada akun ini")
    print(
        f"Error {error_id} | {details.get('time')} | {details.get('stage')} | "
        f"{details.get('message')}"
    )
    last_action = details.get("last_action") or {}
    identifiers = details.get("action_ids")
    if identifiers is None:
        identifiers = [last_action["action_id"]] if last_action.get("action_id") else []
    actions = []
    for identifier in dict.fromkeys(identifiers):
        row = journal.db.execute("SELECT * FROM actions WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError(f"Aksi #{identifier} terkait error tidak ditemukan di ledger akun ini")
        if (details.get("run_id") is not None and row["run_id"] != details["run_id"]) or (
            last_action.get("kind") and row["kind"] != last_action["kind"]
        ):
            raise ValueError(f"Konteks aksi #{identifier} tidak cocok dengan error {error_id}")
        actions.append(dict(row))
    if not actions:
        print("Error ini tidak memiliki referensi aksi ledger yang dapat direkonsiliasi.")
    return actions


def report_action(journal, action, state, evidence, reason, error_id):
    before = load_journal_snapshot(action["before_state"])
    payload = json.loads(action["payload"])
    description = {
        "search": "Cari order",
        "take": "Terima order",
        "complete": "Klaim ongkos",
        "study": "Mulai belajar",
        "study_quiz": "Kuis belajar",
    }.get(action["kind"], action["kind"])
    if action["kind"] == "purchase":
        description = (
            f"Beli {payload.get('product', {}).get('name', payload.get('resource', '?'))} "
            f"di {payload.get('shop', '?')}"
        )
    fields = {
        "observed_at",
        "phase",
        "wallet",
        "fuel",
        "condition",
        "data",
        "needs",
        "trip_id",
        "trip",
    }
    row = journal.db.execute("SELECT status FROM actions WHERE id=?", (action["id"],)).fetchone()
    cashflows = [
        dict(row)
        for row in journal.db.execute(
            "SELECT kind,category,amount FROM cashflows WHERE source_key=?",
            (f"action:{action['id']}",),
        )
    ]
    resources = {"fuel", "condition", "data", *before.needs, *state.needs}
    detail = {
        "account": journal.directory.name,
        "error_id": error_id,
        "action_id": action["id"],
        "run_id": action["run_id"],
        "kind": action["kind"],
        "created": action["created"],
        "payload": payload,
        "description": description,
        "status_before": action["status"],
        "status_after": row["status"],
        "reason": reason,
        "evidence": evidence,
        "before": before.model_dump(mode="json", include=fields),
        "observed": state.model_dump(mode="json", include=fields),
        "wallet_delta": str(state.wallet - before.wallet),
        "resource_delta": {
            key: state.resource_value(key) - before.resource_value(key)
            for key in sorted(resources)
            if state.resource_value(key) is not None and before.resource_value(key) is not None
        },
        "cashflows_recorded_for_action": cashflows,
        "cashflows_added": cashflows if action["status"] != "verified" else [],
    }
    print(
        f"Akun {detail['account']} | Aksi #{action['id']} ({description}) | "
        f"{action['status']} → {row['status']} | {reason}",
        flush=True,
    )
    print("Detail rekonsiliasi: " + json.dumps(detail, ensure_ascii=False), flush=True)
    return detail


async def reconcile(ui, journal, error_id=None, action_id=None):
    if error_id and action_id is not None:
        raise ValueError("Pilih salah satu --error-id atau --action-id")
    error_id = error_id.upper() if error_id else None
    if action_id is not None:
        if action_id <= 0:
            raise ValueError("ID aksi harus bilangan positif")
        row = journal.db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise ValueError(f"Aksi #{action_id} tidak ditemukan pada akun ini")
        actions = [dict(row)]
    else:
        actions = error_actions(journal, error_id) if error_id else journal.unresolved()
    if error_id and not actions:
        return None
    maintenance_file = Path(
        os.environ.get("OJOL_MAINTENANCE_FILE", str(journal.directory / SCHEDULE_FILE))
    )
    while held_window(maintenance_file):
        ui.check_cancel()
        await asyncio.sleep(1)
    resolved = []
    reports = []
    claimed = {
        row[0]
        for row in journal.db.execute(
            "SELECT json_extract(before_state, '$.trip_id') FROM actions "
            "WHERE kind='complete' AND status='verified'"
        )
        if row[0]
    }
    state = None
    for action in actions:
        before = load_journal_snapshot(action["before_state"])
        if action["status"] not in {"pending", "uncertain"}:
            print(f"Aksi #{action['id']}: sudah berstatus {action['status']}.")
            reports.append(
                report_action(
                    journal,
                    action,
                    load_journal_snapshot(action["after_state"])
                    if action["after_state"]
                    else before,
                    None,
                    "Aksi sudah ditangani sebelumnya; menampilkan catatan ledger tersimpan.",
                    error_id,
                )
            )
            continue
        state = await ui.snapshot()
        evidence = None
        reason = "Bukti game belum cukup untuk memastikan hasil aksi."
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
                reports.append(
                    report_action(
                        journal,
                        action,
                        state,
                        evidence,
                        "Dua pengamatan konsisten membuktikan status order saat ini. "
                        "Hasil pencarian asli tetap belum pasti; selisih saldo/resource tanpa atribusi.",
                        error_id,
                    )
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
            reason = (
                "Pencarian belum dapat diserahkan ke kondisi terbaru. "
                "Dua pengamatan harus konsisten; order aktif juga perlu kesinambungan "
                "saldo, pendapatan, riwayat, dan resource dengan aksi awal."
            )
        payload = json.loads(action["payload"])
        valid = False
        if action["kind"] == "purchase":
            resource = payload["resource"]
            previous, current = before.resource_value(resource), state.resource_value(resource)
            tolerance = Decimal("0.02")
            price = Decimal(payload["product"]["price"])
            valid = (
                previous is not None
                and current is not None
                and (current > previous or (previous == 100 and current >= 100))
                and (
                    abs(before.wallet - state.wallet - price) <= tolerance
                    or (
                        price == Decimal(0)
                        and (state.wallet >= before.wallet - tolerance or current > previous)
                    )
                )
            )
            reason = (
                "Resource bertambah dan pengurangan saldo cocok dengan harga satu produk."
                if valid
                else f"Pembelian belum terbukti: {resource} {previous} → {current}; "
                f"saldo berkurang {before.wallet - state.wallet} koin, "
                f"harga produk {payload['product']['price']} koin."
            )
            evidence = {
                "resource": resource,
                "previous": previous,
                "current": current,
                "expected_price": payload["product"]["price"],
                "tolerance": str(tolerance),
            }
        elif action["kind"] in {"study", "study_quiz"}:
            status = await ui.study_status(payload["mode"])
            quiz, facility = status["quiz"], status["facility"]
            track_matches = quiz.get("track", {}).get("id") == payload["track"]
            receipt = payload.get("receipt") or {}
            if action["kind"] == "study":
                receipt_matches = (
                    receipt.get("requestId") == payload["request_id"]
                    and receipt.get("projectId") == payload["facility_id"]
                    and receipt.get("priceMilli")
                    == int(Decimal(payload["product"]["price"]) * 1000)
                    and bool(receipt.get("id"))
                )
                new_visit = (
                    quiz.get("available") is True
                    and quiz.get("visitId")
                    and quiz["visitId"] != payload.get("before_visit_id")
                    and track_matches
                    and facility.get("nextAt")
                )
                valid = receipt_matches or bool(
                    new_visit
                    and before.wallet - state.wallet == Decimal(payload["product"]["price"])
                )
            else:
                receipt_matches = (
                    isinstance(receipt.get("track"), dict)
                    and receipt["track"].get("id") == payload["track"]
                    and type(receipt.get("benar")) is int
                    and type(receipt.get("total")) is int
                    and 0 <= receipt["benar"] <= receipt["total"]
                )
                valid = receipt_matches or (
                    quiz.get("available") is False
                    and quiz.get("reason") == "selesai"
                    and track_matches
                    and facility.get("nextAt") == payload.get("next_at")
                )
            evidence = {
                "mode": payload["mode"],
                "track": payload["track"],
                "quiz": quiz,
                "next_at": facility.get("nextAt"),
            }
            reason = (
                "Kunjungan/kuis belajar terkonfirmasi oleh receipt atau status game."
                if valid
                else "Hasil belajar belum terbukti; POST kunjungan/kuis tidak diulang."
            )
        elif action["kind"] == "take":
            valid = state.phase == "delivering"
            evidence = {"phase": state.phase}
            reason = (
                "Game menunjukkan order sedang diantar."
                if valid
                else f"Game masih berfase {state.phase}; penerimaan order belum terbukti."
            )
        elif action["kind"] == "complete":
            evidence = None if before.trip_id in claimed else completion_evidence(before, state)
            valid = evidence is not None
            if not valid:
                observed = state
                await asyncio.sleep(1)
                state = await ui.snapshot()
                evidence = None if before.trip_id in claimed else completion_evidence(before, state)
                valid = evidence is not None
                if not valid:
                    handoff = journal.handoff_action(action["id"], observed, state)
                    if handoff:
                        resolved.append(action["id"])
                        reports.append(
                            report_action(
                                journal,
                                action,
                                state,
                                handoff,
                                "Dua pengamatan konsisten membuktikan game telah berpindah dari trip lama. "
                                "Hasil klaim lama tetap belum pasti; pendapatan belum diatribusikan.",
                                error_id,
                            )
                        )
                        continue
            reason = (
                "Receipt game cocok dengan trip dan waktu klaim."
                if valid
                else f"Receipt untuk trip {before.trip_id or before.trip or '?'} belum cocok "
                "atau sudah dibukukan. Trip yang masih sama menunggu bukti klaim."
            )
        age = (state.observed_at - before.observed_at).total_seconds()
        if age < 0 or (age > 300 and action["kind"] in {"purchase", "take"}):
            valid = False
            reason = (
                f"Waktu bukti di luar jendela verifikasi aksi (0–300 detik), "
                f"selisih {int(age)} detik."
            )
        if (
            age > 300
            and not valid
            and action["kind"] in {"purchase", "take", "study", "study_quiz"}
        ):
            observed = state
            await asyncio.sleep(1)
            state = await ui.snapshot()
            handoff = journal.handoff_action(action["id"], observed, state)
            if handoff:
                resolved.append(action["id"])
                reports.append(
                    report_action(
                        journal,
                        action,
                        state,
                        handoff,
                        "Aksi melewati 5 menit. Dua snapshot stabil menjadi dasar melanjutkan game. "
                        "Hasil transaksi lama tetap belum pasti; pembukuan transaksi tidak ditambahkan.",
                        error_id,
                    )
                )
                continue
            excluded = {"observed_at", "remaining_seconds", "buttons", "raw_text"}
            first = observed.model_dump(exclude=excluded)
            second = state.model_dump(exclude=excluded)
            changed = [key for key in first if first[key] != second[key]]
            evidence["handoff_checks"] = {
                "changed_fields": changed,
                "observation_times": [
                    observed.observed_at.isoformat(),
                    state.observed_at.isoformat(),
                ],
                "phases": [observed.phase, state.phase],
                "remaining_seconds": [observed.remaining_seconds, state.remaining_seconds],
            }
            reason += (
                f" Dua snapshot belum layak diserahkan. Field berubah: {', '.join(changed) or 'nihil'}; "
                f"fase {observed.phase} → {state.phase}. Periksa waktu dan countdown pada detail."
            )
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
        reports.append(report_action(journal, action, state, evidence, reason, error_id))
    if state is None:
        if error_id or action_id is not None:
            return None
        state = await ui.snapshot()
    journal.sync_game(state, resolved, reports)
    return state


async def wait_until_resolved(ui, journal, settings):
    waiting = False
    transport_outage = False
    limit = 6
    for attempt in range(1, limit + 1):
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
                        "tindakan": "Bot mencoba terhubung kembali otomatis setiap 10 detik, "
                        "maksimal 3 pemeriksaan. Cek Status untuk memantau."
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
        if attempt >= 2 and pending and state is not None and not waiting:
            queue_notice(
                settings,
                "🔒 Game sedang terbuka di tempat lain, jadi bot tidak bisa mencocokkan hasil.\n\n"
                "Keluar dari game, lalu tekan tombol Lanjutkan untuk melanjutkan bot.",
                reply_markup=RESUME_BUTTON,
            )
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
            reconciliation_attempt=attempt,
            reconciliation_limit=limit,
        )
        if state is not None:
            status.update(
                snapshot=state.model_dump(mode="json"), snapshot_received_at=now().isoformat()
            )
        if attempt == limit:
            error = HttpCoreError(
                f"Auto rekonsiliasi gagal setelah {limit} percobaan. Bot dihentikan; "
                "hasil transaksi terakhir masih belum pasti.",
                category="reconciliation_failed",
            )
            status.update(event="gagal", reason=str(error))
            write_private(path, status)
            raise error
        write_private(path, status)
        if not waiting and state is not None:
            queue_notice(
                settings,
                "⏳ Bot sedang memastikan hasil aksi terakhir. Pemeriksaan berjalan otomatis. "
                + "Status akan diperiksa lagi dalam 15 detik, maksimal 6 pemeriksaan.",
            )
        waiting = True
        for _ in range(60):
            ui.check_cancel()
            await asyncio.sleep(0.25)
