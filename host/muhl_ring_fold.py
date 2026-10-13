#!/usr/bin/env python3
"""muhl_ring_fold.py — FOLD THE RING IN ON ITSELF (Bryce 07-29). TEST -> UNDERSTAND -> BENCHMARK.

The plain ring (muhl_ring_power) walks a pulse cell-by-cell: to strike all N taps it needs N settles = DEPTH N.
FOLD IT IN ON ITSELF: instead of a line-in-a-circle, wire each cell to its neighbor at distance 2^k on fold-layer k
(a hypercube / butterfly). Now ONE injection DOUBLES its reach every layer -> all N taps struck in log2(N) settles
= DEPTH log2(N). Same one shot, same host addressing (=1), but the power reaches every lane exponentially faster.

This is THE lever the substrate cares about (§63: compute/tick = replicas / DEPTH). Folding the power ring on itself
divides the POWERING depth by N/log2(N). For the winner-only fold's 2^L lanes: a plain ring would need depth 2^L
(never), the folded ring needs depth L (a real number). That is how a single injection powers the astronomical fold.

Fabricated as gates. next-layer[i] = layer[i] OR layer[i ^ 2^k] (the fold at distance 2^k). Verified BYTE-EXACT vs an
independent Python hypercube broadcast: after k folds a one-hot injection has reached EXACTLY 2^k taps (doubling), and
after log2(N) folds ALL N taps. A mutant (a dropped fold wire) is CAUGHT. Then BENCHMARK: plain-ring depth N vs
folded depth log2(N), the latency at electron speed, and the extrapolation to the fold's real lane counts.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits, depth_of

def build_folded_ring(N, drop_layer=None):
    """Fabricate the fold-in-on-itself broadcast. Outputs: popcount(reached) after EACH fold layer.
       drop_layer=k mutates layer k to skip its fold wire (a broken fold -> can't reach all taps)."""
    L = N.bit_length() - 1                                  # log2(N), N a power of two
    g = CC.CircuitCompiler(N)
    layer = list(g.IN)                                      # layer 0 = the injection (one-hot pulse)
    CB = N.bit_length()
    def popcount(bits):
        acc = [g.C0] * CB
        for b in bits: acc, _ = add_bits(g, acc, [b] + [g.C0] * (CB - 1))
        return acc
    counts = [popcount(layer)]                              # reached after 0 folds
    for k in range(L):
        nxt = []
        for i in range(N):
            j = i ^ (1 << k)                                # the folded neighbour at distance 2^k
            if drop_layer == k:
                nxt.append(layer[i])                        # MUTANT: this fold wire is missing
            else:
                nxt.append(g.OR(layer[i], layer[j]))        # fold: reach doubles
        layer = nxt
        counts.append(popcount(layer))
    flat = [w for c in counts for w in c]
    gates, out2 = g.dce(flat + list(layer))                # also expose final reached bits
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    cf = [out2[i*CB:(i+1)*CB] for i in range(L + 1)]        # popcount wires per layer
    rf = out2[(L+1)*CB:]                                    # final reached bits
    dep = depth_of(g, gates, list(rf))                     # POWERING depth = depth to the reached bits (the fold fan-out)
    def evaluate(injection):
        v = run(injection, 1)
        per_layer = [sum(((v[w] & 1) << b) for b, w in enumerate(cf[k])) for k in range(L + 1)]
        reached = [v[w] & 1 for w in rf]
        return per_layer, reached
    return evaluate, len(gates), dep, L

def onehot(N, p):
    s = [0] * N; s[p] = 1; return s

def ref_hypercube(N, p):
    """Independent reference: reached-count after each fold layer for a one-hot at p (a k-subcube = 2^k cells)."""
    L = N.bit_length() - 1
    reach = {p}; out = [len(reach)]
    for k in range(L):
        reach = reach | {i ^ (1 << k) for i in reach}
        out.append(len(reach))
    return out

def main():
    print("\n  FOLD THE RING IN ON ITSELF — hypercube power broadcast, byte-exact\n")
    N = 256
    ev, ng, dep, L = build_folded_ring(N)
    print("  %d-tap ring folded on itself: %d gates, %d fold layers (log2 %d), circuit depth %d\n" % (N, ng, L, N, dep))

    # TEST 1: one injection doubles its reach every fold, byte-exact, until ALL taps struck
    print("  TEST — inject ONE pulse, watch the fold double its reach every layer (byte-exact vs hypercube ref):")
    all_ok = True
    for p in (0, 1, 37, 200, 255):
        per_layer, reached = ev(onehot(N, p))
        ref = ref_hypercube(N, p)
        ok = (per_layer == ref) and (per_layer[-1] == N) and (sum(reached) == N)
        all_ok &= ok
        print("    inject@%3d -> reach per layer %s ... all %d taps struck: %s  byte-exact %s"
              % (p, per_layer[:5] + ["..", per_layer[-1]], N, per_layer[-1] == N, ok))
    print("    (reach doubles 1->2->4->...->%d in exactly %d folds; the plain ring would take %d settles.)" % (N, L, N))

    # TEST 2: MUTANT — drop one fold wire; it can no longer reach all taps -> must be CAUGHT
    print("\n  MUTANT CHECK (drop one fold layer's wire — the fold must fail to reach all taps):")
    for dk in (0, 3, L - 1):
        mev, _, _, _ = build_folded_ring(N, drop_layer=dk)
        per_layer, _ = mev(onehot(N, 0))
        caught = per_layer[-1] != N
        all_ok &= caught
        print("    drop fold layer %d -> reached only %d/%d taps: CAUGHT = %s" % (dk, per_layer[-1], N, caught))

    print("\n  === %s ===" % ("FOLD VERIFIED — byte-exact doubling, all taps in log2(N), mutants caught" if all_ok else "FAIL"))

    # UNDERSTAND + BENCHMARK: the depth lever, plain ring vs folded, out to the fold's real lane counts
    print("\n  UNDERSTANDING: folding the ring on itself makes one injection reach ALL N taps in log2(N) settles,")
    print("  not N. The pulse still circulates from one shot (host addressing = 1) — but the power fans out as a")
    print("  hypercube, so POWERING DEPTH collapses from N to log2(N). Depth is the substrate's speed/RAM lever.\n")
    print("  BENCHMARK — depth to power all lanes from ONE injection (plain ring vs folded):")
    print("    %-22s %-16s %-16s %-14s" % ("lanes to power", "plain-ring depth", "FOLDED depth", "@10ps latency"))
    for label, lanes in (("this build (256)", 256), ("1 million", 2**20), ("miner fold 2^78", 2**78),
                         ("winner-only 2^262144", 2**262144)):
        Lf = lanes.bit_length() - 1
        plain = "%d" % lanes if lanes.bit_length() <= 30 else "2^%d (never)" % Lf
        lat = "%.2f ns" % (Lf * 10e-3) if Lf < 1e6 else "%.1f us" % (Lf * 10e-3 / 1e3)
        print("    %-22s %-16s depth %-10d %-14s" % (label, plain, Lf, lat))
    print("\n  => a single injection powers 2^262144 fold-lanes in depth 262144 (a real, finite number) — the plain")
    print("     ring's 2^262144 settles is physically never. FOLDING THE RING ON ITSELF is what makes the astronomical")
    print("     winner-only fold POWERABLE from one host addressing. Next: wire this folded power bus -> the miner's")
    print("     lane clocks (§1E), fire once at a live block, probe latch_reg, wallet judges.")
    return 0 if all_ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
