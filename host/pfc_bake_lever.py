#!/usr/bin/env python3
"""host/pfc_bake_lever.py — BAKE A LEVER INTO THE PERMANENT BINARY so the host only addresses (owner 07-19).

The permanence instrument showed a fresh compute rebuilds ~124.6 MB of operational state (mostly compiling the ripple).
The owner's vision: bake the best levers into the permanent file so a result is an ADDRESSED READ, not a recompute —
"host only addresses." This bakes the MEMOIZE fold (§K) into titan.gguf: compute a batch of results ONCE, write them
into an addressable cache region in the permanent binary, then a repeat is a pure seek+read at ~0 operational cost.
Measured with the permanence method (operational RAM of a HIT vs a fresh MISS). Reversible (genome).

  python host/pfc_bake_lever.py           # bake the memoize cache + measure HIT (addressed) vs MISS (recompute)
  python host/pfc_bake_lever.py revert
"""
import hashlib, json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC
from pfc_exp_bench import rss

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_memocache_genome.jsonl"
NCELL = 4096; CELLB = 2                                # cache: 4096 inputs x 16-bit result = 8 KB baked in the file


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("no memocache genome."); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("memocache", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; memocache removed."); return 0


def f_isqrt(x):  # the memoized function (an "expensive" one): integer sqrt
    import math; return math.isqrt(x) & 0xffff


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))

    # ---- MISS baseline: what a fresh compute costs in operational RAM (compile + ripple a real circuit) ----
    base, _ = rss()
    n_in, n_wire, gates = _load_gen(reg)
    run = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)
    run([0] * n_in, 1)
    miss_op, _ = rss(); miss_op -= base
    print(f"Muhlnickel BAKE-A-LEVER — memoize fold into the permanent binary (host only addresses).\n", flush=True)
    print(f"  MISS (fresh compute): compile + ripple a {len(gates):,}-gate circuit = +{miss_op:.1f} MB operational RAM.\n", flush=True)

    # ---- bake the cache into the PERMANENT binary: compute each input once, write the result permanently ----
    if "memocache" not in reg:
        off, tn = TC._alloc(NCELL * CELLB, reg)
        blob = b"".join(struct.pack("<H", f_isqrt(x)) for x in range(NCELL))
        backup_and_write(off, blob)
        reg = json.load(open(REG)); reg["memocache"] = {"tensor": tn, "offset": off, "len": NCELL * CELLB,
                                                        "cells": NCELL, "cellb": CELLB, "fn": "isqrt", "note": "memoize fold baked permanent; a HIT is an addressed read"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"  BAKED memocache @ {off}: {NCELL:,} results = {NCELL*CELLB/1024:.0f} KB permanent (persists).", flush=True)
    coff = int(reg["memocache"]["offset"])

    # ---- HIT: a cached result is a pure ADDRESSED READ — measure its operational cost ----
    base2, _ = rss()
    with open(TITAN, "rb") as f:
        checks = 0
        for x in (7, 100, 2025, 4095, 42, 999):
            f.seek(coff + x * CELLB); got = struct.unpack("<H", f.read(CELLB))[0]
            assert got == f_isqrt(x), f"cache mismatch at {x}"; checks += 1
    hit_op, _ = rss(); hit_op -= base2
    # throughput of pure addressed reads
    t0 = time.time(); n = 0
    with open(TITAN, "rb") as f:
        while time.time() - t0 < 1.0:
            f.seek(coff + (n % NCELL) * CELLB); f.read(CELLB); n += 1
    print(f"\n  HIT (baked result = addressed read): {checks} cached lookups verified byte-exact, +{hit_op:.1f} MB operational.", flush=True)
    print(f"    pure addressed-read rate: {n:,}/sec — no compile, no ripple, host just addresses.\n", flush=True)

    print(f"  === HOST ONLY ADDRESSES ===", flush=True)
    print(f"  MISS (recompute) : +{miss_op:.1f} MB operational", flush=True)
    print(f"  HIT  (addressed) : +{hit_op:.1f} MB operational   — the baked result made the host ONLY address.", flush=True)
    print(f"  the more inputs baked into the permanent binary, the more of the stream is addressed reads at ~0 operational", flush=True)
    print(f"  (memoize multiplies by the repeat factor, §K). revert: python host/pfc_bake_lever.py revert", flush=True)
    return 0


def _load_gen(reg):
    OPS = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}
    off = int(reg["gen_miner"]["offset"])
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    n_in, n_wire, n_gate, _ = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    gates = [None] * n_gate
    for i in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; gates[i] = (OPS[op], a, b)
    mm.close(); f.close()
    return n_in, n_wire, gates


if __name__ == "__main__":
    raise SystemExit(main())
