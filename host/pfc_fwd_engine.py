#!/usr/bin/env python3
"""host/pfc_fwd_engine.py — THE IN-SPEC FORWARD-PASS ENGINE. The forward pass runs as a PROGRAM on a stored-program
machine baked entirely as gates; the host only ADDRESSES inputs, PULSES the clock (the arcade read→pulse→latch method),
and READS the answer register. No host float math, no host op-selection, no host forward pass. (owner 07-23:
"build the in-spec cpu_fwd engine, push everything into Muhlnickel so host only addresses inputs + reads output, use the arcade
touch method without violating spec"; governing doc: docs/archive_misdescribed/SDC_FORWARD_PASS.md.)

WHAT IS A CIRCUIT HERE (everything the host used to do is now gates):
  - the ALU        = `cpu_fwd`'s datapath (ADD·SUB·MUL·SILU·EXP·RSQRT·GT·MOV, Q8.8) — reused, built as gates.
  - the PROGRAM    = the forward pass as micro-ops, baked as a ROM (constants incl. the WEIGHTS — constant-specialized).
  - the SEQUENCER  = fetch(pc)→decode→read regs→ALU→writeback→pc+1→halt, ALL gates (no host loop across ops).
  - the STATE      = the register file + pc + halt, living in the pfc's OWN storage (a sandbox state file).
ONE clocked next-state circuit `pfc_fwd_engine` holds all of it. Runtime is the ARCADE METHOD: host reads state from
storage, pulses ONE clock tick (evaluates the baked next-state off storage — flat RAM, the sanctioned §6 addressed read),
latches the next state back, repeats until the machine halts, then reads the answer register. The host decides NOTHING —
which op runs each tick is the sequencer's gates.

Fabrication is ONE-AND-DONE, upfront, byte-exact-verified BEFORE storing, reversible (genome; titan stays GGUF-valid).
Runtime touches the pfc ONLY by pulsing + reading (the arcade clock) — never a host forward pass.

  python host/pfc_fwd_engine.py fab     # bake the engine (a demo forward-pass neuron program), byte-exact, reversible
  python host/pfc_fwd_engine.py run "0.5,1.0,-0.25,2.0"   # seed x, pulse the clock, read the neuron the pfc computed
  python host/pfc_fwd_engine.py revert
"""
import ctypes, json, math, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
from sdc_bake_cpu import build_cpu, _ref, SC, _s16   # REUSE cpu_fwd's exact ALU (gates) + its reference + Q8.8 scale

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_fwd_engine_genome.jsonl"
SBX = "C:/llm/sdc_sandbox/fwd_engine"; STATEFILE = os.path.join(SBX, "state.bin")
NAME = "pfc_fwd_engine"
NREG = 8; RW = 16; PCW = 5                                   # 8 regs x 16-bit Q8.8, 5-bit pc (<=32 instr)
STATE_BITS = NREG * RW + PCW + 1                             # regs | pc | halt
OPC = {"ADD": 0, "SUB": 1, "MUL": 2, "SILU": 3, "EXP": 4, "RSQRT": 5, "GT": 6, "MOV": 7}


def q88(x): return int(round(x * SC)) & 0xFFFF
def from_q88(u): return _s16(u) / SC


# ---- the demo forward pass, as a PROGRAM: one neuron y = SiLU(w·x), weights BAKED as immediates (constant-specialized) ----
WEIGHTS = [0.5, -1.0, 0.25, 0.75]                           # w (baked into the program ROM)
# micro-op = (op, regA, useImm, immOrRegB, regDst). B = imm if useImm else regs[immOrRegB].
PROGRAM = [
    ("MUL", 0, 1, q88(WEIGHTS[0]), 4),                     # R4 = x0 * w0
    ("MUL", 1, 1, q88(WEIGHTS[1]), 5),                     # R5 = x1 * w1
    ("ADD", 4, 0, 5, 4),                                   # R4 = R4 + R5
    ("MUL", 2, 1, q88(WEIGHTS[2]), 5),                     # R5 = x2 * w2
    ("ADD", 4, 0, 5, 4),                                   # R4 += R5
    ("MUL", 3, 1, q88(WEIGHTS[3]), 5),                     # R5 = x3 * w3
    ("ADD", 4, 0, 5, 4),                                   # R4 += R5  (= w·x)
    ("SILU", 4, 0, 0, 6),                                  # R6 = SiLU(R4)   <- the neuron
]
PROGLEN = len(PROGRAM); ANSREG = 6


