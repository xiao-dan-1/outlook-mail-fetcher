from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import mail_receiver.storage as storage_module
from mail_receiver.imap_client import EmailRecord
from mail_receiver.storage import MailStore, SQLiteMailRepository


def _record(
    *,
    account_email: str = "user@outlook.com",
    mailbox: str = "INBOX",
    uid: str = "1",
    uidvalidity: str = "100",
    subject: str = "Welcome",
    message_id: str | None = None,
) -> EmailRecord:
    return EmailRecord(
        account_email=account_email,
        mailbox=mailbox,
        uid=uid,
        uidvalidity=uidvalidity,
        message_id=(
            message_id if message_id is not None else f"<{uid}-{uidvalidity}@example>"
        ),
        subject=subject,
        sender="sender@example.com",
        recipients=account_email,
        sent_at="2026-07-04T00:00:00+00:00",
        body_preview="hello searchable body",
        raw_message=f"Subject: {subject}\r\n\r\nhello searchable body".encode("utf-8"),
    )


def _unique_index_signatures(
    connection: sqlite3.Connection,
) -> list[tuple[tuple[str, int, str], ...]]:
    signatures = []
    for index_row in connection.execute("PRAGMA index_list(emails)").fetchall():
        if not index_row[2]:
            continue
        index_name = str(index_row[1]).replace('"', '""')
        key_columns = [
            (str(row[2]), int(row[3]), str(row[4]))
            for row in connection.execute(f'PRAGMA index_xinfo("{index_name}")').fetchall()
            if row[5]
        ]
        signatures.append(tuple(key_columns))
    return signatures


def _create_legacy_identity_schema(
    connection: sqlite3.Connection,
    *,
    account_email_declaration: str,
    identity_constraint: str | None,
    additional_statements: tuple[str, ...] = (),
) -> None:
    constraint_sql = f",\n            {identity_constraint}" if identity_constraint else ""
    connection.execute(
        f"""
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_email {account_email_declaration},
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
            fetched_at TEXT NOT NULL DEFAULT (datetime('now')){constraint_sql}
        )
        """
    )
    for statement in additional_statements:
        connection.execute(statement)


def _create_binary_email_schema(connection: sqlite3.Connection) -> None:
    _create_legacy_identity_schema(
        connection,
        account_email_declaration="TEXT NOT NULL",
        identity_constraint="UNIQUE(account_email, mailbox, uidvalidity, uid)",
    )


def _create_wrong_named_secondary_indexes(connection: sqlite3.Connection) -> None:
    for statement in (
        "CREATE INDEX idx_emails_account ON emails(subject)",
        "CREATE INDEX idx_emails_sender ON emails(subject)",
        "CREATE INDEX idx_emails_sent_at ON emails(subject)",
    ):
        connection.execute(statement)


