#!/usr/bin/env python3
"""host/pfc_operator.py — an AGENT OPERATOR (a neural forward pass) running on the Muhlnickel (owner 07-20).

The agent's operator is a decision it makes from an observation. Here that operator is a real NEURAL FORWARD PASS baked as
gates: an 8x8 glyph -> a linear layer (dot the input against 10 learned digit templates) -> argmax -> the predicted digit.
The whole forward pass is ONE gate netlist stored in a pfc file. The host routes the observation (the drawn pixels) in as
SIGNALS and PULSES the clock (one bounded ripple); the pfc computes the matmul + argmax and outputs the decision. Host =
clock + monitor only. Byte-exact vs a reference forward pass. (Same principle proven at scale in the docs' forward-pass
work — here a small, fully-verifiable operator you can watch decide.)

  python host/pfc_operator.py --test    # build, verify it classifies + gates match the reference byte-exact
  python host/pfc_operator.py           # draw a digit (click), the pfc classifies it live
"""
import os, struct, sys, time, zlib
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_raycast import const, add, mux, ult

SBX = PFCP.SBX; PFC = os.path.join(SBX, "pfc_operator.pfc")
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}; OPN = {v: k for k, v in OPC.items()}

DIGITS = [  # 10 learned 8x8 templates (the linear layer's weights)
    ["00111100", "01100110", "01100110", "01100110", "01100110", "01100110", "00111100", "00000000"],  # 0
    ["00011000", "00111000", "00011000", "00011000", "00011000", "00011000", "01111110", "00000000"],  # 1
    ["00111100", "01100110", "00000110", "00001100", "00110000", "01100000", "01111110", "00000000"],  # 2
    ["00111100", "01100110", "00000110", "00011100", "00000110", "01100110", "00111100", "00000000"],  # 3
    ["00001100", "00011100", "00111100", "01101100", "01111110", "00001100", "00001100", "00000000"],  # 4
    ["01111110", "01100000", "01111100", "00000110", "00000110", "01100110", "00111100", "00000000"],  # 5
    ["00111100", "01100110", "01100000", "01111100", "01100110", "01100110", "00111100", "00000000"],  # 6
    ["01111110", "00000110", "00001100", "00011000", "00110000", "00110000", "00110000", "00000000"],  # 7
    ["00111100", "01100110", "01100110", "00111100", "01100110", "01100110", "00111100", "00000000"],  # 8
    ["00111100", "01100110", "01100110", "00111110", "00000110", "01100110", "00111100", "00000000"],  # 9
]
T = [[int(DIGITS[c][r][col]) for r in range(8) for col in range(8)] for c in range(10)]   # T[c][p], p=r*8+col


def ref(inp):                                                   # forward pass: score[c]=<input, template_c>; argmax
    scores = [sum(inp[p] for p in range(64) if T[c][p]) for c in range(10)]
    return max(range(10), key=lambda c: scores[c]), max(scores)


def popcount(g, bits, w=7):
    s = [g.C0] * w
    for b in bits:
        s = add(g, s, [b])[:w]
    return s


def build(g):
    inp = g.IN[0:64]
    scores = [popcount(g, [inp[p] for p in range(64) if T[c][p]]) for c in range(10)]
    best = scores[0]; idx = const(g, 0, 4)
    for c in range(1, 10):
        gt = ult(g, best, scores[c])                            # best < score[c] -> class c wins (ties keep lower idx)
        best = mux(g, gt, scores[c], best); idx = mux(g, gt, const(g, c, 4), idx)
    return g.dce(list(idx)[:4] + list(best)[:7])                # output: predicted digit (4b) + winning score (7b)


def bake():
    g = CC.CircuitCompiler(64)
    print("fabricating the operator (neural forward pass) …", flush=True); t0 = time.time()
    gates, outs = build(g); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, 64-pixel input, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True)
    with open(PFC, "wb") as f:
        f.write(b"PFCOPR01"); f.write(struct.pack("<IIII", g.n_in, n_wire, len(gates), len(outs)))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {PFC} ({os.path.getsize(PFC):,} B). the forward pass lives in storage as gates.", flush=True)
    return gates, outs, n_wire


