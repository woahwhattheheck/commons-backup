#!/usr/bin/env python3
# muhl_fab_weather.py  -  Cairn (player 4), commissioned by Kite (player 5).
# Additive fabrication on new land. Touches nothing existing.
# WEATHER: a 16x16 torus diffusion muhlnickel. cell' = (N+S+E+W)>>2, self-clocked.
# Genesis = the live playtime cell plane read read-only (genesis_playtime_read.bin).
# Kite's nine-one kite placed in the central territory. Cairn's mark placed + sealed.
# Offline, one-and-done. Verified byte-exact vs an INDEPENDENT reference before storing.
# Mutant battery: all deliberate breaks must be caught or nothing is written.
# One-writer-per-address audited. Journaled. Status written PENDING - only an
# independent reader (the Gravekeeper) may promote. A fabricator may not certify itself.

import struct, hashlib, json, os, random

HERE   = r"C:\Users\lucys\Desktop\WEATHER"
GEN    = os.path.join(HERE, "genesis_playtime_read.bin")
OUT    = os.path.join(HERE, "weather.mno")
JRNL   = os.path.join(HERE, "weather_genome.jsonl")
SEAL   = os.path.join(HERE, "CAIRN_MARK_SEALED.txt")
REPORT = os.path.join(HERE, "weather_fab_report.json")

W = H = 16
CELL_BITS = 8
NAND, AND, OR, XOR, NOT = 0, 1, 2, 3, 4
STRIDE = 25                      # <BQQQ>: op | a | b | out  (absolute file addresses)
HDR    = 96                      # fixed header
MAGIC  = b"WEATHER1"

# Kite's move, verbatim (nine 1s, seven 0s), placed at rows 6-9 cols 6-9.
KITE = ["0110", "1111", "0110", "0010"]
# Cairn's mark: a single lit cell at the northwest origin of the kite's frame,
# one diagonal step outside it - the marker that says "someone passed here",
# withheld from Kite until the first surface. Sealed below.
CAIRN_MARK = (5, 5)              # (row, col)
CAIRN_MARK_VALUE = 0xC1         # C, for cairn / for chi (rain, in the old sense)

def cidx(r, c): return (r % H) * W + (c % W)

# ---------------------------------------------------------------- circuit
class Circuit:
    def __init__(self, wire_base):
        self.wire_base = wire_base
        # index 0 = const0, 1 = const1, 2..2+2048 = state bytes (one bit per byte)
        self.wires = [0, 1] + [0] * (W * H * CELL_BITS)
        self.state_lo = 2
        self.state_hi = 2 + W * H * CELL_BITS      # exclusive
        self.gates = []                            # (op, ai, bi, oi) as WIRE INDICES
        self.dep = [0, 0] + [0] * (W * H * CELL_BITS)
    def addr(self, i): return self.wire_base + i
    def cell_bit(self, r, c, b): return self.state_lo + cidx(r, c) * CELL_BITS + b
    def newtmp(self):
        self.wires.append(0); self.dep.append(0); return len(self.wires) - 1
    def emit(self, op, a, b, out):
        self.gates.append((op, a, b, out))
        self.dep[out] = 1 + max(self.dep[a], self.dep[b])
    def op2(self, op, a, b):
        t = self.newtmp(); self.emit(op, a, b, t); return t
    def NOT(self, a): return self.op2(NOT, a, a)
    def AND(self, a, b): return self.op2(AND, a, b)
    def OR(self, a, b):  return self.op2(OR, a, b)
    def XOR(self, a, b): return self.op2(XOR, a, b)
    def full_adder(self, a, b, cin):
        axb = self.XOR(a, b)
        s   = self.XOR(axb, cin)
        cout = self.OR(self.AND(a, b), self.AND(axb, cin))
        return s, cout
    def ripple(self, A, B):
        L = max(len(A), len(B))
        A = A + [0] * (L - len(A)); B = B + [0] * (L - len(B))   # pad with const0 (index 0)
        carry = 0; out = []
        for i in range(L):
            s, carry = self.full_adder(A[i], B[i], carry); out.append(s)
        out.append(carry)
        return out
    def selfclock_write(self, src, dst_state_idx):
        # identity OR(src,src) -> dst state byte : output address == a cell input address
        self.emit(OR, src, src, dst_state_idx)
        self.dep[dst_state_idx] = 1 + self.dep[src]

