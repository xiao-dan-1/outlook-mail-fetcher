from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import imaplib
import logging
import re
import socket
from time import perf_counter
from typing import Callable, Iterable, TypeVar

from .accounts import Account
from .oauth import DEFAULT_SCOPE, TOKEN_ENDPOINT, refresh_access_token


LOGGER = logging.getLogger(__name__)
DEFAULT_IMAP_HOST = "outlook.office365.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_IMAP_TIMEOUT = 30
FETCH_MESSAGE_PARTS = "(UID BODY.PEEK[])"
FETCH_UID_RE = re.compile(rb"\bUID\s+([0-9]+)\b")
FETCH_RESPONSE_START_RE = re.compile(rb"^\s*[0-9]+\s+\(")
RFC822_SIZE_RE = re.compile(rb"\bRFC822\.SIZE\s+([0-9]+)(?=\s|\))", re.IGNORECASE)
UIDVALIDITY_RE = re.compile(rb"\bUIDVALIDITY\s+([0-9]+)\b", re.IGNORECASE)
T = TypeVar("T")


class ImapReceiveError(RuntimeError):
    """Raised when IMAP receiving fails."""


@dataclass(frozen=True)
class EmailRecord:
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
    raw_message: bytes
    raw_message_complete: bool = True


@dataclass(frozen=True)
class AccountCheckResult:
    account_email: str
    mailbox: str
    message_count: int | None


@dataclass(frozen=True)
class MailboxSelection:
    message_count: int
    uidvalidity: str


@dataclass
class FetchDiagnostics:
    timings: dict[str, int] = field(default_factory=dict)
    raw_bytes: int = 0
    message_count: int = 0


@dataclass(frozen=True)
class FetchOptions:
    mailbox: str
    limit: int
    max_bytes: int | None
    host: str
    port: int
    token_endpoint: str
    scope: str
    token_timeout: int
    imap_timeout: int | float | None
    debug: bool
    diagnostics: FetchDiagnostics | None


def build_xoauth2_string(email: str, access_token: str) -> str:
    return f"user={email}\x01auth=Bearer {access_token}\x01\x01"


def check_account(
    account: Account,
    *,
    mailbox: str = "INBOX",
    host: str = DEFAULT_IMAP_HOST,
    port: int = DEFAULT_IMAP_PORT,
    token_endpoint: str = TOKEN_ENDPOINT,
    scope: str = DEFAULT_SCOPE,
    token_timeout: int = 30,
    imap_timeout: int | float | None = DEFAULT_IMAP_TIMEOUT,
    debug: bool = False,
) -> AccountCheckResult:
    token = refresh_access_token(
        account,
        endpoint=token_endpoint,
        scope=scope,
        timeout=token_timeout,
    )
    auth_string = build_xoauth2_string(account.email, token.access_token)

    with _connect_imap(host, port, timeout=imap_timeout) as client:
        if debug:
            client.debug = 4
        _authenticate_xoauth2(client, auth_string)
        selection = _select_mailbox_info(client, mailbox)
        return AccountCheckResult(
            account_email=account.email,
            mailbox=mailbox,
            message_count=selection.message_count,
        )


