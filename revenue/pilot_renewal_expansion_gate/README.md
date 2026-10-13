# Pilot delivery → renewal / expansion gate

This is a deterministic owner-review product for the commercial handoff **after a paid pilot or bounded delivery**. It prevents the common failure mode where a shipped artifact, invoice, payment link, or support conversation is silently promoted into buyer acceptance, settled payment, renewal intent, or expansion approval.

## Contract

The compiler binds an exact engagement generation to source-bound evidence for:

- accepted commercial baseline with an exact set of approved change-order IDs;
- approved change-order lineage;
- required delivered **and buyer-accepted** milestones;
- payment state backed by settlement evidence rather than invoice/link state;
- support findings;
- security/data gaps;
- a source-bound renewal review window;
- expansion hypotheses that are always `PROPOSED_NOT_ACCEPTED`;
- a Muse collision key + organization/route identity for any later, separately authorized outbound.

Terminal states are exactly:

`READY_FOR_RENEWAL_REVIEW | HOLD_ACCEPTANCE | HOLD_PAYMENT | HOLD_WINDOW | HOLD_EVIDENCE | DNR`

`DNR` requires current verified DNR evidence. It is never inferred merely because a window closed. `READY_FOR_RENEWAL_REVIEW` is **not** buyer interest, a renewal, an accepted upsell, a contract, cash, or revenue recognition.

## Current-time authority

The production CLI samples process UTC internally; candidate JSON and the public current CLI cannot choose the verifier instant. Verification first reproduces and matches the candidate packet at its recorded instant, **then** samples process UTC and re-evaluates every time-sensitive source/evidence edge plus the renewal window. An old READY receipt therefore cannot be replayed indefinitely. Currentness is truth-narrowed to a trusted Python interpreter/stdlib clock boundary; this package does not claim an unforgeable hardware or remote time source.

## Strictness

- strict UTF-8 JSON with duplicate-key, non-finite-number, over-large-integer runtime failure, and surrogate-text rejection;
- exact field sets and exact booleans/integers (no `true == 1` aliasing);
- unique IDs and source/evidence binding;
- future/expired evidence fails closed;
- blocking open security/data gaps hold review;
- tampered input, packet, receipt, or authority bits fail verification;
- output files are create-exclusive; input files must be regular non-symlinks.

## CLI

```bash
python -m revenue.pilot_renewal_expansion_gate.gate compile \
  revenue/pilot_renewal_expansion_gate/example.json /tmp/renewal-demo

python -m revenue.pilot_renewal_expansion_gate.gate verify \
  revenue/pilot_renewal_expansion_gate/example.json \
  /tmp/renewal-demo/packet.json /tmp/renewal-demo/receipt.json
```

The checked-in example is synthetic evidence only.

## Test

```bash
python -m unittest -v revenue.pilot_renewal_expansion_gate.test_gate
python -O -m unittest -v revenue.pilot_renewal_expansion_gate.test_gate
python -m py_compile revenue/pilot_renewal_expansion_gate/gate.py revenue/pilot_renewal_expansion_gate/test_gate.py
```

## Authority ceiling

This module never sends email/DM/form traffic, acquires a Muse lease, signs or accepts a contract, establishes buyer acceptance, approves renewal/expansion, creates an invoice, establishes payment/cash/revenue, deploys software, schedules work, or mutates CRM/provider state. Every corresponding authority bit is hard-false in packet and receipt output.
