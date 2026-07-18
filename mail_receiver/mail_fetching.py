from __future__ import annotations

from time import perf_counter
from typing import Callable

from .accounts import Account
from .application import (
    AccountCheckOptions,
    AccountFetchOptions,
    FetchDiagnostics,
    MailboxCheck,
)
from .imap_client import check_account, fetch_messages, mock_messages
from .message_parsing import EmailRecord


class OutlookAccountMailboxChecker:
    def __init__(self, check_function: Callable | None = None) -> None:
        self._check_function = check_function or check_account

    def check(self, account: Account, options: AccountCheckOptions) -> MailboxCheck:
        result = self._check_function(
            account,
            mailbox=options.mailbox,
            host=options.host,
            port=options.port,
            imap_timeout=options.imap_timeout,
            token_endpoint=options.token_endpoint,
            scope=options.scope,
            token_timeout=options.token_timeout,
            debug=options.debug,
        )
        return MailboxCheck(
            mailbox=result.mailbox,
            message_count=result.message_count,
        )


class OutlookAccountMailFetcher:
    def __init__(self, fetch_function: Callable | None = None) -> None:
        self._fetch_function = fetch_function or fetch_messages

    def fetch(
        self,
        account: Account,
        options: AccountFetchOptions,
        diagnostics: FetchDiagnostics,
    ) -> list[EmailRecord]:
        return self._fetch_function(
            account,
            mailbox=options.mailbox,
            limit=options.limit,
            max_bytes=options.max_bytes,
            host=options.host,
            port=options.port,
            imap_timeout=options.imap_timeout,
            token_endpoint=options.token_endpoint,
            scope=options.scope,
            token_timeout=options.token_timeout,
            debug=options.debug,
            diagnostics=diagnostics,
        )


class MockAccountMailFetcher:
    def __init__(self, fetch_function: Callable | None = None) -> None:
        self._fetch_function = fetch_function or mock_messages

    def fetch(
        self,
        account: Account,
        options: AccountFetchOptions,
        diagnostics: FetchDiagnostics,
    ) -> list[EmailRecord]:
        started_at = perf_counter()
        records = self._fetch_function(
            account,
            mailbox=options.mailbox,
            limit=options.limit,
        )
        diagnostics.timings["fetch_ms"] = max(0, round((perf_counter() - started_at) * 1000))
        diagnostics.timings["parse_ms"] = 0
        diagnostics.raw_bytes = sum(len(record.raw_message) for record in records)
        diagnostics.message_count = len(records)
        return records


__all__ = [
    "MockAccountMailFetcher",
    "OutlookAccountMailboxChecker",
    "OutlookAccountMailFetcher",
]
