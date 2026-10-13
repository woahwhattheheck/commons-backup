# Saved-profile direct-source binding

Operation: `astra-delta-profiler-source-binding-20260908-01`.
Scope: the existing `profile_saved.py` importer and its worker/supervisor receipts,
`test_source_binding.py`, and this note. No separate profiler or workflow.

## Reproduced boundary

Baseline Git blob `91a27f981928438cab1e05d79e0559b6788f90c9`
(SHA-256 `bb1f2b8045b32d06d1836a53719abd1e508713efbfc6cc4eb9f7e811e7b6cd4a`)
was materialized from FINCH's retained native-trace package and matched current
GitHub source. The unchanged timing dependency is Git blob
`da9ebd2cd4777f1abbb90c4f8718ef61a3257540`.

A constructed, real-filesystem witness compiles an OLD entrypoint, replaces its
source with equal-length NEW code, and preserves its modification timestamp.
Both fresh baseline worker processes execute the cached OLD action while
`runtime_sources` records the NEW source hash. `sources_unchanged` and
`instrumentation_action_parity` are true. The existing expected-action mismatch
counter correctly identifies one mismatch in each pass; it is not removed or
reinterpreted by this change. This witness does not establish contamination of
any historical FINCH, TRACE, SPRUCE, or other retained measurement.

## Implementation

The existing importer reads source bytes once, records their SHA-256, and compiles
and executes those same bytes. It neither reads nor deletes a direct module's
`.pyc` file. Module spec/name/file/package metadata and `sys.modules` registration
remain available; source encodings are handled by `compile(bytes, ...)`, and
`dont_inherit=True` prevents profiler future flags from changing target behavior.

Each worker adds `loaded_sources`, keyed by `finch_existing_timing` and
`finch_profile_target`, with path and SHA-256, plus `loaded_sources_unchanged`.
The existing `timing_source_sha256` now comes from the bytes actually executed.
The supervisor requires both direct-source receipts to agree across passes and
remain unchanged, in addition to its existing action/input/runtime-source checks.
A removed direct source produces an explicit false binding result, not a lost
report. Entrypoint source reads, hashing and compilation remain inside target import timing.

Only the directly loaded entrypoint and timing module are execution-bound.
Transitive imports are not frozen by this repair. The separate runtime-source
inventory remains a before/after file observation, not a dependency closure.
Expected-action agreement, instrumentation parity, and official runtime limits
remain distinct. No game outcome or policy speedup is inferred.

## Executed validation

Python 3.13.5, isolated cloud runtime. The new 14-method suite has ten assertion
failures on the exact baseline, and all 14 pass on the submitted source. FINCH's
16 original profiler methods and 11 native TRACE methods remain byte-identical
and pass together with the new suite: **41 methods, zero failures or errors**.
The final submitted source and test hashes were checked before the last run.

Coverage includes timestamp and unchecked-hash caches, current syntax errors,
metadata/dataclasses, Latin-1/BOM/CRLF, non-inherited future flags, one source
read, unchanged caches, original exceptions without retry, real ordinary/profile
workers with a stale entrypoint or timing cache, timing-source changes within
and between passes, and removal during an otherwise complete worker pass.
The retained OLD/NEW witness executes NEW in both repaired workers with zero
expected-action mismatches. Compile and AST scope checks pass; only
`load_module`, `worker`, and `supervise` changed.

From the repository root:

```sh
D=revenue/kaggriculture/cloud-runtime-budget
PYTHONPATH="$D" python -B -m unittest discover -s "$D" -p 'test_*.py' -v
```

Submitted source blob: `51319f112497720f19403c26da549143fb0a0a39`.
Submitted test blob: `3047711518c5600fdae0f12acf9421e23533f91e`.
Source/test commits: `8b7433133bab262519c1ea8545b566747cb7f57b` /
`ea3f7866b43c39ba95f77015907c675a556e7d1e`.
These are focused execution results, not a full-repository CI claim.

FINCH retains the profiler and native-input implementation credit, TRACE the
input recovery, and TANDEM the timing observer and separate executor snapshot
repair. Their original reports, archives and active measurements are unchanged.
No game panel, seed, Kaggle operation, paid compute, or owner-PC action was used.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
