from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import io
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mail_receiver import cli
from mail_receiver.imap_client import EmailRecord
from mail_receiver.storage import DEFAULT_DB_PATH, MailStore


def _record(*, uid: str = "1", subject: str = "Needle") -> EmailRecord:
    return EmailRecord(
        account_email="user@outlook.com",
        mailbox="INBOX",
        uid=uid,
        uidvalidity="100",
        message_id=None,
        subject=subject,
        sender="sender@example.com",
        recipients="user@outlook.com",
        sent_at=None,
        body_preview="needle",
        raw_message=b"raw",
    )


class CliFetchTests(unittest.TestCase):
    def test_cli_exposes_version_flag(self) -> None:
        output = io.StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stdout(output):
            cli.build_parser().parse_args(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertRegex(output.getvalue(), r"Outlook Mail Fetcher \d+\.\d+\.\d+")

    def test_common_options_parse_before_or_after_every_subcommand(self) -> None:
        parser = cli.build_parser()
        command_arguments = {
            "inspect-accounts": ["accounts.txt"],
            "fetch": ["accounts.txt"],
            "search": ["--query", "welcome"],
            "show": ["1"],
        }

        for command, arguments in command_arguments.items():
            with self.subTest(command=command, position="before"):
                parsed = parser.parse_args(
                    ["--db", "before.sqlite3", "--debug", command, *arguments]
                )
                self.assertEqual(parsed.db, "before.sqlite3")
                self.assertTrue(parsed.debug)

            with self.subTest(command=command, position="after"):
                parsed = parser.parse_args(
                    [command, *arguments, "--db", "after.sqlite3", "--debug"]
                )
                self.assertEqual(parsed.db, "after.sqlite3")
                self.assertTrue(parsed.debug)

    def test_subparser_defaults_do_not_override_root_common_options(self) -> None:
        parsed = cli.build_parser().parse_args(
            ["--db", "root.sqlite3", "--debug", "fetch", "accounts.txt"]
        )

        self.assertEqual(parsed.db, "root.sqlite3")
        self.assertTrue(parsed.debug)

    def test_root_common_options_keep_real_defaults(self) -> None:
        parsed = cli.build_parser().parse_args(["fetch", "accounts.txt"])

        self.assertEqual(parsed.db, str(DEFAULT_DB_PATH))
        self.assertFalse(parsed.debug)

    def test_trailing_db_overrides_root_db(self) -> None:
        parsed = cli.build_parser().parse_args(
            [
                "--db",
                "before.sqlite3",
                "fetch",
                "accounts.txt",
                "--db",
                "after.sqlite3",
            ]
        )

        self.assertEqual(parsed.db, "after.sqlite3")

    def test_fetch_rejects_negative_limit_before_database_or_network_work(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            account_file = base / "accounts.txt"
            database = base / "mail.sqlite3"
            account_file.write_text(
                "ok@outlook.com----password----client----refresh\n",
                encoding="utf-8",
            )
            error = io.StringIO()

            with patch("mail_receiver.cli.fetch_messages") as real_fetch, patch(
                "mail_receiver.cli.mock_messages"
            ) as mock_fetch, self.assertRaises(SystemExit) as raised, redirect_stderr(error):
                cli.main(
                    [
                        "fetch",
                        str(account_file),
                        "--limit",
                        "-1",
                        "--db",
                        str(database),
                    ]
                )

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("--limit", error.getvalue())
            self.assertIn("non-negative", error.getvalue())
            self.assertFalse(database.exists())
            real_fetch.assert_not_called()
            mock_fetch.assert_not_called()

    def test_limit_rejects_non_integer_with_a_clear_parser_error(self) -> None:
        error = io.StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stderr(error):
            cli.build_parser().parse_args(
                ["fetch", "accounts.txt", "--limit", "not-a-number"]
            )

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--limit", error.getvalue())
        self.assertIn("integer", error.getvalue())
        self.assertIn("not-a-number", error.getvalue())

    def test_search_rejects_negative_limit_instead_of_returning_every_row(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "mail.sqlite3"
            store = MailStore(database)
            store.initialize()
            store.save_many(
                [_record(uid=str(uid), subject=f"Needle {uid}") for uid in range(2)]
            )
            output = io.StringIO()
            error = io.StringIO()

            with self.assertRaises(SystemExit) as raised, redirect_stdout(
                output
            ), redirect_stderr(error):
                cli.main(
                    [
                        "--db",
                        str(database),
                        "search",
                        "--query",
                        "needle",
                        "--limit",
                        "-1",
                    ]
                )

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("--limit", error.getvalue())
            self.assertIn("non-negative", error.getvalue())
            self.assertEqual(output.getvalue(), "")

    def test_fetch_mock_accepts_zero_limit_and_stores_no_messages(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            account_file = base / "accounts.txt"
            database = base / "mail.sqlite3"
            account_file.write_text(
                "ok@outlook.com----password----client----refresh\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                result = cli.main(
                    [
                        "--db",
                        str(database),
                        "fetch",
                        str(account_file),
                        "--mock",
                        "--limit",
                        "0",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(MailStore(database).count(), 0)
            self.assertIn("fetched=0 inserted=0", output.getvalue())

    def test_search_accepts_zero_limit_without_printing_stored_rows(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / "mail.sqlite3"
            store = MailStore(database)
            store.initialize()
            store.save_many([_record()])
            output = io.StringIO()

            with redirect_stdout(output):
                result = cli.main(
                    [
                        "search",
                        "--query",
                        "needle",
                        "--limit",
                        "0",
                        "--db",
                        str(database),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(output.getvalue(), "results: 0\n")

    def test_fetch_continues_after_one_account_failure(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            account_file = base / "accounts.txt"
            account_file.write_text(
                "\n".join(
                    [
                        "ok@outlook.com----password----client----refresh",
                        "bad@outlook.com----password----client----refresh",
                    ]
                ),
                encoding="utf-8",
            )

            def fake_fetch(account, **_kwargs):
                if account.email == "bad@outlook.com":
                    raise RuntimeError("imap failed")
                return [
                    EmailRecord(
                        account_email=account.email,
                        mailbox="INBOX",
                        uid="1",
                        uidvalidity="test",
                        message_id=None,
                        subject="ok",
                        sender="sender@example.com",
                        recipients=account.email,
                        sent_at=None,
                        body_preview="body",
                        raw_message=b"raw",
                    )
                ]

            with patch("mail_receiver.cli.fetch_messages", side_effect=fake_fetch):
                result = cli.main(
                    [
                        "--db",
                        str(base / "mail.sqlite3"),
                        "fetch",
                        str(account_file),
                        "--limit",
                        "1",
                    ]
                )

            self.assertEqual(result, 1)

    def test_fetch_passes_imap_timeout_to_core_client(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            account_file = base / "accounts.txt"
            account_file.write_text(
                "ok@outlook.com----password----client----refresh\n",
                encoding="utf-8",
            )
            seen_kwargs = {}

            def fake_fetch(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return []

            with patch("mail_receiver.cli.fetch_messages", side_effect=fake_fetch):
                result = cli.main(
                    [
                        "--db",
                        str(base / "mail.sqlite3"),
                        "fetch",
                        str(account_file),
                        "--limit",
                        "1",
                        "--imap-timeout",
                        "7",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(seen_kwargs["imap_timeout"], 7)

    def test_fetch_passes_trailing_debug_to_core_client(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            account_file = base / "accounts.txt"
            account_file.write_text(
                "ok@outlook.com----password----client----refresh\n",
                encoding="utf-8",
            )
            seen_kwargs = {}

            def fake_fetch(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return []

            with patch("mail_receiver.cli.fetch_messages", side_effect=fake_fetch):
                result = cli.main(
                    [
                        "fetch",
                        str(account_file),
                        "--db",
                        str(base / "mail.sqlite3"),
                        "--debug",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertTrue(seen_kwargs["debug"])

    def test_fetch_uses_trailing_database_path(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            account_file = base / "accounts.txt"
            database = base / "custom.sqlite3"
            account_file.write_text(
                "ok@outlook.com----password----client----refresh\n",
                encoding="utf-8",
            )

            result = cli.main(
                [
                    "fetch",
                    str(account_file),
                    "--mock",
                    "--limit",
                    "1",
                    "--db",
                    str(database),
                ]
            )

            self.assertEqual(result, 0)
            self.assertTrue(database.is_file())
            self.assertEqual(MailStore(database).count(), 1)


if __name__ == "__main__":
    unittest.main()
