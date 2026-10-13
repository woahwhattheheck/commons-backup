# Proposed Technical Concept — Evidence-Bound Adaptive Water Intelligence

Status: `PROPOSED_NOT_ACCEPTED`
Primary fit: Water4All 2026 Topic 3
Secondary fit: Water4All 2026 Topic 1

## Problem framing

Water managers often receive heterogeneous observations from sensors, laboratory records, cameras, operational logs, forecasts, and human reports. The hard problem is not only prediction. It is preserving the provenance and uncertainty of each observation while producing recommendations that remain explainable, reviewable, transferable between sites, and safe around physical infrastructure.

The proposed role is a bounded technical work package that turns partner-owned monitoring evidence into **owner-review decision support**. It does not autonomously actuate infrastructure, replace domain or regulatory judgment, or claim a pilot that has not occurred.

## Proposed architecture

1. **Evidence ingestion.** Versioned adapters normalize partner-supplied sensor and observation records while retaining source identifiers, capture times, completeness, and content commitments.
2. **Multimodal fusion.** Deterministic joins expose agreement, gaps, and conflicts between physical observations, images, laboratory evidence, operational events, and contextual data.
3. **Uncertainty-aware analytics.** Models emit distributions, intervals, calibration evidence, missing-data disclosures, and declared failure modes rather than a single unqualified score.
4. **Anomaly and infrastructure risk review.** Candidate anomalies are linked to the exact evidence generation and routed to a human review queue.
5. **Adaptive recommendation layer.** Scenario comparisons produce bounded recommendations and counterfactuals. No recommendation is itself an actuation command.
6. **Receipt and replay.** Inputs, model/version descriptors, outputs, dispositions, and owner decisions are content-bound so a result can be reproduced or invalidated when evidence changes.

## Capability-evidence boundary

The readiness compiler requires exact repository, 40-hex commit, repository-relative path, 64-hex content digest, observation time, and verified capability tags. Narrative text cannot promote a capability. Missing Topic 1 or Topic 3 tags remain `HOLD_TECHNICAL_EVIDENCE`.

No current owned-repository evidence is asserted by this static concept note. `example_input.json` intentionally contains no technical evidence and therefore remains blocked.

## Proposed acceptance criteria

- Every recommendation identifies the exact source and model generations it used.
- Missing, stale, conflicting, or future evidence fails closed.
- Calibration, uncertainty, and baseline methodology are declared before performance is reported.
- Pilot data authority, privacy, security, and publication rights are approved by the responsible partner.
- No model output directly mutates pumps, valves, treatment settings, accounts, or provider systems.
- Cross-site transferability is measured rather than inferred.
- Null and negative results remain part of the retained evidence record.
- Commercial scope, IP, publication, and support responsibilities are accepted before delivery begins.

## Partner composition hypothesis

A credible consortium would need funded water-domain, field-validation, and EU/associated coordination authority around the technical work package. The public official partner-search profiles retained in `partner_shortlist.json` are research evidence only. They are not endorsements, commitments, or contact authorizations.

## Commercial boundary

The preferred path is a paid technical teaming or subcontract scope with objective deliverables and acceptance criteria. No amount is quoted here. No partner has accepted a scope. No external contact, consortium commitment, self-funding pledge, proposal submission, award, payment, or revenue is claimed.