def fetch_messages(
    account: Account,
    *,
    mailbox: str = "INBOX",
    limit: int = 20,
    max_bytes: int | None = None,
    host: str = DEFAULT_IMAP_HOST,
    port: int = DEFAULT_IMAP_PORT,
    token_endpoint: str = TOKEN_ENDPOINT,
    scope: str = DEFAULT_SCOPE,
    token_timeout: int = 30,
    imap_timeout: int | float | None = DEFAULT_IMAP_TIMEOUT,
    debug: bool = False,
    diagnostics: FetchDiagnostics | None = None,
) -> list[EmailRecord]:
    options = FetchOptions(
        mailbox=mailbox,
        limit=limit,
        max_bytes=max_bytes,
        host=host,
        port=port,
        token_endpoint=token_endpoint,
        scope=scope,
        token_timeout=token_timeout,
        imap_timeout=imap_timeout,
        debug=debug,
        diagnostics=diagnostics,
    )
    if options.limit <= 0:
        if options.diagnostics is not None:
            options.diagnostics.raw_bytes = 0
            options.diagnostics.message_count = 0
        return []

    token = _timed_stage(
        options.diagnostics,
        "oauth",
        lambda: refresh_access_token(
            account,
            endpoint=options.token_endpoint,
            scope=options.scope,
            timeout=options.token_timeout,
        ),
    )
    auth_string = build_xoauth2_string(account.email, token.access_token)

    LOGGER.debug("connecting to %s:%s for %s", options.host, options.port, account.email)
    imap_client = _timed_stage(
        options.diagnostics,
        "connect",
        lambda: _connect_imap(options.host, options.port, timeout=options.imap_timeout),
    )
    with imap_client as client:
        if options.debug:
            client.debug = 4
        _timed_stage(
            options.diagnostics,
            "auth",
            lambda: _authenticate_xoauth2(client, auth_string),
        )
        selection = _timed_stage(
            options.diagnostics,
            "select",
            lambda: _select_mailbox_info(client, options.mailbox),
        )
        payloads = _timed_stage(
            options.diagnostics,
            "fetch",
            lambda: _fetch_recent_message_payloads_by_uid(
                client,
                limit=options.limit,
                message_parts=_message_fetch_parts(options.max_bytes),
            ),
        )
        if not payloads:
            _record_empty_fetch_diagnostics(options.diagnostics)
            return []
        if options.diagnostics is not None:
            options.diagnostics.raw_bytes = sum(
                len(raw_message) for _uid, raw_message, _raw_message_complete in payloads
            )
            options.diagnostics.message_count = len(payloads)
        return _timed_stage(
            options.diagnostics,
            "parse",
            lambda: _records_from_message_payloads(
                payloads,
                account_email=account.email,
                mailbox=options.mailbox,
                uidvalidity=selection.uidvalidity,
            ),
        )


def mock_messages(account: Account, *, mailbox: str = "INBOX", limit: int = 3) -> list[EmailRecord]:
    count = max(limit, 0)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records: list[EmailRecord] = []

    for index in range(1, count + 1):
        uid = f"mock-{account.source_line}-{index}"
        subject = f"Welcome debug message {index}"
        sender = "debug@example.com"
        recipients = account.email
        message_id = f"<{uid}@local-debug>"
        body = (
            f"This is a mock email for {account.email}.\n"
            "It proves parsing, storing, and searching work without touching the network.\n"
        )
        raw = (
            f"Message-ID: {message_id}\r\n"
            f"Date: {now}\r\n"
            f"From: {sender}\r\n"
            f"To: {recipients}\r\n"
            f"Subject: {subject}\r\n"
            "\r\n"
            f"{body}"
        ).encode("utf-8")
        records.append(
            EmailRecord(
                account_email=account.email,
                mailbox=mailbox,
                uid=uid,
                uidvalidity="mock",
                message_id=message_id,
                subject=subject,
                sender=sender,
                recipients=recipients,
                sent_at=now,
                body_preview=body.strip(),
                raw_message=raw,
            )
        )

    return records


def _parse_select_count(data: Iterable[object]) -> int | None:
    for item in data:
        if isinstance(item, bytes):
            try:
                return int(item.decode("ascii"))
            except ValueError:
                continue
    return None


def _select_mailbox_info(client: imaplib.IMAP4_SSL, mailbox: str) -> MailboxSelection:
    status, data = _select_mailbox(client, mailbox)
    if status != "OK":
        raise ImapReceiveError(f"failed to select mailbox {mailbox!r}: {status}")
    message_count = _parse_select_count(data)
    if message_count is None:
        raise ImapReceiveError(f"failed to read mailbox {mailbox!r} message count")
    uidvalidity = _read_uidvalidity(client, data)
    if uidvalidity is None:
        raise ImapReceiveError(f"failed to read mailbox {mailbox!r} UIDVALIDITY")
    return MailboxSelection(message_count=message_count, uidvalidity=uidvalidity)


