# Paid Discovery Offer Compiler

`revenue/paid_discovery_offer` is the internal revenue bridge between a **verified positive inbound** and an owner-reviewable paid-discovery scope. It converts independently retained evidence into a bounded packet without granting any external authority.

The strongest current state is `READY_FOR_OWNER_PAID_DISCOVERY_REVIEW`. That means the packet is internally coherent enough for Bryce/owner review. It does **not** mean an email may be sent, terms were accepted, a contract exists, payment may be taken, work may start, cash landed, or revenue may be recognized.

## Trust boundary

The candidate JSON cannot carry its own authority roots. The caller must supply a separate retained-roots JSON generated from independently retained source material. The compiler binds five evidence classes:

1. opportunity/buyer-scope census,
2. verified human-positive inbound,
3. exclusive buyer/opportunity/operation custody,
4. landed and verified capability evidence,
5. commercial policy (price/upfront/duration/scope floors and no-free-custom-work rules).

A structurally valid but insufficient candidate emits `HOLD` with stable reason codes. Root mismatch, stale evidence, expired/conflicted custody, unverified capabilities, underpricing, insufficient upfront payment, missing acceptance evidence, excessive duration/scope, or free-custom-work policy cannot produce the ready state.

## Strict input rules

- deterministic JSON; duplicate keys, floats, non-finite values, unsafe integers, unknown fields, malformed timestamps, and non-NFC text fail closed;
- direct email/URL/phone routes, secret-shaped text, control characters, and bidi controls are rejected from public scope text;
- input files are bounded, regular, single-link files and are checked before/after descriptor reads;
- output is a create-exclusive directory containing `packet.json`, `offer.md`, `receipt.sha256`, and `manifest.json`;
- historical replay uses `HISTORICAL_INTEGRITY_ONLY` and can never mint current authority;
- a current READY packet must reverify within 15 minutes and before all evidence expiries.

## CLI

```bash
python -m revenue.paid_discovery_offer.cli compile-current candidate.json retained_roots.json out/bundle
python -m revenue.paid_discovery_offer.cli verify-current candidate.json retained_roots.json out/bundle/packet.json
python -m revenue.paid_discovery_offer.cli audit-at candidate.json retained_roots.json 2026-09-14T12:00:00Z out/audit
python -m revenue.paid_discovery_offer.cli verify-historical candidate.json retained_roots.json out/audit/packet.json
```

All commands are local-only. The package contains no network client, email sender, payment action, provider mutation, or deployment action.

## Verification

Focused acceptance:

```bash
python -m py_compile revenue/paid_discovery_offer/*.py
python -m unittest revenue.paid_discovery_offer.test_offer revenue.paid_discovery_offer.test_hardening -v
python -O -m unittest revenue.paid_discovery_offer.test_offer revenue.paid_discovery_offer.test_hardening -v
```

The workflow in `.github/workflows/paid-discovery-offer.yml` runs the 53 core hostiles plus 8 self-review hardening hostiles (61 total) on Python 3.9 and current Python without touching external systems. The public `engine.py` is a hardened facade over private `_core.py`, preserving the exact originally tested core while adding cross-record chronology, commercial coherence, literal rendering, direct-route rejection, and exact manifest receipts.
