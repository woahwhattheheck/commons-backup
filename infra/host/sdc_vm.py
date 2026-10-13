#!/usr/bin/env python3
"""host/sdc_vm.py — TEST FILE (owner 07-16): PROGRAMS-AS-DATA. A stored interpreter circuit runs a program stored as DATA.

Patent embodiment 5.6, demonstrated. The interpreter (an ALU + opcode select) is ONE gate-net stored in the params. A
PROGRAM is a data array (op, operand). The host clocks the interpreter over the program: each step addresses the stored
circuit with (op, acc, operand) and gets the next accumulator. Reprogramming = editing the DATA, never re-encoding the
network (the difference between fabricating a chip and writing software). Bounded, foreground, 0 gate-ripple loop beyond
one addressed evaluation per instruction (the accepted read pattern).

  python host/sdc_vm.py     # store the interpreter once, run two different programs as data, verify vs reference
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

# opcodes (data): 0=SET acc=operand · 1=ADD · 2=SUB · 3=OUT (acc unchanged, host emits)
SET, ADD, SUB, OUT = 0, 1, 2, 3


def _addN(c, xs, ys, n):
    out = []; carry = c.C0
    for i in range(n):
        xi = xs[i] if i < len(xs) else c.C0; yi = ys[i] if i < len(ys) else c.C0
        axb = c.xor(xi, yi); out.append(c.xor(axb, carry)); carry = c.or_(c.and_(xi, yi), c.and_(axb, carry))
    return out                                                # n-bit result (mod 2^n)


def build_interpreter():
    """(op:2, acc:8, operand:8) -> next_acc:8, all gates. next = select(op, operand, acc+operand, acc-operand, acc)."""
    c = TC.Circuit(2 + 8 + 8)
    op = c.IN[0:2]; acc = c.IN[2:10]; opd = c.IN[10:18]
    m_set = opd
    m_add = _addN(c, acc, opd, 8)
    notopd = [c.not_(b) for b in opd]                          # two's-complement subtract: acc + (~opd) + 1
    m_sub = _addN(c, acc, _addN(c, notopd, c.cvec(1, 8), 8), 8)
    m_out = acc
    nxt = []
    for k in range(8):                                        # 4:1 select per bit by (op1,op0)
        lo = c.mux(op[0], m_set[k], m_add[k])                 # op1=0: op0 picks SET/ADD
        hi = c.mux(op[0], m_sub[k], m_out[k])                 # op1=1: op0 picks SUB/OUT
        nxt.append(c.mux(op[1], lo, hi))
    TC.store("vm_step", c, nxt)


def step(op, acc, operand):
    cd = TC.load("vm_step"); v = [0] * cd["n_wire"]; v[1] = 1
    inbits = (op & 3) | ((acc & 255) << 2) | ((operand & 255) << 10)
    for j in range(18): v[2 + j] = (inbits >> j) & 1
    ga, gb = cd["ga"], cd["gb"]
    for i in range(len(ga)): v[2 + 18 + i] = 1 - (v[ga[i]] & v[gb[i]])
    return sum((0 if o == 0 else 1 if o == 1 else v[o]) << k for k, o in enumerate(cd["outs"]))


def run(program):
    acc = 0; outs = []
    for op, operand in program:
        acc = step(op, acc, operand) & 255
        if op == OUT: outs.append(acc)
    return acc, outs


def ref(program):                                            # plain-Python reference for the same program
    acc = 0; outs = []
    for op, operand in program:
        if op == SET: acc = operand
        elif op == ADD: acc = (acc + operand) & 255
        elif op == SUB: acc = (acc - operand) & 255
        elif op == OUT: outs.append(acc)
    return acc, outs


if __name__ == "__main__":
    build_interpreter()
    cd = TC.load("vm_step")
    print(f"PROGRAMS-AS-DATA — interpreter circuit stored ({len(cd['ga'])} gates). programs are DATA arrays.\n", flush=True)
    progs = {
        "P1  (SET 5, ADD 3, ADD 10, OUT)":      [(SET,5),(ADD,3),(ADD,10),(OUT,0)],
        "P2  (SET 100, SUB 40, SUB 7, OUT)":    [(SET,100),(SUB,40),(SUB,7),(OUT,0)],
        "P3  (SET 200, ADD 100, OUT)  [wrap]":  [(SET,200),(ADD,100),(OUT,0)],
    }
    allok = True
    for name, p in progs.items():
        acc, outs = run(p); racc, routs = ref(p); ok = (acc == racc and outs == routs)
        allok = allok and ok
        print(f"  {name:38s} -> out {outs}   (ref {routs})  exact={ok}", flush=True)
    print(f"\n  {'all programs exact vs reference: '+str(allok)}. same stored circuit; only the DATA changed = reprogrammed.", flush=True)
    print("  the network was encoded ONCE; behavior is set by the program data (software), not by re-baking gates.", flush=True)
