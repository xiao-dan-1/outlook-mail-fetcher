from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor
import threading
import unittest
from unittest.mock import patch

from mail_receiver.accounts import Account
from mail_receiver.application import (
    AccountCheckOptions,
    AccountFetchOptions,
    BatchCheckService,
    BatchFetchService,
    FetchDiagnostics,
    MailboxCheck,
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


class FakeChecker:
    def __init__(self, outcomes: dict[str, MailboxCheck | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def check(self, account: Account, options: AccountCheckOptions) -> MailboxCheck:
        self.calls.append(account.email)
        outcome = self.outcomes[account.email]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class BatchCheckServiceTests(unittest.TestCase):
    def test_preserves_order_and_isolates_account_failures(self) -> None:
        accounts = [
            _account("first@outlook.com", 1),
            _account("second@outlook.com", 2),
            _account("third@outlook.com", 3),
        ]
        checker = FakeChecker(
            {
                accounts[0].email: MailboxCheck(mailbox="INBOX", message_count=4),
                accounts[1].email: RuntimeError("authenticate with XOAUTH2 failed: NO"),
                accounts[2].email: MailboxCheck(mailbox="Archive", message_count=7),
            }
        )

        result = BatchCheckService(checker).check_accounts(
            accounts,
            AccountCheckOptions(mailbox="INBOX"),
        )

        self.assertEqual(checker.calls, [account.email for account in accounts])
        self.assertEqual(
            [row.account_email for row in result.account_results],
            [account.email for account in accounts],
        )
        self.assertEqual([row.source_line for row in result.account_results], [1, 2, 3])
        self.assertTrue(result.account_results[0].is_success)
        self.assertFalse(result.account_results[1].is_success)
        self.assertEqual(result.account_results[1].stage, "auth")
        self.assertTrue(result.account_results[2].is_success)
        self.assertEqual(result.ok_count, 2)
        self.assertEqual(result.failed_count, 1)

    def test_stop_on_error_does_not_check_later_accounts(self) -> None:
        accounts = [
            _account("first@outlook.com", 1),
            _account("second@outlook.com", 2),
            _account("third@outlook.com", 3),
        ]
        checker = FakeChecker(
            {
                accounts[0].email: MailboxCheck(mailbox="INBOX", message_count=1),
                accounts[1].email: RuntimeError("connect to server failed"),
                accounts[2].email: MailboxCheck(mailbox="INBOX", message_count=3),
            }
        )

        result = BatchCheckService(checker).check_accounts(
            accounts,
            AccountCheckOptions(mailbox="INBOX"),
            stop_on_error=True,
        )

        self.assertEqual(checker.calls, [accounts[0].email, accounts[1].email])
        self.assertEqual(len(result.account_results), 2)
        self.assertEqual(result.ok_count, 1)
        self.assertEqual(result.failed_count, 1)


class BatchFetchServiceTests(unittest.TestCase):
    def test_result_exposes_only_safe_account_identity(self) -> None:
        account = Account(
            email="safe-boundary@outlook.com",
            password="fake-password-not-for-output",
            client_id="fake-client-id-not-for-output",
            refresh_token="fake-refresh-token-not-for-output",
            source_line=9,
        )

        result = BatchFetchService(
            FakeFetcher({account.email: []}),
            max_workers=1,
        ).fetch_accounts([account], AccountFetchOptions(limit=1)).account_results[0]

        self.assertFalse(hasattr(result, "account"))
        self.assertEqual(result.account_email, account.email)
        self.assertEqual(result.source_line, 9)
        representation = repr(result)
        self.assertNotIn(account.password, representation)
        self.assertNotIn(account.client_id, representation)
        self.assertNotIn(account.refresh_token, representation)

    def test_zero_accounts_returns_empty_result_without_starting_executor(self) -> None:
        with patch("mail_receiver.application.ThreadPoolExecutor") as executor:
            result = BatchFetchService(FakeFetcher({})).fetch_accounts(
                [],
                AccountFetchOptions(limit=1),
            )

        self.assertEqual(result.account_results, [])
        self.assertEqual(result.total_fetched, 0)
        self.assertEqual(result.total_saved, 0)
        self.assertEqual(result.failed_count, 0)
        executor.assert_not_called()

    def test_all_account_failures_are_isolated_and_ordered(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]

        result = BatchFetchService(
            FakeFetcher(
                {
                    account.email: RuntimeError(f"failure-{account.source_line}")
                    for account in accounts
                }
            ),
            max_workers=2,
        ).fetch_accounts(accounts, AccountFetchOptions(limit=1))

        self.assertEqual(
            [row.account_email for row in result.account_results],
            [account.email for account in accounts],
        )
        self.assertEqual(result.failed_count, 2)
        self.assertEqual(result.total_fetched, 0)
        self.assertTrue(all(not row.is_success for row in result.account_results))

    def test_default_worker_count_is_minimum_of_four_and_account_count(self) -> None:
        observed_worker_counts: list[int] = []

        def recording_executor(*args, **kwargs):
            observed_worker_counts.append(kwargs["max_workers"])
            return RealThreadPoolExecutor(*args, **kwargs)

        with patch(
            "mail_receiver.application.ThreadPoolExecutor",
            side_effect=recording_executor,
        ):
            for account_count in (3, 5):
                accounts = [
                    _account(f"user-{index}@outlook.com", index)
                    for index in range(1, account_count + 1)
                ]
                BatchFetchService(
                    FakeFetcher({account.email: [] for account in accounts})
                ).fetch_accounts(accounts, AccountFetchOptions(limit=1))

        self.assertEqual(observed_worker_counts, [3, 4])

    def test_persistence_failure_continues_to_later_success_when_not_stopping(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        save_calls: list[str] = []

        class FirstSaveFailsRepository:
            def save_many(self, records):
                records = list(records)
                save_calls.append(records[0].account_email)
                if len(save_calls) == 1:
                    raise RuntimeError("database is locked")
                return len(records)

        result = BatchFetchService(
            FakeFetcher({account.email: [_record(account.email)] for account in accounts}),
            repository=FirstSaveFailsRepository(),
            max_workers=2,
        ).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
            stop_on_error=False,
        )

        self.assertEqual(save_calls, [account.email for account in accounts])
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.account_results[1].saved_count, 1)

    def test_sequential_stop_on_persistence_failure_preserves_fetched_messages(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        fetch_calls: list[str] = []

        class RecordingFetcher:
            def fetch(self, account, options, diagnostics):
                fetch_calls.append(account.email)
                return [_record(account.email)]

        class FailingRepository:
            def save_many(self, records):
                raise RuntimeError("database is locked")

        result = BatchFetchService(
            RecordingFetcher(),
            repository=FailingRepository(),
            max_workers=1,
        ).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
            stop_on_error=True,
        )

        self.assertEqual(fetch_calls, ["first@outlook.com"])
        self.assertEqual(len(result.account_results), 1)
        self.assertEqual(len(result.account_results[0].messages), 1)
        self.assertFalse(result.account_results[0].is_success)
        self.assertEqual(result.account_results[0].stage, "storage")
        self.assertEqual(result.total_fetched, 1)
        self.assertEqual(result.total_saved, 0)

    def test_concurrent_stop_on_persistence_failure_skips_later_saves(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        save_calls: list[str] = []

        class SuccessfulFetcher:
            def fetch(self, account, options, diagnostics):
                return [_record(account.email)]

        class FirstSaveFailsRepository:
            def save_many(self, records):
                records = list(records)
                save_calls.append(records[0].account_email)
                raise RuntimeError("database is locked")

        result = BatchFetchService(
            SuccessfulFetcher(),
            repository=FirstSaveFailsRepository(),
            max_workers=2,
        ).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
            stop_on_error=True,
        )

        self.assertEqual(save_calls, ["first@outlook.com"])
        self.assertEqual(result.total_fetched, 2)
        self.assertEqual(result.total_saved, 0)
        self.assertEqual(result.failed_count, 2)
        self.assertTrue(all(row.messages for row in result.account_results))
        self.assertTrue(all(row.stage == "storage" for row in result.account_results))

    def test_fetches_multiple_accounts_on_overlapping_worker_threads(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        barrier = threading.Barrier(2, timeout=2)
        worker_threads: set[int] = set()
        worker_lock = threading.Lock()

        class BarrierFetcher:
            def fetch(self, account, options, diagnostics):
                with worker_lock:
                    worker_threads.add(threading.get_ident())
                barrier.wait()
                return [_record(account.email)]

        result = BatchFetchService(BarrierFetcher()).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
        )

        self.assertTrue(all(row.is_success for row in result.account_results))
        self.assertEqual(len(worker_threads), 2)

    def test_concurrent_completion_keeps_input_order(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        second_completed = threading.Event()
        completion_order: list[str] = []

        class OrderedFetcher:
            def fetch(self, account, options, diagnostics):
                if account.email == "first@outlook.com":
                    self.assert_second_completed()
                completion_order.append(account.email)
                if account.email == "second@outlook.com":
                    second_completed.set()
                return [_record(account.email)]

            @staticmethod
            def assert_second_completed() -> None:
                if not second_completed.wait(timeout=2):
                    raise RuntimeError("second account did not complete concurrently")

        result = BatchFetchService(OrderedFetcher(), max_workers=2).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
        )

        self.assertEqual(completion_order, ["second@outlook.com", "first@outlook.com"])
        self.assertEqual(
            [row.account_email for row in result.account_results],
            ["first@outlook.com", "second@outlook.com"],
        )

    def test_repository_writes_remain_on_calling_thread(self) -> None:
        accounts = [_account("first@outlook.com", 1), _account("second@outlook.com", 2)]
        caller_thread = threading.get_ident()
        barrier = threading.Barrier(2, timeout=2)
        fetch_threads: set[int] = set()
        repository_threads: list[int] = []

        class ThreadFetcher:
            def fetch(self, account, options, diagnostics):
                fetch_threads.add(threading.get_ident())
                barrier.wait()
                return [_record(account.email)]

        class ThreadRepository(FakeRepository):
            def save_many(self, records):
                repository_threads.append(threading.get_ident())
                return super().save_many(records)

        BatchFetchService(
            ThreadFetcher(),
            repository=ThreadRepository(),
            max_workers=2,
        ).fetch_accounts(accounts, AccountFetchOptions(limit=1))

        self.assertNotIn(caller_thread, fetch_threads)
        self.assertEqual(repository_threads, [caller_thread, caller_thread])

    def test_stop_on_error_does_not_schedule_accounts_beyond_active_workers(self) -> None:
        accounts = [
            _account("first@outlook.com", 1),
            _account("second@outlook.com", 2),
            _account("third@outlook.com", 3),
            _account("fourth@outlook.com", 4),
        ]
        failure_started = threading.Event()
        calls: list[str] = []
        calls_lock = threading.Lock()

        class StoppingFetcher:
            def fetch(self, account, options, diagnostics):
                with calls_lock:
                    calls.append(account.email)
                if account.email == "first@outlook.com":
                    if not failure_started.wait(timeout=2):
                        raise RuntimeError("failure worker did not start")
                    return [_record(account.email)]
                if account.email == "second@outlook.com":
                    failure_started.set()
                    raise RuntimeError("imap failed")
                return [_record(account.email)]

        result = BatchFetchService(StoppingFetcher(), max_workers=2).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
            stop_on_error=True,
        )

        self.assertEqual(set(calls), {"first@outlook.com", "second@outlook.com"})
        self.assertEqual(len(result.account_results), 2)
        self.assertEqual(result.failed_count, 1)

    def test_rejects_worker_counts_outside_safe_range(self) -> None:
        fetcher = FakeFetcher({})

        for worker_count in (0, 17):
            with self.subTest(worker_count=worker_count), self.assertRaisesRegex(
                ValueError,
                "max_workers must be between 1 and 16",
            ):
                BatchFetchService(fetcher, max_workers=worker_count)

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
            [row.account_email for row in result.account_results],
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

        result = BatchFetchService(fetcher, max_workers=1).fetch_accounts(
            accounts,
            AccountFetchOptions(limit=1),
            stop_on_error=True,
        )

        self.assertEqual(calls, ["first@outlook.com", "second@outlook.com"])
        self.assertEqual(len(result.account_results), 2)


if __name__ == "__main__":
    unittest.main()
