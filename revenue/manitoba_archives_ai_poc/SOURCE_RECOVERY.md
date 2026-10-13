# Controlling-source recovery runbook

The pursuit remains on HOLD until the complete current solicitation package is recovered from the University of Manitoba / Euna official procurement surface.

## Recovery sequence

1. Navigate from an official University procurement page or the official Euna/Bonfire event to RFP `IT-0280-2627-LB`. Third-party tender indexes and search snippets remain discovery-only.
2. Acquire the solicitation and every currently published attachment, form, Q&A, and addendum. Preserve original bytes.
3. Compute SHA-256 for every acquired file. Assign stable source IDs and record the exact official locator, source kind, currentness, scope completeness, and supersession relation.
4. Extract the **controlling closing timestamp and timezone** from official evidence and normalize it to UTC. Do not infer Central time from buyer location.
5. Reconcile addenda before extracting requirements. A superseded source must be marked non-current before a successor may control.
6. Extract all mandatory, evaluated, and informational requirements with exact source ID + SHA + section/page/locator + source-faithful text.
7. Build the evidence register. `PROVEN` means an actual artifact reference plus SHA-256 exists. Unknown corporate facts stay `UNKNOWN`, `MISSING`, or `OWNER_ATTESTATION_REQUIRED`.
8. Re-run qualification. Do not proceed past any INVALID/HOLD state by interpretation or optimism.
9. Immediately before any owner-authorized external action, re-read the official event for new addenda, Q&A, deadline changes, forms, or submission-state changes.

## Topics that must come from the official package

Do not assume any answer in advance. Extract and source-bind:

- exact PoC use case, collections, record types, languages, modalities, metadata, OCR/transcription state, and expected outputs;
- whether University data is provided and under what access, hosting, residency, retention, deletion, confidentiality, security, privacy, records-management, ethics, or AI-use conditions;
- whether external/hosted models, APIs, open weights, fine-tuning, embeddings, or third-party services are permitted;
- expected environment, integration surfaces, identity/access model, infrastructure, software ownership/licensing, handoff, and reproducibility requirements;
- human-review, explainability, provenance/citation, accuracy, hallucination/abstention, bias, accessibility, audit, and acceptance criteria;
- discovery/workshop/interview expectations, stakeholder groups, onsite/remote requirements, schedule, milestones, and knowledge transfer;
- bidder/entity eligibility, consortium/subcontractor rules, local presence, insurance, references, past-project requirements, key-person qualifications, and conflicts;
- pricing form, currency/tax treatment, expenses, rate structure/caps, negotiation, payment milestones, and commercial terms;
- evaluation weights, mandatory pass/fail gates, demos/presentations/interviews, references, and scoring mechanics;
- required forms, signatures, file/page limits, naming, upload mechanics, Euna account requirements, late-bid rules, official question channel, and question deadline.

## Stop conditions

Keep the pursuit on HOLD if the official pack cannot be obtained, source identity is ambiguous, an addendum cannot be reconciled, the deadline/currentness cannot be verified, a mandatory requirement lacks truthful evidence, or an owner-only corporate fact is unresolved.

This runbook sends no buyer question and creates no procurement account.
