from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
import logging
import socket
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__
from .accounts import Account, AccountFormatError, load_accounts, parse_accounts
from .imap_client import (
    DEFAULT_IMAP_HOST,
    DEFAULT_IMAP_PORT,
    FetchDiagnostics,
    check_account,
    fetch_messages,
    mock_messages,
)
from .oauth import DEFAULT_SCOPE, TOKEN_ENDPOINT
from .output import visible_text


LOGGER = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8"}
STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}
WEB_PREVIEW_MAX_BYTES = 16 * 1024
WEB_MAX_FETCH_LIMIT = 100
WEB_DEFAULT_IMAP_TIMEOUT = 8
WEB_DEFAULT_TOKEN_TIMEOUT = 8
WEB_MAX_JSON_BODY_BYTES = 1024 * 1024
WEB_REQUEST_READ_TIMEOUT = 5.0


class RequestBodyTooLargeError(RuntimeError):
    pass


class RequestBodyTimeoutError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebConfig:
    account_file: Path | None = None


def inspect_accounts_data(account_file: str | Path | None) -> dict[str, Any]:
    if not account_file:
        raise ValueError("请先粘贴账号信息或通过 --account-file 指定账号文件")
    accounts = load_accounts(account_file)
    return {
        "account_file": str(account_file),
        "count": len(accounts),
        "accounts": [account_to_dict(account) for account in accounts],
    }


def inspect_input_accounts_data(payload: dict[str, Any], config: WebConfig) -> dict[str, Any]:
    accounts = resolve_accounts(payload, config)
    account_file = resolve_account_file(payload, config)
    return {
        "account_file": str(account_file) if account_file else None,
        "count": len(accounts),
        "accounts": [account_to_dict(account) for account in accounts],
    }


def check_accounts_data(payload: dict[str, Any], config: WebConfig) -> dict[str, Any]:
    accounts = resolve_accounts(payload, config)
    mailbox = str(payload.get("mailbox") or "INBOX")
    selected_account = str(payload.get("account") or "").strip()
    stop_on_error = payload_bool(payload, "stop_on_error", False)
    imap_port = payload_int(payload, "imap_port", DEFAULT_IMAP_PORT)
    imap_timeout = payload_int(payload, "imap_timeout", WEB_DEFAULT_IMAP_TIMEOUT)
    token_timeout = payload_int(payload, "token_timeout", WEB_DEFAULT_TOKEN_TIMEOUT)
    if selected_account:
        accounts = filter_accounts(accounts, selected_account)

    rows: list[dict[str, Any]] = []
    ok_count = 0
    failed = 0
    for account in accounts:
        try:
            result = check_account(
                account,
                mailbox=mailbox,
                host=str(payload.get("imap_host") or DEFAULT_IMAP_HOST),
                port=imap_port,
                imap_timeout=imap_timeout,
                token_endpoint=str(payload.get("token_endpoint") or TOKEN_ENDPOINT),
                scope=str(payload.get("scope") or DEFAULT_SCOPE),
                token_timeout=token_timeout,
                debug=False,
            )
            ok_count += 1
            rows.append(
                {
                    "email": account.email,
                    "ok": True,
                    "stage": "imap",
                    "mailbox": result.mailbox,
                    "message_count": result.message_count,
                    "error": None,
                }
            )
        except Exception as exc:
            failed += 1
            rows.append(
                {
                    "email": account.email,
                    "ok": False,
                    "stage": classify_error(str(exc)),
                    "mailbox": mailbox,
                    "message_count": None,
                    "error": str(exc),
                }
            )
            if stop_on_error:
                break

    return {
        "accounts": len(accounts),
        "ok": ok_count,
        "failed": failed,
        "rows": rows,
    }


