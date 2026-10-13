# TITAN V3 cross-product SELL slot reservation closure

Operation: `TITAN-V3-CROSS-PRODUCT-SELL-SLOT-RESERVATION-CLOSURE-20260910-01`

This additive carrier binds exact current `scheduler.py` Git blob
`a483b24dd72b580d7d8811636b54d2d44f391575` and closes a product-local versus
shared-queue mismatch without changing the canonical package.

## Exact predecessor

`SellScheduler.act()` asks each product's `feasible(plan)` whether a proposed
SELL fits.  That predicate sees only the inherited market row count and the
matching inherited quantity.  It does not charge the appended row already
promised to every *other* product in `self.planned`.

At a ten-row cap, use nine inherited non-target rows, a due CARROT excess
tranche, and a newly selected MILK current tranche.  The predecessor admits
MILK because `len(orders) == 9`.  Final settlement iterates sorted target names,
appends CARROT into row ten, then silently omits the diagnostics-marked chosen
MILK sale.  The returned action is detached from the optimizer certificate.
The same slot can be promised prospectively by separate calls scheduling
CARROT and MILK for one future date.

## Repair theorem

After the independently owned route-reference normalization, every nonzero
`self.planned[product]` quantity is scheduler-owned excess above fixed inherited
route SELLs.  It therefore needs one appended market row when due.  Before a
candidate uses an extra row, the closure counts one reservation for each other
product due by that step:

- `due <= now` for the current action only when current target quantity exceeds
  inherited same-product SELL capacity;
- every retained nonzero row due at or before a future candidate date, including
  temporarily absent or overdue products that current source can later resurrect;
- one row per product regardless of tranche count or quantity;
- no reservation for the candidate product, whose prior plan is being replaced;
- no extra row when the requested quantity already fits inherited matching SELL
  rows; and
- malformed internal rows fail closed.

The portable witness proves predecessor admission, actual alphabetical MILK
omission, successor rejection, and the two-call future collision.  The source
materializer authenticates the exact Git blob, requires unique preimages,
creates a parseable postimage, and emits a deterministic receipt.

## Composition boundary

This consumes but does not duplicate #12057's route-floor normalization.  It is
complementary to #12027's current-turn multi-coordinate overlay and deliberately
does not claim #12043's raw-prefix seams, saturated-row growth, price/receipt
semantics, cash reserve, canonical runtime/config/archive/pointers, gameplay
strength, provider publication, Kaggle upload, merge, or promotion.

A one-tree owner should compose the reviewed slot ledger with the normalized
excess representation, then require returned-action activation and a complete
both-seat official-interpreter panel before any strength claim.
