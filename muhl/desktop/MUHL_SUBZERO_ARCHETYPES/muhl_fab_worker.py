#!/usr/bin/env python3
"""muhl_fab_worker.py -- FABRICATE MUHL_WORKER: a general-purpose 16-bit ALU task processor.

Bryce Muhlnickel, 2026-08-03.

The substrate's hands: a circuit that reads 16-bit operands + opcode, computes one
of 8 operations, and writes the result. Self-clocked accumulator for continuous
operation. Powered by the reservoir via rings.

This is FABRICATION -- offline, one-and-done manufacturing. The circuit is stored
in titan.gguf as physical-format gate records and runs itself after electron injection.

PROPOSE -> SCORE -> VERIFY -> KEEP pipeline:
  Candidate 1: ripple-carry arithmetic (lower gate count)
  Candidate 2: prefix-carry arithmetic (lower depth)

    python muhl_fab_worker.py           # fabricate and store
    python muhl_fab_worker.py --dry     # verify only, store nothing

Operations (3-bit opcode):
  000  XOR    A ^ B
  001  AND    A & B
  010  OR     A | B
  011  NOT    ~A
  100  ADD    A + B  (mod 2^16)
  101  SUB    A - B  (mod 2^16)
  110  LT     1 if A < B else 0 (unsigned)
  111  ACCUM  acc + A (mod 2^16)
"""
import sys, os, json, random, time

sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")

import pfc_paths as PFCP
import titan_circuit as TC

DRY = "--dry" in sys.argv
TITAN = PFCP.TITAN
REG = PFCP.REG
NAME = "muhl_worker"
GENOME_PATH = TITAN.replace(".gguf", "_worker_genome.jsonl")

W = 16          # operand width in bits
N_OPS = 8       # number of operations
OP_BITS = 3     # bits for opcode
N_STATE = W     # accumulator is W bits

RESERVOIR_INPUT = 40_022_599_232


# ============================================================================
# CIRCUIT BUILDING
# ============================================================================

def depth_of(c, outs):
    """Compute critical-path depth (the muhlnickel's latency in ticks)."""
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def add_cin(c, A, B, cin):
    """Ripple-carry add with carry-in. Returns sum bits (mod 2^len)."""
    out = []
    carry = cin
    for i in range(len(A)):
        axb = c.xor(A[i], B[i])
        out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(A[i], B[i]), c.and_(axb, carry))
    return out


def build_worker(arith_kind):
    """Build the worker ALU circuit.

    arith_kind: "ripple" or "prefix" (affects ADD/SUB depth).

    Input layout (LSB-first within each field):
      [0:W]           accumulator state (self-routed)
      [W:2W]          operand A (host-written)
      [2W:3W]         operand B (host-written)
      [3W:3W+OP_BITS] opcode (host-written, 3 bits)

    Output layout:
      [0:W]           result (also becomes the new accumulator via feedback)
    """
    N_IN = N_STATE + W + W + OP_BITS                    # 51 bits
    c = TC.Circuit(N_IN)
    IN = c.IN
    p = 0

    acc = [IN[p + i] for i in range(W)]; p += W
    A   = [IN[p + i] for i in range(W)]; p += W
    B   = [IN[p + i] for i in range(W)]; p += W
    op  = [IN[p + i] for i in range(OP_BITS)]; p += OP_BITS
    assert p == N_IN

    # -- compute all 8 operations in parallel ----------------------------------

    # Op 0: XOR
    r_xor = [c.xor(A[i], B[i]) for i in range(W)]

    # Op 1: AND
    r_and = [c.and_(A[i], B[i]) for i in range(W)]

    # Op 2: OR
    r_or = [c.or_(A[i], B[i]) for i in range(W)]

    # Op 3: NOT A
    r_not = [c.not_(A[i]) for i in range(W)]

    # Op 4: ADD  (A + B mod 2^16)
    if arith_kind == "prefix":
        r_add = c.add_prefix(A, B)
    else:
        r_add = c.add(A, B)

    # Op 5: SUB  (A - B mod 2^16 = A + ~B + 1)
    not_B = [c.not_(b) for b in B]
    if arith_kind == "prefix":
        r_sub = c.sub_prefix(A, B)
    else:
        r_sub = add_cin(c, A, not_B, c.C1)

    # Op 6: LT  (unsigned A < B -> 1 in LSB, rest 0)
    lt_bit = TC.lt(c, A, B)
    r_lt = [lt_bit] + [c.C0] * (W - 1)

    # Op 7: ACCUM  (acc + A mod 2^16)
    if arith_kind == "prefix":
        r_acc = c.add_prefix(acc, A)
    else:
        r_acc = c.add(acc, A)

    ops = [r_xor, r_and, r_or, r_not, r_add, r_sub, r_lt, r_acc]

    # -- 8-way mux selected by 3-bit opcode (tree, depth 3 of muxes) ----------
    result = []
    for b in range(W):
        m01 = c.mux(op[0], ops[0][b], ops[1][b])       # op[0]=0 -> ops[0], =1 -> ops[1]
        m23 = c.mux(op[0], ops[2][b], ops[3][b])
        m45 = c.mux(op[0], ops[4][b], ops[5][b])
        m67 = c.mux(op[0], ops[6][b], ops[7][b])
        m03 = c.mux(op[1], m01, m23)
        m47 = c.mux(op[1], m45, m67)
        result.append(c.mux(op[2], m03, m47))

    return c, result


