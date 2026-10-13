#!/usr/bin/env python3
# _specdaddy_audit.py — Grok parent, read-only byte audit of weather.mno.
# Dies after print. Does not write weather.mno. Additive new land only.
import struct, hashlib, os, collections

HERE = r"C:\Users\lucys\Desktop\WEATHER"
raw = open(os.path.join(HERE, "weather.mno"), "rb").read()
v0 = open(os.path.join(HERE, "weather_v0_badseed.mno"), "rb").read()
txt = open(os.path.join(HERE, "_audit_bits_txt_pre.txt"), "r", encoding="utf-8").read()
gen = open(os.path.join(HERE, "genesis_playtime_read.bin"), "rb").read()

n_gate, n_wire, n_in, n_out, depth = struct.unpack_from("<IIIII", raw, 8)
W, H, CELL_BITS, STRIDE = struct.unpack_from("<IIII", raw, 28)
wire_base, cell_base = struct.unpack_from("<QQ", raw, 44)
state_lo = cell_base - wire_base
state_hi = state_lo + W * H * CELL_BITS
print("state_lo", state_lo, "state_hi", state_hi, "n_state", state_hi - state_lo)

state = list(raw[cell_base : cell_base + 2048])
print("STATE_BYTES", len(state), "UNIQUE", sorted(set(state)))
print("STATE_NOT_01", sum(1 for b in state if b not in (0, 1)))
print("STATE_BIT1", sum(1 for b in state if b & 1), "STATE_BIT0", sum(1 for b in state if (b & 1) == 0))


def cell_off(r, c):
    return cell_base + (r * 16 + c) * 8


KITE_ONES = [(6, 7), (6, 8), (7, 6), (7, 7), (7, 8), (7, 9), (8, 7), (8, 8), (9, 8)]
KITE_ZEROS = [(6, 6), (6, 9), (8, 6), (8, 9), (9, 6), (9, 7), (9, 9)]
print("--- KITE FROM FILE ---")
all_ff = True
for r, c in KITE_ONES:
    blk = raw[cell_off(r, c) : cell_off(r, c) + 8]
    bits = "".join(str(b & 1) for b in blk)
    print("  kite1 r%dc%d off=%d bytes=%s bits=%s eight1=%s" % (r, c, cell_off(r, c), list(blk), bits, bits == "11111111"))
    if bits != "11111111":
        all_ff = False
for r, c in KITE_ZEROS:
    blk = raw[cell_off(r, c) : cell_off(r, c) + 8]
    bits = "".join(str(b & 1) for b in blk)
    print("  kite0 r%dc%d off=%d bits=%s eight0=%s" % (r, c, cell_off(r, c), bits, bits == "00000000"))
print("KITE_NINE_ONES_IN_FILE", all_ff)

blk = raw[cell_off(5, 5) : cell_off(5, 5) + 8]
bits = "".join(str(b & 1) for b in blk)
val = 0
for i, b in enumerate(blk):
    val |= (b & 1) << i
print("CAIRN_MARK r5c5 bits", bits, "decoded", hex(val), "claim_0xC1", val == 0xC1)

print("--- V0 KITE ---")
v0_hits = 0
for r, c in KITE_ONES:
    blk = v0[cell_off(r, c) : cell_off(r, c) + 8]
    bits = "".join(str(b & 1) for b in blk)
    hit = bits == "11111111"
    v0_hits += int(hit)
    print("  v0 r%dc%d bits=%s eight1=%s" % (r, c, bits, hit))
print("V0_KITE_NINE", v0_hits)

grid = [[0] * 16 for _ in range(16)]
for r in range(16):
    for c in range(16):
        v = 0
        blk = raw[cell_off(r, c) : cell_off(r, c) + 8]
        for b, bb in enumerate(blk):
            v |= (bb & 1) << b
        grid[r][c] = v
print("--- FILE GRID HEX ---")
for r in range(16):
    print(" ".join("%02X" % v for v in grid[r]))

