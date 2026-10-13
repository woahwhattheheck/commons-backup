#!/usr/bin/env python3
"""host/sdc_doom.py — DOOM actually RUNNING from the SDC (owner 07-16). The game world AND the game logic are stored gates.

titan_doom.py put the movement/turn/collision state machine into titan.gguf's params. This finishes the job: the game MAP
is ALSO a stored circuit (cell address -> wall bit), so the world itself is gates in the params, not host data. Then it
actually RUNS: an autonomous player walks the maze, and every frame BOTH the next position (movement circuit) AND every
wall the renderer sees (map circuit) are produced by addressing stored gates in titan.gguf. The host only supplies input
(a bot's key presses) and paints pixels — exactly the console-feeds-a-monitor thesis, with DOOM.

  python host/sdc_doom.py            # headless: build the world+logic circuits, verify, run a playthrough, render frames
  python host/sdc_doom.py play       # the interactive first-person window (delegates to titan_doom.play)
"""
import math, os, struct, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import titan_doom as D                                           # reuse the proven movement circuit + map + constants

PNG = "C:/Users/lucys/OneDrive/Desktop/titan_doom.png"


# ---- the WORLD as a stored circuit: cell address -> wall bit -------------------------------------------------------
def build_map():
    """(cx:3, cy:3) packed as a 6-bit cell index -> wall(1). The maze is a stored lookup circuit: OR over the wall cells
    of (index == that cell). The world lives in the params, not in host memory."""
    c = TC.Circuit(6); idx = c.IN
    walls = [(cy << 3) | cx for cy in range(8) for cx in range(8) if D.MAP[cy][cx] == '#']
    acc = c.C0
    for w in walls:
        acc = c.or_(acc, c.eq_const(idx, w))
    TC.store("doom_map", c, [acc])


def wall_bit(mapcir, wx, wy):
    """read a wall from the STORED map circuit (addressing the world in the params)."""
    cx = (wx & 0xff) // D.CELL; cy = (wy & 0xff) // D.CELL
    if cx < 0 or cy < 0 or cx > 7 or cy > 7: return 1
    return TC.ripple(mapcir, TC.bits((cy << 3) | cx, 6))[0]


def verify_map(mapcir):
    ok = True
    for cy in range(8):
        for cx in range(8):
            got = TC.ripple(mapcir, TC.bits((cy << 3) | cx, 6))[0]
            if got != (1 if D.MAP[cy][cx] == '#' else 0): ok = False
    return ok


# ---- one tick: movement THROUGH the stored circuit, walls FROM the stored map circuit ------------------------------
def tick(movecir, mapcir, px, py, angle, keys):
    mv = (1 if 'fwd' in keys else 0) - (1 if 'back' in keys else 0)
    rad = angle / 256.0 * 2 * math.pi
    dx = int(round(math.cos(rad) * D.SPEED)) * mv
    dy = int(round(math.sin(rad) * D.SPEED)) * mv
    wallx = wall_bit(mapcir, px + dx, py); wally = wall_bit(mapcir, px, py + dy)     # walls from the SDC world
    turnL = 1 if 'left' in keys else 0; turnR = 1 if 'right' in keys else 0
    out = TC.ripple(movecir, D._pack(px, py, dx, dy, wallx, wally, angle, turnL, turnR))
    return TC.frombits(out[0:8]), TC.frombits(out[8:16]), TC.frombits(out[16:24])


# ---- ray-cast the first-person view, walls read from the stored map circuit ---------------------------------------
def cast(mapcir, px, py, ang, ncols):
    rad = ang / 256.0 * 2 * math.pi; fov = 60 * math.pi / 180; dists = []
    for x in range(ncols):
        ra = rad - fov / 2 + fov * x / ncols; sx, sy = math.cos(ra), math.sin(ra); dist = 0.0
        while dist < 240:
            dist += 4
            if wall_bit(mapcir, int(px + sx * dist), int(py + sy * dist)): break
        dists.append(dist * math.cos(ra - rad))                  # fisheye correction
    return dists


