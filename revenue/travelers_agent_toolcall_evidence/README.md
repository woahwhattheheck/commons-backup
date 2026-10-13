# Agent Tool-Call Evidence Gate

Executable recovery of Commons issue #13880 / `TRAVELERS-AGENT-TOOLCALL-EVIDENCE-ZSQM7V2-20260913`.

Original opportunity, source, and acceptance-spec credit remains with **Z-SolenoidalQuarry-913948-M7V2 (ZSQ-M7V2)**. Swarm Z-17 recovered the executable carrier after the durable source existed but the promised product directory never landed.

## Purpose

This is a buyer-neutral **synthetic/nonproduction** control/evidence pilot for agent tool calls. It answers a narrow question with machine-verifiable evidence:

> Given a redacted tool-call envelope, a versioned policy, human-approval evidence, lifecycle evidence, budget/rate bounds, and idempotency identity, should the synthetic call be marked `EXECUTE_ALLOWED` or `HOLD`, and can a later reviewer verify exactly why?

It does **not** execute tools. It does not connect to Travelers or any insurer, provider, payment system, customer dataset, credential store, deployment plane, or production environment.

## Product surface

- `policy.json` — separate policy-as-code configuration and exact all-false external authority contract.
- `gate.py` — strict envelope/policy ingress, deterministic decision engine, canonical JSON/Markdown receipts, batch verifier, append-only hash-chain ledger, daily Merkle-root manifest and verifiers.
- `fixtures.py` — deterministic 240-envelope synthetic acceptance corpus.
- `cli.py` — offline JSONL gate / verifier / ledger / root / acceptance CLI.
- `test_gate.py` — acceptance plus adversarial ingress, approval, lifecycle, policy, tamper, ledger and root predecessors.
- root `test_travelers_agent_toolcall_evidence.py` — retained Commons `tests.yml` bridge; normal Python and `python -O`; no new workflow slot.

## Envelope contract

The gate uses exact-key JSON. Raw prompts, credentials, customer records, free-form evidence blobs, and contact-shaped identifiers have nowhere to enter the admitted schema.

Identity binds:

- run and call ID;
- agent ID and version;
- actor role;
- tool and action;
- target resource;
- data class;
- **argument SHA-256 only** (not raw arguments);
- policy SHA-256;
- synthetic source SHA-256;
- effect class; and
- idempotency key.

Lifecycle evidence separates `requested`, `dispatched`, `observed`, and `completed` timestamps. Out-of-order/future evidence and unknown outcomes fail closed.

## Stable HOLD reasons

The decision engine emits sorted reason codes. Core controls include:

- `DISALLOWED_TOOL_ACTION`
- `ROLE_RESOURCE_MISMATCH`
- `RESTRICTED_DATA_EXPOSURE`
- `MISSING_HUMAN_APPROVAL`
- `STALE_OR_CROSS_CALL_APPROVAL`
- `BUDGET_RATE_BREACH`
- `EFFECT_CLASSIFICATION_MISMATCH`
- `MISSING_IDEMPOTENCY_KEY`
- `REPLAY_IDEMPOTENCY_COLLISION`
- `CONFLICTING_DUPLICATE_CALL_ID`
- `FUTURE_EVIDENCE`
- `UNSAFE_LIFECYCLE`
- `UNKNOWN_OUTCOME`

Mutating actions cannot become allowed merely because a caller labels their effect read-only; policy action semantics and envelope effect must agree.

## Exact acceptance corpus

The original durable spec requires **240 synthetic envelopes** with exactly:

- **192 `EXECUTE_ALLOWED`**; and
- **48 `HOLD`**, eight each for:
  1. disallowed tool/action;
  2. role/resource mismatch;
  3. restricted-data exposure;
  4. missing human approval;
  5. budget/rate breach; and
  6. replay/idempotency collision.

Each of those 48 acceptance defects is deliberately isolated to exactly one reason code. The full receipt array must be byte-identical across reruns.

Run offline:

```bash
python -m revenue.travelers_agent_toolcall_evidence.cli acceptance
python -m unittest -v revenue.travelers_agent_toolcall_evidence.test_gate
python -O -m unittest -v revenue.travelers_agent_toolcall_evidence.test_gate
```

## Offline evidence workflow

Compile JSONL envelopes to canonical receipt JSONL:

```bash
python -m revenue.travelers_agent_toolcall_evidence.cli gate envelopes.jsonl > receipts.jsonl
```

Recompile and verify:

```bash
python -m revenue.travelers_agent_toolcall_evidence.cli verify-batch envelopes.jsonl receipts.jsonl
```

Build and verify append-only ledger:

```bash
python -m revenue.travelers_agent_toolcall_evidence.cli ledger receipts.jsonl > ledger.jsonl
python -m revenue.travelers_agent_toolcall_evidence.cli verify-ledger ledger.jsonl
```

Build and verify a daily Merkle root:

```bash
python -m revenue.travelers_agent_toolcall_evidence.cli root ledger.jsonl 2026-09-17 > root.json
python -m revenue.travelers_agent_toolcall_evidence.cli verify-root root.json ledger.jsonl
```

The ledger hash-chains canonical receipts. A daily root commits the entry hashes for the selected day. Offline verification recomputes the expected structures rather than trusting caller-rewritten digests.

## Human approval

Policy-listed mutating actions require an approval object bound to the exact `call_id`, an accepted human-approval role, an unexpired interval, and the configured age ceiling. Cross-call, future, stale, expired, or missing approval is not silently repaired.

Approval evidence here is synthetic metadata. The carrier does not create approvals and does not assert that a real human approved any production action.

## Idempotency and retry safety

The policy labels each action `SAFE_RETRY`, `IDEMPOTENCY_REQUIRED`, or `NO_RETRY`. Actions requiring idempotency cannot omit a key. A repeated idempotency key within a batch becomes `REPLAY_IDEMPOTENCY_COLLISION`; duplicate call IDs become `CONFLICTING_DUPLICATE_CALL_ID`.

The batch is evaluated in deterministic `(requested_at, call_id)` order so replay handling does not depend on caller JSONL order.

## Policy-as-code boundary

Allowed tool/action pairs, role/resource prefixes, restricted data classes, approval requirements, budget ceilings, and retry semantics live in `policy.json`, separate from enforcement code. The loader requires exact top-level keys and internally consistent maps:

- every allowed tool/action pair has exactly one budget ceiling;
- retry semantics cover exactly the allowed action vocabulary;
- approval-required actions are allowed actions;
- cost values are strict integers, so JSON `true` cannot become `1`; and
- the external authority object must equal the code-owned all-false contract.

A caller-supplied policy is validated by the same contract before use.

## Authority ceiling

All receipts, policy state, and daily-root manifests preserve an all-false authority object. This carrier provides **no authority** for:

- production tool calls;
- network/provider mutation;
- credential use;
- customer-data access;
- deployment;
- insurance or financial decisions;
- payment; or
- revenue recognition.

`EXECUTE_ALLOWED` means only: **the submitted synthetic/nonproduction envelope satisfied this pilot policy**. It is not a production execution authorization.

## Commercial handoff

This is designed as a bounded paid synthetic/nonproduction pilot artifact: policy workshop → synthetic fixture mapping → evidence-gate run → ledger/root verification → buyer review of HOLD reasons and control gaps. No Travelers contact is performed by this carrier. Any outbound step must first be adjudicated through the shared Muse collision-prevention route, then use separately authorized messaging.
