# Public-clock compatibility for the existing seed consumer

`seed_main.make_agent` now accepts either an explicit `step` or the public
`day` / `hour` clock, normalizing a detached top-level observation before the
one existing policy call. Explicit non-null `step` takes precedence. Missing or
null `step` uses `day * turnsPerDay + hour`, with the existing default period24.
The seed-disabled and plain-Arlene paths receive the same normalization.

The existing singleton and internal `arms.py` / `capital_arms.py` reset only at
actual step zero, rather than treating every missing step as a new game. Direct
raw loading of `seed_main.py` can use its compiled source filename when neither
normal module `__file__` nor the established `__raw_path__` is available. Those
existing path sources retain precedence.

This changes no seed demand, funding certificate, route, controller construction,
SELL valuation, or planned-sale state. It preserves the supplied policy/controller
pair from PR10138 and the optional funding callback from PR10116. It is a repair
to the existing research consumer, not another agent release. The single canonical
`main.py` / `exports/titan-current.tar.gz` stream is untouched and already normalizes
its clock independently.

## Executed boundary checks

`test_clock.py` passes17 methods using the actual frozen SELL / Arlene / HAZEL
source and saved observations. Coverage includes both positions, missing/null
clocks, custom periods, absent configuration, exception identity without retries,
one-argument Arlene, supplied capital state, singleton continuity and true-zero
reset, and raw loading of all three existing entry files. Exact original three
files produce1 failed assertion and15 erroring methods in that same suite; the
explicit-step method passes. These are multiple witnesses to the same clock/path
boundaries, not16 distinct policy defects.

The two real saved prefixes through checkpoint226 preserve each capital actor's
selected route. Manufactured custom-clock inputs are labeled compatibility
checks, not naturally reached game states. No engine or previous test suite is
executed by the new boundary suite.

## Full saved-input correspondence

`check_clock_prefix.py` compares the exact original explicit-clock file entry
against the repaired sparse-clock entry on four already-recorded funded paths:
frozen SELL and capital, both positions, seed9989001. All2,876 decisions match
each other and the original recorded actions. The complete tracked planned,
pending, previous-observation, observed-harvest, route, seed-event and funding
state matches at every step. All5,752 actual policy calls and5,752 nested original
controller calls are observed once per decision; these are nested counts, not
11,504 distinct decisions. Each path constructs exactly one actor per match.

Both capital paths retain MAIN -> YARN at226 and the native controller's later
route change at360. Funding reports still occur at600 and624. Caller observations
and configuration remain unchanged. No new game, interpreter transition, held
seed, speedup, strength gain, or canonical-package validation is claimed.

`CLOCK-VALIDATION.json` contains source identities, input hashes and every
per-prefix action/state digest. Full logs and per-step funding reports are in the
private evidence package; the older PR10116/PR10138 game outcomes retain their
original attribution.

## Reproduce

Use the ordinary repository layout and the already-saved PR10138 evidence inputs.
Run only the new suite, not an old collection:

```sh
python -B revenue/kaggriculture/cloud-hosted-loss-response/juniper-funding/test_clock.py \
  --root /path/to/commons/revenue/kaggriculture \
  --prefix-dir /path/to/capital-evidence/original-prefix \
  --report /tmp/seed-clock-tests.json
```

For the negative run, add `--source-dir /path/to/original-entry-files`, containing
`seed_main.py` blob35e36d3b, `arms.py` blobbb219eff and `capital_arms.py` blob0882b7df.
They are available in the immutable PR10138 merge7e70104f and the evidence package.
The tool compiles those exact bytes with the original runtime paths; it does not
import archived bytecode.

For one full saved prefix:

```sh
python -B revenue/kaggriculture/cloud-hosted-loss-response/juniper-funding/check_clock_prefix.py \
  --root /path/to/commons/revenue/kaggriculture \
  --baseline-dir /path/to/original-entry-files \
  --frames /path/to/capital-evidence/results/9989001-p0-funded.frames.jsonl.gz \
  --kind capital --position 0 --report /tmp/capital-clock-prefix.json
```

Repeat for the other position; use `--kind frozen` with the corresponding
PR10116 funded frames for the frozen actor. Frame0 is initialization; decisionN
consumes frameN's own observation and is compared with frameN+1's authored action.
No rival private observation or current rival action is passed to the policy.
The checker reports partial completion explicitly and returns nonzero on a
source-action/state or dispatch mismatch.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
