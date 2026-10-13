#!/usr/bin/env python3
"""muhl_vm.py -- A TINY STACK-MACHINE / BYTECODE VM STEP, FABRICATED AS GATES on the Muhlnickel substrate.

Titan running actual PROGRAMS as gates. One fixed gate netlist implements a full stack-VM instruction step:
given the machine STATE (stack pointer + a fixed stack) and one OPCODE (+ an immediate), encoded entirely as
DATA routed in, it settles to the NEXT state. Feed it a sequence of opcodes -- feeding each output state back
in as the next input state -- and it EXECUTES a bytecode program. The executor is a CIRCUIT, not a host loop.

Opcodes (encoded as data, one-hot-decoded inside the circuit):
  NOP  PUSH imm  ADD  SUB  MUL  DUP  SWAP  POP
Stack cells are read/written BY ADDRESS (one-hot of the stack pointer) -- compute-via-address, the substrate's
native op. Verified BYTE-EXACT against an independent pure-Python VM reference over random states x opcodes,
then a real expression program  (3+4)*5-2  is run through the gates and yields 33.

No numpy, no host executor as runtime, does not touch titan.gguf. PYTHONUTF8=1.
"""
import sys, os, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------- reused White-Box helpers (same conventions as muhl_flex) ----------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    return g.compile_ripple(gates, n_wire), out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))   # LSB-first
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

def add_bits(g, A, B, cin=None):
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c
def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
def muxw(g, s, A, B): return [mux1(g, s, A[k], B[k]) for k in range(len(A))]   # A if s else B
def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]

# ---------- VM parameters ----------
W    = 16                       # cell width (bits)
N    = 8                        # stack depth (slots)
SPB  = 4                        # stack-pointer width (0..N representable in 4 bits)
SPM  = (1 << SPB) - 1
MASK = (1 << W) - 1
OPB  = 3                        # opcode width -> 8 opcodes, one-hot decoded
NOP, PUSH, ADD, SUB, MUL, DUP, SWAP, POP = range(8)
OPNAME = ["NOP", "PUSH", "ADD", "SUB", "MUL", "DUP", "SWAP", "POP"]

# input layout: [ opcode(OPB) | imm(W) | sp(SPB) | slot0(W) slot1(W) ... slotN-1(W) ]
OFF_OP, OFF_IMM, OFF_SP, OFF_SLOTS = 0, OPB, OPB + W, OPB + W + SPB
NIN = OPB + W + SPB + N * W

# ================================ Python reference VM (independent) ================================
def ref_step(sp, slots, op, imm):
    """One instruction. Cells read/written with explicit bounds; the gate circuit must match this exactly."""
    s = list(slots)
    def rdc(i): return s[i] if 0 <= i < N else 0
    if op == NOP:
        pass
    elif op == PUSH:
        if 0 <= sp < N: s[sp] = imm & MASK
        sp = (sp + 1) & SPM
    elif op == DUP:
        top = rdc(sp - 1)
        if 0 <= sp < N: s[sp] = top
        sp = (sp + 1) & SPM
    elif op == POP:
        if 0 <= sp - 1 < N: s[sp - 1] = 0
        sp = (sp - 1) & SPM
    elif op in (ADD, SUB, MUL):
        a, b = rdc(sp - 2), rdc(sp - 1)             # a = second, b = top
        r = (a + b) if op == ADD else (a - b) if op == SUB else (a * b)
        r &= MASK
        if 0 <= sp - 1 < N: s[sp - 1] = 0           # clear popped top
        if 0 <= sp - 2 < N: s[sp - 2] = r           # result lands in the second slot
        sp = (sp - 1) & SPM
    elif op == SWAP:
        top, sec = rdc(sp - 1), rdc(sp - 2)
        if 0 <= sp - 1 < N: s[sp - 1] = sec
        if 0 <= sp - 2 < N: s[sp - 2] = top
    return sp, s