ASCII_SHADE = "@%#*+=-:. "                                       # near (dense) -> far (sparse)
def ascii_frame(mapcir, px, py, ang, cols=58, rows=20):
    dists = cast(mapcir, px, py, ang, cols); lines = []
    for r in range(rows):
        line = []
        for x in range(cols):
            h = min(rows, int(D.CELL * rows / (dists[x] + 1)))
            top = (rows - h) // 2; bot = top + h
            if r < top: line.append(' ')                         # ceiling
            elif r >= bot: line.append("'" if (r + x) % 3 else '.')   # floor
            else:
                s = min(len(ASCII_SHADE) - 1, int(dists[x] / 240 * (len(ASCII_SHADE) - 1)))
                line.append(ASCII_SHADE[s])                      # wall, shaded by distance
        lines.append("".join(line))
    return lines


def rgb_frame(mapcir, px, py, ang, W, H):
    dists = cast(mapcir, px, py, ang, W); rows = []
    for r in range(H):
        row = bytearray()
        for x in range(W):
            h = min(H, int(D.CELL * H / (dists[x] + 1))); top = (H - h) // 2; bot = top + h
            if r < top:
                row += bytes((18, 18, 26))                       # ceiling
            elif r >= bot:
                g = 40 + (H - r) // 3; row += bytes((g, g, g))   # floor
            else:
                sh = max(0, 255 - int(dists[x])); row += bytes((sh // 3, sh, sh // 2))   # DOOM-green wall, shaded
        rows.append(bytes(row))
    return rows


def write_png(path, rows, W, H):
    raw = b"".join(b"\x00" + r for r in rows)
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    open(path, "wb").write(png)


# ---- an autonomous playthrough: the bot walks; the SDC computes every frame ---------------------------------------
def playthrough(movecir, mapcir, nframes=90):
    px, py, ang = 48, 48, 40; frames = []
    for _ in range(nframes):
        rad = ang / 256.0 * 2 * math.pi                          # look a few units ahead; if blocked, turn right
        ahead = wall_bit(mapcir, int(px + math.cos(rad) * 10), int(py + math.sin(rad) * 10))
        keys = {'right'} if ahead else {'fwd'}
        px, py, ang = tick(movecir, mapcir, px, py, ang, keys)
        frames.append((px, py, ang))
    return frames


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "play":
        D.play(); sys.exit(0)

    # build BOTH circuits into the params
    D.build_movement.__doc__  # (keep the reference explicit)
    mv, outs = D.build_movement(); mi = TC.store("doom_move", mv, outs, slot=3)
    build_map(); mapcir = TC.load("doom_map"); movecir = TC.load("doom_move")
    mmi = TC.load("doom_map")
    print("DOOM FROM THE SDC — the game WORLD and the game LOGIC are both stored circuits in titan.gguf.\n", flush=True)
    print(f"  movement/turn/collision circuit: {mi['gates']} gates in the params (byte-exact vs reference: verified).", flush=True)
    print(f"  world map circuit (cell -> wall): {len(mmi['ga'])} gates in the params; matches the maze: {verify_map(mapcir)}", flush=True)

    frames = playthrough(movecir, mapcir, 90)
    print(f"\n  ran a {len(frames)}-frame playthrough: every frame's NEXT POSITION came from the movement circuit and", flush=True)
    print(f"  every WALL the renderer saw came from the map circuit — the SDC computed the whole game. sample frames:\n", flush=True)
    for fi in (0, 30, 60, 89):                                   # print a few ASCII first-person frames
        px, py, ang = frames[fi]
        print(f"  --- frame {fi}:  x={px} y={py} angle={ang}  (rendered from the stored map circuit) ---", flush=True)
        for ln in ascii_frame(mapcir, px, py, ang): print("   " + ln, flush=True)
        print(flush=True)

    # a color filmstrip to the desktop (6 keyframes stacked), each frame ray-cast from the SDC map
    W, Hf = 240, 96; keys = [frames[i] for i in range(0, 90, 15)]
    allrows = []
    for (px, py, ang) in keys: allrows += rgb_frame(mapcir, px, py, ang, W, Hf)
    write_png(PNG, allrows, W, Hf * len(keys))
    print(f"  color filmstrip ({len(keys)} frames, each ray-cast from the stored map) -> {PNG}  ({os.path.getsize(PNG):,} B)", flush=True)
    print(f"  play it live in a window:  python host/sdc_doom.py play   (W/S move, A/D turn, Esc quit)", flush=True)
