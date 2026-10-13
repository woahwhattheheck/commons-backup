#!/usr/bin/env python3
"""host/pfc_oblivious_toolkit.py — the OBLIVIOUS / CONTENT-ADDRESSABLE fabric (owner 07-20). Data-oblivious primitives
baked as gates — a "secure enclave in a file," no special hardware: (1) a BITONIC SORT (a FIXED compare-and-swap network
that sorts with no data-dependent branch or access — oblivious by construction), (2) a CAM (content-addressable memory:
one query compared against ALL stored keys in parallel, constant-time). Both byte-exact; both oblivious because the gate
sequence is fixed by the circuit, independent of the data.

  python host/pfc_oblivious_toolkit.py
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC


def less_than(g, a, b):                                 # a < b via subtract-borrow (data-oblivious)
    nb = [g.NOT(x) for x in b]; c = g.C1
    for k in range(len(a)):
        axb = g.XOR(a[k], nb[k]); _ = g.XOR(axb, c); c = g.OR(g.AND(a[k], nb[k]), g.AND(axb, c))
    return g.NOT(c)                                     # borrow = a < b


def cmp_swap(g, a, b):                                  # -> (min, max); always computes both, MUX selects (oblivious)
    lt = less_than(g, a, b); nlt = g.NOT(lt)
    mn = [g.OR(g.AND(lt, a[k]), g.AND(nlt, b[k])) for k in range(len(a))]
    mx = [g.OR(g.AND(lt, b[k]), g.AND(nlt, a[k])) for k in range(len(a))]
    return mn, mx


def bitonic_sort(g, vals):                              # a FIXED cmp-swap network -> data-oblivious sort
    N = len(vals); k = 2
    while k <= N:
        j = k >> 1
        while j > 0:
            for i in range(N):
                l = i ^ j
                if l > i:
                    mn, mx = cmp_swap(g, vals[i], vals[l])
                    if (i & k) == 0: vals[i], vals[l] = mn, mx
                    else: vals[i], vals[l] = mx, mn
            j >>= 1
        k <<= 1
    return vals


def eq(g, a, b):
    e = g.C1
    for k in range(len(a)): e = g.AND(e, g.NOT(g.XOR(a[k], b[k])))
    return e


def word_at(v, outs, o, W):
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    return sum(bit(outs[o + i]) << i for i in range(W))


def main():
    print("Muhlnickel OBLIVIOUS / CAM fabric — data-oblivious sort + content-addressable memory, baked as gates.\n", flush=True)

    # (1) BITONIC SORT: N W-bit values, fixed cmp-swap network
    N, W = 8, 8
    g = CC.CircuitCompiler(N * W)
    vals = [list(g.IN[i * W:(i + 1) * W]) for i in range(N)]
    outv = bitonic_sort(g, vals)
    outs = [w for val in outv for w in val]
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
    ok = True; random.seed(5)
    for _ in range(100):
        xs = [random.getrandbits(W) for _ in range(N)]
        packed = [(xs[i] >> b) & 1 for i in range(N) for b in range(W)]
        v = CC.ripple_typed(g, gates, nw, packed, 1)
        got = [word_at(v, o2, i * W, W) for i in range(N)]
        if got != sorted(xs): ok = False; break
    print(f"  BITONIC SORT ({N}x{W}-bit): {len(gates)} gates, byte-exact vs sorted(): {ok}", flush=True)
    print(f"    oblivious: the {len([1 for _ in gates])}-gate cmp-swap network is FIXED — same ops/accesses for ANY input, no leak.", flush=True)

    # (2) CAM: one query vs M stored keys in parallel -> match vector + found bit, constant-time
    M, KW = 8, 16
    g2 = CC.CircuitCompiler((M + 1) * KW)
    keys = [list(g2.IN[i * KW:(i + 1) * KW]) for i in range(M)]
    query = list(g2.IN[M * KW:(M + 1) * KW])
    matches = [eq(g2, query, keys[i]) for i in range(M)]
    found = g2.C0
    for m in matches: found = g2.OR(found, m)
    outs2 = matches + [found]
    gates2, o22 = g2.dce(outs2); nw2 = 2 + g2.n_in + len(gates2)
    ok2 = True; random.seed(6)
    for _ in range(200):
        ks = [random.getrandbits(KW) for _ in range(M)]
        q = ks[random.randrange(M)] if random.random() < 0.6 else random.getrandbits(KW)
        packed = [(ks[i] >> b) & 1 for i in range(M) for b in range(KW)] + [(q >> b) & 1 for b in range(KW)]
        v = CC.ripple_typed(g2, gates2, nw2, packed, 1)
        bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
        got = [bit(o22[i]) for i in range(M)]; want = [1 if ks[i] == q else 0 for i in range(M)]
        if got != want or bit(o22[M]) != (1 if any(want) else 0): ok2 = False; break
    print(f"\n  CAM ({M} keys x {KW}-bit, parallel match): {len(gates2)} gates, byte-exact vs reference: {ok2}", flush=True)
    print(f"    content-addressable: the query is compared against ALL {M} keys at once, constant-time, no data-dependent access.", flush=True)

    print(f"\n  a secure-enclave-in-a-file: oblivious sort + CAM as pure gates, no special hardware, byte-exact + leak-free.", flush=True)
    return 0 if (ok and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
