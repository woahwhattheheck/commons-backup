# Methods-ready notes — Indonesian–Javanese track

## Baseline

1. Start with an open-weight multilingual speech-to-text checkpoint that can run entirely offline in the official container.
2. Bundle the checkpoint with the submission; use `starter/main.py` as the container entrypoint.
3. Build a deterministic train/validation manifest from approved local metadata. Group by conversation/session/speaker when the schema exposes such a key.
4. Measure corpus WER with the pinned public scoring normalization.
5. Package through `cli.py pack`, record the ZIP SHA-256, then run the official runtime locally before any platform submission.

The included entrypoint uses `AutoProcessor` + `AutoModelForSpeechSeq2Seq` with `local_files_only=True`; it cannot silently download a checkpoint.

## Indonesian–Javanese error analysis

Code-switching makes language identification per token unreliable: many forms are shared or borrowed across Indonesian and Javanese. Treat transcript correctness as the objective rather than forcing a hard language tag.

For each validation error, classify at least:

- shared/borrowed lexical item
- Javanese speech-level/register form
- Indonesian affix or clitic
- Javanese affix or clitic
- named entity / place / acronym
- numeral / abbreviation
- hesitation, annotation, or unintelligible span
- spelling variant
- segmentation / compound-word boundary
- acoustic deletion, insertion, or substitution

Aggregate WER by these buckets **only using locally permitted annotations**. Do not send challenge text/audio to hosted APIs for classification.

## Candidate iterations

- **Scorer-aware diagnostics, not scorer gaming.** Keep raw model output and report normalized WER separately so improvements are linguistic/acoustic, not punctuation-only.
- **Language-model rescoring.** The pinned runtime includes KenLM + pyctcdecode. A locally trained/published-eligible Indonesian–Javanese text LM can be tested for shallow fusion if the chosen acoustic model exposes CTC logits.
- **Lexicon-free beam search.** Useful when code-switched words or names are absent from fixed lexicons.
- **Long-form chunking.** Validate boundary overlap and duplicate-word removal on synthetic clips before applying to competition audio.
- **Register robustness.** Track errors across Javanese ngoko/krama-like forms when approved labels permit it; do not invent register labels.
- **Acronym/casing behavior.** The official normalization intentionally preserves acronym-like sentence starts differently from ordinary sentence capitalization, so inspect that class.
- **External data.** Use only sources allowed by the rules. If an external dataset triggers Mozilla Data Collective publication obligations, preserve license/source metadata from day one.

## Submission-readiness checklist

- [ ] Re-read current official competition rules and runtime commit.
- [ ] Competition data stayed local; no hosted model/API exposure.
- [ ] External model/data licenses and publication obligations recorded.
- [ ] Validation grouping prevents obvious conversation/session leakage.
- [ ] `audio_filename` coverage exact; no duplicates or extras.
- [ ] Output header exactly `audio_filename,transcript`.
- [ ] `main.py` at ZIP root.
- [ ] Model files bundled; `local_files_only=True`.
- [ ] Official container local run succeeds with network blocked.
- [ ] Official smoke test (if used) recorded as smoke test, not leaderboard score.
- [ ] Methods/replay commands and final ZIP SHA-256 saved.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

