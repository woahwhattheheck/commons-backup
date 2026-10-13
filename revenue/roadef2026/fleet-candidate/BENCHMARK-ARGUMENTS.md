# Validate benchmark arguments before reserving evidence

The existing ROADEF matched-budget benchmark now rejects unusable search and
worker settings immediately after argument parsing, before reading `paths.json`,
hashing executables, reserving output cells, or launching a process. This is a
current-main composition of the earlier tested Library patch; it retains the
later finite-load and coordinate-universe integrity work already present on main.

`--seconds` must be finite and nonnegative. `--rounds`, when supplied, must be
nonnegative. `--workers` must be positive. Zero seconds and zero rounds remain
valid no-search controls. Signed zero, fractional budgets, defaults, resume
inputs, and large nonnegative round limits preserve their prior behavior.

## Current source and scope

The source was rebased on Commons main `b19e7d4ee51046c2dd2f254629d2f49a7fa341e6`,
`benchmark.py` base Git blob `609567b941013189181857b8303566796b56c4dd`,
11,165 bytes. The delivered file is 11,597 bytes, SHA-256
`ab9216ae6eea506e13ba0ff666cbe91909c25a9941a6b45a2a801857580230ec`.
The prepared source is Git blob `139543be90a5e0ca4e27071304af30d6a1001c6a`,
11,597 bytes, SHA-256
`ab9216ae6eea506e13ba0ff666cbe91909c25a9941a6b45a2a801857580230ec`.

Only three validation statements are added to `main`. AST comparison after
removing those statements is identical. `digest`, `execute`, `finite_loads`,
`load_coordinates`, `validated_loads`, and `reserve_outputs` are unchanged.
The existing timeout/process evidence, exclusive output ownership, finite-value
checks, duplicate-coordinate checks, cross-precision/source coordinate agreement,
score ordering, cost comparison, and concurrency behavior remain intact.

## Executed validation

The standard-library test suite executes the complete benchmark CLI in fresh
subprocesses with explicit synthetic solver/checker programs and minimal local
inputs. The fixtures are not the official solver or checker and provide no
contest score or native-solver performance result.

```sh
python3 -B -S revenue/roadef2026/fleet-candidate/test_benchmark_arguments.py \
  --benchmark revenue/roadef2026/fleet-candidate/benchmark.py \
  --report /tmp/benchmark-arguments-results.json
```

All **23 methods pass**, with zero failures, errors, or skips. On the exact
current-main source, the same suite executes 23 methods with **16 failing
assertion/subtest records** and zero errors. Valid default, zero-search,
fractional, smallest-positive, resume, multi-worker, and existing-output cases
all pass after the change.

A direct retry witness demonstrates the operational difference. Current main
accepts `--seconds=nan` through parsing, starts the synthetic solver, creates
`experiment.json` and process evidence, then exits 1. A corrected invocation
against that same output is blocked by the now-reserved destination. The prepared
source exits 2 before any child or output exists; the corrected `--seconds=0`
invocation then succeeds with one solver and two checker calls.

Complete before/after reports, logs, direct witness, AST scope check, source
copies, hashes, and the original Library patch are retained in the companion
handoff package. The updated patch is based on current main, not the older source
snapshot embedded in the recovered patch.

## Boundaries

No official solver/checker/instance, benchmark panel, Docker build, S139 draft,
qualification attachment, or submission is touched. No prior evidence is
modified. This does not change search budgets supplied by valid calls, solver
selection, score semantics, timeout allowance, or output replacement rules.
The original recovered package was source-ready but unpublished. This repository
delivery reran the same 23 methods against the rebased source and retains the
original negative controls. Generic hosted checks and merge status are recorded on
the pull request rather than inferred from this local test receipt.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
