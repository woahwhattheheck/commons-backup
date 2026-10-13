# UIOWA-044 — code-review practice assessment

**Preparation instrument; synthetic examples; not University findings.**
Builder: ZZ-COPPERFINCH-R73D / GPT-6 Astra Pro. Operation: `uiowa-044-review-practice-r73d-20260919`.

This offline kit turns sample review metadata into reproducible interview questions and explicitly denominated process observations. It does not inspect application code, fetch provider records, rate employees, issue maturity scores, or authorize a release. The CLI reads one local UTF-8 JSON file and writes JSON or Markdown to standard output; it changes no source records.

## Run the actual rehearsal

Python 3.10+ syntax; no third-party dependencies. The supplied tests were exercised on Python 3.13, including optimized mode.

```sh
cd revenue/uiowa_rfq_18649_review_practice
python review_practice.py synthetic_reviews.json > /tmp/review-report.json
python review_practice.py synthetic_reviews.json --format markdown > /tmp/review-report.md
python -m unittest -v test_review_practice.py
python -O -m unittest -v test_review_practice.py
```

From the repository root, `python test_uiowa_review_practice_r73d.py` runs the same suite. The root discovery shim integrates the suite with the existing `tests.yml` battery without modifying that workflow. A local pass is not a claim that repository-wide CI passed.

Exit 0 means the input was valid and a report was produced, **not** that practices are adequate. Missing or unresolved evidence produces questions, not a nonzero exit. Invalid JSON, unknown fields, duplicate records and impossible chronology return exit 2 with an explanation on stderr and no report on stdout.

## Supplied example and expected output

The eleven cases are constructed boundary cases, not a random sample. Ten are merged and one is still open at the frozen observation time. Three merged changes contain dated, structured, final-head peer feedback before merge. Eight merged changes are assessable for that narrow signal; the partial export and undated-review case remain unknown.

| Measure | Expected value | Interpretation |
|---|---:|---|
| Changes / merged changes | 11 / 10 | Open work is retained, not inserted into the merged denominator. |
| Structured feedback among assessable merged changes | 3 / 8 | A descriptor of these records, not substantive-review quality. |
| Assessable coverage of merged sample | 8 / 10 | Report alongside the first ratio; unknowns do not disappear. |
| Observed structured feedback among all merged changes | 3 / 10 | Lower observed fraction; not an estimate for missing cases. |
| Dated first-observed final-head feedback pairs | 3 | Complete exports and known request times only. |
| Median / nearest-rank p90 | 30 / 45 calendar minutes | Not working hours, an SLA, or a peer benchmark. |
| Open RIS-203 no-observed-feedback window | 175 minutes | No event observed by cutoff; never a zero-time completed review. |

ESS-101 has linked feedback resolved before merge. ESS-102 has an approval click only. RIS-201 has evidence for an earlier revision. RIS-202 has a partial export. IAM-301 has on-time post-emergency follow-through, which does not retroactively count as pre-merge review. IAM-302 has no demonstrated follow-through in a complete observation window and is overdue against its fictional due date. ESS-103 has an open point. IAM-303 records self-review only. ESS-104 has an undated record. RIS-204 resolves after merge and therefore remains unresolved at the merge cutoff.

## Data contract

All listed keys are required. Use JSON `null`, not an empty string, for a listed nullable value. Extra keys are rejected to catch misspellings and accidental score/authority fields. Dates must contain timezones. `as_of` is an explicit retrospective observation boundary; it is not a trusted clock. Source references are identifiers only: the tool neither dereferences them nor validates their authenticity.

| Object | Required fields and meaning |
|---|---|
| Packet | `schema` = `uiowa-review-practice/v1`; `synthetic` boolean; `as_of`; `sampling_note`; `changes` array. |
| Change | Unique `id`; `group` ESS/RIS/IAM; `service`; `author` pseudonymous role identifier; `head` exact imported revision identity; `created_at`; nullable `review_requested_at`, `merged_at`; `context`, `export`, `emergency`, `reviews`. |
| Context | `workflow`, `review_expectation`, `constraints`: local practice and operating conditions, not vendor requirements. |
| Export | `complete` boolean; nullable `reference`, `captured_at`. A completeness assertion requires both. Coverage is evaluated separately at merge/as-of and at emergency follow-through as-of. |
| Emergency | `declared` boolean; nullable `rationale`, `followup_due_at`. Non-emergencies use null for both. A due date requires a merge and cannot precede it. |
| Review | Change-unique `id`; `reviewer`; `head`; `state` approved/commented/changes_requested/dismissed; nullable `submitted_at`; `source_ref`; nullable `context_ref`; `feedback` array. |
| Feedback | Change-unique `id`; `kind` question/change_request/tradeoff/test_evidence; `summary`; `source_ref`; `disposition` resolved/open/unknown; nullable `resolution_ref`, `resolved_at`. |

