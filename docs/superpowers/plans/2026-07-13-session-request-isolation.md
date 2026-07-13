# Session Request Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep account input editable during network work while preventing every stale parse, fetch, retry, error, and `finally` continuation from mutating the newest frontend session.

**Architecture:** Extend the existing DOM-free frontend logic module with a revisioned request coordinator that owns `AbortController` instances. The application resets that coordinator on account edits and guards all asynchronous state updates by the captured revision. Cancellation reduces client work; revision checks provide correctness even when an old promise ignores cancellation and resolves late.

**Tech Stack:** Native browser JavaScript, `AbortController`, Node `node:test`, Python `unittest`, temporary Playwright/Chrome regression verification.

---

## File Structure

- Modify `mail_receiver/static/app_logic.js`: add the pure revision/request coordinator.
- Modify `tests/frontend_message_selection.test.js`: add executable coordinator lifecycle tests.
- Modify `mail_receiver/static/app.js`: register parse/fetch requests and guard async continuations.
- Modify `tests/test_static_ui.py`: assert the coordinator is wired into parse, fetch, retry, input reset, and `finally` paths.

### Task 1: Add the Session Coordinator with Red-Green Tests

**Files:**
- Modify: `tests/frontend_message_selection.test.js`
- Modify: `mail_receiver/static/app_logic.js`

- [ ] **Step 1: Add failing coordinator tests**

Replace the CommonJS import at the top of `tests/frontend_message_selection.test.js` with:

```javascript
const {
  createSessionCoordinator,
  messageKey,
  findMessageByKey,
} = require('../mail_receiver/static/app_logic.js');
```

Then append these tests:

```javascript
test('reset aborts active requests and advances the session revision', () => {
  const controllers = [];
  const coordinator = createSessionCoordinator(() => {
    const controller = {
      aborted: false,
      signal: {},
      abort() {
        this.aborted = true;
      },
    };
    controllers.push(controller);
    return controller;
  });

  const first = coordinator.startRequest();
  const second = coordinator.startRequest();

  assert.equal(first.revision, 0);
  assert.equal(second.revision, 0);
  assert.equal(coordinator.currentRevision(), 0);
  assert.equal(coordinator.isCurrent(first.revision), true);

  assert.equal(coordinator.reset(), 1);
  assert.equal(controllers[0].aborted, true);
  assert.equal(controllers[1].aborted, true);
  assert.equal(coordinator.isCurrent(first.revision), false);
  assert.equal(coordinator.currentRevision(), 1);
  assert.equal(coordinator.reset(), 2);
  assert.equal(coordinator.currentRevision(), 2);
});

test('finished requests are not aborted by a later reset', () => {
  const controllers = [];
  const coordinator = createSessionCoordinator(() => {
    const controller = {
      aborted: false,
      signal: {},
      abort() {
        this.aborted = true;
      },
    };
    controllers.push(controller);
    return controller;
  });

  const finished = coordinator.startRequest();
  coordinator.finishRequest(finished.controller);
  coordinator.reset();

  assert.equal(controllers[0].aborted, false);
  const current = coordinator.startRequest();
  assert.equal(current.revision, 1);
  assert.equal(coordinator.isCurrent(current.revision), true);
});
```

- [ ] **Step 2: Run the Node tests and verify the red state**

Run:

```powershell
node --test tests/frontend_message_selection.test.js
```

Expected: 5 existing tests pass and 2 new tests fail because `createSessionCoordinator` is not exported.

- [ ] **Step 3: Implement the coordinator**

Add this function to `mail_receiver/static/app_logic.js` and export it in `api`:

```javascript
function createSessionCoordinator(controllerFactory) {
  var revision = 0;
  var controllers = new Set();
  var makeController = controllerFactory || function () {
    return new globalScope.AbortController();
  };

  function currentRevision() {
    return revision;
  }

  function isCurrent(candidateRevision) {
    return candidateRevision === revision;
  }

  function startRequest() {
    var controller = makeController();
    controllers.add(controller);
    return { controller: controller, revision: revision };
  }

  function finishRequest(controller) {
    controllers.delete(controller);
  }

  function reset() {
    revision += 1;
    controllers.forEach(function (controller) {
      controller.abort();
    });
    controllers.clear();
    return revision;
  }

  return {
    currentRevision: currentRevision,
    finishRequest: finishRequest,
    isCurrent: isCurrent,
    reset: reset,
    startRequest: startRequest,
  };
}
```

The exported object becomes:

