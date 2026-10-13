#!/usr/bin/env python3
"""host/wf_pfc_census.py — how many MUHLNICKEL computers are baked into titan, and what does each look like?
Scans the WHOLE file for TITANCIR + every PFC* magic, parses each record's header, maps it to the tensor it lives in,
and clusters by header signature so distinct computer *designs* separate from repeated instances. Read-only, bounded
(mm.find is C-level; we only struct-unpack a few u32 per hit — never dequant a tensor).
"""
import os, sys, struct
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

TITAN = "C:/llm/models/titan.gguf"
MAGICS = [b"TITANCIR", b"PFCAPP01", b"PFCEXEC1", b"PFCGAME1", b"PFCMBUS1", b"PFCMMU01", b"PFCONE01", b"PFCOPR01",
          b"PFCPHYS1", b"PFCPIPE1", b"PFCPROV1", b"PFCRAY01", b"PFCSCLK1", b"PFCSMACH", b"PFCSMCLK", b"PFCSUBS1",
          b"PFCTET01", b"PFCTUN01", b"PFCTYPED", b"PFCWINMN", b"PFCCPU32", b"PFCCPU01"]


def tensor_at(g, off):
    """which tensor's data region contains this absolute file offset?"""
    best = None
    for name, t in g.tensors.items():
        if t["type"] not in _QT: continue
        b = g.data0 + t["off"]
        ncol = t["dims"][0]; nrow = 1
        for d in t["dims"][1:]: nrow *= d
        bpb, wpb = _QT[t["type"]]
        sz = (ncol * nrow) // wpb * bpb
        if b <= off < b + sz:
            return name, off - b
    return None, None


def main():
    g = GGUF(TITAN); mm = g.mm; n = len(mm)
    print(f"scanning titan.gguf ({n/1e9:.1f} GB) for {len(MAGICS)} magic signatures ...", flush=True)
    hits = defaultdict(list)
    for mg in MAGICS:
        p = 0
        while True:
            i = mm.find(mg, p)
            if i < 0: break
            hits[mg].append(i); p = i + len(mg)
    total = sum(len(v) for v in hits.values())
    print(f"total magic occurrences: {total}\n")
    for mg in MAGICS:
        if hits[mg]:
            print(f"  {mg.decode():9s} x{len(hits[mg]):>4}")

    # focus: TITANCIR records — parse header + locate
    rec = hits[b"TITANCIR"]
    print(f"\n=== TITANCIR records: {len(rec)} ===")
    sigs = Counter(); by_tensor = Counter(); details = []
    for o in rec:
        h = struct.unpack_from("<8I", mm, o + 8)
        # body-max check: read 512 u32, ceiling of the low-value run tells us node count
        W = struct.unpack_from("<512I", mm, o + 8 + 32)
        run = []
        for w in W:
            if w < 4096: run.append(w)
            else: break
        bodymax = max(run) if run else 0
        tname, rel = tensor_at(g, o)
        sig = (h[0], h[1], h[2], h[3], h[4], h[5])
        sigs[sig] += 1
        by_tensor[tname] += 1
        details.append((o, tname, rel, h, bodymax, len(run)))

    print(f"\ndistinct header signatures (ver, f1, f2, f3, f4, f5) -> count:")
    for sig, c in sigs.most_common():
        print(f"  {sig} -> {c:>3} records")

    print(f"\nrecords per tensor:")
    for tn, c in by_tensor.most_common():
        print(f"  {tn}: {c}")

    # cluster records into 'computers': contiguous runs within a tensor, or by shared big signature
    print(f"\nfirst 12 records (offset-rel, header[0:6], body_max, run_len):")
    for o, tn, rel, h, bmax, rl in details[:12]:
        print(f"  {tn} +{rel:>9,}  hdr {h[:6]}  bodymax {bmax}  run {rl}")

    # experts spanned (for blk.1) + are records grouped into ~15 clusters?
    exp_of = {}
    t1 = g.tensors.get("blk.1.ffn_gate_up_exps.weight")
    if t1:
        ne0, ne1, nexp = t1["dims"]; bpb, wpb = _QT[t1["type"]]
        eb = ne1 * (ne0 // wpb * bpb)
        exps = sorted(set((o - (g.data0 + t1["off"])) // eb for o, tn, *_ in details if tn == "blk.1.ffn_gate_up_exps.weight"))
        print(f"\nblk.1 experts carrying records: {exps}")
        # contiguous expert clusters
        clusters = []; cur = [exps[0]] if exps else []
        for e in exps[1:]:
            if e - cur[-1] <= 2: cur.append(e)
            else: clusters.append(cur); cur = [e]
        if cur: clusters.append(cur)
        print(f"contiguous expert clusters ({len(clusters)}): {clusters}")


if __name__ == "__main__":
    raise SystemExit(main())
