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
  const attributes = new Map();
  const classes = new Set();
  let html = '';
  const element = {
    id,
    value: '',
    checked: false,
    hidden: false,
    disabled: false,
    title: '',
    textContent: '',
    dataset: {},
    children: [],
    className: '',
    classList: {
      add(...names) {
        names.forEach((name) => classes.add(name));
      },
      remove(...names) {
        names.forEach((name) => classes.delete(name));
      },
      toggle(name, force) {
        const shouldAdd = force === undefined ? !classes.has(name) : Boolean(force);
        if (shouldAdd) {
          classes.add(name);
        } else {
          classes.delete(name);
        }
        return shouldAdd;
      },
      contains(name) {
        return classes.has(name) || element.className.split(/\s+/).includes(name);
      },
    },
    addEventListener() {},
    removeEventListener() {},
    setAttribute(name, value) { attributes.set(name, String(value)); },
    getAttribute(name) { return attributes.get(name) ?? null; },
    removeAttribute(name) { attributes.delete(name); },
    hasAttribute(name) { return attributes.has(name); },
    append(...nodes) { element.children.push(...nodes); },
    appendChild(node) {
      element.children.push(node);
      return node;
    },
    prepend(node) { element.children.unshift(node); },
    querySelector() { return null; },
    querySelectorAll(selector) {
      if (selector === '.mail-row') {
        return element.children.filter((child) => child.className.split(/\s+/).includes('mail-row'));
      }
      return [];
    },
    focus() {},
    scrollIntoView() {},
  };
  Object.defineProperty(element, 'innerHTML', {
    get() { return html; },
    set(value) {
      html = String(value);
      element.children = [];
    },
  });
  return element;
}

function createRuntime() {
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
      clearTimeout,
      DOMParser: null,
      MailReceiverLogic: logic,
      setTimeout,
    },
  };
  context.globalThis = context;
  vm.createContext(context);

  const bridge = `
globalThis.__mailListAriaRuntimeTest = {
  state,
  fetchMail,
  mailOperationGate,
  renderMailErrorState,
  renderMailLoadingState,
  renderResults,
  resetSessionResults,
  selectAccount,
  selectInitialMessage,
  sessionRequests,
};
`;
  vm.runInContext(`${APP_RUNTIME_SOURCE}\n${bridge}`, context, {
    filename: APP_PATH,
  });

  elementFor('mailboxInput').value = 'INBOX';
  elementFor('limitInput').value = '20';
  elementFor('rawFetchToggle').checked = false;

  return {
    context,
    elementFor,
    mailList: elementFor('mailList'),
    runtime: context.__mailListAriaRuntimeTest,
  };
}

