# Phase-1 narrative scaffold — NOT A SUBMISSION

This scaffold mirrors the first-party NIH Phase-1 review areas. It is intentionally incomplete where evidence is not present. Do not remove `OWNER_REQUIRED` markers without real evidence.

## 1. Problem, scientific rationale, and scope

**Prototype:** NOURISH Signal Notebook, a local-first application for recording diet/nutrition exposures, disease-specific or general symptom observations, externally obtained validated patient-reported outcome scores, and obvious context changes.

The prototype is designed to help a user organize repeated observations and inspect *descriptive* lag-aware within-person associations. It does not diagnose an autoimmune condition, recommend food or treatment, infer causality, or tell a user to start/stop medication or diet. Overlapping exposure windows are excluded from the matched summary, context changes are surfaced as warnings, sparse data is labeled, and every analysis carries raw-event provenance.

Validated instrument content is not embedded. The application records a score plus instrument/version/source metadata when the user already has an authorized score. This keeps the prototype extensible to PROMIS or disease-specific measures without republishing questionnaire items.

**OWNER_REQUIRED:** select disease-specific outcome measures and bind exact scientific rationale/licensing for each measure used in the actual entry.

## 2. Engagement

No patient, patient-advocacy, clinician, scientist, dietician, caregiver, focus-group, interview, or beta-testing engagement is claimed by this repository carrier.

**OWNER_REQUIRED:** real engagement evidence, who participated, what they asked for, and which design changes followed from that input. NIH explicitly scores this area.

## 3. Potential impact

The design aims to reduce three common self-tracking failure modes: data leaving the user's device by default, black-box personalized advice presented as medical truth, and correlations shown without sample-size/context warnings. Session data is local by default; research export is user-triggered and strips free-text notes; the analysis result is descriptive and auditably bound to event IDs.

**PROPOSED, NOT VALIDATED:** This architecture may make nutrition/symptom records easier to inspect or reuse in research workflows while preserving clearer uncertainty boundaries.

**OWNER_REQUIRED:** beta/usability evidence and any real-world impact claim.

## 4. Feasibility

The prototype is dependency-free browser JavaScript. It runs without a backend or network request, accepts local JSON imports, exports a reduced research JSON file, includes synthetic demonstration data, and separates event normalization from analysis logic so the calculation is reproducible under Node tests.

The current interoperability surface is a documented, versioned JSON research export—not an EHR certification claim. A future adapter can map records into a study's chosen standard after code-system and workflow requirements are known.

**OWNER_REQUIRED:** privacy/security review, accessibility review with real assistive-technology testing, deployment/maintenance plan, and any care-workflow integration claim.

## 5. Innovation

The proposed distinction is not another food diary. It is an *evidence notebook*: explicit raw-event provenance, lag-aware matched descriptive windows, overlap exclusion, context-change warnings, no hidden cloud transfer, and an intentional refusal to turn association into dietary or therapeutic advice.

The prototype is compatible with externally scored validated measures without distributing their item text. This supports evidence-based outcome tracking while respecting instrument provenance and licensing boundaries.

## AI-use disclosure

This carrier was developed with OpenAI GPT-5.6 Sol assistance. The challenge rules observed on 2026-09-14 permit AI tools in development when usage is fully disclosed. The final submitter must review and adapt this disclosure to the actual work and any subsequent contributors/tools.
