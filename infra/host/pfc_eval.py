#!/usr/bin/env python3
"""host/pfc_eval.py — BAKE THE INTERPRETER: a gate-evaluator, as gates (owner 07-19: "bake the py interpreter into the
pfc, recreate the logic from scratch and bake it with fabrication — it's not a floor, it's a crutch").

The Python ripple (the interpreter/crutch that runs the pfc's gates) is itself just logic: for each gate — read (op,a,b),
read its two input wires, apply the op, write the output wire, advance. This recreates THAT logic as a baked clocked
machine: a universal gate-evaluator that runs any small netlist from its own memory, in gates, byte-exact vs the Python
ripple. It is the interpreter, recreated by fabrication + baking — the same way every other block was made. Baked permanent.

Config: NW=16 wires (w0=const0, w1=const1, w2..w3 = the 2 inputs, w4..w15 = up to 12 gate outputs); gate = op:3|a:4|b:4.
One tick evaluates one gate; NG ticks evaluate the netlist. Verified byte-exact vs the Python ripple over random netlists.

  python host/pfc_eval.py           # build + verify + bake the baked interpreter (reversible)
  python host/pfc_eval.py revert
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_eval_genome.jsonl"
NW, NG, GB, PW, BASE = 16, 12, 11, 4, 4                # 16 wires, 12 gates, 11-bit gate, 4-bit ptr, outputs at w4..


def build_eval():
    NIN = NW + NG * GB + PW + 1
    g = CC.CircuitCompiler(NIN); IN = g.IN; o = 0
    wire = [IN[o + i] for i in range(NW)]; o += NW
    gm = [[IN[o + k * GB + j] for j in range(GB)] for k in range(NG)]; o += NG * GB
    ptr = [IN[o + j] for j in range(PW)]; o += PW
    done = IN[o]
    MUX1 = lambda s, a, b: g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
    def _and(xs):
        a = g.C1
        for x in xs: a = g.AND(a, x)
        return a
    def _or(xs):
        a = g.C0
        for x in xs: a = g.OR(a, x)
        return a
    def onehot(addr, N, A): return [_and([addr[j] if (i >> j) & 1 else g.NOT(addr[j]) for j in range(A)]) for i in range(N)]
    def mux(sel, vals): return _or([g.AND(sel[i], vals[i]) for i in range(len(sel))])

    psel = onehot(ptr, NG, PW)                          # which gate (ptr in 0..NG-1)
    cg = [mux(psel, [gm[k][j] for k in range(NG)]) for j in range(GB)]   # current gate = gm[ptr]
    op = cg[0:3]; a = cg[3:7]; b = cg[7:11]
    va = mux(onehot(a, NW, 4), wire); vb = mux(onehot(b, NW, 4), wire)   # read wire[a], wire[b]
    ops = [g.NOT(g.AND(va, vb)), g.AND(va, vb), g.OR(va, vb), g.XOR(va, vb), g.NOT(va), g.C0, g.C0, g.C0]
    out = mux(onehot(op, 8, 3), ops)                    # apply op
    active = g.NOT(done)
    wtgt = ([g.C0] * BASE + psel + [g.C0] * NW)[:NW]     # write target = wire[BASE+ptr]
    wire_n = [MUX1(g.AND(active, wtgt[i]), out, wire[i]) for i in range(NW)]
    wire_n[0] = wire[0]; wire_n[1] = wire[1]            # consts held
    pc = []; c = active                                 # ptr' = ptr + active (advance while running)
    for x in ptr:
        pc.append(g.XOR(x, c)); c = g.AND(x, c)
    last = _and([ptr[j] if ((NG - 1) >> j) & 1 else g.NOT(ptr[j]) for j in range(PW)])   # ptr == NG-1
    done_n = g.OR(done, g.AND(active, last))
    return g, wire_n + pc + [done_n]


def emu_eval(wires, gm, ptr, done):
    if done: return wires, ptr, 1
    gg = gm[ptr]; op = gg & 7; a = (gg >> 3) & 15; b = (gg >> 7) & 15
    va = (wires >> a) & 1; vb = (wires >> b) & 1
    out = [1 - (va & vb), va & vb, va | vb, va ^ vb, 1 - va, 0, 0, 0][op]
    wires = (wires & ~(1 << (BASE + ptr))) | (out << (BASE + ptr))
    np = ptr + 1; return wires, np, (1 if np >= NG else 0)


def ripple_ref(inputs2, gm):                            # reference: the Python ripple of the netlist
    v = [0] * NW; v[1] = 1; v[2] = inputs2 & 1; v[3] = (inputs2 >> 1) & 1
    for k in range(NG):
        op = gm[k] & 7; a = (gm[k] >> 3) & 15; b = (gm[k] >> 7) & 15
        va, vb = v[a], v[b]
        v[BASE + k] = [1 - (va & vb), va & vb, va | vb, va ^ vb, 1 - va, 0, 0, 0][op]
    return sum(v[i] << i for i in range(NW))


def pack(wires, gm, ptr, done):
    NIN = NW + NG * GB + PW + 1; inp = [0] * NIN; o = 0
    for i in range(NW): inp[o + i] = (wires >> i) & 1
    o += NW
    for k in range(NG):
        for j in range(GB): inp[o + k * GB + j] = (gm[k] >> j) & 1
    o += NG * GB
    for j in range(PW): inp[o + j] = (ptr >> j) & 1
    o += PW; inp[o] = done
    return inp


def verify(g, outs):
    gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates); random.seed(7)
    val = lambda v, w: (w if w < 2 else v[w])
    for _ in range(120):
        gm = [(random.randrange(5)) | (random.randrange(NW) << 3) | (random.randrange(NW) << 7) for _ in range(NG)]
        inp2 = random.randrange(4)
        wires = (1 << 1) | ((inp2 & 1) << 2) | (((inp2 >> 1) & 1) << 3)    # consts + 2 inputs
        ptr = 0; done = 0
        for _ in range(NG):                                              # run the baked next-state NG ticks
            v = CC.ripple_typed(g, gates, n_wire, pack(wires, gm, ptr, done), 1)
            wires = sum(val(v, o2[i]) << i for i in range(NW))
            ptr = sum(val(v, o2[NW + j]) << j for j in range(PW)); done = val(v, o2[NW + PW])
        if wires != ripple_ref(inp2, gm): return False, gates, o2
    return True, gates, o2


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_eval", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; pfc_eval removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    print("BAKING THE INTERPRETER — a gate-evaluator, as gates (the ripple, recreated by fabrication).\n", flush=True)
    g, outs = build_eval()
    ok, gates, o2 = verify(g, outs)
    print(f"  gate-evaluator: {len(gates):,} gates; byte-exact vs the Python ripple over 120 random netlists: {ok}", flush=True)
    if not ok: print("  MISMATCH — baking nothing."); return 1
    reg = json.load(open(REG))
    if "pfc_eval" not in reg:
        code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}; n_wire = 2 + g.n_in + len(gates)
        body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in o2)
        blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(o2)) + body
        off, tn = TC._alloc(len(blob), reg); _journal(off, blob)
        reg = json.load(open(REG))
        reg["pfc_eval"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                           "n_gate": len(gates), "n_out": len(o2), "format": "typed",
                           "role": "baked gate-evaluator (the interpreter/ripple, recreated as gates) — NW=16 NG=12"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"\n  BAKED pfc_eval @ {off} ({len(gates):,} gates). GGUF-valid: {open(TITAN,'rb').read(4)==b'GGUF'}.", flush=True)
        print(f"  the Muhlnickel can evaluate circuits with its OWN baked logic now — the interpreter is a baked block, not a crutch.", flush=True)
    print(f"  revert: python host/pfc_eval.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