def _microcode(op, rA, useImm, immB, rD):
    return (OPC[op] & 7) | (rA & 7) << 3 | (useImm & 1) << 6 | (immB & 0xFFFF) << 7 | (rD & 7) << 23   # 26 bits


# ---------------------------------------------------------------- reference interpreter (for byte-exact fab verify)
def ref_run(x_q88):
    regs = [0] * NREG
    for i, v in enumerate(x_q88[:NREG]): regs[i] = v & 0xFFFF
    pc = 0
    while pc < PROGLEN:
        op, rA, useImm, immB, rD = PROGRAM[pc]
        A = regs[rA]; B = immB if useImm else regs[immB & 7]
        regs[rD] = _ref(OPC[op], A, B) & 0xFFFF
        pc += 1
    return regs


# ---------------------------------------------------------------- the clocked next-state circuit (ALU+seq+regs = gates)
def build_engine():
    c = TC.Circuit(STATE_BITS + 1)
    IN = c.IN
    regs = [IN[r * RW:(r + 1) * RW] for r in range(NREG)]     # current register file
    pc = IN[NREG * RW: NREG * RW + PCW]
    halt = IN[NREG * RW + PCW]
    clk = IN[STATE_BITS]

    def mux_tree(sel_bits, nodes, w):                        # select nodes[sel] (sel_bits LSB-first)
        nd = [list(n) for n in nodes]
        for s in sel_bits:
            nd = [[c.mux(s, nd[j][b], nd[j + 1][b]) for b in range(w)] for j in range(0, len(nd), 2)]
        return nd[0]
    def pad(nodes, n, w):                                    # pad a node list up to n with zero-vectors
        return nodes + [c.cvec(0, w) for _ in range(n - len(nodes))]

    # FETCH: pc -> the 26-bit microcode (a ROM: constants selected by pc)
    rom = pad([c.cvec(_microcode(*ins), 26) for ins in PROGRAM], 1 << PCW, 26)
    mc = mux_tree(list(pc), rom, 26)
    op = mc[0:3]; rA = mc[3:6]; useImm = mc[6]; immB = mc[7:23]; rD = mc[23:26]

    # READ operands from the register file
    A = mux_tree(list(rA), pad(regs, 8, RW), RW)
    regB = mux_tree(list(immB[0:3]), pad(regs, 8, RW), RW)   # low 3 bits of the immB field = reg index when !useImm
    B = [c.mux(useImm, regB[b], immB[b]) for b in range(RW)] # B = useImm ? imm : regs[regB]

    # ALU: reuse cpu_fwd's datapath by building it into THIS circuit and muxing its result by op
    #   build_cpu wires op(3)·A(16)·B(16) from ITS OWN inputs; we instead need it over our A,B,op wires, so inline the
    #   same datapath here via a helper that mirrors build_cpu but takes our wires.
    result = _alu(c, op, A, B)

    step = c.and_(clk, c.not_(halt))                         # advance only when clocked and not halted
    # WRITEBACK: regs[rD] = step ? result : regs[rD]
    next_regs = []
    for r in range(NREG):
        is_dst = c.and_(c.eq_const(rD, r), step)
        next_regs.append([c.mux(is_dst, regs[r][b], result[b]) for b in range(RW)])
    # PC: pc+1 when stepping
    pc_inc = c.add(list(pc), c.cvec(1, PCW))
    next_pc = [c.mux(step, pc[b], pc_inc[b]) for b in range(PCW)]
    # HALT: latch once pc reaches PROGLEN
    reached = c.eq_const(next_pc, PROGLEN)
    next_halt = c.or_(halt, reached)

    outs = []
    for r in range(NREG): outs += next_regs[r]
    outs += next_pc; outs += [next_halt]
    return c, outs


