# Agentic GxP Lineage Evidence Gate

This package is an offline, buyer-neutral validation sidecar for generated manufacturing review artifacts such as deviations, PQRs, and batch-review summaries. It was built from the bounded Aizon Agentic Studio / Unify lineage-proof demand, but it contains no Aizon data, credentials, customer configuration, or production integration.

## Authority boundary

The strongest positive state is:

`QA_REVIEW_READY_EVIDENCE_ONLY`

That means the supplied synthetic/offline evidence is internally coherent under the supplied policy and can move to a human QA review step. It **does not** mean batch release, QA disposition, validated-system status, GAMP/GxP certification, CFR 21 Part 11 compliance, production publication, regulatory approval, buyer acceptance, contract, payment, or recognized revenue.

Every receipt hard-codes all of these as false:

- `source_authenticity_verified`
- `production_release_authorized`
- `qa_disposition_authorized`
- `regulatory_compliance_certified`
- `buyer_acceptance_inferred`
- `recognized_revenue_inferred`

## What v1 binds

Before an artifact is evidence-ready for QA review, the gate binds:

- complete source dataset/snapshot identities and SHA-256 digests;
- approved dataset schema identity/version/hash;
- bounded batch context using an approved ISA-88/95-style context standard;
- artifact identity/type/hash;
- exact model identity/version/hash;
- exact tool identities/versions/hashes;
- exact prompt-policy identity/version/hash;
- query and result hashes;
- actor identity and role;
- intended-use risk class and purpose;
- approved change-control reference that predates execution;
- explicit human review after execution, including authorized reviewer role, four-eyes separation, and exact artifact-hash binding;
- content-addressed event identity, exact replay collapse, and same-case changed-payload conflict quarantine;
- trusted-time freshness for both case capture and every source snapshot, complete batch capture, deterministic manifest/receipt hashes, and a verifier that re-evaluates the bound evidence rather than trusting self-rehashed semantics.

Unknown/extra fields, malformed hashes, non-UTC timestamps, future capture, duplicate source identities, duplicate tool IDs, non-monotonic execution/approval timing, and oversized/noncanonical JSON fail before a receipt can be emitted.

## Synthetic acceptance fixture

`fixture.py` builds a deterministic 120-case corpus:

- 96 evidence-ready cases;
- 24 held cases;
- exactly 3 of each of 8 synthetic fault classes:
  - incomplete source snapshot;
  - unapproved dataset version/hash;
  - unapproved batch-context standard;
  - unapproved model version/hash;
  - unapproved tool version/hash;
  - unapproved prompt-policy version/hash;
  - non-approved change-control state;
  - human approval bound to the wrong artifact hash.

The fixture is synthetic and is not a statement about any buyer environment.

## Run

From the repository root:

```bash
python -m unittest discover -s revenue/agentic_gxp_lineage_gate -t . -p 'test_gate*.py' -v
python -O -m unittest discover -s revenue/agentic_gxp_lineage_gate -t . -p 'test_gate*.py' -v
python -m py_compile \
  revenue/agentic_gxp_lineage_gate/codec.py \
  revenue/agentic_gxp_lineage_gate/case.py \
  revenue/agentic_gxp_lineage_gate/rules.py \
  revenue/agentic_gxp_lineage_gate/gate.py \
  revenue/agentic_gxp_lineage_gate/fixture.py \
  revenue/agentic_gxp_lineage_gate/test_gate.py \
  revenue/agentic_gxp_lineage_gate/test_gate_hostile.py \
  revenue/agentic_gxp_lineage_gate/test_gate_peer_invariant.py
```

Minimal API:

```python
from revenue.agentic_gxp_lineage_gate import evaluate, verify

result = evaluate(policy, evidence_batch, evaluated_at="2026-09-13T09:16:00Z")
assert verify(result, policy=policy, batch=evidence_batch)
```

The caller owns policy approval, source authenticity, human identity/authority, production controls, validation strategy, and every real-world QA/regulatory decision. A supplied source snapshot digest is bound into lineage; this gate does not independently authenticate the source bytes behind that digest. This package only checks the evidence contract it is given.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
