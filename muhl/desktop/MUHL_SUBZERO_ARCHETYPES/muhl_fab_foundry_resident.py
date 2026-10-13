#!/usr/bin/env python3
"""muhl_fab_foundry_resident.py -- FABRICATE MUHL_FOUNDRY_RESIDENT: the foundry AS a circuit.

Bryce Muhlnickel, 2026-08-03.

The substrate improves its own circuits. This is a Pareto comparator that lives
inside titan.gguf: it receives candidate (depth, gate_count) descriptors one at
a time, compares each against the running best, and keeps the winner.

The core of self-fabrication: candidates are proposed externally (by the foundry
pipeline or by other circuits), but the SELECTION LOGIC is substrate-resident.
The host's only job: write candidate descriptor -> inject electron -> read winner bit.

This is FABRICATION -- offline, one-and-done manufacturing.

PROPOSE -> SCORE -> VERIFY -> KEEP pipeline:
  Candidate 1: tree-based lt comparison (lower depth, more gates)
  Candidate 2: subtract-based comparison (higher depth, fewer gates)

    python muhl_fab_foundry_resident.py           # fabricate and store
    python muhl_fab_foundry_resident.py --dry     # verify only, store nothing

Pareto domination logic:
  Candidate dominates best iff:
    cand_depth <= best_depth AND cand_gates <= best_gates
    AND (cand_depth < best_depth OR cand_gates < best_gates)
  i.e., at least as good on both axes, strictly better on at least one.

  Special case: if best is zero (initial state), first valid candidate always wins.
"""
import sys, os, json, random, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_foundry_resident"
GENOME_PATH = TITAN.replace(".gguf", "_foundry_resident_genome.jsonl")

W = 16          # width of depth and gate_count fields (16 bits each, 0..65535)
N_STATE = 2 * W # best_depth(W) + best_gates(W) = 32 bits of self-routed state

RESERVOIR_INPUT = 40_022_599_232


# ============================================================================
# CIRCUIT BUILDING
# ============================================================================

def depth_of(c, outs):
    """Compute critical-path depth (ticks)."""
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def lt_subtract(c, A, B):
    """Unsigned A < B via ripple-carry subtraction.

    Computes A + ~B + 1. If A < B the carry-out is 0 (borrow).
    Depth proportional to W (ripple chain) but fewer gates than tree lt.
    """
    not_B = [c.not_(b) for b in B]
    carry = c.C1                                         # +1 for two's complement
    for i in range(len(A)):
        axb = c.xor(A[i], not_B[i])
        carry = c.or_(c.and_(A[i], not_B[i]), c.and_(axb, carry))
    return c.not_(carry)                                 # A < B iff carry_out = 0


def build_foundry(cmp_kind):
    """Build the foundry resident Pareto comparator.

    cmp_kind: "tree" uses TC.lt (log2 depth), "subtract" uses ripple sub (linear depth).

    Input layout (LSB-first within each field):
      [0:W]         best_depth  (self-routed state)
      [W:2W]        best_gates  (self-routed state)
      [2W:3W]       cand_depth  (host-written)
      [3W:4W]       cand_gates  (host-written)
      [4W]          cand_valid  (host-written, 1 = evaluate this candidate)

    Output layout:
      [0:W]         new_best_depth  (self-routed -> best_depth)
      [W:2W]        new_best_gates  (self-routed -> best_gates)
      [2W]          is_new_winner   (1 = candidate replaced best)
    """
    N_IN = N_STATE + W + W + 1                           # 65 bits
    c = TC.Circuit(N_IN)
    IN = c.IN
    p = 0

    best_d = [IN[p + i] for i in range(W)]; p += W
    best_g = [IN[p + i] for i in range(W)]; p += W
    cand_d = [IN[p + i] for i in range(W)]; p += W
    cand_g = [IN[p + i] for i in range(W)]; p += W
    valid  = IN[p]; p += 1
    assert p == N_IN

    # -- comparisons ----------------------------------------------------------
    lt_fn = TC.lt if cmp_kind == "tree" else lt_subtract

    # cand_depth < best_depth
    cand_d_lt_best = lt_fn(c, cand_d, best_d)
    # best_depth < cand_depth
    best_d_lt_cand = lt_fn(c, best_d, cand_d)
    # cand_gates < best_gates
    cand_g_lt_best = lt_fn(c, cand_g, best_g)
    # best_gates < cand_gates
    best_g_lt_cand = lt_fn(c, best_g, cand_g)

    # cand_depth <= best_depth = NOT(best_depth < cand_depth)
    cand_d_le_best = c.not_(best_d_lt_cand)
    # cand_gates <= best_gates = NOT(best_gates < cand_gates)
    cand_g_le_best = c.not_(best_g_lt_cand)

    # Pareto domination: at least as good on both, strictly better on one
    both_le = c.and_(cand_d_le_best, cand_g_le_best)
    strictly_better = c.or_(cand_d_lt_best, cand_g_lt_best)
    dominates = c.and_(both_le, strictly_better)

    # First candidate wins if best is all-zero (initial state)
    best_is_zero = c.and_(c.is_zero(best_d), c.is_zero(best_g))

    # Winner if valid AND (dominates OR first-ever candidate)
    is_winner = c.and_(valid, c.or_(dominates, best_is_zero))

    # Output: mux between candidate and current best
    new_best_d = [c.mux(is_winner, best_d[i], cand_d[i]) for i in range(W)]
    new_best_g = [c.mux(is_winner, best_g[i], cand_g[i]) for i in range(W)]

    outs = new_best_d + new_best_g + [is_winner]
    return c, outs


