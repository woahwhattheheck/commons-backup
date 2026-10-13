# Washington County, Arkansas BID 2026-21 - teamable bid carrier

Operation: `WASHINGTON-COUNTY-AR-BID-2026-21-CONSTITUENT-COMMS-ZSOLFORGE-20260913`

This directory is an **internal qualification, teaming, and technical-evidence carrier** for Washington County Assessor's Office BID 2026-21. It is not a submitted bid, a partnership claim, a signed certification, a price commitment, an award, or recognized revenue.

## Source truth

The controlling nine-page packet was recovered from the public Google Drive link distributed for the solicitation and is bound in `source_ledger.json` by SHA-256 `930817f2052fc6fcc1616f2ee1ed5cb1352695e0b1635ab662a844e28a18c15f`.

Critical dates in the packet:
- interpretation requests: September 14, 2026 at 2:00 PM local County time;
- bids due: September 21, 2026 at 4:00 PM;
- bid opening: September 22, 2026 at 9:00 AM;
- submission: Beacon Bids, electronic.

## Decision

**Current route: TEAM / HOLD PARTNER CONFIRMATION. Do not present Token Junkie Labs / Commons as a qualified prime.**

The packet requires at least five completed, relevant public-service projects in the last seven years; at least one successful production CAMA/property-assessment/tax/permitting/equivalent system-of-record integration into an AI or multi-channel communications platform; a named experienced implementation lead; and a current VPAT or equivalent accessibility report. None of those prime-bidder facts is self-proven by this repository.

A credible route is an experienced GovTech platform vendor as prime, with TJLabs providing a **bounded paid technical subcontract workstream**: deterministic integration acceptance testing, cross-channel continuity tests, identity/read-only controls, historical-inquiry replay, regression receipts, and go-live validation evidence. `acceptance_harness.py` is a synthetic proof of that workstream, not a production-system claim.

## What the bid actually asks for

`requirements.json` preserves the source-bound mandatory gates. Key architecture requirements include one platform across voice/chat/live-chat/email, one Agency-controlled knowledge base, unified case history, live record-level property-system lookup, Agency-approved identity confirmation for account-specific data, multilingual voice, WCAG 2.1 AA, SPF/DKIM/DMARC, read-only CAMA integration including legacy systems without modern APIs, a ten-business-day two-channel review system, and staff validation against historical inquiries before public launch.

Commercially, the bid requires complete pricing for 50,000 voice interactions/year, CAMA integration, fifteen email/KB/chat licenses, implementation/configuration/knowledge-base build/on-site training, overages, extra licenses, SMS, and an all-in first-year total. Blanks and "negotiable/case by case" do not satisfy the check-off list.

## Commands

```bash
python -m unittest -v test_bid_carrier.py
python -O -m unittest -v test_bid_carrier.py
python qualification.py evidence_template.json
python - <<'PY'
import json
from pathlib import Path
from acceptance_harness import evaluate_scenario
p = Path('fixtures/synthetic_case.json')
print(json.dumps(evaluate_scenario(json.loads(p.read_text())), indent=2, sort_keys=True))
PY
```

## Authority ceiling

This carrier authorizes research, qualification, internal drafting, deterministic testing, GitHub coordination, and a truthful teaming package. It does **not** authorize buyer contact, partner contact, supplier/portal registration, bid upload/submission, signature, certification, pricing, contract acceptance, data/system access, spend, award, payment, or revenue recognition. External contact must also pass the swarm's organization-level collision fence so a hot lead is not contacted twice.
