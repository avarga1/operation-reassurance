# REASSURE: expect god_class UserManager (25 methods, violates SRP)
# REASSURE: expect god_file (methods > 20)
#
# One class doing auth, profile management, billing, notifications,
# session handling, audit logging, and a partridge in a pear tree.
# This is what SRP violations look like in the wild.

import hashlib
import json
import smtplib
import sqlite3
from datetime import datetime, timedelta
from typing import Optional


class UserManager:
    """
    Manages users.

    (By "manages" we mean: authenticates, authorizes, creates, deletes,
    updates, bills, notifies, audits, caches, and exports them.
    Because why have five classes when you can have one?)
    """

    def __init__(self, db_path: str, smtp_host: str, stripe_key: str):
        self.db = sqlite3.connect(db_path)
        self.smtp_host = smtp_host
        self.stripe_key = stripe_key
        self._session_cache: dict[str, datetime] = {}
        self._audit_log: list[dict] = []

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> Optional[str]:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        row = self.db.execute(
            "SELECT id FROM users WHERE email=? AND password_hash=?", (email, hashed)
        ).fetchone()
        if row:
            token = hashlib.sha256(f"{row[0]}{datetime.now()}".encode()).hexdigest()
            self._session_cache[token] = datetime.now() + timedelta(hours=24)
            self._record_audit(row[0], "login")
            return token
        return None

    def logout(self, token: str) -> None:
        self._session_cache.pop(token, None)

    def is_authenticated(self, token: str) -> bool:
        expiry = self._session_cache.get(token)
        return expiry is not None and expiry > datetime.now()

    def reset_password(self, email: str) -> bool:
        user = self._get_by_email(email)
        if not user:
            return False
        new_pass = hashlib.sha256(str(datetime.now()).encode()).hexdigest()[:12]
        self.db.execute(
            "UPDATE users SET password_hash=? WHERE email=?",
            (hashlib.sha256(new_pass.encode()).hexdigest(), email),
        )
        self.db.commit()
        self._send_email(email, "Password reset", f"Your new password is: {new_pass}")
        return True

    def change_password(self, user_id: str, old: str, new: str) -> bool:
        old_hash = hashlib.sha256(old.encode()).hexdigest()
        row = self.db.execute(
            "SELECT id FROM users WHERE id=? AND password_hash=?", (user_id, old_hash)
        ).fetchone()
        if not row:
            return False
        new_hash = hashlib.sha256(new.encode()).hexdigest()
        self.db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user_id))
        self.db.commit()
        return True

    # ── Profile ───────────────────────────────────────────────────────────────

    def create_user(self, email: str, name: str, password: str) -> str:
        user_id = hashlib.md5(email.encode()).hexdigest()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        self.db.execute(
            "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?,?,?,?,?)",
            (user_id, email, name, hashed, datetime.now().isoformat()),
        )
        self.db.commit()
        self._send_email(email, "Welcome", f"Hi {name}, welcome aboard!")
        self._record_audit(user_id, "create")
        return user_id

    def get_user(self, user_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT id, email, name, created_at FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "email": row[1], "name": row[2], "created_at": row[3]}

    def update_profile(self, user_id: str, name: str, email: str) -> bool:
        self.db.execute(
            "UPDATE users SET name=?, email=? WHERE id=?", (name, email, user_id)
        )
        self.db.commit()
        self._record_audit(user_id, "update_profile")
        return True

    def delete_user(self, user_id: str) -> bool:
        self.db.execute("DELETE FROM users WHERE id=?", (user_id,))
        self.db.commit()
        self._record_audit(user_id, "delete")
        return True

    def list_users(self) -> list[dict]:
        rows = self.db.execute("SELECT id, email, name FROM users").fetchall()
        return [{"id": r[0], "email": r[1], "name": r[2]} for r in rows]

    # ── Billing ───────────────────────────────────────────────────────────────

    def charge_user(self, user_id: str, amount_cents: int, description: str) -> bool:
        import urllib.request
        payload = json.dumps({
            "amount": amount_cents,
            "currency": "usd",
            "description": description,
        }).encode()
        req = urllib.request.Request(
            "https://api.stripe.com/v1/charges",
            data=payload,
            headers={"Authorization": f"Bearer {self.stripe_key}"},
        )
        try:
            urllib.request.urlopen(req)
            self._record_audit(user_id, f"charge:{amount_cents}")
            return True
        except Exception:
            return False

    def get_billing_history(self, user_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT amount, description, created_at FROM charges WHERE user_id=?", (user_id,)
        ).fetchall()
        return [{"amount": r[0], "description": r[1], "created_at": r[2]} for r in rows]

    def refund(self, user_id: str, charge_id: str) -> bool:
        self._record_audit(user_id, f"refund:{charge_id}")
        return True

    # ── Notifications ─────────────────────────────────────────────────────────

    def send_notification(self, user_id: str, subject: str, body: str) -> None:
        user = self.get_user(user_id)
        if user:
            self._send_email(user["email"], subject, body)

    def send_bulk_notification(self, subject: str, body: str) -> int:
        users = self.list_users()
        sent = 0
        for u in users:
            try:
                self._send_email(u["email"], subject, body)
                sent += 1
            except Exception:
                pass
        return sent

    # ── Audit ─────────────────────────────────────────────────────────────────

    def get_audit_log(self, user_id: Optional[str] = None) -> list[dict]:
        if user_id:
            return [e for e in self._audit_log if e["user_id"] == user_id]
        return list(self._audit_log)

    def export_audit_log(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self._audit_log, f, indent=2, default=str)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_by_email(self, email: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT id, email, name FROM users WHERE email=?", (email,)
        ).fetchone()
        return {"id": row[0], "email": row[1], "name": row[2]} if row else None

    def _send_email(self, to: str, subject: str, body: str) -> None:
        with smtplib.SMTP(self.smtp_host) as server:
            msg = f"Subject: {subject}\n\n{body}"
            server.sendmail("noreply@example.com", to, msg)

    def _record_audit(self, user_id: str, action: str) -> None:
        self._audit_log.append({
            "user_id": user_id,
            "action": action,
            "timestamp": datetime.now(),
        })