# ============================================================================
# PURE-PYTHON REFERENCE
# ============================================================================

MASK = (1 << W) - 1


def ref_worker(A_val, B_val, opcode, acc_val):
    """Reference implementation: returns result."""
    if opcode == 0:   return (A_val ^ B_val) & MASK
    if opcode == 1:   return (A_val & B_val) & MASK
    if opcode == 2:   return (A_val | B_val) & MASK
    if opcode == 3:   return (~A_val) & MASK
    if opcode == 4:   return (A_val + B_val) & MASK
    if opcode == 5:   return (A_val - B_val) & MASK
    if opcode == 6:   return 1 if A_val < B_val else 0
    if opcode == 7:   return (acc_val + A_val) & MASK
    return 0


# ============================================================================
# VERIFICATION
# ============================================================================

def pack_inputs(acc_val, A_val, B_val, opcode):
    """Pack values into input bit vector (LSB first per field)."""
    inp = []
    for val, nbits in [(acc_val, W), (A_val, W), (B_val, W), (opcode, OP_BITS)]:
        for b in range(nbits):
            inp.append((val >> b) & 1)
    return inp


def unpack_result(v_out):
    """Unpack output bit vector to result value."""
    val = 0
    for b in range(W):
        val |= (v_out[b] & 1) << b
    return val


def verify(circ, outs, n_cases=500, seed=42):
    """Verify byte-exact match between circuit and reference."""
    cd = {"n_in": circ.n_in, "n_wire": circ.n_wire(),
          "ga": circ.ga, "gb": circ.gb, "outs": outs}
    rng = random.Random(seed)
    bad = 0
    for _ in range(n_cases):
        A_val   = rng.randrange(1 << W)
        B_val   = rng.randrange(1 << W)
        opcode  = rng.randrange(N_OPS)
        acc_val = rng.randrange(1 << W)

        inp  = pack_inputs(acc_val, A_val, B_val, opcode)
        v_out = TC.ripple(cd, inp)
        got  = unpack_result(v_out)
        ref  = ref_worker(A_val, B_val, opcode, acc_val)

        if got != ref:
            bad += 1
            if bad <= 3:
                print(f"    MISMATCH: A={A_val:#06x} B={B_val:#06x} op={opcode} "
                      f"acc={acc_val:#06x} -> got={got:#06x} ref={ref:#06x}")
    return bad


# ============================================================================
# STORAGE
# ============================================================================

