# Methods-ready notes

## Objective

Transcribe natural code-switched Spanish–Nahuatl audio. The organizer evaluates transcript accuracy with corpus word error rate after a documented text normalization stage.

## Baseline architecture

The committed baseline separates three concerns:

1. **Execution contract** — exact organizer file paths and output columns.
2. **Offline model hook** — a vendored Hugging Face ASR model is loaded only from `submission_src/model/`; network retrieval is disabled.
3. **Validation** — deterministic packaging, protected-audio exclusion, CSV key checks, and a stdlib scorer compatible with the organizer's published normalization.

With no model assets present, the entrypoint returns empty transcripts. This establishes the packaging/runtime road without inventing a model result.

## Competitive follow-through

A serious candidate should compare at least:

- a multilingual encoder-decoder checkpoint;
- a CTC model with character/subword decoding;
- optional KenLM shallow fusion if a legally redistributable Spanish–Nahuatl text corpus is available.

Preserve the competition reference orthography rather than aggressively normalizing Nahuatl variants. Tune any text normalization only against the organizer's score behavior; do not hide model errors by changing reference conventions.

## Reproducibility ledger

For every measured run record:

- competition dataset version and SHA-256 digests (metadata only in Commons);
- train/validation split algorithm and seed;
- external dataset/model names, exact revisions, licenses, and digests;
- runtime commit and Docker image/tag;
- training/inference command, hardware, wall time, and environment;
- model artifact digest;
- held-out WER from the organizer's scorer;
- final `submission.zip` SHA-256.

No leaderboard score, placement, award, or submission status belongs in this document until the corresponding authenticated action has actually occurred.

## Data fingerprint and split discipline

`tools/split_manifest.py` assigns each authorized local `audio_filename` to
train or validation by SHA-256 of `(seed, filename)`, records the exact source
CSV SHA-256, and deliberately omits transcript/metadata payloads. This gives a
reproducible split receipt without placing competition data in Commons.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

