#!/usr/bin/env python3
"""host/pfc_arcade.py — ONE clickable window for every Muhlnickel demo (owner 07-20: "something i can click").

A fullscreen menu: click a demo and it opens; press Esc to come back to the menu; Quit to exit. Everything runs on the
pfc (each demo is a baked gate netlist; the host only pulses + renders). No terminal needed — launch it from the Desktop
shortcut "PFC Arcade". Single process, no subprocess: each demo reuses its own play() in turn.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import tkinter as tk
import pfc_raycast, pfc_raycast_ui, pfc_game, pfc_game_ui, pfc_tunnel, pfc_tetris, pfc_tetris_ui, pfc_operator
import pfc_langton, pfc_turing, pfc_cyclic, pfc_wireworld   # forged by fable 2026-07-23 — byte-exact gate netlists

DEMOS = [
    ("Tetris", "the challenge — arrows / WASD",
     lambda: pfc_tetris_ui.play(pfc_tetris.load, pfc_tetris.pulse, pfc_tetris.new_game, pfc_tetris.PAL, pfc_tetris.SW, pfc_tetris.SH)),
    ("Raycaster 3D", "first-person maze — WASD",
     lambda: pfc_raycast_ui.play(pfc_raycast.load, pfc_raycast.pulse, pfc_raycast.palette, pfc_raycast.SW, pfc_raycast.SH, pfc_raycast.START)),
    ("Tunnel", "sit back — it animates itself",
     lambda: pfc_tunnel.play()),
    ("Game of Life", "click to seed cells",
     lambda: pfc_game_ui.play("life", pfc_game.load, pfc_game.tick, pfc_game.GAMES)),
    ("Brian's Brain", "3-state cellular automaton",
     lambda: pfc_game_ui.play("brain", pfc_game.load, pfc_game.tick, pfc_game.GAMES)),
    ("Operator (AI)", "draw a digit — the pfc reads it",
     lambda: pfc_operator.play()),
    ("Langton's Ant", "forged on the pfc — watch it build a highway",
     lambda: pfc_langton.play()),
    ("Turing Machine", "forged — a busy beaver runs to HALT",
     lambda: pfc_turing.play()),
    ("Cyclic CA", "forged — noise self-organizes into spirals",
     lambda: pfc_cyclic.play()),
    ("Wireworld", "forged — build logic in a CA that IS logic",
     lambda: pfc_wireworld.play()),
]


def menu():
    root = tk.Tk(); root.title("pfc arcade  —  running on the pfc"); root.configure(bg="#0a0e13")
    root.geometry("560x760"); root.protocol("WM_DELETE_WINDOW", root.destroy)
    pick = {"v": None}
    wrap = tk.Frame(root, bg="#0a0e13"); wrap.place(relx=0.5, rely=0.5, anchor="center")
    tk.Label(wrap, text="RUNNING ON THE pfc", font=("Consolas", 18), fg="#39efc9", bg="#0a0e13").pack(pady=(0, 2))
    tk.Label(wrap, text="prefabricated computation, sandboxed in storage  ·  click a demo", font=("Consolas", 11), fg="#8996a6", bg="#0a0e13").pack(pady=(0, 26))

    def choose(n): pick["v"] = n; root.destroy()
    for name, sub, _ in DEMOS:
        b = tk.Frame(wrap, bg="#111923", highlightbackground="#1c2732", highlightthickness=1, cursor="hand2")
        b.pack(fill="x", pady=5, ipady=8, ipadx=10)
        tk.Label(b, text=name, font=("Consolas", 19, "bold"), fg="#e9eef4", bg="#111923").pack(anchor="w", padx=18)
        tk.Label(b, text=sub, font=("Consolas", 11), fg="#8996a6", bg="#111923").pack(anchor="w", padx=18)
        for w in (b, *b.winfo_children()):
            w.bind("<Button-1>", lambda e, n=name: choose(n))
            w.bind("<Enter>", lambda e, f=b: [f.config(bg="#16202c")] + [c.config(bg="#16202c") for c in f.winfo_children()])
            w.bind("<Leave>", lambda e, f=b: [f.config(bg="#111923")] + [c.config(bg="#111923") for c in f.winfo_children()])
    tk.Label(wrap, text="Esc inside a demo returns here", font=("Consolas", 10), fg="#576270", bg="#0a0e13").pack(pady=(20, 4))
    tk.Button(wrap, text="Quit", font=("Consolas", 13), width=12, bg="#0a0e13", fg="#8996a6", relief="flat",
              activebackground="#0a0e13", activeforeground="#e9eef4", cursor="hand2", command=lambda: choose(None)).pack()
    root.bind("<Escape>", lambda e: choose(None))
    root.mainloop(); return pick["v"]


def main():
    while True:
        c = menu()
        if not c:
            return 0
        try:
            dict((n, f) for n, _, f in DEMOS)[c]()          # run that demo's play(); it returns to the menu on Esc
        except Exception as e:
            print(f"demo '{c}' error: {e}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