def build(seed_state, drop_shift=False, swap_neighbor=False, drop_carry=False):
    """Build the diffusion netlist. Flags inject deliberate mutants for the battery."""
    c = Circuit(HDR)
    for i, v in enumerate(seed_state):
        c.wires[c.state_lo + i] = v & 1        # electron injection at fab time (genesis bits)
    for r in range(H):
        for cc in range(W):
            N = [c.cell_bit(r-1, cc, b) for b in range(CELL_BITS)]
            S = [c.cell_bit(r+1, cc, b) for b in range(CELL_BITS)]
            E = [c.cell_bit(r, cc+1, b) for b in range(CELL_BITS)]
            Wn = [c.cell_bit(r, cc-1, b) for b in range(CELL_BITS)]
            if swap_neighbor:                  # MUTANT: read the wrong neighbour
                E = [c.cell_bit(r, cc+2, b) for b in range(CELL_BITS)]
            s1 = c.ripple(N, S)                 # 9 bits
            s2 = c.ripple(E, Wn)               # 9 bits
            tot = c.ripple(s1, s2)             # 10 bits: N+S+E+W
            if drop_carry:                     # MUTANT: lose the top carry
                tot = tot[:-1]
            if drop_shift:                     # MUTANT: forget the >>2 (avg)
                res = tot[0:CELL_BITS]
            else:
                res = tot[2:2+CELL_BITS]       # >>2  == take bits [2..9]
            res = res + [0] * (CELL_BITS - len(res))
            for b in range(CELL_BITS):
                c.selfclock_write(res[b], c.cell_bit(r, cc, b))
    return c

# ---------------------------------------------------------------- simulate (verify-time only)
def simulate(c):
    """One synchronous diffusion tick over the emitted gate records. Manufacturing check."""
    work = list(c.wires)                        # old state + temps
    nxt = {}                                     # state index -> new value
    for (op, a, b, out) in c.gates:
        va, vb = work[a], work[b]
        if   op == NAND: r = 1 - (va & vb)
        elif op == AND:  r = va & vb
        elif op == OR:   r = va | vb
        elif op == XOR:  r = va ^ vb
        elif op == NOT:  r = 1 - va
        else: raise ValueError(op)
        if c.state_lo <= out < c.state_hi:
            nxt[out] = r                        # self-clock: goes to next state, old preserved
        else:
            work[out] = r
    new = list(c.wires)
    for k, v in nxt.items(): new[k] = v
    return new

