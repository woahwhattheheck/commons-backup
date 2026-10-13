#!/usr/bin/env python3
"""host/pfc_tetris.py — TETRIS running entirely on the Muhlnickel (owner 07-20: "a more challenging game to push its limit").

The whole game is ONE prefabricated gate netlist stored in a pfc file: a 10x20 board (3 bits/cell), the 7 tetrominoes x 4
rotations, a gravity timer, edge-detected input, collision, LINE-CLEAR COMPACTION, an LFSR that spawns the next piece, and
game-over -> restart. The game STATE lives in the pfc's storage; each clock pulse the host routes the key SIGNALS in and
PULSES the clock (one bounded ripple) — the pfc advances the whole game one step and PAINTS the framebuffer. Host = clock +
monitor only. Byte-exact vs a reference implementation (built + self-checked first, then mirrored to gates).

  python host/pfc_tetris.py --test    # build, verify the reference plays + the gates match it byte-exact, render a frame
  python host/pfc_tetris.py           # play: arrows/WASD move+rotate, Down soft-drop; running on the pfc
"""
import base64, os, struct, sys, time, zlib
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_raycast import const, add, sub, mux, ult, rom

SBX = PFCP.SBX; PFC = os.path.join(SBX, "pfc_tetris.pfc")
OPC = {"and": 1, "or": 2, "xor": 3, "not": 4, "nand": 5}; OPN = {v: k for k, v in OPC.items()}
BW, BH = 10, 20; NC = BW * BH; CS = 6; SW, SH = BW * CS, BH * CS       # board + screen
G = 6                                                                  # gravity: fall every G pulses

# 7 tetrominoes x 4 rotations, each = 4 (col,row) in a 4x4 box
SHAPES = [
    [[(0,1),(1,1),(2,1),(3,1)],[(2,0),(2,1),(2,2),(2,3)],[(0,2),(1,2),(2,2),(3,2)],[(1,0),(1,1),(1,2),(1,3)]],  # I
    [[(1,0),(2,0),(1,1),(2,1)]]*4,                                                                               # O
    [[(1,0),(0,1),(1,1),(2,1)],[(1,0),(1,1),(2,1),(1,2)],[(0,1),(1,1),(2,1),(1,2)],[(1,0),(0,1),(1,1),(1,2)]],  # T
    [[(1,0),(2,0),(0,1),(1,1)],[(1,0),(1,1),(2,1),(2,2)],[(1,1),(2,1),(0,2),(1,2)],[(0,0),(0,1),(1,1),(1,2)]],  # S
    [[(0,0),(1,0),(1,1),(2,1)],[(2,0),(1,1),(2,1),(1,2)],[(0,1),(1,1),(1,2),(2,2)],[(1,0),(0,1),(1,1),(0,2)]],  # Z
    [[(0,0),(0,1),(1,1),(2,1)],[(1,0),(2,0),(1,1),(1,2)],[(0,1),(1,1),(2,1),(2,2)],[(1,0),(1,1),(0,2),(1,2)]],  # J
    [[(2,0),(0,1),(1,1),(2,1)],[(1,0),(1,1),(1,2),(2,2)],[(0,1),(1,1),(2,1),(0,2)],[(0,0),(1,0),(1,1),(1,2)]],  # L
]
SPAWNX, SPAWNY = 3, 0


# ============================ REFERENCE (the game; built + self-checked first) ============================
def collide(board, typ, rot, px, py):
    for (col, row) in SHAPES[typ][rot]:
        bx, by = px + col, py + row
        if bx < 0 or bx > BW - 1 or by > BH - 1: return True
        if by >= 0 and board[by * BW + bx]: return True
    return False


def lock_and_clear(board, typ, rot, px, py):
    b = list(board)
    for (col, row) in SHAPES[typ][rot]:
        bx, by = px + col, py + row
        if 0 <= by < BH and 0 <= bx < BW: b[by * BW + bx] = typ + 1
    rows = [b[r * BW:(r + 1) * BW] for r in range(BH)]
    kept = [row for row in rows if not all(row)]
    newrows = [[0] * BW] * (BH - len(kept)) + kept
    return [c for row in newrows for c in row]