def _read_uidvalidity(client: imaplib.IMAP4_SSL, select_data: Iterable[object]) -> str | None:
    response = getattr(client, "response", None)
    if callable(response):
        try:
            _status, data = response("UIDVALIDITY")
        except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError):
            pass
        else:
            uidvalidity = _parse_uidvalidity_response(data, allow_bare_digits=True)
            if uidvalidity is not None:
                return uidvalidity
    return _parse_uidvalidity_response(select_data, allow_bare_digits=False)


def _parse_uidvalidity_response(data: Iterable[object], *, allow_bare_digits: bool) -> str | None:
    for item in data:
        item_bytes = _metadata_bytes(item)
        if item_bytes is None:
            continue
        item_bytes = item_bytes.strip()
        if allow_bare_digits and item_bytes.isdigit():
            return item_bytes.decode("ascii")
        match = UIDVALIDITY_RE.search(item_bytes)
        if match is not None:
            return match.group(1).decode("ascii")
    return None


def _fetch_recent_message_payloads_by_uid(
    client: imaplib.IMAP4_SSL,
    *,
    limit: int,
    message_parts: str = FETCH_MESSAGE_PARTS,
) -> list[tuple[str, bytes, bool]]:
    uids = _search_message_uids(client)
    recent_uids = uids[-limit:]
    if not recent_uids:
        return []
    return _fetch_message_payloads_by_uid(
        client,
        uid_set=",".join(recent_uids),
        message_parts=message_parts,
    )


def _search_message_uids(client: imaplib.IMAP4_SSL) -> list[str]:
    status, data = _imap_operation(
        "search message UIDs",
        lambda: client.uid("SEARCH", None, "ALL"),
    )
    if status != "OK":
        raise ImapReceiveError(f"failed to search message UIDs: {status}")

    uid_values: set[int] = set()
    for item in data or []:
        item_bytes = _metadata_bytes(item)
        if item_bytes is None:
            continue
        for uid in item_bytes.split():
            if not uid.isdigit():
                raise ImapReceiveError("IMAP UID SEARCH response included an invalid UID")
            uid_values.add(int(uid))
    return [str(uid) for uid in sorted(uid_values)]


def _fetch_message_payloads_by_uid(
    client: imaplib.IMAP4_SSL,
    *,
    uid_set: str,
    message_parts: str = FETCH_MESSAGE_PARTS,
) -> list[tuple[str, bytes, bool]]:
    status, data = _imap_operation(
        f"fetch message UIDs {uid_set}",
        lambda: client.uid("FETCH", uid_set, message_parts),
    )
    if status != "OK":
        raise ImapReceiveError(f"failed to fetch message UIDs {uid_set}: {status}")
    is_partial = "BODY.PEEK[]<0." in message_parts.upper()
    return list(_iter_fetch_messages(data, is_partial=is_partial))


def _records_from_message_payloads(
    payloads: Iterable[tuple[str, bytes, bool]],
    *,
    account_email: str,
    mailbox: str,
    uidvalidity: str,
) -> list[EmailRecord]:
    records: list[EmailRecord] = []
    for uid, raw_message, raw_message_complete in payloads:
        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        records.append(
            email_record_from_message(
                account_email=account_email,
                mailbox=mailbox,
                uid=uid,
                uidvalidity=uidvalidity,
                message=message,
                raw_message=raw_message,
                raw_message_complete=raw_message_complete,
            )
        )
    return records


