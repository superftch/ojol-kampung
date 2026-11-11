"""Persistent whitelist, quotas and account ownership. No credentials in registry."""

import hashlib
import re
import sqlite3
import time
from contextlib import closing, contextmanager
from uuid import uuid4


class Accounts:
    def __init__(self, settings):
        self.settings = settings
        self.admin = settings.telegram_chat_id
        settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = settings.runtime_dir / "accounts.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
                    max_accounts INTEGER, selected TEXT
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES users(telegram_id),
                    name TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
                    legacy INTEGER NOT NULL DEFAULT 0, cookie_hash TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS access_requests (
                    id TEXT PRIMARY KEY, telegram_id INTEGER NOT NULL UNIQUE,
                    name TEXT NOT NULL, username TEXT NOT NULL, status TEXT NOT NULL,
                    created REAL NOT NULL, decided_by INTEGER, decided_at REAL
                );
            """)
            if self.admin:
                db.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES(?)", (self.admin,))
                if not db.execute("SELECT 1 FROM accounts WHERE legacy=1").fetchone():
                    identifier = uuid4().hex
                    db.execute(
                        "INSERT INTO accounts(id,owner,name,legacy) VALUES(?,?,?,1)",
                        (identifier, self.admin, "Utama"),
                    )
                    db.execute(
                        "UPDATE users SET selected=? WHERE telegram_id=?", (identifier, self.admin)
                    )
        self.path.chmod(0o600)
        from .session_transfer import parse_cookie_input

        for account in self.list() + self.list(archived=True):
            path = self.scoped_settings(account).runtime_dir / "http-session.json"
            if path.is_file():
                try:
                    digest = self.check_cookie(account["id"], parse_cookie_input(path.read_text()))
                    self.bind_cookie(account["id"], digest)
                except (ValueError, KeyError, TypeError, sqlite3.IntegrityError):
                    raise ValueError(
                        "Sesi akun lama ambigu/duplikat; periksa sebelum startup"
                    ) from None

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def allowed(self, owner):
        if type(owner) is not int or owner <= 0:
            return False
        if owner == self.admin:
            return True
        with self.db() as db:
            row = db.execute("SELECT enabled FROM users WHERE telegram_id=?", (owner,)).fetchone()
        return bool(row and row[0])

    def value(self, name, db=None):
        if db is None:
            with self.db() as connection:
                return self.value(name, connection)
        row = db.execute("SELECT value FROM settings WHERE name=?", (name,)).fetchone()
        return row[0] if row else getattr(self.settings, name)

    @staticmethod
    def limit(value):
        if not re.fullmatch(r"[0-9]{1,3}", str(value)) or not 1 <= int(value) <= 100:
            raise ValueError("❌ Batas harus angka 1–100.")
        return int(value)

    @staticmethod
    def owner_id(value):
        if not re.fullmatch(r"[0-9]{1,16}", str(value)) or int(value) <= 0:
            raise ValueError("❌ Telegram ID harus angka. Contoh: 123456789")
        return int(value)

    def quota(self, owner, db=None):
        if db is None:
            with self.db() as connection:
                return self.quota(owner, connection)
        row = db.execute("SELECT max_accounts FROM users WHERE telegram_id=?", (owner,)).fetchone()
        return row[0] if row and row[0] is not None else self.value("max_accounts_per_user", db)

    def whitelist(self, owner, enabled=True, maximum=None, db=None):
        owner = self.owner_id(owner)
        if owner == self.admin and not enabled:
            raise ValueError("🔒 Akses admin utama tidak bisa dicabut.")
        maximum = self.limit(maximum) if maximum is not None else None
        if db is None:
            with self.db() as connection:
                return self.whitelist(owner, enabled, maximum, connection)
        db.execute(
            "INSERT INTO users(telegram_id,enabled,max_accounts) VALUES(?,?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET enabled=excluded.enabled, "
            "max_accounts=COALESCE(excluded.max_accounts,users.max_accounts)",
            (owner, int(enabled), maximum),
        )
        db.execute(
            "UPDATE access_requests SET status=?,decided_by=?,decided_at=? WHERE telegram_id=?",
            ("approved" if enabled else "rejected", self.admin, time.time(), owner),
        )

    def access_request(self, owner):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM access_requests WHERE telegram_id=?", (owner,)
            ).fetchone()
        return dict(row) if row else None

    def request_access(self, owner, name, username):
        owner = self.owner_id(owner)
        if self.allowed(owner):
            raise ValueError("ℹ️ User ini sudah diizinkan.")
        name = (
            " ".join("".join(c for c in name if c.isprintable() or c.isspace()).split())[:128]
            or "Tanpa nama"
        )
        username = username if re.fullmatch(r"[A-Za-z0-9_]{1,64}", username) else ""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM access_requests WHERE telegram_id=?", (owner,)
            ).fetchone()
            if row:
                return dict(row), False
            identifier = uuid4().hex
            db.execute(
                "INSERT INTO access_requests(id,telegram_id,name,username,status,created) VALUES(?,?,?,?,?,?)",
                (identifier, owner, name, username, "pending", time.time()),
            )
            row = db.execute("SELECT * FROM access_requests WHERE id=?", (identifier,)).fetchone()
        return dict(row), True

    def access_requests(self):
        with self.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM access_requests WHERE status='pending' ORDER BY created,id"
                )
            ]

    def request_by_id(self, identifier):
        with self.db() as db:
            row = db.execute("SELECT * FROM access_requests WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise ValueError("❌ Pengajuan tidak ditemukan.")
        return dict(row)

    def review_request(self, identifier, admin, approve):
        if not self.admin or admin != self.admin:
            raise ValueError("🔒 Pengajuan hanya bisa diproses admin.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM access_requests WHERE id=?", (identifier,)).fetchone()
            if not row or row["status"] != "pending":
                raise ValueError("ℹ️ Pengajuan sudah diproses atau tidak ditemukan.")
            self.whitelist(row["telegram_id"], enabled=approve, db=db)
            return dict(
                db.execute("SELECT * FROM access_requests WHERE id=?", (identifier,)).fetchone()
            )

    def set_limit(self, name, value):
        if name not in {"max_accounts_per_user", "max_active_workers"}:
            raise ValueError("❌ Pengaturan tidak dikenal.")
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (name, self.limit(value)))

    def list(self, owner=None, archived=False):
        with self.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,owner,name,archived,legacy FROM accounts WHERE archived=? "
                    "AND (? IS NULL OR owner=?) ORDER BY rowid",
                    (int(archived), owner, owner),
                )
            ]

    def get(self, identifier, owner=None, archived=False):
        with self.db() as db:
            row = db.execute("SELECT * FROM accounts WHERE id=?", (identifier,)).fetchone()
        if (
            not row
            or bool(row["archived"]) != archived
            or (owner is not None and row["owner"] != owner)
        ):
            raise ValueError("❌ Akun tidak ditemukan atau bukan milik Anda.")
        if not self.allowed(row["owner"]):
            raise ValueError("🔒 Pemilik akun ini belum diizinkan.")
        return dict(row)

    def selected(self, owner):
        if not self.allowed(owner):
            raise ValueError("🔒 User ini belum diizinkan.")
        with self.db() as db:
            row = db.execute("SELECT selected FROM users WHERE telegram_id=?", (owner,)).fetchone()
        return self.get(row[0], owner) if row and row[0] else None

    def select(self, owner, identifier):
        self.get(identifier, owner)
        with self.db() as db:
            db.execute("UPDATE users SET selected=? WHERE telegram_id=?", (identifier, owner))

    @staticmethod
    def name(value):
        if not 1 <= len(value.strip()) <= 40 or any(ord(c) < 32 for c in value):
            raise ValueError("❌ Nama akun harus 1–40 huruf, dalam satu baris.")
        return value.strip()

    def create(self, owner, name):
        if not self.allowed(owner):
            raise ValueError("🔒 User ini belum diizinkan.")
        name = self.name(name)
        identifier = uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT COUNT(*) FROM accounts WHERE owner=? AND archived=0", (owner,)
            ).fetchone()[0]
            if count >= self.quota(owner, db):
                raise ValueError(
                    "Batas akun tercapai; arsipkan akun atau minta admin menaikkan batas"
                )
            db.execute(
                "INSERT INTO accounts(id,owner,name) VALUES(?,?,?)", (identifier, owner, name)
            )
            db.execute("UPDATE users SET selected=? WHERE telegram_id=?", (identifier, owner))
        return self.get(identifier, owner)

    def rename(self, owner, identifier, name):
        self.get(identifier, owner)
        with self.db() as db:
            db.execute("UPDATE accounts SET name=? WHERE id=?", (self.name(name), identifier))

    def archive(self, owner, identifier, archived=True):
        self.get(identifier, owner, archived=not archived)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not archived:
                count = db.execute(
                    "SELECT COUNT(*) FROM accounts WHERE owner=? AND archived=0", (owner,)
                ).fetchone()[0]
                if count >= self.quota(owner, db):
                    raise ValueError(
                        "⚠️ Jumlah akun sudah penuh. Arsipkan akun lain atau hubungi admin."
                    )
            db.execute("UPDATE accounts SET archived=? WHERE id=?", (int(archived), identifier))
            db.execute("UPDATE users SET selected=NULL WHERE selected=?", (identifier,))

    def scoped_settings(self, account):
        return self.settings.model_copy(
            update={
                "runtime_dir": self.settings.runtime_dir
                if account["legacy"]
                else self.settings.runtime_dir / "accounts" / account["id"],
                "telegram_chat_id": account["owner"],
                "account_name": account["name"],
                "tunnel_enabled": False,
            }
        )

    def check_cookie(self, identifier, payload):
        digest = hashlib.sha256(payload["cookies"][0]["value"].encode()).hexdigest()
        with self.db() as db:
            duplicate = db.execute(
                "SELECT 1 FROM accounts WHERE cookie_hash=? AND id<>?", (digest, identifier)
            ).fetchone()
        if duplicate:
            raise ValueError("⚠️ Cookie ini sudah dipakai akun lain. Pakai akun itu saja.")
        return digest

    def bind_cookie(self, identifier, digest):
        with self.db() as db:
            db.execute("UPDATE accounts SET cookie_hash=? WHERE id=?", (digest, identifier))

    def users(self):
        with self.db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM users ORDER BY telegram_id")]
