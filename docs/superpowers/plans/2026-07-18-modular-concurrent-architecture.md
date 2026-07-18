# Modular Concurrent Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Outlook Mail Fetcher into cohesive, loosely coupled components with consistent domain naming, lightweight parsing-rule extension points, and bounded concurrent mailbox fetching while preserving the frontend and Docker startup behavior.

**Architecture:** Extract RFC822/MIME parsing from the IMAP transport, introduce protocol-based application services and repository boundaries, then make the shared batch service concurrent with a bounded `ThreadPoolExecutor`. Keep frontend behavior unchanged while moving verification-rule dispatch behind a tested priority registry.

**Tech Stack:** Python 3.11 standard library (`dataclasses`, `typing.Protocol`, `concurrent.futures`, `unittest`), Node.js built-in `node:test`, SQLite, native HTML/CSS/JavaScript, Docker Compose.

---

## File map

- Create `mail_receiver/message_parsing.py`: email data model, parser protocol, and default RFC822/MIME parser.
- Create `mail_receiver/application.py`: fetch options/results, fetcher and repository protocols, sequential then concurrent batch orchestration.
- Create `mail_receiver/mail_fetching.py`: Outlook and mock implementations of the account fetcher protocol.
- Create `mail_receiver/repositories.py`: persistence protocol used by the application service.
- Modify `mail_receiver/imap_client.py`: retain IMAP protocol behavior and delegate raw message parsing.
- Modify `mail_receiver/storage.py`: expose the explicit `SQLiteMailRepository` implementation while retaining `MailStore` compatibility.
- Modify `mail_receiver/web.py`: adapt HTTP payloads and application results without owning the account loop.
- Modify `mail_receiver/cli.py`: adapt CLI arguments and output without owning the account loop.
- Modify `mail_receiver/static/app_logic.js`: add the generic verification-rule registry.
- Modify `mail_receiver/static/app.js`: register provider rules and call the registry without changing rendering.
- Create `tests/test_message_parsing.py`: isolated parser tests.
- Create `tests/test_application.py`: service, repository, failure, ordering, cancellation, and concurrency tests.
- Create `tests/test_architecture.py`: dependency-direction and naming safeguards.
- Modify existing Python and Node tests only where import or patch locations intentionally change.

## Goal 1: High cohesion — isolate message parsing

### Task 1: Extract the message model and parser

**Files:**
- Create: `mail_receiver/message_parsing.py`
- Modify: `mail_receiver/imap_client.py`
- Modify: `mail_receiver/storage.py`
- Create: `tests/test_message_parsing.py`
- Modify: `tests/test_imap_client.py`

- [ ] **Step 1: Write parser tests against the new module**

Create tests that import `DefaultMessageParser`, `EmailRecord`, `extract_body_text`, and `email_record_from_message` from `mail_receiver.message_parsing`. Include plain text, HTML fallback, attachment exclusion, unknown charset, and date normalization. The key interface test is:

```python
def test_default_message_parser_builds_email_record() -> None:
    parser = DefaultMessageParser()
    raw = b"Subject: Hello\r\nFrom: sender@example.com\r\n\r\nBody"

    record = parser.parse(
        raw,
        MessageContext(
            account_email="user@outlook.com",
            mailbox="INBOX",
            uid="7",
            uidvalidity="9",
            raw_message_complete=True,
        ),
    )

    assert record.subject == "Hello"
    assert record.body_preview == "Body"
    assert record.uid == "7"
```

- [ ] **Step 2: Run the new tests and verify the missing module failure**

Run:

```powershell
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_message_parsing.py
```

Expected: FAIL because `mail_receiver.message_parsing` does not exist.

- [ ] **Step 3: Create the focused parser module**

Define the public boundary:

```python
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
```

Move `EmailRecord`, `email_record_from_message`, `_decode_text_payload`, `_iter_inline_leaf_parts`, `extract_body_text`, `_ReadableHtmlParser`, `_html_to_text`, `_normalize_readable_text`, and `_parse_message_date` into this module without changing parsing behavior.

- [ ] **Step 4: Delegate IMAP payload parsing through `MessageParser`**

Add `message_parser: MessageParser | None = None` to the existing `fetch_messages` keyword parameters, initialize `parser = message_parser or DefaultMessageParser()` before payload conversion, and pass it to `_records_from_message_payloads`. Replace that conversion helper with this focused implementation:

