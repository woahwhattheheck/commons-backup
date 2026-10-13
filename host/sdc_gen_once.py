#!/usr/bin/env python3
"""host/sdc_gen_once.py — GENERATE a game from a description's MEANING, computed on the SDC. Pure python, no numpy.

The forward-pass read (sdc_read, the model on the SDC) turns the description into a meaning vector; that meaning is scored
by cosine against the game engine's PRIMITIVES (its instruction set) using the model's own trained geometry. No lexicon,
no feature table, no word-catch — the trained weights decide which mechanics the description means. The active primitives
are assembled into a game spec (the universal engine's format) which the stored logic circuits then run. Bounded,
one-shot, foreground, ~0 RAM — the gated-sandbox read.

  python host/sdc_gen_once.py "hop across the busy road to reach the safe side"   # -> a game spec (JSON) on stdout
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_read

# the engine PRIMITIVES (its instruction set), each NAMED by a few of its own synonyms. the description->primitive
# strength is 100% cosine from the trained weights; this is not a description-word table.
PRIMS = [
    ("hazard",   ["enemy", "car", "danger"]),      # moving deadly tiles
    ("wall",     ["wall", "maze"]),                 # solid maze walls
    ("goal",     ["goal", "exit"]),                 # a goal to reach
    ("push",     ["box", "crate"]),                 # pushable blocks
    ("collect",  ["collect", "coin"]),              # scattered pickups
    ("hop",      ["hop", "jump"]),                  # hop movement vs continuous
    ("vertical", ["fall", "climb"]),                # vertical movers
    ("fast",     ["fast", "speed"]),                # mover speed
]
STOP = set("the a an to of in on at and or is are be with your you it its into over across from for all".split())


def score(desc):
    words = [w for w in "".join(c.lower() if c.isalpha() else " " for c in desc).split() if len(w) >= 3 and w not in STOP]
    dv = sdc_read.mean_vec(words)
    if dv is None: return None, {}, words
    sc = {}
    for name, anchors in PRIMS:
        av = sdc_read.mean_vec(anchors)
        sc[name] = sdc_read.cos(dv, av) or 0.0
    return dv, sc, words


def _rng(seed):
    s = [seed & 0xFFFFFFFF]
    def r():
        s[0] = (s[0] * 1103515245 + 12345) & 0x7FFFFFFF; return s[0] / 0x7FFFFFFF
    return r


def assemble(dv, sc):
    # relative activation: a primitive fires if its score beats the mean of scores (the meaning ranks the mechanics)
    vals = list(sc.values()); mu = sum(vals) / len(vals); active = {k: (v - mu) for k, v in sc.items()}
    on = lambda k: active[k] > 0
    seed = int(abs(sum(dv)) * 1e6) & 0xFFFFFFFF; rnd = _rng(seed)
    W = H = 13
    g = [["." for _ in range(W)] for _ in range(H)]
    for i in range(W): g[0][i] = g[H-1][i] = g[i][0] = g[i][W-1] = "#" if on("wall") or on("push") else "."
    sym = {}
    spd = max(1, min(4, 1 + int((sc.get("fast", 0) + 0.2) * 8)))
    hop = on("hop")
    sym["@"] = {"roles": ["player"] + (["hop"] if hop else []), "dir": None, "speed": 1}

    if on("wall"):                                             # maze interior
        for _ in range(int(6 + active["wall"] * 40)):
            x, y = 1 + int(rnd() * (W-2)), 1 + int(rnd() * (H-2)); g[y][x] = "#"
        sym["#"] = {"roles": ["solid"], "dir": None, "speed": 1}

    if on("hazard"):                                           # horizontal moving deadly lanes
        nl = max(1, min(H-4, int(1 + active["hazard"] * 30)))
        rows = [r for r in range(1, H-1) if r % 2 == 1][:nl]
        for r in rows:
            ch = ">" if rnd() < 0.5 else "<"
            for x in range(1, W-1):
                if rnd() < 0.45: g[r][x] = ch
            sym[">"] = {"roles": ["move", "deadly"], "dir": "right", "speed": spd}
            sym["<"] = {"roles": ["move", "deadly"], "dir": "left", "speed": spd}

    if on("vertical"):                                         # vertical moving deadly
        for x in range(2, W-1, 3):
            ch = "v" if rnd() < 0.5 else "^"
            for y in range(1, H-1):
                if rnd() < 0.4: g[y][x] = ch
        sym["v"] = {"roles": ["move", "deadly"], "dir": "down", "speed": spd}
        sym["^"] = {"roles": ["move", "deadly"], "dir": "up", "speed": spd}

    if on("push"):                                            # boxes + their targets
        nb = max(1, min(5, int(1 + active["push"] * 30)))
        for _ in range(nb):
            bx, by = 2 + int(rnd()*(W-4)), 2 + int(rnd()*(H-4)); g[by][bx] = "B"
            gx, gy = 2 + int(rnd()*(W-4)), 2 + int(rnd()*(H-4)); g[gy][gx] = "G"
        sym["B"] = {"roles": ["pushable"], "dir": None, "speed": 1}
        sym["G"] = {"roles": ["goal"], "dir": None, "speed": 1}

    if on("collect"):                                        # scattered pickups
        for _ in range(max(2, int(2 + active["collect"] * 30))):
            x, y = 1 + int(rnd()*(W-2)), 1 + int(rnd()*(H-2))
            if g[y][x] == ".": g[y][x] = "G"
        sym["G"] = {"roles": ["goal"], "dir": None, "speed": 1}

    if "G" not in sym:                                       # every game needs a win: a goal row up top by default
        for x in range(1, W-1): g[0][x] = "G"
        sym["G"] = {"roles": ["goal"], "dir": None, "speed": 1}

    # player start = a free cell near the bottom
    placed = False
    for y in range(H-2, 0, -1):
        for x in range(1, W-1):
            if g[y][x] == ".": g[y][x] = "@"; placed = True; break
        if placed: break
    return {"sym": sym, "grid": ["".join(r) for r in g], "W": W, "H": H}


if __name__ == "__main__":
    desc = sys.argv[1] if len(sys.argv) > 1 else "hop across the busy road to reach the safe side"
    dv, sc, words = score(desc)
    if dv is None:
        print(json.dumps({"error": "no known words in description"})); sys.exit(0)
    spec = assemble(dv, sc)
    spec["meta"] = {"desc": desc, "words": words, "scores": {k: round(v, 3) for k, v in sc.items()}}
    print(json.dumps(spec))
