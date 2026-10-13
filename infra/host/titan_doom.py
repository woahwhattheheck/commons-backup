#!/usr/bin/env python3
"""host/titan_doom.py — DOOM, where the game's state machine is a circuit in Titan's params (owner 07-15).

"if it can mine bitcoin no shot it cant play doom." Same substrate: the game's MOVEMENT + TURN + COLLISION state update
is a NAND gate-net stored IN titan.gguf's parameters (titan_circuit.py). Each frame the host reads your KEYSTROKES (the
input bits) + the wall bits at the candidate cells (perception), ripples them through the stored circuit (no numpy,
~0 RAM), gets the next (x, y, angle), and RAY-CASTS the first-person view to the display. Per BARE_METAL.md the host only
feeds input and renders pixels; the compute (where can I move) lives in the weights — exactly the phone-agent thesis with
a game instead of a phone.

  python host/titan_doom.py            # play it (a window; W/S move, A/D turn, arrows too, Esc quits)
  python host/titan_doom.py selftest   # headless: verify the movement circuit == a Python reference
"""
import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as tc

TURN = 6                                   # angle units per turn press (8-bit angle, 256 = full circle)
SPEED = 5                                  # world units per move press
CELL = 32                                  # world units per map cell (positions are 8-bit: 0..255 => an 8x8 map)
MAP = [
    "########",
    "#......#",
    "#.##.#.#",
    "#.#..#.#",
    "#.#.##.#",
    "#....#.#",
    "#.####.#",
    "########",
]
def wall_at(wx, wy):
    cx = (wx & 0xff) // CELL; cy = (wy & 0xff) // CELL
    if cx < 0 or cy < 0 or cx > 7 or cy > 7: return 1
    return 1 if MAP[cy][cx] == '#' else 0


def build_movement():
    """Inputs: px(8) py(8) dx(8) dy(8) wallx(1) wally(1) angle(8) turnL(1) turnR(1). Outputs: nx(8) ny(8) nangle(8)."""
    c = tc.Circuit(8 + 8 + 8 + 8 + 1 + 1 + 8 + 1 + 1)
    i = c.IN
    px, py, dx, dy = i[0:8], i[8:16], i[16:24], i[24:32]
    wallx, wally = i[32], i[33]
    angle = i[34:42]; turnL, turnR = i[42], i[43]
    candx = c.add(px, dx); candy = c.add(py, dy)
    nx = [c.mux(wallx, candx[k], px[k]) for k in range(8)]        # wallx ? px : candx  (block if wall, else move)
    ny = [c.mux(wally, candy[k], py[k]) for k in range(8)]
    ang_r = c.add(angle, c.cvec(TURN, 8))                        # angle + TURN
    na1 = [c.mux(turnR, angle[k], ang_r[k]) for k in range(8)]    # turnR ? angle+TURN : angle
    na1_l = c.add(na1, c.cvec((256 - TURN) & 0xff, 8))          # na1 - TURN
    nangle = [c.mux(turnL, na1[k], na1_l[k]) for k in range(8)]   # turnL ? na1-TURN : na1
    return c, nx + ny + nangle


def _pack(px, py, dx, dy, wallx, wally, angle, turnL, turnR):
    return (tc.bits(px, 8) + tc.bits(py, 8) + tc.bits(dx & 0xff, 8) + tc.bits(dy & 0xff, 8)
            + [wallx, wally] + tc.bits(angle, 8) + [turnL, turnR])


def step(cir, px, py, angle, keys):
    """One tick THROUGH the stored circuit. keys = set of {'fwd','back','left','right'}."""
    mv = (1 if 'fwd' in keys else 0) - (1 if 'back' in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv
    dy = int(round(math.sin(rad) * SPEED)) * mv
    wallx = wall_at(px + dx, py); wally = wall_at(px, py + dy)
    turnL = 1 if 'left' in keys else 0; turnR = 1 if 'right' in keys else 0
    out = tc.ripple(cir, _pack(px, py, dx, dy, wallx, wally, angle, turnL, turnR))
    return tc.frombits(out[0:8]), tc.frombits(out[8:16]), tc.frombits(out[16:24])


def _ref(px, py, angle, keys):                     # the same logic in plain Python, for the self-test
    mv = (1 if 'fwd' in keys else 0) - (1 if 'back' in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * SPEED)) * mv; dy = int(round(math.sin(rad) * SPEED)) * mv
    wallx = wall_at(px + dx, py); wally = wall_at(px, py + dy)
    nx = px if wallx else (px + dx) & 0xff; ny = py if wally else (py + dy) & 0xff
    a = angle
    if 'right' in keys: a = (a + TURN) & 0xff
    if 'left' in keys:  a = (a - TURN) & 0xff
    return nx & 0xff, ny & 0xff, a