```python
def _records_from_message_payloads(
    account: Account,
    mailbox: str,
    uidvalidity: str,
    payloads: Iterable[tuple[str, bytes, bool]],
    *,
    message_parser: MessageParser,
) -> list[EmailRecord]:
    records: list[EmailRecord] = []
    for uid, raw_message, raw_message_complete in payloads:
        records.append(
            message_parser.parse(
                raw_message,
                MessageContext(
                    account_email=account.email,
                    mailbox=mailbox,
                    uid=uid,
                    uidvalidity=uidvalidity,
                    raw_message_complete=raw_message_complete,
                ),
            )
        )
    return records
```

For every payload call `message_parser.parse` with a `MessageContext` constructed from the current account email, mailbox, UID, UIDVALIDITY and completeness flag. Re-export `EmailRecord`, `email_record_from_message`, and `extract_body_text` from `imap_client.py` so existing consumers remain compatible during the migration.

- [ ] **Step 5: Run parser and IMAP tests**

Run:

```powershell
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_message_parsing.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_imap_client.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_storage.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Goal 1**

```powershell
git add mail_receiver/message_parsing.py mail_receiver/imap_client.py mail_receiver/storage.py tests/test_message_parsing.py tests/test_imap_client.py
git commit -m "refactor: isolate message parsing"
```

## Goal 2: Low coupling — shared application service and ports

### Task 2: Introduce application-facing protocols and results

**Files:**
- Create: `mail_receiver/application.py`
- Create: `mail_receiver/mail_fetching.py`
- Create: `mail_receiver/repositories.py`
- Create: `tests/test_application.py`
- Create: `tests/test_architecture.py`

- [ ] **Step 1: Write failing application-service tests**

Use fakes that implement the protocols structurally:

```python
class FakeFetcher:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes

    def fetch(
        self,
        account: Account,
        options: AccountFetchOptions,
        diagnostics: FetchDiagnostics,
    ) -> list[EmailRecord]:
        outcome = self.outcomes[account.email]
        if isinstance(outcome, Exception):
            raise outcome
        return list(outcome)


def test_batch_service_isolates_account_failures_and_preserves_order() -> None:
    service = BatchFetchService(FakeFetcher({
        "first@outlook.com": [_record("first@outlook.com")],
        "second@outlook.com": RuntimeError("imap failed"),
    }))
    result = service.fetch_accounts(accounts, options)
    assert [row.account.email for row in result.account_results] == [
        "first@outlook.com",
        "second@outlook.com",
    ]
    assert result.account_results[0].is_success is True
    assert result.account_results[1].error == "imap failed"
```

Also test optional repository persistence happens outside the fetcher and records `saved_count`.

- [ ] **Step 2: Verify the application tests fail**

Run:

```powershell
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_application.py
```

Expected: FAIL because the application module and types do not exist.

- [ ] **Step 3: Implement the protocol boundaries and sequential service**

Define the persistence boundary in `repositories.py`:

```python
class MailRepository(Protocol):
    def save_many(self, records: Iterable[EmailRecord]) -> int:
        raise NotImplementedError
