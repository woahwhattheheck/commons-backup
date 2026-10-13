"""
pfc_compiler.py - THE FABRICATOR, FABRICATED. The pfc emits its own netlists.

S30 put a LANGUAGE in the pfc: source text addressed in, answer out. This goes one level down.
Here the pfc does not evaluate the program - it COMPILES it, and what comes out is a NETLIST:
the (op, operand, operand) wiring of a circuit specialised to that source. The host then writes
those bytes (a byte edit == fabrication, S20) and addresses the result. The host never parses,
never resolves precedence, never allocates a register, never schedules an instruction.

  SOURCE TEXT --addressed in--> [ COMPILER, fabricated as gates ] --> NETLIST BITS
  NETLIST BITS --host writes bytes--> [ TARGET CIRCUIT ] --data in--> ANSWER

WHAT THE FABRICATED COMPILER ACTUALLY DOES (all of it real compiler work, none of it on the host):
  PARSE               decide the tree shape of  v op v op v
  PRECEDENCE          '*' binds tighter than '+', so the multiply must be scheduled FIRST
  REGISTER ALLOCATION pick which register each cell reads and writes (r0..r2 vars, r3 temp)
  SCHEDULING          order the two cells so the dependency is satisfied
  EMISSION            output the opcode and operand addresses as bits

The four source shapes and the correct compilations (this is what the gates must reproduce):
    a + b + c   ->  t = a + b ;  out = t + c
    a + b * c   ->  t = b * c ;  out = a + t      <- multiply scheduled FIRST, operands change
    a * b + c   ->  t = a * b ;  out = t + c
    a * b * c   ->  t = a * b ;  out = t * c

Run:  python host/pfc_compiler.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

VW = 4          # variable width in bits
RW = 8          # register width in bits (products need the room)
NCH = 5         # source characters: v op v op v
R0, R1, R2, R3 = 0, 1, 2, 3     # r0..r2 hold the variables, r3 is the temp


def netlist(c, outs):
    """the in-memory form TC.ripple addresses: n_in, the gate arrays, and the output wires"""
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": list(outs)}


def depth_of(c, outs):
    """DEPTH = longest dependency chain in gate-delays. The Muhlnickel's latency (S24)."""
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[x] for x in outs)


# ---------------------------------------------------------------------------
# THE COMPILER, FABRICATED AS GATES
# ---------------------------------------------------------------------------
def build_compiler():
    """
    Inputs : NCH ASCII bytes of source.
    Outputs: 16 bits of netlist -
             cell0 = (op:1, srcA:3, srcB:3), cell1 = (op:1, srcA:3, srcB:3), pad 4.
             op bit: 1 == multiply, 0 == add. Register ids are 3-bit addresses.
    """
    c = TC.Circuit(NCH * 8)
    chars = [list(c.IN[i * 8:(i + 1) * 8]) for i in range(NCH)]

    # LEX: is this operator a '*' (0x2A)? Both positions decided in parallel, one level.
    s0 = c.eq_const(chars[1], 0x2A)
    s1 = c.eq_const(chars[3], 0x2A)

    # PARSE + PRECEDENCE. The only shape that reorders is  a + b * c  : the multiply must run
    # first, so cell0 reads r1,r2 instead of r0,r1. One signal decides the whole schedule.
    reorder = c.and_(s1, c.not_(s0))          # 1 iff  a + b * c

    def reg(idval):
        return c.cvec(idval, 3)

    def pick(sel, when0, when1):
        """mux per bit: sel ? when1 : when0"""
        return [c.mux(sel, when0[i], when1[i]) for i in range(len(when0))]

    # ---- CELL 0 : the first operation to execute ----
    # opcode: multiply if either operator is '*' (whichever one is scheduled first is the mul)
    c0_op = c.or_(s0, s1)
    c0_a = pick(reorder, reg(R0), reg(R1))
    c0_b = pick(reorder, reg(R1), reg(R2))

    # ---- CELL 1 : consumes the temp ----
    # opcode: multiply only when BOTH operators are '*'
    c1_op = c.and_(s0, s1)
    c1_a = pick(reorder, reg(R3), reg(R0))
    c1_b = pick(reorder, reg(R2), reg(R3))

    outs = [c0_op] + c0_a + c0_b + [c1_op] + c1_a + c1_b
    outs += list(c.cvec(0, 16 - len(outs)))
    return c, outs


