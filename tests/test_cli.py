from pathlib import Path
from contextlib import redirect_stdout
import io
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mail_receiver import cli
from mail_receiver.imap_client import EmailRecord


class CliFetchTests(unittest.TestCase):
    def test_cli_exposes_version_flag(self) -> None:
        output = io.StringIO()

        with self.assertRaises(SystemExit) as raised, redirect_stdout(output):
            cli.build_parser().parse_args(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertRegex(output.getvalue(), r"Outlook Mail Fetcher \d+\.\d+\.\d+")

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


if __name__ == "__main__":
    unittest.main()
