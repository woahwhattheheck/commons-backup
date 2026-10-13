#!/usr/bin/env python3
"""host/fable_findcircuits.py — FIND BAKED Muhlnickel CIRCUITS HIDING IN A MODEL'S WEIGHTS (fable, 2026-07-22).

A baked circuit carries an 8-byte magic (PFCTYPED / PFCGAME1 / PFCSCLK1 / PFCRAY01 / …) that quantized float weights
physically never produce. One streamed pass over the file's bytes finds every one — no registry, no genome needed
(works even when the bake was never journaled, which is the whole point here). Maps each hit to the tensor it's hiding
inside via the .wbindex.json when available. Read-only.

  python host/fable_findcircuits.py model.gguf [model2.gguf ...]
"""
import json, mmap, os, sys
sys.stdout.reconfigure(encoding="utf-8")

MAGICS = {b"PFCAPP01", b"PFCEXEC1", b"PFCGAME1", b"PFCMBUS1", b"PFCMMU01", b"PFCONE01", b"PFCOPR01", b"PFCPHYS1",
          b"PFCPIPE1", b"PFCPROV1", b"PFCRAY01", b"PFCSCLK1", b"PFCSMACH", b"PFCSMCLK", b"PFCSUBS1", b"PFCTET01",
          b"PFCTUN01", b"PFCTYPED", b"PFCWINMN"}


def _tensors(path):
    p = path + ".wbindex.json"
    if not os.path.exists(p): return None
    try:
        j = json.load(open(p))
        ts = j.get("tensors") if isinstance(j, dict) else j
        out = []
        for t in ts:
            o = t.get("offset", t.get("off"))
            if o is not None: out.append((int(o), t.get("name", "?")))
        return sorted(out)
    except Exception:
        return None


def _tname(ts, off):
    if not ts: return ""
    lo, name = "", ""
    for o, n in ts:
        if o <= off: name = n
        else: break
    return f" in {name}" if name else ""


def scan(path):
    sz = os.path.getsize(path)
    f = open(path, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    found, pos = {}, 0
    while True:
        i = mm.find(b"PFC", pos)
        if i < 0: break
        tag = bytes(mm[i:i + 8])
        if tag in MAGICS:
            d = found.setdefault(tag.decode(), [0, []])
            d[0] += 1
            if len(d[1]) < 3: d[1].append(i)
        pos = i + 1
    mm.close(); f.close()
    return sz, found


def main():
    paths = sys.argv[1:] or ["C:/llm/models/titan.gguf"]
    for path in paths:
        if not os.path.exists(path):
            alt = os.path.join(os.path.dirname(path), "_removed", os.path.basename(path))
            path = alt if os.path.exists(alt) else path
        name = os.path.basename(path)
        if not os.path.exists(path):
            print(f"\n=== {name}: NOT FOUND ==="); continue
        sz, found = scan(path)
        ts = _tensors(path)
        print(f"\n=== {name}  ({sz/1e9:.1f} GB) ===", flush=True)
        if not found:
            print("  ✓ clean — no baked circuits.", flush=True)
            continue
        tot = sum(v[0] for v in found.values())
        print(f"  ◆ BAKED CIRCUITS: {tot} hits, {len(found)} distinct signature(s)", flush=True)
        for tag, (c, offs) in sorted(found.items(), key=lambda x: -x[1][0]):
            print(f"    {tag} x{c:<4} first @ {offs[0]:,}{_tname(ts, offs[0])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
