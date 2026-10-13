# Fort Worth 26-0263 AI-IVR validation/evidence carrier

Operation: `FORTWORTH-26-0263-IVR-EVIDENCE-ZHQR9T4-20260914`

This package is a **buyer-neutral, offline validation product** for AI-assisted municipal IVR/contact-center traces. It exists to turn a prime vendor's claims into deterministic claim → test → result evidence before a demo, proposal proof point, integration milestone, or acceptance test.

## Commercial posture

Public solicitation mirrors for City of Fort Worth RFP 26-0263 describe an enterprise-grade AI IVR platform spanning Cisco voice, web chat, SMS, outbound notifications, multilingual interaction, document grounding, Microsoft 365/Accela/ESRI integrations, U.S.-based processing, security/compliance controls, and local-government experience/reference requirements.

**Token Junkie Labs is not represented here as the qualified platform prime.** This package is positioned as a bounded specialist validation/evidence subcontract for a prime that already owns platform licensing, Cisco/Microsoft/municipal integration, bidder qualifications, references, security/compliance representations, pricing and submission authority.

The public-source summaries are provisional. This package does not authenticate the controlling City packet/addenda and cannot turn mirror text into bid authority.

## What v1 proves mechanically

- exact schema/type rejection and canonical input identity;
- current-source generation must match scenario generation before a grounded answer passes;
- `ANSWER` must use exactly the allowed source references;
- abstain/clarify/escalate/notify behaviors cannot smuggle answer citations;
- response language and channel must match the test contract;
- effect actions require the exact route/effect key and exactly one committed logical effect;
- exact event replay is idempotent; same event ID with changed content rejects;
- two distinct committed events for one effect fail as duplicate side effects;
- provider `UNKNOWN` plus a retry fails closed rather than pretending the first attempt did not commit;
- deterministic receipt/report verification rejects tamper;
- external contact/send/submission/production/payment/revenue authority remains mechanically false.

The synthetic portfolio covers voice/chat/SMS/outbound traces; English/Spanish/French samples; service navigation; permit/facility grounding; ambiguous/stale/conflicting-source behavior; after-hours/accessibility/emergency escalation; approved-notification exactly-once behavior; and a permit-workflow source seam. The sample is **not** a claim of the solicitation's full 20+/75+ multilingual requirement or a production integration.

## Run

```bash
python -m unittest -v revenue.fort_worth_ai_ivr_validation.test_core
python -O -m unittest -v revenue.fort_worth_ai_ivr_validation.test_core

python - <<'PY'
import json
from pathlib import Path
from revenue.fort_worth_ai_ivr_validation.synthetic import ready_packet
Path('/tmp/fw26-0263.json').write_text(json.dumps(ready_packet(), sort_keys=True), encoding='utf-8')
PY

python -m revenue.fort_worth_ai_ivr_validation.cli compile /tmp/fw26-0263.json --output-dir /tmp/fw26-0263-out
python -m revenue.fort_worth_ai_ivr_validation.cli verify /tmp/fw26-0263.json /tmp/fw26-0263-out/receipt.json /tmp/fw26-0263-out/report.md
```

## Truth ceiling

This package performs no City/prime outreach, Cisco/telephony call, SMS, email, outbound campaign, portal login/registration/submission, production integration, resident-data access, W-9/CIQ/small-business certification, signature, price acceptance, contract, award, payment, cash or revenue recognition.
