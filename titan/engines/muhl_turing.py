#!/usr/bin/env python3
"""muhl_turing.py -- A UNIVERSAL TURING MACHINE STEP, fabricated as gates. (PYTHONUTF8=1, no numpy.)

The universal step is ONE fixed gate netlist. It takes a machine STATE, the TAPE SYMBOL under the head,
and a whole TRANSITION TABLE encoded as DATA (delta: (state, symbol) -> (next_state, write, move)), and
emits the next (state, write-symbol, move-direction). Route in a different table and it becomes a
different Turing machine -- no re-fabrication. This is the universal move: the transition logic is gates,
the machine is data.

Verified byte-exact vs an independent Python TM reference over every (state, symbol) address, for every
loaded table plus random tables. Then the fabricated step DRIVES the historic BUSY BEAVER machines
(BB-2, BB-3, BB-4). Their halting behaviour -- how many steps they run and how many 1s they leave on the
tape -- is EMERGENT from iterating the one gate step; we reproduce the known championship values
(BB(2)=6 steps/4 ones, BB(3)=14/6, BB(4)=107/13). This is the literal edge of computability: BB(5)+ is
open / uncomputable. The step is gates; the halting is what falls out.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---- machine geometry (covers every busy beaver here; states A=0,B=1,C=2,D=3, HALT=7) ----
STATE_BITS = 3                       # up to 8 states (incl. the halt sentinel)
SYM_BITS   = 1                       # 2-symbol tape alphabet {0,1}
NSYM       = 1 << SYM_BITS           # 2
NADDR      = 1 << (STATE_BITS + SYM_BITS)   # 16 (state,symbol) table rows
ENTRY      = STATE_BITS + SYM_BITS + 1      # next_state + write + move  = 5 bits/row
TABLE_BITS = NADDR * ENTRY                  # 80 bits of transition-table data
NIN        = SYM_BITS + STATE_BITS + TABLE_BITS   # 84 input wires
HALT       = 7                       # dedicated halt state


def _or(g, xs):
    a = g.C0
    for x in xs: a = g.OR(a, x)
    return a


def build_step():
    """Fabricate the universal Turing-machine step as one gate netlist."""
    g = CC.CircuitCompiler(NIN); IN = g.IN
    sym   = [IN[0]]                                   # symbol bits (LSB of the address)
    state = [IN[SYM_BITS + b] for b in range(STATE_BITS)]   # state bits (high part of address)
    table = IN[SYM_BITS + STATE_BITS:]               # the transition table, as data

    # address = [sym0, st0, st1, st2]  ->  row index i = state*NSYM + sym
    addr = sym + state

    def onehot(bits, n):
        out = []
        for i in range(n):
            m = g.C1
            for j in range(len(bits)):
                m = g.AND(m, bits[j] if (i >> j) & 1 else g.NOT(bits[j]))
            out.append(m)
        return out

    sel = onehot(addr, NADDR)                         # one-hot select of the addressed row
    # each output bit = OR over rows of AND(row-selected, that row's stored bit)
    outw = []
    for k in range(ENTRY):
        outw.append(_or(g, [g.AND(sel[i], table[i * ENTRY + k]) for i in range(NADDR)]))

    gates, out2 = g.dce(outw)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    # critical-path depth (DEPTH is the score, per the corpus)
    d = [0] * (2 + g.n_in + len(gates))
    base = 2 + g.n_in
    for k, (op, a, b) in enumerate(gates):
        d[base + k] = 1 + max(d[a], d[b])
    depth = max(d[w] for w in out2)
    return run, out2, len(gates), depth


# ---------- independent Python reference (NO gates) -- verifies the fabricated step ----------
def ref_step(state, symbol, table_bits):
    i = state * NSYM + symbol
    base = i * ENTRY
    ns = sum(table_bits[base + b] << b for b in range(STATE_BITS))
    wr = table_bits[base + STATE_BITS]
    mv = table_bits[base + STATE_BITS + 1]
    return ns, wr, mv


def encode_table(trans):
    """trans: {(state, symbol): (next_state, write, move)} ; move 'R'->1, 'L'->0."""
    bits = [0] * TABLE_BITS
    for (st, s), (ns, wr, mv) in trans.items():
        base = (st * NSYM + s) * ENTRY
        for b in range(STATE_BITS): bits[base + b] = (ns >> b) & 1
        bits[base + STATE_BITS]     = wr & 1
        bits[base + STATE_BITS + 1] = 1 if (mv == 'R' or mv == 1) else 0
    return bits


def gate_step(run, outw, state, symbol, table_bits):
    inp = [symbol] + [(state >> b) & 1 for b in range(STATE_BITS)] + list(table_bits)
    v = run(inp, 1)
    ns = sum((v[outw[b]] & 1) << b for b in range(STATE_BITS))
    wr = v[outw[STATE_BITS]] & 1
    mv = v[outw[STATE_BITS + 1]] & 1
    return ns, wr, mv


def run_machine(run, outw, table_bits, max_steps=100000):
    """Iterate the fabricated gate step to run a Turing machine to halt. Halting is emergent."""
    tape = {}; pos = 0; state = 0; steps = 0
    while state != HALT and steps < max_steps:
        sym = tape.get(pos, 0)
        ns, wr, mv = gate_step(run, outw, state, sym, table_bits)
        tape[pos] = wr
        pos += 1 if mv == 1 else -1
        state = ns
        steps += 1
    ones = sum(1 for val in tape.values() if val == 1)
    halted = (state == HALT)
    return steps, ones, halted


# ---------- the busy beaver champions (A=0,B=1,C=2,D=3, H=7) ----------
BB2 = {(0,0):(1,1,'R'), (0,1):(1,1,'L'),
       (1,0):(0,1,'L'), (1,1):(7,1,'R')}

BB3 = {(0,0):(1,1,'R'), (0,1):(7,1,'R'),
       (1,0):(2,0,'R'), (1,1):(1,1,'R'),
       (2,0):(2,1,'L'), (2,1):(0,1,'L')}

BB4 = {(0,0):(1,1,'R'), (0,1):(1,1,'L'),
       (1,0):(0,1,'L'), (1,1):(2,0,'L'),
       (2,0):(7,1,'R'), (2,1):(3,1,'L'),
       (3,0):(3,1,'R'), (3,1):(0,0,'R')}

KNOWN = {"BB(2)": (BB2, 6, 4), "BB(3)": (BB3, 14, 6), "BB(4)": (BB4, 107, 13)}


def main():
    run, outw, ng, depth = build_step()
    print(f"\n  MUHLNICKEL UNIVERSAL TURING STEP -- fabricated as {ng:,} gates, depth {depth}")
    print(f"  one fixed circuit: (state[{STATE_BITS}b], symbol[{SYM_BITS}b], table[{TABLE_BITS}b as data])"
          f" -> (next_state, write, move)")
    print(f"  the machine is DATA routed into {NIN} input wires; change the table -> change the machine.\n")

    # ---- byte-exact vs the independent Python reference ----
    rng = random.Random(7); bad = 0; checked = 0
    tables = [encode_table(t) for (t, _, _) in KNOWN.values()]
    for _ in range(200):                                 # random transition tables too
        tables.append([rng.randrange(2) for _ in range(TABLE_BITS)])
    for tb in tables:
        for state in range(1 << STATE_BITS):
            for symbol in range(NSYM):
                if gate_step(run, outw, state, symbol, tb) != ref_step(state, symbol, tb):
                    bad += 1
                checked += 1
    print(f"  gate step == Python TM reference over all {checked:,} (table x state x symbol) cases: "
          f"{'PASS' if bad == 0 else str(bad) + ' WRONG'}")
    if bad:
        return 1

    # ---- run the busy beavers off the fabricated step; halting is emergent ----
    print("\n  BUSY BEAVER machines run by iterating the gate step (halting behaviour is emergent):")
    print(f"    {'machine':8}  {'steps':>7}  {'ones':>5}   known(steps/ones)   match")
    all_ok = True
    for name, (trans, k_steps, k_ones) in KNOWN.items():
        tb = encode_table(trans)
        steps, ones, halted = run_machine(run, outw, tb)
        ok = halted and steps == k_steps and ones == k_ones
        all_ok = all_ok and ok
        print(f"    {name:8}  {steps:7d}  {ones:5d}   {k_steps:>6d}/{k_ones:<6d}      "
              f"{'PASS' if ok else 'FAIL'}")

    print(f"\n  reproduced the known busy-beaver championship values: {'ALL PASS' if all_ok else 'MISMATCH'}")
    print("  BB(5)+ is open / uncomputable -- this is the literal edge of what any machine can decide.")
    print("  The universal step is gates; the halting is what falls out of iterating it.\n")
    return 0 if (bad == 0 and all_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
