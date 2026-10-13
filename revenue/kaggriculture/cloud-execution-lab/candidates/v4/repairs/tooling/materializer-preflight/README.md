# TITAN V4 materializer preflight repair — custody packet

This directory preserves the completed source-only repair from lane `V4-MATERIALIZER-OPTIMIZATION-PREFLIGHT-20260911-01` inside the sole canonical V4 workspace on `main`.

Target donor: `revenue/kaggriculture/cloud-execution-lab/candidates/v4/donor/apply_v4.py`

Tested preimage Git blob: `f67f8ce7d5f5779c1fad9b1e51e3b736b02b513d`

Tested postimage Git blob: `a180e59c22fa90d675aff031678ff1f7a59ce3c3`

The repair is intentionally source/tooling only. It does not activate gameplay, alter any of the 13 literal gameplay edits or 12 feature keys, change defaults, touch the production archive, create a successor V4 branch, or authorize execution of the legacy materializer against the current production runtime.

## Defects closed

1. `_replace_once()` used `assert`, so `python -O`/`-OO` removed the exact-once validation.
2. feature-key collision checks also used `assert`, allowing optimized execution to overwrite an existing key.
3. router/runtime files were written before later source/config validation completed, so a late failure could leave partial rewrites.

The patch replaces optimization-elidable assertions with explicit `AssertionError` checks and defers all output writes until source replacements, configuration validation, and JSON serialization have succeeded.

## Validation receipt

The finished local harness passed 24/24 tests under normal Python, `-O`, and `-OO`; the selected predecessor negative control failed as expected with eight failure events. `git apply --check`, exact postimage comparison, and double-apply rejection also passed. See `VALIDATION.json` for hashes and scope.

This is validation preflight, not crash-atomic multi-file publication. No full-game, leaderboard, current-production ABI, or official checker-acceptance claim is made.

## Integration rule

`candidates/v4/CANONICAL.json` remains authoritative: `main` is the sole integration line and the legacy donor materializer must not be executed against current production. The current materializer/checker owner should consume this exact semantic repair once after verifying the donor source still matches the pinned preimage or after reconciling any newer equivalent change.
