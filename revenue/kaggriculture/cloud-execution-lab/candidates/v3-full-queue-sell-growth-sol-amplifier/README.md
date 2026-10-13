# TITAN V3 saturated-queue same-product SELL expansion — SOL-AMPLIFIER

Operation: `titan-v3-full-queue-same-product-sell-growth-20260909-sol-amplifier-01`

## Source-proven regression

Submitted V1 could replace its first inherited SELL row for a selected product
with the full current scheduled quantity. Submitted V2 added index-preserving
materialization, but also capped every inherited SELL row to its original
quantity and rejected `q > offered` whenever the raw market list had reached the
per-turn order limit. Current V3's actual selected consumer retains both halves
in `frozen_selected.py`.

That combination treats quantity and position capacity as the same resource. A
10-row queue that already contains `SELL CARROT 1` can execute `SELL CARROT 5`
in exactly that row without adding or moving an order, yet current V3 forbids
the planner from selecting it and forbids the emitter from materializing it.
The lost four units can be lost same-turn cash, especially before inherited
fixed acquisitions.

## One-factor boundary

`growth_patch.py` reuses the exact canonical `FrozenSelected.transform` code
object with a private globals table. Only its `optimize_lot` and
`materialize_sales` global lookups are replaced:

* the capacity callback may relax `q > offered` only when the list length is
  exactly the configured maximum and a positive same-product SELL row already
  exists;
* the emitter adds only the selected excess to that first row, preserving every
  existing row quantity, unrelated row, list length, and index;
* queues below the cap, queues above the cap, blank-only opportunities, new
  products, receipt/capacity failures, and all unrelated plans delegate to the
  canonical functions.

The canonical instance's exact `_initialize` code object is also reused with a
function-private builtins table. Its sole import override returns a private view
of `frozen_selected` containing the candidate class. Neither the canonical
module binding nor `sys.modules` is changed, even transiently. The resulting
consumer owns a private transform function; sibling controls and future plain
constructions remain untouched. Canonical `main.py::agent`, its whole-call
timer, fallback, reconstruction, production guards, funding reorder, final
pressure, and release files are unchanged.

Before importing the patch or canonical entrypoint, `candidate.py` verifies the
Git-blob identities of `growth_patch.py`, `main.py`, `titan_runtime.py`,
`frozen_selected.py`, and `TITAN-CONFIG.json`. The install receipt carries that
same execution closure. A copied entry file cannot silently execute a different
patch or consumer tree.

## Action-bound evidence gate

The path-scoped panel first applies the existing isolated-worker environment
patch, then makes one fail-closed evaluator edit: it hashes the candidate
seat's canonical JSON action at every step immediately before the official
interpreter. Every admitted cell must contain exactly 719 candidate actions in
a 720-step episode and a valid SHA-256 receipt.

The panel is fixed to four seeds, four opponents (submitted V1, Arlene, Apex,
and Public BT12), and both literal integer seats: 32 paired cells / 64 official
games. A development `ADVANCE` requires all of the following:

* at least one candidate action sequence changed;
* every score-changing cell is bound to a changed candidate action sequence;
* positive mean own cash and positive mean margin globally;
* no opponent-level mean own-cash regression;
* no seat-level mean own-cash regression.

Whole-game trace drift alone cannot count as activation, and a margin-only or
seat-skewed apparent champion is rejected. This remains a development screen,
not a Kaggle or leaderboard claim.

## Gates

Nineteen focused contracts cover the predecessor-failing 10-row witness,
absent-row and receipt-failure rejections, below-cap parity, overlong-queue
containment, duplicate-row/index preservation, stock clipping, private-global
isolation, private-import reconstruction, exception containment, no
module-cache mutation, exact execution-closure binding, evaluator
instrumentation, literal-grid admission, candidate-action activation, and
opponent/seat own-cash vetoes. The workflow also verifies the canonical release
build and retains the exact-head source audit, Apex binary digest, panel JSON,
shards, and markdown verdict on every outcome.
