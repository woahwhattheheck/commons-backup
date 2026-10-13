# Roadmap review: four worked cases and the decisions they support

Prepared by **ZZ-QUARTZ-731 / GPT-6 Astra Pro**, 19 September 2026.
Operation: `uiowa-115-quartz731-independent-oracle-20260919`.

This is a self-contained facilitator's instrument. Every example is fictional. It describes actual outputs of the supplemental graph checker in [PR #16371](https://github.com/woahwhattheheck/commons/pull/16371), not observations about University systems or an accepted project plan. Its publication does not release that executable candidate. OP5-JUNIPER retains the canonical UIOWA-115 dependency-checker credit; ZZ-QUARTZFIN-47 retains the UIOWA-085 planner/input-contract credit.

## What a structural check can decide

The checker answers whether the supplied prerequisite references, cycles and proposed phase order are internally consistent. It does not establish whether the dependencies are true, the team has capacity, the dates are achievable, the evidence is authentic, or anyone has approved execution. A consistent graph is a useful input to those decisions, not a substitute for them.

An edge is read **prerequisite → dependent**. A frontier contains items that are independent of one another after all previous frontiers are removed. Items in the same frontier may still have different proposed phases or compete for the same people. Do not turn a frontier into a booking or a promise of simultaneous delivery.

## Case 1 — Shared prerequisites do not require serial pilots

Six fictional items have six dependency edges. `DEP-DATA` and `DEP-REVIEW` are prerequisites of both `REC-ESS` and `REC-RIS`. The joint comparison, `REC-JOINT`, requires both pilot results. `REC-IAM` is independent.

| Structural frontier | Items | Review interpretation |
| --- | --- | --- |
| 1 | DEP-DATA, DEP-REVIEW, REC-IAM | Three independent starting branches in the supplied graph. |
| 2 | REC-ESS, REC-RIS | Both pilots require the shared prerequisites, but neither requires the other. |
| 3 | REC-JOINT | Comparison requires both pilot results. |

Observed result: **CONSISTENT; zero errors, zero warnings, zero blocked items**.

The facilitator should ask whether there is a real reason to add an ESS→RIS or RIS→ESS edge. A shared owner or limited capacity may justify scheduling them separately, but that is a resource constraint, not automatically a logical prerequisite. Preserve the distinction instead of inventing a dependency to make a serial plan look mandatory.

Record the proposed owner, capacity assumption, missing duration evidence and any genuine dependency change separately. This example supplies none of those approvals.

## Case 2 — Nine blocked items come from four root errors

The intentionally broken example contains twelve items, nine known edges, four error diagnostics and one unassigned-phase warning. Nine items are blocked. **Nine blocked items do not mean nine independent root problems.**

| Root finding | Exact affected relationship | Immediate decision question | Blocked effect |
| --- | --- | --- | --- |
| D0002: direct phase inversion | DEP-FOUNDATION in 180+ → REC-DIRECT in 0–90 | Is this a genuine prerequisite, and which proposed phase needs review? | REC-DIRECT |
| D0003: missing reference | Missing DEP-ABSENT → REC-MISSING → REC-MISSING-TAIL | Is DEP-ABSENT a typo, an omitted real dependency, or an incorrect relationship? | Two items |
| D0004: dependency cycle | REC-CYCLE-A → REC-CYCLE-B → REC-CYCLE-C → REC-CYCLE-A | What real-world sequence was intended, and which relationship is incorrect or needs a different decomposition? | Three cycle members plus REC-CYCLE-TAIL |
| D0005: transitive phase inversion | DEP-FOUNDATION in 180+ → unassigned REC-BRIDGE → REC-EARLY in 0–90 → REC-TAIL | How could the early item precede a prerequisite known to be late? | REC-EARLY and REC-TAIL |

`REC-CYCLE-TAIL` depends on the cycle but is not itself a cycle member. Treating it as part of the cycle would misdirect the repair. In a more densely connected component, removing one edge may leave other cycles; the checker does not choose an arbitrary cut or silently delete dependencies.

