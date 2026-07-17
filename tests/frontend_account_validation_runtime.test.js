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

const VALID_ACCOUNT = 'user@outlook.com----password----client-id----refresh-token';

function fakeElement(id = '') {
  const attributes = new Map();
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
    setAttribute(name, value) { attributes.set(name, String(value)); },
    getAttribute(name) { return attributes.get(name) ?? null; },
    removeAttribute(name) { attributes.delete(name); },
    hasAttribute(name) { return attributes.has(name); },
    append() {},
    appendChild() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    focus() {},
    scrollIntoView() {},
  };
}

function response(data) {
  return {
    ok: true,
    async json() { return data; },
  };
}

function createRuntime({
  accountText = '',
  accounts = [],
  parsedText = '',
  failedRows = [],
} = {}) {
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

  let nextTimerId = 1;
  const timers = new Map();
  const setFakeTimeout = (callback, delay) => {
    const id = nextTimerId;
    nextTimerId += 1;
    timers.set(id, { callback, delay });
    return id;
  };
  const clearFakeTimeout = (id) => timers.delete(id);

  let controllerStarts = 0;
  const runtimeLogic = {
    ...logic,
    createSessionCoordinator() {
      return logic.createSessionCoordinator(() => {
        controllerStarts += 1;
        return {
          signal: {},
          abort() {},
        };
      });
    },
  };

  const requests = [];
  const context = {
    AbortController,
    clearTimeout: clearFakeTimeout,
    console,
    document,
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      if (url === '/api/accounts') {
        return response({
          count: 1,
          accounts: [{ email: 'user@outlook.com' }],
        });
      }
      if (url === '/api/fetch') {
        return response({
          fetched: 0,
          failed: 0,
          rows: [],
          messages: [],
        });
      }
      throw new Error(`unexpected request: ${url}`);
    },
    localStorage: {
      getItem() { return null; },
      setItem() {},
    },
    navigator: {},
    setTimeout: setFakeTimeout,
    window: {
      clearTimeout: clearFakeTimeout,
      DOMParser: null,
      MailReceiverLogic: runtimeLogic,
      setTimeout: setFakeTimeout,
    },
  };
  context.globalThis = context;
  vm.createContext(context);

  const bridge = `
globalThis.__accountValidationRuntimeTest = {
  state,
  inspectAccountText,
  shouldAutoParseAccountText,
  syncActionAvailability,
  syncAccountPrivacy,
  scheduleAccountParse,
  clearScheduledAccountParse,
  parseInput,
  payloadBase,
  fetchMail,
  retryFailedAccounts,
  installHooks() {
    renderAccounts = function (nextAccounts) { state.accounts = nextAccounts; };
    resetSessionResults = function () {
      state.failedRows = [];
      state.messagesByAccount.clear();
      state.selectedMessageKey = null;
      state.activeAccountEmail = '';
    };
    renderMailLoadingState = function () {};
    renderFetchResult = function () {};
    renderMailErrorState = function () {};
    renderResults = function () {};
    selectInitialMessage = function () {};
    renderMailSummary = function () {};
    syncSessionActions = function () {};
    addLog = function () {};
  },
};
`;
  vm.runInContext(`${APP_RUNTIME_SOURCE}\n${bridge}`, context, {
    filename: APP_PATH,
  });

  const runtime = context.__accountValidationRuntimeTest;
  runtime.installHooks();
  elementFor('accountTextInput').value = accountText;
  elementFor('mailboxInput').value = 'INBOX';
  elementFor('limitInput').value = '20';
  runtime.state.accounts = accounts.slice();
  runtime.state.parsedText = parsedText;
  runtime.state.failedRows = failedRows.slice();
  runtime.state.fetchScope = 'all';

  return {
    controllerStarts: () => controllerStarts,
    elementFor,
    requests,
    runNextTimer() {
      const entry = timers.entries().next();
      assert.equal(entry.done, false, 'no scheduled timer');
      const [id, timer] = entry.value;
      timers.delete(id);
      timer.callback();
    },
    runtime,
    timerCount: () => timers.size,
  };
}

