from __future__ import annotations

from typing import Iterable, Protocol

from .message_parsing import EmailRecord


class MailRepository(Protocol):
    def save_many(self, records: Iterable[EmailRecord]) -> int:
        raise NotImplementedError


__all__ = ["MailRepository"]
