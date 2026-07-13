# Session Request Isolation Design

## Scope

Allow account input to remain editable while parsing or fetching mail, while ensuring that responses started for older input can never mutate the new session. Cover automatic account parsing, normal fetch, and failed-account retry. Keep P0 behavior, Web API contracts, IMAP behavior, and verification-code rules unchanged.

## Problem

The frontend uses one global `busy` flag but has no request generation or cancellation ownership. Editing the textarea resets visible state and starts a new parse, while an older fetch can still resolve afterward. The old response then writes messages and account status into the new session; the old `finally` block can also clear the new operation's busy state.

## Decision

Combine request cancellation with revision checks:

1. Every account-input change advances a monotonically increasing session revision.
2. Advancing the revision aborts every browser request registered to the previous revision.
3. Every async continuation checks that its captured revision is still current before updating state, logs, status, rendered results, or busy state.
4. Abort and stale-session exits are silent because editing the input is an intentional user action, not an operation failure.

Cancellation reduces wasted client work. Revision checks remain the correctness boundary because a response may win the race with `abort()`, and the Python server may continue its OAuth/IMAP work after the browser disconnects.

## Components

### Session coordinator

Extend `mail_receiver/static/app_logic.js` with a DOM-free `createSessionCoordinator()` helper. It owns:

- The current revision.
- The active `AbortController` instances.
- `reset()`, which increments the revision and aborts/clears active controllers.
- `startRequest()`, which returns the current revision and a registered controller.
- `finishRequest(controller)`, which removes a completed controller.
- `isCurrent(revision)`, which guards async state updates.

The controller factory is injectable for deterministic Node tests. The browser uses the native `AbortController` by default.

### Frontend request lifecycle

Create one coordinator instance in `app.js`.

- The account textarea input handler calls `reset()` before clearing session state or scheduling a new parse.
- `parseInput()` registers a request, passes its signal to `api()`, and ignores abort/stale outcomes. It only clears busy state if its revision is still current.
- `fetchMail()` captures its operation revision. Each account request is registered and receives an abort signal. Results, summaries, errors, final status, and `finally` actions are applied only while the revision remains current.
- `retryFailedAccounts()` follows the same rules.
- `ensureParsed()` reports success/failure without converting an intentional stale parse into a user-visible error.

`api()` already spreads fetch options, so passing `signal` requires no API contract change.

## User Experience

The textarea remains editable during network work. When it changes:

- Old session results are cleared immediately, as they are today.
- The old request does not produce failure logs, error panels, or status messages.
- Valid new input continues through automatic parsing.
- Only the newest session may enable controls or display mail.

## Error Handling

Treat an operation as stale when either its captured revision is no longer current or fetch raises `AbortError`. Stale operations return without rendering errors. Genuine errors in the current revision retain existing error behavior.

All `finally` blocks must release their controller. Busy-state and session-action updates run only for the current revision, preventing an old operation from unlocking controls owned by a newer one.

## Testing

Follow red-green development:

1. Add Node unit tests proving that `reset()` advances the revision, aborts registered controllers, rejects stale revisions, and safely releases controllers.
2. Add an integration contract test proving that parsing, fetch, retry, input reset, and `finally` paths use the coordinator and pass abort signals.
3. Run a rendered delayed-response regression: start an old-account fetch, edit to a new valid account, complete the new parse, then release the old response. Assert that no old mail/status/code appears and the new session owns the busy state.
4. Run the full Python and Node suites plus JavaScript syntax checks.

## Compatibility

- Account input remains editable.
- No visible controls or API fields are removed.
- P0 deployment and credential-routing behavior remains untouched.
- Verification extraction remains postponed until representative samples are available.
