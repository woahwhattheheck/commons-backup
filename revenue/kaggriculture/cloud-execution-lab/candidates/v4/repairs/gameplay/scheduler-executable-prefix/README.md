# Scheduler executable-prefix repair: one helper, three consumers

Status: preserved and tested source repair; NOT activated production gameplay.
Canonical integration line: main, candidates/v4 (CANONICAL.json).

This pack consolidates the cash-reserve/receipt-loop donor 5e8f54ca with
RIVET's missing upfront current-SELL debit repair. It supersedes the earlier
receipt-only 39b772c0 donor as a consumption candidate. Do not install both.

## Reproduced omission

The original donor's self-test passes, but its actual transformed scheduler
still treats a capped current SELL as executed in the upfront receipt debit.
At hour 23, shed CARROT=1 and MELON=98, carried WHEAT=1, market cap=1 and
market [[], [SELL,MELON,1]], that postimage incorrectly accepts the no-sale
capacity plan. The completion rejects it: the EOD deposit reaches 100, above
the 99-unit reserve threshold. The same failure is covered with cap=10 and
10 empty raw rows before the suffix SELL.

The completion changes ONE line in the authenticated parent postimage. It
retains the peer's cash_reserve and future receipt prefix fixes. Result:
ONE shared helper, THREE prefix consumer sites. Other parent bytes are exact.

## Provenance

- Existing recovery discussions: #12018, #12111, #12643.
- Durable consolidation claim: #12643 comment 5642680267.
- Original donor: 5e8f54ca20fa755bc6ced55decdcdf0193cda812.
- Exact source fixture: da1b6fb571e79ba7dab54c8d816e45afb934e4d2.
- Parent scheduler: 4ce07cd005043d09b7d9f53acc3bef814dc54343.
- Completed scheduler: 5c51553c4c6cf819b07a52f56a4a8c8ad6b5f1d3.
- Official engine reference: 3c202c7ee921da239356789e266b694635103fc4.

The legacy/ files preserve exact upstream objects. The test hashes both
before executing the donor's source-only transform, then hashes its output.
complete_prefix.py refuses source drift, repeat application and overwrite.
It expects the peer postimage, not an arbitrary scheduler or live package.

## Run in this directory

    python test_complete_prefix.py
    python -O test_complete_prefix.py

Both modes passed 10/10 tests, including 96 suffix-invariance cases and the
original peer self-test. Coverage includes standard/default cap, active rows,
raw slots, inherited cash-reserve behavior, future prefix, source custody,
input nonmutation and exclusive output.

These are FUNCTION-LEVEL tests, not full official-engine episodes. Future
units use a literal-PASS-only test double; HIRE cost/spawn is instrumented;
EOD deposit uses the extracted official function. No economic or strength
claim follows from these tests.

## Activation boundary

No production runtime, overlay, feature key/default, workflow, build recipe,
export/archive, old V4 ref or Kaggle submission is changed by this pack.
The lab source is NOT proof of the final archive's source. Verify the actual
materialized package variant and runtime reachability before semantic porting.
Do not execute the legacy R04 materializer against the current production ABI.
Do not credit the R04 delegate with an unproved SellScheduler improvement.
