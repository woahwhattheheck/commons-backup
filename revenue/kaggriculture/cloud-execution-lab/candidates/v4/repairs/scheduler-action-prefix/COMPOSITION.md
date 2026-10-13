# One current scheduler-prefix composition

The existing modern `scheduler_action_prefix.py` is the consumption target for
current scheduler blob `a483b24dd72b580d7d8811636b54d2d44f391575`. Its exact
postimage is `742a200e9a72e303ad18c51c104895013a7f3a4b`: one
`_engine_market_prefix` helper, six consumers, unchanged raw suffix rows.
This packet adds validation, not another implementation or V4 branch.

## Do not replace modern source with the legacy three-consumer candidate

`../scheduler/executable-prefix/scheduler_candidate.py` at
`4dcf25f0a1a68f6842b71c6cb58ee878c06f6a08` is useful preserved donor evidence,
but is not a replacement for the current scheduler. Its prefix changes overlap
this package. Its older receipt implementation has a current-sale predebit and
does not reproject the current unit stage without the shed cap. It also does
not repair the scheduler's action-output and pending-plan consumers.

The full-module/full-interpreter regression distinguishes both errors:

* With cap 1 and market `[[], ['SELL', 'MILK', 4]]`, the official interpreter
  sells nothing. The modern predecessor and legacy three-consumer candidate
  nevertheless set pending MILK to zero and erase its future plan. The existing
  modern six-consumer output retains pending 4 and that plan without changing
  the returned raw action.
* With 99 WHEAT in the shed and 2 carried MILK, `DROP MILK 2` followed by
  `SELL WHEAT 10` loses one MILK before market execution. The old receipt
  accepts the impossible no-loss plan; modern predecessor and modern repaired
  output correctly reject it. Reducing initial WHEAT to 97 supplies a positive
  admission control, so blanket rejection does not pass.

Both witnesses execute for both physical seats. Other checks cover current and
future cash reservations, future inventory and sale references, partial sales,
nonpositive cap normalization, malformed ignored suffixes, observation
nonmutation, and exact source/transformer/output identity. AST comparison proves
all modern top-level definitions other than `SellScheduler`, including
`post_units`, `MarketPath`, and `optimize_lot`, remain unchanged.

## Reproduce without modifying production

From the repository root, set `PACKAGE` to a directory containing the eight
exact dependencies pinned in `check_scheduler_composition.py`. The recorded
run recovered these from the existing workflow artifact 10285621024,
`seed-retry-runtime/`. That archive is historical dependency custody, **not** a
current TITAN runtime artifact. A checked-out package with the same exact files
also works. Every dependency and all three source inputs are mandatory and
hash-checked before import; a missing engine file fails before the preserved
loader could attempt a download. No network is needed or used by a successful
run. All generated modules and import bytecode are confined to a temporary
package, not the input directories.

```bash
LAB=revenue/kaggriculture/cloud-execution-lab
MODERN="$LAB/candidates/v4/repairs/scheduler-action-prefix"
LEGACY="$LAB/candidates/v4/repairs/scheduler/executable-prefix/scheduler_candidate.py"
PACKAGE=/path/to/pinned/seed-retry-runtime

python "$MODERN/check_scheduler_composition.py" \
  --package "$PACKAGE" --legacy "$LEGACY"
python -O "$MODERN/check_scheduler_composition.py" \
  --package "$PACKAGE" --legacy "$LEGACY"
```

The default source and transformer are the existing `scheduler_before.py` and
`scheduler_action_prefix.py` beside this runner. To test whether a fresh
production scheduler still matches the reviewed source, supply
`--source "$LAB/scheduler.py"`; drift must fail closed, not be silently rebased.

The identical behavioral suite can test the exact negative controls by adding
`--subject current` or `--subject legacy`. These runs **must exit 1** with the
recorded discriminating failures; they are not alternative production modes.
Wrong source, transformer, legacy file, invalid package path, and missing engine
inputs were separately executed and all returned 2 with empty standard output.

## Executed receipt and remaining boundary

`COMPOSITION.json` records exact runner/source/dependency identities and results.
Python 3.13.5: **11/11 normal and 11/11 optimized**, zero skips. Each mode executes
513 full official-interpreter calls, 120 capped-sale custody cells, 80
full-state suffix-equivalence pairs, and 20 partial-prefix sale cells. A separate
real-parent smoke trace uses the unmodified `parent.Agent`, two seeds, both
seats, and 24 callbacks: 96 paired callbacks with equal actions and states.
The other tests use a deterministic authored-route fixture, not fake physics,
receipt math, optimizer, or interpreter. The pinned loader executes the actual
upstream seed-helper function rather than substituting seed behavior.

Exact modern predecessor: 154 failed assertions/subcases plus 4 errors in each
mode. Exact legacy three-consumer candidate: 144 failed assertions/subcases plus
4 errors in each mode. These counts are negative-control results, not game
losses. The original 33-test package suite and all donor bytes were preserved;
this receipt does not claim to have rerun that separate suite.

The 24-callback openings are not full games. No current `titan_runtime` wrapper,
selected-controller call path, packaged archive install, hosted Python 3.11 run,
field economics, default, or Kaggle submission was exercised or changed. The
existing integrator should consume this **one** modern transform, verify its
exact current-package reachability/default behavior, and then run the declared
paired field gate. Preserve the legacy package as donor/history; do not apply
both transformers or copy the legacy scheduler over modern source.
