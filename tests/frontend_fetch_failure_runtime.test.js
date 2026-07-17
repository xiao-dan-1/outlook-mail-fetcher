const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const logic = require('../mail_receiver/static/app_logic.js');

const APP_PATH = path.join(__dirname, '..', 'mail_receiver', 'static', 'app.js');
const APP_SOURCE = fs.readFileSync(APP_PATH, 'utf8');
const BOOTSTRAP_MARKER = '\ninitTheme();';
const BOOTSTRAP_INDEX = APP_SOURCE.lastIndexOf(BOOTSTRAP_MARKER);
assert.notEqual(BOOTSTRAP_INDEX, -1, 'app bootstrap marker not found');
const APP_RUNTIME_SOURCE = APP_SOURCE.slice(0, BOOTSTRAP_INDEX);

function fakeElement(id = '') {
  return {
    id,
    value: '',
    checked: false,
    hidden: false,
    disabled: false,
    title: '',
    textContent: '',
    innerHTML: '',
    dataset: {},
    children: [],
    classList: {
      add() {},
      remove() {},
      toggle() {},
      contains() { return false; },
    },
    addEventListener() {},
    removeEventListener() {},
    setAttribute() {},
    removeAttribute() {},
    hasAttribute() { return false; },
    append() {},
    appendChild() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    focus() {},
    scrollIntoView() {},
  };
}

function createRuntime({ emails = ['first@outlook.com'], failedRows = [] } = {}) {
  const elements = new Map();
  const elementFor = (id) => {
    if (!elements.has(id)) {
      elements.set(id, fakeElement(id));
    }
    return elements.get(id);
  };
  const document = {
    documentElement: fakeElement('documentElement'),
    body: fakeElement('body'),
    getElementById: elementFor,
    querySelector(selector) { return elementFor(selector); },
    querySelectorAll() { return []; },
    createElement(tagName) { return fakeElement(tagName); },
    createTextNode(text) { return { textContent: text }; },
    execCommand() { return true; },
  };
  const context = {
    AbortController,
    clearTimeout,
    console,
    document,
    fetch: async () => {
      throw new Error('fetch mock not configured');
    },
    localStorage: {
      getItem() { return null; },
      setItem() {},
    },
    navigator: {},
    setTimeout,
    window: {
      DOMParser: null,
      MailReceiverLogic: logic,
    },
  };
  context.globalThis = context;
  vm.createContext(context);

  const bridge = `
globalThis.__mailRuntimeTest = {
  state,
  sessionRequests,
  mailOperationGate,
  fetchMail,
  retryFailedAccounts,
  installHooks(hooks = {}) {
    renderAccounts = hooks.renderAccounts || function () {};
    renderMailLoadingState = hooks.renderMailLoadingState || function () {};
    renderFetchResult = hooks.renderFetchResult || function () {};
    renderMailErrorState = hooks.renderMailErrorState || function () {};
    renderResults = hooks.renderResults || function () {};
    selectInitialMessage = hooks.selectInitialMessage || function () {};
    renderMailSummary = hooks.renderMailSummary || function () {};
    syncSessionActions = hooks.syncSessionActions || function () {};
    addLog = hooks.addLog || function () {};
    setStatus = hooks.setStatus || function () {};
    setBusy = hooks.setBusy || function (busy) { state.busy = busy; };
  },
};
`;
  vm.runInContext(`${APP_RUNTIME_SOURCE}\n${bridge}`, context, {
    filename: APP_PATH,
  });

  const runtime = context.__mailRuntimeTest;
  const accountText = emails
    .map((email) => `${email}----password----client-id----refresh-token`)
    .join('\n');
  elementFor('accountTextInput').value = accountText;
  elementFor('mailboxInput').value = 'INBOX';
  elementFor('limitInput').value = '20';
  elementFor('rawFetchToggle').checked = false;
  runtime.state.accounts = emails.map((email) => ({ email }));
  runtime.state.parsedText = accountText;
  runtime.state.fetchScope = 'all';
  runtime.state.failedRows = failedRows.slice();
  runtime.state.accountStatus.clear();
  runtime.state.messagesByAccount.clear();

  const busyTransitions = [];
  const accountStatusSnapshots = [];
  let renderAccountCalls = 0;
  runtime.installHooks({
    renderAccounts() {
      renderAccountCalls += 1;
      accountStatusSnapshots.push(new Map(
        runtime.state.accounts.map((account) => [
          account.email,
          runtime.state.accountStatus.get(account.email)?.kind,
        ]),
      ));
    },
    setBusy(busy) {
      runtime.state.busy = busy;
      busyTransitions.push(busy);
    },
  });

  return {
    accountStatusKinds(email) {
      return accountStatusSnapshots
        .map((snapshot) => snapshot.get(email))
        .filter(Boolean);
    },
    busyTransitions,
    context,
    renderAccountCalls: () => renderAccountCalls,
    runtime,
  };
}

function successResponse(data = {}) {
  return {
    ok: true,
    async json() {
      return {
        fetched: 1,
        failed: 0,
        rows: [],
        messages: [],
        ...data,
      };
    },
  };
}

async function waitFor(predicate, message = 'condition was not reached') {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.fail(message);
}

async function settlesWithin(promise, timeoutMs = 50) {
  let timeout;
  const settled = await Promise.race([
    promise.then(() => true),
    new Promise((resolve) => {
      timeout = setTimeout(() => resolve(false), timeoutMs);
    }),
  ]);
  clearTimeout(timeout);
  return settled;
}