def _insert_legacy_row(
    connection: sqlite3.Connection,
    *,
    email_id: int,
    account_email: str,
    uid: str,
    subject: str,
    sent_at: str,
    fetched_at: str,
    raw_message: bytes,
) -> None:
    connection.execute(
        """
        INSERT INTO emails (
            id, account_email, mailbox, uid, uidvalidity, message_id, subject,
            sender, recipients, sent_at, body_preview, raw_message, fetched_at
        )
        VALUES (?, ?, 'INBOX', ?, '100', ?, ?, 'sender@example.com', ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            account_email,
            uid,
            f"<{email_id}@example>",
            subject,
            account_email,
            sent_at,
            f"preview {subject}",
            raw_message,
            fetched_at,
        ),
    )


def _storage_snapshot(db_path: Path) -> tuple[object, ...]:
    with closing(sqlite3.connect(db_path)) as connection:
        schema = connection.execute(
            """
            SELECT type, name, tbl_name, rootpage, sql
            FROM sqlite_master
            ORDER BY type, name
            """
        ).fetchall()
        rows = connection.execute("SELECT * FROM emails ORDER BY id").fetchall()
        sequence = connection.execute(
            "SELECT name, seq FROM sqlite_sequence ORDER BY name"
        ).fetchall()
        index_list = connection.execute("PRAGMA index_list(emails)").fetchall()
        index_details = []
        for index_row in index_list:
            index_name = str(index_row[1]).replace('"', '""')
            index_details.append(
                (
                    str(index_row[1]),
                    connection.execute(
                        f'PRAGMA index_xinfo("{index_name}")'
                    ).fetchall(),
                )
            )
        return schema, rows, sequence, index_list, index_details


class StorageTests(unittest.TestCase):
    def test_storage_module_publishes_explicit_and_compatibility_names(self) -> None:
        self.assertTrue(
            {"DEFAULT_DB_PATH", "MailStore", "SQLiteMailRepository"}.issubset(
                set(storage_module.__all__)
            )
        )

    def test_explicit_sqlite_repository_name_keeps_mail_store_compatibility(self) -> None:
        self.assertIs(SQLiteMailRepository, MailStore)

    def test_initialize_creates_nocase_account_identity_with_binary_mail_keys(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "mail.sqlite3"
            store = MailStore(db_path)
            store.initialize()

            connection = sqlite3.connect(db_path)
            try:
                table_sql = str(
                    connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'emails'"
                    ).fetchone()[0]
                )
                self.assertRegex(
                    table_sql,
                    r"(?is)account_email\s+TEXT\s+NOT\s+NULL\s+COLLATE\s+NOCASE",
                )
                self.assertEqual(
                    _unique_index_signatures(connection),
                    [
                        (
                            ("account_email", 0, "NOCASE"),
                            ("mailbox", 0, "BINARY"),
                            ("uidvalidity", 0, "BINARY"),
                            ("uid", 0, "BINARY"),
                        )
                    ],
                )
            finally:
                connection.close()

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

    def test_account_email_case_only_identity_conflict_keeps_first_record(self) -> None:
        with TemporaryDirectory() as directory:
            store = MailStore(Path(directory) / "mail.sqlite3")
            store.initialize()

            inserted = store.save_many(
                [
                    _record(account_email="User@Outlook.com", subject="First casing"),
                    _record(account_email="user@outlook.com", subject="Second casing"),
                ]
            )

            self.assertEqual(inserted, 1)
            self.assertEqual(store.count(), 1)
            results = store.search("casing")
            self.assertEqual([result.subject for result in results], ["First casing"])
            self.assertIn(b"First casing", store.get_raw_message(results[0].id) or b"")

    def test_search_account_filter_is_ascii_case_insensitive(self) -> None:
        with TemporaryDirectory() as directory:
            store = MailStore(Path(directory) / "mail.sqlite3")
            store.initialize()
            store.save_many([_record(account_email="User@Outlook.com")])

            results = store.search("searchable", account_email="USER@OUTLOOK.COM")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].account_email, "User@Outlook.com")

    def test_identity_keeps_mailbox_uidvalidity_and_uid_binary(self) -> None:
        with TemporaryDirectory() as directory:
            store = MailStore(Path(directory) / "mail.sqlite3")
            store.initialize()

            inserted = store.save_many(
                [
                    _record(
                        account_email="User@Outlook.com",
                        mailbox="INBOX",
                        uidvalidity="Generation",
                        uid="UID",
                    ),
                    _record(
                        account_email="user@outlook.com",
                        mailbox="inbox",
                        uidvalidity="Generation",
                        uid="UID",
                    ),
                    _record(
                        account_email="user@outlook.com",
                        mailbox="INBOX",
                        uidvalidity="generation",
                        uid="UID",
                    ),
                    _record(
                        account_email="user@outlook.com",
                        mailbox="INBOX",
                        uidvalidity="Generation",
                        uid="uid",
                    ),
                ]
            )

            self.assertEqual(inserted, 4)
            self.assertEqual(store.count(), 4)

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

    def test_initialize_migrates_wrong_unique_key_with_uidvalidity_present(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "mail.sqlite3"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE emails (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_email TEXT NOT NULL COLLATE NOCASE,
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
                        UNIQUE(account_email, mailbox, uid)
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            store = MailStore(db_path)
            store.initialize()

            inserted = store.save_many(
                [
                    _record(uid="1", uidvalidity="100"),
                    _record(uid="1", uidvalidity="200"),
                ]
            )
            self.assertEqual(inserted, 2)

    def test_initialize_migrates_binary_email_schema_deterministically_and_once(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "mail.sqlite3"
            connection = sqlite3.connect(db_path)
            try:
                _create_binary_email_schema(connection)
                _insert_legacy_row(
                    connection,
                    email_id=5,
                    account_email="User@Outlook.com",
                    uid="1",
                    subject="Retained conflict",
                    sent_at="2026-01-05T00:00:00+00:00",
                    fetched_at="2026-02-05 00:00:00",
                    raw_message=b"raw-retained-conflict",
                )
                _insert_legacy_row(
                    connection,
                    email_id=14,
                    account_email="other@outlook.com",
                    uid="2",
                    subject="Retained independent",
                    sent_at="2026-01-14T00:00:00+00:00",
                    fetched_at="2026-02-14 00:00:00",
                    raw_message=b"raw-retained-independent",
                )
                _insert_legacy_row(
                    connection,
                    email_id=30,
                    account_email="user@outlook.com",
                    uid="1",
                    subject="Discarded conflict",
                    sent_at="2026-01-30T00:00:00+00:00",
                    fetched_at="2026-02-28 00:00:00",
                    raw_message=b"raw-discarded-conflict",
                )
                connection.commit()
            finally:
                connection.close()

            store = MailStore(db_path)
            store.initialize()

            connection = sqlite3.connect(db_path)
            try:
                rows = connection.execute(
                    """
                    SELECT id, account_email, subject, sent_at, raw_message, fetched_at
                    FROM emails
                    ORDER BY id
                    """
                ).fetchall()
                self.assertEqual(
                    rows,
                    [
                        (
                            5,
                            "User@Outlook.com",
                            "Retained conflict",
                            "2026-01-05T00:00:00+00:00",
                            b"raw-retained-conflict",
                            "2026-02-05 00:00:00",
                        ),
                        (
                            14,
                            "other@outlook.com",
                            "Retained independent",
                            "2026-01-14T00:00:00+00:00",
                            b"raw-retained-independent",
                            "2026-02-14 00:00:00",
                        ),
                    ],
                )
                schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
                rootpage = int(
                    connection.execute(
                        "SELECT rootpage FROM sqlite_master WHERE type = 'table' AND name = 'emails'"
                    ).fetchone()[0]
                )
                sequence = int(
                    connection.execute(
                        "SELECT seq FROM sqlite_sequence WHERE name = 'emails'"
                    ).fetchone()[0]
                )
                self.assertGreaterEqual(sequence, 30)
            finally:
                connection.close()

            store.initialize()

            connection = sqlite3.connect(db_path)
            try:
                self.assertEqual(
                    int(connection.execute("PRAGMA schema_version").fetchone()[0]),
                    schema_version,
                )
                self.assertEqual(
                    int(
                        connection.execute(
                            "SELECT rootpage FROM sqlite_master "
                            "WHERE type = 'table' AND name = 'emails'"
                        ).fetchone()[0]
                    ),
                    rootpage,
                )
                self.assertEqual(
                    int(
                        connection.execute(
                            "SELECT seq FROM sqlite_sequence WHERE name = 'emails'"
                        ).fetchone()[0]
                    ),
                    sequence,
                )
            finally:
                connection.close()

            self.assertEqual(store.save_many([_record(uid="new")]), 1)
            result = store.search("Welcome", account_email="USER@OUTLOOK.COM")[0]
            self.assertGreater(result.id, 30)

    def test_initialize_rebuilds_every_noncanonical_identity_index_shape(self) -> None:
        cases = (
            (
                "binary column masked by explicit nocase index",
                "TEXT NOT NULL",
                "UNIQUE(account_email COLLATE NOCASE, mailbox, uidvalidity, uid)",
                (),
                False,
            ),
            (
                "extra unique index",
                "TEXT NOT NULL COLLATE NOCASE",
                "UNIQUE(account_email, mailbox, uidvalidity, uid)",
                ("CREATE UNIQUE INDEX legacy_message_unique ON emails(message_id)",),
                True,
            ),
            (
                "partial identity index",
                "TEXT NOT NULL COLLATE NOCASE",
                None,
                (
                    "CREATE UNIQUE INDEX legacy_partial_identity "
                    "ON emails(account_email, mailbox, uidvalidity, uid) "
                    "WHERE subject = 'legacy-only'",
                ),
                False,
            ),
            (
                "descending identity key",
                "TEXT NOT NULL COLLATE NOCASE",
                None,
                (
                    "CREATE UNIQUE INDEX legacy_desc_identity "
                    "ON emails(account_email DESC, mailbox, uidvalidity, uid)",
                ),
                False,
            ),
        )
        expected_signature = [
            (
                ("account_email", 0, "NOCASE"),
                ("mailbox", 0, "BINARY"),
                ("uidvalidity", 0, "BINARY"),
                ("uid", 0, "BINARY"),
            )
        ]

        for (
            name,
            account_declaration,
            identity_constraint,
            statements,
            verify_extra_unique_removed,
        ) in cases:
            with self.subTest(case=name), TemporaryDirectory() as directory:
                db_path = Path(directory) / "mail.sqlite3"
                with closing(sqlite3.connect(db_path)) as connection:
                    _create_legacy_identity_schema(
                        connection,
                        account_email_declaration=account_declaration,
                        identity_constraint=identity_constraint,
                        additional_statements=statements,
                    )
                    connection.commit()

                store = MailStore(db_path)
                store.initialize()

                with closing(sqlite3.connect(db_path)) as connection:
                    table_sql = str(
                        connection.execute(
                            "SELECT sql FROM sqlite_master "
                            "WHERE type = 'table' AND name = 'emails'"
                        ).fetchone()[0]
                    )
                    self.assertRegex(
                        table_sql,
                        r"(?is)account_email\s+TEXT\s+NOT\s+NULL\s+COLLATE\s+NOCASE",
                    )
                    self.assertEqual(
                        _unique_index_signatures(connection),
                        expected_signature,
                    )
                    unique_indexes = [
                        row
                        for row in connection.execute(
                            "PRAGMA index_list(emails)"
                        ).fetchall()
                        if row[2]
                    ]
                    self.assertEqual(len(unique_indexes), 1)
                    self.assertEqual(unique_indexes[0][4], 0)

                self.assertEqual(
                    store.save_many(
                        [
                            _record(
                                account_email="User@Outlook.com",
                                subject="First casing",
                            ),
                            _record(
                                account_email="user@outlook.com",
                                subject="Second casing",
                            ),
                        ]
                    ),
                    1,
                )
                self.assertEqual(
                    len(
                        store.search(
                            "casing",
                            account_email="USER@OUTLOOK.COM",
                        )
                    ),
                    1,
                )

                if verify_extra_unique_removed:
                    self.assertEqual(
                        store.save_many(
                            [
                                _record(uid="2", message_id="<shared@example>"),
                                _record(uid="3", message_id="<shared@example>"),
                            ]
                        ),
                        2,
                    )

    def test_initialize_rolls_back_schema_data_sequence_and_indexes_on_late_failure(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "mail.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                _create_binary_email_schema(connection)
                _create_wrong_named_secondary_indexes(connection)
                _insert_legacy_row(
                    connection,
                    email_id=5,
                    account_email="User@Outlook.com",
                    uid="1",
                    subject="Retained",
                    sent_at="2026-01-05T00:00:00+00:00",
                    fetched_at="2026-02-05 00:00:00",
                    raw_message=b"raw-retained",
                )
                _insert_legacy_row(
                    connection,
                    email_id=40,
                    account_email="deleted@outlook.com",
                    uid="40",
                    subject="Deleted",
                    sent_at="2026-01-30T00:00:00+00:00",
                    fetched_at="2026-02-28 00:00:00",
                    raw_message=b"raw-deleted",
                )
                connection.execute("DELETE FROM emails WHERE id = 40")
                connection.commit()

            before = _storage_snapshot(db_path)
            store = MailStore(db_path)

            def fail_after_rebuild(connection: sqlite3.Connection) -> None:
                table_sql = str(
                    connection.execute(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = 'table' AND name = 'emails'"
                    ).fetchone()[0]
                )
                self.assertIn(
                    "account_email TEXT NOT NULL COLLATE NOCASE",
                    table_sql,
                )
                self.assertIsNone(
                    connection.execute(
                        "SELECT name FROM sqlite_master WHERE name = 'emails_old'"
                    ).fetchone()
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT id, raw_message FROM emails ORDER BY id"
                        ).fetchall()
                    ],
                    [(5, b"raw-retained")],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT seq FROM sqlite_sequence WHERE name = 'emails'"
                    ).fetchone()[0],
                    40,
                )
                raise RuntimeError("injected index creation failure")

            with patch(
                "mail_receiver.storage._create_email_indexes",
                side_effect=fail_after_rebuild,
            ), self.assertRaisesRegex(RuntimeError, "injected index creation failure"):
                store.initialize()

            self.assertEqual(_storage_snapshot(db_path), before)

    def test_initialize_releases_and_recreates_named_secondary_indexes(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "mail.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                _create_binary_email_schema(connection)
                _create_wrong_named_secondary_indexes(connection)
                connection.commit()

            MailStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as connection:
                actual = connection.execute(
                    """
                    SELECT name, tbl_name, sql
                    FROM sqlite_master
                    WHERE type = 'index' AND name LIKE 'idx_emails_%'
                    ORDER BY name
                    """
                ).fetchall()

            expected = [
                (
                    "idx_emails_account",
                    "emails",
                    "CREATE INDEX idx_emails_account ON emails(account_email)",
                ),
                (
                    "idx_emails_sender",
                    "emails",
                    "CREATE INDEX idx_emails_sender ON emails(sender)",
                ),
                (
                    "idx_emails_sent_at",
                    "emails",
                    "CREATE INDEX idx_emails_sent_at ON emails(sent_at)",
                ),
            ]
            self.assertEqual(actual, expected)

    def test_initialize_preserves_sequence_above_old_maximum_id(self) -> None:
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "mail.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                _create_binary_email_schema(connection)
                _insert_legacy_row(
                    connection,
                    email_id=5,
                    account_email="user@outlook.com",
                    uid="1",
                    subject="Retained",
                    sent_at="2026-01-05T00:00:00+00:00",
                    fetched_at="2026-02-05 00:00:00",
                    raw_message=b"raw-retained",
                )
                _insert_legacy_row(
                    connection,
                    email_id=99,
                    account_email="deleted@outlook.com",
                    uid="99",
                    subject="Deleted",
                    sent_at="2026-01-30T00:00:00+00:00",
                    fetched_at="2026-02-28 00:00:00",
                    raw_message=b"raw-deleted",
                )
                connection.execute("DELETE FROM emails WHERE id = 99")
                connection.commit()
                self.assertEqual(
                    connection.execute("SELECT MAX(id) FROM emails").fetchone()[0],
                    5,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT seq FROM sqlite_sequence WHERE name = 'emails'"
                    ).fetchone()[0],
                    99,
                )

            store = MailStore(db_path)
            store.initialize()

            with closing(sqlite3.connect(db_path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT seq FROM sqlite_sequence WHERE name = 'emails'"
                    ).fetchone()[0],
                    99,
                )

            self.assertEqual(
                store.save_many([_record(uid="2", subject="After migration")]),
                1,
            )
            self.assertEqual(store.search("After migration")[0].id, 100)

    def test_ascii_nocase_does_not_fold_or_normalize_non_ascii_accounts(self) -> None:
        with TemporaryDirectory() as directory:
            store = MailStore(Path(directory) / "mail.sqlite3")
            store.initialize()
            account_emails = (
                "Üser@outlook.com",
                "üser@outlook.com",
                "u\u0308ser@outlook.com",
            )

            self.assertEqual(
                store.save_many(
                    [_record(account_email=email) for email in account_emails]
                ),
                3,
            )
            self.assertEqual(store.count(), 3)
            self.assertEqual(len(store.account_counts()), 3)
            for account_email in account_emails:
                with self.subTest(account_email=account_email):
                    results = store.search(
                        "searchable",
                        account_email=account_email,
                    )
                    self.assertEqual(
                        [result.account_email for result in results],
                        [account_email],
                    )


if __name__ == "__main__":
    unittest.main()
