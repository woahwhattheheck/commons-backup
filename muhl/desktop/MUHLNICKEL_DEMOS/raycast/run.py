#!/usr/bin/env python3
"""MUHLNICKEL DEMO — 3D Raycaster (80x60, 384,396 gates)

A REAL first-person raycaster: rays marched through a maze, walls projected to columns,
distance-shaded, multi-colour walls. The ENTIRE raycasting engine is ONE prefabricated
gate netlist in pfc_raycast.pfc. Player state (x, y, angle) lives in the circuit's
storage. Each pulse the circuit moves the player, casts every ray, and paints the
full framebuffer. The host routes WASD keys in and displays the result.
WASD/arrows to move. Esc to quit.

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

PFC_PATH = os.path.join(SBX, "pfc_raycast.pfc")
MAGIC = b"PFCRAY01"
OPN = {1: "and", 2: "or", 3: "xor", 4: "not", 5: "nand"}
SW, SH = 80, 60
START = (3 * 256 + 128, 3 * 256 + 128, 0)  # px, py (Q8.8), angle


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
    return dict(run=run, outs=outs, n_in=n_in, n_gate=n_gate)


def pulse(cd, px, py, ang, keys):
    """ONE clock pulse: route keys in, the circuit casts every ray and paints the framebuffer."""
    inp = ([(px >> i) & 1 for i in range(16)] +
           [(py >> i) & 1 for i in range(16)] +
           [(ang >> i) & 1 for i in range(8)] +
           [(keys >> i) & 1 for i in range(6)])
    v = cd["run"](inp, 1)
    o = cd["outs"]
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    npx = sum(bit(o[i]) << i for i in range(16))
    npy = sum(bit(o[16 + i]) << i for i in range(16))
    nang = sum(bit(o[32 + i]) << i for i in range(8))
    fb = bytes(sum(bit(o[40 + p * 8 + i]) << i for i in range(8)) for p in range(SW * SH))
    return (npx, npy, nang), fb


def palette():
    pal = [(0, 0, 0)] * 256
    for r in range(16):  # ceiling (deep blue)
        pal[1 + r] = (8, 10 + (15 - r), 22 + (15 - r) * 3)
    for r in range(16):  # floor (grey)
        pal[17 + r] = (22 + r, 22 + r, 26 + r)
    wallcol = {1: (210, 70, 60), 2: (80, 200, 110), 3: (90, 150, 235)}
    for t in (1, 2, 3):
        base = 33 + (t - 1) * 16
        br, bg, bb = wallcol[t]
        for s in range(16):
            f = (16 - s) / 16.0
            pal[base + s] = (int(br * f), int(bg * f), int(bb * f))
    return pal


def statefile():
    return os.path.join(SBX, "pfc_raycast_state.bin")


def read_state():
    p = statefile()
    if not os.path.exists(p):
        return START
    with open(p, "rb") as f:
        b = f.read(5)
    if len(b) != 5:
        return START
    return (b[0] | (b[1] << 8), b[2] | (b[3] << 8), b[4])


def write_state(px, py, ang):
    with open(statefile(), "wb") as f:
        f.write(bytes((px & 255, (px >> 8) & 255, py & 255, (py >> 8) & 255, ang & 255)))


def play():
    import tkinter as tk
    import pfc_blit

    cd = load()
    pal = palette()
    px, py, ang = read_state()
    write_state(px, py, ang)

    root = tk.Tk()
    root.title("MUHLNICKEL  Raycaster 3D  --  384,396 gates  --  host = clock + monitor only")
    root.configure(bg="#05070a")
    scale = max(1, min(920 // SW, 720 // SH))
    W, H = SW * scale, SH * scale
    root.geometry(f"{W}x{H}")

    canvas = tk.Canvas(root, width=W, height=H, bg="#05070a", highlightthickness=0)
    canvas.pack()
    img_id = canvas.create_image(0, 0, anchor="nw")
    hud = canvas.create_text(12, 8, anchor="nw", fill="#39efc9", font=("Consolas", 12), text="")
    st = {"px": px, "py": py, "ang": ang, "keys": set(), "frames": 0}
    KMAP = {"w": 0, "s": 1, "a": 2, "d": 3, "Up": 0, "Down": 1, "Left": 2, "Right": 3}

    def render(fb):
        rgb = bytearray(SW * SH * 3)
        for i, ix in enumerate(fb):
            r, gg, b = pal[ix]
            o = i * 3
            rgb[o] = r; rgb[o + 1] = gg; rgb[o + 2] = b
        base = pfc_blit.photo(SW, SH, rgb)
        big = base.zoom(scale)
        canvas.itemconfigure(img_id, image=big)
        canvas.image_big = big
        canvas.itemconfigure(hud, text=(
            f"MUHLNICKEL RAYCASTER -- {cd['n_gate']:,} gates | {SW}x{SH} | host = clock + monitor only\n"
            f"frame {st['frames']:,}   W/A/S/D move | Esc/X close | F11 fullscreen"))

    def step():
        keys = 0
        for k in st["keys"]:
            if k in KMAP:
                keys |= 1 << KMAP[k]
        (npx, npy, nang), fb = pulse(cd, st["px"], st["py"], st["ang"], keys)
        write_state(npx, npy, nang)
        st["px"], st["py"], st["ang"] = npx, npy, nang
        st["frames"] += 1
        render(fb)
        root.after(1, step)

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
    print("MUHLNICKEL Raycaster -- W/A/S/D to move, Esc or X to close.", flush=True)
    step()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(play())