A resolution counts at a cutoff only when disposition, dated resolution and reference all support it. “Resolved” without its dated reference stays unresolved/unknown. A later resolution is preserved but does not rewrite the earlier cutoff. The packet is a snapshot, not a complete event-sourced review history: it cannot infer when an item was reopened or a review was dismissed without those records being modeled separately. For an earlier assessment, obtain the appropriate historical snapshot instead of relabeling a current export.

Deduplicate provider pagination before import. Review IDs are unique within a change and feedback IDs are unique across all reviews of that change. Copying a thread into two reviews must not double-count it. The same local ID may appear in a different change; references plus change identity preserve scope.

## Classification rules and limits

The tool classifies **recorded evidence**, not review quality. A non-dismissed peer review must reference the exact imported final head and have a known submission time at or before the assessment cutoff to support pre-merge coverage. A structured feedback item has an identified kind, summary and reference; its presence triggers `substantive_feedback_recorded`, but the name is a record category, not an independent judgment that the feedback was valuable or correct. Fabricated structured feedback would produce the same signal. Inspect its source before writing findings.

An approval-only record remains distinct from structured feedback. This does not mean the reviewer did no work. Paired or synchronous review may have occurred outside the exported tool. Old-head feedback, self-review and dismissed records retain their references but do not silently become final-head peer review. Ask what changed after the reviewed revision and what the local process considered proportionate; the toolkit does not prescribe reapproval for every edit.

Observed positive evidence can be retained from a partial export. Missing evidence cannot establish a negative until a complete export covers the cutoff; undated final-head reviews keep a negative classification unassessable even when a separate approval click exists. Always show both the assessable denominator and the entire sample count. A selected record set does not establish organization-wide prevalence, fairness, independence of samples or causal effect.

First-feedback intervals start at the supplied initial request and end at the first **recorded structured final-head peer feedback**. They require complete exports and no undated final-head reviews. Missing request times, re-requests recorded after feedback, incomplete exports and unknown timestamps are excluded, not imputed. The median/p90 describe only observed pairs; open and no-event windows are reported separately. Calendar time includes nights and weekends. Do not compare unlike teams or infer individual productivity from it.

Emergency closure requires a post-merge, final-head, contextualized peer review, dated dispositions for **all** active final-head feedback, and a complete export through `as_of`. One newly resolved review cannot hide a still-open earlier point. Completion is measured using the last relevant resolution/submission. Missing coverage or review timing stays unknown. This deliberately conservative metadata rule is not a universal emergency policy: questions and consciously deferred changes can be handled by a linked disposition with an explanation, rather than pretending that every comment required a code change.

The input digest covers canonical parsed JSON with sorted object keys; array order remains significant. It detects a change to the supplied packet, not tamper-proof custody or independent provenance. Reports are regenerated from the input; this version has no report-verification/import API. Do not accept a hand-edited report as if the tool independently validated it.

## Interview and report handoff

Use [INTERVIEW_AND_RUBRIC.md](INTERVIEW_AND_RUBRIC.md). Preserve local workflow context, the sampling frame, export boundary, source locators, competing explanations and unresolved questions. Attach this kit's report and source references as supporting process evidence. It is **not** a replacement for the parent workshare compiler, nor an adapter that grants its evidence authority or maturity values. No automatic numeric mapping to the twelve assessment cells is provided.

Keep real engagement data in the agreed private working location; this public code fixture is entirely fictional. No names, private source excerpts, actual service inventory, customer approvals, staffing commitments or bid representations are needed to run the rehearsal.

## Method reference

The behavior anchors in the companion worksheet are a proposed TJLabs method, not a published benchmark or validated maturity scale. Google's engineering guide describes balancing code-health improvement with progress and keeping important review decisions discoverable; it is used here only as contextual practice guidance, not proof of any University implementation or a requirement to adopt Google's workflow. Source accessed 2026-09-19: [Google, The Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html).

## Maintainer contract

The tests pin unknown-versus-negative handling, exact-head interpretation, duplicate records, late resolution, emergency aggregation, observed-pair denominators, timestamp validity, deterministic rendering and CLI errors. Normal and optimized execution must agree. Future provider adapters must retain their own bounded export/completeness evidence rather than manufacturing `complete=true`; this kit intentionally makes no provider API calls.
