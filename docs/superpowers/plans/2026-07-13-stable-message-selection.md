# Stable Message Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent cross-account message and verification-code selection when independent fetch responses reuse the same numeric message ID.

**Architecture:** Keep the Web API unchanged. Add a DOM-free classic JavaScript helper module that derives a stable key from the IMAP identity tuple, then make all frontend selection paths use that key instead of request-local numeric IDs. Exercise the helper with Node's built-in test runner and include that test in Python unittest discovery through a small bridge.

**Tech Stack:** Native browser JavaScript, Node `node:test`, Python `unittest`, existing static frontend.

---

## File Structure

- Create `mail_receiver/static/app_logic.js`: pure message identity and lookup helpers, usable as a browser global and CommonJS export.
- Create `tests/frontend_message_selection.test.js`: executable behavioral tests for duplicate numeric IDs and fallback identity.
- Create `tests/test_frontend_runtime.py`: unittest bridge that runs the Node behavioral test when Node is installed.
- Modify `mail_receiver/static/index.html`: load `app_logic.js` before `app.js`.
- Modify `mail_receiver/static/app.js`: replace numeric selection state and comparisons with stable message keys.
- Modify `tests/test_static_ui.py`: assert the browser integration contract.

### Task 1: Add Executable Message-Identity Tests and Pure Logic

**Files:**
- Create: `tests/frontend_message_selection.test.js`
- Create: `mail_receiver/static/app_logic.js`

- [ ] **Step 1: Write the failing Node test**

Create `tests/frontend_message_selection.test.js`:

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  findMessageByKey,
  messageKey,
} = require("../mail_receiver/static/app_logic.js");

test("duplicate request-local ids still select the requested account", () => {
  const first = {
    id: 1,
    account_email: "first@outlook.com",
    mailbox: "INBOX",
    uidvalidity: "100",
    uid: "1",
  };
  const second = {
    id: 1,
    account_email: "second@outlook.com",
    mailbox: "INBOX",
    uidvalidity: "200",
    uid: "1",
  };

  assert.notEqual(messageKey(first), messageKey(second));
  assert.equal(findMessageByKey([first, second], messageKey(second)), second);
});

test("missing uid data falls back to an account-scoped numeric id", () => {
  const first = { id: 1, account_email: "first@outlook.com", mailbox: "INBOX" };
  const second = { id: 1, account_email: "second@outlook.com", mailbox: "INBOX" };

  assert.notEqual(messageKey(first), messageKey(second));
  assert.equal(findMessageByKey([first, second], messageKey(second)), second);
  assert.equal(findMessageByKey([first, second], ""), null);
});
```

- [ ] **Step 2: Run the Node test and verify the red state**

Run:

```powershell
node --test tests/frontend_message_selection.test.js
```

Expected: FAIL because `mail_receiver/static/app_logic.js` does not exist.

- [ ] **Step 3: Implement the pure helper module**

Create `mail_receiver/static/app_logic.js`:

```javascript
(function exposeMailReceiverLogic(globalScope) {
  function messageKey(message) {
    const source = message || {};
    const accountEmail = String(source.account_email || "").toLowerCase();
    const mailbox = String(source.mailbox || "");
    const uid = String(source.uid || "");
    const uidvalidity = String(source.uidvalidity || "");
    const identity = uid
      ? ["uid", uidvalidity, uid]
      : ["id", String(source.id ?? "")];
    return JSON.stringify([accountEmail, mailbox, ...identity]);
  }

  function findMessageByKey(messages, selectedKey) {
    if (!selectedKey) {
      return null;
    }
    return (messages || []).find((message) => messageKey(message) === selectedKey) || null;
  }

  const logic = { findMessageByKey, messageKey };
  globalScope.MailReceiverLogic = logic;
  if (typeof module === "object" && module.exports) {
    module.exports = logic;
  }
})(typeof globalThis === "object" ? globalThis : window);
```

- [ ] **Step 4: Run the Node test and verify the green state**

Run:

```powershell
node --test tests/frontend_message_selection.test.js
```

Expected: 2 tests pass, 0 fail.

- [ ] **Step 5: Commit the pure logic and tests**

```powershell
git add mail_receiver/static/app_logic.js tests/frontend_message_selection.test.js
git commit -m "test: define stable frontend message identity"
```

### Task 2: Wire Stable Keys Through the Frontend

**Files:**
- Modify: `mail_receiver/static/index.html:277`
- Modify: `mail_receiver/static/app.js:1-14,426-427,831-839,1000-1006,1214-1218,1280-1286,1339-1345,1603-1700,1732-1735,1905-1920`
- Modify: `tests/test_static_ui.py` in `StaticUiTests`

- [ ] **Step 1: Write a failing browser-integration contract test**

Add this method to `StaticUiTests` in `tests/test_static_ui.py`:

```python
def test_message_selection_uses_stable_cross_account_keys(self) -> None:
    html = STATIC_HTML.read_text(encoding="utf-8")
    js = STATIC_JS.read_text(encoding="utf-8")

    self.assertLess(
        html.index('<script src="/static/app_logic.js"></script>'),
        html.index('<script src="/static/app.js"></script>'),
    )
    self.assertIn("const { findMessageByKey, messageKey } = window.MailReceiverLogic;", js)
    self.assertIn("selectedMessageKey: null", js)
    self.assertIn("findMessageByKey(allSessionMessages(), state.selectedMessageKey)", js)
    self.assertIn("button.dataset.messageKey = key", js)
    self.assertNotIn("selectedEmailId", js)