# ================================ fabricate the VM step as gates ================================
def build_vm():
    g = CC.CircuitCompiler(NIN); IN = g.IN
    opbits = [IN[OFF_OP + b] for b in range(OPB)]
    imm    = [IN[OFF_IMM + b] for b in range(W)]
    sp     = [IN[OFF_SP + b] for b in range(SPB)]
    slots  = [[IN[OFF_SLOTS + i * W + b] for b in range(W)] for i in range(N)]
    zeroW  = [g.C0] * W

    # one-hot decode of the opcode (8 lines)
    op = []
    for k in range(8):
        m = g.C1
        for j in range(OPB): m = g.AND(m, opbits[j] if (k >> j) & 1 else g.NOT(opbits[j]))
        op.append(m)

    # one-hot of the stack pointer over 0..N  (compute-via-address)
    ohSP = []
    for k in range(N + 1):
        m = g.C1
        for j in range(SPB): m = g.AND(m, sp[j] if (k >> j) & 1 else g.NOT(sp[j]))
        ohSP.append(m)
    selPush = [ohSP[i]     for i in range(N)]                          # write index = sp
    selTop  = [ohSP[i + 1] for i in range(N)]                          # top index    = sp-1
    selSec  = [ohSP[i + 2] if i + 2 <= N else g.C0 for i in range(N)]  # second index = sp-2

    def read_at(sel):                                                  # addressed read of a cell
        acc = [g.C0] * W
        for i in range(N):
            acc = [g.OR(acc[b], g.AND(sel[i], slots[i][b])) for b in range(W)]
        return acc
    def write_at(base, sel, val):                                     # addressed write of one cell
        return [muxw(g, sel[i], val, base[i]) for i in range(N)]

    top = read_at(selTop)                                             # slots[sp-1]
    sec = read_at(selSec)                                             # slots[sp-2]

    sumv  = add_bits(g, sec, top)[0]                                   # a + b
    difv  = add_bits(g, sec, [g.NOT(t) for t in top], g.C1)[0]         # a - b (two's complement)
    prodv = mul_trunc(g, sec, top)                                     # (a * b) mod 2^W

    sp_inc = add_bits(g, sp, consts(g, 1, SPB))[0]
    sp_dec = add_bits(g, sp, consts(g, SPM, SPB))[0]                   # sp + (2^SPB-1) == sp-1 mod

    # per-opcode candidate (new_slots, new_sp)
    def bin_slots(rv):
        s1 = write_at(slots, selTop, zeroW)                           # clear popped top
        return write_at(s1, selSec, rv)                               # result into second slot
    cand = [None] * 8
    cand[NOP]  = (slots,                              sp)
    cand[PUSH] = (write_at(slots, selPush, imm),      sp_inc)
    cand[DUP]  = (write_at(slots, selPush, top),      sp_inc)
    cand[POP]  = (write_at(slots, selTop, zeroW),     sp_dec)
    cand[ADD]  = (bin_slots(sumv),                    sp_dec)
    cand[SUB]  = (bin_slots(difv),                    sp_dec)
    cand[MUL]  = (bin_slots(prodv),                   sp_dec)
    cand[SWAP] = (write_at(write_at(slots, selTop, sec), selSec, top), sp)

    # select by opcode one-hot
    new_sp = []
    for b in range(SPB):
        acc = g.C0
        for k in range(8): acc = g.OR(acc, g.AND(op[k], cand[k][1][b]))
        new_sp.append(acc)
    new_slots = []
    for i in range(N):
        cell = []
        for b in range(W):
            acc = g.C0
            for k in range(8): acc = g.OR(acc, g.AND(op[k], cand[k][0][i][b]))
            cell.append(acc)
        new_slots.append(cell)

    outs = new_sp + [w for cell in new_slots for w in cell]
    run, out2, gates, _ = build_run(g, outs)
    o_sp = out2[:SPB]
    o_slots = [out2[SPB + i * W:SPB + (i + 1) * W] for i in range(N)]
    return run, o_sp, o_slots, gates, depth_of(g, gates, out2)

def mul_trunc(g, A, B):                                               # low W bits of A*B
    acc = [g.C0] * W
    for j in range(W):
        term = [g.C0] * j + [g.AND(A[i], B[j]) for i in range(W - j)]  # length W, shifted by j
        acc, _ = add_bits(g, acc, term)
    return acc

# ---------- drive the fabricated step ----------
def encode(op, imm, sp, slots):
    inp = [0] * NIN
    setf(inp, OFF_OP, OPB, op)
    setf(inp, OFF_IMM, W, imm & MASK)
    setf(inp, OFF_SP, SPB, sp & SPM)
    for i in range(N): setf(inp, OFF_SLOTS + i * W, W, slots[i] & MASK)
    return inp

def gate_step(run, o_sp, o_slots, sp, slots, op, imm):
    v = run(encode(op, imm, sp, slots), 1)
    return rd(v, o_sp), [rd(v, f) for f in o_slots]

