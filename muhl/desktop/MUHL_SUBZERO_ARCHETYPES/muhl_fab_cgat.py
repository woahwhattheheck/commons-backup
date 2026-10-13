#!/usr/bin/env python3
"""muhl_fab_cgat.py — FABRICATE the Causal Graph-Algebraic Transducer.

Sub-Zero Archetype #3: Pearl's do-calculus + structural causal model as NAND gates.

Variables: U (8-bit exogenous), X (treatment), Y (outcome).
Structural equations:
    X = NOT(U)              (bitwise, 8 gates)
    Y = X XOR U             (bitwise, 32 gates)

do(X=x) intervention:
    X_active = MUX(do_bit, X_natural, do_value)   (25 gates)
    Y_obs = X_active XOR U                        (32 gates)

Counterfactual twin (same U, forced X):
    Y_cf = do_value XOR U                         (32 gates)

    python muhl_fab_cgat.py           # fabricate and store
    python muhl_fab_cgat.py --dry     # report only, store nothing

97 gates. Depth 6 (Y_obs critical path). 2,599 bytes.
Inputs: U(8) + do_bit(1) + do_value(8) = 17 bits.
Outputs: X_natural(8) + Y_obs(8) + Y_cf(8) = 24 bits.

Verified byte-exact against titan_circuit.Circuit reference AND Python reference.
"""
import json, os, struct, sys

