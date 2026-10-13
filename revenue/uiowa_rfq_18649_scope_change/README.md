# UIOWA-133 scope-change impact calculator

Isolated path: `revenue/uiowa_rfq_18649_scope_change/`

Runnable stdlib calculator and editable quotation worksheet for
**separately priced** scope changes on top of the published TJLabs
$24,000 subcontract workshare. In-scope defect corrections stay $0
incremental. Onsite/travel is a HOLD (travel is excluded from base).

This is not a University submission, invoice, payment, schedule, or
prime bid fee.

## Change catalog (PROPOSED / NOT ACCEPTED)

| Type | Hours | Proposed USD |
|---|---:|---:|
| `additional_group` | 32 | 2,400 |
| `extra_interview_cycle` | 12 | 900 |
| `new_analysis_domain` | 24 | 1,800 |
| `additional_readout` | 16 | 4,000 (the existing option) |
| `added_onsite_day` | 8 | HOLD — travel unauthorized |

## Five worked scenarios

See `scenarios/` (six including mixed correction + onsite HOLD). `fixtures/worksheet.json` is the editable blank. `sample_output/` holds the generated quotes.

```bash
python3 cli.py --worksheet scenarios/01_additional_group.json --out /tmp/uiowa133-g
python3 -m unittest test_calculator.py
python3 -O -m unittest test_calculator.py
```

Closes woahwhattheheck/commons#16185.
