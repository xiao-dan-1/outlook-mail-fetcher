from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import re
from typing import Iterable, Protocol


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
class MessageContext:
    account_email: str
    mailbox: str
    uid: str
    uidvalidity: str
    raw_message_complete: bool = True


class MessageParser(Protocol):
    def parse(self, raw_message: bytes, context: MessageContext) -> EmailRecord:
        raise NotImplementedError


class DefaultMessageParser:
    def parse(self, raw_message: bytes, context: MessageContext) -> EmailRecord:
        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        return email_record_from_message(
            account_email=context.account_email,
            mailbox=context.mailbox,
            uid=context.uid,
            uidvalidity=context.uidvalidity,
            message=message,
            raw_message=raw_message,
            raw_message_complete=context.raw_message_complete,
        )


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


__all__ = [
    "DefaultMessageParser",
    "EmailRecord",
    "MessageContext",
    "MessageParser",
    "email_record_from_message",
    "extract_body_text",
]
