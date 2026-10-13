# Bounded canonical JSON

`tools.bounded_canonical_json` is a dependency-free verifier boundary for JSON
artifacts that can arrive either as raw text/bytes or as already-decoded Python
objects.

It exists because parser limits and object limits are different trust
boundaries. A byte parser can reject duplicate keys and enormous integer
tokens, while a direct-object verifier can still be exposed to cycles, deep
container recursion, stateful/subclassed containers, Python's `False == 0`
mapping equality, lone surrogates, or a small object graph that expands into a
large canonical JSON stream through long scalars or repeated aliases.

## Contract

```python
from tools.bounded_canonical_json import (
    BoundaryError,
    Limits,
    canonical_bytes,
    canonical_equal,
    loads_strict,
)

packet = loads_strict(raw_packet)
receipt_bytes = canonical_bytes(receipt)

if not canonical_equal(receipt, expected_receipt):
    raise BoundaryError("receipt_mismatch")
```

Admission is fail-closed and accepts only exact built-in JSON shapes:
`dict`, `list`, `str`, `int`, `float`, `bool`, and `None`. Dict keys must be
exact strings. Container subclasses, cycles, duplicate text keys, non-finite
numbers, invalid UTF-8/surrogates, and integers outside the configured range
are rejected.

Before the general JSON serializer is entered, direct objects are walked
iteratively and charged for:

- open-container depth;
- every serialized node occurrence (aliases are charged again);
- JSON punctuation;
- exact UTF-8 JSON-string bytes, including escaping;
- every key occurrence;
- scalar bytes.

The same walk freezes one verifier-owned plain JSON generation. Container
cardinality is checked before each bounded snapshot allocation, and the later
serializer sees only that detached generation rather than rereading the
caller's mutable dict/list objects. A mutation after admission therefore cannot
change the bytes that were budgeted and approved.

That also means a huge string or many references to one long string cannot
remain under a node budget and then amplify inside `json.dumps`.

Canonical output is UTF-8 JSON with sorted keys, compact separators,
`ensure_ascii=False`, and `allow_nan=False`. Identity comparisons are therefore
byte/type sensitive: `false` is not `0`, and `true` is not `1`.

## Defaults

`Limits()` defaults to:

- depth: 64 open containers
- nodes: 200,000 serialized occurrences
- canonical bytes: 4 MiB
- integer magnitude: `10**15`

Callers with a smaller legitimate artifact envelope should pass tighter
`Limits`. A boundary error exposes only a stable code such as `too_large`,
`too_complex`, `too_deep`, `duplicate_key`, or `integer_out_of_range`.

## Adoption rule

Use this module at a verifier-owned ingress boundary. Do not validate one
generation and later read the caller's original mutable/stateful object.
`canonical_bytes()` already freezes its direct-object generation before
serialization; retain those canonical bytes (or parse fresh trusted raw input)
and derive trusted digests/receipts from that same admitted generation.

This library does not authorize provider calls, outbound sends, buyer actions,
payments, cash movement, submissions, or any other external effect.
