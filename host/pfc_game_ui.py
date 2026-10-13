#!/usr/bin/env python3
"""host/pfc_game_ui.py — THE RENDER-ONLY HARNESS for Muhlnickel games (owner 07-20: "the harness is only allowed to render").

This file contains NO game logic and NO game math. Its only jobs, per frame:
  (1) PULSE THE CLOCK  — call tick(): one baked next-state propagation on the pfc (owner: "just pulse the clock").
  (2) ROUTE INPUT IN   — write the player's clicks/keys into the pfc's state (one-way).
  (3) RENDER           — read the pfc's state bytes and blit them: a fixed display palette (indexed colour -> RGB, exactly
                         what display hardware does) + nearest-neighbour upscale to fullscreen. No rules are evaluated here.

State lives in the pfc's own storage (a sandbox state file); each frame we read it, pulse, and latch it back — the
host holds none of the game state. `play()` is the live fullscreen loop; `smoke()` renders frames headless to a PNG so the
compute + render path can be verified without opening a window.
"""
import base64, os, struct, sys, time, zlib, random
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)

SBX = PFCP.SBX


# ---- fixed DISPLAY palettes: cell value -> RGB. This is display shading (indexed->RGB), not game logic. ----
def palette(name="life"):
    pal = [(9, 12, 17)] * 16                              # dead/off = near-black ground
    if name == "brain":
        pal[1] = (128, 245, 224)                          # on = bright cyan
        pal[2] = (46, 96, 156)                            # dying = dim blue front
        return pal
    hot = [(57, 239, 201), (74, 226, 214), (110, 210, 226), (150, 190, 232),
           (190, 168, 226), (224, 140, 200), (240, 110, 150), (255, 92, 96)]   # fresh->old heat trail (Life)
    for h in range(8):
        pal[1 | (h << 1)] = hot[h]
    return pal


def frame_rgb(grid, pal):
    buf = bytearray(len(grid) * 3)
    for i, c in enumerate(grid):
        r, g, b = pal[c & 15]; o = i * 3; buf[o] = r; buf[o + 1] = g; buf[o + 2] = b
    return bytes(buf)


def statefile(name): return os.path.join(SBX, f"pfc_{name}_state.bin")


def seed_random(N, density=0.24):
    return [(1 if random.random() < density else 0) for _ in range(N)]


def read_state(name, N):
    p = statefile(name)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        b = f.read(N)
    return list(b) if len(b) == N else None


def write_state(name, grid):
    with open(statefile(name), "wb") as f:
        f.write(bytes(c & 15 for c in grid))


