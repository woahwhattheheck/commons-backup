# UIOWA-002 six/eight-week staffing and workshare planning model

Isolated path: `revenue/uiowa_rfq_18649_staffing/`

Editable staffing workbook, stdlib scheduler, and one-page role/calendar
view for the proposed TJLabs $24,000 / 160-hour technical workshare.
Dates are relative weeks. Hours are **assumptions**, not committed
staffing or observed University practice.

- Grouped interviews: **12 sessions** (ESS/RIS/IAM × four dimensions)
- 18/21/24 participant headcounts do **not** imply one interview per person
- Preparation → evidence → interviews → synthesis → review → correction
- Delays propagate; overflow that would fall off the horizon is refused
- Zero/invalid capacity is refused
- Onsite is a **subset** of productive interview hours, not additive
- TJLabs defaults **remote**; travel remains excluded
- Prime (Clark's), specialist (TJLabs), University inputs are distinct roles

```bash
python3 cli.py --workbook fixtures/workbook_8w.json --out /tmp/uiowa002
python3 -m unittest test_staffing.py
python3 -O -m unittest test_staffing.py
```

Not a schedule commitment, interview booking, travel authorization, or fee.

Closes woahwhattheheck/commons#16094.
