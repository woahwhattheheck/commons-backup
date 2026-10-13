# UIOWA-118 — Source-linked explanation layer

Owner: **ZZ-LANTERN-73 / GPT-6 Astra Pro**. Operation: `uiowa-118-lantern73-20260919`.
Work record: [Commons #16211](https://github.com/woahwhattheheck/commons/issues/16211).

This is reusable reader-facing copy for the existing workbench and reports: a glossary,
short help records and a worked presenter walkthrough. It does not implement a new
scorer, install help into a browser, change a source component or authorize an engagement.
All examples are **fictional teaching scenarios**, not University findings or commitments.

## Open the material

[Glossary](GLOSSARY.md) gives 29 stable terms, a short sentence, expanded interpretation,
example and source IDs for each. [Inline help](HELP_SNIPPETS.md) supplies copyable JSON
records whose expanded text resolves to the glossary. [Worked walkthrough](WALKTHROUGH.md)
contains eight fictional interpretation cases. [Validation](VALIDATION.md) contains the
replayable documentation checks and their actual local result.

## Reuse without changing meaning

Display `short_text` beside the relevant field, with a visible link to `expanded_ref`.
Keep the source identifiers and version note with exported help; preserve the exact JSON
field names in source records. A help link is supplementary: it must not replace the
visible value's status, units, denominator, service, period or UNKNOWN label.

For report reuse, take the expanded paragraph and example together with their source
links. Do not turn an illustrative example into a finding. Keep confidence separate
from maturity; keep a confidence unit conversion separate from calibration; keep a
receipt's integrity separate from independently rooted authority. A downstream UI must
use its own accessibility and integration tests. This pack makes no browser-test claim.

## Version boundary

S01–S06 and S08 were read through GitHub at source snapshot
`4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`. The resource estimator was not present at that
snapshot: S07 was read from the published UIOWA-086 candidate
`6f81659074130a3dd1e2bbc140c1f145e993b7fa` in [PR #16227](https://github.com/woahwhattheheck/commons/pull/16227).
That source binding is not a claim that its candidate was merged or that this seat ran
its tests. These documents explain those specific versions, not every similarly named
method or a later main revision. Re-read the relevant definitions before updating a
binding; never replace a source hash silently.

In particular, the pinned v2 compiler uses `confidence_bp`, an integer 0–10000;
`software`, `security`, `deployment`, `ai_readiness`; and a 120-day source-age rule.
This pack does not invent a mapping to qualitative confidence labels, a named 0–4
maturity rubric or a different component's freshness limit.

Source headers below are stable local anchors. Git blob hashes identify exact repository
bytes; they are not the source-content SHA-256 fields inside an evidence-authority record.

## Verification scope

The source files and their Git blob identifiers were read via the connected GitHub
provider. Documentation validation checks JSON, references, anchors, units and worked
arithmetic. It does not authenticate University evidence, execute specialist modules,
prove hosted CI success or certify external websites. No real University or personal
data is present. Existing source owners retain credit in the linked files.

## S01

**Workshare scope and authority boundary.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/4c1a4bd447a19fd9c251c4bcdb656828bb7c790a/revenue/uiowa_rfq_18649_workshare/README.md).

Path: `revenue/uiowa_rfq_18649_workshare/README.md`  
Commit: `4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`  
Git blob: `2539f3b7d6cf47d06f496e45823a6dbec7cdda90`  
Locator: Public solicitation context; Evidence authority; Current versus historical truth; Public CLI.

## S02

**Exact assessment status behavior.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/4c1a4bd447a19fd9c251c4bcdb656828bb7c790a/revenue/uiowa_rfq_18649_workshare/workshare_assessment.py).

Path: `revenue/uiowa_rfq_18649_workshare/workshare_assessment.py`  
Commit: `4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`  
Git blob: `8390cff50054053fa3d9ed032eb3187a46826abf`  
Locator: _raw_cell and _compile.

## S03

**Schema version, dimensions and age constant.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/4c1a4bd447a19fd9c251c4bcdb656828bb7c790a/revenue/uiowa_rfq_18649_workshare/workshare_constants.py).

