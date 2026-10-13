# Methods-ready notes

## Objective

Build the smallest reproducible contract around the public 2026 RSNA Knee challenge interface before spending compute on a model. The test interface is image-only even though training can use paired multilingual report text, so any eventual system must avoid relying on report text at inference.

## Validation design

1. **Schema first.** Reject missing/reordered target columns, empty or duplicate `StudyInstanceUID` values, non-finite scores, and scores outside `[0,1]`.
2. **Metric parity.** Compute per-target ROC AUC and average all twelve targets, matching the published macro-AUC definition. Ties receive half credit.
3. **Leakage control.** `deterministic_group_split` assigns a whole group to one partition. When authenticated metadata is available locally, the group key should be the strongest non-leaking study/patient/site grouping permitted by the competition data contract.
4. **Offline execution.** The adapter and tests use the Python standard library and make no network calls. That keeps the readiness layer compatible with Kaggle's internet-disabled submission runtime.
5. **Reproducibility.** Artifact packaging sorts archive paths and fixes ZIP metadata timestamps/permissions, yielding byte-identical archives for identical inputs.

## Next modeling work in the compliant competition environment

- establish a simple image-only baseline before adding report-derived supervision;
- quantify target prevalence and missing-label behavior from the permitted training metadata;
- compare leakage-safe split strategies and report per-target AUC, not only the macro average;
- derive weak labels from multilingual reports only inside the accepted competition-data environment;
- profile inference wall time and memory because efficiency prizes are separate from leaderboard accuracy;
- record model/data licenses and provenance for every external asset.

These are planned experiments, not completed results. No competition data or score is represented in this repository.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

