# Spanish–English code-switch ASR carrier

This carrier targets the North American Spanish–English track of Mozilla Data Collective's **Lost in Transcription** competition. It does not contain competition audio, private transcripts, or model weights.

## Competitive thesis

Use two or more complementary **local open-weight** ASR models and choose a complete hypothesis by weighted minimum-Bayes-risk (MBR) decoding. Whole-hypothesis selection deliberately avoids token splicing that can destroy fluent intra-sentential code switches. Candidate risk combines cross-model edit disagreement, each adapter's acoustic confidence, and an optional Laplace-smoothed bigram prior trained **offline** from admitted local/public bilingual transcripts. The prior therefore learns actual Spanish↔English transition patterns instead of assuming language boundaries are clean.

`build_prior.py` hashes its source CSV and writes only aggregate n-gram counts. Raw training transcripts are not copied into the generated prior. `core.py` emits a per-utterance evidence digest plus disagreement/margin diagnostics; uncertain examples can be isolated for offline analysis without changing the required transcript-only submission schema.

## Runtime contract

Pinned upstream runtime commit: `c23d3d9942fea1d4d3e4325f6c0f2fe4d74273f6`.

The official environment runs root `main.py`, reads `/code_execution/data/submission_format.csv` and `/code_execution/data/clips`, and expects `/code_execution/submission/submission.csv` with `audio_filename,transcript`. Execution internet is blocked. The pinned environment includes `faster-whisper==1.2.1`; `submission_main.py` implements only that audited adapter and requires local model paths beneath the unpacked submission root.

## Truth / data boundary

- Never send competition audio or transcripts to hosted model APIs or hosted inference services.
- Keep competition data, external model weights, and derived raw transcripts out of Commons.
- External datasets must satisfy the competition's publication/licensing rules before they are used.
- Synthetic evidence in this repository is **not** a leaderboard or real-data result.
- Registration, terms acceptance, smoke-test upload, final upload, and prize/payment state are external account actions and are not claimed here.

## Next empirical ladder

1. On a local competition-data machine, fit `prior.json` from the track's development transcripts and preserve only its source hash + aggregate counts.
2. Bundle two runtime-compatible open-weight models with deliberately different error profiles (for example a multilingual Whisper-family model and a second locally runnable ASR family after runtime validation).
3. Measure each single model, confidence-only selection, disagreement-only MBR, and full MBR+prior on the development set using the organizer's scorer.
4. Tune only on development folds; freeze config before smoke test. Report corpus WER plus error slices at code-switch boundaries, Spanish-only spans, English-only spans, numbers, names, and high-disagreement clips.
5. Package deterministically with `pack.py`; verify archive + receipt before any authorized platform upload.
