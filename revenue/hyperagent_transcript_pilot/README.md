# Hyperagent transcript pilot adapter

This directory is a **buyer-facing, offline acceptance artifact** for the paid pilot already proposed to Hyperagent. It is not the internal CALIPER Slack relay and it does not send anything to Slack, Gmail, Hyperagent, or another provider.

## What it proves

`adapter.py` normalizes three intentionally different synthetic backend schemas (`alpha`, `beta`, `gamma`) into one deterministic logical transcript model. The included 30-event fixture covers six runs and proves:

- 30 source events become exactly **6 logical transcripts / 30 logical messages**;
- replaying all 30 source events creates **0 new logical messages**;
- reusing a source event ID with changed semantics fails atomically;
- action artifacts are emitted only when approval matches the exact `run_id`, `action_id`, and `generation` and says `approved`;
- missing, foreign, stale, denied, or over-specified approvals emit **0 outbound artifacts**;
- caller-owned approval objects are detached before semantic hashing/authorization;
- clean projection is byte-identical even when source delivery order is reversed;
- the adapter imports no network/provider client.

## Run the acceptance proof

From the repository root:

```bash
python -m unittest revenue.hyperagent_transcript_pilot.test_adapter
python -m revenue.hyperagent_transcript_pilot.verify
```

`verify` prints one canonical JSON proof containing fixture and snapshot SHA-256 digests. It exits non-zero if the promised fixture counts, replay behavior, or byte determinism regress.

## Authority ceiling

This package produces **offline logical transcript artifacts only**. It does not possess buyer credentials, Slack credentials, deployment authority, routing authority, or human approval authority. A later buyer-controlled integration may consume these artifacts, but provider mutation must remain outside this package and behind the buyer's own authorization boundary.

The included fixture is synthetic. It contains no Hyperagent private events, secrets, customer content, or production identifiers.

## Commercial status

The artifact reduces fulfillment risk for an already-sent **paid pilot proposal**. It does **not** represent buyer acceptance, a signed contract, a funded pilot, an invoice, payment, cash, or recognized revenue. Those states require a later human/provider event and separate commercial authority.