sys.path.insert(0, r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent\host")
import pfc_paths as PFCP

TITAN = PFCP.TITAN
REG = PFCP.REG
NAND_OP = 0
GATE_STRIDE = 25
NAME = "muhl_cgat"
MAGIC = b"MUHLCGAT"
GENOME_PATH = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
DRY = "--dry" in sys.argv

N_BITS = 8

# ---- Wire layout (114 bytes) ----
# Inputs (host writes):
#   [0..7]      U[0..7]
#   [8]         do_bit (0=observe, 1=intervene)
#   [9..16]     do_value[0..7]
# Outputs (host reads):
#   [17..24]    X_natural[0..7]
#   [25..32]    Y_obs[0..7]
#   [33..40]    Y_cf[0..7]
# Intermediates:
#   [41]        ns = NOT(do_bit)
#   [42..49]    nand(ns, X_nat[i])
#   [50..57]    nand(do_bit, do_value[i])
#   [58..65]    X_active[i] = MUX output
#   [66..73]    nand(X_active[i], U[i])         Y_obs XOR stage 1
#   [74..81]    nand(X_active[i], prev[i])      Y_obs XOR stage 2a
#   [82..89]    nand(U[i], prev[i])             Y_obs XOR stage 2b
#   [90..97]    nand(do_value[i], U[i])         Y_cf XOR stage 1
#   [98..105]   nand(do_value[i], prev[i])      Y_cf XOR stage 2a
#   [106..113]  nand(U[i], prev[i])             Y_cf XOR stage 2b

def W_U(i):       return i
W_DO_BIT = 8
def W_DO_V(i):    return 9 + i
def W_X_NAT(i):   return 17 + i
def W_Y_OBS(i):   return 25 + i
def W_Y_CF(i):    return 33 + i
W_NS = 41
def W_NNX(i):     return 42 + i    # nand(ns, X_nat[i])
def W_NDV(i):     return 50 + i    # nand(do_bit, do_value[i])
def W_XA(i):      return 58 + i    # X_active[i]
def W_NXU(i):     return 66 + i    # nand(Xa, U)
def W_NXN(i):     return 74 + i    # nand(Xa, nand_XaU)
def W_NUN(i):     return 82 + i    # nand(U, nand_XaU)
def W_NVU(i):     return 90 + i    # nand(V, U)
def W_NVN(i):     return 98 + i    # nand(V, nand_VU)
def W_NUNV(i):    return 106 + i   # nand(U, nand_VU)
N_WIRES = 114


def alloc_space(nbytes):
    """Bump-allocate in titan.gguf."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    occupied = []
    for k, v in reg.items():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            occupied.append((v["offset"], v["offset"] + v["len"]))
    hi = max((e for _, e in occupied), default=0)
    off = ((hi + 63) // 64) * 64
    fsize = os.path.getsize(TITAN)
    if off + nbytes > fsize:
        print("  NOTE: extends past EOF (%d). titan.gguf will grow." % fsize)
    return off


def build_gates():
    """Build CGAT gate network in topological order. Returns list of (op, a, b, out)."""
    gates = []

    # 1. X_natural[i] = NOT(U[i]) — 8 gates, depth 1
    for i in range(N_BITS):
        gates.append((NAND_OP, W_U(i), W_U(i), W_X_NAT(i)))

    # 2. ns = NOT(do_bit) — 1 gate, depth 1
    gates.append((NAND_OP, W_DO_BIT, W_DO_BIT, W_NS))

    # 3. MUX: X_active = MUX(do_bit, X_natural, do_value) — 24 gates, depth 3
    #    MUX(s, a, b) = NAND(NAND(NOT(s), a), NAND(s, b)) = s ? b : a
    for i in range(N_BITS):
        gates.append((NAND_OP, W_NS, W_X_NAT(i), W_NNX(i)))        # nand(ns, Xn) depth 2
        gates.append((NAND_OP, W_DO_BIT, W_DO_V(i), W_NDV(i)))     # nand(do, V)  depth 1
        gates.append((NAND_OP, W_NNX(i), W_NDV(i), W_XA(i)))       # MUX out      depth 3

    # 4. Y_obs = XOR(X_active, U) — 32 gates, depth 6
    #    XOR(a, b) = NAND(NAND(a, NAND(a,b)), NAND(b, NAND(a,b)))
    for i in range(N_BITS):
        gates.append((NAND_OP, W_XA(i), W_U(i), W_NXU(i)))         # nand(Xa, U)        depth 4
        gates.append((NAND_OP, W_XA(i), W_NXU(i), W_NXN(i)))       # nand(Xa, prev)     depth 5
        gates.append((NAND_OP, W_U(i), W_NXU(i), W_NUN(i)))        # nand(U, prev)      depth 5
        gates.append((NAND_OP, W_NXN(i), W_NUN(i), W_Y_OBS(i)))    # XOR result         depth 6

    # 5. Y_cf = XOR(do_value, U) — 32 gates, depth 3
    for i in range(N_BITS):
        gates.append((NAND_OP, W_DO_V(i), W_U(i), W_NVU(i)))       # nand(V, U)         depth 1
        gates.append((NAND_OP, W_DO_V(i), W_NVU(i), W_NVN(i)))     # nand(V, prev)      depth 2
        gates.append((NAND_OP, W_U(i), W_NVU(i), W_NUNV(i)))       # nand(U, prev)      depth 2
        gates.append((NAND_OP, W_NVN(i), W_NUNV(i), W_Y_CF(i)))    # XOR result         depth 3

    return gates


def fabricate(base_off, gates):
    """Build the physical byte blob."""
    # metadata: magic(8) + n_gates(4) + 6 address fields (6x8=48) = 60
    meta_size = 60
    gate_start = N_WIRES + meta_size
    total = gate_start + len(gates) * GATE_STRIDE
    blob = bytearray(total)
    # all wires init to 0
    # metadata
    off = N_WIRES
    blob[off:off + 8] = MAGIC;                             off += 8
    struct.pack_into("<I", blob, off, len(gates));         off += 4
    addrs = {
        "U":      base_off + W_U(0),
        "do_bit": base_off + W_DO_BIT,
        "do_val": base_off + W_DO_V(0),
        "X_nat":  base_off + W_X_NAT(0),
        "Y_obs":  base_off + W_Y_OBS(0),
        "Y_cf":   base_off + W_Y_CF(0),
    }
    for key in ["U", "do_bit", "do_val", "X_nat", "Y_obs", "Y_cf"]:
        struct.pack_into("<Q", blob, off, addrs[key]);     off += 8
    # gate table
    off = gate_start
    for op, a, b, o in gates:
        struct.pack_into("<BQQQ", blob, off, op, base_off + a, base_off + b, base_off + o)
        off += GATE_STRIDE
    return blob, addrs, total


def simulate(gates, inputs):
    """Single-pass gate simulation (fab-time only). inputs = {wire_idx: value}."""
    w = bytearray(N_WIRES)
    for idx, val in inputs.items():
        w[idx] = val
    for _, a, b, o in gates:
        w[o] = 1 - (w[a] & w[b])
    return w


def verify(blob, base_off, gates):
    """Structural + byte-exact functional verification against 3 independent references."""
    meta_off = N_WIRES
    assert blob[meta_off:meta_off + 8] == MAGIC, "bad magic"
    ng = struct.unpack_from("<I", blob, meta_off + 8)[0]
    assert ng == len(gates), "gate count mismatch"

    # One-writer-per-address + gate record correctness
    writers = {}
    gate_start = N_WIRES + 60
    for i, (eop, ea, eb, eo) in enumerate(gates):
        off = gate_start + i * GATE_STRIDE
        op, a, b, o = struct.unpack_from("<BQQQ", blob, off)
        assert op == NAND_OP, "gate %d: op=%d" % (i, op)
        assert a == base_off + ea, "gate %d: a mismatch" % i
        assert b == base_off + eb, "gate %d: b mismatch" % i
        assert o == base_off + eo, "gate %d: out mismatch" % i
        assert o not in writers, "CONFLICT: gates %d and %d write to %d" % (writers.get(o, -1), i, o)
        writers[o] = i

    # Wire range check
    for i, (_, a, b, o) in enumerate(gates):
        assert 0 <= a < N_WIRES, "gate %d: a=%d out of range" % (i, a)
        assert 0 <= b < N_WIRES, "gate %d: b=%d out of range" % (i, b)
        assert 0 <= o < N_WIRES, "gate %d: o=%d out of range" % (i, o)

    # Reference model using titan_circuit.Circuit (fab-time verification only)
    import titan_circuit as TC
    ref = TC.Circuit(17)  # U(8) + do_bit(1) + do_value(8)
    U_r = ref.IN[:8]
    do_bit_r = ref.IN[8]
    do_val_r = ref.IN[9:17]
    X_nat_r = [ref.not_(u) for u in U_r]
    ns_r = ref.not_(do_bit_r)
    X_act_r = [ref.nand(ref.nand(ns_r, X_nat_r[i]), ref.nand(do_bit_r, do_val_r[i]))
               for i in range(N_BITS)]
    Y_obs_r = [ref.xor(X_act_r[i], U_r[i]) for i in range(N_BITS)]
    Y_cf_r = [ref.xor(do_val_r[i], U_r[i]) for i in range(N_BITS)]
    outs_r = X_nat_r + Y_obs_r + Y_cf_r
    ref_cir = {"n_in": 17, "n_wire": ref.n_wire(), "ga": ref.ga, "gb": ref.gb, "outs": outs_r}

    # Test cases: (U, do_bit, do_value)
    test_cases = [
        (0x42, 0, 0x00),   # observe, no intervention value
        (0x42, 1, 0x37),   # intervene with 0x37
        (0xFF, 0, 0xAA),   # observe, all-1s U
        (0x00, 1, 0xFF),   # intervene, all-0s U, all-1s do_value
        (0xA5, 1, 0x5A),   # mixed
    ]

    for test_U, test_do, test_V in test_cases:
        # --- Python reference ---
        py_Xn = (~test_U) & 0xFF
        if test_do == 0:
            py_Yo = (py_Xn ^ test_U) & 0xFF   # always 0xFF
        else:
            py_Yo = (test_V ^ test_U) & 0xFF
        py_Yc = (test_V ^ test_U) & 0xFF

        # --- titan_circuit reference ---
        inbits = TC.bits(test_U, 8) + [test_do] + TC.bits(test_V, 8)
        ref_out = TC.ripple(ref_cir, inbits)
        ref_Xn = TC.frombits(ref_out[:8])
        ref_Yo = TC.frombits(ref_out[8:16])
        ref_Yc = TC.frombits(ref_out[16:24])

        # --- Physical gate simulation ---
        inp = {}
        for i in range(8):
            inp[W_U(i)] = (test_U >> i) & 1
        inp[W_DO_BIT] = test_do
        for i in range(8):
            inp[W_DO_V(i)] = (test_V >> i) & 1
        w = simulate(gates, inp)
        phys_Xn = sum(w[W_X_NAT(i)] << i for i in range(8))
        phys_Yo = sum(w[W_Y_OBS(i)] << i for i in range(8))
        phys_Yc = sum(w[W_Y_CF(i)] << i for i in range(8))

        # All three must agree
        assert py_Xn == ref_Xn == phys_Xn, \
            "X_nat mismatch (U=%02x do=%d V=%02x): py=%02x ref=%02x phys=%02x" % (
                test_U, test_do, test_V, py_Xn, ref_Xn, phys_Xn)
        assert py_Yo == ref_Yo == phys_Yo, \
            "Y_obs mismatch (U=%02x do=%d V=%02x): py=%02x ref=%02x phys=%02x" % (
                test_U, test_do, test_V, py_Yo, ref_Yo, phys_Yo)
        assert py_Yc == ref_Yc == phys_Yc, \
            "Y_cf mismatch (U=%02x do=%d V=%02x): py=%02x ref=%02x phys=%02x" % (
                test_U, test_do, test_V, py_Yc, ref_Yc, phys_Yc)

    return True


def journal_write(off, blob):
    """Journaled write for revertibility."""
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME_PATH, "a") as g:
        g.write(json.dumps({
            "action": "cgat_fab", "off": off, "len": len(blob), "orig": orig.hex()
        }) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def update_registry(base_off, total, addrs, n_gates):
    """Add CGAT to the circuit registry."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg[NAME] = {
        "name": NAME,
        "offset": base_off, "len": total,
        "n_gate": n_gates, "n_out": 24, "depth": 6,
        "format": "physical", "magic": MAGIC.decode(), "gate_stride": GATE_STRIDE,
        "input_U_addr": addrs["U"],
        "input_do_bit_addr": addrs["do_bit"],
        "input_do_val_addr": addrs["do_val"],
        "output_X_nat_addr": addrs["X_nat"],
        "output_Y_obs_addr": addrs["Y_obs"],
        "output_Y_cf_addr": addrs["Y_cf"],
        "variables": {"U": "exogenous (8-bit)", "X": "treatment (8-bit)", "Y": "outcome (8-bit)"},
        "structural_eqs": {"X": "NOT(U)", "Y": "X XOR U"},
        "intervention": "do(X=do_value) via MUX(do_bit, X_natural, do_value)",
        "counterfactual": "Y_cf = do_value XOR U (twin network sharing exogenous U)",
        "foundry_genome": {
            "archetype": "CGAT", "model": "SCM_3var",
            "eq_X": "NOT_U", "eq_Y": "XOR_X_U",
            "intervention": "mux_do", "depth": 6
        },
        "units": "n_gate=GATES depth=TICKS len=BYTES",
        "genome": GENOME_PATH,
        "note": "Causal Graph-Algebraic Transducer: Pearl do-calculus, 3 variables, twin network counterfactual.",
        "verified_by": "structural + one-writer + byte-exact vs Circuit ref + Python ref (5 test cases)"
    }
    json.dump(reg, open(REG, "w"), indent=1)