def fetch_data(payload: dict[str, Any], config: WebConfig) -> dict[str, Any]:
    mailbox = str(payload.get("mailbox") or "INBOX")
    limit = payload_int(payload, "limit", 20)
    if not 0 <= limit <= WEB_MAX_FETCH_LIMIT:
        raise ValueError(f"limit must be between 0 and {WEB_MAX_FETCH_LIMIT}")
    selected_account = str(payload.get("account") or "").strip()
    use_mock = payload_bool(payload, "mock", False)
    stop_on_error = payload_bool(payload, "stop_on_error", False)
    include_raw = payload_bool(payload, "include_raw", False)
    imap_port = payload_int(payload, "imap_port", DEFAULT_IMAP_PORT)
    imap_timeout = payload_int(payload, "imap_timeout", WEB_DEFAULT_IMAP_TIMEOUT)
    token_timeout = payload_int(payload, "token_timeout", WEB_DEFAULT_TOKEN_TIMEOUT)
    max_bytes = None if include_raw else WEB_PREVIEW_MAX_BYTES

    accounts = resolve_accounts(payload, config)
    if selected_account:
        accounts = filter_accounts(accounts, selected_account)

    rows: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    total_fetched = 0
    failed = 0
    next_id = 1

    for account in accounts:
        account_started_at = perf_counter()
        diagnostics = FetchDiagnostics()
        try:
            if use_mock:
                mock_started_at = perf_counter()
                records = mock_messages(account, mailbox=mailbox, limit=limit)
                diagnostics.timings["fetch_ms"] = elapsed_ms(mock_started_at)
                diagnostics.timings["parse_ms"] = 0
                diagnostics.raw_bytes = sum(len(record.raw_message) for record in records)
                diagnostics.message_count = len(records)
            else:
                records = fetch_messages(
                    account,
                    mailbox=mailbox,
                    limit=limit,
                    max_bytes=max_bytes,
                    host=str(payload.get("imap_host") or DEFAULT_IMAP_HOST),
                    port=imap_port,
                    imap_timeout=imap_timeout,
                    token_endpoint=str(payload.get("token_endpoint") or TOKEN_ENDPOINT),
                    scope=str(payload.get("scope") or DEFAULT_SCOPE),
                    token_timeout=token_timeout,
                    debug=False,
                    diagnostics=diagnostics,
                )
            total_fetched += len(records)
            for record in records:
                messages.append(email_record_to_dict(record, next_id=next_id, include_raw=include_raw))
                next_id += 1
            rows.append(
                {
                    "email": account.email,
                    "ok": True,
                    "fetched": len(records),
                    "elapsed_ms": elapsed_ms(account_started_at),
                    "error": None,
                    **fetch_diagnostics_to_dict(diagnostics),
                }
            )
        except Exception as exc:
            failed += 1
            error = str(exc)
            rows.append(
                {
                    "email": account.email,
                    "ok": False,
                    "stage": classify_error(error),
                    "fetched": 0,
                    "elapsed_ms": elapsed_ms(account_started_at),
                    "error": error,
                    **fetch_diagnostics_to_dict(diagnostics),
                }
            )
            LOGGER.info(
                "fetch failed for %s: %s",
                visible_text(account.email),
                visible_text(error),
            )
            if stop_on_error:
                break

    account_file = resolve_account_file(payload, config)
    return {
        "account_file": str(account_file) if account_file else None,
        "accounts": len(accounts),
        "fetched": total_fetched,
        "failed": failed,
        "rows": rows,
        "messages": messages,
    }


def fetch_diagnostics_to_dict(diagnostics: FetchDiagnostics) -> dict[str, Any]:
    return {
        "timings": dict(diagnostics.timings),
        "raw_bytes": diagnostics.raw_bytes,
        "downloaded_bytes": diagnostics.raw_bytes,
        "message_count": diagnostics.message_count,
    }


def resolve_accounts(payload: dict[str, Any], config: WebConfig) -> list[Account]:
    account_text = str(payload.get("account_text") or "").strip()
    if account_text:
        return parse_accounts(account_text.splitlines())
    account_file = resolve_account_file(payload, config)
    if account_file is None:
        raise ValueError("请先粘贴账号信息或通过 --account-file 指定账号文件")
    return load_accounts(account_file)


