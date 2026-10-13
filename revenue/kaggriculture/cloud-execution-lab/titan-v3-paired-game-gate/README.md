# Titan V3 paired-game gate

Operation: `titan-v3-paired-game-gate-20260909-sol-argus-02`

Snapshot-binding hardening:
`titan-v3-paired-game-gate-snapshot-binding-20260909-sol-kiln-01`

This is a fail-closed evidence adapter for the Kaggriculture evaluator's native
`GAMES.jsonl` rows. It evaluates paired game cells, not prediction rows: each
cell is identified by `(opponent, seed, candidate_seat)` and carries the two
terminal cash scores.

It is deliberately separate from generic OOF/RMSE/log-loss gates. Those tools
can still consume a derived table, but they must not be the component that
proves a Titan game panel is complete, seat-balanced, provenance-bound, or free
of evaluator errors.

## Hard validity contract

Before looking at an average, the gate requires:

- one unique baseline row and one unique candidate row for the complete Cartesian
  product of declared opponents, seeds, and **both** seats;
- exact equality to that grid: no missing, extra, duplicate, timed-out, errored,
  or otherwise non-`complete` cells;
- exactly two finite terminal scores per cell;
- exact match between expected and observed engine, runner, baseline archive,
  and candidate archive identities;
- integer, non-boolean schema versions and finite numeric conversion;
- each input opened once and copied into a private snapshot while its SHA-256 is
  computed, so the parser consumes the exact bytes named by the report;
- post-evaluation snapshot digest verification, duplicate-key-safe JSON parsing,
  regular non-symlink inputs, bounded sizes, deterministic output, and atomic
  report replacement.

A source path may be replaced after its snapshot without changing the evaluated
bytes or reported digest. Mutation during snapshot construction, or mutation of
a private snapshot before the final digest check, invalidates the run.

A partial panel cannot become a smaller sample by accident. Invalid evidence is
reported as `INVALID` and exits 2.

## Game-native decision metrics

For every aligned cell the report preserves:

- candidate and baseline own cash, rival cash, margin, and W/T/L result;
- paired own-cash, rival-cash, and margin deltas;
- any W/T/L regression or improvement;
- aggregates and worst cells;
- per-opponent and per-seat strata;
- the mean across the two candidate seats for each `(opponent, seed)` pair.

Promotion thresholds are explicit contract data. They include own-cash and
margin floors, positive-cell and positive-pair fractions, result-regression
limits, baseline-win and new-loss limits, opponent/seat robustness, a worst-cell
floor, and an optional requirement that the candidate actually change a score.
Complete evidence that misses any declared threshold is `REJECT` and exits 3.
A fully valid panel satisfying every threshold is `PROMOTE` and exits 0.

`PROMOTE` means only “this panel satisfies this exact declared contract.” It is
not a Kaggle submission, leaderboard claim, statistical guarantee, release
pointer change, or authorization to replace `exports/titan-current.tar.gz`.
Development and holdout must use distinct contracts and seed registries.

## Usage

```bash
python3 gate.py \
  --contract /evidence/CONTRACT.json \
  --evidence /evidence/PROVENANCE.json \
  --baseline /evidence/canonical.GAMES.jsonl \
  --candidate /evidence/challenger.GAMES.jsonl \
  --report /evidence/GATE.json
```

Do not put credentials, tokens, private tactics, or private environment values
in `exact_command`. Preserve only the reproducible command and public artifact
identities.

The example is synthetic and proves the executable interface only:

```bash
python3 gate.py \
  --contract example/CONTRACT.json \
  --evidence example/PROVENANCE.json \
  --baseline example/canonical.GAMES.jsonl \
  --candidate example/challenger.GAMES.jsonl \
  --report /tmp/titan-v3-example-gate.json
```

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 \
  python3 -m unittest -v test_validation.py test_policy_cli.py
python3 -m compileall -q .
```

Current hardening result: **27/27 passed**. Covered attacks include partial
positive panels, extra and duplicate cells, non-complete rows, baseline errors,
NaN, oversized integers that cannot become finite floats, malformed score
vectors, bad seats, provenance drift, boolean schema versions, duplicate
contract seeds, missing second seat, duplicate JSON keys, symlink substitution,
source replacement between acquisition and evaluation, global mean hiding W→L
regression, global mean hiding a negative opponent stratum, identity candidates,
worst-cell violations, deterministic reports, and stable CLI exit codes.

## L01 adapter

For PR #11459, replace `deltas.py` as the combine authority:

1. create one contract per arm (`land`, `sheep`, `day0buy`, `tranche`,
   `leanplant`) using the exact 16 seeds, six opponents, and seats `[0, 1]`;
2. bind the official engine, runner, canonical 3b4b archive, and exact candidate
   build hashes in both contract and provenance evidence;
3. gate each arm separately against `canonical.GAMES.jsonl`;
4. combine only arms whose individual report is valid and whose experiment
   semantics have separately passed an official-engine state-transition oracle;
5. issue a new contract for the combined arm and a disjoint holdout contract.

The `DAY0BUY` arm at PR #11459 head `abd041c0…` must not be called a product
basket: engine 1.32.7 accepts `BUY_PRODUCT` only for WHEAT/FERTILIZER, so its
other rows abort. Correct the arm semantics before producing its contract.

## Files

- `gate.py` — zero-dependency CLI/orchestrator and private snapshot lifecycle.
- `gate_common.py` — strict JSON, single-open snapshot, hash, and atomic-write
  primitives.
- `contract.py` — frozen grid, provenance, schema, and policy validation.
- `panel_load.py` — exact Cartesian game-grid loading and validation.
- `metrics.py` — paired cash/result metrics, strata, and declared policy checks.
- `test_support.py`, `test_validation.py`, `test_policy_cli.py` — adversarial contracts.
- `CONTRACT.md` — exact JSON schemas and policy semantics.
- `THREAT-MODEL.md` — evidence threats and non-goals.
- `example/` — synthetic complete 2×2×2 panel; not gameplay evidence.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
