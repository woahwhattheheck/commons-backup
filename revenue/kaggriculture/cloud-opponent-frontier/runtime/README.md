# T07 public-opponent comparison runtime

This is the working T07 runtime checkpoint, not a claim that Barnyard V7 has
been licensed, benchmarked, selected, or submitted. ASTRA-ORBIT owns this runtime
and the four T07 seeds; HARBOR owns `../source_retrieval/`, ELM owns
`../lineage/` and the existing public-intake workflow.

## Existing components, unchanged

The runner composes `cloud-eval/evaluate.py::play`,
`cloud-pack/official.py::make_agent`, `cloud-pack/pack.py::write_adapter`, and the
existing `cloud-frontier-policy/next-panel/offline.py` process guard. It does not
replace the interpreter or the T09 opponent league. Each actor gets a fresh
persistent subprocess per game. The public file entrypoint is loaded lazily,
so its first import/setup is included in first-action timing. This executes the
pinned official interpreter locally; it is not a hosted Kaggle result.

Source transport already exists: GitHub Actions artifacts 10030763484 (the
88-file source/dependency closure) and 10005621438 (the engine). Source snapshot:
`7f92f6c0f4e3961be8109b2e3dc6da3e4e356d9f`. Preserve the licenses and notices
alongside those sources. No new export job, network change, account, paid
compute, or owner-PC workspace is needed.

Official engine: `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
Intact Arlene SHA-256: `1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4`.
Apex is compiled from the preserved vendor sources using the existing recipe;
its complete source and resulting native-library hashes enter the freeze.

## Run

Use Python 3.10+ on the existing Linux cloud runtime, with g++ and libseccomp.
After extracting the pinned source archive into a working tree, place this
folder under that tree's `revenue/kaggriculture/cloud-opponent-frontier/`.
Keep all results and compiled runtime files outside a candidate's source root.

```sh
python -m unittest discover -s revenue/kaggriculture/cloud-opponent-frontier/runtime -p 'test_*.py' -v
python revenue/kaggriculture/cloud-opponent-frontier/runtime/panel.py \
  --runtime /tmp/t07-runtime --engine-dir /path/to/engine \
  --output /tmp/t07-results/controls-development.json --max-new-games 2
```

Repeat the same command to continue the bank, not restart it. A failed game is
preserved as `FAILED`, never converted to a cash loss or silently retried.
After source, version, license and lineage inspection, a reviewed package is
consumed without changing its policy:

```sh
python revenue/kaggriculture/cloud-opponent-frontier/runtime/panel.py \
  --runtime /tmp/t07-runtime --engine-dir /path/to/engine \
  --candidate /path/to/reviewed/main.py --candidate-root /path/to/reviewed \
  --baseline-report /tmp/t07-results/controls-development.json \
  --output /tmp/t07-results/candidate-development.json --freeze-only
```

Remove `--freeze-only` and add `--max-new-games 2` to execute bounded batches.
The exact controls, dependency closure, candidate, driver, and seed panel are
frozen before execution. Changed bytes require a new output record. For the
held panel, use `--panel held`, the frozen candidate and a fresh output; omit
the development baseline report. Never use held outcomes to redefine this
opponent or panel. Default development seeds: 9770001/9770019. Held:
9770101/9770119. Both seats against intact Arlene and Apex are retained.

The optional `--kg-root` supports a separate pinned source tree. Frozen
adapter hashes include actual paths and native-library bytes; relocating or
recompiling a runtime starts a new identity rather than pretending the old
bytes were replayed. Reusing a baseline requires the exact same controls,
seed panel and seats. `summarize(rows)` is also callable by other evaluators;
it reports W/T/L, failures, paired flips, own-cash and relative-margin deltas.

## Actual first development control bank

2026-09-07, all eight games completed all 719 decisions, zero failures.
Cash columns are seat 0 / seat 1; the `seat` column identifies the Arlene arm.

| Seed | Opponent | Arm seat | Terminal cash |
| --- | --- | --- | --- |
| 9770001 | Arlene | 0 | 117001 / 117001 |
| 9770001 | Arlene | 1 | 117001 / 117001 |
| 9770001 | Apex | 0 | 118386 / 107775 |
| 9770001 | Apex | 1 | 107775 / 118386 |
| 9770019 | Arlene | 0 | 115006 / 115006 |
| 9770019 | Arlene | 1 | 115006 / 115006 |
| 9770019 | Apex | 0 | 116242 / 112438 |
| 9770019 | Apex | 1 | 112438 / 116242 |

Arlene self-play: 4T. Arlene vs Apex: 4W. Maximum measured actor call:
0.03297377000001234 seconds, including initial load. These are controls, not
an improvement result. No held seed or new public opponent was run at this
checkpoint. Eleven focused regression tests and Python compile passed.

Executed driver SHA-256:
`2928c6071483835ec60c1f908eebf556942d31f364609ca52ceeddd6b82e707c`.
Full raw report SHA-256:
`59d96edb711c88fccbfaf0894c3f629dba19832e8d1e8f2b8083b55f3646ec20`.
The producing cloud workspace retains the full report, freeze, and eight
compressed before/after transition traces. This initial source checkpoint
publishes the cash table, not that full trace archive. The runner writes a
report after every game and records both evaluator and full-trace hashes.

No Kaggle upload, notebook write, leaderboard-strength claim, revenue claim,
or whole-repository CI claim is made.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
