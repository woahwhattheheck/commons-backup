#!/usr/bin/env python3
"""host/pfc_turing.py — A TURING MACHINE, forged as a self-clocked gate netlist and PROVEN byte-exact (fable 2026-07-23).

The universal machine, baked into a file's bytes. State = tape (bits) + head one-hot position + a few state bits; the
entire transition function is prefabricated as gates (sdc_cc), and each frame is one baked next-state propagation. Runs
a 4-state busy-beaver-class program. Host only pulses + renders the space-time diagram. Byte-exact vs a Python TM.

  python host/pfc_turing.py --test     # bake + verify byte-exact vs a reference TM over its whole run
  python host/pfc_turing.py            # play: the tape scrolls as history; the head walks; it halts
"""
import os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

SBX = "C:/llm/sdc_sandbox"
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}; OPN = {v: k for k, v in OPC.items()}
TLEN = 96                                              # toroidal tape length
SBITS = 3                                              # up to 8 machine states (incl. HALT)
# 4-state busy-beaver-class program. (state, read) -> (write, move, next).  move: +1=R, -1=L.  state 7 = HALT.
A, B, C, Dd, H = 0, 1, 2, 3, 7
TRANS = {(A, 0): (1, +1, B), (A, 1): (1, -1, B),
         (B, 0): (1, -1, A), (B, 1): (0, -1, C),
         (C, 0): (1, +1, H), (C, 1): (1, -1, Dd),
         (Dd, 0): (1, +1, Dd), (Dd, 1): (0, +1, A)}
START = A


# ============================ build the machine as a gate netlist ============================
def build_tm(TLEN, SBITS, trans):
    g = CC.CircuitCompiler(TLEN + TLEN + SBITS)        # tape[0..T), head_onehot[T..2T), state[2T..2T+SBITS)
    IN = g.IN
    tape = [IN[i] for i in range(TLEN)]
    head = [IN[TLEN + i] for i in range(TLEN)]
    st = [IN[2 * TLEN + j] for j in range(SBITS)]
    halted = eqc(g, st, H, SBITS)                      # already-halted flag (state == HALT)
    running = g.NOT(halted)

    read = g.C0                                        # symbol under the head = OR_c head[c] & tape[c]
    for c in range(TLEN):
        read = g.OR(read, g.AND(head[c], tape[c]))
    nread = g.NOT(read)

    # decode active transition entries: sel[(s,r)] = (state==s) & (read==r) & running
    sel = {}
    for (s, r), _ in trans.items():
        sel[(s, r)] = g.AND(g.AND(eqc(g, st, s, SBITS), read if r else nread), running)
    orsel = lambda pred: _or(g, [sel[k] for k in trans if pred(trans[k], k)])

    write1 = orsel(lambda out, k: out[0] == 1)         # any active entry that writes a 1
    moveR = orsel(lambda out, k: out[1] > 0)
    moveL = orsel(lambda out, k: out[1] < 0)
    nstate = [orsel(lambda out, k: (out[2] >> j) & 1) for j in range(SBITS)]

    # next tape: cell under head gets `write1` (frozen if halted); others unchanged
    ntape = [g.OR(g.AND(head[c], write1), g.AND(g.NOT(head[c]), tape[c])) for c in range(TLEN)]
    # next head: move L/R along the tape (toroidal). when halted, head stays.
    nhead = []
    for c in range(TLEN):
        fromL = g.AND(head[(c - 1) % TLEN], moveR)     # a head to my left moved right into me
        fromR = g.AND(head[(c + 1) % TLEN], moveL)
        moved = g.OR(fromL, fromR)
        nhead.append(g.OR(g.AND(running, moved), g.AND(halted, head[c])))
    # next state: computed transition while running; frozen at HALT
    fstate = [g.OR(g.AND(running, nstate[j]), g.AND(halted, st[j])) for j in range(SBITS)]

    gates, outs = g.dce(ntape + nhead + fstate)
    return g, gates, outs


def eqc(g, bits, k, nb):                               # bits (LSB..) == constant k
    r = g.C1
    for j in range(nb):
        r = g.AND(r, bits[j] if (k >> j) & 1 else g.NOT(bits[j]))
    return r


def _or(g, xs):
    a = g.C0
    for x in xs:
        a = g.OR(a, x)
    return a


