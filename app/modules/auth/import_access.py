import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path


class LoginAccess:
    """Opaque one-use import tickets and expiring HttpOnly form sessions."""

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "viewer-access.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY,kind TEXT,expires REAL)"
            )
        self.path.chmod(0o600)

    def issue(self, kind, ttl=900):
        token = secrets.token_urlsafe(32)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM tokens WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO tokens VALUES(?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), kind, time.time() + ttl),
            )
        return token

    def expiry(self, token, kind):
        if not token or len(token) > 100:
            return None
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT expires FROM tokens WHERE hash=? AND kind=?",
                (hashlib.sha256(token.encode()).hexdigest(), kind),
            ).fetchone()
        return row[0] if row and row[0] > time.time() else None

    def consume_ticket(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT expires FROM tokens WHERE hash=? AND kind='ticket'", (digest,)
            ).fetchone()
            if not row or row[0] <= time.time():
                return None
            db.execute("DELETE FROM tokens WHERE hash=?", (digest,))
        return self.issue("session")

    def revoke(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM tokens")

    def csrf_token(self, session):
        if not self.expiry(session, "session"):
            return None
        return hmac.new(session.encode(), b"ojol-cookie-import", hashlib.sha256).hexdigest()

    def valid_csrf(self, session, token):
        expected = self.csrf_token(session)
        return bool(expected and isinstance(token, str) and hmac.compare_digest(expected, token))