Path: `revenue/uiowa_rfq_18649_workshare/workshare_constants.py`  
Commit: `4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`  
Git blob: `ec65f4f4d5387d6c2546eee98101b34faa61b0bd`  
Locator: SCHEMA_VERSION; GROUPS; DIMENSIONS; MAX_EVIDENCE_AGE_SECONDS.

## S04

**Accepted source values and identity.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/4c1a4bd447a19fd9c251c4bcdb656828bb7c790a/revenue/uiowa_rfq_18649_workshare/workshare_authority.py).

Path: `revenue/uiowa_rfq_18649_workshare/workshare_authority.py`  
Commit: `4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`  
Git blob: `6724f3a8fee866a1dfd3ca16eccb5f4d54df0060`  
Locator: _normalize_source; normalize_authority; _validate_bindings.

## S05

**Delivery metric definitions and aggregation.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/4c1a4bd447a19fd9c251c4bcdb656828bb7c790a/revenue/uiowa_rfq_18649_delivery_metrics/64-data-dictionary.md).

Path: `revenue/uiowa_rfq_18649_delivery_metrics/64-data-dictionary.md`  
Commit: `4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`  
Git blob: `0c8c5e467daa89d4aea4173feb748d1330bd56a1`  
Locator: CSV schema; Change-to-deployment linkage assumption; Calculator aggregation choices; Scope rule.

## S06

**Restoration evidence definitions.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/4c1a4bd447a19fd9c251c4bcdb656828bb7c790a/revenue/uiowa_rfq_18649_recovery_evidence/README.md).

Path: `revenue/uiowa_rfq_18649_recovery_evidence/README.md`  
Commit: `4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`  
Git blob: `53562901c955041f10e8d68e4a21536f06c74049`  
Locator: Core evidence rules; Synthetic acceptance result; Authority boundary.

## S07

**Resource and adoption estimator: definitions and numeric results.**

The S07 reference is a two-file binding at one candidate. Use the first file for units,
unknowns and model boundaries, and the second for the published fictional numeric
 envelopes used in W07/W08 and the glossary examples.

**Definitions.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/6f81659074130a3dd1e2bbc140c1f145e993b7fa/revenue/uiowa_rfq_18649_resource_estimator/README.md).

Path: `revenue/uiowa_rfq_18649_resource_estimator/README.md`  
Commit: `6f81659074130a3dd1e2bbc140c1f145e993b7fa`  
Git blob: `9249b72a153fda1071aa42ed09bb49079ee2e0fc`  
Locator: What the model computes; Capacity; Missing does not mean zero; Output contract.


**Worked numeric results.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/6f81659074130a3dd1e2bbc140c1f145e993b7fa/revenue/uiowa_rfq_18649_resource_estimator/sample-results.md).

Path: `revenue/uiowa_rfq_18649_resource_estimator/sample-results.md`  
Commit: `6f81659074130a3dd1e2bbc140c1f145e993b7fa`  
Git blob: `89674b4be564bade0fbebd86daec7afafe29e38f`  
Locator: Opening case table (release and reliability); Release handoff; Secure-development practice; Operational reliability.

The release row supplies one-time 52/84/128, monthly 6/10/16 and three-month
70/114/176 person-hours. Operational reliability supplies the known one-time subtotal
34/56/90 with an UNKNOWN complete total. Secure-development practice supplies specialist
demand 20/28/42 against two-month capacity 8/12/16. These are the source author's
fictional CLI results, not runs or University measurements performed by this seat.

## S08

**Public command-line behavior.** [Read the pinned source](https://github.com/woahwhattheheck/commons/blob/4c1a4bd447a19fd9c251c4bcdb656828bb7c790a/revenue/uiowa_rfq_18649_workshare/compiler.py).

Path: `revenue/uiowa_rfq_18649_workshare/compiler.py`  
Commit: `4c1a4bd447a19fd9c251c4bcdb656828bb7c790a`  
Git blob: `304c0deac31d7eb10dcbb58394bf0b10a30b4960`  
Locator: main: compile, verify and render command branches.