# ============================ headless verification: dump frames to a PNG I can look at ============================
def _png(path, rgb, W, H, scale):
    sw, sh = W * scale, H * scale
    rows = []
    for y in range(H):
        row = bytearray()
        for x in range(W):
            o = (y * W + x) * 3
            row += rgb[o:o + 3] * scale                    # repeat each pixel `scale` times horizontally
        line = b"\x00" + bytes(row)                        # filter byte + one scanline
        for _ in range(scale):                             # repeat the whole scanline `scale` times vertically
            rows.append(line)
    raw = b"".join(rows)
    def ch(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", sw, sh, 8, 2, 0, 0, 0)) +
           ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def smoke(name, load, tick, GAMES, out_png):
    cd = load(name); GW, GH = cd["GW"], cd["GH"]; N = GW * GH; pal = palette(name)
    random.seed(7)
    grid = seed_random(N, 0.24)
    for _ in range(14):                                    # let some structure emerge
        grid = tick(cd, grid)
    _png(out_png, frame_rgb(grid, pal), GW, GH, 8)
    print(f"  smoke: rendered a live Muhlnickel frame -> {out_png} ({os.path.getsize(out_png):,} B, {GW*8}x{GH*8}).", flush=True)
    return 0


# ============================ the live fullscreen render-only harness ============================
def play(name, load, tick, GAMES):
    try:
        import tkinter as tk, pfc_blit
    except Exception as e:
        print(f"tkinter unavailable ({e}). Run headless: python host/pfc_game.py {name} --smoke"); return 1
    cd = load(name); GW, GH = cd["GW"], cd["GH"]; N = GW * GH; pal = palette(name)
    spec = GAMES[name]
    grid = read_state(name, N) or seed_random(N)
    write_state(name, grid)

    root = tk.Tk(); root.title(spec["title"] + "  —  Esc / X to close, F11 fullscreen"); root.configure(bg="#05070a")
    scale = max(1, min(760 // GW, 720 // GH)); W, H = GW * scale, GH * scale
    root.geometry(f"{W}x{H}")
    state = {"fs": False, "paused": False, "gen": 0, "scale": scale, "grid": grid, "draw": 0}

    canvas = tk.Canvas(root, width=W, height=H, bg="#05070a", highlightthickness=0); canvas.pack()
    img = tk.PhotoImage(width=GW, height=GH)
    img_id = canvas.create_image(0, 0, anchor="nw", image=img)
    hud = canvas.create_text(12, 8, anchor="nw", fill="#39efc9", font=("Consolas", 13),
                             text="")

    def render():
        rgb = frame_rgb(state["grid"], pal)                # read state bytes -> pixels (display palette only)
        base = pfc_blit.photo(GW, GH, rgb)
        z = state["scale"]; big = base.zoom(z)
        canvas.itemconfigure(img_id, image=big); canvas.image_big = big     # keep ref
        canvas.itemconfigure(hud, text=(f"{spec['title']}\nGENERATION {state['gen']:,}   ·   "
                                        f"{cd['n_gate']:,} gates   ·   {GW}x{GH}   ·   host = clock + render only"
                                        + ("   ·   PAUSED" if state["paused"] else "")))

    def step():
        if not state["paused"]:
            g = read_state(name, N)                        # state from the pfc's storage
            g = tick(cd, g)                                # ONE clock pulse = one baked propagation on the pfc
            write_state(name, g)                           # latch next state back to storage
            state["grid"] = g; state["gen"] += 1
            render()
        root.after(1, step)                                # pulse as fast as we can (no artificial cap)

    def cell_at(ev):
        z = state["scale"]; cx = ev.x // z; cy = ev.y // z
        return (cx, cy) if 0 <= cx < GW and 0 <= cy < GH else (None, None)

    def paint(ev):                                         # mouse = route input in: seed live cells into pfc storage
        cx, cy = cell_at(ev)
        if cx is None:
            return
        g = read_state(name, N)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                x = (cx + dx) % GW; y = (cy + dy) % GH; g[y * GW + x] = 1
        write_state(name, g); state["grid"] = g; render()

    def reseed(_=None):
        g = seed_random(N); write_state(name, g); state["grid"] = g; state["gen"] = 0; render()

    def clear(_=None):
        g = [0] * N; write_state(name, g); state["grid"] = g; state["gen"] = 0; render()

    def toggle_pause(_=None): state["paused"] = not state["paused"]; render()
    def toggle_fs(_=None): state["fs"] = not state["fs"]; root.attributes("-fullscreen", state["fs"])
    def quit_(_=None):
        if root.attributes("-fullscreen"): root.attributes("-fullscreen", False); state["fs"] = False
        else: root.destroy()

    root.bind("<Button-1>", paint); root.bind("<B1-Motion>", paint)
    root.bind("r", reseed); root.bind("c", clear); root.bind("<space>", toggle_pause)
    root.bind("f", toggle_fs); root.bind("<F11>", toggle_fs); root.bind("<Escape>", quit_); root.bind("q", lambda e: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    render()
    print(f"playing '{name}' — fullscreen. click/drag = seed · space = pause · r = reseed · c = clear · f = window · Esc = quit", flush=True)
    root.after(200, step); root.mainloop()
    return 0