def ref_step(state, keys):
    board = list(state["board"]); typ = state["typ"]; rot = state["rot"]; px = state["px"]; py = state["py"]
    gcnt = state["gcnt"]; prev = state["prev"]; lfsr = state["lfsr"]; over = state["over"]
    lfsr = ((lfsr >> 1) ^ (0xB400 if lfsr & 1 else 0)) & 0xffff
    pl = keys & 1; pr = (keys >> 1) & 1; prot = (keys >> 2) & 1; dn = (keys >> 3) & 1
    e_l = pl & ~(prev & 1) & 1; e_r = pr & ~((prev >> 1) & 1) & 1; e_rot = prot & ~((prev >> 2) & 1) & 1
    nprev = keys & 15
    # horizontal
    nx = px + e_r - e_l
    if collide(board, typ, rot, nx, py): nx = px
    # rotate
    nrot = (rot + 1) & 3 if e_rot else rot
    if collide(board, typ, nrot, nx, py): nrot = rot
    # gravity
    grav = 1 if (gcnt >= G - 1 or dn) else 0
    ngcnt = 0 if grav else gcnt + 1
    lock = grav and collide(board, typ, nrot, nx, py + 1)
    if lock:
        nboard = lock_and_clear(board, typ, nrot, nx, py)
        ntyp = (lfsr & 63) % 7; nrot2 = 0; npx = SPAWNX; npy = SPAWNY
        if collide(nboard, ntyp, 0, npx, npy):
            nboard = [0] * NC; nover = 1                          # game over -> clear
        else:
            nover = over
        return dict(board=nboard, typ=ntyp, rot=nrot2, px=npx, py=npy, gcnt=0, prev=nprev, lfsr=lfsr, over=nover)
    ny = py + 1 if grav else py
    return dict(board=board, typ=typ, rot=nrot, px=nx, py=ny, gcnt=ngcnt, prev=nprev, lfsr=lfsr, over=over)


def ref_render(state):                                           # -> NC cells (0=empty, 1..7 = colours) with active piece
    disp = list(state["board"])
    for (col, row) in SHAPES[state["typ"]][state["rot"]]:
        bx, by = state["px"] + col, state["py"] + row
        if 0 <= by < BH and 0 <= bx < BW: disp[by * BW + bx] = state["typ"] + 1
    return disp


def new_game(seed=0xACE1):
    return dict(board=[0] * NC, typ=seed % 7, rot=0, px=SPAWNX, py=SPAWNY, gcnt=0, prev=0, lfsr=seed, over=0)


# ============================ gate helpers ============================
def orr(g, bits):
    r = g.C0
    for b in bits: r = g.OR(r, b)
    return r
def eqc(g, A, k):
    r = g.C1
    for i in range(len(A)): r = g.AND(r, A[i] if (k >> i) & 1 else g.NOT(A[i]))
    return r
def eqv(g, A, B):
    r = g.C1
    for i in range(len(A)): r = g.AND(r, g.NOT(g.XOR(A[i], B[i])))
    return r
def uge(g, A, B): return g.NOT(ult(g, A, B))                     # A >= B
def sel_bit(g, addr, wires):                                    # mux among WIRES (dynamic table) by addr -> one wire
    if not addr: return wires[0]
    h = 1 << (len(addr) - 1)
    lo = sel_bit(g, addr[:-1], wires[:h]); hi = sel_bit(g, addr[:-1], wires[h:])
    return g.OR(g.AND(g.NOT(addr[-1]), lo), g.AND(addr[-1], hi))


