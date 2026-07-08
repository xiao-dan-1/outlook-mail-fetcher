from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from mail_receiver.imap_client import EmailRecord
from mail_receiver.storage import MailStore


def _record(*, uid: str = "1", uidvalidity: str = "100", subject: str = "Welcome") -> EmailRecord:
    return EmailRecord(
        account_email="user@outlook.com",
        mailbox="INBOX",
        uid=uid,
        uidvalidity=uidvalidity,
        message_id=f"<{uid}-{uidvalidity}@example>",
        subject=subject,
        sender="sender@example.com",
        recipients="user@outlook.com",
        sent_at="2026-07-04T00:00:00+00:00",
        body_preview="hello searchable body",
        raw_message=f"Subject: {subject}\r\n\r\nhello searchable body".encode("utf-8"),
    )


class StorageTests(unittest.TestCase):
    def test_save_search_and_show(self) -> None:
        with TemporaryDirectory() as directory:
            store = MailStore(Path(directory) / "mail.sqlite3")
            store.initialize()
            inserted = store.save_many([_record()])

            self.assertEqual(inserted, 1)
            self.assertEqual(store.count(), 1)
            results = store.search("searchable")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].subject, "Welcome")
            self.assertIn(b"Subject: Welcome", store.get_raw_message(results[0].id) or b"")

    def test_duplicate_uid_with_same_uidvalidity_is_ignored(self) -> None:
        with TemporaryDirectory() as directory:
            store = MailStore(Path(directory) / "mail.sqlite3")
            store.initialize()
            record = _record(uid="1", uidvalidity="100", subject="One")

            self.assertEqual(store.save_many([record]), 1)
            self.assertEqual(store.save_many([record]), 0)
            self.assertEqual(store.count(), 1)

    def test_same_uid_with_different_uidvalidity_is_inserted(self) -> None:
        with TemporaryDirectory() as directory:
            store = MailStore(Path(directory) / "mail.sqlite3")
            store.initialize()

            inserted = store.save_many(
                [
                    _record(uid="1", uidvalidity="100", subject="Old generation"),
                    _record(uid="1", uidvalidity="200", subject="New generation"),
                ]
            )

            self.assertEqual(inserted, 2)
            self.assertEqual(store.count(), 2)

    def test_initialize_migrates_old_schema_without_losing_rows(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "mail.sqlite3"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE emails (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_email TEXT NOT NULL,
                        mailbox TEXT NOT NULL,
                        uid TEXT NOT NULL,
                        message_id TEXT,
                        subject TEXT NOT NULL DEFAULT '',
                        sender TEXT NOT NULL DEFAULT '',
                        recipients TEXT NOT NULL DEFAULT '',
                        sent_at TEXT,
                        body_preview TEXT NOT NULL DEFAULT '',
                        raw_message BLOB NOT NULL,
                        fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                        UNIQUE(account_email, mailbox, uid)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO emails (
                        account_email, mailbox, uid, message_id, subject, sender,
                        recipients, sent_at, body_preview, raw_message
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "user@outlook.com",
                        "INBOX",
                        "1",
                        "<legacy@example>",
                        "Legacy",
                        "sender@example.com",
                        "user@outlook.com",
                        "2026-07-04T00:00:00+00:00",
                        "legacy body",
                        b"Subject: Legacy\r\n\r\nlegacy body",
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            store = MailStore(db_path)
            store.initialize()

            self.assertEqual(store.count(), 1)
            results = store.search("Legacy")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].uidvalidity, "")
            self.assertIn(b"Subject: Legacy", store.get_raw_message(results[0].id) or b"")
            self.assertEqual(store.save_many([_record(uid="1", uidvalidity="200")]), 1)
            self.assertEqual(store.count(), 2)


if __name__ == "__main__":
    unittest.main()
