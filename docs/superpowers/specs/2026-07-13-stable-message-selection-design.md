# Stable Message Selection Design

## Scope

Fix the cross-account message selection bug without changing the Web API response contract. The numeric `messages[].id` field remains available for compatibility, and P0 deployment/security behavior is explicitly out of scope.

## Problem

The frontend fetches each account in a separate `/api/fetch` request. Every response numbers messages from `1`, so different accounts commonly contain the same numeric ID. The frontend stores all account results in one session but resolves the selected message globally by that request-local ID. As a result, the reader can show one account while the verification summary and copy action use another account's message.

## Decision

Use a stable frontend message key derived from the IMAP identity tuple:

```text
account_email + mailbox + uidvalidity + uid
```

If UID data is unavailable, fall back to the request-local `id` while retaining account and mailbox scope. Serialize the tuple rather than joining with an ad hoc delimiter.

The alternatives were rejected as follows:

- Scoping only `selectedMail()` to the active account leaves other ID-based selection paths inconsistent.
- Generating a larger numeric ID in the backend cannot guarantee uniqueness across independent stateless requests.

## Components

### Pure frontend logic

Add a small classic-script module that exposes pure helpers to both the browser and Node tests:

- `messageKey(message)` returns the stable serialized key.
- `findMessageByKey(messages, key)` resolves a selected message by the stable key.

The module has no DOM or network dependency. `index.html` loads it before `app.js`.

### Frontend state and rendering

Replace the internal numeric selection state with `selectedMessageKey`. Update message list rendering, initial selection, click handling, keyboard navigation, focus management, detail rendering, verification summary, and copy actions to compare stable keys. Keep `message.id` untouched in API data.

DOM row IDs may remain render-local, but `data-message-key` is the source of selection truth.

## Error Handling

Missing or partial message identity fields must not throw. The fallback key includes account and mailbox scope plus the existing numeric ID. An empty selection key resolves to no message.

## Testing

Follow a red-green sequence:

1. Add a Node built-in test with two accounts whose messages both have `id=1`; selecting the second message must resolve the second account.
2. Add a Python unittest bridge that runs the Node test when Node is available, so the existing discovery command includes frontend behavior coverage.
3. Implement the pure logic module and update `app.js`.
4. Run the focused Node/Python tests, `node --check`, the full Python 3.11 suite, and a rendered two-account interaction check.

## Compatibility

- No Web API fields are removed or renamed.
- No OAuth, IMAP, storage, Docker, or P0 behavior changes.
- Existing single-account behavior remains unchanged.