# ============================ python reference (ground truth) ============================
def ref_step(tape, head, state, trans):
    if state == H:
        return list(tape), head, state
    r = tape[head]; w, mv, ns = trans[(state, r)]
    t = list(tape); t[head] = w
    return t, (head + mv) % len(tape), ns


# ============================ bake / load ============================
def bake():
    print(f"fabricating a Turing machine as a gate netlist (tape {TLEN}, {2**SBITS} states) …", flush=True)
    t0 = time.time(); g, gates, outs = build_tm(TLEN, SBITS, TRANS); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {g.n_in:,} state bits, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True); path = os.path.join(SBX, "pfc_turing.pfc")
    with open(path, "wb") as f:
        f.write(b"PFCTURNG"); f.write(struct.pack("<IIIII", g.n_in, n_wire, len(gates), len(outs), TLEN))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {path}  ({os.path.getsize(path):,} B).", flush=True)
    return path


def load():
    path = os.path.join(SBX, "pfc_turing.pfc")
    if not os.path.exists(path): bake()
    blob = open(path, "rb").read(); assert blob[:8] == b"PFCTURNG"
    n_in, n_wire, n_gate, n_out, T = struct.unpack_from("<IIIII", blob, 8); p = 28
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); run = cc.compile_ripple(gates, n_wire)
    return dict(T=T, S=SBITS, outs=outs, run=run, n_gate=n_gate)


def tick(cd, tape, head, state):
    T = cd["T"]; inp = [0] * (2 * T + cd["S"])
    for c in range(T): inp[c] = tape[c] & 1
    inp[T + head] = 1
    for j in range(cd["S"]): inp[2 * T + j] = (state >> j) & 1
    v = cd["run"](inp, 1); bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    o = cd["outs"]
    ntape = [bit(o[c]) for c in range(T)]
    nhead = next((c for c in range(T) if bit(o[T + c])), head)
    nstate = sum(bit(o[2 * T + j]) << j for j in range(cd["S"]))
    return ntape, nhead, nstate


def selftest():
    cd = load(); T = cd["T"]
    tape = [0] * T; head = T // 2; state = START
    rt, rh, rs = list(tape), head, state
    print(f"\n  self-test: running the machine to HALT, byte-exact vs reference TM …", flush=True)
    ok = True; steps = 0
    for step in range(2000):
        rt, rh, rs = ref_step(rt, rh, rs, TRANS)
        tape, head, state = tick(cd, tape, head, state)
        steps += 1
        if tape != rt or head != rh or state != rs:
            ok = False; print(f"    MISMATCH at step {step+1}"); break
        if state == H: break
    print(f"    ran {steps} ticks to HALT · byte-exact vs reference: {ok} · {sum(tape)} ones on the tape", flush=True)
    print(f"\n  the whole transition function is baked gates; a tick = one propagation. host = clock only.", flush=True)
    return 0 if ok else 1


def play():
    import tkinter as tk
    cd = load(); T = cd["T"]; ROWS = 60; SC = 9
    tape = [0] * T; head = T // 2; state = START; hist = []
    root = tk.Tk(); root.title("Turing machine — forged on the pfc"); root.configure(bg="#0a0e13")
    cv = tk.Canvas(root, width=T * SC, height=ROWS * SC, bg="#0a0e13", highlightthickness=0); cv.pack(padx=10, pady=10)
    root.bind("<Escape>", lambda e: root.destroy())

    def frame():
        nonlocal tape, head, state
        if state != 7:
            tape, head, state = tick(cd, tape, head, state)
        hist.append((list(tape), head, state == 7));
        if len(hist) > ROWS: hist.pop(0)
        cv.delete("all")
        for ry, (row, hd, halt) in enumerate(hist):
            for x in range(T):
                col = "#e8434e" if (ry == len(hist) - 1 and x == hd) else ("#35c9bd" if row[x] else "#121821")
                cv.create_rectangle(x * SC, ry * SC, x * SC + SC, ry * SC + SC, outline="", fill=col)
        root.after(60, frame)
    frame(); root.mainloop()


def main():
    if "--test" in sys.argv[1:]: return selftest()
    if "--bake" in sys.argv[1:]: bake(); return 0
    return play()


if __name__ == "__main__":
    raise SystemExit(main())
