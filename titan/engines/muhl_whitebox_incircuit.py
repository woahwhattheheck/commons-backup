#!/usr/bin/env python3
"""muhl_whitebox_incircuit.py — THE WHITE BOX, OFF THE HOST: a universal netlist evaluator fabricated as gates.

The White Box (sdc_cc) runs on the host: it evaluates a gate netlist to verify it byte-exact before storing.
This fabricates that evaluator ITSELF as a circuit -- a UNIVERSAL netlist interpreter. One fixed gate netlist
that takes ANOTHER netlist (encoded as data: op/operand-a/operand-b per gate) plus its inputs, and evaluates
it. Feed it different netlist-data and it computes different functions -- a fabricated, stored, general-purpose
gate machine. Verified byte-exact against the host ripple over random netlists. The fabricator's runtime now
lives on the substrate it fabricates for (the executor is a CIRCUIT, not a host process -- exactly the spec).
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

NIN, G, NW, AW, OPB = 4, 10, 16, 4, 3     # inputs, gates, wires (0..15), addr bits, op bits
# ops: 0=NAND 1=AND 2=OR 3=XOR 4=NOT ; 5..7 = undefined -> 0

def alu(g, op, va, vb):
    res = {0: g.NOT(g.AND(va, vb)), 1: g.AND(va, vb), 2: g.OR(va, vb), 3: g.XOR(va, vb), 4: g.NOT(va)}
    out = g.C0
    for k in range(5): out = g.OR(out, g.AND(op[k], res[k]))   # op[k] = one-hot of the opcode
    return out

def build_interpreter():
    NBITS = G * (OPB + 2 * AW)
    g = CC.CircuitCompiler(NIN + NBITS); IN = g.IN
    inputs = [IN[i] for i in range(NIN)]; net = IN[NIN:]
    def onehot(bits, n):
        out = []
        for i in range(n):
            m = g.C1
            for j in range(len(bits)): m = g.AND(m, bits[j] if (i >> j) & 1 else g.NOT(bits[j]))
            out.append(m)
        return out
    def mux(sel, wires): return _or(g, [g.AND(sel[i], wires[i]) for i in range(NW)])
    wires = [g.C0, g.C1] + inputs + [g.C0] * G          # future gate slots start at 0
    p = 0
    for gi in range(G):
        opb = [net[p + b] for b in range(OPB)]; p += OPB
        ab = [net[p + b] for b in range(AW)]; p += AW
        bb = [net[p + b] for b in range(AW)]; p += AW
        op = onehot(opb, 8)[:5]                          # only opcodes 0..4 select; 5..7 -> nothing -> 0
        va = mux(onehot(ab, NW), wires); vb = mux(onehot(bb, NW), wires)
        wires[2 + NIN + gi] = alu(g, op, va, vb)
    gates, out2 = g.dce([wires[NW - 1]])                 # output = last wire
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    return run, out2[0], len(gates)

def _or(g, xs):
    a = g.C0
    for x in xs: a = g.OR(a, x)
    return a

def host_eval(netlist, inputs):
    W = [0, 1] + list(inputs) + [0] * G
    for gi, (op, a, b) in enumerate(netlist):
        va, vb = W[a], W[b]
        r = {0: 1 - (va & vb), 1: va & vb, 2: va | vb, 3: va ^ vb, 4: 1 - va}.get(op, 0)
        W[2 + NIN + gi] = r
    return W[NW - 1]

def encode(netlist):
    bits = []
    for op, a, b in netlist:
        bits += [(op >> j) & 1 for j in range(OPB)]
        bits += [(a >> j) & 1 for j in range(AW)]
        bits += [(b >> j) & 1 for j in range(AW)]
    return bits

def main():
    run, outw, ng = build_interpreter()
    print(f"\n  MUHLNICKEL WHITE BOX IN-CIRCUIT — a universal netlist evaluator fabricated as {ng:,} gates\n")
    print(f"  it evaluates ANY {G}-gate netlist over {NW} wires ({NIN} inputs), handed in as DATA.")
    rng = random.Random(3); bad = 0
    for _ in range(500):
        netlist = [(rng.randrange(8), rng.randrange(NW), rng.randrange(NW)) for _ in range(G)]
        inputs = [rng.randrange(2) for _ in range(NIN)]
        inp = inputs + encode(netlist)
        got = run(inp, 1)[outw] & 1
        if got != host_eval(netlist, inputs): bad += 1
    print(f"  byte-exact vs the host ripple over 500 random netlists x inputs: {'PASS' if bad==0 else str(bad)+' WRONG'}")
    if bad: return 1

    # demo: hand it two DIFFERENT netlists -> it computes two different functions, no re-fabrication
    def as_net(gates): return gates + [(1, 0, 0)] * (G - len(gates))   # pad with AND(0,0)=0 no-ops
    XOR3 = as_net([(3, 2, 3), (3, 6, 4)])                # w6 = x0^x1 ; w7 = w6^x2  -> but output is w15...
    # route the result to the last wire via identity ANDs
    XOR3 = as_net([(3, 2, 3), (3, 6, 4), (1, 7, 1)][:3] + [(1, 8, 1)] * 6 + [(1, 14, 1)])
    MAJ = as_net([(1, 2, 3), (1, 2, 4), (1, 3, 4)] + [(2, 6, 7)] + [(2, 10, 8)] + [(1, 11, 1)] * 4 + [(1, 14, 1)])
    for name, net in (("XOR3(x0,x1,x2)", XOR3), ("MAJ(x0,x1,x2)", MAJ)):
        okc = True
        for n in range(16):
            inputs = [(n >> i) & 1 for i in range(NIN)]
            inp = inputs + encode(net)
            if (run(inp, 1)[outw] & 1) != host_eval(net, inputs): okc = False
        print(f"    loaded netlist '{name}': gate output == host eval on all 16 input combos: {okc}")

    print(f"\n  ONE fabricated circuit; the FUNCTION is data you route in. The White Box's evaluate-and-verify")
    print(f"  step no longer runs on the host — it is a stored gate machine that runs other stored gate")
    print(f"  machines. The fabricator has moved onto the substrate. (Scale NW/G for larger netlists;")
    print(f"  bit-slice the netlist-data lane to verify thousands of candidate circuits per settle.)")
    return 0 if bad == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
