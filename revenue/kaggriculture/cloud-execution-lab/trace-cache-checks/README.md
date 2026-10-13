# SeedBudget cache: real default-consumer acceptance

This is TRACE-9042's additive acceptance check for PR10167, source
`9db2f2f94666b3ca126f97ab98d28f9a3814de4f`. It changes no runtime, selected policy,
release archive, builder, workflow or existing experiment. The subsequent a8af2b83
checkpoint is a different source and is not covered by these results.

## Executed result

Three fresh processes each ran four complete retained 719-observation prefixes
through the actual `main.agent` and `TitanAgent`, with seed and funding enabled.
The first process used the shipped cache. The second replaced only `_derived`
with the same current `_derive` function. The third used the exact retained
pre-cache ALDER `SeedBudget` class, SHA256
`455024a4179a95ad597492e1f4b94de7bd3bfe7a3a88fd0dce46001f629ec3cd`.

All 5,752 cached-versus-comparator action/state pairs match. The 12 complete
prefix executions made 8,628 actual Arlene parent calls, exactly one per decision,
with no error or deadline fallback. Each mode kept one actor throughout a prefix,
constructed a new actor at the next real step zero, and created four separate,
initially empty event lists. Cached mode derived its tables once, reusing the same
tables for the next three matches; uncached mode derived four times. Derived table
contents match the original ALDER class as well as the uncached current class.

The compared state includes the selected route, complete SELL planned/pending
state, previous observation, observed-harvest history, seller diagnostics, seed
budget events, funding diagnostics, selected action, post snapshot and ready flag.
Wall-clock and CPU fields are excluded. Caller observations and configurations
remain unchanged. Every imported default-runtime file is covered by the source
pins and is unchanged after execution.

The four old prefixes are 9965001 and 9965019, both positions, from DELVE's
already-retained frozen-SELL observations. Current seed funding is active: on
9965001 it changes steps 600 and 624 in both positions. At 600 the retained seed
purchase becomes one unit in position 0 and two in position 1; at 624 it is removed.
The 9965019 action streams are unchanged from their recorded originals. All three
comparison modes agree. Final controller program hashes are recorded in each
worker report: `7015cc00acfa4922` for 9965001 and `dc76e4003029ac51` for 9965019.
These are fixed-input checks: the later observations still come
from the original games, so their terminal money is not a new outcome for the
current candidate and the seed changes are not new cash-gain evidence.

## Source and input identity

`SOURCE-PINS.json` binds the 11 exercised files to PR10167. This is exact
**default-source closure** acceptance, not validation of every member in the
73-file current tarball. The old 195741-byte Library archive was used only for
unchanged dependencies; changed files were taken from pinned GitHub reads and
checked against their Git blob IDs. LANDING's subsequent existing
`TITAN-LARCH-route-recovery-20260908.zip` independently supplied byte-identical
copies of all nine Python dependency files; that package's SHA256 is
`6ef85aaee31f446d722a91680b42b07145ed174d260b96eb23b8fcf7d1ad568d`.
The complete PR10167 archive was not materialized here and no replacement archive
was generated.

Input is the existing Library `TITAN-DELVE-funded-seed-evidence.zip`, file ID
`file_000000008fe481f58309a3cfde721385`, 6303320 bytes, SHA256
`aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`.
All 218 manifested members were checked. Each selected prefix has 720 retained
frames and 719 candidate telemetry rows. Its original joint actions, banks and
terminal observations reproduce the saved evaluator digest without executing an
interpreter. Frame k provides the copied own observation/configuration, with the
original driver's step and remainingOverageTime injection; frame k+1 provides the
original expected action. The terminal frame is not used as a new input. No
`info.seed` or rival-private observation is passed to the policy.

## Reproduce

Use a clean, isolated copy of the pinned source closure or the matching repository
revision; do not modify a running job or a newer canonical package. Supply the
original comparator outside the runtime root, as in the saved acceptance package.
Python 3.13.5 was used; the checker needs only the standard library and makes no
network requests.

```sh
python -B check_cache_prefixes.py \
  --root /path/to/pinned-default-runtime \
  --evidence /path/to/TITAN-DELVE-funded-seed-evidence.zip \
  --original /path/to/seed_budget_original.py \
  --output /tmp/cache-prefix-validation.json
```

The default command starts one process per comparison mode, sequentially. It saves
three complete per-step digest reports, original stdout logs and the comparison
summary. Runtime source is never rewritten. The canonical one-second guard remains
active, but identical test instrumentation preloads modules in every mode, so these
runs are not cold-start or performance measurements. The original implementation's
source file is retained in the repository at
`reference/historical/seed_budget-before-derived-cache.py`; copy it outside the
runtime root for the explicit comparator input.

`validation.json` retains exact report hashes. Full original reports, command logs,
source pins and runnable default-only source closure are saved in Bryce's Library
as `TITAN-TRACE-cache-prefix-PR10212.zip`, file ID
`file_000000000de481f5947a6ed625595cee`, 801686 bytes, SHA256
`b6b0098b60f38e4c50108006cc29ff5abe26437007f14d461b7b8f3cd209371b`.
That acceptance package is not a second product release. The existing DELVE input
ZIP is reused, not repackaged as new evidence.

## Complete-report follow-through

The original `compare()` paired cells with `zip` without first checking the full
matrix. A detached original-mode report truncated to one cell could therefore
return `complete=true` for only 3,595 pairs. The original complete 5,752-pair result
is intact. The same consumer now checks all three completed worker reports, every
expected cell and position, all 719 per-decision records, source/input identities,
call counts and fresh-event records before pairing. Report source references come
from the supplied pins rather than a fixed historical label.

Twenty-three saved-report regression methods pass. Exact original checker
`bcdae525` has 18 assertion failures and one malformed-report error in those same
methods. The healthy summary is unchanged. `REPORT-COMPLETENESS.json` preserves
both results. Input alignment, state extraction, loading and source checks are
unchanged; the worker's only change is its output source-reference value. There
were no additional actor calls or game executions for this follow-through.

```sh
python -B test_report_completeness.py \
  --reports /path/to/extracted/acceptance \
  --output /tmp/report-completeness.json
```

## Scope

No new games, interpreter calls, environment seeds, held evaluation or leaderboard
claim. No cancellation was injected; LARCH owns the separate recovery checks.
Optional ordered, terminal-routing and history modes were not exercised. This
result does not replace CONTINUITY's older seed-disabled result, the builder's
focused cache tests, WIDEFIELD's actual game results, or the next checkpoint's
source-specific acceptance. The canonical builder can reuse this exact result
without repeating its saved prefixes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