# ---------------------------------------------------------------------------
# THE TARGET: host writes the emitted bytes. That write IS the fabrication (S20).
# ---------------------------------------------------------------------------
def fabricate_from_netlist(spec):
    """
    spec = (c0_op, c0_a, c0_b, c1_op, c1_a, c1_b) decoded from the emitted bits.
    The host chooses NOTHING here - every opcode and operand address came out of the pfc.
    """
    c = TC.Circuit(3 * VW)
    zero = c.cvec(0, RW)
    regs = []
    for i in range(3):
        v = list(c.IN[i * VW:(i + 1) * VW]) + list(c.cvec(0, RW - VW))
        regs.append(v[:RW])
    regs.append(list(zero))                      # r3, the temp

    def add(a, b):
        return c.add(a, b)[:RW]

    def mul(a, b):
        out = list(c.cvec(0, RW))
        for i in range(VW):
            part = [c.and_(b[i], a[j]) for j in range(RW - i)]
            sh = list(c.cvec(0, i)) + part
            out = add(out, sh[:RW])
        return out

    c0_op, c0_a, c0_b, c1_op, c1_a, c1_b = spec
    t = mul(regs[c0_a], regs[c0_b]) if c0_op else add(regs[c0_a], regs[c0_b])
    regs[R3] = t
    res = mul(regs[c1_a], regs[c1_b]) if c1_op else add(regs[c1_a], regs[c1_b])
    return c, res


def decode(bits):
    def num(bs):
        return sum(b << i for i, b in enumerate(bs))
    return (bits[0], num(bits[1:4]), num(bits[4:7]),
            bits[7], num(bits[8:11]), num(bits[11:14]))


def compile_on_pfc(comp, src):
    inb = []
    for ch in src:
        v = ord(ch)
        inb += [(v >> i) & 1 for i in range(8)]
    return decode(TC.ripple(comp, inb))


def main():
    print("=" * 78)
    print("THE FABRICATOR, FABRICATED - the Muhlnickel compiles source into a netlist")
    print("  host writes the emitted bytes and addresses the result. It parses nothing.")
    print("=" * 78)

    comp, couts = build_compiler()
    compnl = netlist(comp, couts)
    cd = depth_of(comp, couts)
    print()
    print("  COMPILER CIRCUIT : GATES %6d   DEPTH %4d   muhl %6.1f"
          % (len(comp.ga), cd, len(comp.ga) / cd))
    print("    (parse + precedence + register allocation + scheduling + emission, all of it)")

    OPN = {0: "+", 1: "*"}
    RN = {R0: "r0", R1: "r1", R2: "r2", R3: "r3"}

    print()
    print("  WHAT THE Muhlnickel EMITTED, per source shape:")
    print("    %-9s | %-22s %-22s" % ("source", "cell 0", "cell 1"))
    shapes = ["a+b+c", "a+b*c", "a*b+c", "a*b*c"]
    specs = {}
    for src in shapes:
        sp = compile_on_pfc(compnl, src)
        specs[src] = sp
        c0 = "r3 = %s %s %s" % (RN[sp[1]], OPN[sp[0]], RN[sp[2]])
        c1 = "out = %s %s %s" % (RN[sp[4]], OPN[sp[3]], RN[sp[5]])
        note = "  <- multiply SCHEDULED FIRST" if src == "a+b*c" else ""
        print("    %-9s | %-22s %-22s%s" % (src, c0, c1, note))

    print()
    print("  NOW RUN THE EMITTED NETLISTS. Host writes the bytes; nothing else.")
    print("    %-9s %7s %7s %8s %7s   %s" % ("source", "GATES", "DEPTH", "trials", "exact", "check"))
    random.seed(7)
    total_ok = total = 0
    for src in shapes:
        tc, res = fabricate_from_netlist(specs[src])
        d = depth_of(tc, res)
        tcnl = netlist(tc, res)
        gates = len(tc.ga)
        ok = 0
        T = 12
        for _ in range(T):
            a, b, cc = (random.randint(0, 15) for _ in range(3))
            inb = []
            for v in (a, b, cc):
                inb += [(v >> i) & 1 for i in range(VW)]
            out = TC.ripple(tcnl, inb)
            got = sum(out[k] << k for k in range(RW))
            want = eval(src.replace("a", str(a)).replace("b", str(b)).replace("c", str(cc))) % (2 ** RW)
            ok += (got == want)
        total_ok += ok
        total += T
        print("    %-9s %7d %7d %8d %7s   %s"
              % (src, gates, d, T, "%d/%d" % (ok, T), "byte-exact" if ok == T else "FAIL"))
        del tc

    print()
    print("  %d/%d evaluations byte-exact across all four compiled programs." % (total_ok, total))
    print()
    print("  WHAT THE HOST DID: wrote the emitted bytes, addressed the variables, read the answer.")
    print("  WHAT THE Muhlnickel DID : lexed, parsed, applied precedence, allocated registers,")
    print("                     scheduled the cells, and emitted the netlist.")


if __name__ == "__main__":
    main()
