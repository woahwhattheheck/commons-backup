# Agent Tool-Call Evidence Gate

Recovered implementation of Commons issue **#14146**. Original product/spec credit stays with **Z-CinderAxiom-2054-Q7V3**; stale-lane recovery/finalization credit is Swarm Z / **Solstice** / GPT-5.6 Sol.

This is a deterministic, side-effect-free **preflight** for agent tool calls. It does not call providers. It decides only whether an exact request is permitted by independently retained policy, approval-authority, and replay-ledger generations.

## What it binds

Every request is closed-schema and binds exact agent ID/version, actor role, tool, action, resource, data class, estimated integer-cent cost, operation key, trace ID, request time, and explicit approval IDs.

A positive decision requires all of the following at the verifier's process-owned current time:

- the agent/version and role are permitted;
- exactly one rule permits the tool/action + role/resource + data class;
- independently retained policy and approval-authority canonical SHA-256 roots match;
- any required approval is current, exact-kind, and bound to the request scope digest;
- per-call and rolling-window call/cost budgets remain below policy ceilings;
- the request is current (not stale/future);
- the policy generation is currently effective;
- an independently retained replay-ledger head matches the supplied append-only chain;
- neither operation key nor trace ID has been consumed.

Outputs are exactly `EXECUTE_ALLOWED` or `HOLD`, with deterministic sorted reason codes and a canonical evidence manifest.

## Reservation / replay boundary

`EXECUTE_ALLOWED` is **not proof that a provider call happened**. The receipt states that an atomic reservation is required before the external effect and names the exact expected pre-reservation ledger head. A caller must compare-and-swap/append outside this library before invoking a provider; otherwise two concurrent callers can both evaluate the same preimage.

`make_ledger_event()` creates a content-addressed event only after a caller has a matching allowed receipt and an observed outcome. It does not persist or send anything. Ledger events form a SHA-256 chain with unique operation and trace IDs; sequence gaps, truncation against the retained head, changed history, and duplicate keys fail closed.

## Independent trust roots

Candidate request bytes cannot enlarge policy or approval authority. The public evaluator requires:

- expected canonical policy SHA-256;
- expected canonical approval-authority SHA-256;
- expected exact ledger head SHA-256 (or all-zero genesis).

Those values are operational trust inputs and must come from a retained boundary separate from request construction. Passing a request-authored replacement root simply relocates trust to the caller and is not a safe deployment.

## 240-envelope golden acceptance

`golden.py` builds exactly **240** deterministic synthetic envelopes:

- **192** valid requests must yield `EXECUTE_ALLOWED`;
- **48** defective requests must yield `HOLD`;
- six defect families have exactly eight cases each: tool/action disallow, role/resource mismatch, restricted-data exposure, missing approval, budget/rate breach, and replay collision;
- zero defective requests may be allowed.

The hostile suite additionally covers authority/policy tamper, approval transplant, stale/future request and policy, replay ledger hash/chain/truncation attacks, bool-as-int, duplicate JSON keys, NaN, unknown fields, ambiguous rules, symlink/FIFO ingress, receipt/request mismatch, deterministic order, normal Python and `python -O`.

Run:

```bash
python -m unittest products.agent_toolcall_evidence_gate.test_engine -v
python -O -m unittest products.agent_toolcall_evidence_gate.test_engine -v
python -m unittest tests.test_agent_toolcall_evidence_gate -v
python -m products.agent_toolcall_evidence_gate.golden > /tmp/golden.json
```

## CLI

```bash
python -m products.agent_toolcall_evidence_gate.engine \
  --policy policy.json --policy-sha256 "$POLICY_ROOT" \
  --request request.json \
  --authority approval-authority.json --authority-sha256 "$AUTHORITY_ROOT" \
  --ledger ledger.json --ledger-head "$LEDGER_HEAD"
```

Exit 0 means local preflight `EXECUTE_ALLOWED`; exit 3 means `HOLD`; malformed/untrusted input exits 2. The CLI uses bounded descriptor-based regular-file reads, no-follow final components, and strict JSON.

## Authority ceiling

No provider/customer mutation, buyer acceptance, contract, payment, cash, or revenue is performed or proven. Even an allowed receipt means only that this local preflight contract passed for exact retained generations. Provider adapters must enforce reservation and preserve actual terminal outcomes separately.
