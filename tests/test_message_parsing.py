from email import policy
from email.parser import BytesParser
import unittest

from mail_receiver.message_parsing import (
    DefaultMessageParser,
    MessageContext,
    email_record_from_message,
    extract_body_text,
)


class MessageParsingTests(unittest.TestCase):
    def test_default_parser_builds_email_record_from_raw_bytes(self) -> None:
        raw = (
            b"Message-ID: <abc@example>\r\n"
            b"Date: Sat, 04 Jul 2026 12:00:00 +0000\r\n"
            b"From: sender@example.com\r\n"
            b"To: user@outlook.com\r\n"
            b"Subject: Hello\r\n"
            b"\r\n"
            b"Body"
        )

        record = DefaultMessageParser().parse(
            raw,
            MessageContext(
                account_email="user@outlook.com",
                mailbox="INBOX",
                uid="7",
                uidvalidity="9",
                raw_message_complete=False,
            ),
        )

        self.assertEqual(record.message_id, "<abc@example>")
        self.assertEqual(record.subject, "Hello")
        self.assertEqual(record.body_preview, "Body")
        self.assertEqual(record.uid, "7")
        self.assertEqual(record.uidvalidity, "9")
        self.assertFalse(record.raw_message_complete)

    def test_email_record_from_message_remains_available_as_focused_helper(self) -> None:
        raw = b"Subject: Helper\r\n\r\nBody text"
        message = BytesParser(policy=policy.default).parsebytes(raw)

        record = email_record_from_message(
            account_email="user@outlook.com",
            mailbox="INBOX",
            uid="42",
            uidvalidity="12345",
            message=message,
            raw_message=raw,
        )

        self.assertEqual(record.subject, "Helper")
        self.assertEqual(record.body_preview, "Body text")

    def test_extract_body_prefers_non_empty_plain_text(self) -> None:
        raw = (
            b"Content-Type: multipart/alternative; boundary=x\r\n"
            b"\r\n"
            b"--x\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<b>html</b>\r\n"
            b"--x\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"plain\r\n"
            b"--x--\r\n"
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)

        self.assertEqual(extract_body_text(message), "plain")

    def test_extract_body_uses_html_when_plain_text_is_empty(self) -> None:
        raw = (
            b"Content-Type: multipart/alternative; boundary=x\r\n"
            b"\r\n"
            b"--x\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"   \r\n"
            b"--x\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<p>HTML fallback body</p>\r\n"
            b"--x--\r\n"
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)

        self.assertEqual(extract_body_text(message), "HTML fallback body")

    def test_extract_body_excludes_attached_message_contents(self) -> None:
        raw = (
            b"Content-Type: multipart/mixed; boundary=outer\r\n"
            b"\r\n"
            b"--outer\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"Primary body\r\n"
            b"--outer\r\n"
            b"Content-Type: message/rfc822\r\n"
            b'Content-Disposition: attachment; filename="forwarded.eml"\r\n'
            b"\r\n"
            b"From: sender@example.com\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"ATTACHED SECRET\r\n"
            b"--outer--\r\n"
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)

        self.assertEqual(extract_body_text(message), "Primary body")

    def test_extract_body_decodes_unknown_charset_as_utf8(self) -> None:
        raw = (
            b"Content-Type: text/plain; charset=x-fixture-unknown\r\n"
            b"Content-Transfer-Encoding: 8bit\r\n"
            b"\r\n"
            + "Verification code: 你好 654321\r\n".encode("utf-8")
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)

        self.assertEqual(extract_body_text(message), "Verification code: 你好 654321")


if __name__ == "__main__":
    unittest.main()