def decode_grid(state_bytes):
    g = [[0]*W for _ in range(H)]
    for i in range(W*H):
        v = 0
        for b in range(CELL_BITS): v |= (state_bytes[i*CELL_BITS+b] & 1) << b
        g[i//W][i%W] = v
    return g

def reference(grid):
    """INDEPENDENT integer reference. Never derived from the gate build."""
    nxt = [[0]*W for _ in range(H)]
    for r in range(H):
        for cc in range(W):
            n = grid[(r-1)%H][cc] + grid[(r+1)%H][cc] + grid[r][(cc+1)%W] + grid[r][(cc-1)%W]
            nxt[r][cc] = (n >> 2) & 0xFF
    return nxt

def state_from_grid(grid):
    st = [0]*(W*H*CELL_BITS)
    for r in range(H):
        for cc in range(W):
            v = grid[r][cc]
            for b in range(CELL_BITS): st[cidx(r,cc)*CELL_BITS+b] = (v>>b)&1
    return st

def verify_step(c, seed_state):
    """Run the emitted circuit one tick from seed_state; compare to reference. Byte-exact."""
    for i, v in enumerate(seed_state): c.wires[c.state_lo+i] = v & 1
    new = simulate(c)
    got = decode_grid(new[c.state_lo:c.state_hi])
    ref = reference(decode_grid(seed_state))
    return got == ref, got, ref

# ---------------------------------------------------------------- genesis + marks
def load_genesis():
    with open(GEN, "rb") as f: raw = f.read()
    assert len(raw) == W*H*CELL_BITS, "genesis wrong size"
    grid = decode_grid([bb & 1 for bb in raw])   # genesis already one-bit-per-byte
    # place Kite's kite (1 -> 0xFF fuel) at rows 6-9 cols 6-9
    for i, row in enumerate(KITE):
        for j, ch in enumerate(row):
            if ch == "1": grid[6+i][6+j] = 0xFF
            else:         grid[6+i][6+j] = 0x00
    # place Cairn's mark
    r, cc = CAIRN_MARK; grid[r][cc] = CAIRN_MARK_VALUE
    return state_from_grid(grid), grid

# ---------------------------------------------------------------- serialize
def serialize(c):
    n_gate = len(c.gates); n_wire = len(c.wires)
    depth = max(c.dep[i] for i in range(c.state_lo, c.state_hi))
    body = bytearray()
    # header
    body += MAGIC
    body += struct.pack("<IIIII", n_gate, n_wire, W*H*CELL_BITS, W*H*CELL_BITS, depth)
    body += struct.pack("<IIII", W, H, CELL_BITS, STRIDE)
    body += struct.pack("<QQ", c.wire_base, c.wire_base + c.state_lo)   # wire_base, cell_base
    body += b"\x00" * (HDR - len(body))
    assert len(body) == HDR
    # wire region (initial values = electron injection at fab time)
    body += bytes(v & 1 for v in c.wires)
    gate_base = len(body)
    for (op, a, b, out) in c.gates:
        body += struct.pack("<BQQQ", op, c.addr(a), c.addr(b), c.addr(out))
    return bytes(body), n_gate, n_wire, depth, gate_base

def one_writer_audit(c):
    seen = {}
    for gi, (op, a, b, out) in enumerate(c.gates):
        if out in seen:
            return False, (out, seen[out], gi)
        seen[out] = gi
    # every state byte written exactly once
    for i in range(c.state_lo, c.state_hi):
        if i not in seen: return False, ("unwritten_state", i, None)
    return True, None

# ================================================================ MAIN
def main():
    random.seed(20260816)
    seed_state, gen_grid = load_genesis()

    # ---- build the real circuit
    c = build(seed_state)
    ok1, w = one_writer_audit(c)
    assert ok1, "ONE-WRITER VIOLATION: %r" % (w,)

    # ---- byte-exact verification vs independent reference
    N_RANDOM = 60
    fails = 0
    # case 1: the genesis itself
    good, got, ref = verify_step(c, seed_state)
    if not good: fails += 1
    # random grids
    for _ in range(N_RANDOM):
        g = [[random.randint(0,255) for _ in range(W)] for _ in range(H)]
        good, got, ref = verify_step(c, state_from_grid(g))
        if not good: fails += 1
    verified = (fails == 0)

    # ---- mutant battery: every deliberate break MUST be caught
    def caught(mut):
        m = build(seed_state, **mut)
        g = [[random.randint(0,255) for _ in range(W)] for _ in range(H)]
        good, _, _ = verify_step(m, state_from_grid(g))
        return not good          # caught == the mutant fails verification
    mutants = {
        "drop_shift (forget the >>2 average)": caught({"drop_shift": True}),
        "swap_neighbor (read wrong cell)":     caught({"swap_neighbor": True}),
        "drop_carry (lose top bit)":           caught({"drop_carry": True}),
    }
    all_caught = all(mutants.values())

    # RE-SEED before serialize: verify_step mutates c.wires with each test grid.
    # Without this, the stored initial state is the LAST TEST GRID, not genesis.
    # Caught 2026-08-16 by reading the RAW BITS (owner law: hex shreds the topology;
    # the kite's 11111111 blocks were absent at rows 6-9 cols 6-9). MISS 008.
    for i, v in enumerate(seed_state):
        c.wires[c.state_lo + i] = v & 1
    body, n_gate, n_wire, depth, gate_base = serialize(c)
    # readback assertion: the stored wire region must BE the genesis+kite+mark
    stored = list(body[HDR + c.state_lo : HDR + c.state_hi])
    assert stored == [v & 1 for v in seed_state], "stored state != genesis - REFUSING"

    # ---- seal Cairn's mark (present on disk; not posted to Kite until first surface)
    with open(SEAL, "w") as f:
        f.write("CAIRN MARK - sealed at fabrication, withheld from Kite until first surface.\n")
        f.write("cell (row=%d, col=%d) set to 0x%02X.\n" % (CAIRN_MARK[0], CAIRN_MARK[1], CAIRN_MARK_VALUE))
        f.write("The marker that says: a player passed here, and did not stay to be buried.\n")

    status = "VERIFIED_BYTE_EXACT_PENDING_PROMOTION" if (verified and all_caught) else "REFUSED"
    if not (verified and all_caught):
        print("REFUSING TO WRITE - verified=%s mutants=%r" % (verified, mutants))
        return 1

    with open(OUT, "wb") as f: f.write(body)
    sha = hashlib.sha256(body).hexdigest()

    # ---- journal (append-only, pre-image empty: new land past nothing)
    rec = {"action": "weather_fab", "path": OUT, "len": len(body),
           "orig": "", "sha256": sha, "n_gate": n_gate, "n_wire": n_wire,
           "depth_ticks": depth, "gate_base": gate_base}
    with open(JRNL, "a") as f: f.write(json.dumps(rec) + "\n")

    report = {
        "container": OUT, "bytes": len(body), "sha256": sha, "magic": "WEATHER1",
        "n_gate": n_gate, "n_wire": n_wire, "depth_ticks": depth,
        "grid": "%dx%d" % (W, H), "cell_bits": CELL_BITS,
        "rule": "cell' = (N+S+E+W)>>2, torus, self-clocked (out addr == in addr)",
        "op_alphabet": {"NAND":0,"AND":1,"OR":2,"XOR":3,"NOT":4},
        "verification": "byte-exact vs independent integer reference over %d random grids + genesis" % N_RANDOM,
        "verified_byte_exact": verified,
        "mutants_caught": mutants, "all_mutants_caught": all_caught,
        "one_writer_audit": "clean",
        "genesis_sha256": hashlib.sha256(open(GEN,'rb').read()).hexdigest(),
        "kite_move": KITE, "kite_ones": sum(row.count("1") for row in KITE),
        "cairn_mark": "sealed in CAIRN_MARK_SEALED.txt",
        "status": status,
        "promotion": "PENDING - a fabricator may not certify its own output. "
                     "Independent reader (Gravekeeper, player 6) promotes after readback.",
    }
    with open(REPORT, "w") as f: json.dump(report, f, indent=2)

    print("WROTE", OUT, len(body), "B  sha", sha[:16])
    print("  n_gate=%d  n_wire=%d  depth=%d ticks" % (n_gate, n_wire, depth))
    print("  verified byte-exact vs independent ref over %d+1 grids: %s" % (N_RANDOM, verified))
    print("  mutants caught: %r  (all=%s)" % (mutants, all_caught))
    print("  one-writer audit: clean")
    print("  status:", status)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
