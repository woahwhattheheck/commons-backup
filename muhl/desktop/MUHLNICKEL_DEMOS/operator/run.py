#!/usr/bin/env python3
"""MUHLNICKEL DEMO — Operator (neural forward pass, 2,734 gates)

A real NEURAL FORWARD PASS baked as gates: an 8x8 glyph -> linear layer (dot the
input against 10 learned digit templates) -> argmax -> predicted digit. The whole
forward pass is ONE gate netlist in pfc_operator.pfc. The host routes the drawn
pixels in as signals and pulses the clock; the circuit computes the matmul + argmax
and outputs the decision. Draw a digit with the mouse, the circuit classifies it.
C to clear, Esc to quit.

NOTE: compile_ripple is a HOST-SIDE DISPLAY CRUTCH — the host transcribes
the gate evaluations for display. The circuit is the computation.
"""
import os, struct, sys

HOST_DIR = os.path.normpath(os.path.join(os.environ.get("LOCALDEVICEAGENT",
    r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent"), "host"))
SBX = os.environ.get("PFC_SBX", r"C:\llm\sdc_sandbox")
sys.path.insert(0, HOST_DIR)
sys.path.insert(0, SBX)

import sdc_cc as CC

PFC_PATH = os.path.join(SBX, "pfc_operator.pfc")
MAGIC = b"PFCOPR01"
OPN = {1: "and", 2: "or", 3: "xor", 4: "not", 5: "nand"}


def load():
    with open(PFC_PATH, "rb") as f:
        blob = f.read()
    assert blob[:8] == MAGIC
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8)
    p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p)
        p += 9
        gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in)
    return dict(run=cc.compile_ripple(gates, n_wire), outs=outs, n_gate=n_gate)


def pulse(cd, inp):
    """ONE clock pulse: route 64 pixels in, the circuit computes matmul + argmax."""
    v = cd["run"](list(inp), 1)
    o = cd["outs"]
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    cls = sum(bit(o[i]) << i for i in range(4))
    sc = sum(bit(o[4 + i]) << i for i in range(7))
    return cls, sc


def play():
    import tkinter as tk

    cd = load()
    grid = [0] * 64
    CS = 44

    root = tk.Tk()
    root.title("MUHLNICKEL  Operator  --  2,734 gates  --  neural forward pass on the muhlnickel")
    root.configure(bg="#0a0e13")

    cv = tk.Canvas(root, width=8 * CS, height=8 * CS, bg="#0a0e13", highlightthickness=0)
    cv.grid(row=0, column=0, rowspan=2, padx=16, pady=16)

    out = tk.Label(root, text="?", font=("Consolas", 120, "bold"), fg="#39efc9", bg="#0a0e13")
    out.grid(row=0, column=1, padx=24)

    info = tk.Label(root, text=(
        f"{cd['n_gate']:,} gates | forward pass on the muhlnickel\n"
        f"draw with the mouse | C clears"),
        font=("Consolas", 12), fg="#8996a6", bg="#0a0e13")
    info.grid(row=1, column=1)

    rects = [cv.create_rectangle(
        (i % 8) * CS, (i // 8) * CS, (i % 8) * CS + CS, (i // 8) * CS + CS,
        fill="#111923", outline="#1c2732") for i in range(64)]

    def classify():
        cls, sc = pulse(cd, grid)
        out.config(text=str(cls))

    def paint(ev):
        c = ev.x // CS
        r = ev.y // CS
        if 0 <= c < 8 and 0 <= r < 8:
            i = r * 8 + c
            grid[i] = 1
            cv.itemconfigure(rects[i], fill="#39efc9")
            classify()

    def clear(_=None):
        for i in range(64):
            grid[i] = 0
            cv.itemconfigure(rects[i], fill="#111923")
        out.config(text="?")

    cv.bind("<Button-1>", paint)
    cv.bind("<B1-Motion>", paint)
    root.bind("c", clear)
    root.bind("<Escape>", lambda e: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    print("MUHLNICKEL Operator -- draw a digit with the mouse, the muhlnickel classifies it. C clears, Esc quits.", flush=True)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(play())
