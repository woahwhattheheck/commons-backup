# Redmond ECM evidence-contract compiler

This package is a deterministic, buyer-safe readiness compiler for **City of Redmond RFP 10915-26 — Enterprise Content Management Software and Implementation Services**.

It is deliberately not a proposal generator and not an ECM-platform claim. It is a reusable evidence/governance layer for an experienced ECM prime/vendor or technical subcontract team.

## Official procurement facts retained by the profile

- Official posting: `https://www.redmond.gov/bids.aspx?bidID=354`
- Official RFP: `https://www.redmond.gov/DocumentCenter/View/43368`
- Status rechecked 2026-10-04: **CLOSED**; the October 2 deadline has passed.
- Current Q&A: `https://www.redmond.gov/DocumentCenter/View/43692` (dated September 18, 2026).
- Current source/use receipt: [October 4 source update](source_updates/20261004/SOURCE_CURRENTNESS.md).
- Proposal due: **2026-10-02 4:00 PM Pacific**
- RFP body identifies these core areas: Technology, AI Governance, General Functionality, Records Management & Document Storage, Data Governance, Scanning, Workflow, Retention and Compliance, Records Search, Public Records Requests, and Reporting.
- RFP requires a proposal PDF, Exhibit A and C in Word, and Exhibit B in Excel.
- Exhibit A is the authoritative key-requirements line-item form. The 17 retained requirement IDs now bind selected current Q&A clarifications as well as the RFP body. This source slice does not acquire or replace Exhibits A–F; full line-item coverage remains outside this profile.
- The 13 critical flags and retained proof methods remain internal evidence classifications. A source update is not supplier capability, an award, or permission to respond after closure.

The original September 14 `profile.json` SHA-256 is retained as historical build identity (accepted recovery [#14479](https://github.com/woahwhattheheck/commons/pull/14479)):

`bdd59cdfe43963e4b23c53d169ee8441874acbe00895a39a2d0143d9b5b5a337`

The [October 4 source update](source_updates/20261004/SOURCE_CURRENTNESS.md) records the current profile identity, actual capture results, and pending compiler use. No readiness output has been generated for this source revision. The earlier September 10 Q&A bytes were not retained, so this update does not claim a complete old-versus-new answer diff.

## Why this exists

A proposal team needs to distinguish five very different things:

1. a current capability that has actual evidence;
2. support that depends on a third party or customization;
3. roadmap-only functionality;
4. unknown/unsubstantiated claims;
5. explicit blockers or contradictions.

Treating all five as "yes" creates proposal risk. The compiler instead maps supplier evidence into deterministic states:

- `met`
- `partial`
- `unknown`
- `blocker`

A critical unknown, explicit not-supported rating, future-only critical claim, or contradiction causes overall `BLOCKED`.

## Input contract

Input JSON has exactly three top-level keys:

```json
{
  "vendor": {
    "name": "Example ECM Prime + TokenJunkieLabs evidence accelerator",
    "role": "subcontractor",
    "scope_notes": "Synthetic example only."
  },
  "responses": [
    {
      "requirement_id": "RET-001",
      "rating": "Y",
      "comment": "Current retention behavior is evidenced.",
      "evidence_ids": ["EV-RET"]
    }
  ],
  "evidence": [
    {
      "id": "EV-RET",
      "kind": "test",
      "source_ref": "artifact://retention-test",
      "statement": "Retention test result retained by the proposal team.",
      "effects": [
        {"requirement_id": "RET-001", "effect": "support"}
      ]
    }
  ]
}
```

Allowed vendor ratings mirror the RFP response format: `Y`, `3P`, `C`, `F`, `N`, and `NA`.

Evidence effects are `support`, `constraint`, or `contradiction`. A `Y` with no linked supporting evidence is never promoted to `met`.

## Run

```bash
python revenue/redmond_ecm_evidence/compiler.py \
  --input revenue/redmond_ecm_evidence/source_updates/20261004/supplier-input.json \
  --json-out /tmp/redmond-ecm-report.json \
  --md-out /tmp/redmond-ecm-report.md
```

The retained October 4 input records an unassigned respondent with no supplier responses or evidence. Its compiler invocation remains pending while the shared executor is unavailable; no readiness state or successful run is asserted. Supply real supplier input for any later evidence assessment.

Both output paths are create-exclusive; existing files are refused. Input files must be regular non-symlink files. The CLI has no network access and exposes no submission, email, buyer-contact, or caller-time controls.

## Output

The JSON artifact contains:

- solicitation/profile identity and SHA-256;
- evaluation weights from the RFP;
- compliance matrix;
- blocker ledger;
- contradiction ledger;
- acceptance-test plan tied one-to-one to retained requirements;
- evidence catalog;
- explicit authority boundary;
- stable report SHA-256.

The Markdown artifact is a human-review rendering of the same compiled decision.

## Historical validation

The accepted original recovery retains the following validation history for its original profile. This source update does not replay it; its pending compiler invocation is tracked in the October 4 receipt.

```bash
python -m py_compile   revenue/redmond_ecm_evidence/compiler.py   revenue/redmond_ecm_evidence/test_compiler.py

python revenue/redmond_ecm_evidence/test_compiler.py -v
python -O revenue/redmond_ecm_evidence/test_compiler.py -v
```

The regression suite covers fail-closed critical unknowns, unsupported/future-only blockers, contradiction handling, partial support, duplicate/invalid IDs, stable ordering, strict JSON duplicate-key rejection, symlink refusal, create-exclusive output, deterministic rendering, and CLI authority boundaries.

## Commercial boundary

Use this package as a **paid ECM implementation/evidence/governance accelerator or technical subcontract** for an experienced prime/vendor.

It does not:

- submit a Redmond proposal;
- accept City terms;
- contact the City or any prospect;
- invent references, certifications, platform capability, pricing, or buyer approval;
- claim TokenJunkieLabs is a complete ECM product vendor;
- assert payment, cash, award, or recognized revenue.

See `COMMERCIAL_HANDOFF.md` for the prime/vendor handoff.