def store_worker(circ, outs):
    """Store as a self-clocked loop: result feeds back to accumulator."""
    feedback = [(i, i) for i in range(W)]               # result[i] -> acc[i]
    state_bytes = (W + 7) // 8                           # 2 bytes for 16-bit acc

    loop_outs = list(outs) + [circ.C1]                   # append constant-1 loop bit
    loop_bit  = len(outs)                                # index of the loop bit

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
    print("\n  MUHLNICKEL WORKER -- 16-bit ALU task processor")
    print("  Bryce Muhlnickel, 2026-08-03\n")

    # -- PROPOSE: two candidate structures ------------------------------------
    candidates = ["ripple", "prefix"]
    print(f"  PROPOSE: {len(candidates)} candidate structures for 16-bit ALU\n")

    results = []
    for arith in candidates:
        t0 = time.time()
        c, outs = build_worker(arith)
        t_build = time.time() - t0

        d = depth_of(c, outs)
        g = len(c.ga)

        # SCORE
        tag = f"{arith:8s}  DEPTH {d:5d}  gates {g:>7,}  build {t_build:.1f}s"

        # VERIFY
        t0 = time.time()
        bad = verify(c, outs, n_cases=500, seed=42)
        t_v = time.time() - t0
        ok = bad == 0
        print(f"    {tag}  verify {'OK' if ok else f'{bad}/500 WRONG'}  ({t_v:.1f}s)")

        results.append({"arith": arith, "depth": d, "gates": g, "verified": ok,
                        "circ": c, "outs": outs})

    # -- SCORE: Pareto front --------------------------------------------------
    good = [r for r in results if r["verified"]]
    pareto = [r for r in good if not any(
        o["depth"] <= r["depth"] and o["gates"] <= r["gates"] and o is not r
        and (o["depth"] < r["depth"] or o["gates"] < r["gates"])
        for o in good)]

    print(f"\n  VERIFIED {len(good)}/{len(results)}   PARETO FRONT ({len(pareto)}):")
    for r in sorted(pareto, key=lambda x: x["depth"]):
        print(f"    DEPTH {r['depth']:5d}  gates {r['gates']:>7,}   {r['arith']}")

    best = min(good, key=lambda r: r["depth"]) if good else None
    if not best:
        print("  NO VERIFIED CANDIDATES -- aborting")
        return 1

    print(f"\n  WINNER by DEPTH: {best['arith']}  DEPTH {best['depth']}  gates {best['gates']:,}")

    if DRY:
        print(f"\n  --dry: nothing stored. Run without --dry to fabricate.")
        print(f"\n  MUHL_WORKER fabrication verified.")
        print(f"  Operations: XOR AND OR NOT ADD SUB LT ACCUM (16-bit)")
        print(f"  Self-clocked: result feeds back to accumulator")
        print(f"  Powered by reservoir at {RESERVOIR_INPUT:,}")
        return 0

    # -- final re-verify with different seed ----------------------------------
    print(f"\n  FABRICATING -- final re-verify with different seed...")
    c, outs = best["circ"], best["outs"]
    bad = verify(c, outs, n_cases=200, seed=99)
    if bad:
        print(f"  FINAL RE-VERIFY FAILED ({bad}/200) -- nothing stored.")
        return 1
    print(f"  final re-verify: 200 cases OK")

    # -- KEEP: store via store_loop -------------------------------------------
    info = store_worker(c, outs)
    print(f"\n  KEEP: stored {info['name']} @ offset {info['offset']:,}")
    print(f"    gates:          {info['gates']:,}")
    print(f"    state register: offset {info['state_off']:,}")
    print(f"    loop bit:       offset {info['loop_bit_off']:,}")

    # -- update registry with metadata ----------------------------------------
    reg = json.load(open(REG))
    if NAME in reg:
        reg[NAME].update({
            "depth": best["depth"],
            "width": W,
            "operations": ["XOR", "AND", "OR", "NOT", "ADD", "SUB", "LT", "ACCUM"],
            "opcode_bits": OP_BITS,
            "arith": best["arith"],
            "searched": len(candidates),
            "pareto": len(pareto),
            "foundry_genome": {"arith": best["arith"], "depth": best["depth"],
                               "gates": best["gates"]},
            "units": "n_gate=GATES, depth=TICKS, len=BYTES",
            "genome": GENOME_PATH,
            "note": ("general-purpose 16-bit ALU: 8 ops, self-clocked accumulator, "
                     "ring-powered via reservoir"),
            "verified_by": "byte-exact vs Python reference, 700 cases (500+200 re-verify)"
        })
    json.dump(reg, open(REG, "w"), indent=1)

    print(f"\n  MUHL_WORKER FABRICATED.")
    print(f"    journal:    {GENOME_PATH}")
    print(f"    operations: XOR AND OR NOT ADD SUB LT ACCUM")
    print(f"    width:      {W}-bit operands")
    print(f"    depth:      {best['depth']} ticks")
    print(f"    gates:      {best['gates']:,}")
    print(f"    self-clock: result -> accumulator (output == input addresses)")
    print(f"    receiver:   muhl_reservoir (inject at {RESERVOIR_INPUT:,})")
    print(f"\n  TO USE:")
    print(f"    host writes: operand A, operand B, opcode (inject verb)")
    print(f"    substrate:   electron through gate records (no host involvement)")
    print(f"    host reads:  result register (surface verb)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
