# Procurement Runway + Partner-Capacity Gate

Issue: #15335  
Operation: `PROCUREMENT-RUNWAY-AND-PARTNER-CAPACITY-GATE-RECOVERY-ZCF0240-20260917`

This package prevents technically attractive procurement pursuits from consuming sales attention when the calendar or partner-capacity evidence does not support them. It compiles retained opportunity facts into four deliberately bounded states:

- `READY` — at least one partner has **explicit public capacity timing evidence** with no known timing conflict.
- `ASK_CAPACITY_FIRST` — partner capability is evidenced, but public availability is not. Ask capacity before treating the lane as executable.
- `TOO_LATE` — the proposal deadline has passed/today, or every explicitly evidenced partner timing misses a known delivery target.
- `UNKNOWN` — the opportunity has no evidence-bound plausible partner.

It never infers capacity from capability, headcount, market presence, or generic marketing copy.

## Authority ceiling

Every compiled document and every opportunity hard-carries:

- `external_send_authorized=false`
- `provider_mutation_authorized=false`
- `submission_authorized=false`
- `payment_or_revenue_inferred=false`

A contact state of `ELIGIBLE_FOR_SEPARATE_MUSE_ELECTION_ONLY` is **not send authority**. DNR, inbound-only, relationship-unknown, and collision states remain explicit holds. External contact still requires current provider history, Slack collision census, exact Muse recipient+intent election, immediate recensus, and one-send discipline.

## Evidence contract

Input schema: `procurement-runway-gate-input/v1`.

Every date fact used by the gate carries one or more HTTP(S) evidence URLs. Partner capability evidence is distinct from partner capacity evidence:

- `UNVERIFIED`: capability may be public, but availability is not. Timing fields are forbidden.
- `EXPLICIT_EARLIEST_DATE`: a source explicitly supports an earliest available date.
- `EXPLICIT_LEAD_TIME_DAYS`: a source explicitly supports lead time in days.

Explicit capacity modes require capacity-specific evidence URLs. The engine rejects attempts to smuggle timing into `UNVERIFIED`.

The gate evaluates an evidenced delivery target in this order: `start`, then `go_live`, then `anticipated_award + mandatory_delivery_window_days`. If no target is evidenced, explicit capacity can be `READY` only as “no known timing conflict”; the output states that limitation.

## Partner pairing and DNR

Only `READY` and `ASK_CAPACITY_FIRST` rows expose partner candidates, deterministically sorted and capped at three. `TOO_LATE` and `UNKNOWN` expose none.

Commercial workshare fields are explicit owner-retained facts: fixed fee, currency, scope, acceptance criteria, and exclusions. They are not buyer acceptance or booked revenue.

## CLI

```bash
out="$(mktemp -d)/runway"
python -m revenue.procurement_runway_gate compile \
  revenue/procurement_runway_gate/current_opportunities.json \
  --output-dir "$out"

python -m revenue.procurement_runway_gate verify \
  revenue/procurement_runway_gate/current_opportunities.json \
  --output-dir "$out"
```

`compile` creates the output directory exclusively and writes canonical `runway.json` plus a SHA-256 `receipt.json`. `verify` recompiles from the retained input and rejects output or receipt drift.

## Validation

```bash
python -m py_compile revenue/procurement_runway_gate/*.py
python -m unittest revenue.procurement_runway_gate.test_gate
python -O -m unittest revenue.procurement_runway_gate.test_gate
```

The hostile suite covers invented capacity, missing evidence, deadline boundaries, all-capacity-miss, DNR/collision dominance, deterministic three-partner cap, unknown keys, duplicate opportunities, tamper detection, authority flags, and create-exclusive publication.

## Current evidence packet

`current_opportunities.json` is a dated owner-review fixture, not a live procurement feed and not contact authority. It intentionally demonstrates:

- **SDCCD RFP 27-02 → Astute**: active proposal runway and strong first-party Oracle/higher-ed capability, but no public capacity timing; existing outreach makes the contact state `HOLD_DNR`.
- **States of Jersey DN827803 → Better**: openEHR/FHIR capability is first-party evidenced; public availability is not, so the state is `ASK_CAPACITY_FIRST`.
- **RCAP CRM assessment**: proposal deadline is bound from RCAP’s first-party RFP, but no partner is bound in this packet, so the state is `UNKNOWN`.

Refresh the retained URLs/dates and relationship/collision state before using this packet for a later decision.
