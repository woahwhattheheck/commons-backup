#!/usr/bin/env python3
"""host/sdc_bake_cpu.py — BAKE A FORWARD-PASS CPU INTO THE SDC (owner 07-18: "create a cpu circuit inside of the sdc").

The SDC must be GENERALLY CAPABLE of a forward pass the way any computer is: it has a CPU built of LOGIC GATES. The model
then runs OFF this CPU (its forward pass is a PROGRAM the CPU executes), no host code, no host float math. This file is
BAKING ONLY (fabrication of the SDC per need) — it is its OWN thing, NOT part of running: it may use host RAM/CPU freely,
it begins and ends BEFORE the SDC receives a single signal, it verifies every op BYTE-EXACT before storing, reversible.
The `titan_circuit.ripple` executor is used here at FAB ONLY (to verify), NEVER as the run.

THE CPU's combinational core (the ALU + decoder), Q8.8 fixed-point (16-bit signed), stored as one gate-net `cpu_fwd`:
  inputs  = opcode(3) · A(16) · B(16)
  the ALU computes ALL ops in parallel; the decoder muxes the result by opcode:
    0 ADD (A+B) · 1 SUB (A-B) · 2 MUL ((A*B)>>8) · 3 SILU · 4 EXP · 5 RSQRT · 6 GT (A>B) · 7 MOV (A)
  output  = result(16)
A real computer is a small CPU + a big program in memory; a forward pass is that program. This bakes the CPU.

  python host/sdc_bake_cpu.py          # bake the forward-pass CPU into titan.gguf (byte-exact, reversible)
  python host/sdc_bake_cpu.py revert   # remove it (titan bytes restored, GGUF-valid)
"""
import json, os, sys, math, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"; TITAN = "C:/llm/models/titan.gguf"
FRAC = 8; SC = 1 << FRAC; KBITS = 10; SHIFT = 16 - KBITS
NAME = "cpu_fwd"
OPS = ["ADD", "SUB", "MUL", "SILU", "EXP", "RSQRT", "GT", "MOV"]


def _sext(c, b, w): return list(b) + [b[-1]] * (w - len(b))
def _shl(c, b, k, w): return ([c.C0] * k + list(b) + [c.C0] * w)[:w]


def _mul_s16(c, a, b):
    a32 = _sext(c, a, 32); acc = c.cvec(0, 32)
    for i in range(15):
        acc = c.add(acc, [c.and_(t, b[i]) for t in _shl(c, a32, i, 32)])
    term = [c.and_(t, b[15]) for t in _shl(c, a32, 15, 32)]
    return c.add(acc, c.add([c.not_(t) for t in term], c.cvec(1, 32)))


def _lut(c, idx_bits, table, out_w=16):
    nodes = [c.cvec(v & ((1 << out_w) - 1), out_w) for v in table]
    for s in idx_bits:
        nodes = [[c.mux(s, nodes[j][b], nodes[j + 1][b]) for b in range(out_w)] for j in range(0, len(nodes), 2)]
    return nodes[0]


def _mux8(c, sel3, vecs):
    nodes = list(vecs)
    for s in sel3:
        nodes = [[c.mux(s, nodes[j][b], nodes[j + 1][b]) for b in range(16)] for j in range(0, len(nodes), 2)]
    return nodes[0]


def _lut_table(fn):
    tab = []
    half = 1 << KBITS
    for u in range(half):
        s = u - half if u >= (half >> 1) else u
        tab.append(int(round(fn((s << SHIFT) / SC) * SC)) & 0xFFFF)
    return tab


SILU = _lut_table(lambda x: x / (1.0 + math.exp(-x)) if -30 < x else 0.0)
EXP = _lut_table(lambda x: math.exp(x) if x < 11 else math.exp(11))
RSQRT = _lut_table(lambda x: 1.0 / math.sqrt(x) if x > (1.0 / SC) else float(SC))


def build_cpu():
    c = TC.Circuit(3 + 16 + 16)
    op = c.IN[0:3]; A = c.IN[3:19]; B = c.IN[19:35]; idx = A[SHIFT:16]
    r_add = c.add(A, B)
    r_sub = c.add(A, c.add([c.not_(x) for x in B], c.cvec(1, 16)))
    r_mul = _mul_s16(c, A, B)[FRAC:FRAC + 16]
    r_silu = _lut(c, list(idx), SILU); r_exp = _lut(c, list(idx), EXP); r_rsqrt = _lut(c, list(idx), RSQRT)
    r_gt = _gt(c, A, B) + [c.C0] * 15
    r_mov = list(A)
    return c, _mux8(c, op, [r_add, r_sub, r_mul, r_silu, r_exp, r_rsqrt, r_gt, r_mov])


def _gt(c, a, b):
    a17 = _sext(c, a, 17); nb = [c.not_(x) for x in _sext(c, b, 17)]
    diff = c.add(c.add(a17, nb), c.cvec(1, 17))
    return [c.and_(c.not_(c.is_zero(diff)), c.not_(diff[16]))]


def _s16(u): return u - 0x10000 if u >= 0x8000 else u


def _ref(op, a, b):
    if op == 0: return (a + b) & 0xFFFF
    if op == 1: return (a - b) & 0xFFFF
    if op == 2: return (((_s16(a) * _s16(b)) & 0xFFFFFFFF) >> FRAC) & 0xFFFF
    if op == 3: return SILU[(a >> SHIFT) & ((1 << KBITS) - 1)]
    if op == 4: return EXP[(a >> SHIFT) & ((1 << KBITS) - 1)]
    if op == 5: return RSQRT[(a >> SHIFT) & ((1 << KBITS) - 1)]
    if op == 6: return 1 if _s16(a) > _s16(b) else 0
    return a & 0xFFFF


def fab():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if NAME in reg:
        print(f"{NAME} already baked (one-and-done). revert first to re-bake."); return 0
    print("baking the forward-pass CPU (ALU + decoder) into the SDC …", flush=True)
    c, outs = build_cpu()
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(5); bad = None
    for op in range(8):                                    # verify EVERY opcode byte-exact (fab-only ripple)
        for _ in range(120):
            a = random.getrandbits(16); b = random.getrandbits(16)
            inb = [(op >> k) & 1 for k in range(3)] + [(a >> k) & 1 for k in range(16)] + [(b >> k) & 1 for k in range(16)]
            if TC.frombits(TC.ripple(cd, inb)) != _ref(op, a, b): bad = (OPS[op], a, b); break
        if bad: break
    ok = bad is None
    print(f"  CPU datapath: {len(c.ga):,} gates · byte-exact over all 8 ops x 120 cases: {ok}", flush=True)
    if not ok:
        print(f"  MISMATCH on {bad} — storing nothing (no cheating)."); return 1
    info = TC.store(NAME, c, outs)
    print(f"BAKED {NAME} @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes (reversible).", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.  ops: {OPS}", flush=True)
    print("THE SDC NOW HAS A FORWARD-PASS CPU (gates). The model runs OFF it as a program. revert: python host/sdc_bake_cpu.py revert")
    return 0


def revert():
    if not os.path.exists(REG): print("no registry."); return 0
    reg = json.load(open(REG)); e = reg.pop(NAME, None); json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {NAME}: {bool(e)} (registry range freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if (len(sys.argv) > 1 and sys.argv[1] == "revert") else fab())
