#!/usr/bin/env python3
"""host/wf_titancir_cells.py — reshape TITANCIR records into their cell-matrix and reconstruct the tiled structure.
Read-only, bounded (a few KB per record). Reveals the bit-slice/datapath regularity: which columns are per-cell
counters (+1), which are node references marching one cell's worth per row (+stride), which are constant.

  python host/wf_titancir_cells.py [record_index]   # default: analyze a few records + summarize tiling
"""
import os, sys, struct
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

TITAN = "C:/llm/models/titan.gguf"
MAGIC = b"TITANCIR"


def find_records(mm, base, end, limit=200):
    offs = []; p = base
    while len(offs) < limit:
        i = mm.find(MAGIC, p, end)
        if i < 0: break
        offs.append(i); p = i + 8
    return offs


def body_of(mm, o, maxu=512, bound=4096):
    hdr = struct.unpack_from("<6I", mm, o + 8)
    W = struct.unpack_from("<%dI" % maxu, mm, o + 8 + 24)
    run = []
    for w in W:
        if w < bound: run.append(w)
        else: break
    return hdr, run


def col_kind(vals):
    d = [vals[i+1]-vals[i] for i in range(len(vals)-1)]
    if not d: return "single", 0
    if all(x == d[0] for x in d):
        return ("const" if d[0] == 0 else f"+{d[0]}" if d[0] > 0 else str(d[0])), d[0]
    cnt = Counter(d)
    common, freq = cnt.most_common(1)[0]
    if freq >= 0.7 * len(d):
        return f"~+{common}", common
    return "irregular", None


def analyze(mm, o, label):
    hdr, body = body_of(mm, o)
    W = 15
    nc = len(body) // W
    M = [body[i*W:(i+1)*W] for i in range(nc)]
    print(f"\n{label}: header {hdr}  body {len(body)} u32  -> {nc} cells x {W}")
    if nc < 2:
        print("  (too few cells to see tiling)"); return hdr, M
    print("  per-column pattern across cells:")
    kinds = []
    for c in range(W):
        col = [row[c] for row in M]
        k, step = col_kind(col)
        kinds.append((k, step))
        print(f"    col{c:>2}: {str(col[:6]):32s} kind={k}")
    stride_cols = [c for c,(k,s) in enumerate(kinds) if s not in (None,0,1) and str(k).startswith('+')]
    counter_cols = [c for c,(k,s) in enumerate(kinds) if s == 1]
    const_cols = [c for c,(k,s) in enumerate(kinds) if k == 'const']
    strides = Counter(kinds[c][1] for c in stride_cols)
    print(f"  => counter cols(+1): {counter_cols} | ref cols(marching): {stride_cols} "
          f"(dominant stride {strides.most_common(1)[0][0] if strides else '-'}) | const cols: {const_cols}")
    print(f"  => reads as a TILED circuit: {nc} slices, references march +{strides.most_common(1)[0][0] if strides else '?'} per slice")
    return hdr, M


def main():
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else None
    g = GGUF(TITAN); mm = g.mm
    t = g.tensors["blk.1.ffn_gate_up_exps.weight"]
    ne0, ne1, nexp = t["dims"]; bpb, wpb = _QT[t["type"]]
    base = g.data0 + t["off"]; eb = ne1 * (ne0 // wpb * bpb)
    end = base + (ne0*ne1*nexp)//wpb*bpb
    offs = find_records(mm, base, end)
    print(f"{len(offs)} TITANCIR records in blk.1")

    if idx is not None:
        analyze(mm, offs[idx], f"record #{idx}")
        return

    # header signature clustering across ALL records (distinct designs)
    sigs = Counter()
    for o in offs:
        h = struct.unpack_from("<6I", mm, o + 8); sigs[h] += 1
    print(f"\ndistinct header signatures = distinct designs: {len(sigs)}")
    for sig, cnt in sigs.most_common():
        exp = None
        for o in offs:
            if struct.unpack_from("<6I", mm, o + 8) == sig:
                exp = (o - base)//eb; break
        print(f"  {sig} -> {cnt:>3} records  (e.g. expert {exp})")

    # analyze one representative of each of the first few designs
    seen = set()
    for o in offs:
        h = struct.unpack_from("<6I", mm, o + 8)
        if h in seen: continue
        seen.add(h)
        analyze(mm, o, f"design {h[:3]} @ expert {(o-base)//eb}")
        if len(seen) >= 4: break


if __name__ == "__main__":
    raise SystemExit(main())
