# ROADEF S139 — cold-screen / saved-incumbent continuation reconciliation

This is a read-only join of two already-completed public-development artifacts. It
verifies both provider SHA-256 values and every payload named by each archive
manifest, then compares exact official six-decimal descending saturation vectors.
It extracts or executes nothing and starts no solver, checker, benchmark, workflow,
container, or submission action.

## Inputs

- QUARTZ 30-second all-B screen: `ROADEF-QUARTZ-screen30-2885d176.zip`,
  `file_0000000004f881f5bb67303fe7f403b4`, SHA-256
  `0fed26e0260aad3c3c840c3e2c38b035f21ce6d3cac5544428f4f8a5f2959d9d`.
- LANDING continuation study: `ROADEF-LANDING-continuation-study-20260908.zip`,
  `file_00000000480081f7ae598a5ec1c24943`, SHA-256
  `963cd540a165ef0c8c0925a9cb3568fe8e6d1a1d707c20d505cbe970d5861928`.
- Shared original fleet source: `2885d176373c33410148829fef93c310c3752c0b`.

The screen contributes 288 manifested payloads. The continuation contributes 260.
The reader checks 24 official six-decimal reports containing 673,632 saturation
coordinates. LANDING's 16 continuations and 32 checker calls remain its original
execution; this reader contributes zero new calls.

## Exact reconciliation

| Instance | Cold fleet loses SEDGE | Best resumed continuation | Gain over saved SEDGE | Best fleet continuation | sampled joint0 vs joint1 |
|---|---|---|---|---|---|
| B02 | rank 47: .092297 / .089904 | FLORA | rank 247: .027125 / .027222 | sampled128_joint0 | joint0 wins rank 247 |
| B05 | rank 6: .427543 / .425636 | sampled128_joint0 | rank 603: .075444 / .075448 | sampled128_joint0 | joint0 wins rank 1,876 |
| B07 | rank 2: .554801 / .543582 | FLORA | rank 4: .517228 / .521665 | directed128_joint0 | joint0 wins rank 8,460 |
| B10 | rank 5: .869291 / .807464 | FLORA | rank 12: .688410 / .689244 | sampled128_joint1 | joint1 wins rank 122 |

Every one of the four resumed arms beats both the saved SEDGE incumbent and the
cold fleet result on every selected instance. The exact best-of-four continuation
is FLORA on B02, B07, and B10, and sampled-128 with joint search disabled on B05.

The two-lane set **FLORA + sampled128_joint0 exactly reproduces the best of all four
continuation arms on all four instances**. Neither directed128_joint0 nor
sampled128_joint1 contributes a best-of-four cell.

## What the continuation resolves

- **B02 and B05 were both cold-screen local-optimum symptoms, but they split.**
  Sampled/no-joint is the best continuation on B05. On B02 it reaches FLORA's
  rank-247 gain but FLORA remains better at rank 437.
- **B07's cold joint-heavy symptom does not establish that accepted joint moves
  caused the loss.** All continuation arms improve the incumbent, but FLORA wins.
  sampled joint0 is better than joint1 only at rank 8,460; directed/no-joint is
  the best fleet continuation but still loses to FLORA at rank 6.
- **B10's cold throughput/acceptance deficit is not cured by a fleet configuration
  alone in this study.** sampled joint1 is the best fleet continuation, but FLORA
  wins much earlier at rank 12.
- `sampled128_joint1` records **zero joint attempts and zero joint accepts in every
  continuation cell**. Its outputs still differ from joint0. The evidence therefore
  cannot credit any result to an accepted joint exchange; speculative search/RNG/time
  effects remain possible but are not isolated by this one-run study.

Transition cost is retained only as a diagnostic and never used to rank solutions.

## Deployment boundary

The result is **warm-start evidence**, not evidence for the current cold portfolio.
Current `fleet-candidate/supervisor.py` blob
`6a32f242aeaa85da70942e39aa1ea2a3c781d383` explicitly removes
`CLOUD_INITIAL_SOLUTION` and starts independent `sedge`, `flora`, and `candidate`
lanes. It does not replay the measured SEDGE-checkpoint → continuation handoff.

Therefore the evidence-supported next integration comparison is:

1. establish and validate one SEDGE checkpoint;
2. continue FLORA and sampled128_joint0 from those exact bytes;
3. compare that staged path with the current independent cold lanes under one
   declared equal-resource envelope;
4. retain B01 and B04 as preservation controls because they were rank-1 cold wins
   with accepted joint activity.

The staged design is not yet a selected runtime change. Four preselected loss
instances are not representative hidden-X evidence, a universal dominance result,
or a qualification ranking. S139's draft and attachment remain unchanged and
unsent.

## Reproduce the read-only join

```sh
python -B reconcile.py \
  /path/to/ROADEF-QUARTZ-screen30-2885d176.zip \
  /path/to/ROADEF-LANDING-continuation-study-20260908.zip \
  --json-output /tmp/reconciliation.json \
  --markdown-output /tmp/reconciliation.md

python -B -m unittest -v test_reconcile
```

Ten synthetic boundary methods pass. They cover archive digests, both manifest
formats, incumbent identity, resumed-state declarations, solution/result binding,
duplicate JSON keys, numeric validity, and joint-counter reporting. `RESULT.json`
contains every exact pairwise result and continuation counter used above.

The complete parser, tests, output, logs and validation are also retained in Library
as `ROADEF-SCREEN-CONTINUATION-RECONCILIATION-20260908.zip`, file
`file_000000005ba881f5b682fe6ec22b2f45`, 18,491 bytes, SHA-256
`3d2577d555390dfb9039f07c7a1e3267099d5231fb44ff99914327a607df0157`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