def _elapsed_ms_since(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


def _timed_stage(
    diagnostics: FetchDiagnostics | None,
    stage: str,
    operation: Callable[[], T],
) -> T:
    started_at = perf_counter()
    try:
        return operation()
    finally:
        if diagnostics is not None:
            diagnostics.timings[f"{stage}_ms"] = _elapsed_ms_since(started_at)


def _record_empty_fetch_diagnostics(diagnostics: FetchDiagnostics | None) -> None:
    if diagnostics is None:
        return
    diagnostics.raw_bytes = 0
    diagnostics.message_count = 0
    diagnostics.timings.setdefault("fetch_ms", 0)
    diagnostics.timings.setdefault("parse_ms", 0)


def _message_fetch_parts(max_bytes: int | None) -> str:
    if max_bytes is None:
        return FETCH_MESSAGE_PARTS
    safe_max_bytes = max(1, int(max_bytes))
    return f"(UID RFC822.SIZE BODY.PEEK[]<0.{safe_max_bytes}>)"


def _connect_imap(
    host: str,
    port: int,
    *,
    timeout: int | float | None,
) -> imaplib.IMAP4_SSL:
    def connect() -> imaplib.IMAP4_SSL:
        if timeout is None:
            return imaplib.IMAP4_SSL(host, port)
        try:
            return imaplib.IMAP4_SSL(host, port, timeout=timeout)
        except TypeError:
            client = imaplib.IMAP4_SSL(host, port)
            _set_socket_timeout(client, timeout)
            return client

    client = _imap_operation(f"connect to {host}:{port}", connect)
    _set_socket_timeout(client, timeout)
    return client


def _set_socket_timeout(client: imaplib.IMAP4_SSL, timeout: int | float | None) -> None:
    if timeout is None:
        return
    sock = getattr(client, "sock", None)
    settimeout = getattr(sock, "settimeout", None)
    if callable(settimeout):
        settimeout(timeout)


def _authenticate_xoauth2(client: imaplib.IMAP4_SSL, auth_string: str) -> None:
    _imap_operation(
        "authenticate with XOAUTH2",
        lambda: client.authenticate("XOAUTH2", lambda _: auth_string.encode("utf-8")),
    )


def _select_mailbox(
    client: imaplib.IMAP4_SSL,
    mailbox: str,
) -> tuple[str, list[object]]:
    return _imap_operation(f"select mailbox {mailbox!r}", lambda: client.select(mailbox, readonly=True))


def _imap_operation(description: str, operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (TimeoutError, socket.timeout) as exc:
        raise ImapReceiveError(f"{description} timed out") from exc
    except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as exc:
        raise ImapReceiveError(f"{description} failed: {exc}") from exc


def _iter_fetch_messages(
    data: Iterable[object],
    *,
    is_partial: bool = False,
) -> Iterable[tuple[str, bytes, bool]]:
    pending_item: tuple[object, ...] | None = None
    trailer_metadata: list[object] = []
    for item in data:
        if isinstance(item, tuple):
            if pending_item is not None:
                yield _parse_fetch_item(
                    pending_item,
                    trailer_metadata=trailer_metadata,
                    is_partial=is_partial,
                )
            pending_item = item
            trailer_metadata = []
            continue
        if pending_item is not None:
            item_metadata = _metadata_bytes(item)
            if item_metadata is not None and FETCH_RESPONSE_START_RE.match(item_metadata):
                yield _parse_fetch_item(
                    pending_item,
                    trailer_metadata=trailer_metadata,
                    is_partial=is_partial,
                )
                pending_item = None
                trailer_metadata = []
                continue
            trailer_metadata.append(item)
    if pending_item is not None:
        yield _parse_fetch_item(
            pending_item,
            trailer_metadata=trailer_metadata,
            is_partial=is_partial,
        )


def _parse_fetch_item(
    item: tuple[object, ...],
    *,
    trailer_metadata: Iterable[object] = (),
    is_partial: bool = False,
) -> tuple[str, bytes, bool]:
    if len(item) < 2 or not isinstance(item[1], bytes):
        raise ImapReceiveError("IMAP FETCH response item did not include message bytes")

    metadata_parts = []
    for value in (item[0], *trailer_metadata):
        metadata_bytes = _metadata_bytes(value)
        if metadata_bytes is not None:
            metadata_parts.append(metadata_bytes)
    metadata_bytes = b" ".join(metadata_parts)
    match = FETCH_UID_RE.search(metadata_bytes)
    if match is None:
        raise ImapReceiveError("IMAP FETCH response item did not include UID")
    raw_message_complete = True
    if is_partial:
        size_match = RFC822_SIZE_RE.search(metadata_bytes)
        raw_message_complete = False
        if size_match is not None:
            try:
                raw_message_complete = int(size_match.group(1)) == len(item[1])
            except ValueError:
                pass
    return match.group(1).decode("ascii"), item[1], raw_message_complete


def _metadata_bytes(value: object) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    return str(value).encode("ascii", errors="ignore")


def email_record_from_message(
    *,
    account_email: str,
    mailbox: str,
    uid: str,
    uidvalidity: str,
    message: Message,
    raw_message: bytes,
    raw_message_complete: bool = True,
) -> EmailRecord:
    subject = str(message.get("subject", ""))
    sender = str(message.get("from", ""))
    recipients = ", ".join(
        value for value in (message.get("to"), message.get("cc"), message.get("bcc")) if value
    )
    sent_at = _parse_message_date(message.get("date"))
    body_preview = extract_body_text(message)[:1000]

    return EmailRecord(
        account_email=account_email,
        mailbox=mailbox,
        uid=uid,
        uidvalidity=uidvalidity,
        message_id=message.get("message-id"),
        subject=subject,
        sender=sender,
        recipients=recipients,
        sent_at=sent_at,
        body_preview=body_preview,
        raw_message=raw_message,
        raw_message_complete=raw_message_complete,
    )


def _decode_text_payload(payload: bytes, charset: str | None) -> str:
    try:
        return payload.decode(charset or "utf-8", errors="replace")
    except (LookupError, UnicodeError):
        return payload.decode("utf-8", errors="replace")


def _iter_inline_leaf_parts(message: Message) -> Iterable[Message]:
    if not message.is_multipart():
        yield message
        return

    payload = message.get_payload()
    if not isinstance(payload, list):
        return
    for child in payload:
        if not isinstance(child, Message):
            continue
        if child.get_content_disposition() == "attachment":
            continue
        yield from _iter_inline_leaf_parts(child)


def extract_body_text(message: Message) -> str:
    if message.is_multipart():
        plain_parts: list[str] = []
        html_parts: list[str] = []
        for part in _iter_inline_leaf_parts(message):
            content_type = part.get_content_type()
            try:
                content = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset()
                content = _decode_text_payload(payload, charset)
            if content_type == "text/plain":
                plain_text = str(content)
                if plain_text.strip():
                    plain_parts.append(plain_text)
            elif content_type == "text/html":
                html_text = _html_to_text(str(content))
                if html_text:
                    html_parts.append(html_text)
        return "\n".join(plain_parts or html_parts).strip()

    try:
        content = str(message.get_content()).strip()
    except Exception:
        payload = message.get_payload(decode=True)
        if payload is None:
            content = str(message.get_payload()).strip()
            if message.get_content_type() == "text/html":
                return _html_to_text(content)
            return content
        charset = message.get_content_charset()
        content = _decode_text_payload(payload, charset).strip()
    if message.get_content_type() == "text/html":
        return _html_to_text(content)
    return content


class _ReadableHtmlParser(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }
    _SKIP_TAGS = {"head", "style", "script", "noscript", "template", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if self._skip_depth:
            if lowered in self._SKIP_TAGS:
                self._skip_depth += 1
            return
        if lowered in self._SKIP_TAGS:
            self._skip_depth = 1
            return
        if lowered in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._skip_depth:
            if lowered in self._SKIP_TAGS:
                self._skip_depth -= 1
            return
        if lowered in self._BLOCK_TAGS and lowered != "br":
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        return _normalize_readable_text("".join(self._chunks))


def _html_to_text(value: str) -> str:
    parser = _ReadableHtmlParser()
    parser.feed(value)
    parser.close()
    return parser.text()


def _normalize_readable_text(value: str) -> str:
    text = value.replace("\u00a0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _parse_message_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
