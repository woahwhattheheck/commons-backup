# TITAN weed-evidence provenance quarantine

This lane prevents benchmark evidence from claiming **W0** (weed continuation
disabled) when the exact runtime under test can still execute weed continuation.
It is deliberately a control-plane tool: it does not change gameplay policy,
package assembly, providers, or the canonical agent.

## Why this exists

Legacy TITAN builds used `P0`/`T0` (pathing and tempo off) as shorthand for a
fully disabled `SpatialTempo`. That shorthand is not sufficient when
`SpatialTempo.transform()` can call `_continue_weed()` before its P/T disable
return. Panels labeled `P0`, `T0`, or `R0P0O0` can therefore mix different weed
semantics and produce invalid ablations or promotion comparisons.

The certifier binds and analyzes the exact bytes of:

1. `spatial_tempo.py`
2. `titan_runtime.py`
3. `main.py`
4. `TITAN-CONFIG.json`

`main.py` is part of the proof because it loads the JSON mapping and expands it
into `Features(**feature_data)`. A source flag and config key are insufficient
if that executable edge is missing, replaced, or detached.

It emits SHA-256 and Git-blob hashes, a deterministic receipt ID, static facts,
and one of five classifications:

| Classification | Meaning | Claimable label |
| --- | --- | --- |
| `EXPLICIT_W0` | Weed capability is independently disabled end to end, or absent | `W0` |
| `EXPLICIT_W1` | Weed capability is independently enabled end to end | `W1` |
| `LEGACY_PRE_GATE_W1` | Legacy runtime can execute weed before the P/T disable gate | `LEGACY_PRE_GATE_W1` only |
| `COUPLED_WEED` | Weed is coupled to P/T rather than independently controlled | none |
| `AMBIGUOUS` | Source, wiring, config, or proof is incomplete | none |

Unknown Boolean forms fail closed. A claim is accepted only when its
declared semantics match a receipt that is recomputed from the exact checkout
at gate time. Otherwise it is quarantined.
Artifact drift, revision drift, a recomputed forged receipt, or malformed input
is invalid.

## Promotion contract

Run the certifier from the exact checkout and archive the receipt alongside the
panel output:

```bash
ROOT=revenue/kaggriculture/cloud-execution-lab
LANE="$ROOT/analysis/titan_v3_weed_evidence_provenance_20260910"
REVISION="$(git rev-parse HEAD)"

python "$LANE/weed_evidence_certifier.py" certify \
  --spatial "$ROOT/spatial_tempo.py" \
  --runtime "$ROOT/titan_runtime.py" \
  --entrypoint "$ROOT/main.py" \
  --config "$ROOT/TITAN-CONFIG.json" \
  --revision "$REVISION" \
  --require EXPLICIT_W0 \
  --output weed-semantics-receipt.json
```

Create a claim that is bound to the receipt and then gate it:

```bash
python "$LANE/weed_evidence_certifier.py" make-claim \
  --receipt weed-semantics-receipt.json \
  --claim-id panel-apex-001 \
  --declared W0 \
  --label R0P0O0 \
  --output weed-evidence-claim.json

python "$LANE/weed_evidence_certifier.py" gate \
  --receipt weed-semantics-receipt.json \
  --claim weed-evidence-claim.json \
  --spatial "$ROOT/spatial_tempo.py" \
  --runtime "$ROOT/titan_runtime.py" \
  --entrypoint "$ROOT/main.py" \
  --config "$ROOT/TITAN-CONFIG.json" \
  --revision "$REVISION" \
  --output weed-evidence-decision.json
```

Exit codes are stable for CI and orchestration:

- `0`: classification requirement or evidence claim accepted
- `2`: classification requirement failed or claim quarantined
- `3`: malformed/unverifiable input

`run_checkout_gate.sh` is the one-command integration wrapper. It refuses to
create a W0 claim unless the checkout certifies as `EXPLICIT_W0`.

## Integrator rules

- Never infer W0 from P0/T0 or `R0P0O0` alone.
- Never reuse a receipt after any of the four bound artifacts changes.
- Archive receipt, claim, gate decision, source revision, and panel output as
  one evidence unit.
- Legacy panels may remain useful, but must be relabeled
  `LEGACY_PRE_GATE_W1`; they cannot establish W0 behavior.
- A repair is not complete until constructor storage, source guard, runtime
  feature wiring, entrypoint config forwarding, and JSON Boolean config all
  agree.

## Tests

```bash
cd revenue/kaggriculture/cloud-execution-lab/analysis/titan_v3_weed_evidence_provenance_20260910
python -m unittest discover -v -p 'test_weed_*.py'
```

The 39-test adversarial suite covers legacy leakage, independent W0/W1,
pseudo-fixes coupled to P/T, unsafe guards, malformed and duplicate config,
missing runtime wiring, detached or mutated entrypoint config flow, fake JSON
loaders, content tampering, artifact-hash mismatch, forged receipts, revision
drift, and `R0P0O0` mislabeling.
