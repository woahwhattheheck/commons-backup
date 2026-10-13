# Technical Capability Packet

`technical-capability-request/v1` turns a verified buyer request plus current proof assets into one deterministic, buyer-readable technical capability packet. It fills the pre-send conversion gap between “a human asked to see what you have” and the existing commercial lifecycle/outbound systems.

It does **not** send anything. It does **not** infer acceptance from a reply, a merged repository artifact, a payment link, or a packet being generated. The output is an owner-review artifact that an independently authorized single writer may use.

## What it proves

The compiler binds one `buyer_id + opportunity_id + request_id + generation` and evaluates explicit requirements against proof assets. Every proof asset carries:

- an immutable HTTPS reference plus SHA-256;
- a generation, observation time and expiry;
- explicit claims;
- explicit limitations;
- either reusable-public scope or an exact buyer/opportunity binding.

Requirement states are `SUPPORTED`, `PARTIAL`, `NEEDS_EVIDENCE`, or `UNSUPPORTED`. Mandatory requirements must all be `SUPPORTED` and the request must still be live before the packet can reach `READY_FOR_OWNER_SEND_REVIEW`. Optional unsupported asks remain visible rather than disappearing.

The selected proof set is the deterministic smallest set that covers every claim actually supported by current evidence. Ties are lexical. Duplicate URI/digest aliases, stale evidence, cross-buyer transplants, proof that contradicts an explicitly unsupported claim, missing limitations, malformed timestamps, and unknown schema fields fail closed.

## Paid next step

The same packet carries one bounded proposed next step with exact integer minor-unit price, currency, duration, scope, deliverables, dependencies, and acceptance criteria. Its status is always `PROPOSED_NOT_ACCEPTED` inside this product. Input cannot override that state.

The authority ceiling is hard-coded false for:

- outbound authorization;
- buyer acceptance;
- payment;
- revenue recognition.

Lifecycle/provider truth remains owned by the existing commercial-deal-room and single-writer integrations.

## CLI

From repository root:

```bash
python -m revenue.technical_capability_packet.cli compile \
  revenue/technical_capability_packet/fixtures/synthetic_request.json --format json

python -m revenue.technical_capability_packet.cli compile \
  revenue/technical_capability_packet/fixtures/synthetic_request.json --format markdown

python -m revenue.technical_capability_packet.cli verify PACKET.json REPORT.json
```

`compile` captures process-owned UTC current time; there is no production `--as-of` override. `verify` first recompiles the exact historical report at its recorded evaluation second, then recompiles at current process time. It returns `CURRENT_VERIFIED` only when the historical receipt is exact and the same evidence state is still current and send-review-ready.

Input is strict UTF-8 JSON: duplicate keys and non-finite numbers are rejected. CLI reads require a regular final file, reject final-component symlinks where `O_NOFOLLOW` exists, cap bytes, and fence descriptor identity/size/mtime across the read.

## Validation

```bash
python -m py_compile revenue/technical_capability_packet/*.py
python -m unittest revenue.technical_capability_packet.test_engine revenue.technical_capability_packet.test_cli -v
python -O -m unittest revenue.technical_capability_packet.test_engine revenue.technical_capability_packet.test_cli -v
```

The checked-in fixture is synthetic. Its URLs demonstrate schema shape only; fixture readiness is not buyer acceptance, deployment, payment, or revenue evidence.