def main():
    print("\n  MUHLNICKEL CGAT — Causal Graph-Algebraic Transducer")
    print("  Sub-Zero Archetype #3 — Bryce Muhlnickel, 2026-08-03\n")

    gates = build_gates()
    n_gates = len(gates)
    meta_size = 60
    total = N_WIRES + meta_size + n_gates * GATE_STRIDE

    print("  model:   SCM with 3 variables (U, X, Y)")
    print("  eqs:     X = NOT(U),  Y = X XOR U")
    print("  do(X=x): MUX(do_bit, X_natural, do_value)")
    print("  twin:    Y_cf = do_value XOR U (counterfactual)")
    print("  inputs:  U(8) + do_bit(1) + do_value(8) = 17 bits")
    print("  outputs: X_natural(8) + Y_obs(8) + Y_cf(8) = 24 bits")
    print("  gates:   %d" % n_gates)
    print("  depth:   6 ticks (Y_obs critical path)")
    print("  size:    %d bytes" % total)

    base_off = alloc_space(total)
    print("  offset:  %d" % base_off)

    blob, addrs, total = fabricate(base_off, gates)
    print("  input U:        %d (8 bytes)" % addrs["U"])
    print("  input do_bit:   %d" % addrs["do_bit"])
    print("  input do_value: %d (8 bytes)" % addrs["do_val"])
    print("  output X_nat:   %d (8 bytes)" % addrs["X_nat"])
    print("  output Y_obs:   %d (8 bytes)" % addrs["Y_obs"])
    print("  output Y_cf:    %d (8 bytes)" % addrs["Y_cf"])

    ok = verify(blob, base_off, gates)
    print("  verify: %s (structural + 3-way functional x 5 cases)" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("  ABORTING — verification failed")
        return 1

    print("\n  PARETO SET (Propose / Score / Verify / Keep):")
    print("    A) XOR_eq:  %d gates, depth 6, %d bytes  <- WINNER" % (n_gates, total))
    print("    B) AND_eq:   65 gates, depth 5, ~1700 bytes  (Y = X AND U)")
    print("    Winner: A — XOR makes causal reasoning non-trivial")
    print("    (B: fewer gates + shallower, but Y=X AND U is separable,")
    print("     making do(X) effects trivially predictable — poor demo)")

    if DRY:
        print("\n  --dry: nothing stored.")
        return 0

    print("\n  FABRICATING — %d bytes at offset %d" % (total, base_off))
    journal_write(base_off, bytes(blob))
    print("  journaled: %s" % GENOME_PATH)
    update_registry(base_off, total, addrs, n_gates)
    print("  registry: %s" % NAME)

    print("\n  CGAT FABRICATED.")
    print("  Observe:       set do_bit=0, write U, read Y_obs (always 0xFF)")
    print("  Intervene:     set do_bit=1, write U + do_value, read Y_obs (= do_value XOR U)")
    print("  Counterfactual: read Y_cf (= do_value XOR U, regardless of do_bit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
