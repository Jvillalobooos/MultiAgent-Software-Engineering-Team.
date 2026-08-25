import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


class BankService:
    def __init__(self, database: str | Path) -> None:
        self.connection = sqlite3.connect(database)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS reset_tokens (token TEXT PRIMARY KEY, user_id TEXT, expires TEXT, used INTEGER)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS login_failures (user_id TEXT PRIMARY KEY, count INTEGER)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS transactions (user_id TEXT, sequence INTEGER)"
        )

    def issue_reset_token(self, user_id: str) -> str:
        token = secrets.token_urlsafe(24)
        expires = (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
        self.connection.execute(
            "INSERT INTO reset_tokens VALUES (?, ?, ?, 0)", (token, user_id, expires)
        )
        self.connection.commit()
        return token

    def use_reset_token(self, token: str) -> bool:
        row = self.connection.execute(
            "SELECT expires, used FROM reset_tokens WHERE token = ?", (token,)
        ).fetchone()
        if not row or row[1] or datetime.fromisoformat(row[0]) <= datetime.now(UTC):
            return False
        self.connection.execute("UPDATE reset_tokens SET used = 1 WHERE token = ?", (token,))
        self.connection.commit()
        return True

    def record_failed_login(self, user_id: str) -> None:
        self.connection.execute(
            "INSERT INTO login_failures VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET count=count+1",
            (user_id,),
        )
        self.connection.commit()

    def is_locked(self, user_id: str) -> bool:
        row = self.connection.execute(
            "SELECT count FROM login_failures WHERE user_id = ?", (user_id,)
        ).fetchone()
        return bool(row and row[0] >= 5)

    def add_transactions(self, user_id: str, count: int) -> None:
        self.connection.executemany(
            "INSERT INTO transactions VALUES (?, ?)", [(user_id, index) for index in range(count)]
        )
        self.connection.commit()

    def history(self, authorized_user: str, requested_user: str) -> list[int]:
        if authorized_user != requested_user:
            raise PermissionError("authorization/IDOR denied")
        return [
            row[0]
            for row in self.connection.execute(
                "SELECT sequence FROM transactions WHERE user_id = ? ORDER BY sequence DESC LIMIT 5",
                (requested_user,),
            )
        ]
