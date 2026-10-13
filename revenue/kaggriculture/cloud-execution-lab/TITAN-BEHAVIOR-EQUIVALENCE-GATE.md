# TITAN behavior-equivalence arm ledger

Operation: `TITAN-V3-BEHAVIOR-EQUIVALENCE-ARM-LEDGER-20260910-01`

This gate prevents two opposite evidence failures in a large candidate swarm:

1. the same executable is registered repeatedly under different candidate labels, consuming screening and validation budget while making one behavior look plural;
2. two candidates return equal action tapes, but their world, terminal, or economic effects differ and are incorrectly called equivalent.

It is an additive measurement/control-plane tool. It never runs a policy, changes a candidate, adjusts alpha, reserves validation seeds, selects an arm, promotes an archive, or touches Kaggle/provider state.

## Two stages, two different meanings

### 1. Pre-result executable preflight

`preflight` consumes only a family declaration marked `declared_before_results: true`. Every candidate must bind:

- candidate ID and archive SHA-256;
- an entrypoint;
- an invocation-contract SHA-256;
- a complete executable-closure manifest;
- the SHA-256 derived from the canonical closure manifest.

An executable identity is the exact tuple:

```text
(entrypoint, executable_closure_sha256, invocation_sha256)
```

If two labels have the same tuple, the family is refused before any outcome is consumed. This is the only class the tool marks safe for registration deduplication.

The closure is not accepted as a naked digest. It must contain a complete, nonempty list of canonical relative paths with lowercase SHA-256 and byte count. Absolute paths, `..`, dot aliases, backslashes, NUL, duplicate paths, missing entrypoint files, contradictory archive identities, duplicate JSON keys, and non-finite JSON are rejected. The closure digest is recomputed over sorted canonical member records.

The upstream package/source owner remains responsible for proving that the member manifest was derived from the actual executable bytes. This tool binds and compares that authenticated manifest; it does not materialize candidate archives itself.

### 2. Post-run observational report

`analyze` first requires a passing preflight, then consumes a complete common grid for every declared candidate. Every candidate and cell must bind the family, archive, closure, invocation, engine, evaluator, opponent, seed, and candidate seat. Each matchup requires exactly seats `{0,1}`.

Each completed cell must contain:

- `action_tape_sha256`: ordered pre-interpreter candidate actions;
- `world_tape_sha256`: ordered world/transition evidence;
- `terminal_state_sha256`;
- finite `own_cash`, `rival_cash`, and coherent `margin`;
- coherent `WIN`, `TIE`, or `LOSS` outcome.

The candidate schedule is recomputed from `(environment_seed, opponent_sha256, seat)` and must equal the predeclared schedule SHA-256. Missing, duplicate, failed, timed-out, one-seat-only, relabeled, differently scheduled, or non-finite cells fail closed.

The report emits three deliberately different classifications:

- **Observational behavior alias:** action, world, terminal, and economic envelopes are identical in every complete cell, despite distinct executable identities. This is reporting only.
- **Action-only contradiction:** action tapes are identical but at least one world, terminal, or economic effect differs. The verdict is `HOLD_ACTION_EFFECT_CONTRADICTION`.
- **Score-only alias:** economic outcomes match while action/world/terminal behavior differs. It is never collapsible.

Observational equality on a finite discovery grid does **not** prove global program equivalence. It cannot be used to reduce a family after seeing results, recycle validation seeds, share validation outcomes, alter Holm/alpha spending, select a winner, or claim promotion.

## Family schema

```json
{
  "schema": "titan-behavior-family/v1",
  "family_id": "screen-20260910",
  "declared_before_results": true,
  "engine_sha256": "<64 lowercase hex>",
  "evaluator_sha256": "<64 lowercase hex>",
  "schedule_sha256": "<canonical schedule SHA-256>",
  "candidates": [
    {
      "candidate_id": "arm-a",
      "archive_sha256": "<64 lowercase hex>",
      "entrypoint": "main.py::agent",
      "invocation_sha256": "<64 lowercase hex>",
      "executable_closure_sha256": "<derived SHA-256>",
      "executable_closure": {
        "schema": "titan-executable-closure/v1",
        "complete": true,
        "members": [
          {"path": "main.py", "sha256": "<64 lowercase hex>", "bytes": 1234},
          {"path": "TITAN-CONFIG.json", "sha256": "<64 lowercase hex>", "bytes": 456}
        ]
      }
    }
  ]
}
```

