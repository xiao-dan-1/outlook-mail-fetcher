from email import policy
from email.parser import BytesParser
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mail_receiver.accounts import Account
from mail_receiver.imap_client import (
    _iter_fetch_messages,
    _parse_fetch_item,
    build_xoauth2_string,
    check_account,
    email_record_from_message,
    extract_body_text,
    FetchDiagnostics,
    fetch_messages,
    ImapReceiveError,
)


class ImapClientTests(unittest.TestCase):
    def test_build_xoauth2_string(self) -> None:
        self.assertEqual(
            build_xoauth2_string("user@outlook.com", "token"),
            "user=user@outlook.com\x01auth=Bearer token\x01\x01",
        )

    def test_partial_fetch_treats_unparseable_rfc822_size_as_incomplete(self) -> None:
        metadata = (
            b"1 (UID 42 RFC822.SIZE "
            + (b"9" * 5000)
            + b" BODY[]<0> {3}"
        )

        uid, raw_message, raw_message_complete = _parse_fetch_item(
            (metadata, b"abc"),
            is_partial=True,
        )

        self.assertEqual(uid, "42")
        self.assertEqual(raw_message, b"abc")
        self.assertFalse(raw_message_complete)

    def test_fetch_literals_use_only_their_contiguous_trailer_metadata(self) -> None:
        data = [
            (b"1 (BODY[]<0> {5}", b"abcde"),
            b" UID 42 RFC822.SIZE 5)",
            (b"2 (BODY[]<0> {3}", b"xyz"),
            b" UID 43 RFC822.SIZE 10)",
        ]

        payloads = list(_iter_fetch_messages(data, is_partial=True))

        self.assertEqual(
            payloads,
            [
                ("42", b"abcde", True),
                ("43", b"xyz", False),
            ],
        )

    def test_byte_only_fetch_response_does_not_supply_previous_literal_uid(self) -> None:
        data = [
            (b"1 (BODY[]<0> {3}", b"abc"),
            b")",
            b"2 (UID 43 RFC822.SIZE 3 FLAGS (\\Seen))",
        ]

        with self.assertRaises(ImapReceiveError) as raised:
            list(_iter_fetch_messages(data, is_partial=True))

        self.assertEqual(
            str(raised.exception),
            "IMAP FETCH response item did not include UID",
        )

    def test_byte_only_fetch_response_does_not_set_previous_literal_size(self) -> None:
        data = [
            (b"1 (UID 42 BODY[]<0> {3}", b"abc"),
            b")",
            b"2 (UID 43 RFC822.SIZE 3 FLAGS (\\Seen))",
        ]

        payloads = list(_iter_fetch_messages(data, is_partial=True))

        self.assertEqual(payloads, [("42", b"abc", False)])

    def test_email_record_from_message_extracts_headers_and_body(self) -> None:
        raw = (
            b"Message-ID: <abc@example>\r\n"
            b"Date: Sat, 04 Jul 2026 12:00:00 +0000\r\n"
            b"From: sender@example.com\r\n"
            b"To: user@outlook.com\r\n"
            b"Subject: Hello\r\n"
            b"\r\n"
            b"body text"
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)

        record = email_record_from_message(
            account_email="user@outlook.com",
            mailbox="INBOX",
            uid="42",
            uidvalidity="12345",
            message=message,
            raw_message=raw,
        )

        self.assertEqual(record.message_id, "<abc@example>")
        self.assertEqual(record.subject, "Hello")
        self.assertEqual(record.sender, "sender@example.com")
        self.assertEqual(record.body_preview, "body text")

    def test_extract_body_prefers_plain_text(self) -> None:
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

    def test_extract_body_uses_html_when_plain_part_is_empty(self) -> None:
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

    def test_extract_body_excludes_attached_rfc822_contents(self) -> None:
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

    def test_extract_body_decodes_multipart_text_with_unknown_charset_as_utf8(self) -> None:
        raw = (
            b"Content-Type: multipart/alternative; boundary=x\r\n"
            b"\r\n"
            b"--x\r\n"
            b"Content-Type: text/plain; charset=x-fixture-unknown\r\n"
            b"Content-Transfer-Encoding: 8bit\r\n"
            b"\r\n"
            + "Verification code: 你好 654321\r\n".encode("utf-8")
            + b"--x\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<p>HTML fallback</p>\r\n"
            b"--x--\r\n"
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)

        self.assertEqual(extract_body_text(message), "Verification code: 你好 654321")

    def test_extract_body_cleans_html_when_plain_text_is_missing(self) -> None:
        raw = (
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<html><head><style>@font-face { font-family: ignored; }</style></head>"
            b"<body><h1>Welcome</h1><p>Your account is ready.</p>"
            b"<script>alert('ignored')</script></body></html>\r\n"
        )
        message = BytesParser(policy=policy.default).parsebytes(raw)

        body = extract_body_text(message)

        self.assertEqual(body, "Welcome\nYour account is ready.")
        self.assertNotIn("@font-face", body)
        self.assertNotIn("<style", body)


