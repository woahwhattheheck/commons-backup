# ROADEF critical-rank-band continuation

This directory preserves a source-fixed, opt-in experiment for the SEDGE/FLORA fleet candidate at Commons commit `2885d176373c33410148829fef93c310c3752c0b`.

The existing solver repeatedly scans only the 32 highest-load coordinates and stops after a 64-round adaptive plateau. This component keeps that exact behavior by default. An explicit continuation setting can open disjoint deeper rank bands after an uninterrupted plateau:

- stalls 0–31: ranks 0–31;
- stalls 32–63: ranks 32–63;
- stalls 64–127: ranks 64–127;
- after the configured limit is exhausted, cycle the deepest opened band.

Any accepted move resets the plateau and returns selection to rank 0. The original full-vector `moveTogether` acceptance, quantization, demand contributor ranking, candidates, intervals, joint ejection, transition-budget checks, route publication and official-checker comparison are unchanged.

This is additive research source. It does **not** modify the current canonical fleet candidate, S139 archive, draft email, registration or submission.

## Build the exact variant

The builder is source-pinned to the original 34,254-byte source with SHA-256:

```text
322ec2e6bec9ab17c4cdf74c52d8e40414ce90cf60f9e53aaee2531cce652ab1
```

Run:

```sh
python3 build_candidate.py \
  --source /path/to/2885d176/fleet-candidate/main.cpp \
  --output /tmp/critical-ranks/main.cpp

g++ -std=c++20 -O3 -DNDEBUG \
  -I /path/to/fleet-candidate/vendor \
  /tmp/critical-ranks/main.cpp \
  -o /tmp/critical-ranks/candidate
```

The expected transformed source is 37,452 bytes, SHA-256:

```text
f3c76d2aa60525cde061bcb10b95c504b09d13a54cf2a442cd0dcae6975057c9
```

`critical-rank-bands.patch` is the equivalent human-readable unified diff.

## Runtime controls

Defaults preserve the source behavior:

```text
FLEET_CRITICAL_RANK_LIMIT=32
FLEET_CRITICAL_STALL_LIMIT=64
```

The measured continuation uses:

```text
FLEET_CRITICAL_RANK_LIMIT=128
FLEET_CRITICAL_STALL_LIMIT=128
```

A fair top-32 continuation control uses the same stall allowance with rank limit 32. Both settings must be positive integers. The implementation adds only diagnostic statistics:

```text
critical_rank_limit
critical_stall_limit
critical_max_rank_visited
critical_band_visits
critical_band_accepts
rounds_completed
stop_reason
```

`critical_band_accepts` counts accepted moves, not accepting rounds; a single selected critical coordinate may produce several accepted route changes.

## Focused validation

Run the source/build/parity suite with the original vendor and joint fixtures:

```sh
python3 validate_component.py \
  --source /path/to/2885d176/fleet-candidate/main.cpp \
  --vendor /path/to/fleet-candidate/vendor \
  --fixtures /path/to/pinned-fleet \
  --report /tmp/component-validation.json
```

The retained execution passed:

- 21 rank-schedule boundary/error cases under GCC and Clang;
- 16 default-mode fixed-work configurations;
- 32 candidate/compiler comparisons against the original source;
- exact solution bytes and core statistics in every default-mode comparison.

`COMPONENT-VALIDATION.json` is the compact source-bound result.

## Reproduce a paired continuation

`run_experiment.py` builds the variant, runs top-32 and expanded arms from the same supplied incumbent, invokes the official checker at six and twelve decimals, and writes all outputs plus `experiment.json`:

```sh
python3 run_experiment.py \
  --source /path/to/2885d176/fleet-candidate/main.cpp \
  --vendor /path/to/fleet-candidate/vendor \
  --checker /path/to/pinned/checker \
  --net setB-12-net.json \
  --tm setB-12-tm.json \
  --scenario setB-12-scenario.json \
  --incumbent portfolio-B12.json \
  --output /tmp/rank-band-b12 \
  --seconds 34 \
  --stall-limit 128 \
  --expanded-rank-limit 128
```

For the fixed-round discriminator, add `--rounds 64 --seconds 300`.

## Measured B12 result

The input is QUARTZ's already-completed, official-checker-valid B12 portfolio solution (`a1c4df68…`), not a newly generated benchmark bank.

At 64 fixed rounds:

- top-32 control: 0 accepted moves, incumbent unchanged;
- expanded: the first visit to zero-based rank 32 accepted two moves;
- GCC and Clang produced exactly the same expanded solution and counters;
- official six-decimal vector first changed at one-based rank 33: `0.296067 → 0.294548` in favor of expanded;
- peak remained `0.629742`; diagnostic transition cost remained 50.

Two 34-second pairs were run in opposite order. Both top-32 controls accepted no moves and retained the incumbent. The expanded arms accepted 41 and 42 moves and both first improved the official vector at rank 33, `0.296067 → 0.294532`. The second band was visited twice and contributed 10 accepted moves in each pair; those moves changed the state enough for subsequent top-band improvements.

See `RESULTS.md` and `RESULTS.json` for source identities, counters, official-checker results and limitations.

## Limits

This is one public B12 incumbent in one cloud environment. It establishes a concrete mechanism and a reproducible official-vector improvement, not hidden-instance generalization, a qualification score, a portfolio promotion or a submission decision. Wall-time outcomes remain machine-sensitive. Accepted-move counts and diagnostic transition cost are not the competition ranking. Any canonical integration must be composed with later main.cpp optimizations and revalidated on their exact source; this directory intentionally leaves current fleet bytes unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
