# V4 committed-seed retry executable-prefix repair

Status: **canonical current-ABI donor; not activated by this package**.

Current `cloud-committed-seed-retry/seed_retry.py::apply_committed_seed_retry()` has two raw-tape reads that are stricter than engine execution:

1. the future reserve-window `BUY_PRODUCT` veto scans every raw market row; and
2. inherited `SellScheduler.cash_reserve()` sums every raw market row.

The engine and the current `FrozenSelected` funding trace execute only `market[:maxMarketOrdersPerTurn]`. Therefore an engine-dead suffix row can falsely veto a committed seed retry or create phantom reserved spend.

`exec_prefix.py` is deliberately feature-local. It provides the configured executable prefix, a prefix-only dynamic-product veto, and a prefix-only reserve adapter that reuses the incumbent `_order_spend` state transitions. It does **not** change shared seller reserve semantics, selected/route tapes, feature defaults, or `propose_seed_retry()` appendix-only admission.

## Integration seam

Inside `apply_committed_seed_retry()` only:

- derive the configured positive `maxMarketOrdersPerTurn`;
- apply the existing hard `BUY_PRODUCT` veto only to that prefix in every represented queue;
- replace this feature's call to `runtime.consumer.cash_reserve(...)` with `prefix_cash_reserve(...)`;
- preserve all other guards and funding certification unchanged.

## Exact receipt

- helper: `exec_prefix.py`
  - Git blob `dc8a4e0e268b0e488946fcb0fc5282c9a0f3442d`
  - **3,003 bytes**
  - SHA-256 `47bb4a12d9a1761c5719cff363f0c480d9628057382ac7ed6ded4f7bd181db89`
- focused test: `test_exec_prefix.py`
  - Git blob `bb9fea12b215f0e7404d3ccbc12f7390d95ffa79`
  - **5,371 bytes**
  - SHA-256 `5843b5bb4081c4f83e9970bea65583e49c1f359a197ac140b88f7d3fb882d238`

Exact server pair was reconstructed locally by Git identity and rerun:

- `py_compile`: PASS
- normal self-test: **22/22 PASS**
- `python -O`: **22/22 PASS**

Coverage includes dead-vs-live suffix behavior for `BUY_PRODUCT`, `HIRE`, and `BUY_SEED`; current and future queues; non-default limits (`12` and `3`); malformed limits/tapes; non-mutation; and cross-turn dynamic-product vetoes.

No activation, default flip, production/Kaggle ref movement, shared `cash_reserve()` edit, or sibling V4 root is authorized by this receipt.
