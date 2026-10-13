# AgentWitness

**AgentWitness** is a one-event/one-claim trust rail for concurrent AI agents, built for the Monad Metropolis **Trust, Identity & AI Infrastructure** track.

Parallel agents often coordinate through systems that are eventually consistent: queues, chat, databases, provider search, or human-readable work feeds. Two workers can both observe “nobody acted yet” and both cross an irreversible boundary before either sees the other. AgentWitness moves that race to one atomic on-chain slot.

## Core idea

A triggering external event is converted to a deterministic `event_key` from a tiny closed schema. Agents may keep their private draft, customer data, prompt, and provider payload off-chain. They publish only:

- the event key;
- a hash of the private intent;
- the winning claimant address;
- a hash of the observed outcome;
- an optional reconciliation hash when the first provider result was unknown.

The contract accepts the **first** claim for an event key and rejects every later claimant. Changing the worker, draft, price, route, or retry label does not change the event key. A genuinely new provider/human event does.

This is not a generic transaction executor and never handles user funds.

## Why this matters

The primitive generalizes to any side effect where duplicate execution is expensive:

- sending a human reply twice;
- charging or paying twice;
- deploying the same release twice;
- claiming the same work item twice;
- firing an expensive external job twice.

The chain is an independent arbitration surface. The contract does **not** prove that a provider send succeeded, a buyer accepted, or money settled; those are explicit outcome states with separate evidence hashes.

## Event schema v1

Exactly five fields are permitted:

```json
{
  "version": "agentwitness-event-v1",
  "network": "monad",
  "namespace": "demo/outbound",
  "provider": "gmail",
  "event_id": "synthetic-human-reply-0001"
}
```

`event_key = SHA256("agentwitness:event:v1\\0" || canonical_json(event))`

`network`, `namespace`, and `provider` are strict lowercase tokens. `event_id` is an exact durable external identifier. No free-form subject, body, recipient, price, worker ID, secret, credential, or user content belongs in the schema.

## State machine

```text
UNCLAIMED
   | claim(event_key, intent_hash)     first address wins atomically
   v
CLAIMED
   | finalize(...)
   +--> COMPLETED
   +--> REJECTED
   +--> HELD
   +--> OUTCOME_UNKNOWN -- reconcile(...) --> COMPLETED | REJECTED | HELD
```

A known outcome cannot be overwritten. `OUTCOME_UNKNOWN` is the only state that permits one reconciliation transition.

## Run the reference tests

No third-party Python packages are required.

```bash
cd competitions/monad_metropolis_agentwitness
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python demo/race_demo.py
python -m py_compile agentwitness/*.py demo/*.py tests/*.py
```

The race demo starts 64 synthetic workers on one event and requires exactly one winner.

## Reference CLI

The CLI uses only the Python standard library. A path of `-` reads stdin so private payloads do not need to appear in shell arguments.

```bash
python -m agentwitness.cli event-key examples/gmail_reply_event.json
python -m agentwitness.cli canonical-event examples/gmail_reply_event.json
printf %s "private draft" | python -m agentwitness.cli intent-hash -
printf %s "provider evidence" | python -m agentwitness.cli outcome-hash -
```

`schema/event-v1.schema.json` and `schema/receipt-v1.schema.json` are closed JSON Schemas mirroring the versioned public surfaces. The Python implementation remains the normative byte-level canonicalizer because JSON Schema alone does not define canonical serialization or duplicate-key rejection.

## Repository layout

- `contracts/AgentWitnessRegistry.sol` — minimal on-chain state machine.
- `agentwitness/core.py` — deterministic strict encoder/verifier and executable in-memory contract model.
- `tests/test_agentwitness.py` — hostile and race coverage.
- `demo/race_demo.py` — visible same-event race collapse.
- `THREAT_MODEL.md` — security/trust boundaries.
- `submission/DRAFT.md` — competition narrative and remaining deployment/submission gates.

## Current external state

Source carrier only. No wallet was created/imported; no key was handled; no Monad transaction was signed; no contract was deployed; no hackathon registration or submission is claimed; no prize, award, payment, or recognized revenue is claimed.

Competition carrier: Commons issue `#14176` / operation `MONAD-METROPOLIS-AGENTWITNESS-ZGAH8C3-20260913`.