```

Define these public types in `application.py`; keep this module free of imports from `imap_client.py`, `web.py`, `cli.py`, and `storage.py`:

```python
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
```

Implement `BatchFetchService.fetch_accounts` sequentially for now. It must construct independent diagnostics per account, classify exceptions, honor current `stop_on_error` behavior, and perform repository writes only after a successful fetch. Move `FetchDiagnostics` out of `imap_client.py`; import it there from `application.py` and keep a compatibility re-export.

- [ ] **Step 4: Implement concrete fetcher adapters**

In `mail_fetching.py`, inject the existing functions so Web and CLI tests can still patch their local aliases:

```python
class OutlookAccountMailFetcher:
    def __init__(self, fetch_function: Callable = fetch_messages) -> None:
        self._fetch_function = fetch_function

    def fetch(self, account, options, diagnostics):
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
```

Implement `MockAccountMailFetcher` with the same protocol and populate fetch/parse diagnostics consistently.

- [ ] **Step 5: Add dependency-direction tests**

Parse imports with `ast` and assert `mail_receiver.application` does not import `argparse`, `http.server`, `imaplib`, `sqlite3`, `mail_receiver.web`, or `mail_receiver.cli`. Assert Web and CLI import `BatchFetchService`.

- [ ] **Step 6: Refactor Web to adapt the shared service**

Replace the loop in `fetch_data` with:

```python
fetcher = (
    MockAccountMailFetcher(fetch_function=mock_messages)
    if use_mock
    else OutlookAccountMailFetcher(fetch_function=fetch_messages)
)
service = BatchFetchService(fetcher)
batch = service.fetch_accounts(accounts, options, stop_on_error=stop_on_error)
```

Map `FetchAccountResult` back to the existing `rows` and `messages` JSON fields. Keep the route and response shape unchanged.

- [ ] **Step 7: Refactor CLI to adapt the shared service**

Construct `SQLiteMailRepository`, choose the concrete fetcher, run `BatchFetchService`, then print results using the existing visible-text escaping. Preserve existing exit codes, raw output, search, and show behavior.

- [ ] **Step 8: Run application, Web, CLI, architecture, storage, and IMAP tests**

Run:

```powershell
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_application.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_architecture.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_web.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_cli.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_storage.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_imap_client.py
```

Expected: all tests pass.

- [ ] **Step 9: Commit Goal 2**

```powershell
git add mail_receiver/application.py mail_receiver/mail_fetching.py mail_receiver/repositories.py mail_receiver/web.py mail_receiver/cli.py tests/test_application.py tests/test_architecture.py tests/test_web.py tests/test_cli.py
git commit -m "refactor: centralize batch mail fetching"
```

## Goal 3: Elegant naming — explicit implementations and vocabulary

### Task 3: Normalize public domain names

**Files:**
- Modify: `mail_receiver/storage.py`
- Modify: `mail_receiver/cli.py`
- Modify: `mail_receiver/application.py`
- Modify: `mail_receiver/__init__.py`
- Modify: `tests/test_storage.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_architecture.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing naming assertions**

Assert that `SQLiteMailRepository` is the concrete public implementation, that the compatibility alias remains valid, and that new architecture modules do not define prohibited vague public names:

```python
def test_sqlite_repository_has_explicit_name() -> None:
    assert SQLiteMailRepository is MailStore


def test_architecture_modules_avoid_vague_public_type_names() -> None:
    prohibited = {"Manager", "Helper", "Utils", "Processor", "Data"}
    assert prohibited.isdisjoint(public_type_names("mail_receiver.application"))
```

- [ ] **Step 2: Verify naming tests fail**

Run the architecture and storage tests. Expected: FAIL because `SQLiteMailRepository` is not defined.

- [ ] **Step 3: Rename the concrete repository with compatibility**

Rename the existing concrete class declaration from `MailStore` to `SQLiteMailRepository`, without changing its method bodies, and keep the old import working:

```python
MailStore = SQLiteMailRepository
```

Update production imports to use `SQLiteMailRepository`. Keep tests for the alias so downstream scripts are not broken unnecessarily.

- [ ] **Step 4: Publish the intentional vocabulary**

Add relevant names to module `__all__` declarations and correct the README default database name to `mail_store.sqlite3`. Ensure methods consistently use `fetch_accounts`, `save_many`, `parse`, `is_success`, and `include_raw`.

- [ ] **Step 5: Run naming and affected behavior tests**

Run:

```powershell
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_architecture.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_storage.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_cli.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_project_metadata.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Goal 3**

```powershell
git add mail_receiver/storage.py mail_receiver/cli.py mail_receiver/application.py mail_receiver/__init__.py tests/test_storage.py tests/test_cli.py tests/test_architecture.py README.md
git commit -m "refactor: clarify architecture naming"
```

## Goal 4: Lightweight plugin design — parsing and verification rules

### Task 4: Add a priority verification-rule registry

**Files:**
- Modify: `mail_receiver/static/app_logic.js`
- Modify: `mail_receiver/static/app.js`
- Modify: `tests/frontend_verification_runtime.test.js`
- Modify: `tests/test_static_ui.py`
- Modify: `tests/test_frontend_runtime.py`

- [ ] **Step 1: Write failing registry tests**

Test registration, priority, stable order, result annotation, no-match fallback, and exception isolation directly against `app_logic.js`:

```javascript
test('verification registry uses priority and annotates the winning rule', () => {
  const registry = logic.createVerificationRuleRegistry();
  registry.register({ id: 'low', priority: 1, match: () => ({ code: '111111' }) });
  registry.register({ id: 'high', priority: 10, match: () => ({ code: '222222' }) });

  assert.deepEqual(registry.find({}), {
    code: '222222',
    rule_id: 'high',
  });
});

