# 26 — Fair comparison across different technology stacks

**Proposed assessment method, version 1.0. Synthetic demonstrations only.**
This method implements UIOWA-026's requested outcome-based comparison of ESS, RIS
and IAM. The work order and scope are preserved in
[issue 16138](https://github.com/woahwhattheheck/commons/issues/16138).
It does not claim University approval, a validated maturity scale, peer percentiles
or a finding about any actual Iowa service. The outcome rules below are proposed
engineering judgments made explicit for review, not requirements attributed to an
external standard.

## 1. The comparison unit is a bounded outcome

Start with a named service, one assessment area, a versioned outcome criterion,
the observed sample and its operating context. Compare the outcome rather than a
product, language, architecture, workflow fashion, document count or release count.
A check box named "code review" is not equivalent to substantive feedback resolved
before release. A pipeline can retain that evidence, but the pipeline's existence
is not evidence of the outcome. A manual review can retain equally useful evidence.

The outcome ID, version and exact criterion text must agree. A deliberate wording
change requires a reviewed definition mapping outside this tool, not fuzzy matching
or silent normalization. The engine preserves mismatched definitions and declines
a direct comparison. Compare unlike local objectives descriptively, not by granting
numerical adjustment points.

The analyst supplies the claim and its basis. The program checks the metadata,
references, dates and comparison rules; it does not read the cited document or infer
from prose whether the claim is true. Every result remains a **supplied-record
comparison**, not an authenticated assessment result.

## 2. Assess support separately from comparability

For each practice, retain one explicit claim: `meets`, `does_not_meet`, `unknown`,
or `not_applicable`. A meets or gap claim requires at least one supplied current
observation record before it becomes `SUPPORTED_MEETS` or `SUPPORTED_GAP`.
Policies and interview statements remain useful context, but this conservative
v1 rule does not promote them alone to demonstrated operation. Current means the
stated analysis date falls within that source's recorded validity interval;
there is no hidden universal age cutoff.

Missing evidence is not a failed practice. A documented failed test is different
from an absent test record. An explicit unknown claim remains unknown even when
an artifact is attached. Not-applicable requires a rationale and stays outside
pass/fail treatment; the tool requests a scope record rather than verifying that
rationale itself. Any listed unresolved dissent makes the support state disputed.
Old dissent does not vanish merely because its date is old: resolving it requires
an explicit reviewed record update with the earlier snapshot retained.

A pair's short verdict never replaces these component states. Definition mismatch,
context uncertainty, both support states, all references and all judgments remain
visible in the detailed output, including when more than one problem coexists.

## 3. Context adjustment is an explanation, not a coefficient

Record four dimensions for each side and retain the original values:

| Dimension | What the assessor establishes | What not to infer |
| --- | --- | --- |
| Criticality | Consequences of an unavailable or incorrect service; important business journeys and relevant objectives. | A more critical service automatically has better or worse maturity. |
| Workload | Named population, load shape, concurrency, seasonal peaks, dependencies and scope of the observation. | A small successful exercise establishes peak-load effectiveness elsewhere. |
| Release cadence | Opportunity frequency, batching, change windows and urgency mix. | Frequent release is inherently mature; a calendar-constrained batch is deficient. |
| Sampling basis | Eligible population, selection method, omitted records, observation period and relevant exclusions. | Two identical percentages carry identical evidentiary strength. |

An unknown context value is `null`, not an empty string, zero or a fabricated
"normal" label. It cannot be erased with a favorable comparison judgment.
Matching known labels are reported as **matched recorded context**, not proof that
the service contexts are identical. An explicit material-difference or unresolved
judgment takes precedence even over matching labels.

When known contexts differ, record one decision for each relevant dimension:
`aligned_for_outcome`, `material_difference`, or `unresolved`. An alignment requires
a nonblank rationale and at least one current policy or observation reference.
For example, different release cadences need not prevent comparing substantive
review before each normal change when the population definition is the same.
An interview-only adjustment remains unresolved under the v1 method. A policy can
justify a comparison design or requirement; it still cannot prove the operating
practice itself.

A recorded material-difference assertion blocks direct comparison conservatively,
even without supporting references. This is **not** a finding that the difference
has been verified. The analyst must establish its basis before claiming it in a
report. Retain locally appropriate strengths and ask which additional exercise or
local criterion would make the intended conclusion supportable.

No multiplication factor, maturity bonus, weighted average or ordinal technology
ranking is applied anywhere in the engine.

## 4. Shared services and repeated evidence

A shared provider can support several named consumers. First establish which
consumer behavior the observation actually covers; a provider-wide document alone
does not establish each consuming application's integration. Then preserve the
common observation's `independence_key` across records and reports.

Within a pair, the engine reports the union and intersection of those provenance
keys. Reusing one record or giving the same observation two IDs must not create
additional evidence strength. These counts describe **provenance clusters, not
statistical sample size or proven independence**. A cluster assignment is supplied
by the analyst and must be reviewed. Do not sum pair-level cluster counts across
pairs or departments. A downstream synthesis component must deduplicate the global
keys again; this pairwise component deliberately does not replace that component.

## 5. Measurements are descriptive and separately comparable

The optional v1 measurement is a proportion: numerator, denominator, versioned
measure definition, population description and closed observation window. Counts
must be nonnegative integers or explicit nulls; booleans, fractions, negative
counts and numerator-greater-than-denominator are invalid. A missing count is not
zero. A denominator of zero means **no observed opportunities**, not 0% or 100%.

Only aligned outcomes and contexts with supported operating claims can receive a
rate delta. Definitions, population descriptions and start/end dates must also
match exactly. Denominator sizes may differ but remain visible. Arithmetic uses
exact rational fractions. A delta of zero means the supplied ratios match; it is
not proof of equal population performance, statistical equivalence, adequate
sample size or causality. Numerical values do not generate an outcome claim; the
analyst must check that the measurement and claim actually refer to the same
criterion and reconcile any contradiction before using them in an assessment.

## 6. Twelve paired demonstrations

Every evidence passage is generated alongside the packet in
`synthetic-evidence.md`; its E01–E11 headings are the exact locators. They are
fictional mini-records, not representations of University evidence.

| Case | Comparison | Defensible treatment and next question |
| --- | --- | --- |
| 01 | ESS manual review, 4/4, versus RIS reviewed automated releases, 40/40. | Same bounded review outcome; no automation bonus. Check substantive review records rather than pipeline status alone. |
| 02 | ESS and RIS consumers in one shared IAM revocation exercise. | Local supplied outcomes meet; one provenance cluster. Confirm named consumers and do not claim independent replications. |
| 03 | Critical registration recovery at seasonal load versus bounded research reporting recovery. | Retain both local successes; criticality and workload make direct transfer inappropriate. Which local journey/load exercise is needed? |
| 04 | AI-checking policy versus a completed small checking trial. | Policy side lacks direct operating evidence; not a low rating. Request a completed task-specific example. |
| 05 | Quarterly batch versus continuous releases, with a recorded comparison-design note. | Compare review per normal change, not deployment frequency; preserve 4 and 40 as different denominators. |
| 06 | Two maintenance changes with explicitly failed acceptance behavior. | Shared bounded gap, no ordinal score or individual blame. Trace the unmet behavior and corrective verification. |
| 07 | Unobserved service revocation practice versus a named observed consumer. | Unknown versus supported; do not manufacture a gap from missing data. |
| 08 | Recovery observation with an unresolved interview challenge to business-journey coverage. | Disputed; retain both sources and resolve the scope difference. |
| 09 | AI-checking v1 versus v2 adding a separate data-use review. | Definitions differ; the added v2 outcome is also unknown. Do not reuse v1 achievement as v2 achievement. |
| 10 | Proposed retired-service exclusion versus an active consumer. | Not-applicable stays separate; request the service-scope record. |
| 11 | Known reviewed changes with missing workload context. | Context unresolved despite a favorable supplied outcome. Ask for the service's observed workload boundary. |
| 12 | July ESS review sample versus August RIS review sample. | Bounded qualitative descriptions can agree, but no July-versus-August rate delta is emitted. |

## 7. Operator worksheet and review sequence

Generate the six-artifact rehearsal using the README command. The editable
`context-worksheet.csv` contains one row per pair and dimension, with both original
context values, recorded treatment, rationale, source IDs, follow-up question and
a **proposed role**, not an assigned person or appointment. It is an analyst
worksheet, not an auto-import interface.

The assessor first confirms the service/outcome boundary and source versions,
then checks support and dissent, then reviews each context judgment, then reads
any quantitative comparison with its denominators. A second reviewer should try
to break the conclusion: change only the implementation label; reuse a shared
source under another ID; remove the adjustment evidence; change the period;
retain stale dissent; change the criterion version. The regression suite makes
these attacks on the comparison logic reproducible without touching live systems.

Record changes as a new input snapshot and rerun. Keep the prior snapshot and
source bytes in the authorized evidence store. The report's SHA-256 covers the
canonical JSON metadata only; it is not a source-document authenticity check.
The current output supports discussion and follow-up, not automatic acceptance,
release, procurement or a University-facing maturity claim.
