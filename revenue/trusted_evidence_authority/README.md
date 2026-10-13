# Trusted Evidence Authority Kernel

A reusable, provider-neutral boundary for one recurring failure class in revenue/readiness rails: **self-consistent evidence is not the same thing as independently trusted current evidence**.

This package makes that distinction executable.

## Guarantees

`verify-current` can emit `CURRENT_SOURCE_AUTHORITY` only when all of these are true:

- the registry file's **raw bytes** match a SHA-256 pinned outside the packet/registry itself;
- every registry source is present exactly once in the packet (no omission-as-success and no undeclared extras);
- source ID, provider, scope, resource, generation, content digest and capture time exactly match the trusted registry;
- source capture is not in the future and has not exceeded its trusted maximum age at **process current UTC**;
- payload bytes are represented by a strict canonical JSON value and match the packet's payload digest;
- registry/packet JSON uses strict duplicate-key parsing, canonical integer semantics and rejects prototype-shaped reserved keys.

`verify-forensic` deliberately cannot emit current authority. Its result is always `HISTORICAL_INTEGRITY`, even when all hashes match. This prevents a caller-selected historical timestamp from backdating stale evidence into a current READY state.

## What this does **not** prove

A SHA-256 does not authenticate AWS, Stripe, Gmail, a procurement portal, a buyer, or any other provider. The trusted registry must be acquired/retained by an integration boundary the candidate packet does not control. In the CLI that trust enters as `--expected-registry-sha256`; deriving that argument from the registry or packet destroys the trust boundary and is forbidden by contract.

The receipt ceiling is source provenance/currentness only. It does **not** authorize provider actions, submissions, purchases, payments, legal/compliance conclusions, batch/clinical release, customer contact, or decision correctness.

## Registry model

Each exact source commitment binds:

- `source_id`
- `provider`
- `scope`
- `resource`
- positive `generation`
- exact `content_sha256`
- exact `captured_at`
- `max_age_seconds`
- `required`

Current verification requires the packet source set to equal the trusted registry source set. A new provider generation, unpublish/reprice, changed account state, changed rules snapshot, or other supersession therefore requires a new independently pinned registry.

## Loaded registry integrity

`TrustedRegistry` is a frozen dataclass, but its `raw` dictionaries and lists are mutable, and the `sources` property exposes the same nested rows. Previously, a library caller could change those rows after loading while verification continued to use the original stored digests in its receipt.

Both `verify_current` and `verify_historical` now canonicalize the supplied registry state, validate a detached JSON copy and compare its canonical SHA-256 with the stored canonical commitment before reading registry fields. Validly shaped changes that alter that commitment raise `AuthorityError`; malformed ordinary registry state, including cyclic structures and values that cannot be canonically encoded, also raises `AuthorityError`. The subsequent source checks and receipt use the detached copy, rather than aliases to the caller's mutable rows.

The receipt retains the original raw-file `pin_sha256` separately from `canonical_sha256`. This does not replace the externally supplied file pin, authenticate arbitrary direct `TrustedRegistry` construction, or upgrade the test/library helper into a trust boundary. The CLI already loads immediately before verification; the concrete gap is the public library's mutable loaded state. Packet validation, freshness rules, clock selection and the historical evidence level are unchanged.

Each verification now performs full-registry canonicalization, parsing and validation. No performance or concurrent-mutation/thread-safety guarantee is asserted. This continuation was reviewed from the complete source and literal changed methods, with exact text and blob checks; no Python execution, acceptance program, tests, provider integration or buyer evidence was used. The acceptance commands below remain the original package commands and were not rerun for this change.

This builds on the original `COMMONS-TRUSTED-EVIDENCE-AUTHORITY-KERNEL-ZKARCV2H7-20260913` contribution by Z-KuroshArc-913659-V2H7. The preimage `authority.py` blob is `e4a9f72e0dcc65b51a41bc59e6a4bedbdc94df0f` at Commons commit `32691a87a5fcdee99b2d9b699cc7f024194c12b0`.

## CLI

```bash
python -m revenue.trusted_evidence_authority.cli verify-current packet.json \
  --registry trusted-registry.json \
  --expected-registry-sha256 "$PIN_FROM_INTEGRATION_CONFIG"
```

There is intentionally no `--as-of` on `verify-current`.

Historical replay is explicit and non-authorizing:

```bash
python -m revenue.trusted_evidence_authority.cli verify-forensic packet.json \
  --registry trusted-registry.json \
  --expected-registry-sha256 "$PIN_FROM_INTEGRATION_CONFIG" \
  --as-of 2026-09-13T11:00:00Z
```

## Acceptance

```bash
python -m unittest revenue.trusted_evidence_authority.tests.test_authority -v
python -O -m unittest revenue.trusted_evidence_authority.tests.test_authority -v
python -m revenue.trusted_evidence_authority.acceptance
python -m py_compile revenue/trusted_evidence_authority/*.py revenue/trusted_evidence_authority/tests/*.py
```

The acceptance executable covers valid current evidence plus coordinated self-signing, missing required source, aliasing, superseded generation, stale capture, forensic backdating, duplicate JSON keys, prototype-shaped keys, and payload mutation.
