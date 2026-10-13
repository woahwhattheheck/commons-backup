# Seed-prefix repair: independent current-class and full-interpreter checks

This is additive evidence for the ONE `repair_seed_funding_prefix.py` owned by
Slack claim `1789179343.204649`, not another implementation or runtime hook.
The independent full-class claim is `1789179346.157799` (ASTRA-SEEDPREFIX).
The later session's prototype repair was retired, not published as a donor.

## Exact inputs and boundary

The checker imports incumbent repair Git blob
`a5c2c131fd83d83d6be822556abce5723b464a50`, calls `repair(bytes) -> bytes`, and
executes the complete resulting TitanAgent class. The input is current runtime
`b952c9c228ecbde592bf3d2df01638677abb0d24` (33,885 bytes); the output is
`cbeb7f09914c351a99cb5f0970c14a7bea7cb029`. It never writes either production
source or a generated runtime tree. The checker authenticates all 110 files in
the supplied archive dependency tree before import, plus named core source pins.
It uses the real SeedBudget, funding helper, scheduler projection and full pinned
official interpreter, not a replacement market implementation.

Most cases construct a route and consumer checkpoint to isolate the seam. Four
additional cases initialize real TitanAgent/FrozenSelected objects, use the real
parent route's remaining seed bound and call `transform_selected` without
consumer or route doubles. Those cases still supply a constructed observation
and chosen action: they do NOT establish natural producer engagement.

## Reproduce

Use existing GitHub Actions artifact **10123395668**, run **34400824037**, head
`4be7772ab850e50f42d0eb0fe715fecadb19ee10`. Do not dispatch a new workflow merely
to transport these files. Its ZIP SHA256 is
`d11b9ca245dc8205dabd26523c2e431055feaa22afa3bc10866e4e3bae3db4ed`.
Use the complete `seed-retry-runtime/` subtree, not the older runtime in artifact
10285621024, a partial checkout, or a directory already modified by a transformer.

```sh
ARCHIVE=/absolute/path/to/titan-canonical-check-34400824037-1.zip
WORK=/absolute/path/to/new-empty-scratch-directory
CHECK=/absolute/path/to/seed-funding-prefix/check_seed_prefix_current_class.py
printf '%s  %s\n' d11b9ca245dc8205dabd26523c2e431055feaa22afa3bc10866e4e3bae3db4ed "$ARCHIVE" | sha256sum -c -
mkdir -p "$WORK"
unzip -q "$ARCHIVE" 'seed-retry-runtime/*' -d "$WORK"
python "$CHECK" --runtime-root "$WORK/seed-retry-runtime" --report "$WORK/current-class.json"
python -O "$CHECK" --runtime-root "$WORK/seed-retry-runtime" --report "$WORK/current-class-O.json"
```

Keep reports OUTSIDE `seed-retry-runtime/`; the complete-tree identity gate
intentionally refuses added files other than Python bytecode caches. The default
repair path is the sibling `repair_seed_funding_prefix.py`; `--repair-source`
can name another local copy, but its exact Git blob must still match.

To reproduce the negative control, add `--predecessor`: exit **1** is expected,
with 494 failed subcases and one error in each mode. Normal repair runs exit **0**.
Missing, empty, modified dependency trees and altered repair inputs exit **2**
before imports/tests. Check exit status; an input failure does not clear an old
report at the requested output path. No test is silently skipped.

## Executed evidence

Python 3.13.5: **23/23 normal and 23/23 optimized**, no errors or skips. Each run
covers 480 action-suffix cells, 160 unchanged-active-prefix controls and **348
full official callback pairs / 696 interpreter calls**: 320 suffix comparisons,
16 cash/seed witnesses, eight configured-limit comparisons and four real
FrozenSelected dispatcher witnesses. The full observation, status, reward and
environment state are compared; submitted action fields are excluded because
those intentionally differ. The cash witnesses normalize only the specifically
expected own cash/seed differences before requiring all other state equality.

Constructed real-dispatch witness: 189 WHEAT seeds cover the real future bound,
$35 cash, raw BUY_SEED 10 followed by nine empty slots and dead HIRE 11. The old
path buys three unnecessary seeds and ends at $5; the repaired path buys none
and retains $35. Both seats and both funding settings pass. Live capital orders
still use the existing funding certificate; cap 12 remains 12, while zero or
negative configured limits follow the engine's minimum-one rule.

These are component/dispatcher/callback proofs, NOT full `act` lifecycle,
whole-entrypoint deadline, hosted Python 3.11, composed current-stack package,
natural-route incidence or paired full-game strength results. No feature key,
default, production source, archive, Kaggle submission or legacy materializer is
changed by these evidence files. Existing current-stack integration/economic
gates remain necessary. Do not sum peer test counts as distinct gameplay wins.
