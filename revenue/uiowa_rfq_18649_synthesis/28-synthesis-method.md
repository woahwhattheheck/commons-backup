# UIOWA-028 — cross-group synthesis method

Owner: ZZ-F4BC7C35 / GPT-6 Astra Pro. Operation: `uiowa-028-f4bc7c35-20260919`.
This is a proposed TJLabs assessment method with fictional worked examples,
not an adopted University framework, an audit conclusion, or a maturity score.

## Purpose and decision boundary

A department-level theme should explain a common capability, a common dependency,
or a useful coordination opportunity without erasing local evidence. Three group
names on a report do not create three independent observations. A common symptom
does not establish a common cause. Consistency does not require identical tools.

The supplied program composes annotated findings. It validates record consistency,
preserves source locations and disagreement, and proposes an action *shape*.
An assessor still judges source credibility, sampling relevance, applicability,
causal support, and the wording of any final recommendation. The program does not
read remote documents, authenticate records, assign confidence from counts, or
replace the workshare compiler's authority/currentness boundary.

## Unit of analysis

Use one finding per sampled service, practice, and observation window. Preserve
`finding_id`, `group`, `dimension`, `service_id`, exact date window, statement,
context, outcome, evidence basis, dependency topology, and proposed mechanism.
A source may support several findings. Each use retains the original `source_id`,
`source_ref`, version, locator, excerpt, and evidence kind. The four separate
reference lists are support, dissent, limitations, and mechanism support.

Use the existing workshare group vocabulary `ESS`, `RIS`, `IAM` and dimension
vocabulary `software`, `security`, `deployment`, `ai`. These are interface names,
not claims about a particular University's organizational boundaries.

`strength` and `gap` require supplied support. `unknown` requires a rationale and
means a relevant conclusion is unavailable; it is not a low rating.
`not_applicable` requires a scoped rationale and must be revisited when scope
changes. `observed` requires an artifact or metric reference; an interview or
policy alone remains `reported`. That structural check does not authenticate an
artifact or establish that it actually supports the assessor's interpretation.

## Synthesis sequence

1. Establish the scope: practice outcome, affected services, observation period,
   source coverage, and relevant group interfaces. Record criticality and cadence
   in context. Do not silently normalize different service boundaries.
2. Separate what happened from why. Record a `mechanism_id` only with a declared
   basis: supported, hypothesis, or unknown. A supported mechanism must cite the
   source carrying the causal explanation. Mere labels do not supply causal proof.
3. Preserve dependence. Reuse the same `origin_id` for one interview, exercise,
   shared-service event, or derivative collection. Equal whole-document digests
   and common origins are transitively clustered. Distinct clusters are **not**
   proven independent: missing origin information remains visible.
4. Compare only the same dimension, practice key, and exact observation window.
   A useful comparison across different periods requires a separately reviewed
   aligned sample; the tool never silently combines partial overlaps.
5. Within a comparison, separate documented mechanisms and local/shared topology.
   Shared records require a dependency ID. Hypotheses, unknowns, and inapplicable
   records remain individual, visible themes rather than a manufactured common cause.
6. Carry every underlying finding and every evidence role into the theme. Display
   affected groups separately from source count and declared correlation clusters.
   Retain related findings outside the theme so distinct explanations are discoverable.
7. Choose the recommendation's scope from the actual coordination need. Resolve
   material dissent and coverage limits before adopting a department-wide statement.

## Relationship and action table

| Relationship | Required supplied structure | Defensible interpretation | Proposed action shape |
|---|---|---|---|
| Shared capability | Shared dependency; same supported mechanism; sampled strengths | One capability reaches the listed sampled groups | Shared owner sustains capability; group leads verify local effects |
| Inherited dependency | Shared dependency; same supported mechanism; gap or mixed outcomes | A dependency is implicated in listed samples, not independently rediscovered in each group | Shared-owner investigation plus affected-group checks; dissent first |
| Repeated local practice | Local topology; common supported mechanism in multiple groups | Similar sampled outcomes through distinct local implementations | Common improvement options with group-specific implementation |
| Local exception | A separate supported local mechanism within an otherwise comparable practice/window | The case needs a distinct explanation; “exception” is not a frequency estimate or blame | Separate group action, retaining links to other explanations |
| Local pattern | One supported sampled local mechanism without a contrasting comparable case | A local result with no supported broader generalization | Group-specific action and proportionate further sampling |
| Unresolved or inapplicable | Unknown outcome/topology, hypothesis, or scoped non-applicability | No common causal conclusion is established | Focused follow-up or scope confirmation, not assumed remediation |

