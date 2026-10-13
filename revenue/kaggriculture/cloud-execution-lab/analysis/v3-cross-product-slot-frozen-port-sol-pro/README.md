# TITAN V3 cross-product slot reservation — executable frozen port

Operation: `TITAN-V3-CROSS-PRODUCT-SLOT-EXECUTABLE-FROZEN-PORT-20260910-01`

This additive successor closes the integration HOLD on draft PR #12100 without
changing canonical runtime, source, configuration, archives, pointers, games, or
provider state.

## Exact composition

The parent is #12100 head
`47aa401c647f330cdd7acae31515e1351f557fad`. That donor authenticates
`scheduler.py` blob `a483b24dd72b580d7d8811636b54d2d44f391575`, adds
`_planned_slot_reservations`, and repairs the scheduler's product-local
`feasible(plan)` closure.

The selected package does not execute that closure. `TITAN-CONFIG.json` blob
`3a3bef83899d3010fad623b628d9e95d9978111b` selects `consumer=frozen`;
`titan_runtime.py` blob `b952c9c228ecbde592bf3d2df01638677abb0d24`
constructs `FrozenSelected`; and `frozen_selected.py` blob
`fc7baf5c179818a55037f6a61d92984d81d1a21c` owns a copied predecessor
closure. The donor helper is underscore-prefixed, so `from scheduler import *`
does not activate it.

This carrier therefore materializes the reviewed scheduler postimage first and
replaces exactly one copied frozen block with a call through the already-present
module import:

```python
reserved = scheduling._planned_slot_reservations(
    self.planned, current, item, now, t, orders
)
```

The helper has one owner and one implementation. The active consumer reuses it
through the module object rather than copying its rules again.

## Active-path discriminator

The exact runtime probe imports a relocated full lab, instantiates
`TitanAgent(Features(**TITAN_CONFIG))`, calls `_initialize()`, and verifies that
the constructed class and its scheduler resolve to the relocated materialized
files. It then executes `FrozenSelected.transform()` while replacing only the
expensive economic surroundings with deterministic controls; the nested
capacity callback remains the literal closure from the loaded postimage.

Four controls run in both predecessor and successor packages:

1. **Saturated current slot:** nine inherited rows, due CARROT excess, selected
   MILK excess. The predecessor admits MILK, records MILK as chosen, then the
   emitter gives row ten to CARROT and omits MILK. The successor rejects MILK
   before it can become a detached certificate.
2. **Two free rows:** eight inherited rows. Both CARROT and MILK remain admitted
   and emitted.
3. **Inherited MILK row:** a matching inherited SELL absorbs MILK quantity, so
   the active helper does not charge another row.
4. **Overdue future row:** an unretired CARROT row due before the future MILK
   candidate still reserves the shared slot. The predecessor overbooks it; the
   successor rejects it.

The successor also executes helper controls for same-item replacement, overdue
future retention, and malformed-ledger fail closure. Every probe runs twice and
must be byte-identical.

## Custody and failure closure

`materialize.py` binds the donor head, donor materializer, scheduler,
`FrozenSelected`, runtime, and package config by Git blob. It requires the exact
single copied preimage, strict duplicate-key/non-finite JSON rejection,
pairwise-distinct regular source and destination paths, and exclusive
publication with rollback if any output already exists. Its deterministic
receipt binds both source and postimage bytes.

The workflow checks out the immutable triggering head, requires a one-commit
stack directly on #12100, enforces the six-path additive allowlist, materializes
both files twice, compiles both postimages, executes predecessor and successor
through the selected runtime, binds probe hashes to the receipt, and requires a
clean repository.

## Boundary

This is an integration donor, not a gameplay-strength result. It performs no
fresh games, promotion, merge, archive rebuild, pointer update, provider action,
or Kaggle submission. T08 retains one-tree composition, official both-seat
panels, release disposition, and upload authority.