test('inspectAccountText trims every field and rejects empty required credentials', () => {
  const harness = createRuntime();
  const invalidInputs = [
    'user@outlook.com--------client-id----refresh-token',
    'user@outlook.com----   ----client-id----refresh-token',
    'user@outlook.com----password--------refresh-token',
    'user@outlook.com----password----   ----refresh-token',
    'user@outlook.com----password----client-id----',
    'user@outlook.com----password----client-id----   ',
  ];

  for (const input of invalidInputs) {
    const report = harness.runtime.inspectAccountText(input);
    assert.equal(report.totalLines, 1, input);
    assert.equal(report.validLines, 0, input);
    assert.equal(report.invalidLines, 1, input);
  }

  const trimmed = harness.runtime.inspectAccountText(
    '  user@outlook.com  ----  password  ----  client-id  ----  refresh-token  ',
  );
  assert.equal(trimmed.validLines, 1);
  assert.equal(trimmed.invalidLines, 0);
});

test('account validation is all-or-nothing across non-empty lines', async () => {
  const accountText = [
    VALID_ACCOUNT,
    '   ',
    'other@outlook.com----password----client-id----   ',
  ].join('\n');
  const harness = createRuntime({ accountText });

  const report = harness.runtime.inspectAccountText(accountText);
  assert.equal(report.totalLines, 2);
  assert.equal(report.validLines, 1);
  assert.equal(report.invalidLines, 1);
  assert.equal(harness.runtime.shouldAutoParseAccountText(), false);
  harness.runtime.scheduleAccountParse();
  assert.equal(harness.timerCount(), 0);
  await harness.runtime.fetchMail();
  assert.deepEqual(harness.requests, []);

  harness.elementFor('accountTextInput').value = [
    VALID_ACCOUNT,
    '',
    'other@outlook.com--password--client-id--refresh-token',
  ].join('\n');
  assert.equal(harness.runtime.shouldAutoParseAccountText(), false);
  await harness.runtime.fetchMail();
  assert.deepEqual(harness.requests, []);
});

test('fetch availability requires fully valid input while privacy still follows non-empty input', () => {
  const harness = createRuntime({
    accountText: 'user@outlook.com----password----client-id----   ',
  });
  const fetchButton = harness.elementFor('fetchBtn');
  const privacyButton = harness.elementFor('privacyToggle');

  harness.runtime.syncActionAvailability();
  harness.runtime.syncAccountPrivacy();
  assert.equal(fetchButton.disabled, true);
  assert.equal(fetchButton.getAttribute('aria-disabled'), 'true');
  assert.equal(privacyButton.disabled, false);
  assert.equal(privacyButton.getAttribute('aria-disabled'), 'false');

  harness.elementFor('accountTextInput').value = VALID_ACCOUNT;
  harness.runtime.syncActionAvailability();
  assert.equal(fetchButton.disabled, false);
  assert.equal(fetchButton.getAttribute('aria-disabled'), 'false');
});

test('parseInput rejects invalid text before starting a request and clears stale accounts', async () => {
  const harness = createRuntime({
    accountText: 'user@outlook.com----password--------refresh-token',
    accounts: [{ email: 'old@outlook.com' }],
    parsedText: 'old@outlook.com----password----client-id----refresh-token',
  });
  harness.runtime.state.selectedAccountEmail = 'old@outlook.com';
  harness.runtime.state.accountStatus.set('old@outlook.com', { kind: 'fetch' });

  const result = await harness.runtime.parseInput();

  assert.equal(result, false);
  assert.deepEqual(harness.requests, []);
  assert.equal(harness.controllerStarts(), 0);
  assert.equal(harness.runtime.state.busy, false);
  assert.equal(harness.runtime.state.accounts.length, 0);
  assert.equal(harness.runtime.state.parsedText, '');
  assert.equal(harness.runtime.state.selectedAccountEmail, '');
  assert.equal(harness.runtime.state.accountStatus.size, 0);
  assert.throws(() => harness.runtime.payloadBase(), /账号|格式|信息/);
});