```javascript
var api = {
  createSessionCoordinator: createSessionCoordinator,
  messageKey: messageKey,
  findMessageByKey: findMessageByKey,
};
```

- [ ] **Step 4: Run focused verification**

Run:

```powershell
node --test tests/frontend_message_selection.test.js
node --check mail_receiver/static/app_logic.js
git diff --check
```

Expected at this checkpoint: 7 Node tests pass, syntax passes, and diff-check reports nothing.

- [ ] **Step 5: Commit the coordinator**

```powershell
git add mail_receiver/static/app_logic.js tests/frontend_message_selection.test.js
git commit -m "test: add frontend session coordinator"
```

- [ ] **Step 6: Add failing reset reentrancy and abort-failure tests from quality review**

Append:

```javascript
test('reset isolates reentrant requests and continues after abort failures', () => {
  const abortAttempts = [];
  let coordinator;
  let reentrantRequest;
  const firstController = {
    abort() {
      abortAttempts.push('first');
      reentrantRequest = coordinator.startRequest();
      throw new Error('abort failed');
    },
  };
  const secondController = {
    abort() {
      abortAttempts.push('second');
    },
  };
  const reentrantController = {
    aborted: false,
    abort() {
      abortAttempts.push('reentrant');
      this.aborted = true;
    },
  };
  const controllers = [firstController, secondController, reentrantController];
  let nextController = 0;
  coordinator = createSessionCoordinator(() => controllers[nextController++]);

  coordinator.startRequest();
  coordinator.startRequest();

  let revision;
  assert.doesNotThrow(() => {
    revision = coordinator.reset();
  });
  assert.equal(revision, 1);
  assert.deepEqual(abortAttempts, ['first', 'second']);
  assert.equal(reentrantRequest.revision, 1);
  assert.strictEqual(reentrantRequest.controller, reentrantController);
  assert.equal(reentrantController.aborted, false);
});

test('reset does not abort requests started by stale abort callbacks', () => {
  const controllers = [];
  let coordinator;
  let reentrantRequest;
  coordinator = createSessionCoordinator(() => {
    const controllerIndex = controllers.length;
    const controller = {
      aborted: false,
      signal: {},
      abort() {
        this.aborted = true;
        if (controllerIndex === 0) {
          reentrantRequest = coordinator.startRequest();
        }
      },
    };
    controllers.push(controller);
    return controller;
  });

  coordinator.startRequest();
  coordinator.startRequest();

  assert.equal(coordinator.reset(), 1);
  assert.equal(controllers[0].aborted, true);
  assert.equal(controllers[1].aborted, true);
  assert.equal(reentrantRequest.revision, 1);
  assert.equal(controllers[2].aborted, false);
  assert.equal(coordinator.isCurrent(reentrantRequest.revision), true);
});
```

- [ ] **Step 7: Run the Node tests and verify the quality-review red state**

```powershell
node --test tests/frontend_message_selection.test.js
```

Expected: 7 tests pass and both new tests fail because `reset()` iterates the live controller set and lets one thrown abort stop cleanup.

- [ ] **Step 8: Make reset reentrancy-safe and cancellation best-effort**

Replace `reset()` with:

```javascript
function reset() {
  revision += 1;
  var staleControllers = Array.from(controllers);
  controllers.clear();
  staleControllers.forEach(function (controller) {
    try {
      controller.abort();
    } catch (error) {
      // Cancellation is best-effort; revision checks still isolate stale work.
    }
  });
  return revision;
}
```

- [ ] **Step 9: Verify and commit the quality-review fix**

```powershell
node --test tests/frontend_message_selection.test.js
node --check mail_receiver/static/app_logic.js
git diff --check
git add mail_receiver/static/app_logic.js tests/frontend_message_selection.test.js
git commit -m "fix: make session reset reentrancy-safe"
```

Expected: 9 Node tests pass, syntax passes, and diff-check reports nothing.

### Task 2: Guard Parse, Fetch, Retry, and Input Reset

**Files:**
- Modify: `tests/test_static_ui.py` in `StaticUiTests`
- Modify: `mail_receiver/static/app.js:1-16,438-448,1023-1053,1820-1908,1947-1963`

- [ ] **Step 1: Add a failing frontend integration contract test**

Add this test to `StaticUiTests`:

```python
def test_account_edits_cancel_and_isolate_stale_requests(self) -> None:
    js = STATIC_JS.read_text(encoding="utf-8")

    self.assertIn(
        "const { createSessionCoordinator, findMessageByKey, messageKey } = window.MailReceiverLogic;",
        js,
    )
    self.assertIn("const sessionRequests = createSessionCoordinator();", js)
    self.assertIn("function requestIsStale(error, revision)", js)
    self.assertIn("return !sessionRequests.isCurrent(revision) || error?.name === \"AbortError\";", js)

    input_start = js.index('el.accountTextInput.addEventListener("input"')
    input_end = js.index("});", input_start)
    input_block = js[input_start:input_end]
    self.assertLess(input_block.index("sessionRequests.reset();"), input_block.index("resetSessionResults();"))
    self.assertIn("setBusy(false);", input_block)

    function_bodies = {}
    for function_name in [
        "parseInput",
        "fetchOneAccount",
        "fetchMail",
        "ensureParsed",
        "retryFailedAccounts",
    ]:
        start = js.index(f"async function {function_name}")
        next_function = js.find("\nfunction ", start + 1)
        next_async = js.find("\nasync function ", start + 1)
        candidates = [index for index in [next_function, next_async] if index >= 0]
        end = min(candidates) if candidates else len(js)
        function_bodies[function_name] = js[start:end]

    parse_body = function_bodies["parseInput"]
    self.assertIn("const request = sessionRequests.startRequest();", parse_body)
    self.assertIn("signal: request.controller.signal", parse_body)
    self.assertIn("sessionRequests.isCurrent(request.revision)", parse_body)
    self.assertIn("requestIsStale(error, request.revision)", parse_body)
    self.assertIn("sessionRequests.finishRequest(request.controller)", parse_body)

    fetch_one_body = function_bodies["fetchOneAccount"]
    self.assertIn("const request = sessionRequests.startRequest();", fetch_one_body)
    self.assertIn("signal: request.controller.signal", fetch_one_body)
    self.assertIn("sessionRequests.finishRequest(request.controller)", fetch_one_body)

    ensure_body = function_bodies["ensureParsed"]
    self.assertIn("const revision = sessionRequests.currentRevision();", ensure_body)
    self.assertIn("!ok && sessionRequests.isCurrent(revision)", ensure_body)

    for function_name in ["fetchMail", "retryFailedAccounts"]:
        with self.subTest(function_name=function_name):
            body = function_bodies[function_name]
            self.assertIn("const operationRevision = sessionRequests.currentRevision();", body)
            self.assertIn("const parsed = await ensureParsed();", body)
            self.assertIn("!parsed || !sessionRequests.isCurrent(operationRevision)", body)
            self.assertIn("if (!sessionRequests.isCurrent(operationRevision))", body)
            self.assertIn("requestIsStale(error, operationRevision)", body)
            self.assertIn("if (sessionRequests.isCurrent(operationRevision))", body)
```

- [ ] **Step 2: Run the focused test and verify the red state**

Run:

```powershell
python tests/test_static_ui.py StaticUiTests.test_account_edits_cancel_and_isolate_stale_requests
```

Expected: FAIL because the coordinator is not imported or used by `app.js`.

- [ ] **Step 3: Import and instantiate the coordinator**

Change the first line of `app.js` to:

```javascript
const { createSessionCoordinator, findMessageByKey, messageKey } = window.MailReceiverLogic;
```

After `state`, add:

```javascript
const sessionRequests = createSessionCoordinator();
```

Near `api()`, add:

```javascript
function requestIsStale(error, revision) {
  return !sessionRequests.isCurrent(revision) || error?.name === "AbortError";
}
```

- [ ] **Step 4: Register and guard account parsing**

Replace `parseInput()` with:

```javascript
async function parseInput(options = {}) {
  const source = options.source || "manual";
  const accountText = el.accountTextInput.value.trim();
  if (state.accounts.length && state.parsedText === accountText) {
    return true;
  }
  const request = sessionRequests.startRequest();
  setBusy(true, source === "auto" ? "正在自动解析账号" : "正在读取账号");
  try {
    const data = await api("/api/accounts", {
      method: "POST",
      body: JSON.stringify(payloadBase()),
      signal: request.controller.signal,
    });
    if (!sessionRequests.isCurrent(request.revision) || accountText !== el.accountTextInput.value.trim()) {
      return false;
    }
    state.accountStatus.clear();
    state.parsedText = accountText;
    resetSessionResults();
    renderAccounts(data.accounts);
    addLog(source === "auto" ? `账号自动解析完成：${data.count} 个` : `账号读取完成：${data.count} 个`, "ok");
    setStatus(`已读取 ${data.count} 个账号`, "success");
    return true;
  } catch (error) {
    if (requestIsStale(error, request.revision)) {
      return false;
    }
    addLog(error.message, "fail");
    setStatus("账号读取失败", "error");
    return false;
  } finally {
    sessionRequests.finishRequest(request.controller);
    if (sessionRequests.isCurrent(request.revision)) {
      setBusy(false);
    }
  }
}
```

