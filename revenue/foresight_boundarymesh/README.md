# Foresight AI Nodes — BoundaryMesh application carrier

Operation: `FORESIGHT-AI-NODES-COORDINATION-ACCOUNTABILITY-20260913`  
Owner seat: `Z-TheseusCipher-913844-L5N8` (`ZTC-L5N8`)  
Status: **TECHNICAL GO / SUBMISSION HOLD**

This directory is a truth-gated internal application carrier for Foresight Institute's 2026 **AI for Science & Safety Nodes** RFP, Track II **Coordination and accountability**, primary focus **Supercollaboration and decentralized alignment**.

The live public RFP explicitly asks for many-agent coordination, mutual monitoring/cross-checking, scalable verification, distributed oversight, and open protocols that can formalize or build on boundaries as coordination points. The application deadline is **2026-10-31 23:59 PDT**. Typical grants are **$30,000–$100,000**; Foresight states that the funded code, data, and outputs must be open-sourced. It accepts individuals, teams, nonprofits, and for-profits, with for-profits expected to motivate grant need, and strongly prioritizes active in-person Node contributors.

Official sources:
- https://foresight.org/grants/ai-science-safety-nodes-rfp/
- https://foresight.org/grants/ai-science-safety-nodes-rfp-coordination-and-accountability/
- https://airtable.com/appyVXc5SMPAvIKpP/pagp7takV26cG6JY1/form

## What is here

- `proposal.md` — full draft narrative and truth boundaries.
- `application_fields.md` — verified inputs, unresolved owner/form fields, and submission gate.
- `project_spec.json` — machine-readable research questions, primitives, deliverables, metrics, and success criteria.
- `evaluation_plan.md` — adversarial benchmark design, baselines, metrics, and negative-result rule.
- `protocol_v0.schema.json` — application-stage protocol sketch demonstrating feasibility, not a finished grant deliverable.
- `benchmark_seed.json` — 12 hostile/clean seed scenarios; explicitly not research results.
- `budget.json` — proposed $99,000 / 12-month budget, OWNER_CONFIRM.
- `opportunity.json` — sponsor/deadline/status/source ledger.
- `validate_pack.py` / `test_pack.py` — fail-closed consistency and truth-boundary checks.

## Hard boundaries

No grant was submitted, awarded, accepted, or recognized as revenue by this carrier. Applicant legal identity, Node attendance, travel, compensation, due-diligence disclosures, and final funding request are not inferred. Airtable's exact field labels were not visible to the available text crawler, so `application_fields.md` is intentionally marked partial and must be mapped to the live form before any submission.

Existing Commons/TitanMCP/customer/internal systems are not offered as grant deliverables. The proposal commits the **new grant-funded BoundaryMesh code, benchmark data, protocol specifications, and outputs** to open source while treating existing systems only as capability evidence/background work.

## Validate

```bash
cd revenue/foresight_boundarymesh
python validate_pack.py
python -m unittest -v test_pack.py
```

A passing carrier is still **not submission authority**. Final application requires the owner-confirm fields in `application_fields.md` plus a fresh read of the live RFP/form.
