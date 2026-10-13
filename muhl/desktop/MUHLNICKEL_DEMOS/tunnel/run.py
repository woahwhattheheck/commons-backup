#!/usr/bin/env python3
"""MUHLNICKEL DEMO — Tunnel (128x96, 828 gates)

A SELF-CLOCKED animated perspective tunnel. The circuit's only state is an 8-bit
time counter. Each pulse it advances time and PAINTS the whole framebuffer: a
rainbow tunnel flying forward. Per pixel: idx = (depth + time + angle/8) & 255,
with polar geometry baked as constants and TIME as the circuit's own state.
The palette is the DAC (indexed colour -> RGB). Host = pulse + blit only.
Sit back and watch. Esc to quit.

NOTE: compile_ripple is a HOST-SIDE DISPLAY CRUTCH — the host transcribes
the gate evaluations for display. The circuit is the computation.
"""
import os, struct, sys, colorsys

HOST_DIR = os.path.normpath(os.path.join(os.environ.get("LOCALDEVICEAGENT",
    r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent"), "host"))
SBX = os.environ.get("PFC_SBX", r"C:\llm\sdc_sandbox")
sys.path.insert(0, HOST_DIR)
sys.path.insert(0, SBX)

import sdc_cc as CC

PFC_PATH = os.path.join(SBX, "pfc_tunnel.pfc")
MAGIC = b"PFCTUN01"
OPN = {1: "and", 2: "or", 3: "xor", 4: "not", 5: "nand"}
SW, SH = 128, 96


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
    run = cc.compile_ripple(gates, n_wire)
    return dict(run=run, outs=outs, n_gate=n_gate)


def pulse(cd, t):
    """ONE clock pulse: advance time, paint the full 128x96 framebuffer."""
    v = cd["run"]([(t >> i) & 1 for i in range(8)], 1)
    o = cd["outs"]
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    nt = sum(bit(o[i]) << i for i in range(8))
    fb = bytes(sum(bit(o[8 + p * 8 + i]) << i for i in range(8)) for p in range(SW * SH))
    return nt, fb


def palette():
    pal = [(0, 0, 0)] * 256
    for i in range(256):
        r, g, b = colorsys.hsv_to_rgb((i / 256.0) % 1.0, 0.85, 1.0)
        pal[i] = (int(r * 255), int(g * 255), int(b * 255))
    return pal


def play():
    import tkinter as tk
    import pfc_blit

    cd = load()
    pal = palette()

    root = tk.Tk()
    root.title("MUHLNICKEL  Tunnel  --  828 gates  --  self-clocked, host = pulse + blit only")
    root.configure(bg="#000")
    scale = max(1, min(920 // SW, 720 // SH))
    W, H = SW * scale, SH * scale
    root.geometry(f"{W}x{H}")

    canvas = tk.Canvas(root, width=W, height=H, bg="#000", highlightthickness=0)
    canvas.pack()
    img_id = canvas.create_image(0, 0, anchor="nw")
    st = {"t": 0}

    def esc(_=None):
        if root.attributes("-fullscreen"):
            root.attributes("-fullscreen", False)
        else:
            root.destroy()

    root.bind("<Escape>", esc)
    root.bind("q", lambda e: root.destroy())
    root.bind("<F11>", lambda e: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    def step():
        nt, fb = pulse(cd, st["t"])
        st["t"] = nt
        rgb = bytearray(SW * SH * 3)
        for i, ix in enumerate(fb):
            r, g, b = pal[ix]
            o = i * 3
            rgb[o] = r; rgb[o + 1] = g; rgb[o + 2] = b
        base = pfc_blit.photo(SW, SH, rgb)
        big = base.zoom(scale)
        canvas.itemconfigure(img_id, image=big)
        canvas.image_big = big
        root.after(1, step)

    print("MUHLNICKEL Tunnel -- self-clocked animation. Esc or X to close.", flush=True)
    step()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(play())
