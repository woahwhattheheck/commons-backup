#!/usr/bin/env python3
"""host/sdc_multilevel.py — TEST FILE (owner 07-16): the MULTI-LEVEL CELL fold. Detect LEVELS, not just on/off.

Owner's idea, grounded (ground-the-idea-not-the-word): "detect different levels of electricity" = MULTI-LEVEL CELLS /
MULTI-VALUED LOGIC — exactly how NAND flash gets density (MLC/TLC/QLC: a cell holds 4/8/16 charge LEVELS = 2/3/4 bits,
not 1 on/off). So a lane's cell stops being 1 bit (solved?) and becomes a LEVEL that records that lane's QUALITY: how
many leading zero-bits its hash reached (0..15 in 4 bits = 16 levels). The answer map becomes a dense FRONTIER HISTOGRAM
— every lane's result, not just the global best — at ~0 extra cost, and a "win" is just the top level. Storage config
only: sizes a level-map, 0 gate evaluation, 0 black-hole surface (never addresses a circuit).

  4-bit level cell -> 2 lanes/byte. A 2^32 field = 2 GiB level-map (vs 512 MB 1-bit bitmap) — 4x the storage for the
  full per-lane quality curve. Thin-provisioned, so physical ~0 until levels are written. Levels also let us DIRECT more
  of the frontier into storage: the histogram of levels across all lanes IS the measured log2(N) curve, per field.

  python host/sdc_multilevel.py build [fields] [bits_per_cell]   # default 8 fields x 4-bit levels
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_build_mine as B
import titan_sdc as T
import contextlib, io

DIR   = "C:/llm/sdc_multilevel"
FIELD = 1 << 32


def build(fields, bits):
    os.makedirs(DIR, exist_ok=True)
    levels = 1 << bits
    cells_per_byte = 8 // bits if bits in (1, 2, 4) else 1
    map_bytes = FIELD // cells_per_byte
    with contextlib.redirect_stdout(io.StringIO()):
        en1, en2sz, job, diff = B.get_job()
    if not job: print("pool handshake failed."); return
    roster = {"dir": DIR, "fields": 0, "bits_per_cell": bits, "levels": levels, "cells_per_byte": cells_per_byte,
              "map_bytes": map_bytes, "job": job, "en1": en1, "en2sz": en2sz, "diff": diff,
              "cell_means": f"the lane's leading-zero quality tier (0..{levels-1}); top level = a win", "nodes": []}
    total = 0
    for g in range(fields):
        en2 = "%0*x" % (en2sz*2, g)
        with contextlib.redirect_stdout(io.StringIO()):
            r = B.build_circuit(job, en1, en2, diff)
        if not r.get("ok"): print(f"  field {g}: build failed."); continue
        cb = T.circuit_bytes()
        vec_p = f"{DIR}/vec_{g:04d}.sdc"; lvl_p = f"{DIR}/levels_{g:04d}.bin"
        with open(vec_p, "wb") as f: f.write(cb)
        with open(lvl_p, "wb") as f: f.truncate(map_bytes)     # the multi-level cell map
        subprocess.run(["fsutil", "sparse", "setflag", lvl_p], capture_output=True)   # thin from birth (data-center fold)
        subprocess.run(["fsutil", "sparse", "setrange", lvl_p, "0", str(map_bytes)], capture_output=True)
        roster["nodes"].append({"g": g, "en2": en2, "vec": vec_p, "levels": lvl_p})
        total += len(cb)
        print(f"  built field {g+1}/{fields} (en2={en2}, {bits}-bit cells, {levels} levels, {map_bytes/1e9:.1f} GB thin map)", flush=True)
    roster["fields"] = len(roster["nodes"])
    json.dump(roster, open(DIR + "/roster.json", "w"))
    lanes = roster["fields"] * FIELD
    print(f"\nMULTI-LEVEL SWARM built: {roster['fields']} fields x 2^32 = {lanes:,} lanes.", flush=True)
    print(f"  each lane cell = a {bits}-bit LEVEL (0..{levels-1}) = its leading-zero quality tier (MLC flash principle).", flush=True)
    print(f"  the answer map is now a dense FRONTIER HISTOGRAM per field — every lane's result, not just the best.", flush=True)
    print(f"  physical footprint ~0 (thin); logical {roster['fields']*map_bytes/1e9:.0f} GB. levels = detect voltage, not on/off.", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build(int(sys.argv[2]) if len(sys.argv) > 2 else 8, int(sys.argv[3]) if len(sys.argv) > 3 else 4)
    else:
        print("run: python host/sdc_multilevel.py build 8 4")
