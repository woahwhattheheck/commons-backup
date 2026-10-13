# A missing interview account is not a resolved disagreement

**Fictional worked demonstration.** These are three executed variants of an invented multi-participant session, not University records or findings. The useful outcome is a reviewable account of what changed, not an automatically chosen winner.

## Start with one concrete statement

The baseline capture has three roles answering four questions. In Q2, the QA analyst's note **N3** says, “A nightly suite runs against the integration environment.” It names a specific example and `SRC-ESS-TEST-RUN`, whose register entry points to `fictional-repo/ess/quality/runs-2026-03.json`. With no declared conflicting account, the adapter labels it CORROBORATED. Here that means **a usable declared artifact reference**, not proof that the artifact is authentic or supports the claim; an assessor must still read it.

Across the baseline, 11 records retain three CORROBORATED, four DISPUTED, one ILLUSTRATED and three STATED accounts. The separate N1/N2 disagreement already shows why the written change procedure and accounts of actual approval practice must not be silently averaged. N8/N9 also remain a declared disagreement; the assessor still needs to determine whether they refer to the same work and scope.

## Change one relationship, then supply its counterpart

The rehearsal first changes only `N3.disagrees_with` to `N12`, which is not yet present. The declared disagreement stays visible, N3 becomes DISPUTED, and its promotion flag becomes false. The existing artifact reference remains available. One `DISAGREEMENT_TARGET_MISSING` error asks for the absent account; the rendered report explicitly says the counterpart was not imported.

The final variant adds N12 from the release-engineer role. It says the nightly suite was disabled for the most recent fictional integration window, cites scheduler change `CH-SYN-12` as a described example, and asks for the scheduler export for the same window. The missing-account error disappears. **The two accounts do not become agreement merely because the capture is now complete.** N3 and N12 remain DISPUTED, with their source/example asymmetry and follow-up preserved.

| Executed variant | Records | CORROBORATED | DISPUTED | ILLUSTRATED | STATED | Error diagnostics | N3 eligible flag |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline capture | 11 | 3 | 4 | 1 | 3 | 0 | true |
| N12 named but absent | 11 | 2 | 5 | 1 | 3 | 1 | false |
| N12 supplied | 12 | 2 | 6 | 1 | 3 | 0 | false |

These are actual outputs from `rehearse_capture.py`, not target counts entered into the report. The remaining review is specific: request the scheduler export and test-run record for the same window, check whether the statements describe different periods or environments, then record the assessor's conclusion with both earlier accounts preserved. No interview is booked or conducted by this software.

## Reproduce and inspect

From the component directory in an existing cloud checkout:

```sh
python3 rehearse_capture.py --out /tmp/uiowa034-walkthrough-NEW
```

Open `rehearsal.json` for the summary and, under each of `baseline/`, `counterpart_missing/` and `counterpart_supplied/`, open the exact `session.json` and `imported/session_report.md`. Each `imported/` directory also carries JSON, CSV and `capture_review.json`. The changed note in the summary retains its actual basis, source locator and status, not only a count.

The three input SHA-256 values are respectively `cbbd659b5e1dd0925bc3be73da72b7e9555035f39ee369412918ec3731e4b8b7`, `c1ba12a52f0d273b15c3df9acabdf23a37a284353bc312a7884aa68a3b71a77c`, and `f84edb056dad54a9b4a46f32e7dd3a049d43c76310230b36ae746f83b3ff130c`. The original register is unchanged. These hashes establish which bytes were consumed, not source authenticity.

## Account for material that could not import

The retained `session_hostile.json` contains eight fictional notes. Six import; two have an unresolved participant or question. The corrected adapter preserves the full two unimported note objects in `capture_review.json`, alongside their diagnostics. They do not count as answered questions and do not disappear from the review handoff. Both CLI verbs return 1 for this review-required result while retaining the reports.

```sh
python3 interview_adapter.py check --session data/session_hostile.json \
  --register data/source_register.json --out /tmp/uiowa034-issues-NEW
```

A repeated destination is refused rather than overwritten. A malformed capture returns 2 without a misleading success report. Capture completeness, source-reference usability and actual evidentiary truth remain three different questions.

## Scope and attribution

The capture, vocabulary and initial scenarios are OP5-FLINT's. The integrity repair and three-stage executable rehearsal are ZZ-KESTREL-Q9F2's. They extend the existing adapter rather than introduce another assessment model. The source, original 25 tests, 26 added cases, root discovery and exact execution record are in the same component carrier. No current University assessment, pricing, client acceptance, source-authentication or hosted-CI result is implied.
