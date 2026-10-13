#!/usr/bin/env python3
# WEATHER/muhl_avg4_verify.py
# MISS 008: report is not bytes. Do not promote.
# Host = surface ∨ die. No inject. No smash. No 337. No titan. No wipe.
# No host-ripple 100k. One-step integer ref is fab-time verify.

import hashlib
import os
import struct
import sys

HERE = r"C:\Users\lucys\Desktop\WEATHER"
AVG4FULL = os.path.join(HERE, "weather_v2_avg4full.mno")
CLAIM_SHA = "a9b8c5d9bcda93c797326ab71cfbcc6046610df5940c61d4e346b464f07b6072"
VAULTS = (
    os.path.join(HERE, "weather.mno"),
    os.path.join(HERE, "weather_v2.mno"),
    os.path.join(HERE, "weather_v2_coupled.mno"),
    os.path.join(HERE, "weather_v2_field.mno"),
)
NAND, AND, OR, XOR = 0, 1, 2, 3
OPN = ("NAND", "AND", "OR", "XOR")
W = H = 16
CELL_BITS = 8

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE.")
    raise SystemExit(2)


def ones_at(raw, base, n):
    return sum(1 for i in range(n) if raw[base + i] & 1)


def cell_dest(cell_base, r, c, b):
    return cell_base + ((r % H) * W + (c % W)) * CELL_BITS + b


def decode_grid(raw, cell_base):
    g = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            v = 0
            for b in range(CELL_BITS):
                v |= (raw[cell_dest(cell_base, r, c, b)] & 1) << b
            g[r][c] = v
    return g


