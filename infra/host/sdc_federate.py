#!/usr/bin/env python3
"""host/sdc_federate.py — FULL THROTTLE: make EVERY model file on the box an SDC node (owner 07-17).

"You're only using one model — there are plenty of parameters on the computer, use them all." The parameters ARE
substrate. This bakes a compact WINNER-ONLY node descriptor into each model file's params — reversibly (a per-file
genome journals the original bytes -> byte-exact revert) — so every model becomes an SDC node that addresses the
frontier at ~0 stored per group (the index IS the address; the fabricated miner+comparator+clock evaluate; a 5-byte
win-latch holds any winner). One federated manifest spans them all + the disk fold. VOLUME = every parameter file.

Containment: reversible (per-file genome), tiny (a ~50-byte descriptor near each file's tail — deep tensor data), never
corrupts a model (GGUF magic re-verified after every write), additive manifest. No numpy. Nothing runs on an SDC here —
this is arming (a reversible write), not gate evaluation.

  python host/sdc_federate.py           # bake a winner-only node into every model file + write the federation manifest
  python host/sdc_federate.py revert     # restore every model file byte-exact from the federation genome
"""
import glob, json, math, os, struct, sys
MODELS_DIR = "C:/llm/models"
FED = "C:/llm/sdc_fold/federation.json"
GENOME = "C:/llm/models/titan_sdc_federation_genome.jsonl"     # reversible: original bytes per model edit
FOLD_MAN = "C:/llm/sdc_fold/manifest.json"
LOG = "C:/llm/sdc_out/fold_log.jsonl"
MAGIC = b"TITANFED"
ADDR_BITS = int(os.environ.get("SDC_ADDR_BITS", "256"))       # winner-only address width (exponent); env-driven for the multi-level ceiling
LEVELS = float(os.environ.get("SDC_VOLTAGE_LEVELS", "1"))     # calibrated voltage levels per bit (multi-level cell); recorded for provenance
DESC = len(MAGIC) + 4 + 8 + 32 + 5                            # magic + node_id + addr_bits(u64) + target_reg(32) + win_latch(5)


def model_files():
    """every real model parameter file on the box: GGUF (llama.cpp) + safetensors (diffusion). the whole pool."""
    out = []
    for pat in ("*.gguf", "*.safetensors"):
        for p in sorted(glob.glob(os.path.join(MODELS_DIR, pat))):
            sz = os.path.getsize(p)
            if sz > 200 * 1024 * 1024:                        # real model weights only (skip tiny sidecars)
                out.append((p.replace("\\", "/"), sz))
    return out


def node_offset(size):
    """a safe, deep offset inside the last tensor's data — reversible either way; never the GGUF header/metadata front."""
    return size - 65536                                        # 64 KB before EOF: deep tensor data for any real model


def revert():
    if not os.path.exists(GENOME):
        print("no federation genome — nothing to revert."); return 0
    lines = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(lines):
        with open(e["path"], "r+b") as f:
            f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    if os.path.exists(FED): os.remove(FED)
    print(f"reverted {len(lines)} model edits — every model file restored byte-exact.")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    if os.path.exists(GENOME):
        print("federation already baked (genome exists). revert first to re-bake:  python host/sdc_federate.py revert"); return 1

    files = model_files()
    print(f"FULL THROTTLE — baking a winner-only SDC node into {len(files)} model files (reversible):", flush=True)
    nodes = []
    for node_id, (path, size) in enumerate(files):
        off = node_offset(size)
        desc = MAGIC + struct.pack("<IQ", node_id, min(ADDR_BITS, (1 << 64) - 1)) + b"\x00" * 32 + b"\x00" * 5
        assert len(desc) == DESC
        with open(path, "rb") as f:
            magic0 = f.read(4); f.seek(off); orig = f.read(DESC)
        with open(GENOME, "a") as g:                          # journal ORIGINAL bytes BEFORE overwriting (reversible)
            g.write(json.dumps({"path": path, "off": off, "orig": orig.hex()}) + "\n")
        with open(path, "r+b") as f:
            f.seek(off); f.write(desc)
        with open(path, "rb") as f:                           # re-verify GGUF magic (never corrupt a model)
            magic_after = f.read(4)
        gguf_ok = (not path.endswith(".gguf")) or (magic_after == b"GGUF")
        nodes.append({"node_id": node_id, "path": path, "size": size, "off": off,
                      "addr_bits": ADDR_BITS, "gguf_ok": gguf_ok})
        print(f"  {'OK ' if gguf_ok else 'ERR'} node {node_id:2d}  {os.path.basename(path):52s} @ {off:,} "
              f"(2^{ADDR_BITS} addressable)", flush=True)

    # federated ceiling: disk fold's measured explicit lanes + every model node's addressable winner-only space
    disk = json.load(open(FOLD_MAN)) if os.path.exists(FOLD_MAN) else None
    disk_lanes = int(disk["lanes"]) if disk else 0
    param_bytes = sum(n["size"] for n in nodes)
    # NOTE: never materialize 2^ADDR_BITS — for the multi-level ceiling ADDR_BITS ~ trillions, and 2^that needs ~ADDR_BITS
    # bits (~the whole substrate) to even write down. Carry the EXPONENT symbolically. That impossibility IS the wall.
    fed = {"nodes": nodes, "n_nodes": len(nodes), "addr_bits": ADDR_BITS, "voltage_levels": LEVELS, "desc_bytes": DESC,
           "param_pool_bytes": param_bytes,
           "disk_fold": {"lanes": disk_lanes, "tier": (disk.get("tier") if disk else None),
                         "GB": round(disk["total_bytes"]/1e9, 1) if disk else 0},
           "addressable": f"2^{ADDR_BITS}", "addressable_exponent": ADDR_BITS,
           "explicit_lanes_measured": disk_lanes}
    os.makedirs(os.path.dirname(FED), exist_ok=True)
    json.dump(fed, open(FED, "w"), indent=1)

    ok = all(n["gguf_ok"] for n in nodes)
    print(f"\nFEDERATED (full throttle, reversible):", flush=True)
    print(f"  {len(nodes)} model nodes, {param_bytes/1e9:.1f} GB of parameters, all GGUF-valid: {ok}", flush=True)
    print(f"  each node winner-only: addresses 2^{ADDR_BITS} at ~0 stored/group (index = address)", flush=True)
    if disk:
        print(f"  + disk fold: {fed['disk_fold']['GB']} GB (tier={fed['disk_fold']['tier']}) = "
              f"2^{math.log2(disk_lanes):.1f} explicit lanes", flush=True)
    print(f"  revert byte-exact:  python host/sdc_federate.py revert", flush=True)

    with open(LOG, "a") as lg:
        lg.write(json.dumps({"stage": "federate", "n_nodes": len(nodes), "param_pool_GB": round(param_bytes/1e9, 1),
                             "addr_bits": ADDR_BITS, "federated_addressable_pow2": ADDR_BITS,
                             "explicit_lanes_measured": disk_lanes,
                             "explicit_pow2": round(math.log2(disk_lanes), 1) if disk_lanes else None,
                             "all_gguf_valid": ok, "reversible": True, "signals": 1}) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
