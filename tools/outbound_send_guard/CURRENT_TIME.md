# Current-time outbound send preflight

## Supported positive boundary

Positive CURRENT truth is supported only by a direct isolated/no-site script process:

```bash
python -I -S tools/outbound_send_guard/cli.py compile --intent intent.json --evidence evidence.json --out receipt.json
python -I -S tools/outbound_send_guard/cli.py verify --intent intent.json --evidence evidence.json --receipt receipt.json --out verification.json
```

`cli.py` rejects imported invocation, package/module invocation, and processes without both isolated and no-site flags before importing the current runtime. After that fence, `current_worker.py` binds the deterministic `_guard_core` to the reviewed verifier-clock implementation in `current_impl.py`. The worker samples UTC inside that fresh process; there is no supported caller-clock parameter.

## Embedded/library boundary

Imported Python is deliberately not positive CURRENT authority:

- package `evaluate` / `current.compile_current` return an explicit `EMBEDDED_CURRENT_UNAVAILABLE` receipt and HOLD historically positive decisions;
- `current.verify_current` is always invalid/non-authorizing;
- compatibility `guard.evaluate` preserves the v1 payload shape, snapshots caller-owned objects through strict JSON, derives canonical-object digests internally, and forces historical `ALLOW_NEW` / `REPLY_ONLY` to HOLD;
- legacy `intent_sha256` / `evidence_sha256` keyword arguments on that compatibility surface are inert migration inputs: their values are ignored and cannot replace provenance;
- `guard.evaluate_bytes(intent_bytes, evidence_bytes)` is the compatibility facade's exact-byte custody path: it strict-parses those bytes itself and derives the exact byte digests internally;
- compatibility receipts add `source_custody.mode` as either `CANONICAL_OBJECT_SNAPSHOT` or `EXACT_CONSUMED_BYTES`, with canonical object digests always present and exact byte digests present only when exact bytes were actually consumed;
- `guard.main` and package `python -m tools.outbound_send_guard` are non-authorizing;
- explicit historical replay is `HISTORICAL_INTEGRITY_ONLY` and outward HOLD.

A caller cannot upgrade object custody into byte custody by supplying a precomputed hash. Exact-byte custody exists only when the facade itself receives and parses both byte strings. The retained legacy evidence digest fields remain for receipt-shape compatibility, but their values are now derived from the custody mode rather than trusted from the caller.

This closes the predecessor in which caller-writable `current._utc_now` and `current._core` were synchronized into the verifier before supported calls, and the later provenance seam in which compatibility callers could overwrite receipt digest fields with arbitrary precomputed values. Those names and values are no longer authority dependencies; even dynamically assigning them cannot make the embedded surface positive or forge its source custody.

`current_worker.py` and `current_impl.py` are internal implementation/testing primitives. Calling or mutating them from an arbitrary already-running interpreter does not establish production CURRENT authority. The product's supported trust boundary starts before caller-authored Python, at the direct `-I -S` CLI process.

## Current semantics

The internal verifier-clock engine retains the reviewed policy ceilings: evidence age 900 seconds, request age 900 seconds, future skew 300 seconds, and positive receipt lifetime 60 seconds. Candidate policy may tighten but never widen those ceilings. `DO_NOT_RESEND` remains terminal; stale/future positive historical decisions become HOLD. Every receipt/verifier result keeps `side_effects_authorized=false`.

Any semantic head movement invalidates prior review/execution evidence.