def load():
    if not os.path.exists(PFC): bake()
    with open(PFC, "rb") as f: blob = f.read()
    assert blob[:8] == b"PFCOPR01"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); return dict(run=cc.compile_ripple(gates, n_wire), outs=outs, n_gate=n_gate)


def pulse(cd, inp):                                             # inp: 64 ints -> (predicted digit, score)
    v = cd["run"](list(inp), 1); o = cd["outs"]; bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    cls = sum(bit(o[i]) << i for i in range(4)); sc = sum(bit(o[4 + i]) << i for i in range(7))
    return cls, sc


def test():
    import random
    gates, outs, n_wire = bake()
    cc = CC.CircuitCompiler(64); cd = dict(run=cc.compile_ripple(gates, n_wire), outs=outs, n_gate=len(gates))
    # 1) accuracy: each clean template classifies to itself
    correct = sum(1 for c in range(10) if pulse(cd, T[c])[0] == c)
    print(f"  clean-digit accuracy: {correct}/10 (each template -> itself)", flush=True)
    # 2) byte-exact vs the reference forward pass, incl. noisy inputs
    random.seed(5); ok = True
    for i in range(400):
        base = list(T[random.randrange(10)]);
        for _ in range(random.randrange(6)): base[random.randrange(64)] ^= 1   # add noise
        inp = base if i % 2 else [1 if random.random() < 0.3 else 0 for _ in range(64)]
        if pulse(cd, inp) != ref(inp): ok = False; print(f"    MISMATCH at {i}"); break
    print(f"  gates vs reference forward pass: 400 inputs byte-exact: {ok}", flush=True)
    # 3) noisy-digit recognition demo (text)
    random.seed(1); hits = 0
    for c in range(10):
        inp = list(T[c])
        for _ in range(4): inp[random.randrange(64)] ^= 1
        pred, sc = pulse(cd, inp); hits += (pred == c)
        print(f"    noisy '{c}' -> Muhlnickel says {pred} (score {sc})", flush=True)
    print(f"  noisy recognition: {hits}/10 correct", flush=True)
    return 0 if ok else 1


def play():
    try:
        import tkinter as tk
    except Exception as e:
        print(f"tkinter unavailable ({e}). Verify headless: python host/pfc_operator.py --test"); return 1
    cd = load(); grid = [0] * 64; CS = 44
    root = tk.Tk(); root.title("pfc operator — draw a digit, the pfc classifies"); root.configure(bg="#0a0e13")
    cv = tk.Canvas(root, width=8 * CS, height=8 * CS, bg="#0a0e13", highlightthickness=0); cv.grid(row=0, column=0, rowspan=2, padx=16, pady=16)
    out = tk.Label(root, text="?", font=("Consolas", 120, "bold"), fg="#39efc9", bg="#0a0e13"); out.grid(row=0, column=1, padx=24)
    info = tk.Label(root, text=f"{cd['n_gate']:,} gates · forward pass on the pfc\ndraw with the mouse · C clears", font=("Consolas", 12), fg="#8996a6", bg="#0a0e13"); info.grid(row=1, column=1)
    rects = [cv.create_rectangle((i % 8) * CS, (i // 8) * CS, (i % 8) * CS + CS, (i // 8) * CS + CS, fill="#111923", outline="#1c2732") for i in range(64)]

    def classify():
        cls, sc = pulse(cd, grid); out.config(text=str(cls))            # ONE clock pulse = the operator decides

    def paint(ev):
        c = ev.x // CS; r = ev.y // CS
        if 0 <= c < 8 and 0 <= r < 8:
            i = r * 8 + c; grid[i] = 1; cv.itemconfigure(rects[i], fill="#39efc9"); classify()

    def clear(_=None):
        for i in range(64): grid[i] = 0; cv.itemconfigure(rects[i], fill="#111923")
        out.config(text="?")
    cv.bind("<Button-1>", paint); cv.bind("<B1-Motion>", paint); root.bind("c", clear); root.bind("<Escape>", lambda e: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    print("Muhlnickel operator — draw a digit with the mouse; the Muhlnickel classifies each stroke. C clears, Esc quits.", flush=True)
    root.mainloop(); return 0


def main():
    if "--test" in sys.argv[1:] or "--bake" in sys.argv[1:]:
        return test()
    return play()


if __name__ == "__main__":
    raise SystemExit(main())