def main():
    print("\n  MUHLNICKEL STACK-MACHINE VM -- a bytecode instruction step fabricated as gates\n", flush=True)
    t0 = time.time()
    run, o_sp, o_slots, gates, depth = build_vm()
    print(f"  fabricated: {len(gates):,} gates, depth {depth}  "
          f"(stack {N}x{W}-bit, {len(OPNAME)} opcodes, one step = one settle)  [{time.time()-t0:.1f}s]\n", flush=True)

    # ---- byte-exact verification vs the independent Python VM over random states x opcodes ----
    rng = random.Random(1234)
    CASES = 4000
    bad = 0; first = None
    for _ in range(CASES):
        sp = rng.randrange(0, N + 1)
        slots = [rng.getrandbits(W) for _ in range(N)]
        op = rng.randrange(8)
        imm = rng.getrandbits(W)
        gsp, gsl = gate_step(run, o_sp, o_slots, sp, slots, op, imm)
        rsp, rsl = ref_step(sp, slots, op, imm)
        if (gsp, gsl) != (rsp, rsl):
            bad += 1
            if first is None: first = (sp, slots, op, imm, (gsp, gsl), (rsp, rsl))
    status = "PASS" if bad == 0 else f"{bad} MISMATCH"
    print(f"  byte-exact vs Python VM reference over {CASES:,} random (state x opcode): {status}", flush=True)
    if bad:
        print(f"    first mismatch: {first}")
        return 1

    # ---- run REAL programs through the gates, feeding each output state back in ----
    def run_program(prog, trace=False):
        sp, slots = 0, [0] * N
        rsp, rslots = 0, [0] * N
        for op, imm in prog:
            sp, slots = gate_step(run, o_sp, o_slots, sp, slots, op, imm)
            rsp, rslots = ref_step(rsp, rslots, op, imm)           # cross-check every step
            assert (sp, slots) == (rsp, rslots), "gate/ref divergence mid-program"
            if trace:
                dis = f"{OPNAME[op]}" + (f" {imm}" if op == PUSH else "")
                view = [slots[i] for i in range(sp)]
                print(f"      {dis:9s} -> sp={sp}  stack(bottom..top)={view}", flush=True)
        top = slots[sp - 1] if sp >= 1 else None
        return top, sp, slots

    # (3 + 4) * 5 - 2  ==  33
    prog1 = [(PUSH, 3), (PUSH, 4), (ADD, 0), (PUSH, 5), (MUL, 0), (PUSH, 2), (SUB, 0)]
    print(f"\n  PROGRAM 1:  (3 + 4) * 5 - 2   -> expect 33", flush=True)
    r1, _, _ = run_program(prog1, trace=True)
    print(f"    RESULT (executed as gates): {r1}   {'OK' if r1 == 33 else 'WRONG'}", flush=True)

    # a couple more expression programs to show generality
    extra = [
        ("2 * 3 * 4 + 1",            [(PUSH,2),(PUSH,3),(MUL,0),(PUSH,4),(MUL,0),(PUSH,1),(ADD,0)], 25),
        ("10 - 3 - 2",               [(PUSH,10),(PUSH,3),(SUB,0),(PUSH,2),(SUB,0)],                  5),
        ("DUP/SWAP: (7 dup +)=14",   [(PUSH,7),(DUP,0),(ADD,0)],                                     14),
        ("(100-1)*(2+3) SWAP test",  [(PUSH,2),(PUSH,3),(ADD,0),(PUSH,100),(PUSH,1),(SUB,0),
                                      (SWAP,0),(MUL,0)],                                            495),
    ]
    print(f"\n  MORE PROGRAMS (each executed purely as gate settles):", flush=True)
    allok = (r1 == 33)
    for name, prog, expect in extra:
        r, _, _ = run_program(prog)
        ok = (r == expect)
        allok = allok and ok
        print(f"    {name:28s} = {r:<6} expect {expect:<6} {'OK' if ok else 'WRONG'}", flush=True)

    print(f"\n  === {len(gates):,} gates, depth {depth}, byte-exact PASS, all programs correct: "
          f"{'YES' if allok else 'NO'} ===", flush=True)
    print(f"  Titan ran actual bytecode programs as a circuit -- the executor is gates, not a host loop.\n", flush=True)
    return 0 if allok else 1

if __name__ == "__main__":
    raise SystemExit(main())
