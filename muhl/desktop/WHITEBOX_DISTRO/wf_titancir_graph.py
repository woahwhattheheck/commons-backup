#!/usr/bin/env python3
"""host/wf_titancir_graph.py — reconstruct a TITANCIR record into an actual gate GRAPH and characterize it:
is it a valid DAG? what is its critical-path DEPTH (= compute latency in gate-delays)? is it TILED (bit-sliced)?
Read-only, bounded reads on titan. Tries several body encodings and reports the one that yields a clean DAG.

  python host/wf_titancir_graph.py [expert] [nth_record_in_expert]
"""
import os, sys, struct
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import wb_config as _cfg                                       # PORTABILITY (distro)

TITAN = _cfg.titan_model()
MAGIC = b"TITANCIR"


def records(mm, base, end):
    offs = []; p = base
    while True:
        i = mm.find(MAGIC, p, end)
        if i < 0: break
        offs.append(i); p = i + 8
    return offs


def read_body(mm, o, want, bound):
    """read up to `want` u32 after the header, keeping the leading run of in-range (< bound) values."""
    raw = struct.unpack_from("<%dI" % min(want + 40, 60000), mm, o + 8 + 24)
    run = []
    for w in raw:
        if w < bound: run.append(w)
        else: break
    return run


def depth_of(N, fanins):
    """longest-path depth over a DAG given per-node fanin lists (indices strictly < node). memoised."""
    d = [0] * N
    ok = True
    for i in range(N):
        best = 0
        for r in fanins[i]:
            if r >= i:
                ok = False; continue
            if d[r] + 1 > best: best = d[r] + 1
        d[i] = best
    return (max(d) if d else 0), ok


def try_encoding(N, E, nIn, arity, body):
    """encoding: node i (i in [nIn, nIn+E)) is a gate; its `arity` fanins are the next `arity` body words.
       node id space = N. returns (frac_backward, depth, valid)."""
    fanins = [[] for _ in range(N)]
    good = tot = 0
    bi = 0
    for gi in range(E):
        nid = nIn + gi
        if nid >= N: break
        fs = []
        for _ in range(max(1, arity)):
            if bi >= len(body): break
            r = body[bi]; bi += 1
            fs.append(r)
            tot += 1
            if r < nid: good += 1
        if nid < N: fanins[nid] = fs
    frac = good / tot if tot else 0
    depth, valid = depth_of(N, fanins)
    return frac, depth, valid, fanins


def tiling(body, width=15):
    """detect the tiled/bit-slice stride: reshape to `width` cols, per-column dominant delta."""
    nc = len(body) // width
    if nc < 3: return None
    cols = []
    for c in range(width):
        col = [body[r*width + c] for r in range(nc)]
        deltas = [col[i+1]-col[i] for i in range(len(col)-1)]
        dom, freq = Counter(deltas).most_common(1)[0]
        cols.append((dom, freq/len(deltas)))
    march = Counter(d for d, f in cols if f >= 0.6 and d not in (0, 1))
    counters = sum(1 for d, f in cols if d == 1 and f >= 0.6)
    consts = sum(1 for d, f in cols if d == 0 and f >= 0.6)
    return {"cells": nc, "width": width, "counter_cols": counters, "const_cols": consts,
            "march_stride": march.most_common(1)[0] if march else None}


def main():
    exp = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    nth = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    g = GGUF(TITAN); mm = g.mm
    t = g.tensors["blk.1.ffn_gate_up_exps.weight"]
    ne0, ne1, nexp = t["dims"]; bpb, wpb = _QT[t["type"]]
    base = g.data0 + t["off"]; eb = ne1 * (ne0 // wpb * bpb)
    end = base + (ne0*ne1*nexp)//wpb*bpb
    offs = records(mm, base, end)
    in_exp = [o for o in offs if (o - base)//eb == exp]
    if not in_exp:
        print(f"no TITANCIR record in expert {exp}. experts with records: "
              f"{sorted(set((o-base)//eb for o in offs))}"); return 1
    o = in_exp[min(nth, len(in_exp)-1)]
    ver, N, E, nIn, nOut, arity = struct.unpack_from("<6I", mm, o + 8)
    print(f"expert {exp} record #{nth}: ver={ver} nodes={N:,} edges={E:,} nIn={nIn} nOut={nOut} arity={arity}")

    want = E * max(1, arity) + 8
    body = read_body(mm, o, want, bound=max(N * 2, 4096))
    print(f"body: {len(body):,} in-range u32  (expected E*arity = {E*max(1,arity):,})")
    print(f"body[:30]: {body[:30]}")

    # tiling / bit-slice detection at a few widths
    print("\ntiling scan (reshape width -> counter/const/march columns):")
    for w in (15, arity, nIn if nIn>1 else 8, 8, 16, 32):
        ti = tiling(body, w)
        if ti: print(f"  w={w:>3}: cells {ti['cells']:>5} counters {ti['counter_cols']} const {ti['const_cols']} march {ti['march_stride']}")

    # DAG encodings
    print("\nDAG reconstruction (node i>=nIn is a gate; its `arity` fanins follow in body):")
    best = None
    for ar in ({arity, 2, 3, 1} if arity else {2,3,1}):
        if ar < 1: continue
        frac, depth, valid, fanins = try_encoding(N, E, nIn, ar, body)
        tag = "VALID DAG" if frac > 0.98 else ("mostly-DAG" if frac > 0.85 else "not a clean DAG")
        print(f"  arity={ar}: {frac:5.1%} backward-refs, depth {depth}  -> {tag}")
        if best is None or frac > best[0]: best = (frac, ar, depth, valid)
    print(f"\n>> best: arity={best[1]}, {best[0]:.1%} backward, critical-path depth ~{best[2]} gate-delays "
          f"({'a real feed-forward circuit' if best[0]>0.9 else 'partially decoded — semantics need the cell spec'})")
    # honest interpretation of node accounting
    print(f"\naccounting: N={N} nodes, nIn={nIn} inputs -> {N-nIn} internal; E={E} edges; "
          f"E*arity/{'':0}={E*max(1,arity)} refs vs {len(body)} body words "
          f"({'match' if abs(E*max(1,arity)-len(body))<=8 else 'mismatch — encoding differs'})")


if __name__ == "__main__":
    raise SystemExit(main())
