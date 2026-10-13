#!/usr/bin/env python3
"""MUHLNICKEL DEMO — Conway's Game of Life (64x64, 4 bits/cell, 270,336 gates)

The ENTIRE game logic is a prefabricated gate netlist stored in pfc_life.pfc.
The host does TWO things: pulse the clock (one bounded ripple) and render the output.
Click/drag to seed cells, Space to pause, R to reseed, C to clear, Esc to quit.

NOTE: compile_ripple is a HOST-SIDE DISPLAY CRUTCH — the host is transcribing
the circuit's gate evaluations so you can see the output on screen. The circuit
itself is the computation; this rendering is the monitor, not the machine.
"""
import os, struct, sys, random

# --- path setup: find sdc_cc + pfc_blit ---
HOST_DIR = os.path.normpath(os.path.join(os.environ.get("LOCALDEVICEAGENT",
    r"C:\Users\lucys\OneDrive\Desktop\LocalDeviceAgent"), "host"))
SBX = os.environ.get("PFC_SBX", r"C:\llm\sdc_sandbox")
sys.path.insert(0, HOST_DIR)
sys.path.insert(0, SBX)

import sdc_cc as CC

# --- constants ---
PFC_PATH = os.path.join(SBX, "pfc_life.pfc")
MAGIC = b"PFCGAME1"
OPN = {1: "and", 2: "or", 3: "xor", 4: "not", 5: "nand"}
GW, GH = 64, 64
BITS = 4  # alive(1) + heat(3)


def load():
    """Load the prefabricated Life circuit from storage. No fabrication."""
    with open(PFC_PATH, "rb") as f:
        blob = f.read()
    assert blob[:8] == MAGIC, f"bad magic: {blob[:8]}"
    n_in, n_wire, n_gate, n_out, gw, gh = struct.unpack_from("<IIIIII", blob, 8)
    assert gw == GW and gh == GH
    p = 8 + 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p)
        p += 9
        gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in)
    run = cc.compile_ripple(gates, n_wire)
    return dict(GW=gw, GH=gh, n_in=n_in, outs=outs, run=run, n_gate=n_gate, bits=BITS)


def grid_to_bits(grid, bits):
    out = [0] * (len(grid) * bits)
    for i, c in enumerate(grid):
        for k in range(bits):
            out[i * bits + k] = (c >> k) & 1
    return out


def out_to_grid(v, outs, bits):
    grid = []
    for i in range(len(outs) // bits):
        c = 0
        for k in range(bits):
            o = outs[i * bits + k]
            c |= (0 if o == 0 else 1 if o == 1 else v[o] & 1) << k
        grid.append(c)
    return grid


def tick(cd, grid):
    """ONE clock pulse: one bounded ripple propagation on the circuit."""
    b = cd["bits"]
    return out_to_grid(cd["run"](grid_to_bits(grid, b), 1), cd["outs"], b)


def palette():
    pal = [(9, 12, 17)] * 16  # dead = near-black
    hot = [(57, 239, 201), (74, 226, 214), (110, 210, 226), (150, 190, 232),
           (190, 168, 226), (224, 140, 200), (240, 110, 150), (255, 92, 96)]
    for h in range(8):
        pal[1 | (h << 1)] = hot[h]
    return pal


def frame_rgb(grid, pal):
    buf = bytearray(len(grid) * 3)
    for i, c in enumerate(grid):
        r, g, b = pal[c & 15]
        o = i * 3
        buf[o] = r; buf[o + 1] = g; buf[o + 2] = b
    return bytes(buf)


def seed_random(N, density=0.24):
    return [(1 if random.random() < density else 0) for _ in range(N)]


def statefile():
    return os.path.join(SBX, "pfc_life_state.bin")


def read_state(N):
    p = statefile()
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        b = f.read(N)
    return list(b) if len(b) == N else None


def write_state(grid):
    with open(statefile(), "wb") as f:
        f.write(bytes(c & 15 for c in grid))


def play():
    import tkinter as tk
    import pfc_blit

    cd = load()
    N = GW * GH
    pal = palette()
    grid = read_state(N) or seed_random(N)
    write_state(grid)

    root = tk.Tk()
    root.title("MUHLNICKEL  Conway's Life  --  270,336 gates  --  host = clock + render only")
    root.configure(bg="#05070a")
    scale = max(1, min(760 // GW, 720 // GH))
    W, H = GW * scale, GH * scale
    root.geometry(f"{W}x{H}")
    state = {"fs": False, "paused": False, "gen": 0, "scale": scale, "grid": grid, "draw": 0}

    canvas = tk.Canvas(root, width=W, height=H, bg="#05070a", highlightthickness=0)
    canvas.pack()
    img = tk.PhotoImage(width=GW, height=GH)
    img_id = canvas.create_image(0, 0, anchor="nw", image=img)
    hud = canvas.create_text(12, 8, anchor="nw", fill="#39efc9", font=("Consolas", 13), text="")

    def render():
        rgb = frame_rgb(state["grid"], pal)
        base = pfc_blit.photo(GW, GH, rgb)
        z = state["scale"]
        big = base.zoom(z)
        canvas.itemconfigure(img_id, image=big)
        canvas.image_big = big
        canvas.itemconfigure(hud, text=(
            f"MUHLNICKEL  Conway's Life\n"
            f"GENERATION {state['gen']:,}   |   {cd['n_gate']:,} gates   |   {GW}x{GH}   |   host = clock + render only"
            + ("   |   PAUSED" if state["paused"] else "")))

    def step():
        if not state["paused"]:
            g = read_state(N)
            g = tick(cd, g)  # ONE clock pulse
            write_state(g)
            state["grid"] = g
            state["gen"] += 1
            render()
        root.after(1, step)

    def paint(ev):
        z = state["scale"]
        cx, cy = ev.x // z, ev.y // z
        if not (0 <= cx < GW and 0 <= cy < GH):
            return
        g = read_state(N)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                x = (cx + dx) % GW
                y = (cy + dy) % GH
                g[y * GW + x] = 1
        write_state(g)
        state["grid"] = g
        render()

    def reseed(_=None):
        g = seed_random(N)
        write_state(g)
        state["grid"] = g
        state["gen"] = 0
        render()

    def clear(_=None):
        g = [0] * N
        write_state(g)
        state["grid"] = g
        state["gen"] = 0
        render()

    def toggle_pause(_=None):
        state["paused"] = not state["paused"]
        render()

    def toggle_fs(_=None):
        state["fs"] = not state["fs"]
        root.attributes("-fullscreen", state["fs"])

    def quit_(_=None):
        if root.attributes("-fullscreen"):
            root.attributes("-fullscreen", False)
            state["fs"] = False
        else:
            root.destroy()

    root.bind("<Button-1>", paint)
    root.bind("<B1-Motion>", paint)
    root.bind("r", reseed)
    root.bind("c", clear)
    root.bind("<space>", toggle_pause)
    root.bind("f", toggle_fs)
    root.bind("<F11>", toggle_fs)
    root.bind("<Escape>", quit_)
    root.bind("q", lambda e: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    render()
    print("MUHLNICKEL Life -- click/drag = seed | space = pause | r = reseed | c = clear | Esc = quit", flush=True)
    root.after(200, step)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(play())