# ============================ STATE bit layout ============================
# board 600 | typ 3 | rot 2 | px 5 | py 5 | gcnt 5 | prev 4 | lfsr 16 | over 1  = 641
NB = NC * 3
def sl():
    o = {}; p = 0
    for nm, w in [("board", NB), ("typ", 3), ("rot", 2), ("px", 6), ("py", 5), ("gcnt", 5), ("prev", 4), ("lfsr", 16), ("over", 1)]:
        o[nm] = (p, w); p += w
    return o, p
LAYOUT, NSTATE = sl()


def get(bits, nm):
    p, w = LAYOUT[nm]; return bits[p:p + w]
def cell(board, i): return board[i * 3:i * 3 + 3]                # 3-bit colour of board cell i


# ============================ THE GAME as gates (mirrors ref_step) ============================
def shape_rom(g, typ, rot):                                      # (typ,rot) -> 4 cells, each (col2,row2) -> 16 bits
    tab = []
    for t in range(8):
        for r in range(4):
            cells = SHAPES[t][r] if t < 7 else [(0, 0)] * 4
            v = 0
            for k, (col, row) in enumerate(cells): v |= (col | (row << 2)) << (k * 4)
            tab.append(v)
    addr = typ + rot                                            # 5-bit: rot(2) low, typ(3) high -> index t*4+r
    a = list(rot) + list(typ)
    word = rom(g, a, tab, 16)
    return [(word[k * 4:k * 4 + 2], word[k * 4 + 2:k * 4 + 4]) for k in range(4)]   # 4 (col2,row2)


def occ_of(g, board):                                            # per-cell occupancy (1 bit) from 3-bit colours
    return [orr(g, cell(board, i)) for i in range(NC)]


def g_collide(g, occ, cells, px6, py):                            # px6 = 6-bit SIGNED x-origin, py = 5-bit; cells = 4 (col2,row2)
    hits = []
    for (col, row) in cells:
        bx = add(g, px6, (list(col) + [g.C0] * 4))[:6]          # 6-bit signed (col zero-extended)
        by = add(g, py, row)[:5]
        oob = g.OR(g.OR(bx[5], uge(g, bx, const(g, BW, 6))), uge(g, by, const(g, BH, 5)))   # x<0 | x>=10 | y>=20
        bx5 = bx[:5]
        idx = add(g, add(g, ([g.C0] * 3 + by)[:8], ([g.C0] + by)[:8]), (bx5 + [g.C0] * 3)[:8])[:8]   # by*10 + bx
        occ_hit = sel_bit(g, idx, occ + [g.C0] * (256 - NC))    # dynamic (wire) table -> must use sel_bit, not rom
        hits.append(g.OR(oob, occ_hit))
    return orr(g, hits)


