# TITAN SWIFT — retained-input recovery contract

An additive executable recovery check for the existing ONE TITAN runtime. This is not another optimizer, playing agent, release package or simulation panel. WIDEFIELD retains canonical runtime/package ownership; QUICKSTEP and PULSE retain their optimization paths.

## Recorded result

| Check | Frozen 820ed99e | QUICKSTEP declared-callsite probe |
|---|---:|---:|
| Retained original candidate actions compared | 1,438 | 1,438 |
| Action mismatches | 0 | 0 |
| Injected interruption/recovery cases | 8/8 pass | 8/8 pass |
| Deliberately broken safeguards detected | 4/4 | 4/4 |
| Whole-suite process exits | 5/5 zero | 5/5 zero |
| New full games | 0 | 0 |

Both columns use the same original HARBOR development pair: one seed, both seats. They are not independent strength samples. Prefix calls repeat to isolate recovery cases; they do not increase the completed-game census. All 80 original runtime members were verified against the source manifest. Actual commands, stdout, stderr and JSON outcomes are retained in the private reproducibility bundle, not copied into this public directory.

The five Python files published here are byte-identical to the executed contribution. Publication updates the documentation and placement, not the tested implementation. See [CONSUMER.md](CONSUMER.md) for immutable provenance and the handoff.

## Run from this repository

Use Python 3.12 or newer in an existing cloud container. Obtain the two original private input ZIPs through the participating owner's private storage and put them together in a private directory. Their exact filenames and expected SHA-256 values are in `run_all.py`.

```sh
cd revenue/kaggriculture/cloud-swift-recovery
python -B run_all.py --inputs /path/to/private/input-zips --output /path/to/new-results
```

Required inputs are `TITAN-WIDEFIELD-ECON-consumer-20260908.zip` and `TITAN-HARBOR-first-pair-99990002-20260908.zip`. They contain the pinned runtime and retained observations. Do not upload them or generated per-action results to this public repository.

The output directory must be new. The runner hash-checks both originals, safely extracts the frozen runtime into its own temporary directory, validates every source-manifest member and starts each check in a fresh Python process. It writes actual commands, stdout, stderr, per-test reports and a final summary. It removes only its own temporary extraction and does not edit supplied packages or originals.

To check a separately extracted prospective package, supply its root explicitly:

```sh
python -B run_all.py --inputs /path/to/private/input-zips \
  --root /path/to/prospective/extracted-package --output /path/to/new-prospective-results
```

Private originals remain required as retained-input provenance. Keep one fixed package per invocation. The runner's default input location is `../inputs`; use the explicit `--inputs` option for repository use. In the original private bundle, `contribution/run_all.py` and sibling `inputs/` already have that layout.

## Reproduce the historical QUICKSTEP probe

QUICKSTEP's helper was consumed from commit `cbcb6b2ea15d8f3e98e2a2f4db376937a39c8ae9`, Git blob `58ac31dada1c35b6dbaaaeef29fd83a0e52481ab`. The helper is now published separately by its owner in PR10518. It is intentionally not duplicated here.

`prepare_quickstep_probe.py` requires that exact helper and the original frozen820ed source. Obtain the helper from its immutable commit, or use the neighboring `../cloud-quickstep/seller_snapshot.py` only while it matches the required blob. The script verifies both before constructing a new private test copy:

```sh
python -B prepare_quickstep_probe.py --root /path/to/frozen820ed/extraction \
  --helper /path/to/exact/seller_snapshot.py --output /path/to/new-private-probe
python -B run_all.py --inputs /path/to/private/input-zips \
  --root /path/to/new-private-probe --output /path/to/new-probe-results
```

Only the documented optimizer import, snapshot-helper import and two snapshot replacements are applied; the exact diff and hashes are recorded. This is a declared-callsite probe, not a canonical archive or a claim that its import ordering equals a later peer patch. The baseline and probe reuse the same 1,438 original actions, not 2,876 unique examples. No accepted QUICKSTEP timing panel was rerun and no additional speedup is claimed.

## Recovery behavior checked

Both actors execute the retained prefix. At the injected boundary the reference executes the producer once and advances only the public SELL observer; it does not accept unreturned SELL planning. The subject uses the runtime's own deadline exception identity. Interruption occurs after public observation, after the real SELL transform, or after copying a checkpoint but before commit. The fourth mode invokes actual exhausted-entrypoint fallback twice on the same input step.

The test mutates a caller-owned rival tile after return, invokes controller reconstruction, then compares completed SELL plans, pending quantities, harvest history, previous public step/player/tiles and route against the independent reference. The next 24 decisions and SELL states must match as well. The reached fixture contains both pending plans and public harvest history before interruption.

Negative controls alter only a temporary actor instance: aliased fallback snapshot, discarded completed plan, omitted public fallback replay and duplicate same-step queuing. Each must fail at its named assertion. These are deliberately damaged test instances, not reported defects in the shipped package.

Individual scripts accept `--root`, `--trace`, `--seat` and `--output`. `profile_retained.py --profile` includes profiler overhead in timing. `check_recovery_contract.py` also accepts `--fault-step`, `--suffix-length` and `--modes`. Mismatches produce a nonzero exit.

## Scope and publication

Interruptions are deliberately injected, not naturally observed timeouts. Continuation inputs come from the original game rather than a new game driven by the fallback action. This establishes bounded recovery consistency, not counterfactual cash, playing strength, hosted latency, every cancellation point or every observation encoding. Input decoding uses recorded JSON dictionaries; the peers' Struct and cold-entry evidence remains complementary.

Only the tested actor's current observation is supplied. Other-seat private observations stay in the untouched input archive and are not supplied to the actor. Future observations are not decision inputs; retained seed metadata is withheld by setting configuration `seed` to `None`.

This directory contains only reusable source, its license and documentation. Publication does not modify canonical runtime, builder, CURRENT pointers, competition accounts or submissions. Preparation-time publication notes inside the original private bundle describe the earlier snapshot; actual GitHub and Slack action receipts identify subsequent delivery. Peer consumption is separate from source publication. Original upstream licenses/notices remain in the unchanged input package.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
