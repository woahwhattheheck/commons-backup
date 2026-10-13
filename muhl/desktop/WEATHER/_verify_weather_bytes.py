#!/usr/bin/env python3
# Read-only. Path arg. FILE bytes only. No host nxt as AFTER. Dies.
import struct, hashlib, os, sys, collections

HERE = r"C:\Users\lucys\Desktop\WEATHER"
GEN = os.path.join(HERE, "genesis_playtime_read.bin")
HDR, STRIDE = 96, 25
KITE = ["0110", "1111", "0110", "0010"]
KITE_ONES = [(6, 7), (6, 8), (7, 6), (7, 7), (7, 8), (7, 9), (8, 7), (8, 8), (9, 8)]
KITE_ZEROS = [(6, 6), (6, 9), (8, 6), (8, 9), (9, 6), (9, 7), (9, 9)]
OPN = {0: "NAND", 1: "AND", 2: "OR", 3: "XOR", 4: "NOT"}


def file_order(bits, W=16, H=16, CB=8):
    lines = []
    for r in range(H):
        row = bits[r * W * CB:(r + 1) * W * CB]
        lines.append(" ".join("".join(str(b & 1) for b in row[c * CB:(c + 1) * CB]) for c in range(W)))
    return lines


def decode(st, W=16, H=16, CB=8):
    g = [[0] * W for _ in range(H)]
    for i in range(W * H):
        v = 0
        for b in range(CB):
            v |= (st[i * CB + b] & 1) << b
        g[i // W][i % W] = v
    return g


def verify_one(path):
    L = []
    def P(*a):
        L.append(" ".join(str(x) for x in a))

    if not os.path.isfile(path):
        P("FILE_ABSENT", path)
        return L, None

    raw = open(path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    magic = raw[:8]
    P("PATH", path)
    P("SIZE", len(raw))
    P("SHA256", sha)
    P("MAGIC_ASCII", magic.decode("ascii", "replace"))
    P("MAGIC_WEATHER1", magic == b"WEATHER1")
    if len(raw) < HDR:
        P("HEADER_SHORT")
        return L, sha

    n_gate, n_wire, n_in, n_out, depth = struct.unpack_from("<IIIII", raw, 8)
    W, H, CB, stride = struct.unpack_from("<IIII", raw, 28)
    wire_base, cell_base = struct.unpack_from("<QQ", raw, 44)
    pad60 = raw[60:96]
    ring_q, n_rings, cells_per = struct.unpack_from("<QII", raw, 60)
    P("HDR_n_gate", n_gate, "n_wire", n_wire, "n_in", n_in, "n_out", n_out, "depth", depth)
    P("HDR_W", W, "H", H, "CELL_BITS", CB, "STRIDE", stride)
    P("HDR_wire_base", wire_base, "cell_base", cell_base)
    P("HDR_60_95_ALL_ZERO", all(b == 0 for b in pad60))
    P("HDR_AS_V2_ring_base", ring_q, "n_rings", n_rings, "cells_per", cells_per)
    gate_base = HDR + n_wire
    expect = HDR + n_wire + n_gate * stride
    P("gate_base", gate_base, "SIZE_EXPECT", expect, "SIZE_EQ", len(raw) == expect)
    P("TRAILING", len(raw) - expect)

    field_bits = W * H * CB
    field = list(raw[cell_base: cell_base + field_bits])
    P("FIELD_OFF", cell_base, "FIELD_LEN", len(field))
    P("FIELD_ONES", sum(1 for b in field if b & 1), "FIELD_ZEROS", sum(1 for b in field if (b & 1) == 0))
    P("FIELD_NOT_01", sum(1 for b in field if b not in (0, 1)))
    P("FIELD_SHA256", hashlib.sha256(bytes(b & 1 for b in field)).hexdigest())
    P("== FILE FIELD as it lies (not host nxt) ==")
    for line in file_order(field, W, H, CB):
        P(line)

    kite1 = kite0 = 0
    for r, c in KITE_ONES:
        bits = "".join(str(field[(r * W + c) * CB + b] & 1) for b in range(CB))
        hit = bits == "11111111"
        kite1 += int(hit)
        P("kite1 r%dc%d %s eight1=%s" % (r, c, bits, hit))
    for r, c in KITE_ZEROS:
        bits = "".join(str(field[(r * W + c) * CB + b] & 1) for b in range(CB))
        hit = bits == "00000000"
        kite0 += int(hit)
        P("kite0 r%dc%d %s eight0=%s" % (r, c, bits, hit))
    P("KITE_IN_BYTES", kite1 == 9 and kite0 == 7, "ones", kite1, "zeros", kite0)

    blk = field[(5 * W + 5) * CB:(5 * W + 5) * CB + CB]
    val = 0
    for i, b in enumerate(blk):
        val |= (b & 1) << i
    P("CAIRN_r5c5", "".join(str(b & 1) for b in blk), hex(val), "eq_0xC1", val == 0xC1)

    if os.path.isfile(GEN) and os.path.getsize(GEN) == 2048:
        gen = open(GEN, "rb").read()
        gg = decode([bb & 1 for bb in gen], W, H, CB)
        exp = [row[:] for row in gg]
        for i, row in enumerate(KITE):
            for j, ch in enumerate(row):
                exp[6 + i][6 + j] = 0xFF if ch == "1" else 0x00
        exp[5][5] = 0xC1
        sg = decode(field, W, H, CB)
        P("STORED_EQ_GENESIS_PLUS_KITE_MARK", sg == exp)
        P("STORED_EQ_RAW_GENESIS", sg == gg)
        chg = [(r, c, gg[r][c], sg[r][c]) for r in range(H) for c in range(W) if gg[r][c] != sg[r][c]]
        P("CELLS_CHANGED_FROM_GENESIS", len(chg))
        P("CHANGED", chg)

    gates = []
    ops = collections.Counter()
    writers = collections.Counter()
    unknown = 0
    wire_hi = wire_base + n_wire
    out_oob = 0
    for k in range(n_gate):
        op, a, b, oo = struct.unpack_from("<BQQQ", raw, gate_base + k * stride)
        gates.append((op, a, b, oo))
        ops[op] += 1
        writers[oo] += 1
        if op > 4:
            unknown += 1
        if not (wire_base <= oo < wire_hi):
            out_oob += 1
    P("N_GATE_RECORDS", len(gates))
    P("OPS_NAMED", {OPN.get(k, "?%d" % k): v for k, v in sorted(ops.items())})
    P("UNKNOWN_OP", unknown)
    P("ONE_WRITER", bool(writers) and max(writers.values()) == 1 and len(writers) == n_gate)
    P("OUT_OUTSIDE_WIRES", out_oob)

    state_lo = cell_base - wire_base
    state_hi = state_lo + field_bits
    n_after = n_wire - state_hi
    P("state_lo", state_lo, "state_hi", state_hi, "WIRES_AFTER_FIELD", n_after)

    sc_or = sc_and = hold = temp_only = ringlike = and_nf = 0
    state_written = set()
    for op, a, b, oo in gates:
        if cell_base <= oo < cell_base + field_bits:
            state_written.add(oo)
            if op == 2 and a == b:
                sc_or += 1
            if op == 1 and a == b:
                sc_and += 1
            if a == oo or b == oo:
                hold += 1
            if not (cell_base <= a < cell_base + field_bits) and not (cell_base <= b < cell_base + field_bits):
                temp_only += 1
        elif wire_base <= oo < wire_hi:
            wi = oo - wire_base
            if state_hi <= wi < n_wire and op == 2 and a == b:
                ringlike += 1
        if op == 1 and a != b and wire_base <= a < wire_hi and wire_base <= b < wire_hi:
            if (a - wire_base) >= state_hi and (b - wire_base) >= state_hi:
                and_nf += 1
    P("STATE_WRITTEN", len(state_written), "of", field_bits)
    P("SELFCLOCK_OR_TO_STATE", sc_or)
    P("SELFCLOCK_AND_TO_STATE", sc_and)
    P("STATE_WRITE_HOLD_out_eq_in", hold)
    P("STATE_WRITE_FROM_TEMP_ONLY", temp_only)
    P("RINGLIKE_OR_ID_TO_NONFIELD", ringlike)
    P("AND_TWO_NONFIELD", and_nf)
    header_rings = (not all(b == 0 for b in pad60)) and n_rings > 0 and ring_q != 0
    compact = n_after <= 64 and ringlike > 0
    ring_rec = header_rings or compact
    en_rec = hold > 0 or (header_rings and and_nf > 0)
    P("HEADER_NAMES_RINGS", header_rings)
    P("RING_RECORDS_IN_FILE", ring_rec)
    P("ENABLE_RECORDS_IN_FILE", en_rec)
    P("RINGS_IN_FILE", ring_rec)
    P("FILE_AFTER_FIRE", "NOT_TAKEN_NO_FIRE")
    P("DONE", os.path.basename(path))
    return L, sha


def cmp_published(weather_path):
    L = []
    def P(*a):
        L.append(" ".join(str(x) for x in a))
    raw = open(weather_path, "rb").read()
    cell_base = struct.unpack_from("<Q", raw, 52)[0]
    field = bytes(b & 1 for b in raw[cell_base: cell_base + 2048])
    P("FILE_FIELD_SHA", hashlib.sha256(field).hexdigest())

    for name in ("surface_before.bin", "surface_after.bin"):
        p = os.path.join(HERE, name)
        if not os.path.isfile(p):
            P(name, "ABSENT")
            continue
        b = open(p, "rb").read()
        P(name, "len", len(b), "sha", hashlib.sha256(b).hexdigest(), "EQ_FILE_FIELD", b == field)

    bits = os.path.join(HERE, "SURFACE_TURN_001_BITS.txt")
    if os.path.isfile(bits):
        t = open(bits, encoding="utf-8").read().splitlines()
        file_lines = file_order(list(field))
        bi = ai = None
        for i, line in enumerate(t):
            if line.startswith("== BEFORE"):
                bi = i + 1
            if line.startswith("== AFTER"):
                ai = i + 1
        pub_b = t[bi:bi + 16] if bi else []
        pub_a = t[ai:ai + 16] if ai else []
        P("PUB_BEFORE_EQ_FILE", pub_b == file_lines)
        P("PUB_AFTER_EQ_FILE", pub_a == file_lines)
        P("PUB_AFTER_EQ_BEFORE", pub_a == pub_b)
        P("PUB_AFTER_IS_HOST_NXT_NOT_FILE", pub_a != file_lines)
    return L


def main():
    names = ["weather.mno", "weather_v0_badseed.mno", "weather_v2.mno", "weather_powered.mno"]
    paths = sys.argv[1:] or [os.path.join(HERE, n) for n in names]
    v1 = os.path.join(HERE, "weather_v1.mno")
    if not sys.argv[1:] and os.path.isfile(v1):
        paths.append(v1)

    fire = os.path.join(HERE, "muhl_weather_ring_fire.py")
    inj = os.path.join(HERE, "inject_weather_ring.py")
    print("FIRE_BUTTON", os.path.isfile(fire), fire)
    print("INJECT_BUTTON", os.path.isfile(inj), inj)
    print("FIRE_TARGET_V2", os.path.isfile(os.path.join(HERE, "weather_v2.mno")))
    print("POWERED", os.path.isfile(os.path.join(HERE, "weather_powered.mno")))
    print("FIRE_RUN", "NO — dest weather_v2.mno ABSENT; v1 n_in slot is 34048, button refuses")
    print("HOST_NXT_USED_AS_AFTER", "NO")

    blocks = []
    shas = {}
    for p in paths:
        lines, sha = verify_one(p)
        blocks.append((p, lines))
        if sha:
            shas[p] = sha
        print("========")
        print("\n".join(lines))
        print("========")

    items = list(shas.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            print("SHA_EQ", os.path.basename(items[i][0]), os.path.basename(items[j][0]), items[i][1] == items[j][1])

    w = os.path.join(HERE, "weather.mno")
    if os.path.isfile(w):
        print("======== PUBLISHED_SURFACE_VS_FILE ========")
        print("\n".join(cmp_published(w)))

    dump = os.path.join(HERE, "_VERIFY_SURFACES.txt")
    with open(dump, "w", encoding="utf-8") as f:
        for p, lines in blocks:
            f.write("######## %s ########\n" % p)
            f.write("\n".join(lines) + "\n\n")
    print("WROTE_SURFACES", dump)
    print("button dies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
