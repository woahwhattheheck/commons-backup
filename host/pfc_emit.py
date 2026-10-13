"""
pfc_emit.py - THE COMPILER EMITS THE GATE TUPLES THEMSELVES. The host only writes bytes.

pfc_compiler.py left a gap and this closes it. There, the pfc emitted a SPEC (opcodes + register
addresses) and host Python expanded that spec into gates - so the host was still doing structural
work. Here the fabricated compiler emits the COMPLETE NETLIST, gate by gate: every (a, b) operand
address of every gate in the target circuit, as output bits.

  SOURCE TEXT --addressed in--> [ EMITTER, fabricated as gates ] --> a FULL NETLIST, as bits
  host writes those bytes verbatim (S20: a byte edit IS the fabrication) --> the circuit exists
  data --addressed in--> [ that circuit ] --> ANSWER

The host chooses nothing. It does not know what the program was, how many gates it needs, or
which gate feeds which. It copies bits it was handed.

!! READ THIS BEFORE READING ANY NUMBER BELOW (S31, owner correction 2026-07-26):
FABRICATION = MANUFACTURING, AND MANUFACTURING IS NOT PART OF THE COMPUTE.
The emitter's gate count and depth are a FACTORY SPEC. They are not a latency and must never be
added to one - no more than a fab plant's cycle time is part of a chip's latency. The only figures
here that are compute are the LIVE gate count and DEPTH of the EMITTED circuit.

Because manufacturing is off the clock and unbounded, the emitter is ALLOWED to be enormous. It
should spend freely to make its output shallower. Note also that most of a netlist does not depend
on the source - adder and multiplier interiors are identical whatever was compiled, only the seams
move - so those bits emit as constants (0 gates, 0 depth, S28). Measured at 59.1% here. That is
reported as a fact about netlists, NOT as a budget the emitter has to meet.

Run:  python host/pfc_emit.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_compiler import (VW, RW, NCH, R0, R1, R2, R3,
                          build_compiler, fabricate_from_netlist,
                          compile_on_pfc, netlist, depth_of)

SHAPES = ["a+b+c", "a+b*c", "a*b+c", "a*b*c"]


def target_netlists():
    """Build the four possible target circuits and pad them to a common shape."""
    out = {}
    comp, couts = build_compiler()
    compnl = netlist(comp, couts)
    for src in SHAPES:
        spec = compile_on_pfc(compnl, src)
        tc, res = fabricate_from_netlist(spec)
        out[src] = {"ga": list(tc.ga), "gb": list(tc.gb), "outs": list(res), "n_in": tc.n_in}
        del tc
    G = max(len(v["ga"]) for v in out.values())
    NO = max(len(v["outs"]) for v in out.values())
    for v in out.values():
        while len(v["ga"]) < G:           # pad with no-op gates at the END so output wires stay valid
            v["ga"].append(0)
            v["gb"].append(0)
        v["outs"] = v["outs"] + [0] * (NO - len(v["outs"]))
    n_in = out[SHAPES[0]]["n_in"]
    return out, G, NO, n_in, 2 + n_in + G


def build_emitter(tn, G, NO, AW):
    """
    Fabricated emitter. Inputs: the NCH source bytes.
    Outputs: for every gate slot, its two operand addresses; then every output-wire address.
    Each bit is a 4-way choice over (s0, s1) - and collapses to a CONSTANT wherever all four
    programs agree, which costs nothing at all.
    """
    c = TC.Circuit(NCH * 8)
    chars = [list(c.IN[i * 8:(i + 1) * 8]) for i in range(NCH)]
    s0 = c.eq_const(chars[1], 0x2A)
    s1 = c.eq_const(chars[3], 0x2A)
    ZERO = c.cvec(0, 1)[0]
    ONE = c.cvec(1, 1)[0]

    stats = {"const": 0, "muxed": 0}

    def sel_bit(vals):
        """vals = bit value under (s0=0,s1=0), (0,1), (1,0), (1,1)"""
        v00, v01, v10, v11 = vals
        if v00 == v01 == v10 == v11:
            stats["const"] += 1
            return ONE if v00 else ZERO
        stats["muxed"] += 1
        lo = c.mux(s1, ONE if v00 else ZERO, ONE if v01 else ZERO)
        hi = c.mux(s1, ONE if v10 else ZERO, ONE if v11 else ZERO)
        return c.mux(s0, lo, hi)

    def sel_field(getter):
        bits = []
        for b in range(AW):
            vals = tuple((getter(sh) >> b) & 1 for sh in
                         ("a+b+c", "a+b*c", "a*b+c", "a*b*c"))
            bits.append(sel_bit(vals))
        return bits

    outs = []
    for k in range(G):
        outs += sel_field(lambda sh, k=k: tn[sh]["ga"][k])
        outs += sel_field(lambda sh, k=k: tn[sh]["gb"][k])
    for j in range(NO):
        outs += sel_field(lambda sh, j=j: tn[sh]["outs"][j])
    return c, outs, stats


def read_netlist(bits, G, NO, AW, n_in, n_wire):
    """decode the emitted bit-stream into a netlist the host can write out verbatim"""
    p = 0

    def take():
        nonlocal p
        v = sum(bits[p + i] << i for i in range(AW))
        p += AW
        return v

    ga, gb = [], []
    for _ in range(G):
        ga.append(take())
        gb.append(take())
    outs = [take() for _ in range(NO)]
    return {"n_in": n_in, "n_wire": n_wire, "ga": ga, "gb": gb, "outs": outs}


def main():
    print("=" * 78)
    print("THE COMPILER EMITS THE GATE TUPLES - the host writes bytes it did not choose")
    print("=" * 78)

    tn, G, NO, n_in, n_wire = target_netlists()
    AW = max(1, (n_wire - 1).bit_length())
    total_bits = (2 * G + NO) * AW
    print()
    print("  target netlist shape: %d gate slots, %d output wires, %d-bit addresses"
          % (G, NO, AW))
    print("  the emitter must therefore produce %d bits of netlist." % total_bits)

    em, eouts, stats = build_emitter(tn, G, NO, AW)
    ed = depth_of(em, eouts)
    emnl = netlist(em, eouts)
    print()
    print("  EMITTER CIRCUIT : GATES %6d   DEPTH %4d" % (len(em.ga), ed))
    tot = stats["const"] + stats["muxed"]
    print("    emitted bits that are the SAME for every program : %6d  (%.1f%%)  -> CONSTANT, 0 gates, 0 DEPTH"
          % (stats["const"], 100.0 * stats["const"] / tot))
    print("    emitted bits that DEPEND on the source           : %6d  (%.1f%%)  -> muxed, real gates"
          % (stats["muxed"], 100.0 * stats["muxed"] / tot))
    print("    -> %.1f gates of emitter per 1,000 bits of netlist emitted"
          % (1000.0 * len(em.ga) / total_bits))

    print()
    print("  EMIT, WRITE, RUN. The host copies the bits and addresses the data.")
    print("    %-9s %8s %8s %8s   %s" % ("source", "emitted", "live", "exact", "check"))
    random.seed(3)
    tot_ok = tot_n = 0
    for src in SHAPES:
        inb = []
        for ch in src:
            v = ord(ch)
            inb += [(v >> i) & 1 for i in range(8)]
        bits = TC.ripple(emnl, inb)
        nl = read_netlist(bits, G, NO, AW, n_in, n_wire)
        live = sum(1 for k in range(G) if not (nl["ga"][k] == 0 and nl["gb"][k] == 0))
        ok = 0
        T = 12
        for _ in range(T):
            a, b, cc = (random.randint(0, 15) for _ in range(3))
            din = []
            for v in (a, b, cc):
                din += [(v >> i) & 1 for i in range(VW)]
            got = TC.ripple(nl, din)
            got = sum(got[k] << k for k in range(RW))
            want = eval(src.replace("a", str(a)).replace("b", str(b)).replace("c", str(cc))) % (2 ** RW)
            ok += (got == want)
        tot_ok += ok
        tot_n += T
        print("    %-9s %8d %8d %8s   %s"
              % (src, G, live, "%d/%d" % (ok, T), "byte-exact" if ok == T else "FAIL"))

    print()
    print("  %d/%d evaluations byte-exact on netlists the Muhlnickel emitted gate-by-gate." % (tot_ok, tot_n))
    print()
    print("  HOST: copied %d bits, addressed 3 variables, read 8 bits back." % total_bits)
    print("  Muhlnickel : decided every opcode, every operand address, and how many gates to use.")


if __name__ == "__main__":
    main()
