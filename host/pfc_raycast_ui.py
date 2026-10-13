#!/usr/bin/env python3
"""host/pfc_raycast_ui.py — RENDER-ONLY monitor for the Muhlnickel raycaster (owner 07-20: host = clock + monitor only).

No game logic, no 3D math, no rendering here. Each frame this harness does exactly three things:
  (1) ROUTE INPUT SIGNALS IN — turn the held keys (W/A/S/D) into the pfc's key-signal bits.
  (2) PULSE THE CLOCK — one bounded ripple: the pfc moves the player, casts every ray, and paints the framebuffer.
  (3) DISPLAY — read the pfc's palette-indexed framebuffer and blit it through the fixed palette (the DAC) + upscale.
The player state lives in the pfc's storage (a state file); we read it, pulse, latch it back. That's all the host does.
"""
import base64, os, struct

SBX = "C:/llm/sdc_sandbox"; STATE = os.path.join(SBX, "pfc_raycast_state.bin")


def read_state(start):
    if not os.path.exists(STATE):
        return start
    with open(STATE, "rb") as f:
        b = f.read(5)
    if len(b) != 5:
        return start
    return (b[0] | (b[1] << 8), b[2] | (b[3] << 8), b[4])


def write_state(px, py, ang):
    with open(STATE, "wb") as f:
        f.write(bytes((px & 255, (px >> 8) & 255, py & 255, (py >> 8) & 255, ang & 255)))


def play(load, pulse, palette, SW, SH, START):
    try:
        import tkinter as tk, pfc_blit
    except Exception as e:
        print(f"tkinter unavailable ({e}). Verify headless: python host/pfc_raycast.py --test"); return 1
    cd = load(); pal = palette()
    px, py, ang = read_state(START); write_state(px, py, ang)

    root = tk.Tk(); root.title("pfc raycaster  —  Esc / X to close, F11 fullscreen"); root.configure(bg="#05070a")
    scale = max(1, min(920 // SW, 720 // SH)); W, H = SW * scale, SH * scale
    root.geometry(f"{W}x{H}")
    canvas = tk.Canvas(root, width=W, height=H, bg="#05070a", highlightthickness=0); canvas.pack()
    img_id = canvas.create_image(0, 0, anchor="nw")
    hud = canvas.create_text(12, 8, anchor="nw", fill="#39efc9", font=("Consolas", 12), text="")
    st = {"px": px, "py": py, "ang": ang, "keys": set(), "frames": 0}

    KMAP = {"w": 0, "s": 1, "a": 2, "d": 3, "Up": 0, "Down": 1, "Left": 2, "Right": 3}

    def render(fb):
        rgb = bytearray(SW * SH * 3)
        for i, ix in enumerate(fb):
            r, gg, b = pal[ix]; o = i * 3; rgb[o] = r; rgb[o + 1] = gg; rgb[o + 2] = b
        base = pfc_blit.photo(SW, SH, rgb); big = base.zoom(scale)
        canvas.itemconfigure(img_id, image=big); canvas.image_big = big
        canvas.itemconfigure(hud, text=(f"pfc RAYCASTER — {cd['n_gate']:,} gates · {SW}x{SH} · host = clock + monitor only\n"
                                        f"frame {st['frames']:,}   W/A/S/D move · Esc/X close · F11 fullscreen"))

    def step():
        keys = 0
        for k in st["keys"]:
            if k in KMAP:
                keys |= 1 << KMAP[k]
        (npx, npy, nang), fb = pulse(cd, st["px"], st["py"], st["ang"], keys)   # ONE clock pulse on the pfc
        write_state(npx, npy, nang)
        st["px"], st["py"], st["ang"] = npx, npy, nang; st["frames"] += 1
        render(fb)
        root.after(1, step)                                # pulse continuously; the pfc's speed is the pfc's, not capped

    root.bind("<KeyPress>", lambda e: st["keys"].add(e.keysym))
    root.bind("<KeyRelease>", lambda e: st["keys"].discard(e.keysym))
    def esc(_=None):
        if root.attributes("-fullscreen"): root.attributes("-fullscreen", False)
        else: root.destroy()
    root.bind("<Escape>", esc); root.bind("q", lambda e: root.destroy())
    root.bind("<F11>", lambda e: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    print("playing the Muhlnickel raycaster — W/A/S/D to move, Esc or the X to close.", flush=True)
    step(); root.mainloop()
    return 0
