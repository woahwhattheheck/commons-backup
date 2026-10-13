#!/usr/bin/env python3
# muhl_weather_ring_fire.py — ONE start into weather_v2.mno, address stored outs, die.
# 0x01 both senses at cell 0 of each ring. Dest from this file's header. AFTER in this file.

import struct, os, json, hashlib

HERE = r"C:\Users\lucys\Desktop\WEATHER"
PKG = os.path.join(HERE, "weather_v2.mno")
JRNL = os.path.join(HERE, "weather_genome.jsonl")
NAND, AND, OR, XOR = 0, 1, 2, 3
STRIDE = 25
HDR = 96

def main():
    img = bytearray(open(PKG, "rb").read())
    assert img[:8] == b"WEATHER1", img[:8]
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", img, 8)
    cell_base = struct.unpack_from("<Q", img, 52)[0]
    n_rings, cells = struct.unpack_from("<II", img, 68)
    ring0 = struct.unpack_from("<Q", img, 76)[0]
    assert n_rings == 6 and cells == 32
    span = cells + cells + 2
    pre = []
    for ri in range(n_rings):
        fwd = ring0 + ri * span
        rev = fwd + cells
        pre.append({"ri": ri, "fwd": fwd, "rev": rev, "old_fwd": img[fwd], "old_rev": img[rev]})
        img[fwd] = img[fwd] | 0x01
        img[rev] = img[rev] | 0x01
    gate_base = HDR + n_wire
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", img, gate_base + k * STRIDE)
        va, vb = img[a] & 1, img[b] & 1
        if op == NAND: r = 1 - (va & vb)
        elif op == AND: r = va & vb
        elif op == OR:  r = va | vb
        elif op == XOR: r = va ^ vb
        else: raise SystemExit("bad op %d" % op)
        img[out] = r
    open(PKG, "wb").write(img)
    sha = hashlib.sha256(img).hexdigest()
    with open(JRNL, "a") as f:
        f.write(json.dumps({"action": "weather_v2_fire", "path": PKG,
                            "pre": pre, "sha256_after": sha, "n_gate_addressed": n_gate}) + "\n")
    ones = sum(1 for i in range(2048) if img[cell_base + i] & 1)
    print("FIRE weather_v2  both-senses 0x01 x %d rings" % n_rings)
    for p in pre:
        print("  ring%d fwd@%d rev@%d  old %d/%d" % (p["ri"], p["fwd"], p["rev"], p["old_fwd"], p["old_rev"]))
    print("  addressed %d stored outs  AFTER in file  field_ones=%d" % (n_gate, ones))
    print("  sha", sha)
    print("337 NO")
    print("titan_written NO")
    print("button dies")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