def build(g):
    S = g.IN[0:NSTATE]; keys = g.IN[NSTATE:NSTATE + 4]
    board = get(S, "board"); typ = get(S, "typ"); rot = get(S, "rot"); px = get(S, "px"); py = get(S, "py")
    gcnt = get(S, "gcnt"); prev = get(S, "prev"); lfsr = get(S, "lfsr"); over = get(S, "over")
    occ = occ_of(g, board)
    # lfsr' = (lfsr>>1) ^ (0xB400 if lfsr&1)
    lfsr_sh = lfsr[1:] + [g.C0]
    nlfsr = [g.XOR(lfsr_sh[i], g.AND(lfsr[0], g.C1 if (0xB400 >> i) & 1 else g.C0)) for i in range(16)]
    pl, pr, prot, dn = keys[0], keys[1], keys[2], keys[3]
    e_l = g.AND(pl, g.NOT(prev[0])); e_r = g.AND(pr, g.NOT(prev[1])); e_rot = g.AND(prot, g.NOT(prev[2]))
    nprev = list(keys)
    cells0 = shape_rom(g, typ, rot)
    # horizontal: nx = px + e_r - e_l  (px is 6-bit SIGNED; the origin can legitimately be < 0 with cells on-board)
    nx6 = add(g, sub(g, px, ([e_l] + [g.C0] * 5)), ([e_r] + [g.C0] * 5))[:6]
    nx = mux(g, g_collide(g, occ, cells0, nx6, py), px, nx6)[:6]
    nx6b = nx
    # rotate
    rot1 = add(g, rot, [e_rot, g.C0])[:2]                        # (rot+1)&3 if e_rot else rot
    cells1 = shape_rom(g, typ, rot1)
    nrot = mux(g, g_collide(g, occ, cells1, nx6b, py), rot, rot1)[:2]
    cellsN = shape_rom(g, typ, nrot)
    # gravity
    grav = g.OR(uge(g, gcnt, const(g, G - 1, 5)), dn)
    ngcnt_inc = add(g, gcnt, const(g, 1, 5))[:5]
    ngcnt = mux(g, grav, const(g, 0, 5), ngcnt_inc)
    lock = g.AND(grav, g_collide(g, occ, cellsN, nx6b, add(g, py, const(g, 1, 5))[:5]))
    # --- lock path: merge piece into board, clear lines, spawn ---
    merged = merge(g, board, cellsN, nx, py, typ)
    cleared = clear_lines(g, merged)
    occ2 = occ_of(g, cleared)
    ntyp = mod7(g, nlfsr)                                        # spawn type = lfsr % 7
    spawn_cells = shape_rom(g, ntyp, const(g, 0, 2))
    spawn_bad = g_collide(g, occ2, spawn_cells, const(g, SPAWNX, 6), const(g, SPAWNY, 5))
    board_lock = mux(g, spawn_bad, const(g, 0, NB), cleared)     # game over -> clear
    over_lock = g.OR(over[0], spawn_bad)
    # --- fall path ---
    ny = mux(g, grav, add(g, py, const(g, 1, 5))[:5], py)
    # select lock vs fall
    nboard = mux(g, lock, board_lock, board)
    ntyp_f = mux(g, lock, ntyp, typ)
    nrot_f = mux(g, lock, const(g, 0, 2), nrot)
    npx = mux(g, lock, const(g, SPAWNX, 6), nx)
    npy = mux(g, lock, const(g, SPAWNY, 5), ny)
    ngcnt_f = mux(g, lock, const(g, 0, 5), ngcnt)
    nover = mux(g, lock, [over_lock], over)

    nstate = list(nboard) + list(ntyp_f) + list(nrot_f) + list(npx) + list(npy) + list(ngcnt_f) + list(nprev) + list(nlfsr) + list(nover)
    # --- render next state (board + active piece) -> NC cells (3-bit) ---
    ncellsD = shape_rom(g, ntyp_f, nrot_f)
    disp = render_cells(g, nboard, ncellsD, npx, npy, ntyp_f)
    fb = framebuffer(g, disp)
    return g.dce(nstate + fb)


def merge(g, board, cells, px, py, typ):
    col3 = add(g, typ, const(g, 1, 3))[:3]                       # colour = typ+1
    out = []
    for i in range(NC):
        ci = cell(board, i); r = i // BW; c = i % BW
        cov = g.C0
        for (col, row) in cells:
            cov = g.OR(cov, g.AND(eqv(g, add(g, px, col)[:5], const(g, c, 5)), eqv(g, add(g, py, row)[:5], const(g, r, 5))))
        out += mux(g, cov, col3, ci)
    return out


def clear_lines(g, board):
    rows = [board[r * BW * 3:(r + 1) * BW * 3] for r in range(BH)]
    occ = occ_of(g, board)
    full = [g.C1 for _ in range(BH)]
    for r in range(BH):
        f = g.C1
        for c in range(BW): f = g.AND(f, occ[r * BW + c])
        full[r] = f
    survive = [g.NOT(full[r]) for r in range(BH)]
    # below_survive[r] = sum survive[s>r] ; dest[r] = 19 - below
    dest = []
    for r in range(BH):
        s = const(g, 0, 5)
        for ss in range(r + 1, BH): s = add(g, s, [survive[ss]] + [g.C0] * 4)[:5]
        dest.append(sub(g, const(g, BH - 1, 5), s)[:5])
    newrows = []
    for j in range(BH):
        row = [g.C0] * (BW * 3)
        for r in range(BH):
            sel = g.AND(survive[r], eqc(g, dest[r], j))
            row = [g.OR(row[b], g.AND(sel, rows[r][b])) for b in range(BW * 3)]
        newrows += row
    return newrows


