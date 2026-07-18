from __future__ import annotations

from dataclasses import dataclass, field
import re
from time import perf_counter
from typing import Protocol, Sequence

from .accounts import Account
from .message_parsing import EmailRecord
from .repositories import MailRepository


@dataclass(frozen=True)
class AccountFetchOptions:
    mailbox: str = "INBOX"
    limit: int = 20
    max_bytes: int | None = None
    host: str = "outlook.office365.com"
    port: int = 993
    token_endpoint: str = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    scope: str = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
    token_timeout: int = 30
    imap_timeout: int | float | None = 30
    debug: bool = False


@dataclass
class FetchDiagnostics:
    timings: dict[str, int] = field(default_factory=dict)
    raw_bytes: int = 0
    message_count: int = 0


class AccountMailFetcher(Protocol):
    def fetch(
        self,
        account: Account,
        options: AccountFetchOptions,
        diagnostics: FetchDiagnostics,
    ) -> list[EmailRecord]:
        raise NotImplementedError


@dataclass
class FetchAccountResult:
    account: Account
    messages: list[EmailRecord]
    elapsed_ms: int
    diagnostics: FetchDiagnostics
    is_success: bool
    error: str | None = None
    stage: str | None = None
    saved_count: int = 0


@dataclass(frozen=True)
class BatchFetchResult:
    account_results: list[FetchAccountResult]

    @property
    def total_fetched(self) -> int:
        return sum(len(result.messages) for result in self.account_results if result.is_success)

    @property
    def total_saved(self) -> int:
        return sum(result.saved_count for result in self.account_results if result.is_success)

    @property
    def failed_count(self) -> int:
        return sum(not result.is_success for result in self.account_results)


class BatchFetchService:
    def __init__(
        self,
        fetcher: AccountMailFetcher,
        *,
        repository: MailRepository | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._repository = repository

    def fetch_accounts(
        self,
        accounts: Sequence[Account],
        options: AccountFetchOptions,
        *,
        stop_on_error: bool = False,
    ) -> BatchFetchResult:
        account_results: list[FetchAccountResult] = []
        for account in accounts:
            result = self._fetch_account(account, options)
            if result.is_success and self._repository is not None:
                result = self._save_result(result)
            account_results.append(result)
            if stop_on_error and not result.is_success:
                break
        return BatchFetchResult(account_results)

    def _fetch_account(
        self,
        account: Account,
        options: AccountFetchOptions,
    ) -> FetchAccountResult:
        diagnostics = FetchDiagnostics()
        started_at = perf_counter()
        try:
            messages = self._fetcher.fetch(account, options, diagnostics)
        except Exception as exc:
            error = str(exc)
            return FetchAccountResult(
                account=account,
                messages=[],
                elapsed_ms=_elapsed_ms(started_at),
                diagnostics=diagnostics,
                is_success=False,
                error=error,
                stage=classify_fetch_error(error),
            )
        return FetchAccountResult(
            account=account,
            messages=messages,
            elapsed_ms=_elapsed_ms(started_at),
            diagnostics=diagnostics,
            is_success=True,
        )

    def _save_result(self, result: FetchAccountResult) -> FetchAccountResult:
        repository = self._repository
        if repository is None:
            return result
        try:
            result.saved_count = repository.save_many(result.messages)
        except Exception as exc:
            error = str(exc)
            result.messages = []
            result.is_success = False
            result.error = error
            result.stage = classify_fetch_error(error)
        return result


def classify_fetch_error(message: str) -> str:
    lowered = message.lower()
    if "authenticate" in lowered or "authenticated" in lowered or "xoauth2" in lowered:
        return "auth"
    if "token" in lowered or "oauth" in lowered or "refresh" in lowered:
        return "oauth"
    if "select mailbox" in lowered or "failed to select mailbox" in lowered or "mailbox" in lowered:
        return "select"
    if (
        "fetch messages" in lowered
        or "failed to fetch" in lowered
        or lowered.startswith("failed to search message uids:")
        or lowered.startswith("search message uids failed:")
        or lowered == "search message uids timed out"
        or re.match(
            r"fetch message uids \d+(?:,\d+)* (?:failed:|timed out$)",
            lowered,
        )
        is not None
    ):
        return "fetch"
    if "connect to" in lowered or "connection" in lowered or "network is unreachable" in lowered:
        return "connect"
    if "imap" in lowered:
        return "connect"
    return "unknown"


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


__all__ = [
    "AccountFetchOptions",
    "AccountMailFetcher",
    "BatchFetchResult",
    "BatchFetchService",
    "FetchAccountResult",
    "FetchDiagnostics",
    "classify_fetch_error",
]
