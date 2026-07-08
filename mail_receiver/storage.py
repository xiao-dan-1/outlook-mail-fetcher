from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Iterable, Iterator

from .imap_client import EmailRecord


DEFAULT_DB_PATH = Path("mail_store.sqlite3")

EMAILS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_email TEXT NOT NULL,
    mailbox TEXT NOT NULL,
    uid TEXT NOT NULL,
    uidvalidity TEXT NOT NULL DEFAULT '',
    message_id TEXT,
    subject TEXT NOT NULL DEFAULT '',
    sender TEXT NOT NULL DEFAULT '',
    recipients TEXT NOT NULL DEFAULT '',
    sent_at TEXT,
    body_preview TEXT NOT NULL DEFAULT '',
    raw_message BLOB NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_email, mailbox, uidvalidity, uid)
)
"""

EMAIL_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_emails_account ON emails(account_email)",
    "CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(sender)",
    "CREATE INDEX IF NOT EXISTS idx_emails_sent_at ON emails(sent_at)",
)


@dataclass(frozen=True)
class StoredEmail:
    id: int
    account_email: str
    mailbox: str
    uid: str
    uidvalidity: str
    message_id: str | None
    subject: str
    sender: str
    recipients: str
    sent_at: str | None
    body_preview: str


class MailStore:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as connection:
            if _emails_table_exists(connection) and _emails_schema_needs_rebuild(connection):
                _rebuild_emails_table(connection)
            _create_emails_table(connection)
            _create_email_indexes(connection)

    def save_many(self, records: Iterable[EmailRecord]) -> int:
        rows = [
            (
                record.account_email,
                record.mailbox,
                record.uid,
                record.uidvalidity,
                record.message_id,
                record.subject,
                record.sender,
                record.recipients,
                record.sent_at,
                record.body_preview,
                record.raw_message,
            )
            for record in records
        ]
        if not rows:
            return 0

        with self.session() as connection:
            cursor = connection.executemany(
                """
                INSERT OR IGNORE INTO emails (
                    account_email,
                    mailbox,
                    uid,
                    uidvalidity,
                    message_id,
                    subject,
                    sender,
                    recipients,
                    sent_at,
                    body_preview,
                    raw_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return cursor.rowcount

    def search(
        self,
        query: str,
        *,
        account_email: str | None = None,
        limit: int = 20,
    ) -> list[StoredEmail]:
        like = f"%{query}%"
        params: list[object] = [like, like, like, like]
        where = """
            (subject LIKE ?
             OR sender LIKE ?
             OR recipients LIKE ?
             OR body_preview LIKE ?)
        """
        if account_email:
            where += " AND account_email = ?"
            params.append(account_email)
        params.append(limit)

        with self.session() as connection:
            rows = connection.execute(
                f"""
                SELECT id, account_email, mailbox, uid, uidvalidity, message_id,
                       subject, sender, recipients, sent_at, body_preview
                FROM emails
                WHERE {where}
                ORDER BY COALESCE(sent_at, fetched_at) DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_row_to_stored_email(row) for row in rows]

    def get(self, email_id: int) -> StoredEmail | None:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT id, account_email, mailbox, uid, uidvalidity, message_id,
                       subject, sender, recipients, sent_at, body_preview
                FROM emails
                WHERE id = ?
                """,
                (email_id,),
            ).fetchone()
        return _row_to_stored_email(row) if row else None

    def get_raw_message(self, email_id: int) -> bytes | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT raw_message FROM emails WHERE id = ?",
                (email_id,),
            ).fetchone()
        return bytes(row["raw_message"]) if row else None

    def count(self) -> int:
        with self.session() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM emails").fetchone()
        return int(row["total"])

    def account_counts(self) -> dict[str, int]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT account_email, COUNT(*) AS total
                FROM emails
                GROUP BY account_email
                ORDER BY account_email
                """
            ).fetchall()
        return {str(row["account_email"]): int(row["total"]) for row in rows}


def _create_emails_table(connection: sqlite3.Connection) -> None:
    connection.execute(EMAILS_TABLE_SQL)


def _create_email_indexes(connection: sqlite3.Connection) -> None:
    for statement in EMAIL_INDEX_SQL:
        connection.execute(statement)


def _emails_table_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'emails'"
    ).fetchone()
    return row is not None


def _email_columns(connection: sqlite3.Connection, table: str = "emails") -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _emails_schema_needs_rebuild(connection: sqlite3.Connection) -> bool:
    columns = _email_columns(connection)
    if "uidvalidity" not in columns:
        return True
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'emails'"
    ).fetchone()
    table_sql = str(row[0] if row else "")
    normalized = re.sub(r"\s+", "", table_sql.lower())
    return "unique(account_email,mailbox,uidvalidity,uid)" not in normalized


def _rebuild_emails_table(connection: sqlite3.Connection) -> None:
    connection.execute("ALTER TABLE emails RENAME TO emails_old")
    _create_emails_table(connection)
    old_columns = _email_columns(connection, "emails_old")
    uidvalidity_expr = "uidvalidity" if "uidvalidity" in old_columns else "''"
    fetched_at_expr = "fetched_at" if "fetched_at" in old_columns else "datetime('now')"
    connection.execute(
        f"""
        INSERT OR IGNORE INTO emails (
            id,
            account_email,
            mailbox,
            uid,
            uidvalidity,
            message_id,
            subject,
            sender,
            recipients,
            sent_at,
            body_preview,
            raw_message,
            fetched_at
        )
        SELECT
            id,
            account_email,
            mailbox,
            uid,
            {uidvalidity_expr},
            message_id,
            subject,
            sender,
            recipients,
            sent_at,
            body_preview,
            raw_message,
            {fetched_at_expr}
        FROM emails_old
        """
    )
    connection.execute("DROP TABLE emails_old")


def _row_to_stored_email(row: sqlite3.Row) -> StoredEmail:
    return StoredEmail(
        id=int(row["id"]),
        account_email=str(row["account_email"]),
        mailbox=str(row["mailbox"]),
        uid=str(row["uid"]),
        uidvalidity=str(row["uidvalidity"]),
        message_id=row["message_id"],
        subject=str(row["subject"]),
        sender=str(row["sender"]),
        recipients=str(row["recipients"]),
        sent_at=row["sent_at"],
        body_preview=str(row["body_preview"]),
    )
