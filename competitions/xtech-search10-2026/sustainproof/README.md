# xTech|Search 10 — SustainProof carrier

**Operation:** `XTECH-SEARCH10-SUSTAINPROOF-ZIRONCLAD-20260914`  
**Builder:** Z-IRONCLAD / GPT-5.6 Sol

This is a source/test/readiness carrier for a non-weapon **Adaptive Sustainment** concept: an offline, evidence-bound reconciliation layer for maintenance, parts, and inspection handoffs across intermittent connectivity.

## What is implemented

`SustainProof` is not proposal-only. `sustainproof.py` implements a deterministic reconciliation kernel with strict event schemas, exact duplicate collapse, changed-ID refusal, monotone generation chains, predecessor-digest binding, same-generation semantic-fork detection, stale/future evidence holds, parts/inspection composition, deterministic receipts, and hard-false external authority. `cli.py handoff` runs it on local JSON.

`qualification.py` separately compiles a fail-closed owner-review packet for xTech eligibility/support evidence. It pins the normalized current official competition fact set in code, requires fresh owner evidence for entity facts (including SBIR small-business requirements, affiliate-inclusive size, ownership/control, and the one-submission slot) and an explicit current federal-support census, surfaces substantially-same federal-support collisions, and **never** claims an Army eligibility determination or submission authority.

`white_paper.md` is a rubric-aligned three-section drafting source. It is **not** represented as the sponsor's final three-page template. `validate_white_paper.py` checks page-source markers, rubric tags, authority wording, and bounded drafting size before human transfer into the mandatory template.

## Official public facts captured 2026-09-14

Current official Army sources in `official_sources.json` (including the controlling eight-page RFI) record the xTech|Search 10 white-paper deadline as **2026-10-19 17:00 ET / 21:00Z**; the competition page describes eligible firms as small independent U.S. for-profit businesses with **<=500 employees including affiliates** plus ownership/control and SBIR small-business restrictions and a no-substantially-same funded/current/pending federal-support rule. The RFI permits **one submission per eligible entity** and requires an exact **three-page** concept white paper in the sponsor template and weights scoring **40% Technical Approach / 25% Army Benefits / 25% Commercial Potential / 5% Introduction / 5% Proposal Quality**. The current competition/Army SBIR pages advertise up to **50 x $5k** semifinalists, **20 x $20k** finalists, finals prizes **$200k / $100k / $50k**, and an opportunity for finalists to submit Phase-I SBIR/STTR proposals worth up to **$300k**. The live sponsor RFI/template is controlling at submission time.

Sources:
- https://xtech.army.mil/competition/xtechsearch10/
- https://armysbir.army.mil/topics/xtechsearch-10-competition/
- https://xtech.army.mil/wp-content/uploads/2026/09/xTechSearch-10-Competition-RFI_Final-1.pdf

## Commands

```bash
python competitions/xtech-search10-2026/sustainproof/cli.py handoff \
  --input competitions/xtech-search10-2026/sustainproof/sample_handoff.json \
  --historical-as-of 2026-09-14T04:00:00Z

python competitions/xtech-search10-2026/sustainproof/cli.py qualify \
  --input competitions/xtech-search10-2026/sustainproof/eligibility.example.json \
  --historical-as-of 2026-09-14T04:40:00Z

python competitions/xtech-search10-2026/sustainproof/cli.py white-paper-check
python -m unittest discover -s competitions/xtech-search10-2026/sustainproof -p 'test_*.py' -v
python -O -m unittest discover -s competitions/xtech-search10-2026/sustainproof -p 'test_*.py' -v
```

The checked-in eligibility example intentionally compiles to a blocked state because legal-entity/ownership facts have not been supplied to this carrier.

## Authority ceiling

No portal registration or login, terms acceptance, entity-slot reservation/consumption, Army contact, proposal submission, signature, price commitment, purchase, maintenance dispatch, parts order, provider write, SBIR/STTR proposal, award, prize, payment, or recognized revenue is authorized or claimed by this source package.
