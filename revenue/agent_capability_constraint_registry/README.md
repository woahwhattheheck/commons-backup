# Agent Capability & Constraint Registry

This directory is a **buyer-neutral, offline, execution-free evidence product**. It compiles a strict census of agent seats/workstreams into deterministic JSON and Markdown projections plus a content-addressed receipt.

The commercial trigger was a release-gated multi-partner agent-capability census concept. This carrier deliberately contains **no prospect-specific branding, data, credentials, endpoint, deployment, or outreach logic**.

## What it does

Each source record binds an `agent_id` + integer `revision` to a workstream, provider/model-or-harness declaration, measured capabilities with exact evidence references + SHA-256 hashes, declared constraints with source references/hashes/timestamps, required and available tools, owner-decision state, and explicit blocking reasons. The top-level `evidence_max_age_seconds` binds an explicit freshness window against `generated_at`; future or stale capability/constraint evidence fails closed.

Compilation produces exactly one status per record:

- `HOLD` — explicit blocker, failed measured capability, denied constraint/owner verdict, or any request to execute external effects;
- `OWNER_DECISION` — an owner verdict or constraint decision is still pending;
- `TOOLING_NEEDED` — required tooling is absent or a declared constraint names a tooling need;
- `READY` — none of the above registry conditions apply.

`READY` is **not execution authority**. The result hard-codes every external authority bit false. The registry never runs tools, calls models, deploys software, elevates access, sends messages, spends money, or changes external state.

## Fail-closed input contract

The loader rejects duplicate JSON keys, UTF-8 BOMs, floats, NaN/Infinity, unknown/missing fields, bool-as-int revisions/minutes/freshness windows, malformed hashes/timestamps, future or stale evidence, duplicate agent+revision identities, duplicate capability/constraint names, incomplete evidence provenance and invalid enum values.

The compiler canonicalizes ordering, emits byte-stable `registry.json` + `registry.md`, and emits `receipt.json` binding the normalized input, JSON projection and Markdown projection. Verification recompiles from source and requires all three output files to match byte-for-byte.

## Frozen acceptance

`fixture_12_agents.json` is a synthetic fixture with the required distribution:

- `READY=5`
- `TOOLING_NEEDED=3`
- `OWNER_DECISION=2`
- `HOLD=2`

Run from repository root:

```bash
PYTHONPATH=. python3 -m unittest -v revenue.agent_capability_constraint_registry.test_registry
PYTHONPATH=. python3 -O -m unittest -v revenue.agent_capability_constraint_registry.test_registry
python3 revenue/agent_capability_constraint_registry/acceptance.py
python3 -O revenue/agent_capability_constraint_registry/acceptance.py
```

Compile and verify a source census:

```bash
python3 revenue/agent_capability_constraint_registry/cli.py compile \
  --input revenue/agent_capability_constraint_registry/fixture_12_agents.json \
  --out-dir /tmp/agent-registry-output

python3 revenue/agent_capability_constraint_registry/cli.py verify \
  --input revenue/agent_capability_constraint_registry/fixture_12_agents.json \
  --out-dir /tmp/agent-registry-output
```

## Truth boundary

This is a deterministic evidence/census utility, not a benchmark, vendor ranking, policy engine, orchestrator, deployment controller, authorization system, monitoring daemon, or buyer acceptance. It makes no customer, contract, payment, award, deployment, production-readiness, security-certification, or revenue claim.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
