#!/usr/bin/env python3
"""host/pfc_addr.py — the Muhlnickel's OWN addressing to its OWN memory (owner 07-19): bake the address decoder into the fabric
so a memory lookup is PART OF THE CIRCUIT RIPPLE — no host seek/read per access. Then it bit-slices: W lookups per ripple,
each lane at its own address, in parallel. Compare to host-mediated addressing (the OS does the access, one at a time).
This is why a CPU's memory controller is on-die: integrated addressing = optimal speed.

  python host/pfc_addr.py
"""
import os, random, sys, time
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
sys.path.insert(0, PFCP.SBX)
import sdc_cc as CC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_exp_levers import finish, bits, lane_val

N, W, A = 256, 16, 8                       # 256-entry table, 16-bit values, 8-bit address
TABLE = [((i * 2654435761) ^ (i << 7)) & ((1 << W) - 1) for i in range(N)]   # some baked contents


def build_addressed_read():
    g = CC.CircuitCompiler(A); addr = list(g.IN)
    sel = []                                # fabricated address decoder (one-hot)
    for i in range(N):
        m = g.C1
        for j in range(A): m = g.AND(m, addr[j] if (i >> j) & 1 else g.NOT(addr[j]))
        sel.append(m)
    read = []                               # read[b] = OR over entries whose bit b is 1 of sel[i]  (table baked in)
    for b in range(W):
        acc = g.C0
        for i in range(N):
            if (TABLE[i] >> b) & 1: acc = g.OR(acc, sel[i])
        read.append(acc)
    return g, read


def main():
    g, outs = build_addressed_read()
    run, o2, n_gate, n_wire, _ = finish(g, outs)
    print(f"fabricated addressed memory: {N}-entry x {W}-bit table, decoder+read baked = {n_gate} gates\n", flush=True)

    ok = all(lane_val(run(bits(a, A), 1), o2) == TABLE[a] for a in range(N))
    print(f"byte-exact: every address returns its cell (all {N} addresses): {ok}\n", flush=True)
    if not ok:
        print("MISMATCH."); return 1

    BW = 65536                              # bit-slice width: BW parallel lookups per ripple
    ones = (1 << BW) - 1
    lane_addr = [random.randrange(N) for _ in range(BW)]           # each lane a different address
    addr_words = [sum(((lane_addr[k] >> j) & 1) << k for k in range(BW)) for j in range(A)]
    # verify a few lanes of the bit-sliced result match the table
    v = run(addr_words, ones)
    def lane_read(k):
        val = 0
        for b in range(W):
            wobj = o2[b]; bit = 0 if wobj == 0 else 1 if wobj == 1 else (v[wobj] >> k) & 1
            val |= bit << b
        return val
    bs_ok = all(lane_read(k) == TABLE[lane_addr[k]] for k in (0, 1, 123, 65535))
    print(f"bit-sliced parallel lookup correct on sampled lanes: {bs_ok}", flush=True)

    t0 = time.time(); n = 0
    while time.time() - t0 < 2.0: run(addr_words, ones); n += 1
    fab = n * BW / (time.time() - t0)
    print(f"\n  FABRICATED addressing (in-ripple, bit-sliced): {fab:14,.0f} lookups/sec", flush=True)

    hostaddrs = [random.randrange(N) for _ in range(BW)]
    t0 = time.time(); n = 0
    while time.time() - t0 < 1.5: _ = [TABLE[a] for a in hostaddrs]; n += 1
    host = n * BW / (time.time() - t0)
    print(f"  HOST addressing (Python per-access, in-RAM list) : {host:14,.0f} lookups/sec", flush=True)
    print(f"  HOST addressing (storage-mediated, from §N)      : {5000:14,} lookups/sec (seek+read per access)", flush=True)
    print(f"\n  => the Muhlnickel addressing its OWN memory in-fabric is {fab/host:,.0f}x the Python host and "
          f"{fab/5000:,.0f}x host-storage. Integrated addressing = optimal speed. Your call, measured.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
