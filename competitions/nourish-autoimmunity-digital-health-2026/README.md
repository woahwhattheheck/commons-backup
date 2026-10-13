# NOURISH Signal Notebook — NIH NOURISH Digital Health Challenge carrier

A real browser prototype plus evidence/readiness carrier for the 2026 NIH **NOURISH: Autoimmunity Digital Health Challenge**.

## What works now

Open `app.html` in a modern browser (or serve the directory with any static server). The app:

- records session-local diet/nutrition exposures with user-defined tags;
- records general or disease-specific symptom severity observations;
- records *scores* from externally administered validated measures with instrument/version/source provenance, without copying questionnaire items;
- records obvious context changes (medication, sleep, stress, activity, intercurrent illness, menstrual cycle, other);
- computes deterministic pre/post descriptive association windows;
- excludes overlapping exposure windows from the matched aggregate;
- surfaces sparse data, missing windows and nearby context changes;
- labels every result `DESCRIPTIVE_ASSOCIATION_NOT_CAUSATION`;
- imports local event JSON and exports a reduced research JSON file with free-text notes removed;
- ships synthetic demo data that contains no patient information;
- makes no network request and has no backend.

It does **not** diagnose, prescribe, recommend diets, infer causality, replace clinical care, or claim FDA/medical-device status.

## Challenge truth

First-party NIH source observed 2026-09-14:

- challenge launched September 1, 2026;
- Phase 1 submission window opens October 1, 2026;
- total purse up to $650,000;
- up to ten Phase-1 prizes of $20,000 each;
- Phase 1 requires registration, a narrative, and a 3–5 minute prototype video;
- judging weighs scientific rationale/scope, engagement, impact, feasibility, and innovation equally;
- privacy/security, accessibility, interoperability and sustainability matter;
- AI-assisted development is permitted if fully disclosed;
- real patient/community/interdisciplinary engagement is judged.

Canonical source: <https://www.nih.gov/challenges/nourish-autoimmunity-digital-health-challenge>

## Important evidence boundary

This repository does **not** claim:

- actual entrant eligibility;
- challenge registration or terms acceptance;
- patient, advocacy-group, clinician, scientist, dietician or caregiver engagement;
- clinical validation or beta testing;
- ownership/licensing of questionnaire item text;
- a submitted entry, award, payment, or recognized revenue.

Run `node readiness.mjs` through the tests or consume `evaluateReadiness()` with actual owner facts. The template intentionally returns HOLD until external facts are proven.

## Why validated scores instead of embedded questionnaires

NIH catalogs PROMIS and other common data elements, and PROMIS is a public patient-reported outcome system. Exact instrument use/distribution can still carry source/version/usage terms. This prototype therefore stores an already-obtained score plus provenance rather than copying instrument items into a public repository.

## Descriptive analysis contract

Given a diet tag and an outcome domain, the engine builds a pre-exposure baseline window and a post-exposure window around each matching exposure. It calculates each window's mean change only when both sides have observations and excludes windows that overlap neighboring matching exposures. Nearby context changes are preserved as warnings.

This is an audit-friendly descriptive summary, **not causal inference**. Repeated observations can still be confounded by medication changes, illness, sleep, activity, selection effects, measurement error, regression to the mean and many other factors.

## Privacy model

- no server;
- no analytics;
- no `fetch`, XHR, WebSocket or beacon transport;
- session-memory only unless the user explicitly exports a local file;
- research export pseudonymizes event IDs and removes private notes, diet labels, and context values; it is still explicitly labeled sensitive and **not de-identified**.

This is a prototype privacy architecture, not a HIPAA certification or comprehensive threat model.

## Tests

```bash
node --test test_core.mjs test_readiness.mjs
```

Tests cover deterministic replay, future timestamps, duplicate IDs, invalid symptom/score bounds, overlapping exposure exclusion, sparse-data warnings, context-confounder warnings, causal-language leakage, reduced-export pseudonymization/text removal, and the fail-closed external readiness contract.

## Submission work still required

1. Establish actual entrant eligibility and register through the official challenge portal.
2. Engage real people living with autoimmune disease and/or patient advocacy groups plus relevant scientific/clinical/nutrition expertise; document resulting design changes.
3. Select and bind actual disease-specific and general measures, including exact permitted use and scoring provenance.
4. Conduct privacy/security/accessibility review and real user testing.
5. Produce final six-page-or-less narrative and 3–5 minute demo video against the then-current rules.
6. Re-read the official page immediately before submission for deadline/rule changes.

See `narrative_scaffold.md`, `sources.json`, and `owner_evidence.template.json`.
