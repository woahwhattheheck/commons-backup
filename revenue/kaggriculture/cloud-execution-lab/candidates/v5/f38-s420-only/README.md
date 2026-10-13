# TITAN V5 F38 — S420-only source carrier

`F38` is the released single-factor ablation for the historical S420 policy on the current TITAN V5 production line. It keeps the production seller horizon at **8** and changes exactly one semantic boundary: at `step >= 420`, `FrozenSelected.transform` stops selecting **new** plans. The untouched tail still materializes inherited/base SELL rows and already-planned due commitments.

This lane is deliberately **source-only** while the runtime gate is closed. The materializer publishes only a transformed `frozen_selected.py` and `RECEIPT.json`. It does **not** build a candidate archive or component, does not mutate CURRENT/default/release state, and cannot submit to Kaggle.

## Production authority

The carrier fails closed on the exact public production20f / production-v3 identity:

- archive SHA-256: `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`
- `frozen_selected.py`: `5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef`
- `scheduler.py`: `00d72a5c6b511e73ed1923ea402c4a36e0f9490f3b4c177490ddc72440f4a64a`
- `main.py`: `b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035`
- `TITAN-CONFIG.json`: `ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af`
- member count: `92`

The CLI also reuses the production-v3 semantic-topology verifier before transforming the source. The scheduler is authenticated and retained unchanged; unlike the historical H3+S420 bridge, F38 introduces no local `HORIZON=3` shadow.

## Materialize source evidence

```bash
python f38_s420_only.py \
  --baseline /path/to/titan-v5-production-recovery-v3.tar.gz \
  --source-out /fresh/path/frozen_selected.py \
  --receipt /fresh/path/RECEIPT.json
```

Both outputs are create-exclusive and published as one custody transaction using the shared V5 publication helper. Existing destinations are not overwritten.

## Tests

```bash
python -m unittest -v test_f38_s420_only.py
python -m py_compile f38_s420_only.py test_f38_s420_only.py
```

The suite covers the trigger, pre-420 behavior, untouched post-selection tail, H3 rejection, duplicate/missing structural anchors, exact member identity gates, member-count gate, deterministic output, no candidate/component emission, and archive rejection before support loading.

## Promotion boundary

This commit is not economics evidence. Native matched economics remain blocked by the current runtime gate. When runtime-qualified execution is available again, a separate owner may materialize a candidate/component from this authenticated postimage and run the matched F38 screen. Until then, `kaggle_submission_hold=true` is part of the receipt contract.
