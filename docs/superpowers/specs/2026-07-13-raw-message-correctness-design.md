# Raw Message Correctness Design

## Scope

Make partial IMAP fetches report whether their RFC822 bytes are complete, and make the Web API's opt-in raw response byte-preserving. Keep the existing fast 16 KiB preview mode, readable `raw_message` string, fetch batching, and public request fields.

## Problems

### Partial literals are modeled as complete raw messages

`fetch_messages(max_bytes=N)` requests `BODY.PEEK[]<0.N>`, but the returned literal is stored unconditionally in `EmailRecord.raw_message`. A literal of exactly `N` bytes can be either a complete `N`-byte message or an `N`-byte prefix of a larger message. The current request does not include `RFC822.SIZE`, so callers cannot distinguish them.

### The Web raw string is not byte-preserving

`email_record_to_dict(..., include_raw=True)` decodes RFC822 bytes as UTF-8 with replacement. Legal non-UTF-8 8BITMIME bytes become U+FFFD and cannot be reconstructed, despite the API documentation calling this field the complete original.

## Decision

### IMAP completeness metadata

Partial fetches request:

```text
(UID RFC822.SIZE BODY.PEEK[]<0.N>)
```

Parse the literal together with `RFC822.SIZE`. A partial literal is complete only when its byte length equals the reported RFC822 size. If size metadata is absent, mark it incomplete conservatively. Full `BODY.PEEK[]` fetches remain complete by definition.

Add `raw_message_complete: bool = True` to `EmailRecord`. Propagate the parsed flag through record construction and always serialize it in Web message objects. Existing constructors remain compatible through the default.

The IMAP test double must honor partial ranges and emit `BODY[]<0>` plus `RFC822.SIZE`, so tests exercise actual prefix behavior instead of returning full bytes for every request.

### Byte-preserving Web representation

When `include_raw` is true, return both:

- `raw_message`: the existing UTF-8-with-replacement text view for compatibility and convenient inspection.
- `raw_message_base64`: Base64 of the exact `EmailRecord.raw_message` bytes.

`raw_message_complete` states whether those bytes represent the complete RFC822 message. In the documented Web flow, `include_raw=true` uses a full fetch, so it is true. Base64 is the authoritative lossless representation.

## Compatibility

- No request field is removed or renamed.
- Existing `raw_message` consumers continue receiving a string.
- Default Web responses still omit both raw content fields.
- `EmailRecord` callers that do not specify completeness default to true.
- SQLite and CLI full-fetch behavior remain unchanged.

## Error Handling

Missing `RFC822.SIZE` on a partial response does not fail the batch; it produces `raw_message_complete=false`. Malformed size text is treated the same way. Existing malformed UID and FETCH response behavior is unchanged and will be handled in its separate trailer fix.

## Testing

1. A realistic partial IMAP batch returns one short complete message and one truncated prefix, with accurate completeness flags and bytes.
2. A full fetch remains complete.
3. Default Web serialization omits raw content but includes completeness metadata.
4. Opt-in serialization round-trips non-UTF-8 bytes through `raw_message_base64` exactly while preserving the compatibility text view.
5. API documentation identifies Base64 as the lossless field.
6. Python 3.11 and current-Python full suites pass.

## Exclusions

- UID metadata found only after the literal is a separate FETCH trailer fix.
- Sequence-number races and mailbox encoding are separate IMAP fixes.
- The 1,000-character body preview limit and preview rendering are unchanged.