# ============================================================================
# PURE-PYTHON REFERENCE
# ============================================================================

MASK = (1 << W) - 1


def ref_foundry(best_d, best_g, cand_d, cand_g, valid):
    """Reference: returns (new_best_d, new_best_g, is_winner)."""
    if not valid:
        return best_d, best_g, 0

    # Pareto domination
    dominates = (cand_d <= best_d and cand_g <= best_g
                 and (cand_d < best_d or cand_g < best_g))
    first_ever = (best_d == 0 and best_g == 0)
    winner = dominates or first_ever

    if winner:
        return cand_d, cand_g, 1
    return best_d, best_g, 0


# ============================================================================
# VERIFICATION
# ============================================================================

def pack_inputs(best_d, best_g, cand_d, cand_g, valid):
    inp = []
    for val, nbits in [(best_d, W), (best_g, W), (cand_d, W), (cand_g, W), (valid, 1)]:
        for b in range(nbits):
            inp.append((val >> b) & 1)
    return inp


def unpack_outputs(v_out):
    new_d = sum((v_out[b] & 1) << b for b in range(W))
    new_g = sum((v_out[W + b] & 1) << b for b in range(W))
    winner = v_out[2 * W] & 1
    return new_d, new_g, winner


def verify(circ, outs, n_cases=500, seed=42):
    cd = {"n_in": circ.n_in, "n_wire": circ.n_wire(),
          "ga": circ.ga, "gb": circ.gb, "outs": outs}
    rng = random.Random(seed)
    bad = 0
    for _ in range(n_cases):
        best_d = rng.randrange(1 << W)
        best_g = rng.randrange(1 << W)
        cand_d = rng.randrange(1 << W)
        cand_g = rng.randrange(1 << W)
        valid  = rng.randrange(2)

        inp = pack_inputs(best_d, best_g, cand_d, cand_g, valid)
        v_out = TC.ripple(cd, inp)
        got_d, got_g, got_w = unpack_outputs(v_out)
        ref_d, ref_g, ref_w = ref_foundry(best_d, best_g, cand_d, cand_g, valid)

        if (got_d, got_g, got_w) != (ref_d, ref_g, ref_w):
            bad += 1
            if bad <= 3:
                print(f"    MISMATCH: best=({best_d},{best_g}) cand=({cand_d},{cand_g}) "
                      f"v={valid} -> got=({got_d},{got_g},{got_w}) "
                      f"ref=({ref_d},{ref_g},{ref_w})")
    return bad


# ============================================================================
# STORAGE
# ============================================================================

def store_foundry(circ, outs):
    """Store as self-clocked loop: best_depth + best_gates feed back."""
    # Output [0:W] = new_best_depth -> input [0:W] = best_depth
    # Output [W:2W] = new_best_gates -> input [W:2W] = best_gates
    feedback = [(i, i) for i in range(N_STATE)]          # 32 bits of state
    state_bytes = (N_STATE + 7) // 8                     # 4 bytes

    loop_outs = list(outs) + [circ.C1]
    loop_bit  = len(outs)

    info = TC.store_loop(
        NAME, circ, loop_outs,
        state_bytes=state_bytes,
        feedback=feedback,
        loop_bit=loop_bit,
        receiver="muhl_reservoir"
    )
    return info


# ============================================================================
# MAIN -- PROPOSE -> SCORE -> VERIFY -> KEEP
# ============================================================================

