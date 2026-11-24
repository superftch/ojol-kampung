"""Persistent whitelist, quotas and account ownership. No credentials in registry."""

import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from decimal import Decimal
from functools import cached_property
from uuid import uuid4

from .identity import cached_profile

DRAFT_NAME = "Menunggu cookie"


class Accounts:
    def __init__(self, settings):
        self.settings = settings
        settings.runtime_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = settings.runtime_dir / "accounts.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
                    max_accounts INTEGER, selected TEXT,
                    name TEXT, username TEXT
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES users(telegram_id),
                    name TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
                    legacy INTEGER NOT NULL DEFAULT 0, cookie_hash TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
            """)
            for col in ("name TEXT", "username TEXT"):
                try:
                    db.execute(f"ALTER TABLE users ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass
        self.path.chmod(0o600)
        self.apply_db_settings()
        from .cookies import parse_cookie_input

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

    @cached_property
    def web(self):
        from .web_auth import WebAuth

        return WebAuth(self)

    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

    def allowed(self, owner):
        if type(owner) is not int or owner <= 0:
            return False
        with self.db() as db:
            row = db.execute("SELECT enabled FROM users WHERE telegram_id=?", (owner,)).fetchone()
        return bool(row and row[0])

    def owner_for_user(self, user):
        return self.web.get_owner_for_user(user)

    def value(self, name, db=None):
        if db is None:
            with self.db() as connection:
                return self.value(name, connection)
        row = db.execute("SELECT value FROM settings WHERE name=?", (name,)).fetchone()
        if not row:
            return getattr(self.settings, name, None)
        raw = row[0]
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def apply_db_settings(self):
        try:
            with self.db() as db:
                rows = db.execute("SELECT name, value FROM settings").fetchall()
        except sqlite3.OperationalError:
            return
        for r in rows:
            name, raw_val = r["name"], r["value"]
            try:
                val = json.loads(raw_val)
            except Exception:
                val = raw_val
            if hasattr(self.settings, name):
                try:
                    if name in {
                        "threshold",
                        "resource_reserve_percent",
                        "idle_poll_seconds",
                        "max_accounts_per_user",
                        "max_active_workers",
                    }:
                        setattr(
                            self.settings,
                            name,
                            int(val) if val is not None else getattr(self.settings, name),
                        )
                    elif name in {"min_balance", "max_spend"}:
                        setattr(
                            self.settings,
                            name,
                            Decimal(str(val))
                            if val is not None and str(val).strip() != ""
                            else None,
                        )
                    elif name in {"max_jobs", "max_minutes"}:
                        setattr(
                            self.settings,
                            name,
                            int(val) if val is not None and str(val).strip() != "" else None,
                        )
                    elif name in {
                        "smart_thresholds",
                        "auto_start",
                        "tunnel_enabled",
                    }:
                        setattr(self.settings, name, bool(val))
                    elif name in {"ojol_mode", "login_public_url"}:
                        setattr(self.settings, name, str(val))
                except Exception:
                    pass

    def get_all_settings(self) -> dict:
        self.apply_db_settings()
        return {
            "threshold": getattr(self.settings, "threshold", 60),
            "smart_thresholds": getattr(self.settings, "smart_thresholds", True),
            "resource_reserve_percent": getattr(self.settings, "resource_reserve_percent", 20),
            "min_balance": float(getattr(self.settings, "min_balance", 5.0)),
            "max_spend": float(self.settings.max_spend)
            if getattr(self.settings, "max_spend", None) is not None
            else None,
            "max_jobs": getattr(self.settings, "max_jobs", None),
            "max_minutes": getattr(self.settings, "max_minutes", None),
            "idle_poll_seconds": getattr(self.settings, "idle_poll_seconds", 10),
            "ojol_mode": getattr(self.settings, "ojol_mode", "otomatis"),
            "max_accounts_per_user": getattr(self.settings, "max_accounts_per_user", 3),
            "max_active_workers": getattr(self.settings, "max_active_workers", 3),
            "auto_start": getattr(self.settings, "auto_start", True),
            "login_public_url": getattr(self.settings, "login_public_url", "http://localhost:6080"),
            "tunnel_enabled": getattr(self.settings, "tunnel_enabled", False),
        }

    def update_settings(self, updates: dict) -> dict:
        allowed = {
            "threshold",
            "smart_thresholds",
            "resource_reserve_percent",
            "min_balance",
            "max_spend",
            "max_jobs",
            "max_minutes",
            "idle_poll_seconds",
            "ojol_mode",
            "max_accounts_per_user",
            "max_active_workers",
            "auto_start",
            "login_public_url",
            "tunnel_enabled",
        }
        with self.db() as db:
            for k, v in updates.items():
                if k not in allowed:
                    continue
                if v is None or (isinstance(v, str) and v.strip() == ""):
                    if k in {"max_spend", "max_jobs", "max_minutes"}:
                        val = None
                    else:
                        val = v
                elif k in {
                    "threshold",
                    "resource_reserve_percent",
                    "idle_poll_seconds",
                    "max_accounts_per_user",
                    "max_active_workers",
                }:
                    val = int(v)
                elif k in {"min_balance", "max_spend"}:
                    val = float(v)
                elif k in {"max_jobs", "max_minutes"}:
                    val = int(v)
                elif k in {"smart_thresholds", "auto_start", "tunnel_enabled"}:
                    val = bool(v)
                elif k in {"ojol_mode", "login_public_url"}:
                    val = str(v).strip()
                else:
                    val = v

                db.execute(
                    "INSERT OR REPLACE INTO settings(name, value) VALUES(?,?)", (k, json.dumps(val))
                )
        self.apply_db_settings()
        return self.get_all_settings()

    @staticmethod
    def limit(value):
        if not re.fullmatch(r"[0-9]{1,3}", str(value)) or not 1 <= int(value) <= 100:
            raise ValueError("Kirim angka dari 1 sampai 100 untuk batas akun.")
        return int(value)

    @staticmethod
    def owner_id(value):
        if not re.fullmatch(r"[0-9]{1,16}", str(value)) or int(value) <= 0:
            raise ValueError("ID pemilik harus berupa angka positif.")
        return int(value)

    def quota(self, owner, db=None):
        if db is None:
            with self.db() as connection:
                return self.quota(owner, connection)
        row = db.execute("SELECT max_accounts FROM users WHERE telegram_id=?", (owner,)).fetchone()
        return row[0] if row and row[0] is not None else self.value("max_accounts_per_user", db)

    def set_owner_access(
        self, owner, enabled=True, maximum=None, name=None, username=None, db=None
    ):
        owner = self.owner_id(owner)
        maximum = self.limit(maximum) if maximum is not None else None
        if db is None:
            with self.db() as connection:
                return self.set_owner_access(owner, enabled, maximum, name, username, connection)
        name = name.strip() if isinstance(name, str) and name.strip() else None
        username = username.strip() if isinstance(username, str) and username.strip() else None
        db.execute(
            "INSERT INTO users(telegram_id,enabled,max_accounts,name,username) VALUES(?,?,?,?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET enabled=excluded.enabled, "
            "max_accounts=COALESCE(excluded.max_accounts,users.max_accounts), "
            "name=COALESCE(excluded.name, users.name), "
            "username=COALESCE(excluded.username, users.username)",
            (owner, int(enabled), maximum, name, username),
        )

    def set_limit(self, name, value):
        if name not in {"max_accounts_per_user", "max_active_workers"}:
            raise ValueError("Pilihan pengaturan belum dikenali. Buka menu kembali.")
        val = self.limit(value)
        self.update_settings({name: val})

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
            raise ValueError(
                "Akun belum tersedia atau bukan milik Anda. Pilih lagi lewat Akun Saya."
            )
        if not self.allowed(row["owner"]):
            raise ValueError("Akses pemilik akun belum aktif. Hubungi admin.")
        account = dict(row)
        self.scoped_settings(account)
        return account

    def selected(self, owner):
        if not self.allowed(owner):
            raise ValueError("Akses Anda belum aktif. Hubungi admin untuk meminta akses.")
        with self.db() as db:
            row = db.execute("SELECT selected FROM users WHERE telegram_id=?", (owner,)).fetchone()
        return self.get(row[0], owner) if row and row[0] else None

    def select(self, owner, identifier):
        self.get(identifier, owner)
        with self.db() as db:
            db.execute(
                "INSERT INTO users(telegram_id, selected) VALUES(?, ?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET selected=excluded.selected",
                (owner, identifier),
            )

    @staticmethod
    def name(value):
        if not 1 <= len(value.strip()) <= 40 or any(ord(c) < 32 for c in value):
            raise ValueError("Nama akun harus 1 sampai 40 karakter dalam satu baris.")
        return value.strip()

    def create(self, owner, name=DRAFT_NAME):
        if not self.allowed(owner):
            raise ValueError("Akses Anda belum aktif. Hubungi admin untuk meminta akses.")
        name = self.name(name)
        identifier = uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT COUNT(*) FROM accounts WHERE owner=? AND archived=0", (owner,)
            ).fetchone()[0]
            if count >= self.quota(owner, db):
                raise ValueError(
                    "Batas akun tercapai. Arsipkan salah satu akun atau minta admin menambah batas."
                )
            db.execute(
                "INSERT INTO accounts(id,owner,name) VALUES(?,?,?)", (identifier, owner, name)
            )
            db.execute(
                "INSERT INTO users(telegram_id, selected) VALUES(?, ?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET selected=excluded.selected",
                (owner, identifier),
            )
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
                        "Batas akun tercapai. Arsipkan salah satu akun sebelum memulihkan akun ini."
                    )
            db.execute("UPDATE accounts SET archived=? WHERE id=?", (int(archived), identifier))
            db.execute("UPDATE users SET selected=NULL WHERE selected=?", (identifier,))

    def scoped_settings(self, account):
        directory = (
            self.settings.runtime_dir
            if account["legacy"]
            else self.settings.runtime_dir / "accounts" / account["id"]
        )
        profile = cached_profile(directory)
        if profile and profile["nickname"] != account["name"]:
            with self.db() as db:
                db.execute(
                    "UPDATE accounts SET name=? WHERE id=?", (profile["nickname"], account["id"])
                )
            account["name"] = profile["nickname"]
        return self.settings.model_copy(
            update={
                "runtime_dir": directory,
                "account_name": account["name"],
                "tunnel_enabled": False,
            }
        )

    def check_cookie(self, identifier, payload):
        digest = hashlib.sha256(payload["cookies"][0]["value"].encode()).hexdigest()
        with self.db() as db:
            duplicate = db.execute(
                "SELECT id, name, archived FROM accounts WHERE cookie_hash=? AND id<>?",
                (digest, identifier),
            ).fetchone()
        if duplicate:
            name = duplicate["name"]
            archived = " (sedang diarsipkan)" if duplicate["archived"] else ""
            raise ValueError(
                f"Cookie sudah terhubung ke akun lain ('{name}'{archived}). Pilih akun '{name}' lewat Akun Saya."
            )
        return digest

    def bind_cookie(self, identifier, digest):
        with self.db() as db:
            db.execute("UPDATE accounts SET cookie_hash=? WHERE id=?", (digest, identifier))

    def users(self):
        with self.db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT telegram_id AS owner, enabled, max_accounts, selected, name, username "
                    "FROM users ORDER BY telegram_id"
                )
            ]
