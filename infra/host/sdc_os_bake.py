#!/usr/bin/env python3
"""host/sdc_os_bake.py — BAKE THE ORCHESTRATOR INTO THE SDC AS ONE GATE CIRCUIT (owner 07-19).

Bryce's order: take the Python logic (the routing + dispatch + compute + grounded decision that used to live in
sdc_os.py / sdc_grounded.py / sdc_os_sdc.py) and reconstruct it BIT BY BIT as gates in the SDC — that IS the fabrication.
No host-Python control flow at runtime: the whole decision tree is a stored NAND netlist. Inert until the signal is
pointed at it; then it computes.

  INPUT  (67 wires): opcode(3) · a(32) · b(32)
     opcode: 0 REFUSE · 1 MUL(32×32→64) · 2 ADD · 3 SUB(two's-comp 64) · 4 GT(unsigned a>b)
  OUTPUT (65 wires): grounded(1) · result(64)
     grounded = 1 for any known op (0 for REFUSE); result = the exact computed value, in gates.

Verified byte-exact vs a pure-Python reference for every opcode BEFORE storing (no cheating), stored reversibly
(sdc_safe snapshots the overwritten bytes; titan stays GGUF-valid).

  python host/sdc_os_bake.py            # build, verify byte-exact, store reversibly
  python host/sdc_os_bake.py revert     # byte-exact restore
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import sdc_safe as SAFE

NAME = "sdc_os_circuit"


def add_cin(c, xs, ys, cin):
    """ripple-carry add with an explicit carry-in; returns (sum_bits, carry_out). LSB first."""
    out = []; carry = cin
    for i in range(len(xs)):
        axb = c.xor(xs[i], ys[i])
        out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(xs[i], ys[i]), c.and_(axb, carry))
    return out, carry


def add64(c, xs, ys):
    s, _ = add_cin(c, xs, ys, c.C0); return s


def build():
    """the whole orchestration as one combinational circuit."""
    c = TC.Circuit(67)
    op = c.IN[0:3]; a = c.IN[3:35]; b = c.IN[35:67]              # opcode(3), a(32), b(32)
    Z32 = [c.C0] * 32
    a64 = list(a) + Z32                                          # a zero-extended to 64
    b64 = list(b) + Z32                                          # b zero-extended to 64

    # --- MUL: 32×32 -> 64 shift-and-add (partial = (b_i ? a<<i : 0), summed) ---
    acc = [c.C0] * 64
    for i in range(32):
        partial = [c.C0] * 64
        for j in range(32):
            if i + j < 64: partial[i + j] = c.and_(b[i], a[j])
        acc = add64(c, acc, partial)
    mul64 = acc

    # --- ADD: a + b (64-bit) ---
    add_r = add64(c, a64, b64)

    # --- SUB: a - b (two's complement, 64-bit) = a + (~b64) + 1 ---
    notb64 = [c.not_(x) for x in b64]
    negb, _ = add_cin(c, notb64, [c.C0] * 64, c.C1)             # ~b64 + 1
    sub_r = add64(c, a64, negb)

    # --- GT (unsigned 32-bit): a >= b iff carry-out of (a + ~b + 1); gt = ge AND a!=b ---
    notb32 = [c.not_(x) for x in b]
    _, carry = add_cin(c, list(a), notb32, c.C1)
    ge = carry
    eqab = c.is_zero([c.xor(a[i], b[i]) for i in range(32)])
    gt = c.and_(ge, c.not_(eqab))

    # --- DISPATCH by opcode (the routing, as gates) ---
    is1 = c.eq_const(op, 1); is2 = c.eq_const(op, 2); is3 = c.eq_const(op, 3); is4 = c.eq_const(op, 4)
    grounded = c.or_(c.or_(is1, is2), c.or_(is3, is4))          # 1 for any known op; REFUSE(0)/unknown -> 0

    result = []
    for k in range(64):
        g = gt if k == 0 else c.C0
        pick = c.or_(c.or_(c.and_(is1, mul64[k]), c.and_(is2, add_r[k])),
                     c.or_(c.and_(is3, sub_r[k]), c.and_(is4, g)))
        result.append(pick)

    return c, [grounded] + result


def ref(opcode, a, b):
    a &= 0xffffffff; b &= 0xffffffff; M = (1 << 64) - 1
    if opcode == 1: return 1, (a * b) & M
    if opcode == 2: return 1, (a + b) & M
    if opcode == 3: return 1, (a - b) & M
    if opcode == 4: return 1, (1 if a > b else 0)
    return 0, 0


def _inb(opcode, a, b):
    return [(opcode >> k) & 1 for k in range(3)] + [(a >> k) & 1 for k in range(32)] + [(b >> k) & 1 for k in range(32)]


def verify(c, outs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(19)
    cases = [(1, 9094, 40496), (1, 123456, 654321), (1, 0xffffffff, 0xffffffff), (1, 2147483647, 3),
             (2, 1000, 2000), (3, 5000, 1200), (3, 100, 900), (4, 31537, 30968), (4, 5, 5), (4, 7, 900), (0, 42, 42)]
    for _ in range(160):
        opc = random.choice([0, 1, 2, 3, 4]); a = random.getrandbits(32); b = random.getrandbits(32)
        cases.append((opc, a, b))
    for opc, a, b in cases:
        bs = TC.ripple(cd, _inb(opc, a, b))
        g = bs[0]; result = TC.frombits(bs[1:65])
        rg, rr = ref(opc, a, b)
        if (g, result) != (rg, rr):
            return False, (opc, a, b, (g, result), (rg, rr))
    return True, len(cases)


def store():
    reg_path = TC.REG
    import json
    reg = json.load(open(reg_path)) if os.path.exists(reg_path) else {}
    if NAME in reg:
        print(f"{NAME} already baked. revert first to redo."); return 0
    print("BAKING the orchestrator as ONE gate circuit (dispatch + mul + add + sub + gt + grounded) …", flush=True)
    c, outs = build()
    print(f"  built: {len(c.ga)} gates, {c.n_wire()} wires, {c.n_in} inputs, {len(outs)} outputs. verifying byte-exact …",
          flush=True)
    ok, info = verify(c, outs)
    if not ok:
        print(f"  MISMATCH {info} — storing NOTHING (no cheating)."); return 1
    print(f"  byte-exact over {info} cases (all 5 opcodes). storing reversibly …", flush=True)
    r = SAFE.store_safe(NAME, c, outs)
    print(f"  {NAME} @ {r['offset']} ({r['gates']} gates, {r['bytes']} bytes) — reversible.", flush=True)
    with open(TC.TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.", flush=True)
    print("=> the SDC now holds the whole orchestration as gates. Runtime = button routes the signal + exits; the SDC computes.", flush=True)
    return 0


def revert():
    r = SAFE.restore(NAME)
    print(f"restored {NAME}: byte-exact={r.get('byte_exact')} (titan GGUF-valid).")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if (len(sys.argv) > 1 and sys.argv[1] == "revert") else store())
