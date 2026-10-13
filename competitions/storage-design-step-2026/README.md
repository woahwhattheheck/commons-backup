# Storage Design STEP 2026 — FerroFrame

**Operation:** `DOE-STORAGE-DESIGN-STEP-ZRVQ7M2-20260913`

This workspace turns the DOE Storage Design Strategies to Ease Production (STEP) Phase 1 prompt into a
bounded engineering packet for **FerroFrame**, a proposed supplier-flexible manufacturing architecture
for an alkaline all-soluble iron redox-flow battery.

The electrochemistry is **not claimed as our invention**. Peer-reviewed work already demonstrates
all-soluble alkaline iron systems, including ferri/ferrocyanide paired with iron-gluconate. The proposed
contribution is a design-for-manufacture and supply-resilience architecture: standardized stack cassettes,
fewer bespoke wetted SKUs, qualification interfaces for multiple membrane suppliers, factory-dry / site-filled
system integration, and explicit cost/single-source sensitivity gates.

## Why this is a STEP fit

- stationary electrical storage with decoupled power and energy;
- emerging all-soluble iron chemistry rather than a mature commodity Li-ion pack;
- manufacturing architecture is the object of the entry, not an AI wrapper;
- design targets directly attack production complexity and single-source exposure;
- every quantitative literature value is source-bound and separated from entrant targets/assumptions.

## Package

- `submission/technical_narrative.md` — Phase 1 technical draft, under the 3,000-word limit.
- `submission/competitor_background_TEMPLATE.md` — owner-fillable background, deliberately unresolved.
- `submission/public_summary_slide.md` — one-slide copy/layout.
- `submission/video_script.md` — <=90 s script/shot plan.
- `evidence/sources.md` — literature + competition authority ledger.
- [Manufacturing prior-art review (2026-10-04)](evidence/prior_art_review_20261004.md) — nine-source comparison and unresolved design evidence.
- `model/production_model.py` — exact-decimal manufacturing scenario comparator.
- `model/example_*.synthetic.json` — intentionally synthetic examples, never supplier quotes.
- `validate_submission.py` + `readiness.json` — fail-closed release gate.

## Validation

```bash
python competitions/storage-design-step-2026/tests/test_model.py
python competitions/storage-design-step-2026/validate_submission.py
python competitions/storage-design-step-2026/validate_submission.py --require-ready  # intentionally exits 3 today
```

## Current truth state

`BLOCKED` for external submission. Missing gates include owner eligibility/background, independent novelty search,
quote-backed manufacturing inputs, EHS/hazmat review, final slide/video, human technical review, HeroX terms
acceptance, and explicit human submission authorization. No registration, submission, equipment purchase, prize,
award, or revenue claim is represented by this repository.

The dated [prior-art review](evidence/prior_art_review_20261004.md) identifies earlier disclosures and experiments
covering the proposed manufacturing features. The current packet does not yet demonstrate a design-specific
distinction or measured savings. This bounded review leaves all readiness gates false, including the independent
novelty-search and human-review gates; it assigns no official prize score.