`family_sha256` may be supplied. When present, it must equal the canonical digest recomputed by the gate.

## Observation schema

```json
{
  "schema": "titan-behavior-observations/v1",
  "family_sha256": "<derived family SHA-256>",
  "engine_sha256": "<family engine SHA-256>",
  "evaluator_sha256": "<family evaluator SHA-256>",
  "schedule_sha256": "<family schedule SHA-256>",
  "candidates": [
    {
      "candidate_id": "arm-a",
      "archive_sha256": "<family archive SHA-256>",
      "entrypoint": "main.py::agent",
      "invocation_sha256": "<family invocation SHA-256>",
      "executable_closure_sha256": "<family closure SHA-256>",
      "games": 2,
      "cells": [
        {
          "status": "COMPLETE",
          "candidate_archive_sha256": "<family archive SHA-256>",
          "candidate_executable_closure_sha256": "<family closure SHA-256>",
          "candidate_invocation_sha256": "<family invocation SHA-256>",
          "engine_sha256": "<family engine SHA-256>",
          "evaluator_sha256": "<family evaluator SHA-256>",
          "environment_seed": 101,
          "opponent_sha256": "<opponent archive SHA-256>",
          "seat": 0,
          "action_tape_sha256": "<ordered action SHA-256>",
          "world_tape_sha256": "<ordered world SHA-256>",
          "terminal_state_sha256": "<terminal SHA-256>",
          "own_cash": 1200,
          "rival_cash": 1100,
          "margin": 100,
          "outcome": "WIN"
        }
      ]
    }
  ]
}
```

The abbreviated example shows one cell; a valid matchup must contain both seats, and every declared candidate must contain the identical full schedule.

## Commands

```bash
python -B titan_behavior_equivalence_gate.py preflight \
  --family FAMILY.json \
  --json-out PREFLIGHT.json \
  --markdown-out PREFLIGHT.md \
  --ledger RECEIPTS.jsonl

python -B titan_behavior_equivalence_gate.py analyze \
  --family FAMILY.json \
  --observations OBSERVATIONS.json \
  --json-out EQUIVALENCE.json \
  --markdown-out EQUIVALENCE.md \
  --ledger RECEIPTS.jsonl

python -B titan_behavior_equivalence_gate.py verify-ledger \
  --ledger RECEIPTS.jsonl \
  --json-out LEDGER-VERIFY.json
```

Exit status is `0` only for `PASS`; refusals and HOLD verdicts return `2`.

## Deterministic receipts and ledger

Every preflight and analysis report is sealed with `receipt_sha256`, computed over canonical finite JSON without the receipt field. Optional JSONL ledger entries are sequence-numbered and chain `previous_entry_sha256` to `entry_sha256`. Existing entries are fully verified before and after each append. Mutation, deletion, insertion, reordering, blank lines, broken sequence, or broken hashes is detected.

The ledger is a receipt chain, not a substitute for retaining the referenced family, observation, archive, and action-envelope bytes.

## Composition boundary

This child is designed to consume, not duplicate, the other live TITAN evidence lanes:

- paired-ledger custody supplies per-row candidate binding and exact two-seat topology;
- canonical action-envelope work supplies ordered action/world/terminal digests;
- familywise selection owns complete-family registration, clustered statistics, Holm correction, alpha spending, and validation-seed reservation/reuse.

This tool contributes only pre-result exact-executable duplicate refusal and post-run behavior-equivalence reporting. Its output must remain upstream evidence, never an independent score or promotion verdict.

## Contract coverage

The focused suite includes predecessor killers for:

- duplicate candidate labels and exact executable aliases;
- naked/tampered closure digests, incomplete closure manifests, unsafe and duplicate paths, and absent entrypoint files;
- same closure under a different invocation or entrypoint;
- archive/closure/invocation relabeling at candidate and row level;
- one-seat-only, missing, duplicate, failed, differently scheduled, and mismatched candidate grids;
- row/candidate order dependence;
- one-cell action drift;
- equal actions with unequal world or terminal effects;
- score-only equality with different behavior;
- incoherent cash, margin, and W-T-L;
- boolean seeds, non-finite JSON, duplicate JSON keys, wrong counts, and stale declared digests;
- forged report receipts and tampered append-only chains;
- CLI JSON/Markdown/ledger production.