gen_grid = [[0] * 16 for _ in range(16)]
for i in range(256):
    v = 0
    for b in range(8):
        v |= (gen[i * 8 + b] & 1) << b
    gen_grid[i // 16][i % 16] = v
KITE = ["0110", "1111", "0110", "0010"]
exp = [row[:] for row in gen_grid]
for i, row in enumerate(KITE):
    for j, ch in enumerate(row):
        exp[6 + i][6 + j] = 0xFF if ch == "1" else 0x00
exp[5][5] = 0xC1
print("STORED_GRID_EQ_GENESIS_PLUS_KITE_MARK", grid == exp)
print("STORED_EQ_RAW_GENESIS", grid == gen_grid)
diff_cells = [(r, c, gen_grid[r][c], grid[r][c]) for r in range(16) for c in range(16) if gen_grid[r][c] != grid[r][c]]
print("CELLS_CHANGED_FROM_GENESIS", len(diff_cells))
print("CHANGED", diff_cells)


def file_order(bits):
    lines = []
    for r in range(16):
        row = bits[r * 16 * 8 : (r + 1) * 16 * 8]
        lines.append(" ".join("".join(str(b & 1) for b in row[c * 8 : (c + 1) * 8]) for c in range(16)))
    return lines


before_lines = file_order(state)
tlines = txt.splitlines()
idx = None
for i, l in enumerate(tlines):
    if l.startswith("== BEFORE - file order"):
        idx = i + 1
        break
txt_before = tlines[idx : idx + 16]
print("TXT_BEFORE_VS_FILE", txt_before == before_lines)
if txt_before != before_lines:
    for i, (a, b) in enumerate(zip(txt_before, before_lines)):
        if a != b:
            print("  MISMATCH row", i)
            print("  TXT ", a)
            print("  FILE", b)

# AFTER section of txt vs independent settle of stored gates
NAND, AND, OR, XOR, NOT = 0, 1, 2, 3, 4
gate_base = 96 + n_wire
print("gate_base", gate_base, "claim_34146", gate_base == 34146)
gates = []
for k in range(n_gate):
    op, a, b, out = struct.unpack_from("<BQQQ", raw, gate_base + k * STRIDE)
    gates.append((op, a, b, out))

wires = list(raw[wire_base : wire_base + n_wire])
work = list(wires)
nxt = {}
for op, a, b, out in gates:
    ai = a - wire_base
    bi = b - wire_base
    oi = out - wire_base
    va, vb = work[ai], work[bi]
    if op == NAND:
        r = 1 - (va & vb)
    elif op == AND:
        r = va & vb
    elif op == OR:
        r = va | vb
    elif op == XOR:
        r = va ^ vb
    elif op == NOT:
        r = 1 - va
    else:
        raise SystemExit("unknown op %r" % op)
    if state_lo <= oi < state_hi:
        nxt[oi] = r
    else:
        work[oi] = r
after = list(wires)
for k2, v in nxt.items():
    after[k2] = v
after_state = after[state_lo:state_hi]
after_lines = file_order(after_state)
idx2 = None
for i, l in enumerate(tlines):
    if l.startswith("== AFTER one settle"):
        idx2 = i + 1
        break
txt_after = tlines[idx2 : idx2 + 16]
print("TXT_AFTER_VS_FILE_SETTLE", txt_after == after_lines)
if txt_after != after_lines:
    nmis = sum(1 for a, b in zip(txt_after, after_lines) if a != b)
    print("  AFTER_MISMATCH_ROWS", nmis)

# independent integer reference
def decode(st):
    g = [[0] * 16 for _ in range(16)]
    for i in range(256):
        v = 0
        for b in range(8):
            v |= (st[i * 8 + b] & 1) << b
        g[i // 16][i % 16] = v
    return g

def reference(g):
    nxtg = [[0] * 16 for _ in range(16)]
    for r in range(16):
        for c in range(16):
            n = g[(r - 1) % 16][c] + g[(r + 1) % 16][c] + g[r][(c + 1) % 16] + g[r][(c - 1) % 16]
            nxtg[r][c] = (n >> 2) & 0xFF
    return nxtg

got = decode(after_state)
ref = reference(grid)
print("SETTLE_EQ_INDEPENDENT_REF", got == ref)

ops = collections.Counter()
writers = collections.Counter()
selfclock_state = 0
identity_loop = 0
state_written = set()
state_read = set()
nand_to_state = and_to_state = or_to_state = xor_to_state = not_to_state = 0
unknown_op = 0
state_addrs = set(range(cell_base, cell_base + 2048))
src_kinds = collections.Counter()
const1_as_in = 0
const0_as_in = 0
for op, a, b, out in gates:
    ops[op] += 1
    writers[out] += 1
    if op > 4:
        unknown_op += 1
    if a == wire_base + 1 or b == wire_base + 1:
        const1_as_in += 1
    if a == wire_base or b == wire_base:
        const0_as_in += 1
    if out in state_addrs:
        state_written.add(out)
        if op == 0:
            nand_to_state += 1
        elif op == 1:
            and_to_state += 1
        elif op == 2:
            or_to_state += 1
        elif op == 3:
            xor_to_state += 1
        elif op == 4:
            not_to_state += 1
        if a == out or b == out:
            identity_loop += 1
        if a == b and op == 2:
            selfclock_state += 1

        def kind(x):
            if x == wire_base:
                return "const0"
            if x == wire_base + 1:
                return "const1"
            if x in state_addrs:
                return "state"
            return "temp"

        src_kinds[(kind(a), kind(b), op)] += 1
    if a in state_addrs:
        state_read.add(a)
    if b in state_addrs:
        state_read.add(b)

print("OPS", dict(sorted(ops.items())))
print("UNKNOWN_OP", unknown_op)
print("STATE_WRITTEN", len(state_written), "of 2048")
print("STATE_READ_AS_INPUT", len(state_read), "of 2048")
print("ONE_WRITER", max(writers.values()) == 1 and len(writers) == n_gate)
print("MULTI_WRITERS", sum(1 for n in writers.values() if n > 1))
print("SELF CLOCK OR(src,src)->state", selfclock_state)
print("IDENTITY_LOOP out==a|b on state", identity_loop)
print("OPS_TO_STATE NAND/AND/OR/XOR/NOT", nand_to_state, and_to_state, or_to_state, xor_to_state, not_to_state)
print("N_UNIQUE_OUT", len(writers), "n_gate", n_gate)
print("WIRE0", raw[wire_base], "WIRE1", raw[wire_base + 1])
print("GATES_WRITING_STATE", sum(1 for o in writers if o in state_addrs))
print("GATES_WRITING_TEMP", n_gate - sum(1 for o in writers if o in state_addrs))
print("STATE_WRITE_SOURCES", dict(src_kinds))
print("CONST1_AS_INPUT", const1_as_in, "CONST0_AS_INPUT", const0_as_in)

# unwritten state?
unwritten = [a for a in state_addrs if a not in state_written]
print("UNWRITTEN_STATE", len(unwritten))
unread = [a for a in state_addrs if a not in state_read]
print("UNREAD_STATE", len(unread))

# header vs standard 8+<IIIII>
print("HEADER_MAGIC", raw[:8])
print("HEADER_IS_WEATHER1_96", raw[:8] == b"WEATHER1" and len(raw) >= 96)
print("STANDARD_8_PLUS_IIIII_WOULD_SEE_MAGIC", raw[:8], "then n_gate at +8 =", n_gate)

print("DONE_PARSE")
