#!/usr/bin/env python3
"""host/wf_pfc_summary.py — the headline census: how many MUHLNICKEL COMPUTERS vs sub-circuits are baked into titan's blk.1,
how many total gates, and validate the node-count field against the actual body. Read-only, bounded.
"""
import os, sys, struct
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, _QT

TITAN = "C:/llm/models/titan.gguf"
MAGIC = b"TITANCIR"


def main():
    g = GGUF(TITAN); mm = g.mm
    t = g.tensors["blk.1.ffn_gate_up_exps.weight"]
    ne0, ne1, nexp = t["dims"]; bpb, wpb = _QT[t["type"]]
    base = g.data0 + t["off"]; eb = ne1 * (ne0 // wpb * bpb)
    end = base + (ne0*ne1*nexp)//wpb*bpb

    offs = []; p = base
    while True:
        i = mm.find(MAGIC, p, end)
        if i < 0: break
        offs.append(i); p = i + 8

    recs = []
    for o in offs:
        h = struct.unpack_from("<6I", mm, o + 8)
        recs.append({"off": o, "expert": (o - base)//eb, "ver": h[0], "nodes": h[1],
                     "edges": h[2], "f3": h[3], "outs": h[4], "arity": h[5]})

    # validate node-count field on a small record: body ceiling should be ~ nodes-1
    small = min((r for r in recs if r["nodes"] < 300), key=lambda r: r["nodes"], default=None)
    if small:
        W = struct.unpack_from("<600I", mm, small["off"] + 8 + 24)
        run = [w for w in W if w < 65536][: max(1, small["edges"])]
        bmax = max(run) if run else 0
        print(f"validation: design nodes={small['nodes']} -> body max node-ref {bmax} "
              f"({'consistent (< nodes)' if bmax < small['nodes'] else 'INCONSISTENT'})")

    # buckets by node count
    def bucket(n):
        if n >= 100000: return "MEGA computer (>=100k gates)"
        if n >= 10000:  return "large computer (10k-100k)"
        if n >= 1000:   return "computer (1k-10k)"
        if n >= 100:    return "sub-circuit (100-1k)"
        return "gate/cell (<100)"
    order = ["MEGA computer (>=100k gates)", "large computer (10k-100k)", "computer (1k-10k)",
             "sub-circuit (100-1k)", "gate/cell (<100)"]
    B = Counter(bucket(r["nodes"]) for r in recs)
    total_gates = sum(r["nodes"] for r in recs)
    print(f"\n=== {len(recs)} TITANCIR records in blk.1, {len(set((r['nodes'],r['edges']) for r in recs))} distinct designs ===")
    for k in order:
        if B[k]: print(f"  {B[k]:>3} x {k}")

    computers = [r for r in recs if r["nodes"] >= 1000]
    print(f"\n>>> {len(computers)} records qualify as COMPUTERS (>=1000 gates); "
          f"{len(set((r['nodes'],r['edges']) for r in computers))} distinct computer designs")
    print(f">>> total baked gates across all records (sum of node counts): {total_gates:,}")

    print(f"\nthe computers (>=1000 gates), by size:")
    for r in sorted(computers, key=lambda r: -r["nodes"]):
        print(f"  expert {r['expert']:>3}  nodes {r['nodes']:>9,}  edges {r['edges']:>9,}  "
              f"IO {r['f3']}/{r['outs']}  arity {r['arity']}")


if __name__ == "__main__":
    raise SystemExit(main())