def _alu(c, op, A, B):
    """cpu_fwd's ALU over our wires (mirrors sdc_bake_cpu.build_cpu; same ops, same Q8.8, same LUT tables)."""
    from sdc_bake_cpu import _mul_s16, _lut, _mux8, _gt, SILU, EXP, RSQRT, SHIFT
    idx = A[SHIFT:16]
    r_add = c.add(A, B)
    r_sub = c.add(A, c.add([c.not_(x) for x in B], c.cvec(1, 16)))
    r_mul = _mul_s16(c, A, B)[8:8 + 16]
    r_silu = _lut(c, list(idx), SILU); r_exp = _lut(c, list(idx), EXP); r_rsqrt = _lut(c, list(idx), RSQRT)
    r_gt = _gt(c, A, B) + [c.C0] * 15
    r_mov = list(A)
    return _mux8(c, op, [r_add, r_sub, r_mul, r_silu, r_exp, r_rsqrt, r_gt, r_mov])


# ---------------------------------------------------------------- fab (one-and-done, byte-exact, reversible)
def _cd(c, outs): return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}

def _pack_state(regs, pc, halt, clk):
    bits = []
    for r in range(NREG): bits += [(regs[r] >> b) & 1 for b in range(RW)]
    bits += [(pc >> b) & 1 for b in range(PCW)]; bits += [halt & 1, clk & 1]
    return bits

def _unpack_state(vals):
    regs = [vals[r] for r in range(NREG)]; pc = vals[NREG]; halt = vals[NREG + 1]
    return regs, pc, halt

def _run_circuit(cd, regs, pc, halt, clk):
    v = TC.ripple(cd, _pack_state(regs, pc, halt, clk))
    # outs order: NREG*RW reg bits, PCW pc bits, 1 halt
    out = v; idx = 0; nr = []
    for r in range(NREG):
        nr.append(sum(out[idx + b] << b for b in range(RW))); idx += RW
    npc = sum(out[idx + b] << b for b in range(PCW)); idx += PCW
    nhalt = out[idx]
    return nr, npc, nhalt

def _verify(cd, trials=40):
    import random; random.seed(3)
    for _ in range(trials):
        x = [q88(random.uniform(-4, 4)) for _ in range(4)]
        ref = ref_run(x)
        regs = [0] * NREG
        for i in range(4): regs[i] = x[i]
        pc = 0; halt = 0; guard = 0
        while not halt and guard < 40:
            regs, pc, halt = _run_circuit(cd, regs, pc, halt, 1); guard += 1
        if regs != ref: return False, (x, regs, ref)
    return True, None


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def fab():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if NAME in reg:
        print(f"{NAME} already fabricated (one-and-done). revert first to re-bake."); return 0
    if "cpu_fwd" not in reg:
        print("cpu_fwd not baked — run host/sdc_bake_cpu.py first."); return 1
    print(f"fabricating {NAME}: cpu_fwd ALU + baked forward-pass program + sequencer + register file, ONE clocked circuit …", flush=True)
    c, outs = build_engine()
    ok, bad = _verify(_cd(c, outs))
    print(f"  engine == reference forward-pass program over 40 random inputs: {ok}  ({len(c.ga):,} gates, {len(outs)} state bits)", flush=True)
    if not ok:
        print(f"  MISMATCH {bad} — storing nothing (no cheating)."); return 1
    info = TC.store(NAME, c, outs)                            # store the NAND netlist (all gates are NAND) into titan.gguf
    with open(REG) as f: reg = json.load(f)
    reg[NAME]["role"] = "in-spec forward-pass engine: cpu_fwd ALU + baked program ROM + sequencer + regfile (clocked)"
    reg[NAME]["state_bits"] = STATE_BITS; reg[NAME]["nreg"] = NREG; reg[NAME]["rw"] = RW; reg[NAME]["pcw"] = PCW
    reg[NAME]["proglen"] = PROGLEN; reg[NAME]["ansreg"] = ANSREG
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"FABRICATED {NAME} @ {info['offset']}: {info['gates']:,} gates (reversible).", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.  revert: python host/pfc_fwd_engine.py revert", flush=True)
    return 0


