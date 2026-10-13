# Copilot Agent Training Evidence Gate

A deterministic, dependency-free evidence compiler for a Copilot-agent training engagement. It compiles supplied evidence without inventing credentials, references, partner facts, or buyer acceptance.

## What it records

The package keeps four evidence classes separate:

1. **Proposal / teaming gate** — named trainer, delivery-window coverage, two comparable engagements, two references, explicit subcontract role, commercial role split, and sample-agreement availability.
2. **Governance gate** — approved data sources, least privilege, human escalation, logging/audit, and retention/deletion.
3. **Agent evaluation gate** — five scored dimensions (`task_success`, `groundedness`, `permission_boundaries`, `safe_failure`, `human_handoff`), retained evidence references, and an observed result.
4. **Adoption / outcome gate** — invited/trained staff, builders, functioning agents, and evaluated agents, including the buyer outcome of at least one functioning agent.

`compile_delivery_pack()` returns `HOLD` unless every gate is satisfied. It also emits a canonical SHA-256 receipt so identical evidence produces an identical receipt.

## Claims boundary

This code does **not**:

- claim Microsoft credentials, partner status, client history, or references;
- validate a Microsoft tenant or production deployment;
- make legal, procurement, privacy, accessibility, or security-compliance conclusions;
- independently verify a counterparty's statements;
- submit a bid or contact the buyer;
- claim partnership, award, acceptance, payment, or booked revenue.

It compiles supplied evidence and exposes missing proof.

## Run

From the repository root:

```bash
python -m commercial.legal_aid_copilot_agents.cli \
  commercial/legal_aid_copilot_agents/example_hold.json \
  --json-out /tmp/legal-aid-pack.json \
  --markdown-out /tmp/legal-aid-pack.md
```

Exit code is `0` only for `ACCEPTANCE_READY`; a gated `HOLD` returns `2`.

The included example intentionally remains `HOLD` because it contains no fabricated partner credentials or references.

## Test

```bash
python -m unittest test_legal_aid_copilot_agents -v
```

Tests cover truth-preserving proposal holds, delivery-window mismatch, governance gaps, rubric validation, duplicate case identifiers, functioning-agent outcomes, deterministic receipts, and a complete synthetic acceptance-ready path. Synthetic fixtures demonstrate software behavior only.
