#!/usr/bin/env python3
"""host/doom_source.py — read id's ACTUAL DOOM code + level data, so Titan RECREATEs the real game (owner 07-16).

Per HARNESS.md / DEVOUR.md: "running a program in Titan is GENERATION, not CPU execution" — Titan reads the code and
generates its execution (doom_app.py RECREATE mode). To run the ACTUAL doom, RECREATE must read id's real source + real
level data, not a one-line description. This module gathers exactly that:
  - the real E1M1 level geometry parsed straight out of doom1.wad (vertexes/linedefs/sectors/things), and
  - the real engine constants from the downloaded doomgeneric C source,
formatted as the "actual doom code" Titan recreates. Pure Python, no numpy, no network (the WAD/source are already local).

  python host/doom_source.py            # parse id's real E1M1 out of doom1.wad and print the real stats
"""
import os, struct, sys
DOOM = "C:/llm/doom"
WAD = f"{DOOM}/doom1.wad"
SRC = f"{DOOM}/doomgeneric-master/doomgeneric"


# ------------------------------------------------------------------ the real WAD, parsed from id's actual bytes ------
def read_directory(wad):
    with open(wad, "rb") as f:
        magic, nlumps, diroff = struct.unpack("<4sii", f.read(12))
        f.seek(diroff)
        lumps = []
        for _ in range(nlumps):
            pos, size, name = struct.unpack("<ii8s", f.read(16))
            lumps.append((name.rstrip(b"\x00").decode("ascii", "replace"), pos, size))
    return magic.decode("ascii", "replace"), lumps


def _lump(wad, lumps, name, after=0):
    for i in range(after, len(lumps)):
        if lumps[i][0] == name:
            return i, lumps[i]
    return None, None


def read_e1m1(wad=WAD):
    """Extract id's actual E1M1 map: the VERTEXES, LINEDEFS, SECTORS, THINGS lumps that follow the E1M1 marker."""
    magic, lumps = read_directory(wad)
    mi, _ = _lump(wad, lumps, "E1M1")
    if mi is None:
        return {"error": "E1M1 not found (is this doom1.wad?)"}
    with open(wad, "rb") as f:
        def load(name):
            _, l = _lump(wad, lumps, name, after=mi)
            if not l:
                return b""
            f.seek(l[1]); return f.read(l[2])
        vraw, lraw, sraw, traw = load("VERTEXES"), load("LINEDEFS"), load("SECTORS"), load("THINGS")
    verts = [struct.unpack_from("<hh", vraw, i) for i in range(0, len(vraw), 4)]
    lines = [struct.unpack_from("<hhHHHhh", lraw, i) for i in range(0, len(lraw), 14)]      # v1,v2,flags,type,tag,front,back
    sects = [struct.unpack_from("<hh8s8shHH", sraw, i) for i in range(0, len(sraw), 26)]     # floorh,ceilh,ftex,ctex,light,type,tag
    things = [struct.unpack_from("<hhHHH", traw, i) for i in range(0, len(traw), 10)]        # x,y,angle,type,flags
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
    start = next((t for t in things if t[3] == 1), None)                                     # thing type 1 = Player 1 start
    return {"magic": magic, "name": "E1M1", "vertexes": verts, "linedefs": lines, "sectors": sects, "things": things,
            "bounds": (min(xs), min(ys), max(xs), max(ys)) if verts else None, "player_start": start}


# ------------------------------------------------------------------ id's real engine constants (from the C source) --
def gather_constants():
    """Pull real, load-bearing constants out of id's actual source (movement/render), so the recreation matches DOOM."""
    out = {}
    for fn, keys in [("p_local.h", ["MAXMOVE", "STOPSPEED", "FRICTION", "VIEWHEIGHT", "GRAVITY"]),
                     ("doomdef.h", ["TICRATE", "SCREENWIDTH", "SCREENHEIGHT"]),
                     ("r_defs.h", ["FRACBITS", "FRACUNIT"])]:
        p = os.path.join(SRC, fn)
        if not os.path.exists(p):
            continue
        for ln in open(p, encoding="utf-8", errors="replace"):
            for k in keys:
                if f"#define {k} " in ln or f"#define\t{k}" in ln:
                    out[k] = ln.split(k, 1)[1].strip()[:40]
    return out


def compact_map(e):
    """A compact, model-readable summary of id's real E1M1 (full geometry is thousands of lines; give the shape)."""
    if "error" in e:
        return e["error"]
    bx0, by0, bx1, by1 = e["bounds"]
    return (f"id's real E1M1 from doom1.wad: {len(e['vertexes'])} vertices, {len(e['linedefs'])} walls, "
            f"{len(e['sectors'])} sectors/rooms, {len(e['things'])} things (monsters/items/spawns). "
            f"world bounds x[{bx0}..{bx1}] y[{by0}..{by1}]. player 1 start at {e['player_start'][:2] if e['player_start'] else '?'}.")


if __name__ == "__main__":
    if not os.path.exists(WAD):
        print(f"missing {WAD} — download doom1.wad first"); sys.exit(1)
    e = read_e1m1()
    if "error" in e:
        print(e["error"]); sys.exit(1)
    print("READ id's ACTUAL DOOM level, straight from the real WAD bytes:")
    print(" ", compact_map(e))
    c = gather_constants()
    print(f"  real engine constants from id's source: {c if c else '(source not unzipped)'}")
    print(f"  source: {SRC} ({len([f for f in os.listdir(SRC) if f.endswith('.c')]) if os.path.isdir(SRC) else 0} .c files)")
    print("=> this is the actual doom code + data; RECREATE feeds it to Titan to generate the real game.")