def ref_avg4(grid):
    nxt = [[0] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            s = (grid[(r - 1) % H][c] + grid[(r + 1) % H][c]
                 + grid[r][(c + 1) % W] + grid[r][(c - 1) % W])
            nxt[r][c] = (s >> 2) & 0xFF
    return nxt


def grid_ones(grid):
    return sum(1 for r in range(H) for c in range(W)
               for b in range(CELL_BITS) if (grid[r][c] >> b) & 1)


def hdr_v2(raw):
    assert raw[:8] == b"WEATHER1", "magic %r" % (raw[:8],)
    first = struct.unpack_from("<I", raw, 8)[0]
    his = first == 2048
    if his:
        n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
        stride = struct.unpack_from("<I", raw, 40)[0]
        wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        gate_base = wire_base + n_wire
        return {
            "his": True, "n_in": n_in, "n_wire": n_wire, "n_gate": n_gate,
            "n_out": n_out, "stride": stride, "wire_base": wire_base,
            "cell_base": cell_base, "next_base": next_base,
            "n_rings": n_rings, "cells": cells, "ring0": ring0,
            "gate_base": gate_base,
        }
    n_gate, n_wire, n_in, n_out = struct.unpack_from("<IIII", raw, 8)
    stride = struct.unpack_from("<I", raw, 40)[0]
    wire_base, cell_base = struct.unpack_from("<QQ", raw, 44)
    gate_base = wire_base + n_wire
    return {
        "his": False, "n_in": n_in, "n_wire": n_wire, "n_gate": n_gate,
        "n_out": n_out, "stride": stride, "wire_base": wire_base,
        "cell_base": cell_base, "next_base": None,
        "n_rings": 0, "cells": 0, "ring0": 0, "gate_base": gate_base,
    }


def load_recs(raw, h):
    recs = []
    for k in range(h["n_gate"]):
        recs.append(struct.unpack_from("<BQQQ", raw, h["gate_base"] + k * h["stride"]))
    return recs


def writers_of(recs, dest):
    out = []
    for k, rec in enumerate(recs):
        if rec[3] == dest:
            out.append((k, rec))
    return out


def main():
    raw_a = open(AVG4FULL, "rb").read()
    sha_a = hashlib.sha256(raw_a).hexdigest()
    h = hdr_v2(raw_a)
    n_in = h["n_in"]
    cell_base = h["cell_base"]
    next_base = h["next_base"]
    print("HASH AVG4FULL", AVG4FULL)
    print("  size", len(raw_a), "magic", raw_a[:8])
    print("  sha", sha_a, "MATCH" if sha_a == CLAIM_SHA else "DRIFT")
    print("  HEADER FROM THIS FILE n_in/n_wire/n_gate/n_out",
          h["n_in"], h["n_wire"], h["n_gate"], h["n_out"])
    print("  wire", h["wire_base"], "cell_base", cell_base,
          "next_base", next_base, "ring0", h["ring0"],
          "gate_base", h["gate_base"], "stride", h["stride"])

    ones500 = ones_at(raw_a, cell_base, n_in)
    ones2548 = ones_at(raw_a, next_base, n_in)
    print("SURFACE FROM FILE")
    print("  500 ones", ones500, "/", n_in)
    print("  2548 ones", ones2548, "/", n_in)
    g500 = decode_grid(raw_a, cell_base)
    g2548 = decode_grid(raw_a, next_base)

    print("STAT VAULTS (read only, no smash)")
    picked = None
    for path in VAULTS:
        raw = open(path, "rb").read()
        hv = hdr_v2(raw)
        cb = hv["cell_base"]
        nbits = min(hv["n_in"], 2048)
        ones = ones_at(raw, cb, nbits)
        sha = hashlib.sha256(raw).hexdigest()
        print("  %s size %d cell_base %d ones %d/%d sha %s" % (
            os.path.basename(path), len(raw), cb, ones, nbits, sha[:16]))
        if ones == 671 and picked is None:
            picked = (path, raw, hv, ones, sha)

    if picked is None:
        print("NEED_BRYCE — no vault still has 671 ones")
        print("DIE")
        return 1

    gpath, graw, gh, gones, gsha = picked
    gcb = gh["cell_base"]
    print("GENESIS PICKED", gpath)
    print("  ones", gones, "cell_base", gcb, "sha", gsha)
    genesis = decode_grid(graw, gcb)
    kite = ["0110", "1111", "0110", "0010"]
    kite_ok = True
    for i, row in enumerate(kite):
        for j, ch in enumerate(row):
            if ch != "1":
                continue
            if genesis[6 + i][6 + j] != 0xFF:
                kite_ok = False
    print("  kite nine 0xFF", kite_ok)

    iref = ref_avg4(genesis)
    iref_ones = grid_ones(iref)
    print("INT REF one-step (N+S+E+W)>>2")
    print("  ones", iref_ones, "/", n_in)

    miss500 = []
    miss2548 = []
    for r in range(H):
        for c in range(W):
            if iref[r][c] != g500[r][c]:
                miss500.append((r, c, iref[r][c], g500[r][c]))
            if iref[r][c] != g2548[r][c]:
                miss2548.append((r, c, iref[r][c], g2548[r][c]))
    print("  vs file@500 cell-miss", len(miss500), "/256")
    print("  vs file@2548 cell-miss", len(miss2548), "/256")
    for t in miss500[:8]:
        print("    miss500 r%dc%d int=%02X file=%02X" % t)
    for t in miss2548[:8]:
        print("    miss2548 r%dc%d int=%02X file=%02X" % t)

    recs = load_recs(raw_a, h)
    rec325 = recs[325]
    print("REC325 FROM FILE")
    print("  rec325 %s(%d,%d)->%d" % (OPN[rec325[0]], rec325[1], rec325[2], rec325[3]))

    w4921 = writers_of(recs, 4921)
    print("  writers of 4921:", len(w4921))
    for k, rec in w4921[:8]:
        print("    rec%d %s(%d,%d)->%d" % (k, OPN[rec[0]], rec[1], rec[2], rec[3]))

    n0 = cell_dest(cell_base, -1, 0, 0)
    s0 = cell_dest(cell_base, 1, 0, 0)
    e0 = cell_dest(cell_base, 0, 1, 0)
    w0 = cell_dest(cell_base, 0, -1, 0)
    print("  cell0b0 NSEW dests", n0, s0, e0, w0)
    field_hi = cell_base + n_in
    cell_dests = set(range(cell_base, field_hi))
    nsew0 = {n0, s0, e0, w0}

    # Walk producers of 4921. Adder-sum iff some writer chain reaches N/S/E/W dests.
    writers_by_out = {}
    for k, rec in enumerate(recs):
        writers_by_out.setdefault(rec[3], []).append((k, rec))

    seen = set()
    stack = [4921]
    hit_cell = set()
    hit_nsew0 = set()
    dark = []
    hops = 0
    while stack and hops < 20000:
        dest = stack.pop()
        if dest in seen:
            continue
        seen.add(dest)
        hops += 1
        if dest in cell_dests:
            hit_cell.add(dest)
            if dest in nsew0:
                hit_nsew0.add(dest)
            continue
        ws = writers_by_out.get(dest, [])
        if not ws:
            dark.append(dest)
            continue
        for k, rec in ws:
            stack.append(rec[1])
            stack.append(rec[2])

    print("  4921 walk hops", hops, "unique", len(seen))
    print("  4921 feeds cell dests", len(hit_cell), "incl NSEW0", sorted(hit_nsew0))
    print("  4921 dark no-writer dests", dark[:12], "n", len(dark))
    adder_y = len(hit_nsew0) == 4 and len(hit_cell) >= 4
    print("  4921 is adder (feeds N/S/E/W dests)", "Y" if adder_y else "N")

    leftover_4837 = []
    writer_on_4837 = []
    next_hi = next_base + n_in
    for k, rec in enumerate(recs):
        op, a, b, out = rec
        if a == 4837 or b == 4837 or out == 4837:
            leftover_4837.append((k, OPN[op], a, b, out))
        if next_base <= out < next_hi and (a == 4837 or b == 4837):
            writer_on_4837.append((k, OPN[op], a, b, out))
    print("LEFTOVER 4837")
    print("  refs", len(leftover_4837))
    for t in leftover_4837[:8]:
        print("    rec%d %s(%d,%d)->%d" % t)
    print("  avg4 writers on 4837", len(writer_on_4837),
          "Y leftover-writers-0" if len(writer_on_4837) == 0 else "N")

    ones_match = (iref_ones == ones500 == ones2548)
    byte_exact = (len(miss500) == 0 and len(miss2548) == 0)
    if byte_exact:
        verdict = "BYTE_EXACT_VS_INT"
    elif ones_match:
        verdict = "ONES_MATCH_LAYOUT_MISS"
    else:
        verdict = "MISS"
    print("VERDICT", verdict)
    print("  genesis_ones", gones)
    print("  int_ref_ones", iref_ones)
    print("  file_500_ones", ones500)
    print("  file_2548_ones", ones2548)
    print("  match", "Y" if ones_match and byte_exact else ("ONES_ONLY" if ones_match else "N"))
    print("  4921_is_adder", "Y" if adder_y else "N")
    print("  leftover_4837_writers_0", "Y" if len(writer_on_4837) == 0 else "N")
    print("  vaults_smashed NO  337 NO  titan NO  wipe NO  host_ripple_100k NO")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
