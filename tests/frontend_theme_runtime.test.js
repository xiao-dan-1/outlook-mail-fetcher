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

function createRuntime(localStorage) {
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
    localStorage,
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
globalThis.__themeRuntimeTest = {
  initTheme,
  toggleTheme,
  themeToggle: el.themeToggle,
  storageKey: THEME_STORAGE_KEY,
};
`;
  vm.runInContext(`${APP_RUNTIME_SOURCE}\n${bridge}`, context, {
    filename: APP_PATH,
  });

  return {
    context,
    document,
    runtime: context.__themeRuntimeTest,
  };
}

function storageError(message) {
  const error = new Error(message);
  error.name = 'SecurityError';
  return error;
}

test('initTheme falls back to light when localStorage reads are blocked', () => {
  const harness = createRuntime({
    getItem() { throw storageError('storage read denied'); },
    setItem() {},
  });

  assert.doesNotThrow(() => harness.runtime.initTheme());
  assert.equal(harness.document.documentElement.dataset.theme, 'light');
  assert.equal(harness.runtime.themeToggle.getAttribute('aria-pressed'), 'false');
});

test('toggleTheme still updates the DOM when localStorage writes are blocked', () => {
  const harness = createRuntime({
    getItem() { return null; },
    setItem() { throw storageError('storage write denied'); },
  });
  harness.document.documentElement.dataset.theme = 'light';

  assert.doesNotThrow(() => harness.runtime.toggleTheme());
  assert.equal(harness.document.documentElement.dataset.theme, 'dark');
  assert.equal(harness.runtime.themeToggle.getAttribute('aria-pressed'), 'true');
});

test('theme persistence remains active when localStorage is available', () => {
  const writes = [];
  const harness = createRuntime({
    getItem(key) {
      assert.equal(key, 'mailReceiverTheme');
      return 'dark';
    },
    setItem(key, value) { writes.push([key, value]); },
  });

  harness.runtime.initTheme();
  assert.equal(harness.document.documentElement.dataset.theme, 'dark');
  assert.equal(harness.runtime.themeToggle.getAttribute('aria-pressed'), 'true');

  harness.runtime.toggleTheme();
  assert.deepEqual(writes, [['mailReceiverTheme', 'light']]);
  assert.equal(harness.document.documentElement.dataset.theme, 'light');
  assert.equal(harness.runtime.themeToggle.getAttribute('aria-pressed'), 'false');
});

test('initTheme does not swallow applyTheme failures after a blocked read', () => {
  const harness = createRuntime({
    getItem() { throw storageError('storage read denied'); },
    setItem() {},
  });
  harness.runtime.themeToggle.setAttribute = () => {
    throw new Error('apply theme failed');
  };

  assert.throws(() => harness.runtime.initTheme(), /apply theme failed/);
});

test('toggleTheme does not swallow applyTheme failures after a blocked write', () => {
  const harness = createRuntime({
    getItem() { return null; },
    setItem() { throw storageError('storage write denied'); },
  });
  harness.document.documentElement.dataset.theme = 'light';
  harness.runtime.themeToggle.setAttribute = () => {
    throw new Error('apply theme failed');
  };

  assert.throws(() => harness.runtime.toggleTheme(), /apply theme failed/);
});
