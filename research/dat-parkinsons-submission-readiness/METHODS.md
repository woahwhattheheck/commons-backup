# Methods / provenance checklist

This kit separates **public submission mechanics** from **restricted competition data/model development**.

1. Keep all competition scans, labels, metadata, derived features, caches, and trained weights in the participant’s rule-compliant local environment. Do not paste or upload them to ChatGPT/Codex.
2. Pin the organizer runtime and verify the final model uses only packages present in that image.
3. Build validation splits locally from the actual permitted training metadata. Any patient/site/group leakage analysis must be performed locally from the real metadata; this public kit does not guess the dataset grouping fields.
4. Optimize/evaluate calibrated probabilities locally because the competition metric is log loss. Record calibration method and validation protocol in winner-ready documentation.
5. At inference, process each test scan independently. The runner in `contract.py` passes a predictor only the path for the current scan, never the other test rows or prior predictions.
6. Record every external dataset/model in an asset manifest with source, license, commercial-use confirmation, redistribution-in-submission confirmation, and organizer disclosure status. Human review of the actual license is still required.
7. Before packaging, run the data-exclusion guard. The public packer refuses NIfTI files and competition-format/output CSVs so accidental dataset publication is harder.
8. Run the organizer’s official local Docker test and an authenticated platform smoke test only from an eligible participant environment. Those steps are not performed or claimed here.
9. Do not claim leaderboard score, clinical performance, diagnostic utility, prize eligibility, submission, or award without the corresponding executed evidence.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

