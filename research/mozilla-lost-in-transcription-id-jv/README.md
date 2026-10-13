# Mozilla Lost in Transcription — Indonesian–Javanese offline baseline kit

This directory is a **competition-safe engineering starter**, not a leaderboard submission and not a claim of any score. It intentionally contains **no competition audio, transcripts, credentials, or model weights**.

## What is pinned

The implementation contract was read from the official DrivenData runtime at commit `05b89385334512c8bff98f1bf35616df3ab0bca9` (2026-09-04). The corresponding source identities are recorded in `runtime-lock.json`.

At that pin:

- `submission.zip` must contain `main.py` at the ZIP root.
- The runtime executes without general internet access.
- Input clips are under `/code_execution/data/clips`.
- `submission_format.csv` supplies `audio_filename`.
- The entrypoint must write `/code_execution/submission/submission.csv`.
- The scorer expects `audio_filename,transcript` and computes corpus-level word error rate after text normalization.
- The runtime includes Python 3.12 plus `torch`, `torchaudio`, `transformers<5`, `librosa`, `qwen-asr`, `kenlm`, `pyctcdecode`, and related packages.

Re-read the official runtime before a real submission. The competition can update its image and contract.

## Included

- `toolkit.py` — pure-stdlib scoring-normalization diagnostics, corpus WER, exact CSV coverage validation, deterministic leakage-aware split generation, and byte-stable ZIP packaging.
- `cli.py` — commands for `score`, `validate`, `split`, `pack`, and `inspect`.
- `starter/main.py` — offline `transformers` speech-to-text entrypoint. It requires a competition-permitted open-weight checkpoint bundled under `starter/model/`.
- `test_toolkit.py` — synthetic-only tests. No challenge data is used.
- `METHODS.md` — baseline/research plan and language-specific failure-analysis checklist.
- `runtime-lock.json` — source pin and contract identities.

## Run synthetic tests

```bash
cd research/mozilla-lost-in-transcription-id-jv
python test_toolkit.py
```

## Local scoring

Ground truth and predictions both use:

```csv
audio_filename,transcript
clip001.wav,contoh transkrip
```

Then:

```bash
python cli.py score ground_truth.csv submission.csv
python cli.py validate submission_format.csv submission.csv
```

The local normalizer follows the public scorer behavior for diagnostics. The official scorer remains authoritative.

## Deterministic split

If training metadata has a conversation/session/speaker group column, keep each group on one side of the split:

```bash
python cli.py split train_metadata.csv split.csv \
  --group-column conversation_id \
  --validation-fraction 0.2
```

If no grouping field exists, omit `--group-column`; filenames become the stable split key. Prefer a real conversation/session key when available to avoid leakage.

## Package a submission

Copy `starter/` to a private working directory, place a rules-compliant local model under `model/`, then:

```bash
python cli.py pack /path/to/submission_src submission.zip
python cli.py inspect submission.zip
```

`pack` rejects archives without root `main.py`, uses sorted members and fixed ZIP timestamps, and prints a SHA-256 digest for readback.

## Data/model boundary

Competition audio and transcripts must remain in the approved local competition workflow and **must not be sent to third-party hosted model APIs or inference services**. This Commons directory therefore contains synthetic fixtures only.

Open-weight pretrained models are permitted by the published competition description, but model licensing and any external-data publication obligation must be rechecked for the exact model/data used. Do not commit competition data or model weights here.

## Status

Engineering baseline/tooling only. No registration, official smoke test, leaderboard submission, rank, prize, award, or payment is claimed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