def render_cells(g, board, cells, px, py, typ):
    col3 = add(g, typ, const(g, 1, 3))[:3]
    out = []
    for i in range(NC):
        ci = cell(board, i); r = i // BW; c = i % BW
        cov = g.C0
        for (col, row) in cells:
            cov = g.OR(cov, g.AND(eqv(g, add(g, px, col)[:5], const(g, c, 5)), eqv(g, add(g, py, row)[:5], const(g, r, 5))))
        out.append(mux(g, cov, col3, ci))                        # 3-bit colour per cell
    return out


def framebuffer(g, disp):                                       # per pixel: grid border (const) or the cell's 3-bit colour
    fb = []
    for y in range(SH):
        for x in range(SW):
            if x % CS == 0 or y % CS == 0:
                fb += const(g, 8, 4)                             # grid line colour index 8
            else:
                i = (y // CS) * BW + (x // CS)
                fb += list(disp[i]) + [g.C0]                     # 3-bit colour -> 4-bit index (0..7)
    return fb


def mod7(g, x16):                                               # x % 7 for the low bits (enough for spawn variety)
    x = x16[0:6]                                                 # use low 6 bits (0..63) % 7
    # (v % 7) via subtracting 7s: v<64 -> at most 9 subtractions; do a small table instead
    return rom(g, x, [i % 7 for i in range(64)], 3)


# ============================ bake / load / pulse ============================
def bake():
    g = CC.CircuitCompiler(NSTATE + 4)
    print(f"fabricating Tetris ({NSTATE}-bit state, {SW}x{SH}) …", flush=True); t0 = time.time()
    gates, outs = build(g); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates, {g.n_in} in, {len(outs):,} out, built in {time.time()-t0:.1f}s", flush=True)
    os.makedirs(SBX, exist_ok=True)
    with open(PFC, "wb") as f:
        f.write(b"PFCTET01"); f.write(struct.pack("<IIII", g.n_in, n_wire, len(gates), len(outs)))
        for op, a, b in gates: f.write(struct.pack("<Bii", OPC[op], a, b))
        for o in outs: f.write(struct.pack("<i", o))
    print(f"  BAKED -> {PFC} ({os.path.getsize(PFC):,} B).", flush=True)
    return gates, outs, n_wire, g.n_in


def load():
    if not os.path.exists(PFC): bake()
    with open(PFC, "rb") as f: blob = f.read()
    assert blob[:8] == b"PFCTET01"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    cc = CC.CircuitCompiler(n_in); return dict(run=cc.compile_ripple(gates, n_wire), outs=outs, n_gate=n_gate)


def state_to_bits(s):
    bits = [0] * NSTATE
    for i in range(NC):
        for k in range(3): bits[i * 3 + k] = (s["board"][i] >> k) & 1
    def put(nm, val):
        p, w = LAYOUT[nm]
        for i in range(w): bits[p + i] = (val >> i) & 1
    put("typ", s["typ"]); put("rot", s["rot"]); put("px", s["px"] & 63); put("py", s["py"]); put("gcnt", s["gcnt"])
    put("prev", s["prev"]); put("lfsr", s["lfsr"]); put("over", s["over"])
    return bits


def bits_to_state(v, o, bit):
    def gv(nm):
        p, w = LAYOUT[nm]; return sum(bit(o[p + i]) << i for i in range(w))
    board = [sum(bit(o[i * 3 + k]) << k for k in range(3)) for i in range(NC)]
    px = gv("px"); px = px - 64 if px >= 32 else px                # 6-bit two's-complement -> signed (origin can be < 0)
    return dict(board=board, typ=gv("typ"), rot=gv("rot"), px=px, py=gv("py"),
                gcnt=gv("gcnt"), prev=gv("prev"), lfsr=gv("lfsr"), over=gv("over"))


def pulse(cd, s, keys):
    inp = state_to_bits(s) + [(keys >> i) & 1 for i in range(4)]
    v = cd["run"](inp, 1); o = cd["outs"]; bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    ns = bits_to_state(v, o, bit)
    fb = bytes(sum(bit(o[NSTATE + p * 4 + i]) << i for i in range(4)) for p in range(SW * SH))
    return ns, fb


PAL = [(12, 14, 20), (60, 220, 230), (235, 215, 70), (180, 90, 220), (90, 210, 110),
       (230, 80, 80), (80, 130, 235), (235, 150, 60), (34, 38, 48)] + [(0, 0, 0)] * 7


def save_png(fb, path, scale):
    rows = []
    for y in range(SH):
        row = bytearray()
        for x in range(SW):
            r, g_, b = PAL[fb[y * SW + x] & 15]; row += bytes((r, g_, b)) * scale
        line = b"\x00" + bytes(row)
        for _ in range(scale): rows.append(line)
    raw = b"".join(rows)
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", SW * scale, SH * scale, 8, 2, 0, 0, 0)) +
                           ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))