test('fetchMail turns the pending account from busy into a request failure', async () => {
  const harness = createRuntime();
  harness.context.fetch = async () => {
    throw new TypeError('network connection lost');
  };

  await harness.runtime.fetchMail();

  const status = harness.runtime.state.accountStatus.get('first@outlook.com');
  assert.equal(status.kind, 'fail');
  assert.equal(status.stage, 'request');
  assert.equal(status.error, 'network connection lost');
  assert.deepEqual(
    Array.from(harness.runtime.state.failedRows, (row) => ({
      email: row.email,
      stage: row.stage,
      error: row.error,
    })),
    [{
      email: 'first@outlook.com',
      stage: 'request',
      error: 'network connection lost',
    }],
  );
  assert.equal(harness.renderAccountCalls(), 2);
  assert.deepEqual(
    harness.accountStatusKinds('first@outlook.com'),
    ['busy', 'fail'],
  );
  assert.equal(harness.runtime.state.busy, false);
});

test('retryFailedAccounts updates the rejected email and preserves other failed rows', async () => {
  const retriedFailure = {
    email: 'retry@outlook.com',
    ok: false,
    stage: 'fetch',
    error: 'old failure',
  };
  const otherFailure = {
    email: 'other@outlook.com',
    ok: false,
    stage: 'oauth',
    error: 'keep this failure',
  };
  const harness = createRuntime({
    emails: ['retry@outlook.com', 'other@outlook.com'],
    failedRows: [retriedFailure, otherFailure],
  });
  harness.context.fetch = async () => {
    throw new Error('HTTP 503 unavailable');
  };

  await harness.runtime.retryFailedAccounts();

  const status = harness.runtime.state.accountStatus.get('retry@outlook.com');
  assert.equal(status.kind, 'fail');
  assert.equal(status.stage, 'request');
  const retryRow = harness.runtime.state.failedRows.find(
    (row) => row.email === 'retry@outlook.com',
  );
  const preservedRow = harness.runtime.state.failedRows.find(
    (row) => row.email === 'other@outlook.com',
  );
  assert.equal(retryRow.stage, 'request');
  assert.equal(retryRow.error, 'HTTP 503 unavailable');
  assert.strictEqual(preservedRow, otherFailure);
  assert.equal(harness.runtime.state.failedRows.length, 2);
  assert.deepEqual(
    harness.accountStatusKinds('retry@outlook.com'),
    ['busy', 'fail'],
  );
});

test('AbortError does not write a request failure into the current session', async () => {
  const harness = createRuntime();
  harness.context.fetch = async () => {
    const error = new Error('request aborted');
    error.name = 'AbortError';
    throw error;
  };

  await harness.runtime.fetchMail();

  assert.equal(
    harness.runtime.state.accountStatus.get('first@outlook.com').kind,
    'busy',
  );
  assert.deepEqual(Array.from(harness.runtime.state.failedRows), []);
  assert.equal(harness.renderAccountCalls(), 1);
});

test('a stale request rejection does not write failure state', async () => {
  const harness = createRuntime();
  let rejectRequest;
  harness.context.fetch = () => new Promise((resolve, reject) => {
    rejectRequest = reject;
  });

  const operation = harness.runtime.fetchMail();
  await waitFor(() => typeof rejectRequest === 'function', 'fetch did not start');
  harness.runtime.sessionRequests.reset();
  rejectRequest(new Error('late network failure'));
  await operation;

  assert.equal(
    harness.runtime.state.accountStatus.get('first@outlook.com').kind,
    'busy',
  );
  assert.deepEqual(Array.from(harness.runtime.state.failedRows), []);
  assert.equal(harness.renderAccountCalls(), 1);
});

test('render failures after a successful request are not mislabeled as request failures', async () => {
  const preservedFailure = {
    email: 'other@outlook.com',
    ok: false,
    stage: 'oauth',
    error: 'preserved',
  };
  const harness = createRuntime({ failedRows: [preservedFailure] });
  harness.context.fetch = async () => successResponse();
  harness.runtime.installHooks({
    renderFetchResult() {
      throw new Error('render exploded');
    },
    setBusy(busy) {
      harness.runtime.state.busy = busy;
      harness.busyTransitions.push(busy);
    },
  });

  await harness.runtime.fetchMail();

  const status = harness.runtime.state.accountStatus.get('first@outlook.com');
  assert.equal(status.kind, 'busy');
  assert.notEqual(status.stage, 'request');
  assert.deepEqual(Array.from(harness.runtime.state.failedRows), [preservedFailure]);
  assert.equal(harness.runtime.state.busy, false);
});

test('a stale finally block cannot release the current operation gate owner', async () => {
  const harness = createRuntime();
  const requests = [];
  harness.context.fetch = () => new Promise((resolve, reject) => {
    requests.push({ resolve, reject });
  });

  const staleOperation = harness.runtime.fetchMail();
  await waitFor(() => requests.length === 1, 'stale fetch did not start');
  harness.runtime.sessionRequests.reset();
  harness.runtime.mailOperationGate.reset();

  const currentOperation = harness.runtime.fetchMail();
  await waitFor(() => requests.length === 2, 'current fetch did not start');
  requests[0].reject(new Error('stale request failed'));
  await staleOperation;

  const blockedAttempt = harness.runtime.fetchMail();
  const blockedReturned = await settlesWithin(blockedAttempt);
  if (!blockedReturned && requests[2]) {
    requests[2].resolve(successResponse());
    await blockedAttempt;
  }
  assert.equal(blockedReturned, true, 'stale finally released the current gate owner');
  assert.equal(requests.length, 2);
  assert.deepEqual(harness.busyTransitions, [true, true]);

  requests[1].resolve(successResponse());
  await currentOperation;
  assert.equal(harness.runtime.state.busy, false);

  const nextOperation = harness.runtime.fetchMail();
  await waitFor(() => requests.length === 3, 'gate did not admit later work');
  requests[2].resolve(successResponse());
  await nextOperation;
  assert.equal(requests.length, 3);
});
