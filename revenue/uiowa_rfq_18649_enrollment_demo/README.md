# UIOWA-106 ESS/IAM enrollment-period change demonstration

Isolated path: `revenue/uiowa_rfq_18649_enrollment_demo/`

Two-stage, append-only synthetic timeline: an ESS registration-window change
and the IAM access-dependency that later evidence can actually support.
Later evidence **changes supportable conclusions without rewriting** the
stage-1 evidence history.

Consumes published UIOWA-023 field names and GRANITE UIOWA-031 additions
read-only (`revenue/uiowa_rfq_18649_evidence_register/`). Does not invent a
second register contract and does not edit occupied packages.

```bash
python3 cli.py --fixtures ./fixtures
python3 cli.py --out /tmp/uiowa106
python3 -m unittest test_demo.py
python3 -O -m unittest test_demo.py
```

See `walkthrough.md`. Not a University finding, live system, schedule, or outreach.

Closes woahwhattheheck/commons#16245.
