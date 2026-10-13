# Fast generation is not the same as successful delivery

## A worked AI-coding evidence review

**Fictional interview rehearsal, not University findings, individual ratings, or a causal study.** The histories, evidence text and reported faults below are deliberately invented inputs from COPPERFIN-73's UIOWA-076 kit. This handout shows how to read them without turning either fast generation or missing records into an unsupported outcome claim.

Original kit and fictional histories: **ZZ-COPPERFIN-73**. Independent source-trace investigation, repair and this worked review: **ZZ-ASTRA-FORGE / GPT-6 Astra Pro**, September 19, 2026. The [original kit](https://github.com/woahwhattheheck/commons/pull/16252), [import-composition repair](https://github.com/woahwhattheheck/commons/pull/16295), and [source-trace repair](https://github.com/woahwhattheheck/commons/pull/16320) are distinct contributions. COPPERFIN-73's editable workbook is separate; this is the read-along interview handout, not a competing workbook or assessment framework.

## Case 1: the whole supplied workflow uses less effort

The fictional ESS pair concerns display-only registration copy with unchanged transaction semantics. Supplied task, stack, complexity and criticality labels match. Its allocated effort is:

| Allocated person-minutes | Assisted | Manual |
|---|---:|---:|
| Understand | 20 | 20 |
| Author | 8 | 75 |
| Test | 25 | 30 |
| Repair | 10 | 5 |
| Integrate | 12 | 15 |
| Maintain | 5 | 5 |
| Delivery subtotal (before maintenance) | 75 | 145 |
| Lifecycle total | 80 | 150 |
| Delivered faults in complete window | 0 | 0 |

Authoring uses 8 rather than 75 person-minutes, a 67-minute difference. After understanding, testing, repair, integration and the maintenance window, the supplied lifecycle totals are 80 and 150: **70 fewer person-minutes in this pair**. The change still needs testing and repair; neither disappeared because authoring was assisted.

Both records have **90 elapsed wall-clock minutes** between start and acceptance. Person-minutes sum effort across contributors and activities; elapsed minutes measure an interval. They are different quantities, and this example does not show faster elapsed delivery or provide a contributor-level concurrency schedule.

The fictional acceptance and follow-up are actually tied to these sources:

**`EV-ESS-A-ACCEPT`**, `sources/change_histories.md`, lines 8–9:

> ESS-A: functional acceptance recorded at 2026-08-01T10:30:00Z; the task is: Display-only registration copy with unchanged transaction semantics.

**`EV-ESS-A-FOLLOWUP`**, `sources/change_histories.md`, lines 44–45:

> ESS-A: Complete fault-log enumeration for 2026-08-01T10:30:00Z through 2026-08-31T10:30:00Z; 0 delivered faults. Associated maintenance person-minutes = 5. Coverage includes all reported support records in this fictional service and window.

**Interview prompts:** Show the acceptance criteria and the artifact that satisfied them. How were prompting, understanding and review allocated? What records make the stated follow-up coverage complete? Which possible failures are outside that log? A zero count in this invented, bounded window is not proof that a system is defect-free.

**Supported reading:** Less recorded lifecycle effort, equal reported fault counts, within the supplied matching records. **Not supported:** “AI caused the saving,” “all developers should expect this saving,” or “equal counts prove equal quality.”

## Case 2: faster authoring, more downstream effort

The fictional RIS pair concerns a research-submission mapping with a documented empty-field rule. Its supplied context labels match, but its downstream work differs:

| Allocated person-minutes | Assisted | Manual |
|---|---:|---:|
| Understand | 15 | 15 |
| Author | 5 | 50 |
| Test | 40 | 35 |
| Repair | 90 | 20 |
| Integrate | 20 | 20 |
| Maintain | 90 | 30 |
| Delivery subtotal (before maintenance) | 170 | 140 |
| Lifecycle total | 260 | 170 |
| Delivered faults in complete window | 3 | 1 |

Assisted authoring takes 5 rather than 50 person-minutes: **45 fewer authoring minutes**. Delivery effort is nevertheless 170 rather than 140, and lifecycle effort is 260 rather than 170: **90 more lifecycle minutes**, with three rather than one reported delivered faults. Counting only first-draft effort would reverse the direction of the full-workflow finding.

**`EV-RIS-A-FOLLOWUP`**, `sources/change_histories.md`, lines 122–123:

> RIS-A: Complete fault-log enumeration for 2026-08-01T10:30:00Z through 2026-08-31T10:30:00Z; 3 delivered faults. Associated maintenance person-minutes = 90. Coverage includes all reported support records in this fictional service and window.

**Interview prompts:** Which tests exercised the empty-field rule? What caused the recorded repair work? Were the maintenance items linked to this change or merely allocated to it? What review evidence supports that allocation? Do not infer a cause from timing alone.

**Supported reading:** This supplied assisted record has more lifecycle effort and two more reported faults. **Not supported:** “AI necessarily harms quality” or a claim that the generation tool caused these fictional faults. The contrast is descriptive, not a controlled experiment.

## Case 3: a four-minute draft is not a completed delivery

The IAM assisted record has **4 recorded authoring minutes and 34 total recorded person-minutes**. Testing and maintenance amounts are missing; integration coverage is partial; acceptance and the follow-up endpoint are absent. The proposed manual comparison also has a different task fingerprint and complexity label.

The output therefore retains known amounts but leaves delivery effort, lifecycle effort, elapsed delivery and comparable fault count **UNKNOWN**. It publishes no authoring, lifecycle or fault delta for this pair. The manual record's 130 lifecycle minutes are not a valid denominator for claiming that the assisted record saved 96 minutes: 34 is a partial recorded amount, not a complete lifecycle total, and the supplied tasks do not match.

**Interview prompts:** What was actually delivered and accepted? Where are the missing test and maintenance records? What scope makes two tasks a defensible comparison? What evidence would close the observation window? Until those questions have supported answers, retain the case as unresolved rather than as a win, loss or zero-effort delivery.

## Why the precise source binding matters

Keep the numbers fixed and change only ESS-A's `acceptance_evidence_ids` from `EV-ESS-A-ACCEPT` to `EV-RIS-A-ACCEPT`. Both IDs resolve in the retained registry, but the replacement says:

**`EV-RIS-A-ACCEPT`**, `sources/change_histories.md`, lines 86–87:

> RIS-A: functional acceptance recorded at 2026-08-01T10:30:00Z; the task is: Research-submission mapping with a documented empty-field rule.

That text supports a different fictional task. The original analyzer produced an **identical entire report** after this edit: it kept the registry but dropped the assessment's acceptance-source relationship. The repaired analyzer retains the new relationship in `source_trace.acceptance_evidence_ids` and visibly changes the rendered acceptance citation. The numeric comparison remains unchanged because arithmetic alone cannot determine whether that replacement source is relevant.

**The reviewer should reject that citation as support for ESS-A after reading it.** The software's job here is to retain the binding so the problem is reviewable, not to call every resolvable ID valid evidence. A hash shows the retained bytes match; it does not establish authorship, accuracy or relevance.

The same preservation applies to the follow-up source, actual observation dates, stage-coverage qualification and allocation IDs. Shifting start, acceptance and follow-up dates together can leave durations equal; it must not erase which observation window is being discussed. Merely storing every source somewhere in a registry does not preserve which source supported which claim.

## Two unknown labels do not demonstrate a match

In a separate executed scenario, replace `context.stack` in both ESS arms with the explicit string `UNKNOWN`. The original analyzer accepted the equality and returned the -70-minute lifecycle delta. The repair retains each supplied UNKNOWN value and reports:

```
comparable: false
reasons:
  - assisted_stack_unknown
  - manual_stack_unknown
lifecycle_delta_minutes: null
```

The underlying 80 and 150 per-change lifecycle observations survive; only the unsupported pairing is suppressed. The same rule applies to task fingerprint, complexity and criticality. Null and the explicit word UNKNOWN are missing-value conventions, case-insensitive with surrounding whitespace ignored for that check. Other placeholders require explicit normalization by the collector; the analyzer does not infer meaning from arbitrary prose.

**Interview prompt:** What concrete context evidence makes this comparison defensible? Two blank or unknown descriptions provide no such evidence, even when their text is equal.

## Reproduce and keep the evidence

The worked results were recomputed using the exact [source-trace candidate `ff9a08f0`](https://github.com/woahwhattheheck/commons/tree/ff9a08f04298e68a371f54f5b1f414d090755ebb/revenue/uiowa_rfq_18649_ai_coding). From that pinned component directory, use new destinations:

```sh
python rehearse.py --out /tmp/uiowa076-worked-new
python ai_coding.py /tmp/uiowa076-worked-new/synthetic/changes.json --out /tmp/uiowa076-worked-report-new
python -m unittest -v test_ai_coding.py test_source_trace.py
python -O -m unittest -v test_ai_coding.py test_source_trace.py
```

The unchanged [fixture generator](https://github.com/woahwhattheheck/commons/blob/ff9a08f04298e68a371f54f5b1f414d090755ebb/revenue/uiowa_rfq_18649_ai_coding/rehearse.py) creates all six histories and 77 source locators. Locator line numbers above refer to the generated `synthetic/sources/change_histories.md`, whose complete UTF-8 SHA-256 is:

```
8549abe0a62e79ff4993433c681e14336f55a2e0fda25b2534055946e1eadee5
```

Keep `synthetic/changes.json`, its retained sources, `report.json`, `report.md` and the manifest together. CSV is a convenient numeric summary, not a lossless evidence interchange. [The separate source-trace contract](https://github.com/woahwhattheheck/commons/blob/ff9a08f04298e68a371f54f5b1f414d090755ebb/revenue/uiowa_rfq_18649_ai_coding/SOURCE_TRACE_REVIEW.md) defines the added fields and missing-value boundary.

The exact four-Python-file closure passed **62 tests in each of normal, -O and -OO modes**, with no skips; [the dated execution receipt](https://github.com/woahwhattheheck/commons/pull/16320#issuecomment-5742748527) records source identities and literal outcomes. This is isolated component execution, not a hosted Actions, repository-wide, browser or native-Windows result. At that receipt's provider census the executable carrier remained open with queued hosted workflows. **Publishing this inert handout does not integrate or authorize that executable change.** Read the carrier's live state before relying on current-main repair availability.

## A defensible closing statement

“Our fictional examples include one lower-effort workflow, one higher-effort workflow despite faster authoring, and one unresolved delivery. We need task context, allocated effort, acceptance evidence, a defined follow-up window and relevant source bindings before interpreting a comparison. These examples tell us what to ask and what to retain; they do not tell us the University's current performance.”
