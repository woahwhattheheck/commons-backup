# Ordered consumer executable-prefix repair

This extends the existing canonical V4 executable-prefix package. It is not a
second V4 root, controller, feature key, or runtime entrypoint. The prior
scheduler repair files in this directory are untouched.

## Exact current source

`integrated_selected.py` Git blob `defa9b84c77fff28ae107bce291b6235bec5d26c`
was read from current main and independently matched in existing workflow
artifact 10289166804. The composer changes five literal anchors inside only
`IntegratedSelectedAgent._projection` and `IntegratedSelectedAgent.transform`.
Output blob: `282d58612f80fec29109fbcd38fac0b317063c17`.

The official engine takes the raw prefix `market[:max(1, int(cap))]`. Empty
rows count as slots. The predecessor stopped a future projection on a dead
suffix BUY_PRODUCT and treated a dead suffix HIRE/acquisition as a funding
obligation after an eligible seed reduction. The repair uses the same capped
prefix in both consumers and supplies the engine-clamped limit to ALDER.
No row is filtered, reordered, added or deleted by the prefix repair itself.
The existing ALDER reduction retains its own original ownership and guards.

## Executed witnesses

With cap10, BUY_SEED WHEAT10 in row0 and HIRE in dead row10, one future WHEAT
PLANT requires only one seed. Real ALDER through the actual class previously
retained10 seeds: a $100 engine fixture ended with cash0/seeds10/hands0.
The repaired result ends with cash90/seeds1/hands0. The actor count does not
change. An executable HIRE remains a funding barrier and retains the original
queue unless the incumbent selector certifies it.

At cap1, a future `[[], [BUY_PRODUCT, WHEAT, 2]]` previously cut the projection
at step100. The repair reaches step108 and includes a scheduled step101
DROP(+3 MILK), without treating the dead purchase as inventory or cash.
The unchanged eight-step, EOD, route-switch, final-step and stock-dependent
PICKUP boundaries are exercised separately.

17 tests pass under normal Python and Python -O, with zero skips. Each mode
includes108 projection suffix cases,108 seed suffix cases,108 full official
market differential pairs, six further nonpositive-cap/seat engine checks and
two deliberate predecessor variants. Actual ordered SELL-consumer invocation
also preserves the seed repair and corrected projection packet.

## Reproduce

Use an already materialized reference package whose eleven input blobs match
`PINS` in the runner. The exact inputs are present under `seed-retry-runtime/`
in artifact10289166804. Its old `titan_runtime.py` and `scheduler.py` are NOT
current main and are not imported by these tests. The runner refuses missing
or changed inputs with exit2 rather than skipping tests.

```sh
P=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/scheduler/executable-prefix
python -B "$P/check_ordered_consumer_prefix.py" --package-root /path/to/seed-retry-runtime
python -O -B "$P/check_ordered_consumer_prefix.py" --package-root /path/to/seed-retry-runtime
python "$P/ordered_consumer_prefix.py" /path/to/current/integrated_selected.py --output /tmp/integrated_selected.prefix.py
```

The composer requires the exact current source, rejects double application,
checks AST scope, and refuses existing destinations, in-place writes and
file aliases. It never executes the source or legacy `apply_v4.py`.

## Integration boundary

This is component correctness on constructed engine fixtures, not a full-game
or current-whole-package gate. Production, archive, defaults, entrypoint and
Kaggle are unchanged. The current shipped frozen consumer does not become
stronger merely because an optional ordered consumer is repaired. The one V4
composer can consume this exact semantic delta once when validating that
consumer. Current TitanAgent seed-prefix and return/snapshot-lifecycle peers
retain their separate runtime files; do not copy this entire archived package
into production.
