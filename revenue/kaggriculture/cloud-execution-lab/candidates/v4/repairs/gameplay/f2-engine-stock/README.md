# F2 engine-stock semantics repair pack

Status: **canonical repair evidence only; not production activation**.

This package preserves a receipt-backed F2 correction discovered on legacy donor
PR #12609 while `main` / `candidates/v4` is the sole V4 integration line.
Nothing here advances an old V4 ref, executes the legacy materializer, or turns
F2 on in production.

## Proven defect

Legacy F2 helper blob `00cbafea47a5dd753a97fc047efffe15627e42f5`
contains a public-stock availability veto equivalent to:

```python
wheat_stock = inventory.get("WHEAT")
if type(wheat_stock) is not int or wheat_stock < quantity:
    return None
```

That second predicate is not an engine-executability theorem. The pinned official
Kaggriculture engine blob `3c202c7ee921da239356789e266b694635103fc4`
quotes `BUY_PRODUCT`, then `_commit_unit` checks cash and shed capacity only;
on success it decrements `market["inventory"][item]` without requiring the
public inventory to remain nonnegative. Negative public inventory is therefore
reachable under official semantics.

## Required semantic port

When F2 is ported into the canonical V4 implementation:

* keep strict observed-stock **shape** custody: WHEAT public inventory must be a
  literal Python `int` (so bool/float/string/None/missing shapes fail closed);
* remove the `wheat_stock < quantity` availability veto;
* a qualifying q=2 F2 buy must remain admissible at literal public WHEAT values
  `2`, `1`, `0`, and `-1`;
* preserve independent F2 guards already proven elsewhere: +25 same-turn funding
  bound, exact numeric money handling, shed capacity, V217 counterfactual proof,
  complete remaining-day cash proof, and malformed future-market barriers;
* do not describe a nonnegative public-stock threshold as correctness. If such a
  threshold is later desired, it must be an explicitly measured economics/strength
  policy with separate evidence.

## Preserved donor artifacts

`legacy/r04_feed_prebuy.py` is the exact pre-repair helper object.
`legacy/test_v4_feed_prebuy.py` is the exact focused test object from the same
legacy head. `legacy/patch_f2_engine_stock_semantics.py` is the exact
ancestry-neutral repair donor published during the audit; it is preserved for
provenance and must not be treated as a production installer.

Durable review receipts: legacy PR #12609 comments `5642629016` and `5642633812`.
The package is intentionally isolated from checker repairs and production runtime
files until a separate canonical semantic-port + execution gate proves promotion.
