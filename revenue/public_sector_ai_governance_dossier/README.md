# Public-sector AI governance control dossier

A buyer-neutral, standard-library-only compiler for **GenAI + Operational-AI governance evidence** in public-sector and critical-infrastructure environments.

It is deliberately different from [`tools/proposal_gate`](../../tools/proposal_gate/README.md). The proposal gate answers **“is the bid packet evidence-complete?”** This tool answers **“what AI use cases exist, how much control intensity do they require, which controls have acceptable evidence, and what remains on hold?”** A live pursuit can use both: this dossier supplies governance work-product evidence; the proposal gate controls proposal completeness.

## Safety / authority boundary

The compiler never grants permission to deploy, publish, procure, sign, or make a legal/compliance assertion. `CONTROL_READY_OWNER_DECISION` means only that every control required by this deterministic model has appropriately scoped evidence. Owner, security, legal/policy, and independent-review authorities stay separate.

Control tiers are an **internal control-intensity heuristic**, not a statutory or regulatory risk classification.

## What it models

Each use case records:

- `generative` vs `operational` AI;
- discovery/evaluation/pilot/production/retired stage;
- advisory → recommendation → automated decision authority;
- administrative/service/infrastructure/safety operational impact;
- recoverability;
- public-record, sensitive, regulated, and operational-critical data classes;
- external-publication and shadow-AI flags;
- exact vendor/model identity.

The compiler derives a tier and required controls. Conditional controls cover public records, sensitive/regulated data, external publication, shadow AI, operational fallback, automated override, safety hazards, and production release.

Evidence is accepted only when it is:

1. scoped to the use case (`use_case_ids` or `*`),
2. bound to the exact control,
3. `verified`, and
4. supplied by an authority accepted for that control.

For example, an owner note cannot satisfy `PUBLIC_RECORDS_REVIEW`; that control requires `legal_approved` evidence. High-impact `INDEPENDENT_VALIDATION` requires independent-review evidence. This separation keeps self-consistent paperwork from silently becoming authority.

## Evidence privacy

Input evidence may contain local/private fields such as `private_notes`. Output intentionally emits metadata only: ID, status, authority, reference, digest, scope, and control IDs. Payloads/private notes never enter the generated dossier.

## CLI

```bash
python revenue/public_sector_ai_governance_dossier/ai_governance_dossier.py compile \
  --input revenue/public_sector_ai_governance_dossier/examples/municipal_wastewater_synthetic.json \
  --json-out /tmp/ai-governance.json \
  --markdown-out /tmp/ai-governance.md

python revenue/public_sector_ai_governance_dossier/ai_governance_dossier.py verify \
  --input revenue/public_sector_ai_governance_dossier/examples/municipal_wastewater_synthetic.json \
  --dossier /tmp/ai-governance.json
```

Add `--fail-on-hold` to `compile` when a pipeline should exit `2` while any required control lacks accepted evidence.

## Synthetic municipal/wastewater example

The included example is intentionally **not production-ready**. It demonstrates three common policy surfaces without claiming anything about a real buyer:

- internal GenAI drafting where outputs can become public records;
- operational anomaly recommendations over critical plant telemetry;
- discovered/shadow meeting summarization using sensitive material.

It exists to exercise governance mechanics, not to represent legal requirements or a customer deployment.

## Tests

```bash
python -m py_compile revenue/public_sector_ai_governance_dossier/ai_governance_dossier.py
python -m unittest discover -s revenue/public_sector_ai_governance_dossier -p 'test_*.py' -v
```

The hostile suite covers deterministic output, evidence redaction, public-record authority mismatch, tier escalation, safety-critical controls, shadow-AI disposition, vendor/model identity binding, strict scalar types, tamper detection, CLI round-trip, and fail-on-hold behavior.