def _account() -> Account:
    return Account(
        email="user@outlook.com",
        password="password",
        client_id="client-id",
        refresh_token="refresh-token",
        source_line=1,
    )


def _raw_message(uid: str) -> bytes:
    return (
        f"Message-ID: <{uid}@example.com>\r\n"
        "Date: Sat, 04 Jul 2026 12:00:00 +0000\r\n"
        "From: sender@example.com\r\n"
        "To: user@outlook.com\r\n"
        f"Subject: Message {uid}\r\n"
        "\r\n"
        f"Body {uid}"
    ).encode("utf-8")


class InstrumentedIMAP:
    instances: list["InstrumentedIMAP"] = []
    messages: list[tuple[str, bytes]] = []
    select_status = "OK"
    select_error: BaseException | None = None
    search_status = "OK"
    search_error: BaseException | None = None
    search_result: bytes | None = None
    fetch_status = "OK"
    fetch_error: BaseException | None = None
    response_error: BaseException | None = None
    malformed_sequences: set[int] = set()
    expunge_uid_after_search: str | None = None
    uidvalidity: bytes | None = b"12345"
    select_uidvalidity: bytes | None = None

    def __init__(self, host: str, port: int, timeout: int | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = InstrumentedSocket()
        self.commands: list[tuple[object, ...]] = []
        self.debug = 0
        InstrumentedIMAP.instances.append(self)

    @classmethod
    def reset(
        cls,
        *,
        count: int = 3,
        select_status: str = "OK",
        uidvalidity: bytes | None = b"12345",
        select_uidvalidity: bytes | None = None,
    ) -> None:
        cls.instances = []
        cls.messages = [(str(index), _raw_message(str(index))) for index in range(1, count + 1)]
        cls.select_status = select_status
        cls.select_error = None
        cls.search_status = "OK"
        cls.search_error = None
        cls.search_result = None
        cls.fetch_status = "OK"
        cls.fetch_error = None
        cls.response_error = None
        cls.malformed_sequences = set()
        cls.expunge_uid_after_search = None
        cls.uidvalidity = uidvalidity
        cls.select_uidvalidity = select_uidvalidity

    def __enter__(self) -> "InstrumentedIMAP":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def authenticate(self, mechanism: str, callback: object) -> tuple[str, list[bytes]]:
        payload = callback(None)  # type: ignore[misc]
        self.commands.append(("AUTHENTICATE", mechanism, payload))
        return "OK", [b""]

    def select(self, mailbox: bytes, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.commands.append(("SELECT", mailbox, readonly))
        if self.select_error is not None:
            raise self.select_error
        data = [str(len(self.messages)).encode("ascii")]
        if self.select_uidvalidity is not None:
            data.append(b"[UIDVALIDITY " + self.select_uidvalidity + b"]")
        return self.select_status, data

    def response(self, code: str) -> tuple[str, list[bytes | None]]:
        if self.response_error is not None:
            raise self.response_error
        if code.upper() == "UIDVALIDITY" and self.uidvalidity is not None:
            return "UIDVALIDITY", [self.uidvalidity]
        return "UIDVALIDITY", [None]

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        self.commands.append(("UID", command, *args))
        if command == "SEARCH":
            if self.search_error is not None:
                raise self.search_error
            if self.search_status != "OK":
                return self.search_status, [b""]
            uids = self.search_result
            if uids is None:
                uids = b" ".join(uid.encode("ascii") for uid, _ in self.messages)
            if self.expunge_uid_after_search is not None:
                self.messages = [
                    (uid, raw)
                    for uid, raw in self.messages
                    if uid != self.expunge_uid_after_search
                ]
            return "OK", [uids]
        if command == "FETCH":
            if self.fetch_error is not None:
                raise self.fetch_error
            if self.fetch_status != "OK":
                return self.fetch_status, [b""]
            requested_uids = str(args[0]).split(",")
            message_parts = str(args[1])
            partial_match = re.search(r"BODY\.PEEK\[\]<0\.([0-9]+)>", message_parts)
            data: list[object] = []
            for sequence, (uid, raw) in enumerate(self.messages, start=1):
                if uid not in requested_uids:
                    continue
                if sequence in self.malformed_sequences:
                    data.append((f"{sequence} (UID {uid})".encode("ascii"),))
                    continue
                if partial_match is not None:
                    literal = raw[: int(partial_match.group(1))]
                    header = (
                        f"{sequence} (UID {uid} RFC822.SIZE {len(raw)} "
                        f"BODY[]<0> {{{len(literal)}}}"
                    ).encode("ascii")
                else:
                    literal = raw
                    header = f"{sequence} (UID {uid} BODY[] {{{len(raw)}}}".encode("ascii")
                data.extend([(header, literal), b")"])
            return "OK", data
        raise AssertionError(f"unexpected UID command: {command!r}")


class InstrumentedSocket:
    def __init__(self) -> None:
        self.timeout: int | None = None

    def settimeout(self, timeout: int | None) -> None:
        self.timeout = timeout


class FetchMessagesInstrumentedTests(unittest.TestCase):
    def test_fetch_messages_selects_ascii_mailbox_as_quoted_bytes(self) -> None:
        InstrumentedIMAP.reset(count=0)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            fetch_messages(_account(), mailbox="INBOX", limit=1)

        self.assertIn(
            ("SELECT", b'"INBOX"', True),
            InstrumentedIMAP.instances[0].commands,
        )

    def test_fetch_messages_encodes_literal_ampersand_in_mailbox(self) -> None:
        InstrumentedIMAP.reset(count=0)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            fetch_messages(_account(), mailbox="A&B", limit=1)

        self.assertIn(
            ("SELECT", b'"A&-B"', True),
            InstrumentedIMAP.instances[0].commands,
        )

    def test_fetch_messages_encodes_modified_utf7_mailbox_vectors(self) -> None:
        vectors = {
            "台北": b'"&U,BTFw-"',
            "日本語": b'"&ZeVnLIqe-"',
            "~peter/mail/台北/日本語": b'"~peter/mail/&U,BTFw-/&ZeVnLIqe-"',
            "台北日本語": b'"&U,BTF2XlZyyKng-"',
            "Emoji 😀": b'"Emoji &2D3eAA-"',
            "é": b'"&AOk-"',
            "e\N{COMBINING ACUTE ACCENT}": b'"e&AwE-"',
            "&U,BTFw-": b'"&-U,BTFw-"',
        }

        for mailbox, expected_wire_mailbox in vectors.items():
            with self.subTest(mailbox=mailbox):
                InstrumentedIMAP.reset(count=0)
                with patch(
                    "mail_receiver.imap_client.refresh_access_token",
                    return_value=SimpleNamespace(access_token="access-token"),
                ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
                    fetch_messages(_account(), mailbox=mailbox, limit=1)

                self.assertIn(
                    ("SELECT", expected_wire_mailbox, True),
                    InstrumentedIMAP.instances[0].commands,
                )

    def test_fetch_messages_escapes_quoted_string_mailbox_characters(self) -> None:
        InstrumentedIMAP.reset(count=0)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            fetch_messages(_account(), mailbox='Shared "Team"\\Inbox', limit=1)

        self.assertIn(
            ("SELECT", b'"Shared \\"Team\\"\\\\Inbox"', True),
            InstrumentedIMAP.instances[0].commands,
        )

    def test_fetch_messages_rejects_command_frame_characters_before_select(self) -> None:
        invalid_mailboxes = {
            "CR": "Inbox\rInjected",
            "LF": "Inbox\nInjected",
            "NUL": "Inbox\x00Injected",
        }

        for character_name, mailbox in invalid_mailboxes.items():
            with self.subTest(character_name=character_name):
                InstrumentedIMAP.reset(count=0)
                with patch(
                    "mail_receiver.imap_client.refresh_access_token",
                    return_value=SimpleNamespace(access_token="access-token"),
                ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
                    with self.assertRaises(ImapReceiveError) as raised:
                        fetch_messages(_account(), mailbox=mailbox, limit=1)

                self.assertIn(character_name, str(raised.exception))
                self.assertIn(repr(mailbox), str(raised.exception))
                self.assertFalse(
                    any(command[0] == "SELECT" for command in InstrumentedIMAP.instances[0].commands)
                )

    def test_fetch_messages_rejects_unpaired_surrogate_before_select(self) -> None:
        mailbox = "Inbox\ud800"
        InstrumentedIMAP.reset(count=0)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), mailbox=mailbox, limit=1)

        self.assertIn("surrogate", str(raised.exception).lower())
        self.assertIn(repr(mailbox), str(raised.exception))
        self.assertFalse(
            any(command[0] == "SELECT" for command in InstrumentedIMAP.instances[0].commands)
        )

    def test_fetch_messages_preserves_logical_unicode_mailbox_on_records(self) -> None:
        mailbox = "收件箱"
        InstrumentedIMAP.reset(count=1)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), mailbox=mailbox, limit=1)

        self.assertEqual([record.mailbox for record in records], [mailbox])
        self.assertIn(
            ("SELECT", b'"&ZTZO9nux-"', True),
            InstrumentedIMAP.instances[0].commands,
        )

    def test_check_account_preserves_logical_unicode_mailbox_on_result(self) -> None:
        mailbox = "收件箱"
        InstrumentedIMAP.reset(count=7)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            result = check_account(_account(), mailbox=mailbox)

        self.assertEqual(result.mailbox, mailbox)
        self.assertEqual(result.message_count, 7)
        self.assertIn(
            ("SELECT", b'"&ZTZO9nux-"', True),
            InstrumentedIMAP.instances[0].commands,
        )

    def test_select_failure_keeps_logical_unicode_mailbox_in_error(self) -> None:
        mailbox = "收件箱"
        InstrumentedIMAP.reset(count=0, select_status="NO")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), mailbox=mailbox, limit=1)

        self.assertIn(repr(mailbox), str(raised.exception))
        self.assertNotIn("&ZTZO9nux-", str(raised.exception))

    def test_fetch_messages_sorts_uid_search_results_before_taking_last_uids(self) -> None:
        InstrumentedIMAP.reset(count=0)
        InstrumentedIMAP.messages = [
            ("2", _raw_message("2")),
            ("7", _raw_message("7")),
            ("20", _raw_message("20")),
            ("42", _raw_message("42")),
        ]
        InstrumentedIMAP.search_result = b"42 2 20 7"

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["20", "42"])
        self.assertIn(("UID", "FETCH", "20,42", "(UID BODY.PEEK[])"), client.commands)

    def test_fetch_messages_deduplicates_uid_search_results_before_applying_limit(self) -> None:
        InstrumentedIMAP.reset(count=0)
        InstrumentedIMAP.messages = [
            ("2", _raw_message("2")),
            ("7", _raw_message("7")),
            ("20", _raw_message("20")),
            ("42", _raw_message("42")),
        ]
        InstrumentedIMAP.search_result = b"2 7 20 42 42"

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["20", "42"])
        self.assertIn(("UID", "FETCH", "20,42", "(UID BODY.PEEK[])"), client.commands)

    def test_fetch_messages_deduplicates_uid_search_results_by_numeric_value(self) -> None:
        InstrumentedIMAP.reset(count=0)
        InstrumentedIMAP.messages = [
            ("2", _raw_message("2")),
            ("7", _raw_message("7")),
            ("20", _raw_message("20")),
            ("42", _raw_message("42")),
        ]
        InstrumentedIMAP.search_result = b"2 7 20 42 042"

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["20", "42"])
        self.assertIn(("UID", "FETCH", "20,42", "(UID BODY.PEEK[])"), client.commands)

    def test_fetch_messages_uses_one_uid_fetch_for_last_non_contiguous_uids(self) -> None:
        InstrumentedIMAP.reset(count=0)
        InstrumentedIMAP.messages = [
            ("2", _raw_message("2")),
            ("7", _raw_message("7")),
            ("20", _raw_message("20")),
            ("42", _raw_message("42")),
        ]

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["20", "42"])
        self.assertIn(("UID", "SEARCH", None, "ALL"), client.commands)
        self.assertIn(("UID", "FETCH", "20,42", "(UID BODY.PEEK[])"), client.commands)
        self.assertEqual(sum(1 for command in client.commands if command[:2] == ("UID", "FETCH")), 1)
        self.assertEqual(sum(1 for command in client.commands if command[0] == "FETCH"), 0)

    def test_uid_fetch_silently_ignores_uid_expunged_after_search(self) -> None:
        InstrumentedIMAP.reset(count=0)
        InstrumentedIMAP.messages = [
            ("10", _raw_message("10")),
            ("20", _raw_message("20")),
            ("30", _raw_message("30")),
            ("40", _raw_message("40")),
        ]
        InstrumentedIMAP.expunge_uid_after_search = "30"

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["40"])
        self.assertIn(("UID", "FETCH", "30,40", "(UID BODY.PEEK[])"), client.commands)
        self.assertEqual(sum(1 for command in client.commands if command[:2] == ("UID", "FETCH")), 1)
        self.assertEqual(sum(1 for command in client.commands if command[0] == "FETCH"), 0)

    def test_fetch_messages_attaches_uidvalidity_from_imaplib_response(self) -> None:
        InstrumentedIMAP.reset(count=2, uidvalidity=b" 98765 ")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2)

        self.assertEqual([record.uid for record in records], ["1", "2"])
        self.assertEqual({record.uidvalidity for record in records}, {"98765"})

    def test_fetch_messages_keeps_batch_when_message_has_unknown_charset(self) -> None:
        for charset in ("x-fixture-unknown", "idna"):
            with self.subTest(charset=charset):
                InstrumentedIMAP.reset(count=2)
                fallback_charset_message = (
                    b"Message-ID: <1@example.com>\r\n"
                    + f"Content-Type: text/plain; charset={charset}\r\n".encode("ascii")
                    + b"Content-Transfer-Encoding: 8bit\r\n"
                    b"\r\n"
                    + "Verification code: 你好 123456".encode("utf-8")
                )
                InstrumentedIMAP.messages = [
                    ("1", fallback_charset_message),
                    ("2", _raw_message("2")),
                ]

                with patch(
                    "mail_receiver.imap_client.refresh_access_token",
                    return_value=SimpleNamespace(access_token="access-token"),
                ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
                    records = fetch_messages(_account(), limit=2)

                self.assertEqual([record.uid for record in records], ["1", "2"])
                self.assertEqual(records[0].body_preview, "Verification code: 你好 123456")
                self.assertEqual(records[1].body_preview, "Body 2")

    def test_fetch_messages_falls_back_to_select_uidvalidity_when_response_raises(self) -> None:
        InstrumentedIMAP.reset(count=1, uidvalidity=b"98765", select_uidvalidity=b"13579")
        InstrumentedIMAP.response_error = OSError("UIDVALIDITY response unavailable")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=1)

        self.assertEqual(records[0].uidvalidity, "13579")

    def test_fetch_messages_falls_back_to_select_uidvalidity_data(self) -> None:
        InstrumentedIMAP.reset(count=1, uidvalidity=None, select_uidvalidity=b"24680")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=1)

        self.assertEqual(records[0].uidvalidity, "24680")

    def test_fetch_messages_missing_uidvalidity_is_readable(self) -> None:
        InstrumentedIMAP.reset(count=1, uidvalidity=None, select_uidvalidity=None)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=1)

        self.assertIn("UIDVALIDITY", str(raised.exception))
        self.assertIn("INBOX", str(raised.exception))

    def test_limit_zero_returns_empty_without_token_or_imap_connection(self) -> None:
        InstrumentedIMAP.reset(count=3)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ) as refresh_token, patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=0)

        self.assertEqual(records, [])
        refresh_token.assert_not_called()
        self.assertEqual(InstrumentedIMAP.instances, [])

    def test_fetch_messages_applies_imap_timeout_to_connection_and_socket(self) -> None:
        InstrumentedIMAP.reset(count=1)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=1, imap_timeout=12)

        self.assertEqual(len(records), 1)
        self.assertEqual(InstrumentedIMAP.instances[0].timeout, 12)
        self.assertEqual(InstrumentedIMAP.instances[0].sock.timeout, 12)

    def test_check_account_applies_imap_timeout_to_connection_and_socket(self) -> None:
        InstrumentedIMAP.reset(count=7)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            result = check_account(_account(), imap_timeout=9)

        self.assertEqual(result.message_count, 7)
        self.assertEqual(InstrumentedIMAP.instances[0].timeout, 9)
        self.assertEqual(InstrumentedIMAP.instances[0].sock.timeout, 9)

    def test_fetch_messages_wraps_imap_operation_timeout(self) -> None:
        InstrumentedIMAP.reset(count=1)
        InstrumentedIMAP.select_error = TimeoutError("socket timed out")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=1, imap_timeout=5)

        self.assertIn("select mailbox", str(raised.exception))
        self.assertIn("timed out", str(raised.exception))

    def test_token_failure_does_not_connect_to_imap(self) -> None:
        InstrumentedIMAP.reset(count=1)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            side_effect=RuntimeError("token failed"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(RuntimeError):
                fetch_messages(_account(), limit=1)

        self.assertEqual(InstrumentedIMAP.instances, [])

    def test_fetch_messages_uses_one_readonly_uid_batch_fetch_for_recent_messages(self) -> None:
        InstrumentedIMAP.reset(count=1000)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["999", "1000"])
        self.assertTrue(all(record.raw_message_complete for record in records))
        self.assertIn(("SELECT", b'"INBOX"', True), client.commands)
        self.assertIn(("UID", "SEARCH", None, "ALL"), client.commands)
        self.assertIn(("UID", "FETCH", "999,1000", "(UID BODY.PEEK[])"), client.commands)
        self.assertEqual(sum(1 for command in client.commands if command[:2] == ("UID", "SEARCH")), 1)
        self.assertEqual(sum(1 for command in client.commands if command[:2] == ("UID", "FETCH")), 1)
        self.assertEqual(sum(1 for command in client.commands if command[0] == "FETCH"), 0)

    def test_fetch_messages_can_use_partial_raw_fetch_for_preview_mode(self) -> None:
        InstrumentedIMAP.reset(count=1000)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=5, max_bytes=16384)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["996", "997", "998", "999", "1000"])
        self.assertTrue(all(record.raw_message_complete for record in records))
        self.assertIn(
            (
                "UID",
                "FETCH",
                "996,997,998,999,1000",
                "(UID RFC822.SIZE BODY.PEEK[]<0.16384>)",
            ),
            client.commands,
        )
        self.assertEqual(sum(1 for command in client.commands if command[:2] == ("UID", "FETCH")), 1)
        self.assertEqual(sum(1 for command in client.commands if command[0] == "FETCH"), 0)

    def test_fetch_messages_marks_partial_raw_messages_by_rfc822_size(self) -> None:
        short_raw = _raw_message("short")
        max_bytes = len(short_raw) + 8
        long_raw = _raw_message("long") + (b"x" * max_bytes)
        InstrumentedIMAP.reset(count=2)
        InstrumentedIMAP.messages = [("1", short_raw), ("2", long_raw)]

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2, max_bytes=max_bytes)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual(records[0].raw_message, short_raw)
        self.assertTrue(records[0].raw_message_complete)
        self.assertEqual(records[1].raw_message, long_raw[:max_bytes])
        self.assertFalse(records[1].raw_message_complete)
        self.assertIn(
            ("UID", "FETCH", "1,2", f"(UID RFC822.SIZE BODY.PEEK[]<0.{max_bytes}>)"),
            client.commands,
        )

    def test_fetch_messages_records_stage_timings_and_downloaded_bytes(self) -> None:
        InstrumentedIMAP.reset(count=3)
        diagnostics = FetchDiagnostics()

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=2, diagnostics=diagnostics)

        expected_raw_bytes = sum(len(record.raw_message) for record in records)
        self.assertEqual([record.uid for record in records], ["2", "3"])
        self.assertEqual(diagnostics.message_count, 2)
        self.assertEqual(diagnostics.raw_bytes, expected_raw_bytes)
        for key in ["oauth_ms", "connect_ms", "auth_ms", "select_ms", "fetch_ms", "parse_ms"]:
            self.assertIn(key, diagnostics.timings)
            self.assertIsInstance(diagnostics.timings[key], int)
            self.assertGreaterEqual(diagnostics.timings[key], 0)

    def test_fetch_messages_records_failed_stage_timing_before_raising(self) -> None:
        InstrumentedIMAP.reset(count=2)
        InstrumentedIMAP.fetch_status = "NO"
        diagnostics = FetchDiagnostics()

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError):
                fetch_messages(_account(), limit=2, diagnostics=diagnostics)

        self.assertIn("fetch_ms", diagnostics.timings)
        self.assertEqual(diagnostics.raw_bytes, 0)
        self.assertEqual(diagnostics.message_count, 0)

    def test_fetch_messages_empty_uid_search_skips_fetch(self) -> None:
        InstrumentedIMAP.reset(count=0)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=20)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual(records, [])
        self.assertEqual(client.commands, [
            ("AUTHENTICATE", "XOAUTH2", b"user=user@outlook.com\x01auth=Bearer access-token\x01\x01"),
            ("SELECT", b'"INBOX"', True),
            ("UID", "SEARCH", None, "ALL"),
        ])

    def test_fetch_messages_limit_larger_than_mailbox_uses_one_batch_fetch(self) -> None:
        InstrumentedIMAP.reset(count=2)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=10)

        client = InstrumentedIMAP.instances[0]
        self.assertEqual([record.uid for record in records], ["1", "2"])
        self.assertIn(("UID", "FETCH", "1,2", "(UID BODY.PEEK[])"), client.commands)
        self.assertEqual(sum(1 for command in client.commands if command[:2] == ("UID", "FETCH")), 1)
        self.assertEqual(sum(1 for command in client.commands if command[0] == "FETCH"), 0)

    def test_fetch_messages_uid_search_status_failure_is_readable(self) -> None:
        InstrumentedIMAP.reset(count=2)
        InstrumentedIMAP.search_status = "NO"

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=2)

        self.assertIn("failed to search message UIDs", str(raised.exception))
        self.assertIn("NO", str(raised.exception))
        client = InstrumentedIMAP.instances[0]
        self.assertEqual(sum(1 for command in client.commands if command[:2] == ("UID", "FETCH")), 0)

    def test_fetch_messages_uid_search_exception_is_readable(self) -> None:
        InstrumentedIMAP.reset(count=2)
        InstrumentedIMAP.search_error = OSError("search connection lost")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=2)

        self.assertIn("search message UIDs failed", str(raised.exception))
        self.assertIn("search connection lost", str(raised.exception))

    def test_fetch_messages_batch_fetch_failure_is_readable(self) -> None:
        InstrumentedIMAP.reset(count=2)
        InstrumentedIMAP.fetch_status = "NO"

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=2)

        self.assertIn("failed to fetch message UIDs", str(raised.exception))
        self.assertIn("NO", str(raised.exception))

    def test_fetch_messages_uid_fetch_exception_is_readable(self) -> None:
        InstrumentedIMAP.reset(count=2)
        InstrumentedIMAP.fetch_error = OSError("fetch connection lost")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=2)

        self.assertIn("fetch message UIDs 1,2 failed", str(raised.exception))
        self.assertIn("fetch connection lost", str(raised.exception))

    def test_fetch_messages_single_malformed_message_is_readable(self) -> None:
        InstrumentedIMAP.reset(count=2)
        InstrumentedIMAP.malformed_sequences = {2}

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=2)

        self.assertIn("FETCH response item", str(raised.exception))

    def test_fetch_messages_select_failure_is_readable(self) -> None:
        InstrumentedIMAP.reset(count=2, select_status="NO")

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            with self.assertRaises(ImapReceiveError) as raised:
                fetch_messages(_account(), limit=2)

        self.assertIn("failed to select mailbox 'INBOX': NO", str(raised.exception))

    def test_fetch_messages_keeps_xoauth2_payload(self) -> None:
        InstrumentedIMAP.reset(count=1)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ), patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            fetch_messages(_account(), limit=1)

        self.assertEqual(
            InstrumentedIMAP.instances[0].commands[0],
            ("AUTHENTICATE", "XOAUTH2", b"user=user@outlook.com\x01auth=Bearer access-token\x01\x01"),
        )

    def test_negative_limit_returns_empty_without_token_or_imap_connection(self) -> None:
        InstrumentedIMAP.reset(count=3)

        with patch(
            "mail_receiver.imap_client.refresh_access_token",
            return_value=SimpleNamespace(access_token="access-token"),
        ) as refresh_token, patch("mail_receiver.imap_client.imaplib.IMAP4_SSL", InstrumentedIMAP):
            records = fetch_messages(_account(), limit=-1)

        self.assertEqual(records, [])
        refresh_token.assert_not_called()
        self.assertEqual(InstrumentedIMAP.instances, [])


if __name__ == "__main__":
    unittest.main()