test('defensive fetch and retry calls do not contact any URL for invalid input', async () => {
  const invalidText = 'user@outlook.com----password----client-id----   ';
  const staleAccount = { email: 'user@outlook.com' };
  const fetchHarness = createRuntime({
    accountText: invalidText,
    accounts: [staleAccount],
    parsedText: VALID_ACCOUNT,
  });

  await fetchHarness.runtime.fetchMail();
  assert.deepEqual(fetchHarness.requests, []);
  assert.equal(fetchHarness.runtime.state.busy, false);
  assert.equal(fetchHarness.runtime.state.accounts.length, 0);

  const retryHarness = createRuntime({
    accountText: invalidText,
    accounts: [staleAccount],
    parsedText: VALID_ACCOUNT,
    failedRows: [{
      email: 'user@outlook.com',
      ok: false,
      stage: 'fetch',
      error: 'old failure',
    }],
  });
  await retryHarness.runtime.retryFailedAccounts();
  assert.deepEqual(retryHarness.requests, []);
  assert.equal(retryHarness.runtime.state.busy, false);
  assert.equal(retryHarness.runtime.state.accounts.length, 0);
});

test('an auto-parse timer cannot POST after the input becomes invalid', async () => {
  const harness = createRuntime({ accountText: VALID_ACCOUNT });

  harness.runtime.scheduleAccountParse();
  assert.equal(harness.timerCount(), 1);
  harness.elementFor('accountTextInput').value =
    'user@outlook.com----password----client-id----   ';
  harness.runNextTimer();
  await Promise.resolve();

  assert.deepEqual(harness.requests, []);
  assert.equal(harness.timerCount(), 0);
  assert.equal(harness.runtime.state.busy, false);
});

test('a stale auto-parse timer clears an old busy account session when the new input is invalid', async () => {
  const oldAccountText = 'old@outlook.com----password----client-id----refresh-token';
  const harness = createRuntime({
    accountText: VALID_ACCOUNT,
    accounts: [{ email: 'old@outlook.com' }],
    parsedText: oldAccountText,
  });
  harness.runtime.state.selectedAccountEmail = 'old@outlook.com';
  harness.runtime.state.accountStatus.set('old@outlook.com', { kind: 'busy' });
  harness.runtime.state.busy = true;

  harness.runtime.scheduleAccountParse();
  assert.equal(harness.timerCount(), 1);
  harness.elementFor('accountTextInput').value =
    'user@outlook.com----password----client-id----   ';
  harness.runNextTimer();
  await Promise.resolve();

  assert.deepEqual(harness.requests, []);
  assert.equal(harness.timerCount(), 0);
  assert.equal(harness.runtime.state.accounts.length, 0);
  assert.equal(harness.runtime.state.parsedText, '');
  assert.equal(harness.runtime.state.selectedAccountEmail, '');
  assert.equal(harness.runtime.state.accountStatus.size, 0);
  assert.equal(harness.runtime.state.busy, false);
});

test('valid account input still parses and fetches normally', async () => {
  const harness = createRuntime({ accountText: VALID_ACCOUNT });

  assert.equal(await harness.runtime.parseInput(), true);
  assert.deepEqual(harness.requests.map((request) => request.url), ['/api/accounts']);
  assert.equal(harness.runtime.state.accounts.length, 1);
  assert.equal(harness.runtime.state.parsedText, VALID_ACCOUNT);

  harness.requests.length = 0;
  await harness.runtime.fetchMail();
  assert.deepEqual(harness.requests.map((request) => request.url), ['/api/fetch']);
  assert.equal(harness.runtime.state.busy, false);
});
