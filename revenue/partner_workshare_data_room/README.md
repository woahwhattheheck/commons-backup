# Partner / Workshare Conversion Data Room

Operation: `PARTNER-WORKSHARE-CONVERSION-DATA-ROOM-20260916`

This package turns evidence-bound prime/sub teaming notes into a deterministic owner-review packet. It is a **conversion and review tool**, not an outbound system and not commercial or relationship authority.

## Truth boundary

The hard relationship ceiling is:

`PROPOSED_NOT_ACCEPTED`

The compiler cannot represent a prospective partner as accepted, committed, awarded, paid, or revenue-producing. It also rejects numeric pricing commitments and any acceptance state other than `NOT_REQUESTED_OR_ACCEPTED`.

A packet status has only two operational meanings:

- `OWNER_REVIEW_READY`: the supplied evidence is internally sufficient for human review. It does **not** mean a partner accepted, a buyer received anything, a bid was submitted, pricing was approved, work was awarded, payment occurred, or revenue exists.
- `HOLD`: the packet was structurally valid, but at least one evidence-sensitive assertion lacks current verified support.

Malformed or authority-violating input fails closed with exit code `1`. `--fail-on-hold` makes an evidence HOLD return exit code `2`.

## What it binds

The v1 input captures:

- source-bound opportunity identity, observation time, deadline, and SHA-256;
- exactly one prime plus one or more prospective partners;
- evidence receipts with subject, kind, status, source, hash, observed time, and optional validity;
- explicit capability claims and capability slices;
- proposed workstreams with one lead and basis-point allocations summing to 10,000;
- exclusions and assumptions;
- required security/access evidence;
- delivery-proof references with path/URL and SHA-256;
- **pricing-basis placeholders only**, never amount/rate/total/currency commitments;
- explicit acceptance questions that remain unanswered by the compiler.

Sensitive claims (`CAPABILITY`, `CERTIFICATION`, `PAST_PERFORMANCE`, `SECURITY`, `PRICING_BASIS`) require at least one current `VERIFIED` receipt for the same party or they compile to `HOLD`. `PARTNER_RELATIONSHIP` free-text claims are rejected entirely; the bounded `relationship_state` field is the only relationship-state carrier.

Required security/access entries additionally require a current `VERIFIED` receipt whose kind is exactly `SECURITY`.

## Determinism and receipts

The compiler normalizes semantically unordered lists, renders one Markdown packet, and emits a receipt containing:

- normalized canonical-input SHA-256;
- packet byte SHA-256;
- status and sorted HOLD reasons;
- opportunity identity and `as_of`.

`verify` recompiles from the supplied input and checks exact packet bytes and exact receipt structure. It detects packet or receipt tampering.

No `assert` statement carries a safety guard. The suite runs the compiler and verifier under optimized Python (`python -O`) to prove guard behavior is not optimized away.

## Five-minute synthetic demo

From repository root:

```bash
python revenue/partner_workshare_data_room/compile_packet.py compile \
  --input revenue/partner_workshare_data_room/fixtures/opportunity.synthetic.json \
  --out-dir /tmp/workshare-room \
  --fail-on-hold

python revenue/partner_workshare_data_room/compile_packet.py verify \
  --input revenue/partner_workshare_data_room/fixtures/opportunity.synthetic.json \
  --packet /tmp/workshare-room/packet.md \
  --receipt /tmp/workshare-room/receipt.json
```

Expected verifier prefix:

```text
VERIFY_OK opportunity=SYN-TEAM-001 status=OWNER_REVIEW_READY
```

Inspect `/tmp/workshare-room/packet.md` and `/tmp/workshare-room/receipt.json`. The bundled fixture is deliberately synthetic; its receipts demonstrate mechanics and are **not real-world qualifications**.

## Tests

```bash
python -m unittest discover \
  -s revenue/partner_workshare_data_room/tests \
  -p 'test_*.py' -v

python -O -m unittest discover \
  -s revenue/partner_workshare_data_room/tests \
  -p 'test_*.py' -v
```

The suite covers:

- ready-path compile + verify;
- semantic permutation determinism;
- stale evidence;
- conflicting/unverified evidence;
- missing sensitive-claim evidence;
- partner-relationship truth escalation;
- accepted relationship state rejection;
- numeric pricing rejection;
- acceptance-state rejection;
- repository-path traversal rejection;
- HTTPS URL userinfo rejection;
- invalid/ambiguous workshare allocations;
- duplicate IDs;
- security-kind mismatch;
- receipt/packet tampering;
- fail-on-HOLD behavior;
- optimized-Python enforcement.

## Input contract

The normative runtime contract is implemented by `validate_and_normalize()` in `compile_packet.py`; `schema/input.schema.json` is a review-friendly structural companion. Runtime validation is intentionally stricter in several cross-field areas that plain JSON Schema does not conveniently express:

1. exactly one `PRIME`;
2. all party/evidence/workshare references must resolve;
3. evidence subject must match the claim/capability subject;
4. required security evidence must have `kind=SECURITY`;
5. current validity is evaluated against `as_of`;
6. workshare basis points sum to exactly 10,000 and the lead has a positive allocation;
7. IDs are unique in each collection;
8. pricing cannot carry amount/currency/rate/total;
9. partner-relationship claims are not free-text;
10. output truth never exceeds `PROPOSED_NOT_ACCEPTED`.

## Side-effect boundary

The program performs no network calls. Its only mutation is writing these files beneath the operator-provided output directory:

- `canonical_input.json`
- `packet.md`
- `receipt.json`

It has no code path for email, Slack, forms, CRM, buyer submission, partner contact, signature, price mutation, payment, provider mutation, award recording, or revenue recording.

External outreach or submission is a separate owner-controlled workflow. In the current swarm operating model, any outbound also requires the independent Muse single-writer collision gate before a send is attempted.

## Source and delivery-reference safety

Evidence `source` and delivery-proof `path` fields accept only:

- `https://` URLs without embedded userinfo; or
- safe repository-relative POSIX paths with no absolute root, `.` segment, `..` segment, or backslash.

A SHA-256 field binds the claimed source/proof bytes at the evidence layer. This compiler validates the digest shape and carries it into the packet; it does not fetch or silently re-interpret the referenced material.

## Intended revenue use

The data room reduces the friction between “this opportunity might need a partner” and “an owner can inspect exactly what each party is proposed to do, which assertions have evidence, which assertions are on HOLD, and which commercial/acceptance questions remain open.”

That is useful before a prime/sub discussion or submission decision, while preserving the distinction between a **proposal** and an **accepted relationship**.