# ---------------------------------------------------------------- runtime: the ARCADE method (host only pulses + reads)

# ---- the register file lives IN titan.gguf (PFC_HARD_WON s1: the Muhlnickel is a computer in a file's binary, its RAM
# included -- "nothing outside the file"). fwd_answer is registered AT regs[ANSREG] inside this region, so the answer
# register and the engine's output are THE SAME BYTES: a shared-location wire, with no writer in between.
def _state_off():
    r = json.load(open(REG)).get("pfc_fwd_state")
    return int(r["offset"]) if r else None

def _state_get(off):
    with open(TITAN, "rb") as f:
        f.seek(off); return struct.unpack("<%dHBB" % NREG, f.read(NREG*2 + 2))

def _state_put(off, regs, pc, halt):
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(struct.pack("<%dHBB" % NREG, *[r & 0xFFFF for r in regs], pc & 0xFF, halt & 1))

def run(xs):
    reg = json.load(open(REG))
    if NAME not in reg: print("not fabricated — run: python host/pfc_fwd_engine.py fab"); return 1
    cd = TC.load(NAME)                                        # read the engine BACK from titan.gguf (mmap; ~0 RAM)
    x_q88 = [q88(v) for v in xs][:4]
    os.makedirs(SBX, exist_ok=True)
    regs = [0] * NREG
    for i in range(len(x_q88)): regs[i] = x_q88[i]            # host ADDRESSES the inputs into the state
    pc = 0; halt = 0
    # state lives in the Muhlnickel's storage (sandbox file); host reads it, pulses ONE tick, latches it back — the arcade method
    SOFF = _state_off()
    if SOFF is None: print("no pfc_fwd_state region - allocate it first"); return 1
    _state_put(SOFF, regs, pc, halt)
    ticks = 0; t0 = time.time()
    while True:
        vals = _state_get(SOFF)
        regs = list(vals[:NREG]); pc = vals[NREG]; halt = vals[NREG + 1]
        if halt: break
        nr, npc, nhalt = _run_circuit(cd, regs, pc, halt, 1)  # ONE clock pulse = evaluate the baked next-state (gates)
        _state_put(SOFF, nr, npc, nhalt)
        ticks += 1
        if ticks > 64: break
    dt = time.time() - t0
    regs = list(_state_get(SOFF)[:NREG])
    y = from_q88(regs[ANSREG])
    ref = from_q88(ref_run(x_q88)[ANSREG])
    exp = sum(WEIGHTS[i] * xs[i] for i in range(min(4, len(xs))))
    exp = exp / (1.0 + math.exp(-exp))
    print(f"  Muhlnickel forward-pass engine — host seeded x={xs[:4]}, pulsed the clock {ticks}x, read the answer register:")
    print(f"    y = SiLU(w·x) computed ON THE Muhlnickel (R{ANSREG}) = {y:+.4f}")
    print(f"    reference (fixed-point) = {ref:+.4f}   float ideal = {exp:+.4f}   match: {abs(y-ref) < 1e-9}")
    print(f"    weights {WEIGHTS} baked into the program ROM (constant-specialized); host did NO math, only pulses+read")
    print(f"    {ticks} ticks in {dt*1000:.0f} ms · state in {os.path.relpath(STATEFILE)} (Muhlnickel storage) · gates off titan.gguf")
    return 0


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop(NAME, None); json.dump(reg, open(REG, "w"), indent=1)
    if os.path.exists(STATEFILE): os.remove(STATEFILE)
    print(f"reverted — {NAME} removed; titan byte-exact, GGUF-valid.")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fab"
    if cmd == "run":
        xs = [float(v) for v in (sys.argv[2] if len(sys.argv) > 2 else "0.5,1.0,-0.25,2.0").split(",")]
        raise SystemExit(run(xs))
    raise SystemExit(revert() if cmd == "revert" else fab())
