from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mail_receiver import cli
from mail_receiver.accounts import Account, AccountFormatError
from mail_receiver.imap_client import EmailRecord
from mail_receiver.storage import DEFAULT_DB_PATH, MailStore


def _record(
    *,
    uid: str = "1",
    subject: str = "Needle",
    raw_message: bytes = b"raw",
) -> EmailRecord:
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
        raw_message=raw_message,
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
        self.assertIsNone(parsed.max_workers)

    def test_fetch_accepts_bounded_worker_count(self) -> None:
        parsed = cli.build_parser().parse_args(
            ["fetch", "accounts.txt", "--max-workers", "3"]
        )

        self.assertEqual(parsed.max_workers, 3)

        for invalid_value in ("0", "17"):
            with self.subTest(invalid_value=invalid_value), self.assertRaises(SystemExit):
                cli.build_parser().parse_args(
                    ["fetch", "accounts.txt", "--max-workers", invalid_value]
                )

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


class CliRawOutputTests(unittest.TestCase):
    RAW_MESSAGE = b"\xff\x00header\r\nbody\n\x80trailing-byte-without-lf"

    def _create_database(self, database: Path) -> int:
        store = MailStore(database)
        store.initialize()
        self.assertEqual(
            store.save_many([_record(raw_message=self.RAW_MESSAGE)]),
            1,
        )
        return store.search("Needle", limit=1)[0].id

    def _run_show_raw(self, arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-m", "mail_receiver.cli", *arguments],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_show_raw_subprocess_preserves_bytes_with_trailing_db(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            email_id = self._create_database(database)

            completed = self._run_show_raw(
                ["show", str(email_id), "--raw", "--db", str(database)]
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, self.RAW_MESSAGE)
        self.assertEqual(completed.stderr, b"")

    def test_show_raw_subprocess_preserves_bytes_with_leading_db(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            email_id = self._create_database(database)

            completed = self._run_show_raw(
                ["--db", str(database), "show", str(email_id), "--raw"]
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, self.RAW_MESSAGE)
        self.assertEqual(completed.stderr, b"")

    def test_show_raw_supports_a_binary_stdout_without_buffer_attribute(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            email_id = self._create_database(database)
            output = io.BytesIO()

            with patch.object(cli.sys, "stdout", output):
                result = cli.show(
                    SimpleNamespace(db=str(database), email_id=email_id, raw=True)
                )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), self.RAW_MESSAGE)

    def test_show_raw_does_not_pass_message_bytes_through_visible_text(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            email_id = self._create_database(database)
            output = io.BytesIO()

            with patch.object(cli.sys, "stdout", output), patch.object(
                cli, "visible_text", wraps=cli.visible_text
            ) as visible:
                result = cli.show(
                    SimpleNamespace(db=str(database), email_id=email_id, raw=True)
                )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), self.RAW_MESSAGE)
        visible.assert_not_called()

    def test_show_raw_keeps_missing_message_exit_behavior(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            MailStore(database).initialize()

            completed = self._run_show_raw(
                ["show", "999", "--raw", "--db", str(database)]
            )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, b"")
        self.assertEqual(completed.stderr.decode().strip(), "email not found: 999")

    def test_show_non_raw_still_supports_text_stdout_without_buffer(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            email_id = self._create_database(database)
            output = io.StringIO()

            with redirect_stdout(output):
                result = cli.show(
                    SimpleNamespace(db=str(database), email_id=email_id, raw=False)
                )

        self.assertEqual(result, 0)
        self.assertIn("subject: Needle", output.getvalue())


class CliVisibleOutputTests(unittest.TestCase):
    @staticmethod
    def _subprocess_environment() -> dict[str, str]:
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    def _run_cli(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "mail_receiver.cli", *arguments],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            env=self._subprocess_environment(),
            check=False,
        )

    def test_main_escapes_account_format_and_unexpected_error_messages(self) -> None:
        cases = (
            (AccountFormatError("bad\r\nforged\x1b[31m\x00\u2028"), 2, "account format error"),
            (RuntimeError("bad\r\nforged\x1b[31m\x00\u2028"), 1, "error"),
        )

        for exception, expected_code, prefix in cases:
            with self.subTest(exception=type(exception).__name__):
                error = io.StringIO()
                with patch(
                    "mail_receiver.cli.inspect_accounts", side_effect=exception
                ), redirect_stderr(error):
                    result = cli.main(["inspect-accounts", "accounts.txt"])

                self.assertEqual(result, expected_code)
                self.assertEqual(
                    error.getvalue(),
                    f"{prefix}: bad\\r\\nforged\\x1b[31m\\x00\\u2028\n",
                )
                self.assertEqual(len(error.getvalue().splitlines()), 1)
                self.assertNotIn("\x1b", error.getvalue())
                self.assertNotIn("\x00", error.getvalue())

    def test_inspect_accounts_escapes_every_dynamic_account_field(self) -> None:
        account = Account(
            email="user\r\nforged\x1b@example.com",
            password="\rApasswordB\n",
            client_id="client\x00id\u2028",
            refresh_token="refresh\tTOKEN-value\vending",
            source_line=7,
        )
        output = io.StringIO()

        with patch("mail_receiver.cli.load_accounts", return_value=[account]), redirect_stdout(
            output
        ):
            result = cli.inspect_accounts("accounts.txt")

        self.assertEqual(result, 0)
        self.assertEqual(len(output.getvalue().splitlines()), 2)
        self.assertIn("email=user\\r\\nforged\\x1b@example.com", output.getvalue())
        self.assertIn("password=\\rA********B\\n", output.getvalue())
        self.assertIn("client_id=client\\x00id\\u2028", output.getvalue())
        self.assertIn("refresh_token=refresh\\t********ending", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())
        self.assertNotIn("\x00", output.getvalue())

    def test_fetch_escapes_accounts_mailbox_errors_database_path_and_log_arguments(self) -> None:
        good = Account("good\r\nforged\x1b@example.com", "p", "c", "r", 1)
        bad = Account("bad\x00\u2028@example.com", "p", "c", "r", 2)
        mailbox = "INBOX\tname\x1b"
        failure = "connect\r\nforged\x1b[31m\x00\u2028"

        class FakeStore:
            path = "mail\r\nforged\x1b.sqlite3"

            def initialize(self) -> None:
                pass

            def save_many(self, records: list[EmailRecord]) -> int:
                return len(records)

        def fake_fetch(account: Account, **_kwargs: object) -> list[EmailRecord]:
            if account is bad:
                raise RuntimeError(failure)
            return []

        args = SimpleNamespace(
            account_file="accounts.txt",
            account=None,
            db="ignored.sqlite3",
            mailbox=mailbox,
            limit=1,
            mock=False,
            stop_on_error=False,
            imap_host="host",
            imap_port=993,
            imap_timeout=1,
            token_endpoint="endpoint",
            scope="scope",
            token_timeout=1,
            debug=False,
        )
        output = io.StringIO()
        error = io.StringIO()

        with patch("mail_receiver.cli.load_accounts", return_value=[good, bad]), patch(
            "mail_receiver.cli.SQLiteMailRepository", return_value=FakeStore()
        ), patch("mail_receiver.cli.fetch_messages", side_effect=fake_fetch), patch(
            "mail_receiver.cli.logging.info"
        ) as info, redirect_stdout(output), redirect_stderr(error):
            result = cli.fetch(args)

        self.assertEqual(result, 1)
        self.assertEqual(len(output.getvalue().splitlines()), 2)
        self.assertIn("good\\r\\nforged\\x1b@example.com: fetched=0 inserted=0", output.getvalue())
        self.assertIn("db=mail\\r\\nforged\\x1b.sqlite3", output.getvalue())
        self.assertEqual(len(error.getvalue().splitlines()), 3)
        self.assertEqual(error.getvalue().count("connect\\r\\nforged\\x1b[31m\\x00\\u2028"), 2)
        self.assertNotIn("\x1b", output.getvalue() + error.getvalue())
        self.assertNotIn("\x00", output.getvalue() + error.getvalue())
        self.assertEqual(
            info.call_args_list[0].args,
            (
                "fetching %s mailbox=%s limit=%s",
                "good\\r\\nforged\\x1b@example.com",
                "INBOX\\tname\\x1b",
                1,
            ),
        )
        self.assertEqual(
            info.call_args_list[1].args,
            (
                "fetching %s mailbox=%s limit=%s",
                "bad\\x00\\u2028@example.com",
                "INBOX\\tname\\x1b",
                1,
            ),
        )

    def test_fetch_escapes_requested_account_when_it_is_not_found(self) -> None:
        requested = "missing\r\nforged\x1b\x00\u2028@example.com"
        args = SimpleNamespace(account_file="accounts.txt", account=requested)
        error = io.StringIO()

        with patch("mail_receiver.cli.load_accounts", return_value=[]), redirect_stderr(error):
            result = cli.fetch(args)

        self.assertEqual(result, 1)
        self.assertEqual(
            error.getvalue(),
            "account not found: missing\\r\\nforged\\x1b\\x00\\u2028@example.com\n",
        )
        self.assertEqual(len(error.getvalue().splitlines()), 1)

    def test_search_subprocess_escapes_stored_fields_without_terminal_injection(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            store = MailStore(database)
            store.initialize()
            store.save_many(
                [
                    EmailRecord(
                        account_email="account\r\nFORGED@example.com",
                        mailbox="INBOX",
                        uid="1",
                        uidvalidity="1",
                        message_id=None,
                        subject="Needle\u2028subject",
                        sender="sender\x00\x1b[31m@example.com",
                        recipients="recipient@example.com",
                        sent_at="2026-07-18\t12:00",
                        body_preview="Needle",
                        raw_message=b"raw",
                    )
                ]
            )

            completed = self._run_cli(
                ["search", "--query", "Needle", "--db", str(database)]
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(completed.stdout.splitlines()), 2)
        self.assertIn("2026-07-18\\t12:00", completed.stdout)
        self.assertIn("account\\r\\nFORGED@example.com", completed.stdout)
        self.assertIn("sender\\x00\\x1b[31m@example.com", completed.stdout)
        self.assertIn("subject=Needle\\u2028subject", completed.stdout)
        self.assertNotIn("\x1b", completed.stdout)
        self.assertNotIn("\x00", completed.stdout)
        self.assertNotIn("\u2028", completed.stdout)

    def test_show_non_raw_subprocess_escapes_every_stored_text_field(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "mail.sqlite3"
            store = MailStore(database)
            store.initialize()
            store.save_many(
                [
                    EmailRecord(
                        account_email="account\r\nFORGED@example.com",
                        mailbox="INBOX\tname",
                        uid="uid\x00",
                        uidvalidity="1",
                        message_id="message\bidentifier",
                        subject="Needle\u2028subject",
                        sender="sender\x1b[31m@example.com",
                        recipients="to\f@example.com",
                        sent_at="2026-07-18\v12:00",
                        body_preview="body\r\nFORGED\x00\u2029tail",
                        raw_message=b"raw",
                    )
                ]
            )
            email_id = store.search("Needle", limit=1)[0].id

            completed = self._run_cli(
                ["show", str(email_id), "--db", str(database)]
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(completed.stdout.splitlines()), 11)
        expected_fragments = (
            "account: account\\r\\nFORGED@example.com",
            "mailbox: INBOX\\tname",
            "uid: uid\\x00",
            "message_id: message\\bidentifier",
            "sent_at: 2026-07-18\\v12:00",
            "from: sender\\x1b[31m@example.com",
            "to: to\\f@example.com",
            "subject: Needle\\u2028subject",
            "body\\r\\nFORGED\\x00\\u2029tail",
        )
        for fragment in expected_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, completed.stdout)
        self.assertNotIn("\x1b", completed.stdout)
        self.assertNotIn("\x00", completed.stdout)
        self.assertNotIn("\u2028", completed.stdout)
        self.assertNotIn("\u2029", completed.stdout)


if __name__ == "__main__":
    unittest.main()
