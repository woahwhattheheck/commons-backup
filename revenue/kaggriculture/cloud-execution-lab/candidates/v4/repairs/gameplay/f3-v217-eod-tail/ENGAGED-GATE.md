# F3 V217 EOD-tail engaged candidate

The existing F3 package already preserves the reviewed EOD-tail theorem and a current-router semantic rebase, but its live V217 caller is deliberately hard-OFF. `CURRENT-ROUTER-EXECUTION.json` verifies that rebase only at source / extracted-planner level; it explicitly does not claim full-engine or production activation.

`materialize_engaged_variant.py` closes the missing **candidate-construction** gap without adding another router or feature controller:

1. consume the exact current donor through the landed `rebase_current_router.py` source pin;
2. OFF output is byte-identical to that first-stage rebase;
3. ON output changes exactly one live-call literal:
   `..._v217_plan(..., configuration, False)` → `..._v217_plan(..., configuration, True)`;
4. AST-parse the result and fail closed on donor drift, missing/duplicate anchors, double application, non-bool admission, or alias writes;
5. leave canonical runtime/default/archive untouched.

Example source-only materialization:

```bash
python materialize_engaged_variant.py \
  ../../../donor/overlay/r04_full_router.py /tmp/f3-off.py
python materialize_engaged_variant.py --enabled \
  ../../../donor/overlay/r04_full_router.py /tmp/f3-on.py \
  --receipt /tmp/f3-on.json
```

Focused checks:

```bash
python -m unittest -v test_materialize_engaged_variant.py
python -O -m unittest -v test_materialize_engaged_variant.py
```

The tests pin the current donor Git blob, prove OFF byte identity, prove ON is the one-literal delta, inspect the `_v217_plan` call AST, and require source drift/non-bool admission to fail closed.

## Remaining acceptance boundary

This does **not** turn F3 on in production. The historical receipt reported engagement without cash realization, so the next useful gate is current-native/full-engine: natural activation count; successful FEED completion at the final pre-reset callback; avoided return-walk callbacks; animal survival/production consequence; both seats; exact source hashes; no fallback/timeouts; and matched own/rival/margin economics. A zero-realization or materially negative engaged panel rejects activation rather than weakening the theorem.
