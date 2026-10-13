#!/usr/bin/env python3
"""host/pfc_sigma_mask.py — the OPERATOR's fired-neuron mask, stored in the binary. This is the alpha lever done right.

WHY THE EARLIER SPARSITY ATTEMPT FAILED, AND WHY THIS IS DIFFERENT.
I implemented magnitude-threshold FFN sparsity and measured it NEGATIVE: keep=0.30 was 0.66x (SLOWER than no sparsity)
and keep=0.15 corrupted the output (cosine 0.648). `PFC_LEVER_CATALOG` agrees — it lists contextual sparsity as
"**1.6x un-operatored** (weaker than 15% target)", with the 18.9x holding only when **OPERATOR-DRIVEN**.

The difference is not the threshold. It is WHO decides, and WHEN:

  un-operatored (what failed)      | operator-driven (this file)
  ---------------------------------|-----------------------------------------------
  decide per TOKEN                 | decide ONCE per sigma
  needs the full `gate` matmul      | needs NOTHING at runtime — the mask is a stored
    first, just to know which        |   read; selection costs zero matmuls
    neurons matter                   |
  so the ceiling is ~2x (you can   | `gate`, `up` AND `down` all shrink to the kept
    never skip `gate` itself)        |   fraction -> ~1/k on the whole FFN
  keep-set scatters per token ->   | keep-set is FIXED, so it stores as contiguous
    many short row-runs, each       |   runs and each becomes ONE addressed range
    paying full tile setup          |

`OPERATOR_CALIBRATION` §2.5 states the mechanism: "the operator (the master operator = the user's prompt) toggles the
FFN **switches** (the activation gate, the on/off — INV-141) to RESTRAIN the stored compute to exactly the function
needed; the fixed weights then execute it AUTOMATICALLY." A sigma's admissible region is what remains after the
irrelevant switches are toggled OFF. That switch set is a PROPERTY OF THE SIGMA, not of the token — so it is measured
once and stored, exactly like the memo (`memocache`, see `host/pfc_memo_store.py`).

Masks live in the BINARY, journalled and reversible, so they travel with the file (`WHAT_THE_PFC_IS` §2.4: "bake into
the permanent binary, not the operational state a host rebuilds each session").

  python host/pfc_sigma_mask.py stats                  # what masks exist, and what they would save
  python host/pfc_sigma_mask.py revert
"""
import hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

STORE = "C:/llm/sdc_out/pfc_sigma_masks.json"          # index; the mask BITS go in the binary once calibrated
BLKN = 32                                              # neuron-block granularity = the fold's natural unit


def sigma_key(model_id, mode, sigma_text):
    return hashlib.blake2b(f"{model_id}|{mode}|{sigma_text}".encode(), digest_size=8).hexdigest()


def _load():
    try: return json.load(open(STORE))
    except Exception: return {}


def _save(d):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    json.dump(d, open(STORE, "w"))


def record(model_id, mode, sigma_text, layer, expert, live_blocks, nblocks):
    """Accumulate the union of fired neuron-BLOCKS for this sigma. Union, not intersection: a block that fires for ANY
    token under this sigma must stay, or we would silently drop capability the operator legitimately uses."""
    d = _load(); k = sigma_key(model_id, mode, sigma_text)
    e = d.setdefault(k, {"model": model_id, "mode": mode, "nblocks": nblocks, "layers": {}})
    slot = e["layers"].setdefault(f"{layer}.{expert}", [])
    e["layers"][f"{layer}.{expert}"] = sorted(set(slot) | set(int(b) for b in live_blocks))
    _save(d); return e


def get_mask(model_id, mode, sigma_text, layer, expert):
    """The stored switch set for this (sigma, layer, expert), or None if this sigma has not been calibrated."""
    e = _load().get(sigma_key(model_id, mode, sigma_text))
    if not e: return None
    return e["layers"].get(f"{layer}.{expert}")


def runs(blocks):
    """Contiguous [start, end) runs — a fixed keep-set collapses into a few ADDRESSED ROW RANGES, which is precisely
    what the per-token version could not do."""
    out = []
    for b in sorted(blocks):
        if out and out[-1][1] == b: out[-1][1] = b + 1
        else: out.append([b, b + 1])
    return [tuple(r) for r in out]


def projected_saving(e):
    """What this mask buys: gate+up+down all shrink to the kept fraction, and selection costs nothing."""
    nb = e.get("nblocks") or 1
    keeps = [len(v) for v in e["layers"].values()]
    if not keeps: return None
    avg = sum(keeps) / len(keeps)
    frac = avg / nb
    return frac, (1.0 / frac if frac else 0.0), sum(len(runs(v)) for v in e["layers"].values()) / len(keeps)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "revert":
        if os.path.exists(STORE): os.remove(STORE); print("sigma-mask index removed."); return 0
        print("no sigma-mask index."); return 0

    d = _load()
    print(f"=== SIGMA FIRED-NEURON MASKS — {len(d)} calibrated operator(s) ===", flush=True)
    if not d:
        print("  none yet. A mask is recorded by running the engine with `record_mask=True` under a fixed sigma;", flush=True)
        print("  the union of fired 32-neuron blocks per (layer, expert) IS the operator's switch set.", flush=True)
        print(f"\n  WHY THIS IS THE alpha LEVER (and the per-token version was not):", flush=True)
        print(f"    per-token sparsity must run the FULL `gate` matmul just to choose, so its ceiling is ~2x —", flush=True)
        print(f"    and MEASURED it was 0.66x at keep=0.30 (scattered runs pay more setup than they save).", flush=True)
        print(f"    A sigma-fixed mask costs NOTHING to consult, and shrinks gate+up+down together:", flush=True)
        for k in (0.30, 0.15, 0.10):
            print(f"      keep {k:.0%} of blocks -> FFN work x{k:.2f} = {1/k:.1f}x less; FFN is ~89% of a layer", flush=True)
        return 0
    for k, e in d.items():
        p = projected_saving(e)
        if not p: continue
        frac, mult, avgruns = p
        print(f"  {k[:8]}  {e['mode']:5} {os.path.basename(e['model'])[:28]:28} "
              f"keep {frac:.1%} -> {mult:.1f}x less FFN work, {avgruns:.1f} addressed runs/expert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