```

- [ ] **Step 2: Run the focused unittest and verify the red state**

Run:

```powershell
python -m unittest tests.test_static_ui.StaticUiTests.test_message_selection_uses_stable_cross_account_keys
```

Expected: FAIL because `app_logic.js` is not loaded and `app.js` still uses `selectedEmailId`.

- [ ] **Step 3: Load the logic module before the application script**

Change the end of `mail_receiver/static/index.html` to:

```html
<script src="/static/app_logic.js"></script>
<script src="/static/app.js"></script>
```

- [ ] **Step 4: Import the helpers and replace selection state**

At the beginning of `mail_receiver/static/app.js`, add:

```javascript
const { findMessageByKey, messageKey } = window.MailReceiverLogic;
```

Replace `selectedEmailId` in `state` with:

```javascript
selectedMessageKey: null,
```

Replace `selectedMail()` with:

```javascript
function selectedMail() {
  return findMessageByKey(allSessionMessages(), state.selectedMessageKey);
}
```

Every selection reset must assign `state.selectedMessageKey = null`.

- [ ] **Step 5: Replace list, detail, focus, and keyboard comparisons**

For each rendered mail, derive `const key = messageKey(mail)`. Store it in `button.dataset.messageKey`, compare it with `state.selectedMessageKey`, and call `showEmail(key)` from click and keyboard paths.

Use these function shapes:

```javascript
function selectInitialMessage(results = visibleMessages()) {
  if (!results.length) {
    return;
  }
  const selectedStillExists = results.some(
    (mail) => messageKey(mail) === state.selectedMessageKey,
  );
  showEmail(selectedStillExists ? state.selectedMessageKey : messageKey(results[0]));
}

function showEmail(key, results = visibleMessages()) {
  const mail = findMessageByKey(results, key);
  if (!mail) {
    addLog(`邮件不存在：${key}`, "fail");
    return;
  }
  renderDetail(mail);
  for (const row of el.mailList.querySelectorAll(".mail-row")) {
    const isSelected = row.dataset.messageKey === key;
    row.classList.toggle("active", isSelected);
    row.setAttribute("aria-selected", String(isSelected));
    row.tabIndex = isSelected ? 0 : -1;
    if (isSelected) {
      el.mailList.setAttribute("aria-activedescendant", row.id);
    }
  }
}
```

At the start of `renderDetail(mail)`, assign:

```javascript
state.selectedMessageKey = messageKey(mail);
```

Keyboard navigation must read `event.target?.dataset?.messageKey`, find the active result with `messageKey(mail)`, and pass the destination key to `showEmail()`.

- [ ] **Step 6: Run the focused integration and logic tests**

Run:

```powershell
python -m unittest tests.test_static_ui.StaticUiTests.test_message_selection_uses_stable_cross_account_keys
node --test tests/frontend_message_selection.test.js
node --check mail_receiver/static/app_logic.js
node --check mail_receiver/static/app.js
```

Expected: all commands pass.

- [ ] **Step 7: Run the complete static UI suite**

Run:

```powershell
python -m unittest tests.test_static_ui
```

Expected: 175 static UI tests pass.

- [ ] **Step 8: Commit the frontend integration**

```powershell
git add mail_receiver/static/index.html mail_receiver/static/app.js tests/test_static_ui.py
git commit -m "fix: prevent cross-account message selection"
```

### Task 3: Include Runtime JavaScript in Unittest Discovery and Verify

**Files:**
- Create: `tests/test_frontend_runtime.py`
- Modify: `README.md:131-136`

- [ ] **Step 1: Add the unittest bridge**

Create `tests/test_frontend_runtime.py`:

```python
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class FrontendRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(NODE, "Node.js is required for frontend runtime tests")
    def test_message_selection_runtime(self) -> None:
        completed = subprocess.run(
            [NODE, "--test", "tests/frontend_message_selection.test.js"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Document the development-time Node requirement**

In the README Development section, state that runtime remains Python-standard-library-only, while frontend behavioral tests run when Node.js is available. Keep the existing unittest command as the canonical full-suite command.

- [ ] **Step 3: Run fresh verification**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
py -V:Astral/CPython3.11 -m unittest discover -s tests
node --test tests/frontend_message_selection.test.js
node --check mail_receiver/static/app_logic.js
node --check mail_receiver/static/app.js
git diff --check
```

Expected: 247 Python tests pass with no skips on this workstation, 2 Node tests pass, both JavaScript syntax checks pass, and `git diff --check` reports nothing.

- [ ] **Step 4: Perform the rendered regression check**

Run a temporary local mock API outside the repository, load the real static files, return two accounts whose messages both have `id=1`, and verify:

```text
Select second account -> reader shows second account -> verification summary shows second code -> copy action copies second code
```

Also confirm there are no browser console errors. Store any temporary script or screenshot outside the repository.

- [ ] **Step 5: Commit runtime coverage and documentation**

```powershell
git add tests/test_frontend_runtime.py README.md
git commit -m "test: run frontend selection behavior in unittest"
```
