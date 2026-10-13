# T09 variant boundary regression

Operation: `titan-meridian-variant-boundaries-20260908-01`; publication worker identified by Slack claim `1788866234.992229`.

## Scope

The adjacent `variants.py` derives the final executable day from `episodeSteps - 2`, uses the official default shed capacity of 100, and applies the engine's one-turn minimum. Without an episode horizon, the existing `days` alias remains supported. The original `labor_cadence` hire filter and all three variant identities are unchanged. This is an evaluation-helper repair, not a new competitive policy.

Only `variants.py` and this regression directory are published. No canonical archive, runtime selector, current-source pointer, LARK opponent, running frozen job, or provider submission is changed. Private diagnostic trajectories are excluded.

## Run

From the repository root, using an existing local copy of the three pinned official engine files:

```sh
ENGINE_DIR=/absolute/path/to/engine python -B revenue/kaggriculture/cloud-opponent-league/meridian-boundaries/test_variant_boundaries.py
```

Without `ENGINE_DIR`, the test reads only the three regular `checks/reference/engine/` members of the existing `cloud-execution-lab/exports/titan-current.tar.gz`. It verifies every engine hash before loading; it never downloads missing dependencies. The existing offline-agent helper is also byte-pinned. A changed dependency requires explicit review, not silent substitution.

To reproduce the original defects, use the same command with `VARIANTS_PATH=variants_original.py`. That file is an unchanged historical fixture, not an alternative runtime.

## Executed validation

On the prepared production bytes, the checkout-runnable suite passes all 15 methods with no failures, errors, or skips (0.048 seconds unittest time in the recorded cloud run). The same suite on the original source gives 16 failed parameterized assertions and one division-by-zero error. Patch check and actual patch application both succeed, producing byte-identical source. The original private-bundle test adapter separately passes its same 15 methods; these are not 30 distinct tests.

The continuity method makes 2,157 exact comparisons: all 719 executable steps times the three existing transforms for one fixed fixture under `episodeSteps=720`, `turnsPerDay=24`, `shedCapacity=100`. All match the original. Four constructed official-interpreter terminal-sale cases (two variants, both seats) retain the sale after the repair; these are one-step fixtures, not whole games or measured competitive gains.

The no-environment-variable archive-loader route also passes the same 15 methods using a synthetic three-member transport containing the identical pinned engine bytes. This tests archive loading, not an actual canonical archive or package build. No full-repository CI, hosted deadline, or playing-strength result is asserted. Full games added: zero.

## Exact source identity

- Original fixture: Git blob `374a23ffb3cf6cc1c67571df74fde9f84467e832`; SHA256 `69df8c159d8f0b48377052d1637c49727ec551a8774f9f0215984fa89acd0746`.
- Repaired helper: Git blob `654d949a1937b682b62a82f7f7fe237ce67138e9`; SHA256 `548723019116655c17ef8ed58e1cb346a49e3c95c8e3c2fed4d778d56f3fe189`.
- Regression: Git blob `fe707bda42edc204c839d083889301a60f7eb522`; SHA256 `bcaba76753e9da6eba4f894024debaa09af3697d66ab431e77bc36d8388c1f85`.
- Official engine: `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; all three expected hashes are in the test.
- Unchanged existing loader: Git blob `23948e10cfc3d32f46c9abb1321b0d8fc8db21d5`; SHA256 `cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e`.

The historical baseline is existing Apache-2.0 Commons source. Engine and loader are consumed from existing sources, not republished here. Actual PR merge and current-main readback are recorded in the publication receipt, not inferred from these tests.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
