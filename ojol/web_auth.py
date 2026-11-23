"""Web authentication, session management, and Telegram linking."""

import hashlib
import hmac
import re
import secrets
import time
from typing import Any


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    if not salt:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return digest.hex(), salt


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    """Verify password against stored salt and hash."""
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hash, password_hash)


def verify_telegram_widget(data: dict[str, Any], bot_token: str) -> bool:
    """Verify Telegram Login Widget authentication data."""
    check_hash = data.get("hash")
    if not check_hash or not bot_token:
        return False
    data_check = sorted(f"{k}={v}" for k, v in data.items() if k != "hash")
    data_check_string = "\n".join(data_check)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    hmac_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(hmac_hash, check_hash):
        return False
    try:
        auth_date = int(data.get("auth_date", 0))
        if time.time() - auth_date > 86400:  # 24 hours
            return False
    except (ValueError, TypeError):
        return False
    return True


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
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS telegram_link_codes (
                    code TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES web_users(id),
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS telegram_login_codes (
                    code TEXT PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    expires_at REAL NOT NULL
                );
            """)
            try:
                db.execute(
                    "ALTER TABLE web_users ADD COLUMN has_password INTEGER NOT NULL DEFAULT 1"
                )
            except Exception:
                pass

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

            # If no approved admin exists in web_users yet and Telegram is disabled, first user becomes admin
            total_users = db.execute("SELECT COUNT(*) FROM web_users").fetchone()[0]
            if total_users == 0 and not (self.accounts.admin and self.accounts.settings.telegram_enabled):
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

    def authenticate_telegram_widget(self, data: dict[str, Any]) -> dict:
        raw = self.accounts.settings.telegram_bot_token
        bot_token = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw or "")
        if not bot_token:
            raise ValueError("Token bot Telegram belum dikonfigurasi.")
        if not verify_telegram_widget(data, bot_token):
            raise ValueError("Autentikasi Telegram tidak valid atau kedaluwarsa.")
        telegram_id = int(data["id"])
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        username = data.get("username", "")
        return self.login_or_register_telegram(telegram_id, first_name, last_name, username)

    def login_or_register_telegram(
        self, telegram_id: int, first_name: str = "", last_name: str = "", username: str = ""
    ) -> dict:
        display_name = f"{first_name} {last_name}".strip() or username or str(telegram_id)
        is_admin = bool(self.accounts.admin and telegram_id == self.accounts.admin)

        with self.accounts.db() as db:
            row = db.execute(
                "SELECT * FROM web_users WHERE telegram_id=?", (telegram_id,)
            ).fetchone()
            if row:
                user = dict(row)
                if is_admin and user.get("role") != "admin":
                    db.execute(
                        "UPDATE web_users SET role='admin', status='approved' WHERE id=?",
                        (user["id"],),
                    )
                    user["role"] = "admin"
                    user["status"] = "approved"

                if user["status"] == "pending":
                    raise ValueError("Akun Telegram Anda sedang menunggu persetujuan admin.")
                if user["status"] == "rejected":
                    raise ValueError("Akun Telegram Anda ditolak oleh admin.")

                # Keep profile updated
                db.execute(
                    "UPDATE web_users SET name=COALESCE(NULLIF(?,''), name), "
                    "username=COALESCE(NULLIF(?,''), username) WHERE id=?",
                    (display_name, username.lower() if username else None, user["id"]),
                )
                return user

            # Not in web_users yet: check if already in telegram users table
            is_allowed = self.accounts.allowed(telegram_id)
            if is_allowed or is_admin:
                status = "approved"
                role = "admin" if is_admin else "user"
            else:
                status = "pending"
                role = "user"
                # Record access request in telegram access_requests table as well
                try:
                    self.accounts.request_access(telegram_id, display_name, username)
                except ValueError:
                    pass

            # Create web_user
            base_username = username.lower() if username else f"tg_{telegram_id}"
            candidate = base_username
            idx = 1
            while db.execute("SELECT 1 FROM web_users WHERE username=?", (candidate,)).fetchone():
                candidate = f"{base_username}_{idx}"
                idx += 1

            dummy_pwd, salt = hash_password(secrets.token_urlsafe(32))
            cursor = db.execute(
                "INSERT INTO web_users(username, password_hash, salt, name, telegram_id, has_password, status, role, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    candidate,
                    dummy_pwd,
                    salt,
                    display_name,
                    telegram_id,
                    0,
                    status,
                    role,
                    time.time(),
                ),
            )
            user_id = cursor.lastrowid
            if status == "pending":
                raise ValueError("Akun Telegram Anda baru dan sedang menunggu persetujuan admin.")

            row = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            return dict(row)

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
            row = db.execute(
                "SELECT u.* FROM web_sessions s JOIN web_users u ON s.user_id = u.id "
                "WHERE s.token = ? AND s.expires_at > ?",
                (token, time.time()),
            ).fetchone()
            if not row:
                return None
            user = dict(row)
            # Remove sensitive credentials
            user.pop("password_hash", None)
            user.pop("salt", None)
            return user

    def revoke_session(self, token: str):
        if not token:
            return
        with self.accounts.db() as db:
            db.execute("DELETE FROM web_sessions WHERE token=?", (token,))

    def setup_password(self, user_id: int, username: str, password: str) -> dict:
        """Set permanent username and password for user who logged in via Telegram."""
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

    def issue_telegram_login_code(self, telegram_id: int, ttl: int = 600) -> str:
        """Issue 6-digit one-time login code from Telegram bot."""
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = time.time() + ttl
        with self.accounts.db() as db:
            db.execute("DELETE FROM telegram_login_codes WHERE expires_at < ?", (time.time(),))
            db.execute(
                "INSERT OR REPLACE INTO telegram_login_codes(code, telegram_id, expires_at) VALUES(?,?,?)",
                (code, telegram_id, expires_at),
            )
        return code

    def authenticate_telegram_code(self, code: str) -> dict:
        code = (code or "").strip()
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT * FROM telegram_login_codes WHERE code=? AND expires_at > ?",
                (code, time.time()),
            ).fetchone()
            if not row:
                raise ValueError("Kode login tidak valid atau sudah kedaluwarsa.")
            telegram_id = row["telegram_id"]
            db.execute("DELETE FROM telegram_login_codes WHERE code=?", (code,))

        # Get profile from telegram users table if available
        with self.accounts.db() as db:
            tg_user = db.execute(
                "SELECT name, username FROM users WHERE telegram_id=?", (telegram_id,)
            ).fetchone()
            name = tg_user["name"] if tg_user and tg_user["name"] else ""
            uname = tg_user["username"] if tg_user and tg_user["username"] else ""

        return self.login_or_register_telegram(telegram_id, first_name=name, username=uname)

    def issue_telegram_link_code(self, user_id: int, ttl: int = 900) -> str:
        """Issue 6-digit link code for user to type in Telegram bot (/connect <code>)."""
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = time.time() + ttl
        with self.accounts.db() as db:
            db.execute("DELETE FROM telegram_link_codes WHERE expires_at < ?", (time.time(),))
            db.execute(
                "INSERT OR REPLACE INTO telegram_link_codes(code, user_id, expires_at) VALUES(?,?,?)",
                (code, user_id, expires_at),
            )
        return code

    def consume_telegram_link_code(
        self, code: str, telegram_id: int, name: str = "", username: str = ""
    ) -> dict:
        code = (code or "").strip()
        with self.accounts.db() as db:
            row = db.execute(
                "SELECT * FROM telegram_link_codes WHERE code=? AND expires_at > ?",
                (code, time.time()),
            ).fetchone()
            if not row:
                raise ValueError("Kode penghubung tidak valid atau sudah kedaluwarsa.")
            user_id = row["user_id"]
            db.execute("DELETE FROM telegram_link_codes WHERE code=?", (code,))

        return self.link_telegram_to_web_user(user_id, telegram_id, name, username)

    def link_telegram_to_web_user(
        self, user_id: int, telegram_id: int, name: str = "", username: str = ""
    ) -> dict:
        with self.accounts.db() as db:
            # Check if telegram_id was linked to another web_users record.
            # Since the user verified ownership through the Telegram bot (/connect command or widget),
            # release telegram_id from the old record to merge into this account.
            other = db.execute(
                "SELECT id, username FROM web_users WHERE telegram_id=? AND id<>?",
                (telegram_id, user_id),
            ).fetchone()
            if other:
                db.execute("UPDATE web_users SET telegram_id=NULL WHERE id=?", (other["id"],))

            user_row = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            if not user_row:
                raise ValueError("Pengguna web tidak ditemukan.")

            is_admin = bool(self.accounts.admin and telegram_id == self.accounts.admin)
            synthetic = 10_000_000_000 + user_id

            # Check if telegram_id exists in users table
            tg_user = db.execute(
                "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
            ).fetchone()
            if tg_user:
                # Merge synthetic accounts into existing telegram_id
                db.execute("UPDATE accounts SET owner=? WHERE owner=?", (telegram_id, synthetic))
                db.execute("DELETE FROM users WHERE telegram_id=?", (synthetic,))
            else:
                # Insert real telegram_id first before updating accounts to satisfy foreign key
                db.execute(
                    "INSERT INTO users(telegram_id, enabled, max_accounts, name, username) "
                    "SELECT ?, enabled, max_accounts, COALESCE(NULLIF(?,''), name), COALESCE(NULLIF(?,''), username) "
                    "FROM users WHERE telegram_id=?",
                    (telegram_id, name, username, synthetic),
                )
                db.execute("UPDATE accounts SET owner=? WHERE owner=?", (telegram_id, synthetic))
                db.execute("DELETE FROM users WHERE telegram_id=?", (synthetic,))

            # Update web_users record
            db.execute(
                "UPDATE web_users SET telegram_id=?, "
                "role=CASE WHEN ? THEN 'admin' ELSE role END "
                "WHERE id=?",
                (telegram_id, int(is_admin), user_id),
            )
            updated = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            result = dict(updated)
            result.pop("password_hash", None)
            result.pop("salt", None)
            return result

    def disconnect_telegram(self, user_id: int) -> dict:
        with self.accounts.db() as db:
            user = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            if not user or not user["telegram_id"]:
                raise ValueError("Akun tidak memiliki koneksi Telegram.")
            old_tg = user["telegram_id"]
            synthetic = 10_000_000_000 + user_id
            # Transfer accounts to synthetic
            db.execute(
                "INSERT OR IGNORE INTO users(telegram_id, enabled, name, username) VALUES(?,1,?,?)",
                (synthetic, user["name"], user["username"]),
            )
            db.execute("UPDATE accounts SET owner=? WHERE owner=?", (synthetic, old_tg))
            db.execute("UPDATE web_users SET telegram_id=NULL WHERE id=?", (user_id,))
            updated = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            res = dict(updated)
            res.pop("password_hash", None)
            res.pop("salt", None)
            return res

    def get_owner_for_user(self, user: dict) -> int:
        if user.get("telegram_id"):
            return int(user["telegram_id"])
        synthetic = 10_000_000_000 + int(user["id"])
        with self.accounts.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO users(telegram_id, enabled, name, username) VALUES(?,1,?,?)",
                (synthetic, user.get("name"), user.get("username")),
            )
        return synthetic

    def list_users(self) -> list[dict]:
        with self.accounts.db() as db:
            rows = db.execute(
                "SELECT id, username, name, telegram_id, status, role, created_at, decided_by, decided_at "
                "FROM web_users ORDER BY id DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def list_pending(self) -> list[dict]:
        with self.accounts.db() as db:
            rows = db.execute(
                "SELECT id, username, name, telegram_id, status, role, created_at "
                "FROM web_users WHERE status='pending' ORDER BY id ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def review_user(self, user_id: int, admin_id: int, approve: bool) -> dict:
        with self.accounts.db() as db:
            row = db.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise ValueError("Pengguna tidak ditemukan.")
            user = dict(row)
            new_status = "approved" if approve else "rejected"
            db.execute(
                "UPDATE web_users SET status=?, decided_by=?, decided_at=? WHERE id=?",
                (new_status, admin_id, time.time(), user_id),
            )
            # If user has telegram_id, update whitelist in telegram users as well
            if user["telegram_id"]:
                self.accounts.whitelist(
                    user["telegram_id"],
                    enabled=approve,
                    name=user.get("name"),
                    username=user.get("username"),
                    db=db,
                )
            elif approve:
                synthetic = 10_000_000_000 + user_id
                db.execute(
                    "INSERT OR IGNORE INTO users(telegram_id, enabled, name, username) VALUES(?,1,?,?)",
                    (synthetic, user.get("name"), user.get("username")),
                )

            updated = db.execute(
                "SELECT id, username, name, telegram_id, status, role, created_at FROM web_users WHERE id=?",
                (user_id,),
            ).fetchone()
            return dict(updated)