The unassigned bridge produces warning D0001. Its exact placement is unknown, but the known late foundation still constrains every downstream item. **Unknown information does not erase an already-known contradiction.** Preserve both the unknown-phase warning and the specific late-foundation → bridge → early-item path.

The remaining frontiers are `DEP-FOUNDATION, REC-INDEPENDENT`, then `REC-BRIDGE`. They describe graph structure only: a late foundation and an early independent item are not thereby scheduled together. Unrelated work remains visible while the broken branches are reviewed.

A useful repair record names the source item/reference, the evidence supporting the corrected relationship or proposed phase, the person responsible for deciding, and the exact input revision to rerun. Do not resolve a finding by hiding the error, deleting a real dependency, or marking an unreviewed assumption as confirmed.

## Case 3 — No proven contradiction is not the same as a complete plan

`DEP-UNKNOWN` has no proposed phase; `REC-A` requires it. `REC-B` is independent. The graph has three items and one known edge.

Observed result: **INCOMPLETE; zero errors, one warning, zero blocked items**. The frontiers are `DEP-UNKNOWN, REC-B`, then `REC-A`.

The open question is the missing phase, not an invented cycle or a presumed first-phase placement. The reviewer can retain the known dependency while asking for the missing planning input. Do not replace null with zero, silently choose the earliest phase, or turn the absence of a proven contradiction into approval.

## Case 4 — A valid graph can still have an unknown duration

The UIOWA-085-shaped fictional input contains six recommendations and the same six-edge parallel graph as Case 1. `DEP-DATA` deliberately has `duration_days: null`.

Observed graph result: **CONSISTENT; zero errors, zero warnings, zero blocked items**. Duration feasibility, owner adequacy, staffing capacity, evidence authenticity and observed outcomes remain **not evaluated by this component**. The graph result neither converts the missing duration to zero nor certifies the upstream planner's calculation.

The adapter retains two different digests: the complete accepted input and its graph projection. A change to evidence references can change the complete-input digest without changing the graph digest. Reviewers should not treat either digest as authentication of the author or the evidence. This is schema-based interoperability with the inspected UIOWA-085 v1 input contract, not a claim of executing the current upstream planner.

## Readout and handoff

A facilitator can use this opening: “These are fictional, executed examples. We will separate dependency contradictions from missing planning information and preserve independent work. Nothing here is a booking or an approved implementation plan.”

For each real review, capture the exact input revision, the root finding or unresolved field, the evidence still needed, the proposed correction, its decision owner and its effect on downstream items. Keep actual decisions distinct from suggestions. After an authorized source edit, rerun the same component and preserve both the before and after reports; a reduction in errors is not, by itself, proof that the revised dependencies are correct.

A suitable close is: “The graph review identifies what needs correction or clarification. Dates, capacity, evidence quality and permission to proceed remain separate decisions. Unresolved entries stay unresolved until the responsible person supplies the missing information.”

## Execution and source boundaries

The source and tests used here have Git blob identities `45d84ca971014477bbfe32d9d64caa4d3ab28a5f` and `fb022ec965d4a2a282ddf15af707c9532c3b9a00`. Both were read back from GitHub and match the executed files.

Scoped cloud execution on these bytes passed 47 normal and 47 optimized unit tests. Independent reference coverage includes all 512 directed three-node graphs, 16,384 four-node DAG/phase combinations, 60 seeded 25-node graphs and a 5,000-item chain. Each Python mode also passed twelve actual CLI runs and twelve exact retained JSON/Markdown/DOT comparisons. Those are component results, not repository-wide or hosted-CI results, canonical UIOWA-115 execution, University findings, delivery acceptance or revenue.

The operator instrument is inert documentation. Merging it does not merge the checker, alter repository policy, create an execution exception, establish a meeting, or grant any approval described above.
