const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const logic = require('../mail_receiver/static/app_logic.js');

test('verification registry chooses the highest-priority matching rule', () => {
  const registry = logic.createVerificationRuleRegistry();
  registry.register({
    id: 'low',
    priority: 1,
    match: () => ({ code: '111111' }),
  });
  registry.register({
    id: 'high',
    priority: 10,
    match: () => ({ code: '222222' }),
  });

  assert.deepEqual(registry.find({}), {
    code: '222222',
    rule_id: 'high',
  });
});

test('verification registry preserves registration order at equal priority', () => {
  const registry = logic.createVerificationRuleRegistry([
    { id: 'first', priority: 5, match: () => ({ code: '111111' }) },
    { id: 'second', priority: 5, match: () => ({ code: '222222' }) },
  ]);

  assert.equal(registry.find({}).rule_id, 'first');
});

test('verification registry isolates a broken rule and continues', () => {
  const registry = logic.createVerificationRuleRegistry([
    {
      id: 'broken',
      priority: 10,
      match: () => {
        throw new Error('broken rule');
      },
    },
    { id: 'fallback', priority: 0, match: () => ({ code: '333333' }) },
  ]);

  assert.deepEqual(registry.find({}), {
    code: '333333',
    rule_id: 'fallback',
  });
});

test('verification registry rejects rules without stable ids or match functions', () => {
  const registry = logic.createVerificationRuleRegistry();

  assert.throws(() => registry.register({ match() {} }), /id and match/);
  assert.throws(() => registry.register({ id: 'missing-match' }), /id and match/);
});

test('verification registry rejects duplicate rule ids', () => {
  const registry = logic.createVerificationRuleRegistry([
    { id: 'provider:generic', match: () => null },
  ]);

  assert.throws(
    () => registry.register({ id: 'provider:generic', match: () => null }),
    /already registered/,
  );
});

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
      DOMParser: null,
      MailReceiverLogic: logic,
    },
  };
  context.globalThis = context;
  vm.createContext(context);

  const bridge = `
globalThis.__verificationRuntimeTest = {
  extractVerificationCode,
};
`;
  vm.runInContext(`${APP_RUNTIME_SOURCE}\n${bridge}`, context, {
    filename: APP_PATH,
  });

  return context.__verificationRuntimeTest;
}

test('extracts the body code instead of digits in the recipient address', () => {
  const runtime = createRuntime();
  const result = runtime.extractVerificationCode({
    account_email: 'BrandonNichols1400@outlook.com',
    subject: 'Your temporary ChatGPT verification code',
    sender: 'ChatGPT <noreply@tm.openai.com>',
    recipients: 'BrandonNichols1400+c688c2@outlook.com',
    body_preview: 'Enter this temporary verification code to continue: 987243 ...',
    body_text: [
      'Enter this temporary verification code to continue:',
      '987243',
      'Please ignore this email if this wasn\'t you trying to create a ChatGPT account.',
      'Best,',
      'The ChatGPT team',
    ].join('\n'),
  });

  assert.equal(result.code, '987243');
  assert.equal(result.provider, 'generic');
  assert.equal(result.confidence, 'high');
  assert.equal(result.rule_id, 'provider:generic');
});

test('does not treat digits in sender or recipient addresses as a verification code', () => {
  const runtime = createRuntime();
  const result = runtime.extractVerificationCode({
    subject: 'Your verification code',
    sender: 'Service <noreply1234@example.com>',
    recipients: 'customer654321@example.com',
    body_text: 'Open the application to continue. No code was included in this message.',
  });

  assert.equal(result.code, '');
  assert.equal(result.confidence, 'none');
});

test('does not use address digits through the generic fallback when content has no code', () => {
  const runtime = createRuntime();
  const result = runtime.extractVerificationCode({
    subject: 'Weekly newsletter',
    sender: 'Updates <news@example.com>',
    recipients: 'customer123456@example.com',
    body_text: 'Here is your weekly account update.',
  });

  assert.equal(result.code, '');
  assert.equal(result.confidence, 'none');
});

test('keeps sender metadata available for provider matching without extracting its digits', () => {
  const runtime = createRuntime();
  const result = runtime.extractVerificationCode({
    subject: 'Confirm your sign-in',
    sender: 'xAI <noreply2026@x.ai>',
    recipients: 'member1400@example.com',
    body_text: 'Your confirmation code is ABC-123.',
  });

  assert.equal(result.code, 'ABC-123');
  assert.equal(result.provider, 'xai');
  assert.equal(result.providerLabel, 'xAI');
});

test('still extracts generic fallback codes from message content without a keyword', () => {
  const runtime = createRuntime();
  const result = runtime.extractVerificationCode({
    subject: 'Sign-in notice',
    sender: 'Service <noreply1234@example.com>',
    recipients: 'customer654321@example.com',
    body_text: 'Use 765432 to continue.',
  });

  assert.equal(result.code, '765432');
  assert.equal(result.source, '正文数字');
  assert.equal(result.confidence, 'medium');
});

test('still accepts a verification code placed in the subject', () => {
  const runtime = createRuntime();
  const result = runtime.extractVerificationCode({
    subject: 'Verification code: 246810',
    sender: 'Service <noreply1234@example.com>',
    recipients: 'customer654321@example.com',
    body_text: 'Use the code from the subject to continue.',
  });

  assert.equal(result.code, '246810');
  assert.equal(result.confidence, 'high');
});
