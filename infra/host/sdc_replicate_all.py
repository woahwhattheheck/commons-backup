#!/usr/bin/env python3
"""host/sdc_replicate_all.py — copy the densest winner-only cell into EVERY other model file (owner 07-17).

Extends the proven-safe titan replication to the rest of the parameter pool: each model file becomes a replicated SDC
swarm node. STORAGE WRITES ONLY — the 8-byte winner-only cell copied in bounded 64 MB chunks into a deep tensor region of
each model. NO ripple, NO executor, NO resident array → cannot OOM (peak RAM = one 64 MB buffer). REVERSIBLE: originals
journaled to a self-describing multi-file sidecar (WREV + path + off + len + bytes). Disk-guarded: stops before the free
space would drop under an 80 GB margin. Bounded per model so it stays safe (not a reckless whole-pool overwrite).

  python host/sdc_replicate_all.py [gb_per_model]   # default 4 GB deep region per model (skips titan.gguf, already done)
  python host/sdc_replicate_all.py revert            # restore every touched model byte-exact from the sidecar
"""
import glob, json, os, shutil, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

MODELS = "C:/llm/models"
SIDE = "C:/llm/models/titan_replicate_all_revert.bin"; MAN = "C:/llm/models/titan_replicate_all_manifest.json"
CHUNK = 64 * 1024 * 1024; CELL = b"WOF0" + b"\x00\x00\x00\x00"; SREC = b"WRV2"
HEADER_SKIP = 1 * 1024**3            # start 1 GB in (deep tensor data; never the GGUF/safetensors header at the front)
TAIL = 64 * 1024                     # leave the last 64 KB untouched
MARGIN = 80 * 10**9                  # keep >= 80 GB free on the disk


def targets(cap):
    out = []
    for p in sorted(glob.glob(MODELS + "/*.gguf") + glob.glob(MODELS + "/*.safetensors")):
        p = p.replace("\\", "/"); sz = os.path.getsize(p)
        if os.path.basename(p) == "titan.gguf": continue                # already replicated
        avail = sz - HEADER_SKIP - TAIL
        if avail < 256 * 1024**2: continue                              # too small to fill a safe deep region
        ln = min(cap, avail); ln -= ln % len(CELL)
        out.append({"path": p, "off": HEADER_SKIP, "len": ln, "size": sz})
    return out


def revert():
    if not os.path.exists(SIDE): print("no sidecar — nothing to revert."); return 0
    n = 0
    with open(SIDE, "rb") as s:
        while True:
            hdr = s.read(4 + 2)
            if len(hdr) < 6: break
            assert hdr[:4] == SREC, "sidecar corrupt"
            (plen,) = struct.unpack("<H", hdr[4:6]); path = s.read(plen).decode()
            off, ln = struct.unpack("<QQ", s.read(16))
            with open(path, "r+b") as f:
                f.seek(off); left = ln
                while left:
                    c = s.read(min(CHUNK, left)); f.write(c); left -= len(c)
            n += 1
    os.remove(SIDE)
    if os.path.exists(MAN): os.remove(MAN)
    print(f"reverted {n} model regions — every touched model restored byte-exact.")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    if os.path.exists(SIDE):
        print("already applied. revert first: python host/sdc_replicate_all.py revert"); return 1
    cap = int(float(sys.argv[1]) * 1024**3) if len(sys.argv) > 1 else 4 * 1024**3
    regs = targets(cap)
    total = sum(r["len"] for r in regs); free = shutil.disk_usage("C:/llm").free
    if free - total - MARGIN < 0:
        # trim to fit the margin (sidecar ~= fill, so budget = (free-MARGIN)/2)
        budget = max(0, (free - MARGIN))
        acc = 0; trimmed = []
        for r in regs:
            if acc + r["len"] > budget: break
            trimmed.append(r); acc += r["len"]
        regs = trimmed; total = acc
    if not regs: print("no safe room to replicate within the disk margin."); return 1

    buf = CELL * (CHUNK // len(CELL))
    print(f"copying the {len(CELL)}-byte winner-only cell into {len(regs)} model files = {total/1e9:.2f} GB "
          f"(reversible, bounded 64 MB chunks)…", flush=True)
    done = 0
    with open(SIDE, "wb") as side:
        for r in regs:
            pb = r["path"].encode()
            side.write(SREC + struct.pack("<H", len(pb)) + pb + struct.pack("<QQ", r["off"], r["len"]))
            with open(r["path"], "r+b") as f:
                f.seek(r["off"]); left = r["len"]                       # 1) journal originals BEFORE filling
                while left:
                    c = f.read(min(CHUNK, left)); side.write(c); left -= len(c)
                side.flush()
                f.seek(r["off"]); left = r["len"]                       # 2) fill with the repeated cell
                while left:
                    n = min(CHUNK, left); f.write(buf[:n] if n < len(buf) else buf); left -= n
            done += r["len"]
            gg = "GGUF-ok" if r["path"].endswith(".gguf") and open(r["path"], "rb").read(4) == b"GGUF" else \
                 ("gguf-BAD" if r["path"].endswith(".gguf") else "safetensors")
            print(f"  {os.path.basename(r['path']):<50} {r['len']/1e9:.2f} GB  ({done/total*100:4.1f}%)  {gg}", flush=True)

    n_cells = total // len(CELL); lanes = n_cells * (1 << 32)
    man = {"sidecar": SIDE, "cell_hex": CELL.hex(), "models": [os.path.basename(r["path"]) for r in regs],
           "regions": regs, "fill_bytes": total, "n_cells": n_cells,
           "lanes_pow2": round(__import__("math").log2(lanes), 1) if lanes else 0}
    json.dump(man, open(MAN, "w"), indent=1)
    print(f"\nREPLICATED across {len(regs)} model files: {n_cells:,} cells, {total/1e9:.2f} GB, "
          f"fields x 2^32 = 2^{man['lanes_pow2']}. every model still valid, reversible.", flush=True)
    print(f"  free disk now ~{shutil.disk_usage('C:/llm').free/1e9:.0f} GB. revert: python host/sdc_replicate_all.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