test('verification registry isolates a broken rule', () => {
  const registry = logic.createVerificationRuleRegistry([
    { id: 'broken', priority: 10, match: () => { throw new Error('broken'); } },
    { id: 'fallback', priority: 0, match: () => ({ code: '333333' }) },
  ]);
  assert.equal(registry.find({}).rule_id, 'fallback');
});
```

- [ ] **Step 2: Verify Node tests fail**

Run:

```powershell
node --test tests/frontend_verification_runtime.test.js
```

Expected: FAIL because `createVerificationRuleRegistry` is not exported.

- [ ] **Step 3: Implement the generic registry in `app_logic.js`**

```javascript
function createVerificationRuleRegistry(initialRules) {
  var entries = [];
  var nextOrder = 0;

  function register(rule) {
    if (!rule || !rule.id || typeof rule.match !== 'function') {
      throw new TypeError('verification rule requires id and match');
    }
    entries.push({ rule: rule, order: nextOrder++ });
    entries.sort(function (left, right) {
      return (Number(right.rule.priority) || 0) - (Number(left.rule.priority) || 0)
        || left.order - right.order;
    });
  }

  function find(context) {
    for (var entry of entries) {
      try {
        var result = entry.rule.match(context);
        if (result) {
          return Object.assign({}, result, { rule_id: entry.rule.id });
        }
      } catch (error) {
        continue;
      }
    }
    return null;
  }

  (initialRules || []).forEach(register);
  return { find: find, register: register };
}
```

Export it through `MailReceiverLogic` and CommonJS.

- [ ] **Step 4: Register existing provider rules in `app.js`**

Destructure the registry factory, create one registry, and register each provider with explicit priority. `extractVerificationCode` builds the search context once and calls `registry.find`. Preserve all current result fields and add `rule_id` to matches.

```javascript
const verificationRuleRegistry = createVerificationRuleRegistry();
VERIFICATION_PROVIDERS.forEach((provider, index) => {
  verificationRuleRegistry.register({
    id: `provider:${provider.id}`,
    priority: provider.priority ?? (VERIFICATION_PROVIDERS.length - index),
    match: ({ text, identityText }) => providerVerificationCandidate(provider, text, identityText),
  });
});
```

- [ ] **Step 5: Verify existing and new frontend behavior**

Run:

```powershell
node --test tests/frontend_verification_runtime.test.js
node --test tests/*.test.js
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_frontend_runtime.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_static_ui.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_message_parsing.py
```

Expected: all tests pass and frontend markup/CSS snapshots remain unchanged.

- [ ] **Step 6: Commit Goal 4**

```powershell
git add mail_receiver/static/app_logic.js mail_receiver/static/app.js tests/frontend_verification_runtime.test.js tests/test_static_ui.py tests/test_frontend_runtime.py
git commit -m "refactor: add verification rule registry"
```

## Goal 5: Concurrent account fetching

### Task 5: Add bounded account-level concurrency

**Files:**
- Modify: `mail_receiver/application.py`
- Modify: `mail_receiver/web.py`
- Modify: `mail_receiver/cli.py`
- Modify: `tests/test_application.py`
- Modify: `tests/test_web.py`
- Modify: `tests/test_cli.py`
- Modify: `docs/api.md`

- [ ] **Step 1: Write deterministic concurrency tests**

Use `threading.Barrier` to prove overlap without relying on elapsed-time thresholds:

```python
def test_batch_service_fetches_accounts_concurrently() -> None:
    barrier = threading.Barrier(2, timeout=2)

    class BarrierFetcher:
        def fetch(self, account, options, diagnostics):
            barrier.wait()
            return [_record(account.email)]

    result = BatchFetchService(BarrierFetcher(), max_workers=2).fetch_accounts(
        _accounts(2),
        AccountFetchOptions(limit=1),
    )
    assert all(row.is_success for row in result.account_results)
```

Add tests for default worker calculation, maximum worker validation, input-order preservation when completion order differs, partial failure, `max_workers=1`, and cancellation of pending work under `stop_on_error=True`.

- [ ] **Step 2: Verify concurrency tests fail**

Run the application tests. Expected: the barrier test fails or times out because the service is sequential.

- [ ] **Step 3: Implement bounded `ThreadPoolExecutor` scheduling**

Add `MAX_ACCOUNT_FETCH_WORKERS = 16`. Resolve workers as `min(4, account_count)` when unspecified and reject values outside `1..16`.

Submit indexed account tasks, collect with `as_completed`, cancel not-yet-started futures after the first observed failure when `stop_on_error` is true, wait for already-running tasks, then sort successful/failed completed results by original index. Perform repository writes afterward on the calling thread in input order.

```python
with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="mail-account") as executor:
    future_indexes = {
        executor.submit(self._fetch_account, account, options): index
        for index, account in enumerate(accounts)
    }
    for future in as_completed(future_indexes):
        index = future_indexes[future]
        if future.cancelled():
            continue
        result = future.result()
        completed[index] = result
        if stop_on_error and not result.is_success:
            for pending in future_indexes:
                if pending is not future:
                    pending.cancel()
```

- [ ] **Step 4: Expose worker configuration without changing the UI**

- Web accepts optional integer `max_workers` in `/api/fetch`; the existing frontend omits it and receives the concurrent default.
- CLI `fetch` accepts `--max-workers` with validation.
- Docker command and ports remain unchanged.
- API documentation describes the optional field and `1..16` range.

- [ ] **Step 5: Run concurrency and adapter tests**

Run:

```powershell
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_application.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_web.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_cli.py
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests -p test_architecture.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Goal 5**

```powershell
git add mail_receiver/application.py mail_receiver/web.py mail_receiver/cli.py tests/test_application.py tests/test_web.py tests/test_cli.py docs/api.md
git commit -m "feat: fetch mail accounts concurrently"
```

## Final regression

### Task 6: Automated and runtime regression

**Files:**
- Modify only if a regression reveals a defect; any fix requires its own test and commit before repeating the full regression.

- [ ] **Step 1: Run complete CI-aligned test suites**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py '-V:Astral\CPython3.11.15' -m unittest discover -s tests
node --test tests/*.test.js
```

Expected: 0 failures and 0 errors.

- [ ] **Step 2: Verify the Git history and worktree**

```powershell
git log --oneline -8
git status --short
git diff HEAD~5..HEAD --check
```

Expected: one implementation commit for each goal, no accidental credential/database/audit-artifact additions, and only the two pre-existing untracked audit directories outside the feature changes.

- [ ] **Step 3: Build and start the local Docker image**

```powershell
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
docker compose ps
curl.exe --fail http://127.0.0.1:8765/api/config
```

Expected: container is healthy and `/api/config` returns version/default JSON.

- [ ] **Step 4: Exercise multi-account Web mock flow**

POST two syntactically valid mock accounts to `/api/accounts` and `/api/fetch` with `mock=true`, `limit=2`, and `max_workers=2`. Verify two ordered account rows, four messages, zero failures, and no credentials in the response beyond the documented masked account endpoint.

- [ ] **Step 5: Exercise CLI mock persistence flow**

Create the temporary account and database files under the operating-system temporary directory, then run `inspect-accounts`, `fetch --mock --max-workers 2`, `search`, and `show`. Verify inserts, search results, and readable output, then remove only those temporary files.

- [ ] **Step 6: Run authorized real Outlook regression**

Use the explicitly authorized account path supplied through `$env:OUTLOOK_TEST_ACCOUNTS`. Require that it contains at least two accounts. Use `--limit 1`, a temporary SQLite database, and normal non-debug logging:

```powershell
$regressionDb = Join-Path $env:TEMP 'outlook-mail-fetcher-regression.sqlite3'
py '-V:Astral\CPython3.11.15' -m mail_receiver.cli fetch $env:OUTLOOK_TEST_ACCOUNTS --limit 1 --max-workers 2 --db $regressionDb
```

Verify both accounts complete OAuth refresh, IMAP authentication, mailbox selection, and limited fetch without displaying credentials or raw message contents. Do not commit the account file or database. If credentials are unavailable, leave the overall goal incomplete and report that exact external blocker.

- [ ] **Step 7: Stop the regression container and perform final audit**

```powershell
docker compose -f docker-compose.yml -f docker-compose.build.yml down
git status --short --branch
```

Audit every design acceptance criterion against code, tests, runtime output, and Git history before marking the goal complete.
