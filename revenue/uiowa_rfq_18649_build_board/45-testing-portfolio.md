# UIOWA-045 — Testing portfolio and release confidence

**Status:** synthetic assessment instrument for RFQ 18649 preparation.  
**Evidence boundary:** every example below is fictional. It demonstrates the assessment method and is not a finding about the University of Iowa.

## Purpose

Use this worksheet to connect business-critical behavior to the smallest useful portfolio of tests that provides release confidence. The method distinguishes what a passing test **does** establish from what it **does not** establish, so teams can find duplicated checks, untested behavior, and uncertain coverage without equating test count with quality.

## Test-level interpretation

| Level | Best evidence for | Common overclaim to avoid |
|---|---|---|
| Unit | Isolated rules, transformations, calculations, and state logic | "The application works" |
| Integration | Boundaries between application components, data stores, or services | "The complete user journey works" |
| Contract | Compatibility of a documented interface between producer and consumer | "Both systems implement all business behavior correctly" |
| End-to-end | A representative journey across deployed components | "Every variation and edge case is covered" |
| User acceptance | Agreed business outcome for stated acceptance criteria | "All internal technical behavior is correct" |

## Synthetic multi-service portfolio

| Service | Critical behavior | Unit | Integration | Contract | End-to-end | UAT | Portfolio interpretation |
|---|---|---|---|---|---|---|---|
| ESS | Fictional enrollment request preserves selected course and resulting state | Covered: domain rules | Covered: persistence round trip | Covered: downstream event shape | Covered: one representative journey | Covered for material workflow changes | Balanced layers. Keep E2E technical and UAT business-focused so the happy path is not needlessly duplicated. |
| ESS | Fictional enrollment status update reaches a downstream reporting consumer | Partial | Covered at producer boundary | Covered | **Gap** | N/A | Contract compatibility exists, but there is no evidence that the complete propagation path works. Do not infer end-to-end confidence from contract success. |
| RIS | Fictional proposal record preserves sponsor and submission metadata | Covered: field rules | Covered: API/data round trip | N/A | Partial: one workflow | Covered for major workflow changes | Strong isolated and integration evidence. E2E sample is narrow, so uncommon workflow variants remain uncertain. |
| RIS | Fictional approved-status value appears in a downstream report | N/A | Partial | Covered | **Gap** | N/A | Interface shape is checked, but propagation/timing is untested. Add a small representative E2E scenario only if the behavior is materially important. |
| IAM | Fictional directory profile update appears in a representative dependent application | Covered: mapping rules | Covered: directory adapter | Covered: profile schema | Covered: one representative consumer | N/A | Good layered evidence for the representative path, but it does not prove every dependent application consumes updates correctly. |
| Shared | Fictional notification service accepts requests from both ESS and RIS | N/A | Covered separately by both clients | Covered | Partial | N/A | **Duplication candidate:** two client suites repeat shared-service happy-path assertions. Consolidate shared assertions where practical while retaining client-specific behavior tests. |

## Coverage states

Use four states rather than a binary "tested / untested":

- **Covered** — current evidence directly exercises the behavior at the stated level.
- **Partial** — evidence covers only a meaningful subset or representative path.
- **Gap** — no current evidence directly establishes the behavior at this level.
- **N/A** — this level does not add useful confidence for the behavior; record the reason.

A missing test level is not automatically a defect. The question is whether the **portfolio as a whole** gives proportionate confidence for the business consequence and change frequency.

## Release-confidence worksheet

For each important behavior, record:

| Field | Question |
|---|---|
| Behavior ID | What stable identifier lets findings and evidence refer to the same behavior? |
| Business consequence | What user/service outcome matters if this behavior fails? |
| Change frequency | How often does this behavior or its dependencies change? |
| Test level | Which layer exercises the behavior most economically? |
| Test asset | What suite/scenario/script is the evidence source? |
| Trigger | Per change, merge request, nightly, release candidate, or explicit acceptance event? |
| Environment | Where is the test executed? |
| Owner role | Who maintains the evidence and triages failures? |
| Assertion | What exact condition is evaluated? |
| Passing establishes | What claim is directly supported by a pass? |
| Passing does not establish | What adjacent claims remain unsupported? |
| Coverage state | Covered / Partial / Gap / N/A |
| Regression rule | What change should cause this test to run? |
| Failure-triage rule | What happens on first failure before repeated reruns? |
| Evidence location | Where can a reviewer inspect the result? |
| Maintenance burden | Approximate execution and upkeep cost |
| Duplication / gap note | Is the same confidence already supplied elsewhere, or is an important behavior missing? |

## Regression-selection method

Prefer **behavior- and dependency-based selection** over indiscriminate execution:

