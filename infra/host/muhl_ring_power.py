#!/usr/bin/env python3
"""muhl_ring_power.py — THE RING POWER BUS (Bryce's topology, 2026-07-29). TEST + UNDERSTAND, then deliver.

A one-way wire in a CIRCLE, tapping the circuit at N points. Shoot the signal in ONCE; it circles the ring,
DINGING each tap it passes. A STRONGER shot splits into K electrons spaced around the loop -> K taps ding
per lap = K PARALLEL clocks from one injection. Energy in = electron count = parallelism (powered, not free).

Fabricated as gates: state = N ring cells; the one-way circulation is next[i] = state[(i-1) mod N] (the pulse
moves forward one cell each settle); dings-this-step = popcount(state). Verified BYTE-EXACT vs an independent
Python ring, a MUTANT (broken rotate) is caught, and we measure that exactly K taps ding per step and the swarm
circulates with period N. This is the power-distribution bus for the winner-only fold.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits

def build_ring(N, mutant=None):
    g = CC.CircuitCompiler(N); st = g.IN
    nxt = [st[(i - 1) % N] for i in range(N)]              # ONE-WAY circulation: pulse advances one cell / settle
    if mutant == "no_move":  nxt = [st[i] for i in range(N)]          # pulses frozen (not circulating)
    if mutant == "drop":     nxt = [st[(i - 1) % N] if i != 0 else g.C0 for i in range(N)]  # tap 0 eats a pulse
    CB = N.bit_length()
    acc = [g.C0] * CB                                      # dings-this-step = popcount(state) = # taps struck now
    for i in range(N): acc, _ = add_bits(g, acc, [st[i]] + [g.C0] * (CB - 1))
    gates, out2 = g.dce(nxt + acc)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    nf, cf = out2[:N], out2[N:]
    def step(state):
        v = run(state, 1)
        return [v[w] & 1 for w in nf], sum(((v[w] & 1) << b) for b, w in enumerate(cf))
    return step, len(gates)

def inject_k_electrons(N, K):                              # a stronger shot = K pulses spaced evenly around the ring
    s = [0] * N
    for j in range(K): s[(j * N) // K] = 1
    return s

def ref_rotate(s): return [s[(i - 1) % len(s)] for i in range(len(s))]

def main():
    N = 24
    step, ng = build_ring(N)
    print("\n  RING POWER BUS — %d-cell one-way ring, fabricated as %d gates (popcount of the taps)\n" % (N, ng))

    # TEST 1: byte-exact circulation + exactly K dings/step, for stronger and stronger shots
    print("  TEST — inject K electrons, run a full lap+, verify byte-exact & count the parallel dings:")
    all_ok = True
    for K in (1, 2, 3, 4, 6, 8, 12):
        state = inject_k_electrons(N, K); start = list(state)
        ok = True; dings_each = set(); period = None
        ref = list(state)
        for t in range(1, 2 * N + 1):
            gs, dings = step(state)                        # fabricated ring
            ref = ref_rotate(ref)                          # independent reference
            if gs != ref: ok = False; break
            dings_each.add(dings)
            state = gs
            if state == start and period is None: period = t
        all_ok &= ok and dings_each == {K} and period == N // K   # symmetric K-swarm recurs every N/K steps
        print("    K=%2d electrons -> %d taps ding EVERY step (set=%s), pattern period %d (=N/K, tighter with K), byte-exact %s"
              % (K, K, sorted(dings_each), period, ok))
    print("\n  => the shot strength K IS the parallel-lane count: K electrons = K clocks ticking at once, one injection.")

    # TEST 2: MUTANTS — a broken ring must be CAUGHT (a check that can't fail has measured nothing)
    print("\n  MUTANT CHECK (a broken ring must fail the byte-exact test):")
    for mut, why in (("no_move", "pulses frozen — never circulate"), ("drop", "tap 0 eats a pulse — lane lost")):
        mstep, _ = build_ring(N, mutant=mut)
        state = inject_k_electrons(N, 4); ref = list(state); caught = False
        for t in range(N):
            gs, _ = mstep(state); ref = ref_rotate(ref)
            if gs != ref: caught = True; break
            state = gs
        print("    mutant '%s' (%s): CAUGHT by byte-exact check = %s" % (mut, why, caught))
        all_ok &= caught

    print("\n  === %s ===" % ("RING VERIFIED — byte-exact, K-parallel, mutants caught" if all_ok else "FAIL"))
    print("  UNDERSTANDING: one hard injection of K electrons self-circulates a K-wide clock over the ring; each lap")
    print("  strikes all N taps, K at a time, forever (period N), host addressing = 1. Wire the taps to the miner's")
    print("  clocks (§1E) and this is the fold's POWER BUS — signal strength K sets how many lanes fire in parallel.")
    return 0 if all_ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