def resolve_account_file(payload: dict[str, Any], config: WebConfig) -> Path | None:
    raw_account_file = payload.get("account_file")
    if raw_account_file is not None and str(raw_account_file).strip():
        return Path(str(raw_account_file))
    return config.account_file


def filter_accounts(accounts: list[Account], selected_account: str) -> list[Account]:
    selected = [
        account
        for account in accounts
        if account.email.lower() == selected_account.lower()
    ]
    if not selected:
        raise NotFoundError(f"account not found: {selected_account}")
    return selected


def payload_int(payload: dict[str, Any], name: str, default: int) -> int:
    value = payload.get(name, default)
    if value in (None, ""):
        return default
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def payload_bool(payload: dict[str, Any], name: str, default: bool) -> bool:
    value = payload.get(name, default)
    if value is None:
        return default
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


def classify_error(message: str) -> str:
    lowered = message.lower()
    if "authenticate" in lowered or "authenticated" in lowered or "xoauth2" in lowered:
        return "auth"
    if "token" in lowered or "oauth" in lowered or "refresh" in lowered:
        return "oauth"
    if "select mailbox" in lowered or "failed to select mailbox" in lowered or "mailbox" in lowered:
        return "select"
    if "fetch messages" in lowered or "failed to fetch" in lowered:
        return "fetch"
    if "connect to" in lowered or "connection" in lowered or "network is unreachable" in lowered:
        return "connect"
    if "imap" in lowered:
        return "connect"
    return "unknown"


def account_to_dict(account: Account) -> dict[str, Any]:
    return {
        "line": account.source_line,
        "email": account.email,
        "password": account.masked_password,
        "client_id": account.client_id,
        "refresh_token": account.masked_refresh_token,
    }


def email_record_to_dict(record: Any, *, next_id: int, include_raw: bool = False) -> dict[str, Any]:
    data = {
        "id": next_id,
        "account_email": record.account_email,
        "mailbox": record.mailbox,
        "uid": record.uid,
        "uidvalidity": record.uidvalidity,
        "message_id": record.message_id,
        "subject": record.subject,
        "sender": record.sender,
        "recipients": record.recipients,
        "sent_at": record.sent_at,
        "body_preview": record.body_preview,
        "raw_message_complete": record.raw_message_complete,
    }
    if include_raw:
        data["raw_message"] = record.raw_message.decode("utf-8", errors="replace")
        data["raw_message_base64"] = base64.b64encode(record.raw_message).decode("ascii")
    return data