1. Identify the changed component, interface, rule, or configuration.
2. Map the change to business behaviors that depend on it.
3. Run cheap local/unit checks for the changed logic.
4. Run integration/contract checks for affected boundaries.
5. Add representative end-to-end tests where the changed behavior crosses multiple deployed components or has high consequence.
6. Invoke UAT when acceptance criteria or user-facing workflow meaningfully changes.
7. Keep a small broad smoke set for unexpected coupling, but do not use a giant end-to-end suite as a substitute for targeted evidence.

A full suite may still be appropriate when change impact cannot be bounded reliably. Record that uncertainty rather than pretending selection is precise.

## Failure triage

A failed test is an observation, not yet a root cause.

For the first failure, preserve the original result and classify the next action:

1. **Reproducible product behavior:** same meaningful failure under a controlled rerun.
2. **Test/fixture issue:** test setup or data makes the assertion invalid.
3. **Environment/infrastructure issue:** execution context prevents a valid result.
4. **Intermittent/unknown:** failure does not yet have enough evidence for classification.

Repeated reruns without preserving the original evidence should not turn a red result into confidence. The useful question is what was learned and whether the release decision now has adequate evidence.

## Duplicated-check analysis

Two tests are candidates for consolidation when they:

- assert substantially the same behavior;
- exercise the same boundary;
- fail for the same underlying causes; and
- add little independent confidence.

Do **not** consolidate merely because test names look similar. A unit test and an end-to-end test may share a business label while providing different evidence.

**Synthetic example:** ESS and RIS each call the same fictional notification service and each suite repeats the service's generic "request accepted" cases. Move the shared contract cases to the service-owned suite, then retain client-specific tests for each system's payload rules. This reduces maintenance without losing distinct business evidence.

## Untested-behavior analysis

Treat a behavior as a material portfolio gap when:

- the consequence matters;
- no current test directly exercises the behavior or a defensible proxy;
- interviewees rely on assumption, manual memory, or unrelated passing tests; and
- a proportionate automated or acceptance check is feasible.

**Synthetic example:** the RIS portfolio checks reporting-feed schema compatibility but has no evidence that a fictional approved proposal reaches the downstream report. Record end-to-end propagation as **unknown**, then decide whether one representative release-candidate scenario is worth its upkeep.

## Confidence-per-effort prioritization

Use a simple qualitative decision table rather than maximizing test volume:

| Confidence gain | Maintenance/execution effort | Typical action |
|---|---|---|
| High | Low | Add or retain first |
| High | Medium/High | Retain when consequence justifies it; simplify setup if possible |
| Medium | Low | Useful supporting coverage |
| Low | High | Consolidate, narrow, or remove unless it protects a rare high-consequence condition |
| Unknown | Any | Gather evidence before claiming value |

This prioritization is a discussion aid, not a maturity score.

## Interview guide

### Portfolio shape
- What business behaviors would make you stop a release if confidence were missing?
- For each one, which current test provides the strongest evidence?
- Which suites exist because they still protect important behavior, and which exist mainly because they have always run?
- Where do several suites repeat the same confidence?

### Meaning of a pass
- Pick a recent green release. What did the passing tests directly establish?
- What important things remained untested or depended on monitoring/UAT/manual review?
- Are there tests whose names imply broader coverage than their assertions actually provide?

### Regression selection
- How is a changed component mapped to tests that should run?
- When do teams run the entire suite because impact is uncertain?
- How are shared libraries/interfaces handled across ESS, RIS, and IAM?

### Failure triage
- What happens before a failed test is rerun?
- How are product failures distinguished from test, fixture, or execution-environment problems?
- Are original failure artifacts retained so a later pass does not erase the evidence?

### Maintenance and ownership
- Who owns slow, flaky, or obsolete tests?
- Which checks are expensive enough that teams avoid running them?
- What test would the team add first if it could remove a recurring release uncertainty?
- What test would the team remove first if it had to cut maintenance cost without losing meaningful confidence?

## Evidence requests

Request representative artifacts, not exhaustive repositories:

- current test inventory or suite list;
- CI/test-run exports for a bounded sample;
- mapping from a few important business behaviors to tests;
- recent failed-run and triage examples;
- representative acceptance criteria and UAT record;
- regression-selection rules or change-impact examples;
- ownership/maintenance records for high-cost suites.

If evidence is missing, record **unknown**. Missing evidence is not itself proof that the practice does not exist.

## Completion check

- [x] Connects business-critical behaviors to unit, integration, contract, end-to-end, and UAT evidence.
- [x] Defines what passing at each level establishes and does not establish.
- [x] Includes regression selection and first-failure triage.
- [x] Synthetic ESS/RIS/IAM/shared-service examples identify duplicated checks, untested behavior, and uncertain coverage.
- [x] Recommendations explicitly prioritize useful confidence per unit of effort.
- [x] Synthetic examples are clearly separated from University findings.