function message(accountEmail, uid, subject = `Message ${uid}`) {
  return {
    id: Number(uid),
    uid: String(uid),
    uidvalidity: '42',
    account_email: accountEmail,
    mailbox: 'INBOX',
    sender: 'Sender <sender@example.com>',
    recipients: accountEmail,
    subject,
    sent_at: '2026-07-18T10:00:00Z',
    body_preview: `Preview ${uid}`,
    body_text: `Body ${uid}`,
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

async function waitFor(predicate, messageText = 'condition was not reached') {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.fail(messageText);
}

function configureAccount(harness, accountEmail) {
  const accountText = `${accountEmail}----password----client-id----refresh-token`;
  harness.elementFor('accountTextInput').value = accountText;
  harness.runtime.state.accounts = [{ email: accountEmail }];
  harness.runtime.state.parsedText = accountText;
  harness.runtime.state.selectedAccountEmail = accountEmail;
  harness.runtime.state.activeAccountEmail = accountEmail;
  harness.runtime.state.fetchScope = 'selected';
}

function resetInputSession(harness) {
  harness.runtime.sessionRequests.reset();
  harness.runtime.mailOperationGate.reset();
  harness.elementFor('accountTextInput').value = '';
  harness.runtime.state.accounts = [];
  harness.runtime.state.accountStatus.clear();
  harness.runtime.state.selectedAccountEmail = '';
  harness.runtime.state.activeAccountEmail = '';
  harness.runtime.state.fetchScope = 'selected';
  harness.runtime.state.parsedText = '';
  harness.runtime.resetSessionResults();
}

function assertNoListboxSemantics(harness) {
  assert.equal(harness.mailList.getAttribute('role'), null);
  assert.equal(harness.mailList.getAttribute('aria-label'), null);
  assert.equal(harness.mailList.getAttribute('aria-activedescendant'), null);
  assert.equal(harness.runtime.state.selectedMessageKey, null);
}

function renderSelectedMessages(harness, messages) {
  harness.runtime.renderResults(messages);
  harness.runtime.selectInitialMessage(messages);
}

test('populated results expose selected options and a real active descendant', () => {
  const harness = createRuntime();
  const messages = [
    message('first@outlook.com', 1),
    message('first@outlook.com', 2),
  ];

  renderSelectedMessages(harness, messages);

  assert.equal(harness.mailList.getAttribute('role'), 'listbox');
  assert.equal(harness.mailList.getAttribute('aria-label'), '邮件列表');
  assert.equal(harness.mailList.children.length, 2);
  assert.ok(harness.mailList.children.every((row) => row.getAttribute('role') === 'option'));
  const activeId = harness.mailList.getAttribute('aria-activedescendant');
  const activeRow = harness.mailList.children.find((row) => row.id === activeId);
  assert.ok(activeRow, 'aria-activedescendant must name a rendered mail row');
  assert.equal(activeRow.getAttribute('aria-selected'), 'true');
  assert.equal(activeRow.dataset.messageKey, harness.runtime.state.selectedMessageKey);
  assert.ok(
    harness.mailList.children
      .filter((row) => row !== activeRow)
      .every((row) => row.getAttribute('aria-selected') === 'false'),
  );
});

test('loading after populated results removes listbox semantics and keeps a polite busy status', () => {
  const harness = createRuntime();
  renderSelectedMessages(harness, [message('first@outlook.com', 1)]);

  harness.runtime.renderMailLoadingState('正在拉取邮件');

  assertNoListboxSemantics(harness);
  assert.equal(harness.mailList.getAttribute('aria-busy'), 'true');
  assert.match(
    harness.mailList.innerHTML,
    /role="status" aria-live="polite" aria-busy="true"/,
  );
});

test('empty results after populated results remove listbox semantics and selection', () => {
  const harness = createRuntime();
  renderSelectedMessages(harness, [message('first@outlook.com', 1)]);

  harness.runtime.renderResults([]);

  assertNoListboxSemantics(harness);
});

test('an error without results removes listbox semantics but remains a non-interrupting status', () => {
  const harness = createRuntime();
  renderSelectedMessages(harness, [message('first@outlook.com', 1)]);

  harness.runtime.renderMailErrorState('connection reset');

  assertNoListboxSemantics(harness);
  assert.match(harness.mailList.innerHTML, /role="status"/);
  assert.doesNotMatch(harness.mailList.innerHTML, /role="alert"/);
});

test('a fetch failure that re-renders preserved messages keeps populated listbox semantics', async () => {
  const harness = createRuntime();
  const accountEmail = 'first@outlook.com';
  const preserved = message(accountEmail, 1);
  configureAccount(harness, accountEmail);
  harness.runtime.state.messagesByAccount.set(accountEmail, [preserved]);
  harness.context.fetch = async () => {
    throw new Error('network unavailable');
  };

  await harness.runtime.fetchMail();

  assert.equal(harness.mailList.getAttribute('role'), 'listbox');
  assert.equal(harness.mailList.getAttribute('aria-label'), '邮件列表');
  const activeId = harness.mailList.getAttribute('aria-activedescendant');
  assert.ok(harness.mailList.children.some((row) => row.id === activeId));
  assert.equal(harness.runtime.state.selectedMessageKey, logic.messageKey(preserved));
});

test('a late fetch success cannot restore listbox semantics after an input reset', async () => {
  const harness = createRuntime();
  const accountEmail = 'first@outlook.com';
  const lateMessage = message(accountEmail, 9, 'Late response');
  configureAccount(harness, accountEmail);
  let resolveFetch;
  harness.context.fetch = () => new Promise((resolve) => {
    resolveFetch = resolve;
  });

  const operation = harness.runtime.fetchMail();
  await waitFor(() => typeof resolveFetch === 'function', 'fetch did not start');
  assert.match(harness.mailList.innerHTML, /mail-loading-state/);
  assertNoListboxSemantics(harness);

  resetInputSession(harness);
  const resetMarkup = harness.mailList.innerHTML;
  assertNoListboxSemantics(harness);
  resolveFetch(successResponse({
    rows: [{
      email: accountEmail,
      ok: true,
      fetched: 1,
      elapsed_ms: 1,
      raw_bytes: 10,
      downloaded_bytes: 10,
      message_count: 1,
      timings: {},
    }],
    messages: [lateMessage],
  }));
  await operation;

  assertNoListboxSemantics(harness);
  assert.equal(harness.mailList.innerHTML, resetMarkup);
  assert.equal(harness.mailList.children.length, 0);
  assert.equal(harness.runtime.state.messagesByAccount.size, 0);
  assert.equal(harness.runtime.state.accountStatus.size, 0);
});

test('a late fetch rejection cannot replace reset markup with an error state', async () => {
  const harness = createRuntime();
  const accountEmail = 'first@outlook.com';
  configureAccount(harness, accountEmail);
  let rejectFetch;
  harness.context.fetch = () => new Promise((resolve, reject) => {
    rejectFetch = reject;
  });

  const operation = harness.runtime.fetchMail();
  await waitFor(() => typeof rejectFetch === 'function', 'fetch did not start');
  resetInputSession(harness);
  const resetMarkup = harness.mailList.innerHTML;
  rejectFetch(new Error('late network failure'));
  await operation;

  assertNoListboxSemantics(harness);
  assert.equal(harness.mailList.innerHTML, resetMarkup);
  assert.doesNotMatch(harness.mailList.innerHTML, /mail-error-state/);
  assert.equal(harness.runtime.state.accountStatus.size, 0);
});

test('switching from a populated account to an empty account leaves no stale active descendant', () => {
  const harness = createRuntime();
  const firstEmail = 'first@outlook.com';
  const emptyEmail = 'empty@outlook.com';
  const firstMessages = [message(firstEmail, 1)];
  harness.runtime.state.accounts = [{ email: firstEmail }, { email: emptyEmail }];
  harness.runtime.state.selectedAccountEmail = firstEmail;
  harness.runtime.state.activeAccountEmail = firstEmail;
  harness.runtime.state.messagesByAccount.set(firstEmail, firstMessages);
  harness.runtime.state.messagesByAccount.set(emptyEmail, []);
  renderSelectedMessages(harness, firstMessages);
  assert.notEqual(harness.mailList.getAttribute('aria-activedescendant'), null);

  harness.runtime.selectAccount(emptyEmail);

  assertNoListboxSemantics(harness);
});

test('resetting a populated session removes the active descendant and listbox role', () => {
  const harness = createRuntime();
  const messages = [message('first@outlook.com', 1)];
  harness.runtime.state.messagesByAccount.set('first@outlook.com', messages);
  renderSelectedMessages(harness, messages);

  harness.runtime.resetSessionResults();

  assertNoListboxSemantics(harness);
});
