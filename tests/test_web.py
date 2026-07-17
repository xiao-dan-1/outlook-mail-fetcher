import base64
from pathlib import Path
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import socket
import threading
import time
from tempfile import TemporaryDirectory
import unittest

from unittest.mock import patch

from mail_receiver import web
from mail_receiver.imap_client import AccountCheckResult, EmailRecord
from mail_receiver.web import (
    WebConfig,
    build_parser,
    check_accounts_data,
    create_handler,
    fetch_data,
    inspect_accounts_data,
    inspect_input_accounts_data,
)


class WebServiceTests(unittest.TestCase):
    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str | None, dict]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(WebConfig()))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            response_body = json.loads(response.read().decode("utf-8"))
            return response.status, response.getheader("Content-Type"), response_body
        finally:
            conn.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def assert_json_error(self, response: tuple[int, str | None, dict], status: int) -> None:
        response_status, content_type, body = response
        self.assertEqual(response_status, status)
        self.assertEqual(content_type, "application/json; charset=utf-8")
        self.assertIsInstance(body["error"], str)

    def request_raw_json(
        self,
        request: bytes,
        *,
        max_body_bytes: int = 1024 * 1024,
        read_timeout: float = 0.1,
        shutdown_write: bool = False,
        client_timeout: float = 1.0,
        expect_eof: bool = False,
        delayed_chunks: tuple[bytes, ...] = (),
        chunk_delay: float = 0.0,
    ) -> tuple[int, str | None, dict]:
        handler = create_handler(WebConfig())
        handler.max_json_body_bytes = max_body_bytes
        handler.request_read_timeout = read_timeout
        handler.protocol_version = "HTTP/1.1"
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        sock = socket.create_connection(server.server_address, timeout=client_timeout)
        sock.settimeout(client_timeout)
        sender_thread: threading.Thread | None = None
        try:
            sock.sendall(request)
            if delayed_chunks:
                def send_delayed_chunks() -> None:
                    for chunk in delayed_chunks:
                        time.sleep(chunk_delay)
                        try:
                            sock.sendall(chunk)
                        except OSError:
                            break

                sender_thread = threading.Thread(target=send_delayed_chunks, daemon=True)
                sender_thread.start()
            if shutdown_write:
                sock.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                response_bytes = b"".join(chunks)
                if b"\r\n\r\n" not in response_bytes:
                    continue
                header_bytes, body = response_bytes.split(b"\r\n\r\n", 1)
                content_length = 0
                for line in header_bytes.split(b"\r\n")[1:]:
                    if line.lower().startswith(b"content-length:"):
                        content_length = int(line.split(b":", 1)[1].strip())
                        break
                if len(body) >= content_length and not expect_eof:
                    break
        finally:
            sock.close()
            if sender_thread is not None:
                sender_thread.join(timeout=1)
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        response_bytes = b"".join(chunks)
        self.assertIn(b"\r\n\r\n", response_bytes)
        header_bytes, body = response_bytes.split(b"\r\n\r\n", 1)
        status = int(header_bytes.split(b"\r\n", 1)[0].split()[1])
        content_type = None
        for line in header_bytes.split(b"\r\n")[1:]:
            if line.lower().startswith(b"content-type:"):
                content_type = line.split(b":", 1)[1].strip().decode("ascii")
                break
        return status, content_type, json.loads(body.decode("utf-8"))

    def test_post_invalid_json_returns_json_bad_request(self) -> None:
        response = self.request_json(
            "POST",
            "/api/accounts",
            body=b'{"account_text":',
            headers={"Content-Type": "application/json"},
        )

        self.assert_json_error(response, 400)

    def test_post_invalid_utf8_returns_json_bad_request(self) -> None:
        response = self.request_json("POST", "/api/accounts", body=b"\xff")

        self.assert_json_error(response, 400)

    def test_post_invalid_content_length_returns_json_bad_request(self) -> None:
        for content_length in ("not-a-number", "-1", "+2"):
            with self.subTest(content_length=content_length):
                response = self.request_json(
                    "POST",
                    "/api/accounts",
                    body=b"{}",
                    headers={"Content-Length": content_length},
                )

                self.assert_json_error(response, 400)
                self.assertIn("Content-Length", response[2]["error"])

    def test_post_requires_top_level_json_object(self) -> None:
        for body in (b"[]", b"null", b'"text"', b"42"):
            with self.subTest(body=body):
                response = self.request_json("POST", "/api/accounts", body=body)

                self.assert_json_error(response, 400)
                self.assertIn("object", response[2]["error"])

    def test_post_rejects_non_finite_json_constants(self) -> None:
        account_text = "user@outlook.com----secret----client----refresh-token"
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                body = json.dumps({"account_text": account_text})[:-1] + f', "value": {constant}}}'
                response = self.request_json("POST", "/api/accounts", body=body.encode("utf-8"))

                self.assert_json_error(response, 400)
                self.assertIn(constant, response[2]["error"])

    def test_fetch_rejects_non_integer_limit_over_http(self) -> None:
        account_text = "user@outlook.com----secret----client----refresh-token"
        for limit in (1.9, True, "8"):
            with self.subTest(limit=limit):
                response = self.request_json(
                    "POST",
                    "/api/fetch",
                    body=json.dumps(
                        {"account_text": account_text, "mock": True, "limit": limit}
                    ).encode("utf-8"),
                )

                self.assert_json_error(response, 400)
                self.assertIn("limit", response[2]["error"])

    def test_check_rejects_non_integer_imap_port_over_http(self) -> None:
        response = self.request_json(
            "POST",
            "/api/check",
            body=json.dumps(
                {
                    "account_text": "user@outlook.com----secret----client----refresh-token",
                    "imap_port": "abc",
                }
            ).encode("utf-8"),
        )

        self.assert_json_error(response, 400)
        self.assertIn("imap_port", response[2]["error"])

    def test_fetch_rejects_string_boolean_fields_over_http(self) -> None:
        account_text = "user@outlook.com----secret----client----refresh-token"
        for name in ("mock", "include_raw", "stop_on_error"):
            with self.subTest(name=name):
                response = self.request_json(
                    "POST",
                    "/api/fetch",
                    body=json.dumps(
                        {"account_text": account_text, "mock": True, name: "false"}
                    ).encode("utf-8"),
                )

                self.assert_json_error(response, 400)
                self.assertIn(name, response[2]["error"])

    def test_payload_int_rejects_non_finite_floats_with_field_name(self) -> None:
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "imap_timeout"):
                    web.payload_int({"imap_timeout": value}, "imap_timeout", 8)

    def test_payload_int_accepts_only_int_values(self) -> None:
        self.assertEqual(web.payload_int({}, "limit", 20), 20)
        self.assertEqual(web.payload_int({"limit": None}, "limit", 20), 20)
        self.assertEqual(web.payload_int({"limit": ""}, "limit", 20), 20)
        self.assertEqual(web.payload_int({"limit": 8}, "limit", 20), 8)
        for value in (True, False, 1.9, "8", "abc"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "limit"):
                    web.payload_int({"limit": value}, "limit", 20)

    def test_payload_bool_accepts_only_boolean_values(self) -> None:
        self.assertFalse(web.payload_bool({}, "mock", False))
        self.assertTrue(web.payload_bool({"mock": None}, "mock", True))
        self.assertFalse(web.payload_bool({"mock": False}, "mock", True))
        self.assertTrue(web.payload_bool({"mock": True}, "mock", False))
        for value in ("false", "true", 0, 1, ""):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "mock"):
                    web.payload_bool({"mock": value}, "mock", False)

    def test_unknown_post_route_returns_json_not_found_without_reading_body(self) -> None:
        response = self.request_json(
            "POST",
            "/api/unknown",
            headers={"Content-Length": "not-a-number"},
        )

        self.assert_json_error(response, 404)

    def test_post_empty_body_remains_an_empty_object(self) -> None:
        response = self.request_json("POST", "/api/accounts")

        self.assert_json_error(response, 400)
        self.assertIn("请先", response[2]["error"])

    def test_post_rejects_oversized_body_before_reading_it(self) -> None:
        response = self.request_raw_json(
            b"POST /api/accounts HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Length: 1048577\r\n"
            b"\r\n",
            expect_eof=True,
        )

        self.assert_json_error(response, 413)

    def test_post_partial_body_times_out(self) -> None:
        response = self.request_raw_json(
            b"POST /api/accounts HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"{",
            read_timeout=0.05,
            expect_eof=True,
        )

        self.assert_json_error(response, 408)

    def test_post_body_timeout_is_a_total_deadline(self) -> None:
        response = self.request_raw_json(
            b"POST /api/accounts HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Length: 7\r\n"
            b"\r\n"
            b"{",
            read_timeout=0.1,
            expect_eof=True,
            delayed_chunks=(b'"', b"a", b'"', b":", b"1", b"}"),
            chunk_delay=0.06,
        )

        self.assert_json_error(response, 408)

    def test_post_short_body_returns_bad_request(self) -> None:
        response = self.request_raw_json(
            b"POST /api/accounts HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Length: 10\r\n"
            b"Connection: close\r\n\r\n"
            b"{}",
            shutdown_write=True,
        )

        self.assert_json_error(response, 400)
        self.assertIn("incomplete", response[2]["error"].lower())

    def test_post_accepts_body_at_configured_limit(self) -> None:
        body = b'{"padding":"' + (b"x" * 46) + b'"}'
        self.assertEqual(len(body), 60)
        response = self.request_raw_json(
            b"POST /api/accounts HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Length: 60\r\n"
            b"Connection: close\r\n\r\n"
            + body,
            max_body_bytes=60,
        )

        self.assert_json_error(response, 400)
        self.assertNotEqual(response[0], 413)

    def test_web_parser_does_not_default_to_order_account_file(self) -> None:
        args = build_parser().parse_args([])

        self.assertIsNone(args.account_file)

    def test_main_without_account_file_does_not_print_account_file(self) -> None:
        class FakeServer:
            def __init__(self, _address, _handler):
                self.closed = False

            def serve_forever(self):
                return None

            def server_close(self):
                self.closed = True

        output = io.StringIO()

        with patch("mail_receiver.web.ThreadingHTTPServer", FakeServer), redirect_stdout(output):
            result = web.main(["--host", "127.0.0.1", "--port", "8765"])

        self.assertEqual(result, 0)
        self.assertIn("Mail receiver debug UI: http://127.0.0.1:8765/", output.getvalue())
        self.assertNotIn("account_file=", output.getvalue())

    def test_main_prints_account_file_when_explicitly_configured(self) -> None:
        class FakeServer:
            def __init__(self, _address, _handler):
                self.closed = False

            def serve_forever(self):
                return None

            def server_close(self):
                self.closed = True

        output = io.StringIO()

        with patch("mail_receiver.web.ThreadingHTTPServer", FakeServer), redirect_stdout(output):
            result = web.main(
                [
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8765",
                    "--account-file",
                    "accounts.txt",
                ]
            )

        self.assertEqual(result, 0)
        self.assertIn("account_file=accounts.txt", output.getvalue())

    def test_input_accounts_requires_text_or_configured_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "请先粘贴账号信息"):
            inspect_input_accounts_data({}, WebConfig(account_file=None))

    def test_config_endpoint_uses_json_null_when_account_file_is_not_configured(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(WebConfig()))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
            conn.request("GET", "/api/config")
            response = conn.getresponse()
            data = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(response.status, 200)
        self.assertIsNone(data["account_file"])
        self.assertRegex(data["version"], r"^\d+\.\d+\.\d+$")

    def test_inspect_accounts_returns_masked_accounts(self) -> None:
        with TemporaryDirectory() as directory:
            account_file = Path(directory) / "accounts.txt"
            account_file.write_text(
                "user@outlook.com----secret----client----refresh-token\n",
                encoding="utf-8",
            )

            data = inspect_accounts_data(account_file)

            self.assertEqual(data["count"], 1)
            self.assertEqual(data["accounts"][0]["email"], "user@outlook.com")
            self.assertNotEqual(data["accounts"][0]["password"], "secret")
            self.assertNotEqual(data["accounts"][0]["refresh_token"], "refresh-token")

    def test_mock_fetch_returns_messages_without_local_store(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            account_file = base / "accounts.txt"
            db_path = base / "mail.sqlite3"
            account_file.write_text(
                "user@outlook.com----secret----client----refresh-token\n",
                encoding="utf-8",
            )
            config = WebConfig(account_file=account_file)

            fetch_result = fetch_data({"mock": True, "limit": 2}, config)

            self.assertEqual(fetch_result["accounts"], 1)
            self.assertEqual(fetch_result["fetched"], 2)
            self.assertEqual(fetch_result["failed"], 0)
            self.assertEqual(len(fetch_result["messages"]), 2)
            self.assertTrue(fetch_result["messages"][0]["raw_message_complete"])
            self.assertNotIn("raw_message", fetch_result["messages"][0])
            self.assertNotIn("raw_message_base64", fetch_result["messages"][0])
            self.assertEqual(fetch_result["messages"][0]["uidvalidity"], "mock")
            self.assertFalse(db_path.exists())

    def test_mock_fetch_can_include_raw_message_when_requested(self) -> None:
        with TemporaryDirectory() as directory:
            account_file = Path(directory) / "accounts.txt"
            account_file.write_text(
                "user@outlook.com----secret----client----refresh-token\n",
                encoding="utf-8",
            )
            config = WebConfig(account_file=account_file)

            fetch_result = fetch_data({"mock": True, "limit": 1, "include_raw": True}, config)

            self.assertEqual(fetch_result["fetched"], 1)
            message = fetch_result["messages"][0]
            self.assertTrue(message["raw_message_complete"])
            self.assertIn("raw_message", message)
            self.assertIn("Subject: Welcome debug message 1", message["raw_message"])
            self.assertEqual(
                base64.b64decode(message["raw_message_base64"]),
                message["raw_message"].encode("utf-8"),
            )
            self.assertEqual(message["uidvalidity"], "mock")

    def test_fetch_include_raw_preserves_non_utf8_bytes_as_base64(self) -> None:
        raw_message = b"Subject: Raw\r\n\r\ncaf\xe9"
        record = EmailRecord(
            account_email="user@outlook.com",
            mailbox="INBOX",
            uid="123",
            uidvalidity="456",
            message_id="<raw@example.com>",
            subject="Raw",
            sender="sender@example.com",
            recipients="user@outlook.com",
            sent_at=None,
            body_preview="caf�",
            raw_message=raw_message,
            raw_message_complete=False,
        )

        with patch("mail_receiver.web.fetch_messages", return_value=[record]):
            fetch_result = fetch_data(
                {
                    "account_text": "user@outlook.com----secret----client----refresh-token",
                    "include_raw": True,
                },
                WebConfig(),
            )

        message = fetch_result["messages"][0]
        self.assertIn("caf�", message["raw_message"])
        self.assertEqual(base64.b64decode(message["raw_message_base64"]), raw_message)
        self.assertFalse(message["raw_message_complete"])

    def test_mock_fetch_preserves_zero_limit(self) -> None:
        with TemporaryDirectory() as directory:
            account_file = Path(directory) / "accounts.txt"
            account_file.write_text(
                "user@outlook.com----secret----client----refresh-token\n",
                encoding="utf-8",
            )
            config = WebConfig(account_file=account_file)

            fetch_result = fetch_data({"mock": True, "limit": 0}, config)

            self.assertEqual(fetch_result["fetched"], 0)
            self.assertEqual(fetch_result["failed"], 0)
            self.assertEqual(fetch_result["messages"], [])

    def test_inline_fetch_returns_json_null_account_file(self) -> None:
        result = fetch_data(
            {
                "account_text": "user@outlook.com----secret----client----refresh-token",
                "mock": True,
                "limit": 0,
            },
            WebConfig(),
        )

        self.assertIsNone(result["account_file"])

    def test_fetch_rejects_limit_outside_server_range_before_work(self) -> None:
        account_text = "user@outlook.com----secret----client----refresh-token"
        for limit in (-1, 101, 1_000_000_000):
            with self.subTest(limit=limit), patch(
                "mail_receiver.web.mock_messages"
            ) as mock_fetch, patch("mail_receiver.web.fetch_messages") as real_fetch:
                with self.assertRaisesRegex(ValueError, "limit"):
                    fetch_data(
                        {"account_text": account_text, "mock": True, "limit": limit},
                        WebConfig(),
                    )

                mock_fetch.assert_not_called()
                real_fetch.assert_not_called()

    def test_fetch_accepts_server_limit_boundary(self) -> None:
        account_text = "user@outlook.com----secret----client----refresh-token"
        with patch("mail_receiver.web.mock_messages", return_value=[]) as mock_fetch:
            result = fetch_data(
                {"account_text": account_text, "mock": True, "limit": 100},
                WebConfig(),
            )

        self.assertEqual(result["failed"], 0)
        self.assertEqual(mock_fetch.call_args.kwargs["limit"], 100)

    def test_http_fetch_rejects_limit_outside_server_range(self) -> None:
        account_text = "user@outlook.com----secret----client----refresh-token"
        for limit in (-1, 101, 1_000_000_000):
            with self.subTest(limit=limit), patch(
                "mail_receiver.web.mock_messages"
            ) as mock_fetch, patch("mail_receiver.web.fetch_messages") as real_fetch:
                response = self.request_json(
                    "POST",
                    "/api/fetch",
                    body=json.dumps(
                        {"account_text": account_text, "mock": True, "limit": limit}
                    ).encode("utf-8"),
                )

                self.assert_json_error(response, 400)
                self.assertIn("limit", response[2]["error"])
                mock_fetch.assert_not_called()
                real_fetch.assert_not_called()

    def test_mock_fetch_can_limit_to_selected_account(self) -> None:
        with TemporaryDirectory() as directory:
            account_file = Path(directory) / "accounts.txt"
            account_file.write_text(
                "\n".join(
                    [
                        "first@outlook.com----secret----client----refresh-token",
                        "second@outlook.com----secret----client----refresh-token",
                    ]
                ),
                encoding="utf-8",
            )
            config = WebConfig(account_file=account_file)

            fetch_result = fetch_data(
                {"mock": True, "limit": 1, "account": "second@outlook.com"},
                config,
            )

            self.assertEqual(fetch_result["accounts"], 1)
            self.assertEqual(fetch_result["fetched"], 1)
            self.assertEqual(fetch_result["messages"][0]["account_email"], "second@outlook.com")

    def test_input_accounts_are_supported(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(
                account_file=Path(directory) / "missing.txt",
            )

            data = inspect_input_accounts_data(
                {
                    "account_text": "user@outlook.com----secret----client----refresh-token",
                },
                config,
            )

            self.assertEqual(data["count"], 1)
            self.assertEqual(data["accounts"][0]["email"], "user@outlook.com")

    def test_check_accounts_uses_imap_validation_without_saving(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(
                account_file=Path(directory) / "missing.txt",
            )

            with patch(
                "mail_receiver.web.check_account",
                return_value=AccountCheckResult(
                    account_email="user@outlook.com",
                    mailbox="INBOX",
                    message_count=7,
                ),
            ):
                data = check_accounts_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                    },
                    config,
                )

            self.assertEqual(data["ok"], 1)
            self.assertEqual(data["failed"], 0)
            self.assertEqual(data["rows"][0]["message_count"], 7)

    def test_check_accounts_passes_imap_timeout_to_core_client(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")
            seen_kwargs = {}

            def fake_check(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return AccountCheckResult(
                    account_email="user@outlook.com",
                    mailbox="INBOX",
                    message_count=1,
                )

            with patch("mail_receiver.web.check_account", side_effect=fake_check):
                data = check_accounts_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "imap_timeout": 8,
                    },
                    config,
                )

            self.assertEqual(data["ok"], 1)
            self.assertEqual(seen_kwargs["imap_timeout"], 8)

    def test_check_accounts_uses_fast_web_timeouts_by_default(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")
            seen_kwargs = {}

            def fake_check(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return AccountCheckResult(
                    account_email="user@outlook.com",
                    mailbox="INBOX",
                    message_count=1,
                )

            with patch("mail_receiver.web.check_account", side_effect=fake_check):
                data = check_accounts_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                    },
                    config,
                )

            self.assertEqual(data["ok"], 1)
            self.assertEqual(seen_kwargs["imap_timeout"], 8)
            self.assertEqual(seen_kwargs["token_timeout"], 8)

    def test_fetch_passes_imap_timeout_to_core_client(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")
            seen_kwargs = {}

            def fake_fetch(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return []

            with patch("mail_receiver.web.fetch_messages", side_effect=fake_fetch):
                data = fetch_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "limit": 1,
                        "imap_timeout": 6,
                    },
                    config,
                )

            self.assertEqual(data["failed"], 0)
            self.assertEqual(seen_kwargs["imap_timeout"], 6)

    def test_fetch_uses_fast_web_timeouts_by_default(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")
            seen_kwargs = {}

            def fake_fetch(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return []

            with patch("mail_receiver.web.fetch_messages", side_effect=fake_fetch):
                data = fetch_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "limit": 5,
                    },
                    config,
                )

            self.assertEqual(data["failed"], 0)
            self.assertEqual(seen_kwargs["imap_timeout"], 8)
            self.assertEqual(seen_kwargs["token_timeout"], 8)

    def test_fetch_failure_rows_classify_failure_stage(self) -> None:
        cases = {
            "token refresh network error: timed out": "oauth",
            "connect to outlook.office365.com:993 timed out": "connect",
            "authenticate with XOAUTH2 failed: NO": "auth",
            "select mailbox 'INBOX' timed out": "select",
            "failed to fetch messages 996:*: NO": "fetch",
        }
        for message, expected_stage in cases.items():
            with self.subTest(message=message), TemporaryDirectory() as directory:
                config = WebConfig(account_file=Path(directory) / "missing.txt")

                with patch("mail_receiver.web.fetch_messages", side_effect=RuntimeError(message)):
                    data = fetch_data(
                        {
                            "account_text": "user@outlook.com----secret----client----refresh-token",
                            "limit": 5,
                        },
                        config,
                    )

                self.assertEqual(data["failed"], 1)
                self.assertEqual(data["rows"][0]["stage"], expected_stage)

    def test_fetch_uses_partial_preview_fetch_by_default(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")
            seen_kwargs = {}

            def fake_fetch(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return []

            with patch("mail_receiver.web.fetch_messages", side_effect=fake_fetch):
                data = fetch_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "limit": 5,
                    },
                    config,
                )

            self.assertEqual(data["failed"], 0)
            self.assertEqual(seen_kwargs["limit"], 5)
            self.assertEqual(seen_kwargs["max_bytes"], 16384)

    def test_fetch_include_raw_uses_full_message_fetch(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")
            seen_kwargs = {}

            def fake_fetch(_account, **kwargs):
                seen_kwargs.update(kwargs)
                return []

            with patch("mail_receiver.web.fetch_messages", side_effect=fake_fetch):
                data = fetch_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "limit": 5,
                        "include_raw": True,
                    },
                    config,
                )

            self.assertEqual(data["failed"], 0)
            self.assertEqual(seen_kwargs["limit"], 5)
            self.assertIsNone(seen_kwargs["max_bytes"])

    def test_fetch_rows_include_elapsed_milliseconds_per_account(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")

            def fake_fetch(_account, **_kwargs):
                return []

            with patch("mail_receiver.web.fetch_messages", side_effect=fake_fetch):
                data = fetch_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "limit": 1,
                    },
                    config,
                )

            self.assertEqual(data["failed"], 0)
            self.assertIsInstance(data["rows"][0]["elapsed_ms"], int)
            self.assertGreaterEqual(data["rows"][0]["elapsed_ms"], 0)

    def test_fetch_rows_include_stage_timings_and_downloaded_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")

            def fake_fetch(_account, **kwargs):
                diagnostics = kwargs["diagnostics"]
                diagnostics.timings.update(
                    {
                        "oauth_ms": 11,
                        "connect_ms": 22,
                        "auth_ms": 33,
                        "select_ms": 44,
                        "fetch_ms": 2500,
                        "parse_ms": 55,
                    }
                )
                diagnostics.raw_bytes = 1536
                diagnostics.message_count = 1
                return []

            with patch("mail_receiver.web.fetch_messages", side_effect=fake_fetch):
                data = fetch_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "limit": 1,
                    },
                    config,
                )

            row = data["rows"][0]
            self.assertEqual(data["failed"], 0)
            self.assertEqual(row["timings"]["fetch_ms"], 2500)
            self.assertEqual(row["raw_bytes"], 1536)
            self.assertEqual(row["downloaded_bytes"], 1536)
            self.assertEqual(row["message_count"], 1)

    def test_fetch_failure_rows_keep_partial_stage_diagnostics(self) -> None:
        with TemporaryDirectory() as directory:
            config = WebConfig(account_file=Path(directory) / "missing.txt")

            def fake_fetch(_account, **kwargs):
                diagnostics = kwargs["diagnostics"]
                diagnostics.timings["connect_ms"] = 8001
                raise RuntimeError("connect to outlook.office365.com:993 timed out")

            with patch("mail_receiver.web.fetch_messages", side_effect=fake_fetch):
                data = fetch_data(
                    {
                        "account_text": "user@outlook.com----secret----client----refresh-token",
                        "limit": 5,
                    },
                    config,
                )

            row = data["rows"][0]
            self.assertEqual(data["failed"], 1)
            self.assertEqual(row["stage"], "connect")
            self.assertEqual(row["timings"]["connect_ms"], 8001)
            self.assertEqual(row["raw_bytes"], 0)
            self.assertEqual(row["message_count"], 0)


if __name__ == "__main__":
    unittest.main()
