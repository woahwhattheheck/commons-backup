# ROADEF A-RANK1 targeted diversion

This is a bounded, source-preserving experiment for the three remaining **rank-one**
set-A gaps identified by the authoritative 30-second calibration. It is not a new
portfolio, a set-wide rerun, or a qualification submission.

The builder inserts one opt-in `Solver::rankOne()` method into the exact frozen
composed candidate. Normal dispatch remains `solver.run()` unless
`FLEET_RANK1=1`. Every candidate route still passes through the existing
`move()` / `moveTogether()` implementation, preserving exact ECMP, segment
limits, transition budgets, and full sorted six-decimal acceptance.

For the current maximum coordinate, the pass records contributors and tests:

1. direct route and removal of each current waypoint;
2. every one-waypoint route returned by the existing full-node scorer, without
   the ordinary top-48/top-128 truncation;
3. replacements and insertions around the current route;
4. bounded ordered two-waypoint routes; and
5. the existing joint ejection move.

A deterministic pass with no accepted move is a stopping condition; the same
state is not blindly replayed. Accepted moves restart at the new rank-one
coordinate. The full contributor/attempt report is retained per instance.

## Authoritative inputs

The execution resumes exact selected incumbents from GitHub Actions run
`34197720573`, artifact `10044831235`, using frozen composed candidate source
SHA-256 `758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f`.

| Instance | Peak coordinate | Calibrated candidate | Published reference |
|---|---|---:|---:|
| A04 | t1 `43→12` | 0.587276 | 0.581237 |
| A14 | t1 `215→122` | 0.533147 | 0.517621 |
| A16 | t1 `131→228` | 0.079918 | 0.044262 |

QUARTZ's separate larger-allowance run already showed A04 and A14 terminate
naturally unchanged. This experiment changes the neighborhood, not merely the
allowance. A16 is treated as structural because the same arc is also the t0
maximum.

## Local source checks

```sh
python3 -B test_rank1_builder.py \
  --builder build_rank1_candidate.py \
  --source /path/to/frozen-composed/main.cpp \
  --vendor /path/to/context/sources/sedge/vendor -v

python3 -B build_rank1_candidate.py /path/to/frozen-composed/main.cpp \
  --expected-sha256 758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f \
  --output /tmp/rank1.cpp --receipt /tmp/rank1-builder.json
```

## Execute

The workflow `.github/workfows/roadef-a-rank1.yml` downloads the exact selected
incumbent artifact, fetches only A04/A14/A16 from official commit
`d84d319a7fdb8de3b1866830d2eaa2937871e5ae`, builds the targeted source, and runs:

```sh
FLEET_RANK1=1 FLEET_RANK1_PASSES=16 \
FLEET_RANK1_DEMANDS=32 FLEET_RANK1_PAIR_NODES=24 \
python3 -B run_rank1.py \
  --context /path/to/built-context \
  --official-root /path/to/pinned-official-checkout \
  --calibration /path/to/calibration-artifact \
  --candidate-source /path/to/frozen-composed/main.cpp \
  --output /fresh/output --seconds 180 --case-timeout 245
```

Each complete result is independently checked at 6 and 12 decimals. The harness
retains selected/continued solutions, input hashes, solver and rank-one reports,
stdout/stderr, target movement, and first changed full-vector rank. It rejects any
six-decimal worsening.

No Gmail draft, attachment, organizer communication, competition upload, or S139
submission is performed. The standing submission hold remains unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