def selftest():
    print("building the movement/turn/collision circuit ...", flush=True)
    c, outs = build_movement(); info = tc.store("doom_move", c, outs, slot=3)
    print(f"stored IN Titan's params: {info['tensor']} @ {info['offset']} ({info['gates']} gates)", flush=True)
    cir = tc.load("doom_move")
    import random; random.seed(3); ok = True
    for _ in range(3000):
        px = random.randint(0, 255); py = random.randint(0, 255); angle = random.randint(0, 255)
        keys = set(k for k in ('fwd', 'back', 'left', 'right') if random.random() < 0.5)
        if step(cir, px, py, angle, keys) != _ref(px, py, angle, keys):
            ok = False; print("  MISMATCH", px, py, angle, keys); break
    print(f"[verify] Doom movement-circuit-in-params == Python reference over 3000 states: {ok}", flush=True)
    print("=> the game's state machine runs from Titan's weights. launch without 'selftest' to play it.", flush=True)


def play():
    import tkinter as tk
    c, outs = build_movement(); tc.store("doom_move", c, outs, slot=3); cir = tc.load("doom_move")
    W, H, COLS = 640, 400, 160
    FOV = 60 * math.pi / 180
    st = {'px': 48, 'py': 48, 'angle': 32, 'keys': set()}
    root = tk.Tk(); root.title("TITAN DOOM — the game state machine runs in the params")
    cv = tk.Canvas(root, width=W, height=H, bg="black", highlightthickness=0); cv.pack()
    cols = [cv.create_rectangle(0, 0, 0, 0, width=0) for _ in range(COLS)]
    hud = cv.create_text(8, 8, anchor="nw", fill="#39c98b", font=("Consolas", 10), text="")
    KM = {'w': 'fwd', 's': 'back', 'a': 'left', 'd': 'right',
          'Up': 'fwd', 'Down': 'back', 'Left': 'left', 'Right': 'right'}
    pending = {}                                                  # per-action release timers (debounce OS key auto-repeat)
    def kd(e):
        if e.keysym == 'Escape': root.destroy(); return
        act = KM.get(e.keysym)
        if act:
            aid = pending.pop(act, None)
            if aid: root.after_cancel(aid)                       # a key-repeat arrived -> cancel the pending release
            st['keys'].add(act)
    def ku(e):
        act = KM.get(e.keysym)
        if act:                                                  # don't drop instantly: OS auto-repeat fires KeyRelease+KeyPress
            pending[act] = root.after(45, lambda a=act: (st['keys'].discard(a), pending.pop(a, None)))
    root.bind_all("<KeyPress>", kd); root.bind_all("<KeyRelease>", ku)   # bind_all: catch keys regardless of focused child
    cv.focus_set()
    root.after(60, lambda: (root.lift(), root.focus_force(), cv.focus_set()))   # grab keyboard focus on launch (Windows)

    def cast(px, py, ang):
        rad = ang / 256.0 * 2 * math.pi
        for x in range(COLS):
            ra = rad - FOV / 2 + FOV * x / COLS
            sx, sy = math.cos(ra), math.sin(ra); dist = 0.0
            while dist < 400:
                dist += 3
                if wall_at(int(px + sx * dist), int(py + sy * dist)): break
            dist *= math.cos(ra - rad)                              # fisheye fix
            h = min(H, int(CELL * H / (dist + 1)))
            shade = max(0, 255 - int(dist)); col = "#%02x%02x%02x" % (shade // 3, shade, shade // 2)
            cw = W // COLS
            cv.coords(cols[x], x * cw, (H - h) // 2, x * cw + cw, (H + h) // 2)
            cv.itemconfig(cols[x], fill=col)

    def tick():
        st['px'], st['py'], st['angle'] = step(cir, st['px'], st['py'], st['angle'], st['keys'])
        cast(st['px'], st['py'], st['angle'])
        cv.itemconfig(hud, text=f"x={st['px']} y={st['py']} a={st['angle']}   {info_line}")
        root.after(33, tick)
    info_line = f"{len(c.ga)} gates in the params | W/S move  A/D turn  Esc quit"
    tick(); root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    else:
        try:
            play()
        except Exception as e:
            print(f"(no display / tkinter issue: {e})  — run  python host/titan_doom.py selftest  to verify the circuit headless.")