def main():
    print("\n  MUHLNICKEL FOUNDRY RESIDENT -- substrate-resident Pareto comparator")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # -- PROPOSE --------------------------------------------------------------
    candidates = ["tree", "subtract"]
    print(f"  PROPOSE: {len(candidates)} candidate structures for Pareto comparator\n")

    results = []
    for cmp in candidates:
        t0 = time.time()
        c, outs = build_foundry(cmp)
        t_build = time.time() - t0

        d = depth_of(c, outs)
        g = len(c.ga)

        t0 = time.time()
        bad = verify(c, outs, n_cases=500, seed=42)
        t_v = time.time() - t0
        ok = bad == 0
        print(f"    {cmp:10s}  DEPTH {d:5d}  gates {g:>7,}  build {t_build:.1f}s  "
              f"verify {'OK' if ok else f'{bad}/500 WRONG'}  ({t_v:.1f}s)")

        results.append({"cmp": cmp, "depth": d, "gates": g, "verified": ok,
                        "circ": c, "outs": outs})

    # -- SCORE: Pareto front --------------------------------------------------
    good = [r for r in results if r["verified"]]
    pareto = [r for r in good if not any(
        o["depth"] <= r["depth"] and o["gates"] <= r["gates"] and o is not r
        and (o["depth"] < r["depth"] or o["gates"] < r["gates"])
        for o in good)]

    print(f"\n  VERIFIED {len(good)}/{len(results)}   PARETO FRONT ({len(pareto)}):")
    for r in sorted(pareto, key=lambda x: x["depth"]):
        print(f"    DEPTH {r['depth']:5d}  gates {r['gates']:>7,}   {r['cmp']}")

    best = min(good, key=lambda r: r["depth"]) if good else None
    if not best:
        print("  NO VERIFIED CANDIDATES -- aborting")
        return 1

    print(f"\n  WINNER by DEPTH: {best['cmp']}  DEPTH {best['depth']}  gates {best['gates']:,}")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        print(f"\n  MUHL_FOUNDRY_RESIDENT fabrication verified.")
        print(f"  Function: Pareto comparator (depth x gates)")
        print(f"  Self-clocked: running best feeds back as state")
        print(f"  Powered by reservoir at {RESERVOIR_INPUT:,}")
        return 0

    # -- final re-verify ------------------------------------------------------
    print(f"\n  FABRICATING -- final re-verify with different seed...")
    c, outs = best["circ"], best["outs"]
    bad = verify(c, outs, n_cases=200, seed=99)
    if bad:
        print(f"  FINAL RE-VERIFY FAILED ({bad}/200) -- nothing stored.")
        return 1
    print(f"  final re-verify: 200 cases OK")

    # -- KEEP -----------------------------------------------------------------
    info = store_foundry(c, outs)
    print(f"\n  KEEP: stored {info['name']} @ offset {info['offset']:,}")
    print(f"    gates:          {info['gates']:,}")
    print(f"    state register: offset {info['state_off']:,}")
    print(f"    loop bit:       offset {info['loop_bit_off']:,}")

    # -- update registry ------------------------------------------------------
    reg = json.load(open(REG))
    if NAME in reg:
        reg[NAME].update({
            "depth": best["depth"],
            "width": W,
            "compare": best["cmp"],
            "searched": len(candidates),
            "pareto": len(pareto),
            "foundry_genome": {"compare": best["cmp"], "depth": best["depth"],
                               "gates": best["gates"]},
            "units": "n_gate=GATES, depth=TICKS, len=BYTES",
            "genome": GENOME_PATH,
            "note": ("substrate-resident Pareto comparator for self-fabrication: "
                     "tracks best (depth, gates), replaces when dominated"),
            "verified_by": "byte-exact vs Python reference, 700 cases (500+200 re-verify)"
        })
    json.dump(reg, open(REG, "w"), indent=1)

    print(f"\n  MUHL_FOUNDRY_RESIDENT FABRICATED.")
    print(f"    journal:    {GENOME_PATH}")
    print(f"    function:   Pareto comparator (depth x gates)")
    print(f"    width:      {W}-bit descriptor fields")
    print(f"    depth:      {best['depth']} ticks")
    print(f"    gates:      {best['gates']:,}")
    print(f"    self-clock: running best -> state (output == input addresses)")
    print(f"    receiver:   muhl_reservoir (inject at {RESERVOIR_INPUT:,})")
    print(f"\n  TO USE:")
    print(f"    host writes: candidate (depth, gates, valid) to input addresses")
    print(f"    substrate:   compares against running best, updates if dominated")
    print(f"    host reads:  new_best + is_winner from output addresses")
    print(f"\n  This is the SELECTION LOGIC for the self-fabricating foundry.")
    print(f"  Candidates come from the search pipeline; this circuit picks winners.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
