# UIOWA-140 — amendment-to-proposal update mechanism

Owner: **ZZ-Semaphore / GPT-5.6 Sol**  
Status: **proposal-preparation tooling; no submission or buyer contact**

This directory provides a deterministic local workflow for taking a normalized before/after requirement manifest and propagating safe structured changes into a proposal-state record.

It exists to prevent two opposite failures:

1. **stale proposal facts** surviving after an RFQ amendment; and
2. **over-automation** silently rewriting scope, pricing, or authority when wording changed and human interpretation is required.

## Files

- `amendment_update.py` — requirement comparator, guarded propagator, CSV/Markdown/JSON report generator.
- `fixtures/real_deadline_before.json` — repository-documented pre-amendment Sep. 22 deadline state.
- `fixtures/real_deadline_after.json` — repository-documented current Sep. 29 deadline state.
- `fixtures/proposal_before.json` — downstream proposal fields carrying the stale deadline plus unchanged $24k/$4k facts.
- `fixtures/synthetic_ambiguous_before.json` / `synthetic_ambiguous_after.json` — explicitly fictional scope-wording case that must stop for interpretation.
- `reports/real-deadline-delta.md` — worked requirement-delta report and provenance notes.
- `reports/real-deadline-affected-sections.csv` — machine-readable affected-section map.
- `reports/real-deadline-updated-proposal.json` — expected updated proposal state.
- `test_amendment_update.py` — six regression/hostile tests.

## Real deadline case and provenance

The repository itself preserves the documented change:

- commit `964ba1c328f70c770560bb4f999494b018c61103`, `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md`, records the earlier **September 22, 2026, 3:00 PM Central** response deadline;
- current `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_CHANGELOG.md` records the correction to **September 29, 2026, 3:00 PM Central** and identifies the University eBid RFQ 18649 solicitation as controlling;
- current `ACCEPTANCE_EXHIBIT.md` on `main` contains the September 29 deadline.

The session web reader could not access the IonWave public-detail page directly on 2026-09-19. Therefore this package does **not** claim a fresh portal scrape. It uses the saved/documented repository states for the worked propagation case and preserves the instruction that the controlling official solicitation must be refreshed before any external submission.

## Change classes

### UNCHANGED

Value and requirement text are unchanged.

- no proposal value rewrite;
- existing source binding is retained;
- the report records the clause as unchanged.

### STRUCTURED_CHANGE

A requirement is explicitly modeled as `change_type=structured_value`, the before/after values are both present, and the semantic `data_type` is stable.

This is the only class eligible for automatic replacement.

Even then, each downstream field is updated only when its current value exactly matches the old requirement value. A locally modified value becomes `CONFLICT`, not an overwrite.

### REVIEW_REQUIRED

Text/semantics changed without a safe structured replacement contract.

The tool records affected fields but does not modify them.

### ADDED / REMOVED

Requirement-set changes are surfaced for review. They are never treated as simple string replacements.

## Real worked result

The deadline fixture contains one structured change and two unchanged commercial facts.

Expected result:

- response deadline: Sep. 22 → Sep. 29;
- proposal timeline label: Sep. 22 → Sep. 29;
- review-window note: Sep. 22 → Sep. 29;
- RFQ deadline assumption: Sep. 22 → Sep. 29;
- proposed base workshare: **USD 24000 retained**;
- optional readout: **USD 4000 retained**;
- conflicts: **0**.

A second run against the already-updated proposal reports the four changed fields as `ALREADY_CURRENT`; it does not mutate them again.

## Synthetic ambiguity result

The fictional wording fixture changes:

- “Provide review support for prepared material.”
- to “Provide review and certification support for prepared material.”

That potentially changes scope and authority. Because it is modeled as semantic text rather than a declared structured value replacement, the comparator returns `REVIEW_REQUIRED`.

No RFQ fact should be inferred from that synthetic example.

## Run

```bash
cd revenue/uiowa_rfq_18649_amendment_updates

python amendment_update.py \
  fixtures/real_deadline_before.json \
  fixtures/real_deadline_after.json \
  fixtures/proposal_before.json \
  --json-output /tmp/uiowa140.json \
  --csv-output /tmp/uiowa140.csv \
  --markdown-output /tmp/uiowa140.md

python -m unittest -v test_amendment_update.py
```

Authored-fixture verification: **6/6 tests pass**.

## Adoption path for official saved material

The comparator intentionally works on normalized manifests instead of scraping arbitrary PDFs or HTML itself. For each newly saved RFQ version, attachment, or published Q&A:

1. preserve the source file/version and stable locator;
2. extract requirements into the manifest without discarding the source locator;
3. compare requirement IDs against the previous saved version;
4. declare a structured replacement only for a bounded field whose before/after values and semantic type are unambiguous;
5. map each requirement to affected proposal fields, prices, schedules, or assumptions;
6. run the updater;
7. resolve every `REVIEW_REQUIRED`, `CONFLICT`, or `MISSING_FIELD`;
8. re-check the controlling official material before external submission.

## Authority boundary

This tool reads local normalized material. It does not:

- send procurement questions;
- contact the University;
- submit a bid;
- certify an interpretation;
- schedule activity;
- authorize a price/scope change;
- treat a synthetic fixture as an RFQ requirement.

Automatic propagation is intentionally narrower than change detection.
