# BidBridge — Pazhou AI for Women 2026 carrier

Operation: `PAZHOU-AI-FOR-WOMEN-BIDBRIDGE-ZDCF7L4-20260913`

BidBridge is a working, dependency-free prototype for the Fifth Pazhou Algorithm Competition “Algorithms for Good, A Smart Future for Women” **women-friendly AI product** lane.

It is an evidence-bound procurement/RFP review tool for women entrepreneurs and other small owner-led teams. It does **not** claim eligibility/compliance, contact issuers or partners, register vendors, submit questions/bids, make teaming commitments, sign contracts, move money, or make the owner’s go/no-go decision.

## What is here

- `index.html` — static public demo.
- `styles.css` — responsive presentation.
- `bidbridge.js` — browser/Node deterministic review core.
- `demo-opportunity.json` — fictional opportunity and evidence fixture.
- `test_bidbridge.mjs` — hostile focused tests.
- `business-plan.md` — competition-ready product/business proposal.
- `application-answers.md` — portal copy bank with explicit owner-only placeholders.
- `demo-script.md` — 3–5 minute demo/screenshot script.

## Run the demo locally

Use a static server so `fetch('./demo-opportunity.json')` works:

```bash
python3 -m http.server 8000 --directory .
```

Then open the competition folder through `http://localhost:8000/...`.

After this carrier is merged and GitHub Pages updates, the expected public path is:

`https://woahwhattheheck.github.io/commons/competitions/pazhou-ai-for-women-bidbridge-2026/`

Check it before calling it live.

## Test

```bash
node --check competitions/pazhou-ai-for-women-bidbridge-2026/bidbridge.js
node --test competitions/pazhou-ai-for-women-bidbridge-2026/test_bidbridge.mjs
node --no-addons --test competitions/pazhou-ai-for-women-bidbridge-2026/test_bidbridge.mjs
```

## Competition truth checked during preparation

Official topic page:  
https://www.aicompetition-pz.com/topic_detail/48

Official general guidelines:  
https://www.aicompetition-pz.com/guidelines

During the 2026-09-13 preparation pass, the live topic page stated that the women-friendly product lane:

- accepts teams up to 5 people;
- has no female-member minimum for this lane;
- requires a project application and project proposal;
- allows supplementary technical docs, demo/screenshots, qualifications and result/innovation evidence;
- lists a Sept. 15, 2026 registration deadline;
- lists ¥50,000 / ¥30,000 / ¥20,000 awards for first/second/third in each product sub-lane, subject to official qualification/result/tax rules.

The general guidelines state that submitted works are jointly owned by the participant and organizing committee and may be publicly displayed by the organizer under the stated terms. The owner must review the final portal terms before submitting any asset.

## Current truth boundary

Verified in this carrier:

- working static demo source;
- deterministic decision core;
- synthetic fixture;
- focused tests;
- competition/business-plan draft.

Not claimed:

- Pazhou account registration;
- submission;
- customer/pilot;
- women-owned customer;
- revenue;
- WOSB certification;
- legal compliance;
- award;
- organizer endorsement;
- Guangzhou deployment/partner.