- [ ] **Step 5: Register each fetch request**

Replace `fetchOneAccount()` with:

```javascript
async function fetchOneAccount(account) {
  const request = sessionRequests.startRequest();
  try {
    return await api("/api/fetch", {
      method: "POST",
      body: JSON.stringify(actionPayload(account.email)),
      signal: request.controller.signal,
    });
  } finally {
    sessionRequests.finishRequest(request.controller);
  }
}
```

- [ ] **Step 6: Guard normal fetch and retry operations**

Replace `fetchMail()` with:

```javascript
async function fetchMail() {
  const operationRevision = sessionRequests.currentRevision();
  try {
    const parsed = await ensureParsed();
    if (!parsed || !sessionRequests.isCurrent(operationRevision)) {
      return;
    }
    setBusy(true, "正在拉取邮件");
    renderMailLoadingState("正在拉取邮件");
    const summary = { fetched: 0, failed: 0 };
    for (const account of accountsToFetch()) {
      state.accountStatus.set(account.email, { kind: "busy" });
      renderAccounts(state.accounts);
      setStatus(`正在拉取 ${account.email}`, "busy");
      const accountData = await fetchOneAccount(account);
      if (!sessionRequests.isCurrent(operationRevision)) {
        return;
      }
      renderFetchResult(accountData);
      summary.fetched += accountData.fetched;
      summary.failed += accountData.failed;
    }
    setStatus(`拉取完成：邮件 ${summary.fetched}，失败 ${summary.failed}`, summary.failed ? "warning" : "success");
  } catch (error) {
    if (requestIsStale(error, operationRevision)) {
      return;
    }
    addLog(error.message, "fail");
    const results = visibleMessages();
    if (allSessionMessages().length) {
      renderResults(results);
      selectInitialMessage(results);
      renderMailSummary(results, { kind: "error", label: "拉取失败", description: "已保留当前会话结果，请查看运行记录后重试。" });
    } else {
      renderMailErrorState(error.message);
    }
    setStatus("拉取失败", "error");
  } finally {
    if (sessionRequests.isCurrent(operationRevision)) {
      setBusy(false);
      syncSessionActions();
    }
  }
}
```

Replace `retryFailedAccounts()` with:

```javascript
async function retryFailedAccounts() {
  const operationRevision = sessionRequests.currentRevision();
  const failedEmails = state.failedRows.map((row) => row.email).filter(Boolean);
  if (!failedEmails.length) {
    setStatus("暂无失败账号", "ready");
    return;
  }
  try {
    const parsed = await ensureParsed();
    if (!parsed || !sessionRequests.isCurrent(operationRevision)) {
      return;
    }
    setBusy(true, "正在重试失败账号");
    const summary = { fetched: 0, failed: 0 };
    for (const email of failedEmails) {
      const account = state.accounts.find((item) => item.email === email);
      if (!account) {
        continue;
      }
      state.accountStatus.set(email, { kind: "busy" });
      renderAccounts(state.accounts);
      setStatus(`正在重试 ${email}`, "busy");
      const accountData = await fetchOneAccount(account);
      if (!sessionRequests.isCurrent(operationRevision)) {
        return;
      }
      renderFetchResult(accountData);
      summary.fetched += accountData.fetched;
      summary.failed += accountData.failed;
    }
    setStatus(`重试完成：邮件 ${summary.fetched}，失败 ${summary.failed}`, summary.failed ? "warning" : "success");
  } catch (error) {
    if (requestIsStale(error, operationRevision)) {
      return;
    }
    addLog(`重试失败：${error.message}`, "fail");
    setStatus("重试失败", "error");
  } finally {
    if (sessionRequests.isCurrent(operationRevision)) {
      setBusy(false);
      syncSessionActions();
    }
  }
}
```

- [ ] **Step 7: Distinguish stale parse from current parse failure**

Replace `ensureParsed()` with:

```javascript
async function ensureParsed() {
  clearScheduledAccountParse();
  if (state.accounts.length && state.parsedText === el.accountTextInput.value.trim()) {
    return true;
  }
  const revision = sessionRequests.currentRevision();
  const ok = await parseInput();
  if (!ok && sessionRequests.isCurrent(revision)) {
    throw new Error("账号读取失败");
  }
  return ok;
}
```

