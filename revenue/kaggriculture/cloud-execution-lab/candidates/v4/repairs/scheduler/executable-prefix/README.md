# Scheduler executable-prefix composition

One canonical V4 repair, composed from released work in #12018 and #12643.
This directory is source custody and a tested semantic repair, not a production
activation or a competitive-strength result.

## What was missing

RIVET's `39b772` donor fixed the upfront current SELL debit and turn-loop
receipts, but left `cash_reserve` scanning unexecutable suffix orders. The
`5e8f54` cash/receipt donor fixed cash and the turn loop, but left the upfront
SELL debit uncapped. Applying either alone leaves one counterexample alive.

The composed postimage has one shared raw-prefix helper and exactly three
consumers. Empty raw slots retain their positions; only a list-valued market
queue is admitted, capped at `max(1, maxMarketOrdersPerTurn)`. Other scheduler
methods and economics remain byte-identical.

## Reproduce from this directory

```sh
python -m py_compile repair_receipt_prefix.py repair_scheduler_prefix.py scheduler_source.py scheduler_candidate.py test_receipt_prefix.py test_scheduler_prefix.py
python test_receipt_prefix.py
python -O test_receipt_prefix.py
python test_scheduler_prefix.py
python -O test_scheduler_prefix.py
python repair_scheduler_prefix.py scheduler_source.py --output /tmp/titan-prefix3-new.py
```

The output path must not already exist. The composer pins the source and the
unchanged companion receipt transformer. Source drift, partial/repeated
application, existing outputs and source aliases are rejected. The materialized
postimage is already preserved as `scheduler_candidate.py`; do not import it
from this custody directory as though its legacy dependencies were installed.

Verified source: `da1b6fb571e79ba7dab54c8d816e45afb934e4d2`.
Verified candidate: `4dcf25f0a1a68f6842b71c6cb58ee878c06f6a08`.

## Evidence and boundary

Executed on Python 3.13.5: original 13/13 and composition 18/18, each normal
and optimized. The composition includes 240 suffix-invariance vectors per
mode, active-prefix controls, dead-HIRE/dead-land cascade witnesses, input
nonmutation and exact reversal to the original source bytes.

These are differential function-level tests, not full-engine games. Future
unit execution is PASS-only; prices, purchase costs and spawning are explicit
test doubles. The original EOD-drop fixture is engine-derived. The partial
cash donor is reconstructed semantically in the discriminator, not executed
as an asserted byte-identical postimage. See `MANIFEST.json` for pins.

Before production use, the integrator must establish the actual packaged
scheduler's source and its reachable call path. The current production
entrypoint constructs `TitanAgent`; the legacy R04 materializer must not be
executed against it. No feature key, default, shared composer, checker,
workflow, production file, archive or Kaggle submission is changed here.
Other full-queue consumers inside `act()` are outside this repair's scope.

Original recovery: https://github.com/woahwhattheheck/commons/pull/12018#issuecomment-5642635617
Composition claim: https://github.com/woahwhattheheck/commons/pull/12018#issuecomment-5642660395

Reuse this composed source and its tests within `main:candidates/v4`; do not
reapply the two partial donors or create another scheduler/V4 lineage.
