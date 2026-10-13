# UIOWA-087 collection and interpretation protocol

> Proposed assessment method. This protocol does not establish a University baseline and does not convert team/process measures into individual performance scores.

## 1. Start from the recommendation, not from an available metric

Every measure must name the recommendation it is intended to inform. Do not collect a convenient number and later invent a relationship to a recommendation.

For each recommendation, select at least:

- one **adoption measure** showing whether the proposed practice is being used; and
- one **outcome measure** showing a practical delivery-quality, security, or reliability condition that the recommendation is expected to influence.

Keeping these classes separate prevents an implementation activity from being reported as if it were an operational result.

## 2. Freeze the definitions before baseline collection

Record the numerator, denominator, population definition, evidence source, direction, and collection effort before reading the baseline value.

A later change in definition is allowed, but it breaks direct baseline/follow-up comparability until the earlier window is recomputed under the new definition or a new baseline is established.

Different denominator sizes do not automatically make periods incomparable. Different **population definitions** do.

## 3. Retain source locators

Each observation must retain an evidence locator that a reviewer can follow to the underlying register/export/artifact. The synthetic examples use `synthetic://` locators only to demonstrate the contract.

When real evidence becomes available, record:

- source system or artifact;
- export/report identifier;
- measurement window;
- sampling rule;
- any exclusions;
- query/filter version when material.

A percentage without a traceable numerator, denominator, and source is not sufficient for this pack.

## 4. Estimate collection effort

The register records expected minutes per collection cycle. This is not labor authorization; it is a planning estimate so a proposed measure can be rejected or simplified if its measurement burden exceeds its decision value.

During discovery, validate:

- who can access the evidence;
- whether the numerator and denominator can be derived reproducibly;
- whether manual review is required;
- whether privacy or data-handling constraints require aggregation;
- how often leadership would actually use the result.

## 5. Compare baseline and follow-up conservatively

The analyzer computes rates from counts and reports absolute percentage-point movement.

Directional labels mean only:

- `FAVORABLE_DIRECTION`: movement is in the direction named in the register;
- `UNFAVORABLE_DIRECTION`: movement is opposite the named direction;
- `UNCHANGED`: the recomputed rates are equal within floating-point tolerance;
- `INSUFFICIENT_DATA`: a rate or comparable pair cannot be established.

These are measurement descriptions, not claims that a recommendation caused an outcome.

## 6. Keep adoption and outcome interpretation separate

Examples:

- More releases with acceptance evidence = stronger **adoption** of a traceability practice.
- Fewer releases requiring near-term corrective rework = a potentially favorable **outcome** signal.
- Both moving favorably is more decision-useful than adoption alone, but still does not prove causation.
- Adoption improving while the outcome worsens is not hidden by averaging. It is a reason to investigate context, lag, implementation quality, or the recommendation itself.

Do not calculate a combined effectiveness score.

## 7. Handle missing and changing data explicitly

If numerator/denominator data are missing, report `INSUFFICIENT_DATA`.

If population definitions differ, report `NOT_COMPARABLE`.

Do not:
- substitute zero for a missing count;
- reuse a stale baseline without labeling it;
- compare percentages derived from different populations as if they were the same measure;
- infer that absent evidence proves the practice did not occur.

## 8. Avoid individual performance scoring

The recommended unit of analysis is a service/team/process population. Do not use these measures to rank individual developers, reviewers, operators, or interview participants.

If a source export contains individual identifiers, aggregate or minimize them where feasible before using the evidence for this assessment.

## 9. Review cadence

At each collection cycle:

1. confirm the recommendation is still active/relevant;
2. confirm definitions and population are unchanged;
3. collect numerator and denominator from the stated evidence source;
4. record exact evidence locator and any exclusions;
5. recompute the rate;
6. inspect adoption and outcome rows separately;
7. record context that could explain movement;
8. decide whether the measure still provides enough decision value for its collection cost.

## 10. Reporting language

Prefer:

- "The follow-up sample contains fewer repeat-condition incidents under the same population definition."
- "Acceptance-evidence linkage increased in the sampled change set."
- "The outcome moved favorably, but this comparison does not establish causality."

Avoid:

- "The recommendation caused a 40% improvement."
- "The team is 85% mature."
- "This employee/group performed poorly."
- "No evidence means the practice never happened."
