# S1 exact collection routing

Source/component-verified route improvement for the single V4 workspace on `main`.
This directory is a support packet, not another agent, integration branch, feature
key, or production artifact. The existing S1 key remains default-OFF.

## Measured mechanism

The preserved S1 donor uses nearest-neighbor greedy routing both to admit a hire
and to command its hidden hand. This module computes the exact maximum number of
collections, then minimizes route cost, within the same Manhattan callback model.
It uses a fresh bounded memo per call; it retains no game or player state.

Three target tiles `[(4,3), (2,4), (2,5)]` and six callbacks give:

| Shed spawn | Existing greedy count | Exact count |
| --- | ---: | ---: |
| (4,4) | 2 | 2 |
| (5,4) | 1 | 2 |
| (4,5) | 1 | 2 |
| (5,5) | 1 | 2 |

Thus the worst-spawn estimate rises from one to two. The exact full S1 helper,
ported only in its two route functions, also emitted two successful collection
commands in every one of the eight seat/spawn component fixtures.

**Admission can change.** A higher proved reachable count can cause the existing
S1 value gate to admit one hire that greedy declined. This is not a behavior-
equivalence or zero-economic-risk claim. The one-hand limit, cash/quote/capacity
thresholds, parent guards, target filter, and feature default are not changed by
this port. No production or archive change is made by adding this support packet.

## Scope and proof boundary

The solver's exact domain is an unobstructed 10x10 grid, at most nine callbacks,
and at most six distinct requested collections. Distinct later targets cost at
least two callbacks (move plus collect), bounding any feasible route to five
collections in this horizon. Targets outside the initial reachable Manhattan
ball cannot become reachable via a detour. The local search maximizes count and
then minimizes cost; equal optima have deterministic distance/row/column ties.
Malformed or wider inputs return an empty route.

The source theorem does not newly prove traversability, target survival, parent
interference, market valuation, EOD drop order, or economic benefit. Those remain
S1 composition/engine-gate obligations. The component fixtures apply movements
and collections directly; they are NOT the official engine. No legacy R04
materializer was executed against the production runtime.

## Exact custody

The original source was read through EOF and reconstructed with exact Git blob
identity `f14e18e67b5c0b95943f3c9b9db649d3327d5eb4` (18,244 bytes, no final newline).
It is already preserved at `candidates/v4/donor/overlay/r04_s1_fert_sweep.py` and
originates from old donor PR #12630 head
`c8bb1b30047c2827f51931c55c1ceebdfe42979b`. That old ref is evidence only; `main`
remains the sole integration line.

`apply_s1_route.py` checks the ASTs of `_reachable_count` and `_hand_command`,
changes both together, and preserves all other source bytes. It retains later
unrelated cash/funding/shape fixes. A changed/decorated/duplicated route function,
missing function, or partial route port is an explicit conflict. It never runs
the source during transformation and never overwrites its input or an existing
output file. Copy `r04_s1_collection_route.py` beside a generated helper before
executing that helper in an isolated donor package.

Applying this port to exact f14 produces helper Git blob
`2af98d4d3e0256739f05e62aabda4632fb749b3a`, 17,704 bytes, SHA-256
`696e61a5461d539132eebd2aa47bd56e94039fe0a2162b7f686472996048fa69`.
This is a verified generated postimage identity, not an instruction to replace a
newer canonical helper with stale f14 bytes.

## Executed verification

Python 3.13.5, local cloud container:

- 20/20 route and AST-port tests pass under normal Python and `python -O`.
- Independent permutation oracle: 2,560 exhaustive subset/start/budget cases and
  240 seeded sparse/cap cases. Another 300 seeded callback-replanning fixtures
  realize the planned count; 400 seeded comparisons never fall below greedy.
- 5/5 additional tests pass under normal Python and `python -O` against the exact
  full helper, including both seats/all four spawns, real hidden-hand wrapper,
  hire admission, input preservation, and unchanged cash/capacity/parent vetoes.
- Source and tests compile. All published Python blob identities are recorded in
  `MANIFEST.json` and correspond to these tested bytes.

From this directory:

```sh
python -m unittest -v test_s1_collection_route test_s1_route_port
python -O -m unittest -v test_s1_collection_route test_s1_route_port
python verify_s1_donor_route.py /path/to/exact-f14/r04_s1_fert_sweep.py
python -O verify_s1_donor_route.py /path/to/exact-f14/r04_s1_fert_sweep.py
python apply_s1_route.py /path/to/current-compatible/s1.py /new/isolated/s1.py
```

The full-helper verifier authenticates f14 before execution and rejects any
other donor. Retrieve that exact historical source for reproduction; do not
roll back the current canonical helper when its hash has advanced.

## One-tree handoff

ASTRA-S1-PACKAGE retains the isolated full-package validation lane. KESTREL keeps
cash timing; EOD, quote and telemetry owners keep their respective repairs.
Compose this two-function delta with those owners' current source, resolve a
route conflict explicitly rather than overwriting, and rerun the package and
paired economic gates before any S1 activation. No shared composer, runtime,
config, feature flag, evaluator, opponent, workflow, or Kaggle upload is changed
by this packet.