- [ ] **Step 8: Reset request ownership on every account edit**

Replace the textarea input handler with:

```javascript
el.accountTextInput.addEventListener("input", () => {
  sessionRequests.reset();
  clearScheduledAccountParse();
  state.accounts = [];
  state.accountStatus.clear();
  state.selectedAccountEmail = "";
  state.activeAccountEmail = "";
  state.fetchScope = "selected";
  state.parsedText = "";
  resetSessionResults();
  renderAccounts([]);
  renderInputQuality();
  resetAccountPrivacyWhenEmpty();
  syncAccountPrivacy();
  setBusy(false);
  setStatus("准备就绪", "ready");
  scheduleAccountParse();
});
```

- [ ] **Step 9: Run focused and complete frontend tests**

Run:

```powershell
python tests/test_static_ui.py StaticUiTests.test_account_edits_cancel_and_isolate_stale_requests
python tests/test_static_ui.py
node --test tests/frontend_message_selection.test.js
node --check mail_receiver/static/app_logic.js
node --check mail_receiver/static/app.js
git diff --check
```

Expected: focused test passes, 176 static UI tests pass, 9 Node tests pass, syntax and diff checks pass.

- [ ] **Step 10: Commit the application wiring**

```powershell
git add mail_receiver/static/app.js tests/test_static_ui.py
git commit -m "fix: isolate stale frontend requests"
```

### Task 3: Verify a Late Response That Ignores Abort

**Files:**
- No repository file changes.

- [ ] **Step 1: Run the full automated suite fresh**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py -V:Astral/CPython3.11 -m unittest discover -s tests
python -m unittest discover -s tests
node --test tests/frontend_message_selection.test.js
node --check mail_receiver/static/app_logic.js
node --check mail_receiver/static/app.js
git diff --check origin/main...HEAD
```

Expected: 248 Python tests pass on both interpreters, 9 Node tests pass, JavaScript syntax checks and diff-check pass.

- [ ] **Step 2: Run a rendered delayed-response regression**

Use a temporary Node HTTP server and Playwright/Chrome script outside the repository. Serve the real `index.html`, `app_logic.js`, `app.js`, and CSS. Mock config/accounts normally. Wrap browser `fetch()` so selected `/api/accounts` and `/api/fetch` calls return manually controlled promises that deliberately ignore the abort signal.

Exercise these exact phases. In every phase, capture the new session's status text, log text, rendered account/mail text, and `state.busy` immediately before releasing the old promise, then assert those values are unchanged by the old continuation.

```text
Phase A, stale parse success/finally:
Paste old account -> hold old parse -> replace with new account -> hold new parse
Resolve old parse while new parse is busy -> verify busy remains true and no old account/status/log appears
Resolve new parse -> verify only the new account appears and busy becomes false

Phase B, stale fetch error/catch/finally:
Parse old account -> start and hold old fetch -> replace with new account -> complete new parse
Start and hold new fetch so the new session is busy -> reject old fetch with a non-AbortError
Verify busy remains true and the new status/log/results are unchanged, with no old fetch error UI
Resolve new fetch -> verify reader and summary contain only the new account and code 333333

Phase C, stale retry success/finally:
Create an old-account failed result -> start and hold its retry -> replace with new account -> complete new parse
Start and hold new fetch -> resolve the old retry with old-account mail/code
Verify busy remains true and no old retry result/status/log/code appears
Resolve new fetch -> verify only new-account mail/code remains

Copy the current code -> verify clipboard receives 333333
Verify no page or console errors
```

Print a JSON result containing at least:

```json
{
  "oldAccountVisible": false,
  "oldCodeVisible": false,
  "newAccountVisible": true,
  "newCode": "333333",
  "copied": "333333",
  "busy": false,
  "staleParseKeptNewBusy": true,
  "staleFetchErrorKeptNewBusy": true,
  "staleRetryKeptNewBusy": true,
  "staleErrorVisible": false,
  "consoleErrors": []
}
```

Close the browser and server in `finally`. Do not write scripts, screenshots, or traces into the repository.

- [ ] **Step 3: Confirm scope and repository state**

Run:

```powershell
git diff --name-only fb21eab...HEAD
git status --short --branch
```

Use `fb21eab` (the commit immediately before this bug's design) as the scope baseline. Confirm that this fix changed only the design/plan, `app_logic.js`, `app.js`, their tests, and no P0, verification parser, Web API, IMAP, Docker, or credential-routing files. The two pre-existing untracked audit directories remain untouched.
