# TITAN V4 — represented physical transition execution receipt

Status: **SOURCE CARRIER BUILT / LOCAL CONTRACTS GREEN / EXACT-CHECKOUT GATE REQUIRED BEFORE MERGE**

This is the single current-V4 carrier for the represented-market physical-execution seam described by the package README and Slack build demand `1789192940.001649`. It does not create a second controller, V4 root, runtime default, composition pointer, archive, provider, or submission surface.

## Bound inputs

- branch base at claim/build start: `1bb11ccb01eb153225b050fdad96d8675dedab8f`
- raw scheduler Git blob: `a483b24dd72b580d7d8811636b54d2d44f391575`
- official engine Git blob: `3c202c7ee921da239356789e266b694635103fc4`
- canonical scheduler-prefix materializer Git blob: `f36e9120ea07c861a7eca5821a5306c6dbfa4613`

`materialize_represented_physical_transition.py` first executes the exact scheduler-prefix materializer from captured bytes, then applies one source-bound `receipt_profile()` closure. The raw executable prefix therefore remains the upstream authority and inactive suffix bytes/indexes are not compacted or reinterpreted.

## Physical theorem

Inside the admitted prefix, represented state may only gain goods or workers when execution is source-provable from the bound prestate. The carrier:

- accepts `BUY_PRODUCT` only for official WHEAT/FERTILIZER rows and only when the first quote, cash, and real shed capacity are provable;
- preserves deterministic partial fill when shed capacity proves the stop, otherwise fails closed once lockstep rival activity makes a later product quote unknowable;
- executes fixed-cost `BUY_ANIMAL` units sequentially until cash or real shed capacity stops the row;
- executes HIRE only from known cash using native Fibonacci `_hire_cost`, mutating money, `hires_today`, hand cardinality, and private inventory atomically;
- never credits SELL proceeds as later BUY/HIRE funding authority;
- invalidates later funding proof after unmodeled BUY_SEED/BUY_LAND debits;
- rejects type-coerced market quantities and receipt-critical config values;
- returns an always-false feasibility predicate whenever a represented arrival is unresolved, instead of undercounting possible future stock/actors.

## Focused execution

Local source-shaped contracts run from the carrier package:

```text
python -B  -m unittest -v test_represented_physical_transition.py test_receipt_config_guard.py
16/16 PASS

python -OB -m unittest -v test_represented_physical_transition.py test_receipt_config_guard.py
16/16 PASS

python -m py_compile materialize_represented_physical_transition.py \
  test_represented_physical_transition.py test_receipt_config_guard.py \
  test_repository_materialization.py
PASS
```

The predecessor killers cover zero-cash WHEAT/GOOSE, illegal CARROT product buy, full shed, capacity-limited partial fill, fixed-price sequential animal cash, funded HIRE, Fibonacci `1+1+2`, uncertain SELL-credit before HIRE, prior unmodeled purchase before HIRE, non-first lockstep BUY_PRODUCT quote ambiguity, type-coerced quantity, type-coerced shed capacity, and type-coerced market-cap configuration.

## Exact-checkout gate

`test_repository_materialization.py` must run from a complete current checkout before merge. It binds all three Git blobs, composes the exact prefix materializer, parses/compiles the generated scheduler, proves both prefix consumers survive, proves the physical helper appears exactly once, and proves the predecessor phantom BUY/HIRE projections are absent.

No strength, activation, gameplay-economics, or Kaggle claim is made by this source-only closure. After the exact-checkout gate is green, the package can merge as the preserved V4 repair carrier and remain default-inactive until the current one-tree gameplay admission owner consumes it.
