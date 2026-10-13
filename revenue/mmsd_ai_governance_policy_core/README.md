# MMSD AI Governance Policy Core

Deterministic AI-inventory, risk-tier, and control-evidence workbench for the Madison Metropolitan Sewerage District Comprehensive Artificial Intelligence (AI) Use and Governance Policy RFP.

This is an **RFP-supporting technical/governance component**, not a proposal submission, legal opinion, adopted District policy, operational authorization, procurement approval, security assessment, records-disposition decision, or instruction to start/stop an AI or wastewater-control system.

## RFP fit

The District's published scope calls for an actionable governance policy spanning:

- Generative AI used in administrative and drafting workflows;
- Operational AI used in wastewater treatment, infrastructure analytics, and plant upgrades;
- AI inventory / shadow-AI discovery;
- operational risk tiers and employee-use standards;
- data security, sovereignty, public-records and retention controls;
- vendor/procurement review;
- incident response;
- staff AI literacy and training.

`policy_assessment.py` supplies a reproducible evidence layer underneath that consulting work. It does not replace stakeholder interviews, legal review, OT/SCADA engineering judgment, cybersecurity testing, public-records counsel, or District adoption authority.

## Contract

Input contract: `mmsd-ai-governance-assessment/v1`.

Each inventory item binds:

- stable system ID and business-facing name;
- `GENERATIVE` vs `OPERATIONAL`;
- lifecycle: discovery, pilot, production, or procurement;
- assistive, recommendation, or autonomous behavior;
- data classes and impact areas;
- vendor / connectivity / public-output facts;
- whether the system can change operational state;
- accountable owner role.

Control evidence is supplied separately and must bind the exact canonical inventory SHA-256. Evidence records include an evidence ID, trusted timestamp, and explicit booleans for controls such as ownership, approved use case, data classification, records retention/export, vendor terms, security review, incident response, logging, human oversight, output validation, change management, OT safety review, rollback/fail-safe, training, and data residency.

## Risk tiers

The classifier is intentionally conservative and deterministic:

| Tier | Intended review meaning |
| --- | --- |
| `T1_LOW` | bounded internal assistive use with no elevated data/operational/public impact |
| `T2_MODERATE` | vendor/network/public-record/public-output/production or recommendation exposure |
| `T3_HIGH` | sensitive/security/critical-infrastructure data, consequential decisions, autonomous behavior, or operational-state authority |
| `T4_CRITICAL` | operational AI touching wastewater/safety/infrastructure with actuation, autonomy, or direct operational-state capability |

The tier is **inherent review risk**, not a legal label and not an approval decision.

## Fail-closed properties

The compiler rejects:

- unknown input/system/control fields;
- duplicate system IDs, evidence IDs, or control rows;
- control evidence bound to a different inventory digest;
- evidence for systems absent from the inventory;
- caller-smuggled evaluation timestamps;
- future or non-canonical timestamps;
- duplicate JSON keys, NaN, floats, and non-canonical scalar shapes;
- duplicate enum values;
- secret-shaped strings such as bearer tokens, private keys, and API-key material;
- tampered result receipts.

Inventory order and evidence order do not change the canonical result.

## Output

The strongest result state is `ASSESSMENT_COMPLETE`, which means only that the declared required control set has evidence for every supplied inventory item. Missing evidence or false required controls produce `CONTROL_GAPS_PRESENT`.

Every result hard-codes these authorities to `false`:

- legal conclusion;
- policy adoption;
- procurement approval;
- production change;
- system shutdown;
- incident command;
- records disposition;
- public statement;
- contract/revenue recognition.

A human District/consulting governance process remains authoritative for every one of those actions.

## Validation

From this directory:

```bash
python -m py_compile policy_assessment.py test_policy_assessment.py
python -m unittest -v test_policy_assessment.py
python -O -m unittest -v test_policy_assessment.py
```

The checked-in hostile suite contains 38 tests and is expected to pass in both normal and optimized Python; correctness does not depend on `assert` statements.

## Public-record handling

The District states that proposal responses and their contents are public record. Do not put credentials, participant/personnel PII, protected security details, SCADA/OT secrets, network diagrams, exploit details, or confidential vendor material into this workbench. The secret-shape check is only a backstop, not a substitute for records classification or counsel.

See `DELIVERY_SCOPE.md` for a six-month consulting work plan and responsibility boundary.
