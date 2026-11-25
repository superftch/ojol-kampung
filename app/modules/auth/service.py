"""Web credentials, sessions, and existing account ownership."""

import contextlib
import re
import secrets
import time

from app.core.security import hash_password, verify_password


def web_owner_id(user):
    return int(user["telegram_id"]) if user.get("telegram_id") else 10_000_000_000 + int(user["id"])


class WebAuth:
    """Authentication and session manager for web interface."""

    def __init__(self, accounts):
        self.accounts = accounts
        self.ensure_tables()

    def ensure_tables(self):
        with self.accounts.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS web_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    name TEXT,
                    telegram_id INTEGER UNIQUE,
                    has_password INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at REAL NOT NULL,
                    decided_by INTEGER,
                    decided_at REAL
                );
                CREATE TABLE IF NOT EXISTS web_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES web_users(id),
                    expires_at REAL NOT NULL,
                    parent_token TEXT REFERENCES web_sessions(token) ON DELETE CASCADE
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            with contextlib.suppress(Exception):
                db.execute(
                    "ALTER TABLE web_users ADD COLUMN has_password INTEGER NOT NULL DEFAULT 1"
                )
            if not any(
                col["name"] == "parent_token"
                for col in db.execute("PRAGMA table_info(web_sessions)")
            ):
                db.execute(
                    "ALTER TABLE web_sessions ADD COLUMN parent_token TEXT "
                    "REFERENCES web_sessions(token) ON DELETE CASCADE"
                )

    def validate_username(self, username: str) -> str:
        username = (username or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9_]{3,32}", username):
            raise ValueError(
                "Username harus 3-32 karakter alfanumerik (huruf kecil, angka, atau underscore)."
            )
        return username

    def validate_password(self, password: str) -> str:
        if not password or len(password) < 6:
            raise ValueError("Password minimal 6 karakter.")
        if len(password) > 128:
            raise ValueError("Password terlalu panjang (maksimal 128 karakter).")
        return password

    def register(self, username: str, password: str, name: str = "") -> dict:
        username = self.validate_username(username)
        password = self.validate_password(password)
        name = " ".join((name or "").strip().split())[:64] or username

        with self.accounts.db() as db:
            existing = db.execute(
                "SELECT id FROM web_users WHERE username=?", (username,)
            ).fetchone()
            if existing:
                raise ValueError("Username sudah terdaftar. Silakan pilih username lain.")

            if db.execute("SELECT COUNT(*) FROM web_users").fetchone()[0] == 0:
                status = "approved"
                role = "admin"
            else:
                status = "pending"
                role = "user"

            pwd_hash, salt = hash_password(password)
            now_ts = time.time()
            cursor = db.execute(
                "INSERT INTO web_users(username, password_hash, salt, name, status, role, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (username, pwd_hash, salt, name, status, role, now_ts),
            )
            user_id = cursor.lastrowid

            # If approved, ensure synthetic owner row in users table
            if status == "approved":
                synthetic = 10_000_000_000 + user_id
                db.execute(
                    "INSERT OR IGNORE INTO users(telegram_id, enabled, name, username) VALUES(?,1,?,?)",
                    (synthetic, name, username),
                )

            row = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            return dict(row)

    def authenticate_password(self, username: str, password: str) -> dict:
        username = (username or "").strip().lower()
        with self.accounts.db() as db:
            row = db.execute("SELECT * FROM web_users WHERE username=?", (username,)).fetchone()
            if not row:
                raise ValueError("Username atau password salah.")
            user = dict(row)
            if not verify_password(password, user["salt"], user["password_hash"]):
                raise ValueError("Username atau password salah.")

            if user["status"] == "pending":
                raise ValueError("Akun Anda sedang menunggu persetujuan admin.")
            if user["status"] == "rejected":
                raise ValueError("Akun Anda telah ditolak atau dinonaktifkan oleh admin.")

            # Ensure user has owner row in users
            owner = self.get_owner_for_user(user)
            db.execute(
                "INSERT OR IGNORE INTO users(telegram_id, enabled, name, username) VALUES(?,1,?,?)",
                (owner, user.get("name"), user.get("username")),
            )
            return user

    def issue_session(self, user_id: int, ttl: int = 604800) -> str:
        """Create session token valid for 7 days."""
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + ttl
        with self.accounts.db() as db:
            db.execute("DELETE FROM web_sessions WHERE expires_at < ?", (time.time(),))
            db.execute(
                "INSERT INTO web_sessions(token, user_id, expires_at) VALUES(?,?,?)",
                (token, user_id, expires_at),
            )
        return token

    def get_user_by_session(self, token: str) -> dict | None:
        if not token or len(token) > 128:
            return None
        with self.accounts.db() as db:
            current = time.time()
            row = db.execute(
                """SELECT u.*, s.parent_token IS NOT NULL AS impersonating
                   FROM web_sessions s JOIN web_users u ON s.user_id = u.id
                   WHERE s.token=? AND s.expires_at>? AND (
                     s.parent_token IS NULL OR (u.status='approved' AND u.role='user' AND EXISTS (
                       SELECT 1 FROM web_sessions parent JOIN web_users admin ON admin.id=parent.user_id
                       WHERE parent.token=s.parent_token AND parent.expires_at>?
                         AND admin.status='approved' AND admin.role='admin'
                     ))
                   )""",
                (token, current, current),
            ).fetchone()
            if not row:
                return None
            user = dict(row)
            # Remove sensitive credentials
            user.pop("password_hash", None)
            user.pop("salt", None)
            if not user.pop("impersonating"):
                return user
            user["impersonating"] = True
            return user

    def issue_impersonation(self, parent_token: str, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        current = time.time()
        with self.accounts.db() as db:
            row = db.execute(
                """INSERT INTO web_sessions(token, user_id, expires_at, parent_token)
                   SELECT ?, target.id, MIN(parent.expires_at, ?), parent.token
                   FROM web_sessions parent JOIN web_users admin ON admin.id=parent.user_id
                   JOIN web_users target ON target.id=?
                   WHERE parent.token=? AND parent.expires_at>? AND parent.parent_token IS NULL
                     AND admin.status='approved' AND admin.role='admin'
                     AND target.status='approved' AND target.role='user'""",
                (token, current + 3600, user_id, parent_token, current),
            )
            if not row.rowcount:
                raise ValueError("Hanya pengguna non-admin yang disetujui dapat dibuka.")
        return token

    def end_impersonation(self, token, parent_token) -> bool:
        parent = self.get_user_by_session(parent_token)
        if not parent or parent["role"] != "admin" or parent["status"] != "approved":
            return False
        with self.accounts.db() as db:
            child = db.execute(
                "SELECT parent_token FROM web_sessions WHERE token=?", (token,)
            ).fetchone()
            if child and child[0] != parent_token:
                return False
            db.execute(
                "DELETE FROM web_sessions WHERE token=? AND parent_token=?", (token, parent_token)
            )
        return True

    def revoke_session(self, token: str):
        if not token:
            return
        with self.accounts.db() as db:
            db.execute("DELETE FROM web_sessions WHERE token=?", (token,))

    def setup_password(self, user_id: int, username: str, password: str) -> dict:
        """Set web credentials for an existing user."""
        username = self.validate_username(username)
        password = self.validate_password(password)
        with self.accounts.db() as db:
            user = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            if not user:
                raise ValueError("Pengguna tidak ditemukan.")

            existing = db.execute(
                "SELECT id FROM web_users WHERE username=? AND id<>?",
                (username, user_id),
            ).fetchone()
            if existing:
                raise ValueError("Username sudah digunakan. Silakan pilih username lain.")

            pwd_hash, salt = hash_password(password)
            db.execute(
                "UPDATE web_users SET username=?, password_hash=?, salt=?, has_password=1 WHERE id=?",
                (username, pwd_hash, salt, user_id),
            )
            updated = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            result = dict(updated)
            result.pop("password_hash", None)
            result.pop("salt", None)
            return result

    def recover_password(self, username: str, password: str) -> None:
        password = self.validate_password(password)
        with self.accounts.db() as db:
            user = db.execute(
                "SELECT id FROM web_users WHERE username=? AND status='approved'", (username,)
            ).fetchone()
            if not user:
                raise ValueError("Pengguna web aktif tidak ditemukan.")
            digest, salt = hash_password(password)
            db.execute(
                "UPDATE web_users SET password_hash=?, salt=?, has_password=1 WHERE id=?",
                (digest, salt, user["id"]),
            )
            db.execute("DELETE FROM web_sessions WHERE user_id=?", (user["id"],))

    def get_owner_for_user(self, user: dict) -> int:
        if user.get("telegram_id"):
            return int(user["telegram_id"])
        synthetic = web_owner_id(user)
        with self.accounts.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO users(telegram_id, enabled, name, username) VALUES(?,1,?,?)",
                (synthetic, user.get("name"), user.get("username")),
            )
            if user.get("role") == "admin":
                # Adopt the root account only when its old owner has no web identity.
                legacy = db.execute(
                    "SELECT DISTINCT owner FROM accounts WHERE legacy=1 AND owner<>? "
                    "AND owner<? AND NOT EXISTS (SELECT 1 FROM web_users WHERE telegram_id=owner)",
                    (synthetic, 10_000_000_000),
                ).fetchall()
                if len(legacy) == 1:
                    old_owner = legacy[0]["owner"]
                    db.execute("UPDATE accounts SET owner=? WHERE owner=?", (synthetic, old_owner))
                    db.execute(
                        "UPDATE users SET selected=COALESCE(selected, "
                        "(SELECT selected FROM users WHERE telegram_id=?)) WHERE telegram_id=?",
                        (old_owner, synthetic),
                    )
        return synthetic

    def list_users(self) -> list[dict]:
        with self.accounts.db() as db:
            rows = db.execute(
                "SELECT id, username, name, telegram_id, has_password, status, role, created_at, decided_by, decided_at "
                "FROM web_users ORDER BY id DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_user(self, user_id: int) -> dict:
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT id, username, name, telegram_id, status, role FROM web_users WHERE id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Pengguna tidak ditemukan.")
        return dict(row)

    def list_pending(self) -> list[dict]:
        with self.accounts.db() as db:
            rows = db.execute(
                "SELECT id, username, name, telegram_id, status, role, created_at "
                "FROM web_users WHERE status='pending' ORDER BY id ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def set_account_limit(self, user_id: int, maximum: int) -> None:
        with self.accounts.db() as db:
            user = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            if user is None or user["status"] != "approved":
                raise ValueError("Pengguna aktif tidak ditemukan.")
            owner = web_owner_id(dict(user))
            self.accounts.set_owner_access(owner, maximum=maximum, db=db)

    def review_user(self, user_id: int, admin_id: int, approve: bool) -> dict:
        with self.accounts.db() as db:
            row = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Pengguna tidak ditemukan.")
            user = dict(row)
            if user["role"] == "admin" and not approve:
                raise ValueError("Akses administrator tidak dapat dicabut.")
            new_status = "approved" if approve else "rejected"
            db.execute(
                "UPDATE web_users SET status=?, decided_by=?, decided_at=? WHERE id=?",
                (new_status, admin_id, time.time(), user_id),
            )
            owner = web_owner_id(user)
            self.accounts.set_owner_access(
                owner, enabled=approve, name=user.get("name"), username=user.get("username"), db=db
            )
            if not approve:
                db.execute("DELETE FROM web_sessions WHERE user_id=?", (user_id,))

            updated = db.execute(
                "SELECT id, username, name, telegram_id, status, role, created_at FROM web_users WHERE id=?",
                (user_id,),
            ).fetchone()
            return dict(updated)