def create_handler(config: WebConfig) -> type[BaseHTTPRequestHandler]:
    class ReceiverHandler(BaseHTTPRequestHandler):
        server_version = f"OutlookMailFetcher/{__version__}"
        max_json_body_bytes = WEB_MAX_JSON_BODY_BYTES
        request_read_timeout = WEB_REQUEST_READ_TIMEOUT

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("", "/"):
                self._serve_static("index.html")
                return
            if parsed.path.startswith("/static/"):
                self._serve_static(parsed.path.removeprefix("/static/"))
                return
            if parsed.path == "/api/config":
                self._send_json(
                    {
                        "version": __version__,
                        "account_file": str(config.account_file) if config.account_file else None,
                        "defaults": {
                            "mailbox": "INBOX",
                            "limit": 1,
                            "imap_host": DEFAULT_IMAP_HOST,
                            "imap_port": DEFAULT_IMAP_PORT,
                            "imap_timeout": WEB_DEFAULT_IMAP_TIMEOUT,
                            "token_endpoint": TOKEN_ENDPOINT,
                            "token_timeout": WEB_DEFAULT_TOKEN_TIMEOUT,
                            "scope": DEFAULT_SCOPE,
                        },
                    }
                )
                return
            if parsed.path == "/api/accounts":
                query = parse_qs(parsed.query)
                account_file = query.get("account_file", [config.account_file])[0]
                self._run_json(lambda: inspect_accounts_data(account_file))
                return
            self._send_error(HTTPStatus.NOT_FOUND, "not found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            routes = {
                "/api/accounts": inspect_input_accounts_data,
                "/api/check": check_accounts_data,
                "/api/fetch": fetch_data,
            }
            callback = routes.get(parsed.path)
            if callback is None:
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
                return
            self._run_json(lambda: callback(self._read_json(), config))

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.info(
                "%s - %s",
                visible_text(self.address_string()),
                visible_text(format % args),
            )

        def _serve_static(self, relative_path: str) -> None:
            safe_name = relative_path.replace("\\", "/").lstrip("/")
            target = (STATIC_DIR / safe_name).resolve()
            if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                self._send_error(HTTPStatus.FORBIDDEN, "forbidden")
                return
            if not target.exists() or not target.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
                return
            content_type = STATIC_TYPES.get(target.suffix, "application/octet-stream")
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length")
            if raw_length in (None, ""):
                length = 0
            else:
                if not raw_length.isascii() or not raw_length.isdigit():
                    raise ValueError("invalid Content-Length header")
                length = int(raw_length)
            if length <= 0:
                return {}
            if length > self.max_json_body_bytes:
                self.close_connection = True
                raise RequestBodyTooLargeError(
                    f"JSON request body exceeds {self.max_json_body_bytes} bytes"
                )
            previous_timeout = self.connection.gettimeout()
            try:
                deadline = monotonic() + self.request_read_timeout
                chunks: list[bytes] = []
                remaining = length
                read_chunk = getattr(self.rfile, "read1", self.rfile.read)
                while remaining:
                    timeout = deadline - monotonic()
                    if timeout <= 0:
                        self.close_connection = True
                        raise RequestBodyTimeoutError("JSON request body read timed out")
                    self.connection.settimeout(timeout)
                    try:
                        chunk = read_chunk(min(remaining, 64 * 1024))
                    except (TimeoutError, socket.timeout) as exc:
                        self.close_connection = True
                        raise RequestBodyTimeoutError("JSON request body read timed out") from exc
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                body = b"".join(chunks)
            finally:
                self.connection.settimeout(previous_timeout)
            if len(body) != length:
                raise ValueError(
                    f"incomplete JSON request body: expected {length} bytes, got {len(body)}"
                )
            payload = json.loads(
                body.decode("utf-8"),
                parse_constant=self._reject_json_constant,
            )
            if not isinstance(payload, dict):
                raise ValueError("JSON request body must be an object")
            return payload

        @staticmethod
        def _reject_json_constant(value: str) -> None:
            raise ValueError(f"invalid JSON constant: {value}")

        def _run_json(self, callback: Any) -> None:
            try:
                self._send_json(callback())
            except RequestBodyTooLargeError as exc:
                self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, str(exc))
            except RequestBodyTimeoutError as exc:
                self._send_error(HTTPStatus.REQUEST_TIMEOUT, str(exc))
            except (NotFoundError, FileNotFoundError) as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except AccountFormatError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                safe_traceback = visible_text(
                    "".join(
                        traceback.format_exception(
                            type(exc),
                            exc,
                            exc.__traceback__,
                        )
                    )
                )
                LOGGER.error("request failed: %s", safe_traceback)
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            for name, value in JSON_HEADERS.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status=status)

    return ReceiverHandler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local mail receiver debug web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    parser.add_argument("--account-file", help="Default account file.")
    parser.add_argument("--debug", action="store_true", help="Enable verbose server logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    config = WebConfig(account_file=Path(args.account_file) if args.account_file else None)
    handler = create_handler(config)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Mail receiver debug UI: http://{args.host}:{args.port}/")
    if config.account_file:
        print(f"account_file={config.account_file}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nserver stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
