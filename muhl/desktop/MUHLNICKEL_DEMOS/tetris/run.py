#!/usr/bin/env python3
"""MUHLNICKEL DEMO — Tetris (10x20 board, 46,353 gates)

The WHOLE game is ONE prefabricated gate netlist: board state, 7 tetrominoes x 4
rotations, gravity, edge-detected input, collision, LINE-CLEAR COMPACTION, LFSR
random spawning, and game-over restart. Stored in pfc_tetris.pfc.
The host does TWO things: route key signals in, pulse the clock, and render.
Arrows/WASD to play. Esc to quit.

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

PFC_PATH = os.path.join(SBX, "pfc_tetris.pfc")
MAGIC = b"PFCTET01"
OPN = {1: "and", 2: "or", 3: "xor", 4: "not", 5: "nand"}

BW, BH = 10, 20
NC = BW * BH
CS = 6
SW, SH = BW * CS, BH * CS  # 60 x 120 screen pixels
NB = NC * 3  # board bits

# State layout: board 600 | typ 3 | rot 2 | px 6 | py 5 | gcnt 5 | prev 4 | lfsr 16 | over 1 = 642
def sl():
    o = {}; p = 0
    for nm, w in [("board", NB), ("typ", 3), ("rot", 2), ("px", 6), ("py", 5),
                  ("gcnt", 5), ("prev", 4), ("lfsr", 16), ("over", 1)]:
        o[nm] = (p, w); p += w
    return o, p
LAYOUT, NSTATE = sl()

# Palette: cell colours (0=empty, 1-7=piece colours, 8=grid line)
PAL = [(12, 14, 20), (60, 220, 230), (235, 215, 70), (180, 90, 220), (90, 210, 110),
       (230, 80, 80), (80, 130, 235), (235, 150, 60), (34, 38, 48)] + [(0, 0, 0)] * 7
SPAWNX = 3


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


def new_game(seed=0xACE1):
    return dict(board=[0] * NC, typ=seed % 7, rot=0, px=SPAWNX, py=0,
                gcnt=0, prev=0, lfsr=seed, over=0)


def state_to_bits(s):
    bits = [0] * NSTATE
    for i in range(NC):
        for k in range(3):
            bits[i * 3 + k] = (s["board"][i] >> k) & 1
    def put(nm, val):
        p, w = LAYOUT[nm]
        for i in range(w):
            bits[p + i] = (val >> i) & 1
    put("typ", s["typ"]); put("rot", s["rot"]); put("px", s["px"] & 63)
    put("py", s["py"]); put("gcnt", s["gcnt"]); put("prev", s["prev"])
    put("lfsr", s["lfsr"]); put("over", s["over"])
    return bits


def bits_to_state(v, o, bit):
    def gv(nm):
        p, w = LAYOUT[nm]
        return sum(bit(o[p + i]) << i for i in range(w))
    board = [sum(bit(o[i * 3 + k]) << k for k in range(3)) for i in range(NC)]
    px = gv("px")
    px = px - 64 if px >= 32 else px  # 6-bit two's complement
    return dict(board=board, typ=gv("typ"), rot=gv("rot"), px=px, py=gv("py"),
                gcnt=gv("gcnt"), prev=gv("prev"), lfsr=gv("lfsr"), over=gv("over"))


def pulse(cd, s, keys):
    """ONE clock pulse: route keys in, advance the entire game one step."""
    inp = state_to_bits(s) + [(keys >> i) & 1 for i in range(4)]
    v = cd["run"](inp, 1)
    o = cd["outs"]
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    ns = bits_to_state(v, o, bit)
    fb = bytes(sum(bit(o[NSTATE + p * 4 + i]) << i for i in range(4)) for p in range(SW * SH))
    return ns, fb


def play():
    import tkinter as tk
    import pfc_blit

    cd = load()
    st = {"s": new_game(0xACE1), "keys": set(), "frames": 0}

    root = tk.Tk()
    root.title("MUHLNICKEL  Tetris  --  46,353 gates  --  host = clock + monitor only")
    root.configure(bg="#0a0e13")
    scale = max(1, min(760 // SW, 760 // SH))
    W, H = SW * scale, SH * scale
    root.geometry(f"{W}x{H}")

    canvas = tk.Canvas(root, width=W, height=H, bg="#0a0e13", highlightthickness=0)
    canvas.pack()
    img_id = canvas.create_image(0, 0, anchor="nw")
    hud = canvas.create_text(10, 8, anchor="nw", fill="#39efc9", font=("Consolas", 11), text="")
    KMAP = {"Left": 0, "a": 0, "Right": 1, "d": 1, "Up": 2, "w": 2, "Down": 3, "s": 3}

    def render(fb):
        rgb = bytearray(SW * SH * 3)
        for i, ix in enumerate(fb):
            r, g, b = PAL[ix & 15]
            o = i * 3
            rgb[o] = r; rgb[o + 1] = g; rgb[o + 2] = b
        base = pfc_blit.photo(SW, SH, rgb)
        big = base.zoom(scale)
        canvas.itemconfigure(img_id, image=big)
        canvas.image_big = big
        canvas.itemconfigure(hud, text=(
            f"MUHLNICKEL TETRIS -- {cd['n_gate']:,} gates | host = clock + monitor only\n"
            f"frame {st['frames']:,}   <- -> move | Up rotate | Down drop | Esc/X close"))

    def step():
        keys = 0
        for k in st["keys"]:
            if k in KMAP:
                keys |= 1 << KMAP[k]
        s, fb = pulse(cd, st["s"], keys)
        st["s"] = s
        st["frames"] += 1
        render(fb)
        root.after(45, step)  # display clock ~22 Hz

    root.bind("<KeyPress>", lambda e: st["keys"].add(e.keysym))
    root.bind("<KeyRelease>", lambda e: st["keys"].discard(e.keysym))

    def esc(_=None):
        if root.attributes("-fullscreen"):
            root.attributes("-fullscreen", False)
        else:
            root.destroy()

    root.bind("<Escape>", esc)
    root.bind("q", lambda e: root.destroy())
    root.bind("<F11>", lambda e: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    print("MUHLNICKEL Tetris -- Arrows/WASD to play, Esc or X to close.", flush=True)
    step()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(play())