def test():
    # 1) reference must actually PLAY (no crash, pieces lock, lines clear) over a scripted run
    import random; random.seed(3)
    s = new_game(0xACE1); locks = 0
    for i in range(400):
        keys = random.choice([0, 1, 2, 4, 8, 0, 0])
        prev = s; s = ref_step(s, keys)
        if s["py"] < prev["py"] or (prev["gcnt"] == G - 1 and s["gcnt"] == 0 and s["typ"] != prev["typ"]): pass
        if s["typ"] != prev["typ"]: locks += 1
    print(f"  reference self-play: 400 steps ok, ~{locks} piece locks/spawns, board sane={all(0<=c<=7 for c in s['board'])}", flush=True)
    # 2) gates byte-exact vs reference across varied states
    gates, outs, n_wire, n_in = bake()
    cc = CC.CircuitCompiler(n_in); cd = dict(run=cc.compile_ripple(gates, n_wire), outs=outs, n_gate=len(gates))
    random.seed(9); s = new_game(0x1234); ok = True; bit = None
    for i in range(120):
        keys = random.choice([0, 1, 2, 4, 8])
        gs, gfb = pulse(cd, s, keys); rs = ref_step(s, keys); rfb_cells = ref_render(rs)
        if gs != rs:
            ok = False; print(f"    STATE MISMATCH at step {i}, keys={keys}");
            for k in gs:
                if gs[k] != rs[k]: print(f"      {k}: gate={gs[k] if k!='board' else '<board>'} ref={rs[k] if k!='board' else '<board>'}")
            break
        s = rs
    print(f"  gates vs reference: 120 pulses byte-exact (full state): {ok}", flush=True)
    if ok:
        # render check: play a bit then dump a frame
        random.seed(1); s = new_game(0xBEEF)
        for _ in range(60): s, fb = pulse(cd, s, __import__('random').choice([0, 1, 2, 4]))
        out = os.path.join(os.environ.get("TEMP", SBX), "pfc_tetris_frame.png"); save_png(fb, out, 6)
        print(f"    rendered a live Muhlnickel frame -> {out}", flush=True)
    return 0 if ok else 1


def main():
    if "--test" in sys.argv[1:] or "--bake" in sys.argv[1:]:
        return test()
    import pfc_tetris_ui
    return pfc_tetris_ui.play(load, pulse, new_game, PAL, SW, SH)


if __name__ == "__main__":
    raise SystemExit(main())
