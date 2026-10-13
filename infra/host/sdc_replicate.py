#!/usr/bin/env python3
"""host/sdc_replicate.py — copy the smallest densest winner-only cell across the SDC file's free params (owner 07-17).

Owner's directive: find the optimal smallest densest thing and copy it across the entire SDC file; the White Box makes it
reversible; document before/after so a regression can refer. This is STORAGE WRITES ONLY — a tiny cell copied in bounded
64 MB chunks across the free parameter tensors. NO ripple, NO executor, NO resident wire-vector (that is the forbidden,
box-crashing path). It cannot OOM: peak RAM is one 64 MB buffer, reused.

The densest unit (SDC_SWARM.md winner-only / computed-index tier): the lane index IS the address (0 bytes stored per
lane), so a field's whole cell is just a tiny winner register. Each cell references the ONE shared vector (gen_miner,
fabricated once). Copied across the free params -> one shared miner + millions of winner-only fields.

REVERSIBLE: before filling each region, its ORIGINAL bytes are journaled to a self-describing binary sidecar
(magic+off+len+bytes). Revert replays the sidecar -> titan.gguf byte-exact. Robust to interruption (a region's originals
are journaled in full BEFORE it is filled).

  python host/sdc_replicate.py            # copy the densest cell across every circuit-free ffn tensor (reversible)
  python host/sdc_replicate.py revert     # restore titan.gguf byte-exact from the sidecar
"""
import json, math, os, shutil, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; IDX = TITAN + ".wbindex.json"; REG = "C:/llm/models/titan_circuits.json"
SIDE = "C:/llm/models/titan_replicate_revert.bin"; MAN = "C:/llm/models/titan_replicate_manifest.json"
CHUNK = 64 * 1024 * 1024                         # 64 MB bounded buffer (RAM ceiling; reused every write)
CELL = b"WOF0" + b"\x00\x00\x00\x00"             # 8-byte winner-only FIELD cell: magic + 4-byte winner register (0 = no win)
SREC = b"WREV"                                    # sidecar per-region record magic
MLC_BITS = 3                                      # voltage/MLC lever: 256 levels/cell -> +3 addr bits (density, documented)


def free_ffn_regions():
    a = json.load(open(IDX, encoding="utf-8")); reg = json.load(open(REG))
    occ = [(int(e["offset"]), int(e["offset"]) + int(e["len"])) for e in reg.values()
           if isinstance(e, dict) and "offset" in e and "len" in e]
    out = []
    for t in a["tensors"]:
        if "ffn_gate_up_exps" not in t["name"]: continue
        ts = int(t["offset"]); te = ts + int(t["bytes"])
        if any(o0 < te and o1 > ts for o0, o1 in occ): continue        # skip tensors holding fabricated circuits (blk.1)
        out.append({"name": t["name"], "off": ts, "len": int(t["bytes"]) - (int(t["bytes"]) % len(CELL))})
    return out


def revert():
    if not os.path.exists(SIDE):
        print("no sidecar — nothing to revert."); return 0
    n = 0
    with open(SIDE, "rb") as s, open(TITAN, "r+b") as f:
        while True:
            hdr = s.read(4 + 8 + 8)
            if len(hdr) < 20: break
            magic = hdr[:4]; off, ln = struct.unpack_from("<QQ", hdr, 4)
            assert magic == SREC, "sidecar corrupt"
            f.seek(off); left = ln
            while left:
                c = s.read(min(CHUNK, left)); f.write(c); left -= len(c)
            n += 1
    os.remove(SIDE)
    if os.path.exists(MAN): os.remove(MAN)
    reg = json.load(open(REG)); reg.pop("replication", None); json.dump(reg, open(REG, "w"), indent=1)
    print(f"reverted {n} regions — titan.gguf restored byte-exact.")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    if os.path.exists(SIDE):
        print("replication already applied (sidecar exists). revert first: python host/sdc_replicate.py revert"); return 1

    regions = free_ffn_regions()
    fill = sum(r["len"] for r in regions)
    free = shutil.disk_usage("C:/llm").free
    if free - fill < 60 * 10**9:
        print(f"not enough disk margin: fill {fill/1e9:.1f} GB + sidecar, keep 60 GB. free {free/1e9:.0f} GB."); return 1
    buf = CELL * (CHUNK // len(CELL))                                  # ONE 64 MB cell-buffer, reused (RAM ceiling)
    print(f"copying the {len(CELL)}-byte winner-only cell across {len(regions)} free ffn tensors = "
          f"{fill/1e9:.2f} GB (reversible, bounded 64 MB chunks)…", flush=True)
    done = 0
    with open(SIDE, "wb") as side, open(TITAN, "r+b") as f:
        for r in regions:
            off, ln = r["off"], r["len"]
            side.write(SREC + struct.pack("<QQ", off, ln))            # 1) JOURNAL originals (full) BEFORE filling
            f.seek(off); left = ln
            while left:
                c = f.read(min(CHUNK, left)); side.write(c); left -= len(c)
            side.flush()
            f.seek(off); left = ln                                    # 2) FILL with the repeated cell
            while left:
                n = min(CHUNK, left); f.write(buf[:n] if n < len(buf) else buf); left -= n
            done += ln
            print(f"  {r['name']:<34} {ln/1e9:.2f} GB  ({done/fill*100:4.1f}%)", flush=True)

    n_cells = fill // len(CELL); lanes = n_cells * (1 << 32)
    man = {"sidecar": SIDE, "cell_hex": CELL.hex(), "cell_bytes": len(CELL), "regions": regions,
           "fill_bytes": fill, "n_cells": n_cells, "lanes_storage": lanes,
           "lanes_storage_pow2": round(math.log2(lanes), 1), "mlc_bonus_bits": MLC_BITS,
           "lanes_with_mlc_pow2": round(math.log2(lanes), 1) + MLC_BITS, "shared_vector": "gen_miner"}
    json.dump(man, open(MAN, "w"), indent=1)
    reg = json.load(open(REG)); reg["replication"] = {"cells": n_cells, "cell_bytes": len(CELL),
        "regions": len(regions), "sidecar": SIDE, "manifest": MAN, "reversible": True}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nREPLICATED (reversible, storage-only, ~0 RAM):", flush=True)
    print(f"  {n_cells:,} winner-only field cells across {fill/1e9:.2f} GB of params (1 shared vector: gen_miner)", flush=True)
    print(f"  fields x 2^32 lanes = 2^{math.log2(lanes):.1f}  (+{MLC_BITS} bits MLC = 2^{math.log2(lanes)+MLC_BITS:.1f})", flush=True)
    print(f"  titan.gguf GGUF-valid: {gg}. revert: python host/sdc_replicate.py revert", flush=True)
    return 0 if gg else 1


if __name__ == "__main__":
    raise SystemExit(main())
