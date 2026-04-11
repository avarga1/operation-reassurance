"""
REASSURE TEST FIXTURE — intentionally bad Python.
Expect: god file (LOC), god class (methods), SoC violation (concern mixing).
"""

import logging
import os
import smtplib
import sqlite3
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class GarbageDump:
    """
    One class to rule them all. User management, billing, emails, DB,
    file I/O, and a sprinkle of SMTP — all in one glorious god class.
    """

    def __init__(self, db_path: str = "app.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._ensure_schema()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self, username: str, password: str) -> bool:
        row = self.conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return False
        return row[0] == self._hash(password)

    def logout(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()

    def reset_password(self, username: str, new_password: str) -> None:
        self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (self._hash(new_password), username),
        )
        self.conn.commit()

    def change_password(self, username: str, old: str, new: str) -> bool:
        if not self.login(username, old):
            return False
        self.reset_password(username, new)
        return True

    # ── User CRUD ─────────────────────────────────────────────────────────────

    def create_user(self, username: str, password: str, email: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            (username, self._hash(password), email),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_user(self, username: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, username, email FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "email": row[2]}

    def update_profile(self, username: str, **fields: str) -> None:
        for col, val in fields.items():
            self.conn.execute(
                f"UPDATE users SET {col} = ? WHERE username = ?",
                (val, username),  # noqa: S608
            )
        self.conn.commit()

    def delete_user(self, username: str) -> None:
        self.conn.execute("DELETE FROM users WHERE username = ?", (username,))
        self.conn.commit()

    def list_users(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, username, email FROM users").fetchall()
        return [{"id": r[0], "username": r[1], "email": r[2]} for r in rows]

    # ── Billing ───────────────────────────────────────────────────────────────

    def charge_user(self, username: str, amount_cents: int, description: str) -> str:
        charge_id = os.urandom(8).hex()
        self.conn.execute(
            "INSERT INTO charges (user, amount, description, charge_id) VALUES (?, ?, ?, ?)",
            (username, amount_cents, description, charge_id),
        )
        self.conn.commit()
        self.send_notification(username, f"Charged ${amount_cents / 100:.2f}: {description}")
        return charge_id

    def get_billing_history(self, username: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT charge_id, amount, description FROM charges WHERE user = ?", (username,)
        ).fetchall()
        return [{"id": r[0], "amount": r[1], "desc": r[2]} for r in rows]

    def refund(self, charge_id: str) -> bool:
        row = self.conn.execute(
            "SELECT user, amount FROM charges WHERE charge_id = ?", (charge_id,)
        ).fetchone()
        if not row:
            return False
        username, amount = row
        self.conn.execute(
            "INSERT INTO refunds (charge_id, amount) VALUES (?, ?)", (charge_id, amount)
        )
        self.conn.commit()
        self.send_notification(username, f"Refund of ${amount / 100:.2f} issued.")
        return True

    # ── Notifications / Email ─────────────────────────────────────────────────

    def send_notification(self, username: str, message: str) -> None:
        user = self.get_user(username)
        if not user:
            return
        self._send_email(user["email"], "Notification", message)

    def send_bulk_notification(self, message: str) -> None:
        for user in self.list_users():
            self._send_email(user["email"], "Announcement", message)

    def _send_email(self, to: str, subject: str, body: str) -> None:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = "no-reply@example.com"
        msg["To"] = to
        with smtplib.SMTP("localhost", 25) as s:
            s.sendmail("no-reply@example.com", [to], msg.as_string())

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def get_audit_log(self, username: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT action, ts FROM audit WHERE user = ? ORDER BY ts DESC", (username,)
        ).fetchall()
        return [{"action": r[0], "ts": r[1]} for r in rows]

    def export_audit_log(self, username: str, path: str) -> None:
        log = self.get_audit_log(username)
        with open(path, "w") as f:
            for entry in log:
                f.write(f"{entry['ts']}\t{entry['action']}\n")

    def _log_action(self, username: str, action: str) -> None:
        self.conn.execute("INSERT INTO audit (user, action) VALUES (?, ?)", (username, action))
        self.conn.commit()

    # ── File storage ──────────────────────────────────────────────────────────

    def save_avatar(self, username: str, data: bytes, ext: str = "png") -> str:
        path = f"avatars/{username}.{ext}"
        os.makedirs("avatars", exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        self._log_action(username, f"uploaded avatar {path}")
        return path

    def delete_avatar(self, username: str) -> None:
        for ext in ("png", "jpg", "jpeg", "gif"):
            p = f"avatars/{username}.{ext}"
            if os.path.exists(p):
                os.remove(p)

    def list_avatars(self) -> list[str]:
        if not os.path.isdir("avatars"):
            return []
        return os.listdir("avatars")

    # ── Schema / helpers ──────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS charges (
                charge_id TEXT PRIMARY KEY,
                user TEXT,
                amount INTEGER,
                description TEXT
            );
            CREATE TABLE IF NOT EXISTS refunds (charge_id TEXT, amount INTEGER);
            CREATE TABLE IF NOT EXISTS audit (user TEXT, action TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP);
        """)

    @staticmethod
    def _hash(value: str) -> str:
        import hashlib

        return hashlib.sha256(value.encode()).hexdigest()
