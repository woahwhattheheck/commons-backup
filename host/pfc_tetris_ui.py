#!/usr/bin/env python3
"""host/pfc_tetris_ui.py — RENDER-ONLY monitor for Muhlnickel Tetris (owner 07-20: host = clock + monitor only).

No game logic here. Each frame: (1) route the held keys in as SIGNALS, (2) PULSE the clock (one bounded ripple — the pfc
advances the whole game: move/rotate/gravity/collision/line-clear/spawn), (3) blit the framebuffer the pfc painted through
the fixed palette (the DAC). The `root.after` interval is the display CLOCK's rate (how often we pulse) — not a throttle on
the pfc, which computes each pulse at its own speed.
"""
import base64


def play(load, pulse, new_game, PAL, SW, SH):
    try:
        import tkinter as tk, pfc_blit
    except Exception as e:
        print(f"tkinter unavailable ({e}). Verify headless: python host/pfc_tetris.py --test"); return 1
    cd = load(); st = {"s": new_game(0xACE1), "keys": set(), "frames": 0}
    root = tk.Tk(); root.title("pfc Tetris  —  Esc / X to close, F11 fullscreen"); root.configure(bg="#0a0e13")
    scale = max(1, min(760 // SW, 760 // SH)); W, H = SW * scale, SH * scale; root.geometry(f"{W}x{H}")
    canvas = tk.Canvas(root, width=W, height=H, bg="#0a0e13", highlightthickness=0); canvas.pack()
    img_id = canvas.create_image(0, 0, anchor="nw")
    hud = canvas.create_text(10, 8, anchor="nw", fill="#39efc9", font=("Consolas", 11), text="")
    KMAP = {"Left": 0, "a": 0, "Right": 1, "d": 1, "Up": 2, "w": 2, "Down": 3, "s": 3}

    def render(fb):
        rgb = bytearray(SW * SH * 3)
        for i, ix in enumerate(fb):
            r, g, b = PAL[ix & 15]; o = i * 3; rgb[o] = r; rgb[o + 1] = g; rgb[o + 2] = b
        base = pfc_blit.photo(SW, SH, rgb)
        big = base.zoom(scale); canvas.itemconfigure(img_id, image=big); canvas.image_big = big
        canvas.itemconfigure(hud, text=(f"pfc TETRIS — {cd['n_gate']:,} gates · host = clock + monitor only\n"
                                        f"frame {st['frames']:,}   <- -> move · Up rotate · Down drop · Esc/X close"))

    def step():
        keys = 0
        for k in st["keys"]:
            if k in KMAP:
                keys |= 1 << KMAP[k]
        s, fb = pulse(cd, st["s"], keys)                   # ONE clock pulse: the pfc advances the whole game
        st["s"] = s; st["frames"] += 1
        render(fb)
        root.after(45, step)                               # display clock rate (~22 Hz); the pfc computes each pulse full-speed

    root.bind("<KeyPress>", lambda e: st["keys"].add(e.keysym))
    root.bind("<KeyRelease>", lambda e: st["keys"].discard(e.keysym))
    def esc(_=None):
        if root.attributes("-fullscreen"): root.attributes("-fullscreen", False)
        else: root.destroy()
    root.bind("<Escape>", esc); root.bind("q", lambda e: root.destroy())
    root.bind("<F11>", lambda e: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    print("Muhlnickel Tetris — Arrows/WASD to play, Esc or the X to close.", flush=True)
    step(); root.mainloop(); return 0
