# TITAN V4 Raw Replay Binding

`bind_raw_replay.py` closes the semantic boundary between an immutable Kaggle
replay JSON and the existing V4 replay-loss-autopsy tooling. It is custody and
provenance tooling only: it does **not** execute a candidate, the Kaggriculture
engine, or a promotion gate.

## Why this exists

The existing `extract_episode.py` summarizes already-derived CSV tables and
intentionally refuses to infer state or causality. A raw Kaggle replay has a
separate convention that must be authenticated before it can safely feed a
counterfactual: the action stored in replay state `i` is the action applied to
the preceding observation in state `i - 1`.

This binder makes that convention explicit and hash-bound. It rejects episode,
seat, metadata, step, action-shape, and non-finite-number ambiguity instead of
silently repairing it.

## Contract

Given exact replay bytes, an expected episode, and a recorded seat, the binder:

- SHA-256 hashes the **exact raw replay bytes**.
- Requires `info.EpisodeId` to match the requested episode.
- Requires a stable player count and a valid recorded seat.
- Reconciles team/submission identity from `TeamNames`, `SubmissionIds`, and
  `Agents` metadata; disagreement is fatal.
- Optionally requires an expected team and/or submission ID.
- Binds `steps[i][seat].action` to
  `steps[i-1][seat].observation.step` for every recorded action.
- Rejects missing actions, duplicate/non-increasing observation steps, boolean
  steps, non-finite JSON numbers, and malformed metadata.
- Emits deterministic canonical SHA-256 identities for the configuration and
  extracted open-loop action trace.
- Records terminal statuses/rewards as source facts without treating them as a
  causal explanation or current-V4 strength evidence.

The optional manifest and trace outputs use exclusive-create mode; an existing
artifact is never overwritten.

## Episode 108038484 handoff

Once the immutable replay is materialized, first inspect the replay metadata to
identify the opponent seat, then bind it with the known opponent submission:

```bash
python -B bind_raw_replay.py episode-108038484.json \
  --expected-episode 108038484 \
  --recorded-seat <opponent-seat> \
  --expected-submission 56158124 \
  --output episode-108038484.binding.json \
  --trace-output episode-108038484.opponent-trace.json
```

Do not guess the seat. If replay metadata omits submission identity, omit the
`--expected-submission` check only when an independent custody artifact binds
seat identity; the resulting manifest will honestly show the metadata that was
available.

## Boundaries with other V4 tooling

- `repairs/tooling/custody-audit/`: generic packet/file ingress and byte
  custody. This binder consumes already-materialized replay bytes and validates
  **replay semantics and action-step identity**.
- `research/replay-loss-autopsy/extract_episode.py`: summaries from derived CSV
  tables. This binder accepts the original replay JSON.
- `gauntlet_audit.py` / CHAINLOCK-style result provenance: experiment/result
  integrity. This binder does not authenticate a candidate result.
- Counterfactual replay: a later consumer may execute a candidate against the
  bound recorded action schedule. Once the new world diverges from the source
  replay, that opponent trace is open-loop historical stress, not an adaptive
  reconstruction of the original opponent.

No replay payloads are committed by this package, no gameplay component is
activated, and no default/archive/Kaggle state is changed.

## Validation

From this directory:

```bash
python -B -m unittest -v test_bind_raw_replay.py
python -O -B -m unittest -v test_bind_raw_replay.py
python -B -m py_compile bind_raw_replay.py test_bind_raw_replay.py
```

The focused suite includes episode/submission/team mismatch, metadata
contradiction, seat/player-count poison, missing actions, duplicate and boolean
steps, non-finite payloads, canonical trace hashing, exact source-byte hashing,
and fail-closed output overwrite behavior.

See `RAW-REPLAY-BINDING-RECEIPT.json` for the exact tested file identities.

## Donor provenance

The replay action/preceding-observation convention and explicit open-loop
counterfactual caveat were cross-checked against the public MIT-licensed
`Seyamalam/Kaggriculture` replay tooling. This implementation is independently
written and stdlib-only. See `RAW-REPLAY-DONOR-NOTICE.md`.
