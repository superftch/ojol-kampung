import json
import os
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

from .finance import WIB, day_bounds, received_income, report_date
from .models import Snapshot, now
from .planner import SLEEPING_NOTICE


class Journal:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / "history.sqlite3"
        self.db = sqlite3.connect(path, timeout=10)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,started TEXT,ended TEXT,outcome TEXT,settings TEXT);
            CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY,run_id INTEGER REFERENCES runs(id),created TEXT,
                kind TEXT,status TEXT,before_state TEXT,payload TEXT,after_state TEXT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,run_id INTEGER REFERENCES runs(id),created TEXT,event TEXT,data TEXT);
            CREATE TABLE IF NOT EXISTS cashflows(id INTEGER PRIMARY KEY,run_id INTEGER REFERENCES runs(id),source_key TEXT UNIQUE,
                created TEXT,kind TEXT,category TEXT,amount TEXT,detail TEXT);
            CREATE INDEX IF NOT EXISTS cashflows_created ON cashflows(created);
        """)
        self.backfill_cashflows()

    def close(self):
        self.db.close()

    def start(self, settings):
        unresolved = self.db.execute(
            "SELECT id,kind FROM actions WHERE status IN ('pending','uncertain') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if unresolved:
            raise RuntimeError(
                f"Aksi #{unresolved['id']} ({unresolved['kind']}) belum terverifikasi. Periksa history sebelum menjalankan ulang; klik tidak diulang."
            )
        with self.db:
            return self.db.execute(
                "INSERT INTO runs(started,outcome,settings) VALUES(?,?,?)",
                (now().isoformat(), "running", settings.model_dump_json()),
            ).lastrowid

    def finish(self, run_id, outcome):
        with self.db:
            self.db.execute(
                "UPDATE runs SET ended=?,outcome=? WHERE id=?", (now().isoformat(), outcome, run_id)
            )

    def reject_sleeping_search(self, action_id, after):
        row = self.db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
        if not row or row["kind"] != "search" or row["status"] not in {"pending", "uncertain"}:
            return False
        before = Snapshot.model_validate_json(row["before_state"])
        # Waking changes the notice/trip text, so require unchanged effects and no active order.
        if (
            not SLEEPING_NOTICE.search(before.raw_text)
            or before.phase not in {"idle", "sleeping"}
            or after.phase not in {"idle", "sleeping"}
            or after.remaining_seconds is not None
            or sum("Cari order" in button for button in after.buttons) != 1
            or any(
                re.search(
                    r"Mencari|Terima|Ambil|Antar sekarang|Mengantar|Sampai|Selesai",
                    button,
                    re.IGNORECASE,
                )
                for button in after.buttons
            )
            or re.search(r"📍|🏁|→", after.trip or "")
            or after.observed_at < before.observed_at
            or before.observed_at.astimezone(WIB).date() != after.observed_at.astimezone(WIB).date()
            or any(
                getattr(before, field) != getattr(after, field)
                for field in ("wallet", "fuel", "condition", "data", "today_income", "history")
            )
        ):
            return False
        with self.db:
            result = self.db.execute(
                "UPDATE actions SET status='rejected',after_state=? WHERE id=? AND kind='search' AND status IN ('pending','uncertain')",
                (after.model_dump_json(), action_id),
            )
        return result.rowcount == 1

    def begin(self, run_id, kind, state, payload):
        with self.db:
            return self.db.execute(
                "INSERT INTO actions(run_id,created,kind,status,before_state,payload) VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    now().isoformat(),
                    kind,
                    "pending",
                    state.model_dump_json(),
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            ).lastrowid

    def settle(self, action_id, verified, after=None):
        with self.db:
            self.db.execute(
                "UPDATE actions SET status=?,after_state=? WHERE id=?",
                (
                    "verified" if verified else "uncertain",
                    after.model_dump_json() if after else None,
                    action_id,
                ),
            )
            if verified:
                row = self.db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
                return self.record_action_cashflow(row)

    def record_action_cashflow(self, row):
        if not row or row["status"] != "verified" or not row["after_state"]:
            return None
        payload = json.loads(row["payload"])
        before, after = (
            Snapshot.model_validate_json(row["before_state"]),
            Snapshot.model_validate_json(row["after_state"]),
        )
        detail = {
            "action_id": row["id"],
            "wallet_before": str(before.wallet),
            "wallet_after": str(after.wallet),
        }
        if row["kind"] == "purchase" and isinstance(payload.get("product"), dict):
            amount = Decimal(payload["product"]["price"])
            kind, category = "expense", payload["resource"]
            detail.update(shop=payload["shop"], product=payload["product"]["name"])
        elif row["kind"] == "complete":
            observed = received_income(before, after)
            if observed is None:
                return None
            amount, entries = observed
            kind, category = "income", "ojol"
            detail.update(history_entries=entries, source="observed_game_history_received_payout")
        else:
            return None
        self.db.execute(
            "INSERT OR IGNORE INTO cashflows(run_id,source_key,created,kind,category,amount,detail) VALUES(?,?,?,?,?,?,?)",
            (
                row["run_id"],
                f"action:{row['id']}",
                row["created"],
                kind,
                category,
                str(amount),
                json.dumps(detail, ensure_ascii=False),
            ),
        )
        return {"kind": kind, "category": category, "amount": str(amount)}

    def backfill_cashflows(self):
        rows = self.db.execute(
            "SELECT a.* FROM actions a LEFT JOIN cashflows c ON c.source_key='action:'||a.id "
            "WHERE a.status='verified' AND a.kind IN ('purchase','complete') AND c.id IS NULL"
        ).fetchall()
        with self.db:
            for row in rows:
                self.record_action_cashflow(row)

    def observed_income(self, run_id, before, after):
        observed = received_income(before, after)
        if observed is None:
            return None
        amount, entries = observed
        detail = json.dumps(
            {"history_entries": entries, "source": "observed_automatic_completion"},
            ensure_ascii=False,
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO cashflows(run_id,source_key,created,kind,category,amount,detail) VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    f"auto:{before.observed_at.isoformat()}:{detail}",
                    now().isoformat(),
                    "income",
                    "ojol",
                    str(amount),
                    detail,
                ),
            )
        return str(amount)

    def cashflow_filter(self, run_id=None, day=None):
        conditions, values = [], []
        if run_id is not None:
            conditions.append("run_id=?")
            values.append(run_id)
        if day is not None:
            conditions.extend(["created>=?", "created<?"])
            values.extend(day_bounds(day))
        return (" WHERE " + " AND ".join(conditions) if conditions else ""), values

    def profit(self, run_id=None, day=None):
        where, values = self.cashflow_filter(run_id, day)
        rows = self.db.execute(
            "SELECT kind,category,amount FROM cashflows" + where, values
        ).fetchall()
        income = sum(
            (Decimal(row["amount"]) for row in rows if row["kind"] == "income"), Decimal(0)
        )
        expenses = sum(
            (Decimal(row["amount"]) for row in rows if row["kind"] == "expense"), Decimal(0)
        )
        categories = {}
        for row in rows:
            if row["kind"] == "expense":
                categories[row["category"]] = categories.get(row["category"], Decimal(0)) + Decimal(
                    row["amount"]
                )
        return {
            "pendapatan_ojol": str(income),
            "pengeluaran": str(expenses),
            "laba_bersih": str(income - expenses),
            "biaya_per_kategori": {key: str(value) for key, value in categories.items()},
            "trip_tercatat": sum(row["kind"] == "income" for row in rows),
            "pembelian_tercatat": sum(row["kind"] == "expense" for row in rows),
            "basis": "Payout diterima dari riwayat game (angka tampilan); biaya pembelian terverifikasi. Potongan aplikasi sudah termasuk dalam payout.",
        }

    def financial_report(self, day=None, all_time=False):
        day = None if all_time else report_date(day)
        where, values = self.cashflow_filter(day=day)
        runs = self.db.execute(
            "SELECT DISTINCT run_id FROM cashflows" + where + " ORDER BY run_id DESC", values
        ).fetchall()
        return {
            "tanggal": day.isoformat() if day else None,
            "zona_waktu": "Asia/Jakarta",
            "total": self.profit(day=day),
            "per_sesi": [
                {"run_id": row["run_id"], **self.profit(row["run_id"], day)} for row in runs
            ],
            "transaksi_terakhir": [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM cashflows" + where + " ORDER BY id DESC LIMIT 20", values
                )
            ],
        }

    def event(self, run_id, name, data):
        with self.db:
            self.db.execute(
                "INSERT INTO events(run_id,created,event,data) VALUES(?,?,?,?)",
                (
                    run_id,
                    now().isoformat(),
                    name,
                    json.dumps(data, ensure_ascii=False, default=str),
                ),
            )

    def history(self, limit=10):
        return {
            table: [
                dict(row)
                for row in self.db.execute(
                    f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)
                )
            ]
            for table in ("runs", "actions")
        }
