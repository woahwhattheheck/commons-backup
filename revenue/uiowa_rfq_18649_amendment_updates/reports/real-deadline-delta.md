# UIOWA-140 — real deadline requirement delta

Old documented state: `rfq18649-documented-state-pre-deadline-amendment`  
Current documented state: `rfq18649-documented-state-current-2026-09-19`

Repository provenance:
- Old carrier: `woahwhattheheck/commons@964ba1c328f70c770560bb4f999494b018c61103`, `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md`, which records **September 22, 2026, 3:00 PM Central**.
- Current change log: `revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_CHANGELOG.md`, which records **September 29, 2026, 3:00 PM Central** and identifies the University eBid RFQ 18649 public solicitation as controlling.
- Current clean exhibit on `main` also records **September 29, 2026, 3:00 PM Central**.

The public eBid page itself could not be fetched through the session web reader on 2026-09-19, so this carrier does **not** claim a fresh portal scrape. It demonstrates propagation from the saved/documented repository states and preserves the rule that the official solicitation must be re-read before external submission.

## Delta

Summary: **1 structured change, 2 unchanged commercial facts, 4 downstream field updates, 0 conflicts.**

| Requirement | Status | Old | New | Automatic? |
|---|---|---|---|---|
| REQ-BASE-WORKSHARE | UNCHANGED | USD 24000 | USD 24000 | no |
| REQ-OPTION-READOUT | UNCHANGED | USD 4000 | USD 4000 | no |
| REQ-RESPONSE-DEADLINE | STRUCTURED_CHANGE | September 22, 2026, 3:00 PM Central | September 29, 2026, 3:00 PM Central | yes |

## Affected proposal fields

| Field | Action | Before | After |
|---|---|---|---|
| `proposal.response_deadline` | UPDATED | September 22, 2026, 3:00 PM Central | September 29, 2026, 3:00 PM Central |
| `proposal.timeline.label` | UPDATED | September 22, 2026, 3:00 PM Central | September 29, 2026, 3:00 PM Central |
| `proposal.review_window.note` | UPDATED | September 22, 2026, 3:00 PM Central | September 29, 2026, 3:00 PM Central |
| `proposal.assumption.rfq_deadline` | UPDATED | September 22, 2026, 3:00 PM Central | September 29, 2026, 3:00 PM Central |
| `proposal.base_price` | RETAIN | USD 24000 | USD 24000 |
| `proposal.option_price` | RETAIN | USD 4000 | USD 4000 |

Unchanged facts keep their existing source binding. Changed structured fields are rebound to the current requirement source. A field that no longer equals either the old or the new structured value becomes `CONFLICT` and is not overwritten.

## Synthetic ambiguity case

`fixtures/synthetic_ambiguous_before.json` and `fixtures/synthetic_ambiguous_after.json` intentionally change “review support” to “review and certification support.” That wording can change scope and authority, so the tool emits `REVIEW_REQUIRED` rather than treating it as a text replacement.

This synthetic case is not an RFQ fact.

## Reproduce

```bash
python amendment_update.py \
  fixtures/real_deadline_before.json \
  fixtures/real_deadline_after.json \
  fixtures/proposal_before.json \
  --json-output /tmp/uiowa140.json \
  --csv-output /tmp/uiowa140.csv \
  --markdown-output /tmp/uiowa140.md

python -m unittest -v test_amendment_update.py
```

Expected authored-fixture result: **6/6 tests pass**.
