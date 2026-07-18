import unittest

from mail_receiver.accounts import Account
from mail_receiver.application import (
    AccountFetchOptions,
    BatchFetchService,
    FetchDiagnostics,
)
from mail_receiver.message_parsing import EmailRecord


def _account(email: str, line: int) -> Account:
    return Account(
        email=email,
        password="password",
        client_id="client-id",
        refresh_token="refresh-token",
        source_line=line,
    )


def _record(email: str, uid: str = "1") -> EmailRecord:
    return EmailRecord(
        account_email=email,
        mailbox="INBOX",
        uid=uid,
        uidvalidity="9",
        message_id=f"<{uid}@example.com>",
        subject=f"Message {uid}",
        sender="sender@example.com",
        recipients=email,
        sent_at="2026-07-18T00:00:00+00:00",
        body_preview="Body",
        raw_message=b"Subject: Message\r\n\r\nBody",
    )


class FakeFetcher:
    def __init__(self, outcomes: dict[str, list[EmailRecord] | Exception]) -> None:
        self.outcomes = outcomes
        self.diagnostics: list[FetchDiagnostics] = []

    def fetch(
        self,
        account: Account,
        options: AccountFetchOptions,
        diagnostics: FetchDiagnostics,
    ) -> list[EmailRecord]:
        self.diagnostics.append(diagnostics)
        outcome = self.outcomes[account.email]
        if isinstance(outcome, Exception):
            raise outcome
        diagnostics.message_count = len(outcome)
        diagnostics.raw_bytes = sum(len(record.raw_message) for record in outcome)
        return list(outcome)


class FakeRepository:
    def __init__(self) -> None:
        self.saved_batches: list[list[EmailRecord]] = []

    def save_many(self, records: list[EmailRecord]) -> int:
        batch = list(records)
        self.saved_batches.append(batch)
        return len(batch)


class BatchFetchServiceTests(unittest.TestCase):
    def test_isolates_failures_and_preserves_account_order(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        fetcher = FakeFetcher(
            {
                "first@outlook.com": [_record("first@outlook.com")],
                "second@outlook.com": RuntimeError("authenticate with XOAUTH2 failed: NO"),
            }
        )

        result = BatchFetchService(fetcher).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
        )

        self.assertEqual(
            [row.account.email for row in result.account_results],
            ["first@outlook.com", "second@outlook.com"],
        )
        self.assertTrue(result.account_results[0].is_success)
        self.assertEqual(result.account_results[0].messages[0].uid, "1")
        self.assertFalse(result.account_results[1].is_success)
        self.assertEqual(result.account_results[1].stage, "auth")
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.total_fetched, 1)

    def test_uses_independent_diagnostics_for_every_account(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        fetcher = FakeFetcher(
            {
                account.email: [_record(account.email, str(index))]
                for index, account in enumerate(accounts, start=1)
            }
        )

        BatchFetchService(fetcher).fetch_accounts(accounts, AccountFetchOptions(limit=1))

        self.assertEqual(len(fetcher.diagnostics), 2)
        self.assertIsNot(fetcher.diagnostics[0], fetcher.diagnostics[1])

    def test_persists_successful_results_through_repository_port(self) -> None:
        account = _account("user@outlook.com", 1)
        repository = FakeRepository()

        result = BatchFetchService(
            FakeFetcher({account.email: [_record(account.email)]}),
            repository=repository,
        ).fetch_accounts([account], AccountFetchOptions(limit=1))

        self.assertEqual(len(repository.saved_batches), 1)
        self.assertEqual(repository.saved_batches[0][0].account_email, account.email)
        self.assertEqual(result.account_results[0].saved_count, 1)

    def test_stop_on_error_does_not_start_later_accounts_in_sequential_service(self) -> None:
        accounts = [
            _account("first@outlook.com", 1),
            _account("second@outlook.com", 2),
            _account("third@outlook.com", 3),
        ]
        calls: list[str] = []

        class RecordingFetcher(FakeFetcher):
            def fetch(self, account, options, diagnostics):
                calls.append(account.email)
                return super().fetch(account, options, diagnostics)

        fetcher = RecordingFetcher(
            {
                "first@outlook.com": [_record("first@outlook.com")],
                "second@outlook.com": RuntimeError("imap failed"),
                "third@outlook.com": [_record("third@outlook.com")],
            }
        )

        result = BatchFetchService(fetcher).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
            stop_on_error=True,
        )

        self.assertEqual(calls, ["first@outlook.com", "second@outlook.com"])
        self.assertEqual(len(result.account_results), 2)


if __name__ == "__main__":
    unittest.main()
