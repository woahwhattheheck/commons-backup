# Bid deadline owner-action critical path

Carrier: `woahwhattheheck/commons#15144`

This module turns retained **authoritative solicitation, amendment, qualification, and dependency evidence** into a deterministic owner-action critical path. Its purpose is to keep a real bid from dying between “we found it” and “the owner completed the irreversible portal steps.”

It is downstream of solicitation/amendment ingestion. It does **not** scrape a portal, log in, sign, upload, submit, contact a buyer, recognize an award, invoice, charge, or recognize revenue.

## Truth boundary

`OWNER_ACTION_PLANNING_ONLY`

Every packet and receipt keeps these false:

- portal login authority
- signature authority
- upload authority
- submission authority
- buyer-contact authority
- buyer acceptance / award recognition
- invoice / payment / cash / revenue recognition

An `OWNER` action in the plan is an instruction to the human owner, not a permission or claim that the system can perform it.

`evaluation_time` is an owner-supplied evaluation clock. It is used for deterministic age/slack math and is never represented as buyer-authenticated time.

## Decision states

| State | Meaning |
| --- | --- |
| `READY_FOR_OWNER_ACTION` | Buyer-official deadline/amendment evidence is current, qualification is supported, dependencies are coherent, and every pending action still has non-negative latest-safe slack. |
| `HOLD_SOURCE` | Deadline evidence is nonofficial/stale or input is explicitly synthetic. |
| `HOLD_AMENDMENT` | Amendment evidence is nonofficial/stale/open/unknown. |
| `HOLD_QUALIFICATION` | Prime/partner qualification is not currently evidenced. |
| `HOLD_DEPENDENCY` | A pending dependency is blocked or has stale evidence. |
| `MISSED_WINDOW` | The buyer deadline passed **or** required remaining work/buffers make at least one pending action's latest-safe start already past. |
| `DNR` | The opportunity has a do-not-pursue state. |

## Scheduling model

The compiler validates an acyclic dependency DAG and schedules backward from:

`buyer deadline - final_submission_buffer_seconds`

For each pending action:

`latest_safe_start = earliest_successor_latest_start - duration - handoff_buffer`

Completed or not-applicable actions consume zero remaining duration/buffer. The packet records UTC latest-safe start/finish and slack seconds relative to the supplied evaluation time.

Each action also records `waiting_on_action_ids`: its direct prerequisites whose
state is neither `COMPLETE` nor `NOT_APPLICABLE`. The Markdown path shows the same
dependencies. Owner instructions select pending owner work with no remaining
prerequisites; if every pending owner action is waiting, the instructions name the
earliest handoff and its prerequisites instead of presenting it as ready to start.
When only non-owner work remains, they call for completing that work before the
final owner decision. These are dependency facts within the plan, not action
authority; source holds, deadline feasibility, and owner-only requirements still
apply.

Sensitive classes `PORTAL_LOGIN`, `SIGNATURE`, and `SUBMIT` are accepted only when `actor_class` is `OWNER`. This keeps the plan useful without granting the swarm credential/signature/submission authority.

## Input evidence

The strict JSON contract binds:

- solicitation ID, explicit `Z` UTC deadline, source timezone label, buyer-official source digest + observed time;
- amendment state plus buyer-official source digest + observed time;
- qualification/workshare state, source digest, gaps;
- final submission buffer;
- action DAG with actor/action class, state, duration, handoff buffer, dependencies, and source digests/times.

No credential/password/token/session-cookie fields exist. Unknown keys fail closed.

The parser also rejects duplicate JSON keys, floats/non-finite values, boolean-as-integer values, invalid/naive timestamps, future source observations, duplicate action IDs/dependencies, missing dependencies, self-dependencies, and cycles.

## CLI

```bash
python -m revenue.bid_deadline_critical_path.engine compile \
  input.json \
  --packet critical-path.packet.json \
  --markdown critical-path.md \
  --receipt critical-path.receipt.json

python -m revenue.bid_deadline_critical_path.engine verify \
  input.json critical-path.packet.json critical-path.md critical-path.receipt.json
```

Exact verification prints:

```text
EXACT_CRITICAL_PATH_MATCH
```

Output publication is create-exclusive: all destinations are preflighted, bytes are staged and `fsync`'d, hard-linked into place, and rolled back if publication fails partway.

## Synthetic rehearsal

`demo/synthetic_bid.json` is intentionally marked `fixture: true` and uses synthetic source authority. It must compile to:

```text
HOLD_SOURCE
```

and its exact bundle must still verify as:

```text
EXACT_CRITICAL_PATH_MATCH
```

The demo does not represent a real solicitation, deadline, buyer, submission, award, payment, or revenue.

Run the retained rehearsal through the ordinary compiler and verifier, using new
output paths:

```bash
python -m revenue.bid_deadline_critical_path.engine compile \
  revenue/bid_deadline_critical_path/demo/synthetic_bid.json \
  --packet synthetic-bid.packet.json \
  --markdown synthetic-bid.md \
  --receipt synthetic-bid.receipt.json
python -m revenue.bid_deadline_critical_path.engine verify \
  revenue/bid_deadline_critical_path/demo/synthetic_bid.json \
  synthetic-bid.packet.json synthetic-bid.md synthetic-bid.receipt.json
```
