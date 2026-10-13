# Official-local v2 vs v3 A/B runner

Status: execution tooling for the same ARC-AGI-3 paid lane. This runner does not submit to Kaggle or the ARC competition and does not replace stable v2 or experimental v3.

## Purpose

The organizer's pinned `ARC-AGI-3-Kaggle-Starter` exposes `scripts/play_local.py`, which runs `agent/my_agent.py` through `arc_agi.Arcade(OperationMode.NORMAL)` and the official `Agent.main()` loop, then reports per-game state, levels completed, action count, and the aggregate scorecard score. `compare_official_local.py` wraps that exact local runner so a cloud peer can compare stable v2 and experimental v3 under one game/version/action budget without manually swapping files.

Pinned starter evidence used when authoring this wrapper:

- starter commit: `eeb1535404f321d280a8f9194bbc1d7aca5f05fc`
- official `scripts/play_local.py` Git blob: `6e11153821c5716f64971fba853351ec64636080`
- stable v2 merge anchor: `accb281bf95acd9a43a97cd5f68738e7095d9fe0`
- experimental v3 merge anchor: `e96eed4374b1fe12f116d6d20d889bf3a7700423`

## What the wrapper does

1. Reads the starter's original `agent/my_agent.py` bytes and SHA-256.
2. Calls the official local runner with `--list` and resolves the requested short game ID to the exact versioned environment ID.
3. Generates the experimental one-file v3 candidate from the current stable sibling `../kaggle_my_agent.py` using `build_kaggle_v3.py`.
4. Copies stable v2 into `agent/my_agent.py`, invokes the official `scripts/play_local.py`, and stores exact stdout/stderr logs plus SHA-256 hashes.
5. Repeats the identical command/action budget with generated v3.
6. Restores the starter's original `agent/my_agent.py` in a `finally` block even if one arm fails.
7. Re-runs official `--list` and requires the exact game version to be unchanged before/after for the receipt to be marked comparable.
8. If the starter is a Git checkout, records `git rev-parse HEAD` and marks a commit mismatch non-comparable unless `--starter-commit` was deliberately changed to the actual revision.
9. Writes `ab-receipt.json` with both arm commands, exits, parsed score/levels/actions/state, agent hashes, log hashes, version IDs, starter commit evidence, restoration status, and an explicit `competition_submission_performed: false` field.

The wrapper invokes no Kaggle provider action and has no submission code path.

## Usage

From a Commons checkout at the current ARC3 merge, using a clean official starter checkout with its normal `make setup` already completed:

```bash
cd research/arc-agi-3/experimental
python compare_official_local.py \
  --starter-root /path/to/ARC-AGI-3-Kaggle-Starter \
  --game ls20 \
  --max-steps 400 \
  --output-dir /tmp/sol-arc3-ab-ls20
```

If the official starter has intentionally advanced from the pinned revision, pass that exact audited 40-character commit:

```bash
python compare_official_local.py \
  --starter-root /path/to/ARC-AGI-3-Kaggle-Starter \
  --starter-commit <audited-exact-commit> \
  --game ls20 \
  --max-steps 400 \
  --output-dir /tmp/sol-arc3-ab-ls20
```

Return these files/hashes to the canonical ARC3 Slack thread:

- `ab-receipt.json`
- `stable_v2.stdout.txt` / `.stderr.txt`
- `experimental_v3.stdout.txt` / `.stderr.txt`
- the receipt SHA-256 printed by the wrapper
- if the official runtime separately emits recordings or native scorecard files, their exact hashes as additional evidence

Do **not** interpret a synthetic unit test or the existing 63→21 corridor result as this official-local result. The A/B receipt is only comparable when both arms exit successfully, parse one result for the requested game, use the same exact environment version, and the original starter agent is restored.

## Offline verification

The local wrapper test uses a fake starter whose `scripts/play_local.py` follows the official output contract; it does not require `arc_agi` to be installed.

```bash
python -m py_compile compare_official_local.py test_compare_official_local.py
python test_compare_official_local.py
```

Authoring checkpoint: **4/4 PASS**, plus both `py_compile` checks PASS. Tests cover a complete A/B receipt, exact environment version evidence, parsed score/action differences, SHA-256 log evidence, original-agent restoration, parser refusal without a game row, positive action-budget enforcement, and absence of a competition-submission invocation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