An explicit dissent reference, or mixed strength/gap findings inside one theme,
marks that theme contested. Reported-only or mixed evidence also routes to focused
follow-up. A tool status of `sample_supported` means the supplied annotations are
structurally sufficient to compose a sample theme; it is not verified factual truth.

## When a department-level statement is justified

A department-wide **capability** claim needs a defined capability boundary, an
accountable shared owner, actual evidence of operation, and evidence that the
claimed groups/services inherit or use it. A single shared exercise may establish
one common event, not reliability across all downstream functions.

A department-wide **gap** claim needs a stated affected universe and support for
that scope. Multiple local examples can justify a coordinated investigation or
common improvement option without establishing prevalence throughout AIS.
A local exception does not invalidate an appropriately qualified common theme,
but its consequence and explanation must remain in the report.

A **consistency opportunity** can be useful even where local practices are
individually effective: align identifiers, handoffs, outcome definitions, or shared
ownership rather than forcing one toolchain. Explain the operational benefit and
adoption burden. Different-but-effective manual and automated practices should not
be ranked merely by their implementation style.

The program deliberately emits `sampled_all_three_groups`, never “department-wide
proven.” Promotion of the wording requires assessor judgment and evidence outside
simple group counting. Retain the denominator, selection method, period, exceptions,
and unresolved questions with any broader conclusion.

## Worked fictional cases and expected conclusions

| Practice | Supplied observations | Theme and retained uncertainty | Practical response |
|---|---|---|---|
| Business recovery | ESS/RIS/IAM reuse one shared restoration exercise; IAM supplies a counterexample | One inherited dependency; three affected groups; one support cluster; contested | Shared owner reconciles exercise scope; test the relevant business functions separately |
| Requirements review | ESS manual checklist and RIS automated routing both show requirement checking and recheck; IAM sample absent | Repeated local strength in ESS/RIS; two declared support origins; IAM remains unknown | Compare useful review outcomes; request an IAM sample; do not prescribe automation |
| Delivery waiting | ESS trace reports ownership handoff wait; RIS trace reports test-worker queue wait | Two local exceptions with linked comparison context, not one generic “slow delivery” cause | Clarify handoff ownership in ESS; inspect test capacity/selection in RIS |
| Release identity | One shared trace connects source and artifact for all three groups | One shared capability with three-group reach and one support cluster | Maintain the shared map; sample downstream use before claiming universal coverage |
| AI summary review | ESS policy proposes a practice; IAM scoped service does not perform it | A reported hypothesis and a separately reasoned non-applicable case | Collect operating examples for ESS; preserve the IAM scope condition |

Each source excerpt is retained in `fixtures/synthetic.json`. The generated
`examples/themes.md` contains the worked table and exact fictional locators.
`examples/themes.csv` is a summary view; JSON output is the full evidence-bearing
interchange representation. CSV guards formula-like presentation cells with an
apostrophe without altering the JSON data.

## Reviewer worksheet

For each theme, record the proposed sentence, audience, claimed service universe,
period, finding IDs, support/dissent/limitation IDs, shared dependencies, declared
origins, alternative explanations, and missing sample. Then ask:

- Could a shared source, source alias, or derivative interview have been counted twice?
- Do the source excerpts actually support the annotated mechanism and outcome?
- Would the same outcome receive the same treatment under another stack or workflow?
- Does dissent change the scope, mechanism, or action rather than merely the wording?
- Who owns the shared action, and what remains each group's responsibility?

A usable recommendation names the practice change, intended result, accountable
role, evidence required to validate it, effort assumptions, prerequisites, and
scope limits. This module supplies linkage and action shape; the recommendation
register owns estimates, phases, and final acceptance. No duplicate score or
parallel roadmap is created here.

## Source and interface anchors

The task definition is the live demo's UIOWA-028 order, Slack timestamp
`1789824411.364929`; durable work record is Commons issue `#16133`.
The existing [workshare README](../uiowa_rfq_18649_workshare/README.md) defines the
non-authorizing inspection boundary. Its
[synthetic authority fixture](../uiowa_rfq_18649_workshare/fixtures/synthetic_authority.json)
supplies the group/dimension/source-ID vocabulary. No field mapping turns a
synthesis annotation into compiler authority, a trusted root, or a maturity value.
