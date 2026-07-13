# Raw Message Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Distinguish partial RFC822 prefixes from complete messages and provide a byte-preserving raw Web API representation.

**Architecture:** Partial IMAP FETCH requests include `RFC822.SIZE`; parsing carries a completeness boolean into `EmailRecord`. Web serialization keeps the existing readable raw string and adds exact Base64 bytes. Existing request contracts and full-fetch callers stay compatible.

**Tech Stack:** Python standard library `email`, `imaplib`, `base64`, `unittest`.

---

### Task 1: Model Partial RFC822 Completeness

**Files:**
- Modify: `mail_receiver/imap_client.py`
- Modify: `tests/test_imap_client.py`

- [ ] **Step 1: Make the IMAP test double return realistic partial literals**

In `InstrumentedIMAP.fetch()`, detect `BODY.PEEK[]<0.N>`, slice each raw message to `N`, and emit metadata containing its full size:

```python
partial_match = re.search(r"BODY\.PEEK\[\]<0\.(\d+)>", message_parts)
partial_limit = int(partial_match.group(1)) if partial_match else None
returned_raw = raw if partial_limit is None else raw[:partial_limit]
size_metadata = f" RFC822.SIZE {len(raw)}" if partial_limit is not None else ""
body_metadata = "BODY[]" if partial_limit is None else "BODY[]<0>"
header = (
    f"{sequence} (UID {uid}{size_metadata} {body_metadata} "
    f"{{{len(returned_raw)}}}"
).encode("ascii")
```

Add `import re` to the test module.

- [ ] **Step 2: Add a failing public batch test**

Create one short raw message and one long raw message, fetch both with a limit between their lengths, then assert:

```python
self.assertEqual(records[0].raw_message, short_raw)
self.assertTrue(records[0].raw_message_complete)
self.assertEqual(records[1].raw_message, long_raw[:partial_limit])
self.assertFalse(records[1].raw_message_complete)
```

Also assert the command contains `RFC822.SIZE`.

- [ ] **Step 3: Verify RED**

```powershell
python -m unittest discover -s tests -p test_imap_client.py
```

Expected: FAIL because `EmailRecord` has no completeness field and the partial command omits `RFC822.SIZE`.

- [ ] **Step 4: Implement completeness propagation**

Add:

```python
RFC822_SIZE_RE = re.compile(rb"\bRFC822\.SIZE\s+([0-9]+)\b", re.IGNORECASE)
```

Extend the record model compatibly:

```python
raw_message: bytes
raw_message_complete: bool = True
```

Partial commands become:

```python
return f"(UID RFC822.SIZE BODY.PEEK[]<0.{safe_max_bytes}>)"
```

Change parsed payload tuples to carry `(uid, raw_message, raw_message_complete)`. For partial commands, completeness is true only when `RFC822.SIZE` exists and equals `len(raw_message)`; for full commands it is true. Pass the flag into `email_record_from_message()` and `EmailRecord`.

- [ ] **Step 5: Verify and commit**

```powershell
python -m unittest discover -s tests -p test_imap_client.py
python -m unittest discover -s tests
git diff --check
git add mail_receiver/imap_client.py tests/test_imap_client.py
git commit -m "fix: track partial raw message completeness"
```

### Task 2: Add Lossless Raw Web Serialization

**Files:**
- Modify: `mail_receiver/web.py`
- Modify: `tests/test_web.py`
- Modify: `docs/api.md`

- [ ] **Step 1: Add failing serialization tests**

Patch `fetch_messages()` to return an `EmailRecord` whose raw bytes end with `b"caf\xe9"`. With `include_raw=True`, assert:

```python
self.assertEqual(base64.b64decode(message["raw_message_base64"]), record.raw_message)
self.assertTrue(message["raw_message_complete"])
self.assertIn("\ufffd", message["raw_message"])
```

With default serialization, assert `raw_message` and `raw_message_base64` are absent while `raw_message_complete` remains present.

- [ ] **Step 2: Verify RED**

```powershell
python -m unittest discover -s tests -p test_web.py
```

Expected: FAIL because the Base64 and completeness fields are absent.

- [ ] **Step 3: Implement additive serialization**

Import `base64` and update `email_record_to_dict()`:

```python
"raw_message_complete": record.raw_message_complete,
```

When `include_raw` is true:

```python
data["raw_message"] = record.raw_message.decode("utf-8", errors="replace")
data["raw_message_base64"] = base64.b64encode(record.raw_message).decode("ascii")
```

- [ ] **Step 4: Update API documentation**

Document `raw_message_complete` in normal message objects. Describe `raw_message` as a readable, potentially lossy text view and `raw_message_base64` as the authoritative byte-preserving RFC822 value.

- [ ] **Step 5: Verify and commit**

```powershell
python -m unittest discover -s tests -p test_web.py
python -m unittest discover -s tests
git diff --check
git add mail_receiver/web.py tests/test_web.py docs/api.md
git commit -m "fix: preserve raw message bytes in web responses"
```

### Task 3: Integrated Verification

- [ ] **Step 1: Run both Python suites and frontend checks**

```powershell
& 'C:\Users\xiaodan\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe' -m unittest discover -s tests
python -m unittest discover -s tests
node --test tests/frontend_message_selection.test.js
node --check mail_receiver/static/app_logic.js
node --check mail_receiver/static/app.js
git diff --check
```

Expected: 254 Python tests pass on both interpreters, 9 Node tests pass, and syntax/diff checks report no errors.

- [ ] **Step 2: Confirm exact scope**

```powershell
git diff --name-only b95b4cb...HEAD
git status --short --branch
```

Expected tracked files: this design/plan, `mail_receiver/imap_client.py`, `tests/test_imap_client.py`, `mail_receiver/web.py`, `tests/test_web.py`, and `docs/api.md`. P0, verification extraction, CLI raw output, sequence handling, mailbox encoding, and FETCH trailer behavior remain unchanged. The two pre-existing untracked audit directories remain untouched.
