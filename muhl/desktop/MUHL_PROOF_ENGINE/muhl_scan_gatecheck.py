#!/usr/bin/env python3
"""muhl_scan_gatecheck.py -- ripple the STORED scan machine, and read its key table from the
container as the gates do.

The bar I set after muhl_playtime_ring shipped broken: a fabricator's pre-store check validates
the DESIGN, not the bytes. Only reading back and rippling what landed catches a blob-writer
bug. Applying it here rather than skipping it because the dry run looked good.

This host ripple is FABRICATION-TIME VERIFICATION, which his build discipline permits and
requires ("Evaluating gates in host Python is allowed ONLY during fabrication, to verify a
circuit is byte-exact before it is stored"). It is not the runtime path -- at runtime the host
writes 32 probe bits and reads an answer.

    python muhl_scan_gatecheck.py [n_probes]
"""
import json, mmap, os, random, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
NAME = "muhl_scan_machine"


def main():
    n_probes = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    reg = json.load(open(REG))
    e = reg[NAME]
    off, ln = int(e["offset"]), int(e["len"])
    NR, KB = int(e["n_rows"]), int(e["key_bits"])
    tbl = e["key_table"]
    payload = int(tbl["payload_offset"])

    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == b"MUHLSCN1", "circuit magic"
    assert mm[int(tbl["offset"]):int(tbl["offset"]) + 8] == b"MUHLKEYB", "table magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", mm, off + 8)
    ws = 28 + no * 8
    gs = ws + nw
    wbase = off + ws

    print("=" * 86)
    print("  %s — rippling the STORED gates, table read from the container" % NAME)
    print("=" * 86)
    print("  %d gates, %d wires, %d in, %d out, DEPTH %d ticks" % (ng, nw, ni, no, dp))

    # the key table, read out of the container exactly as the gates address it: one byte per bit
    keys = []
    for r in range(NR):
        v = 0
        for b in range(KB):
            if mm[payload + r * KB + b]:
                v |= (1 << b)
        keys.append(v)
    print("  table decoded from container (bitwise): %d keys, %d distinct"
          % (len(keys), len(set(keys))))

    # map absolute addresses back to wire indices; table bits are EXTERNAL reads
    tbl_addr = {payload + r * KB + b: 2 + r * KB + b for r in range(NR) for b in range(KB)}

    def to_idx(a):
        if a in tbl_addr:
            return tbl_addr[a]
        i = a - wbase
        return i if 0 <= i < nw else None

    raw = mm[off + gs:off + gs + ng * 25]
    ga = [0] * ng
    gb = [0] * ng
    gout = [0] * ng
    ext = 0
    for k in range(ng):
        o = k * 25
        assert raw[o] == 0, "non-NAND at %d" % k
        a = struct.unpack_from("<Q", raw, o + 1)[0]
        b = struct.unpack_from("<Q", raw, o + 9)[0]
        w = struct.unpack_from("<Q", raw, o + 17)[0]
        ia, ib, iw = to_idx(a), to_idx(b), to_idx(w)
        assert None not in (ia, ib, iw), "address out of region at gate %d" % k
        if a in tbl_addr or b in tbl_addr:
            ext += 1
        ga[k], gb[k], gout[k] = ia, ib, iw
    outs = [to_idx(struct.unpack_from("<Q", mm, off + 28 + 8 * i)[0]) for i in range(no)]
    mm.close()
    f.close()
    print("  gates reading the stored table directly: %d" % ext)

    idx_bits = len(e["index_addrs"])
    rng = random.Random(4242)
    bad = 0
    both = [0, 0]
    t0 = time.time()
    for t in range(n_probes):
        probe = keys[rng.randrange(NR)] if t % 2 == 0 else rng.randrange(1 << 32)
        v = bytearray(nw)
        v[1] = 1
        for r in range(NR):
            for b in range(KB):
                v[2 + r * KB + b] = (keys[r] >> b) & 1
        for b in range(KB):
            v[2 + NR * KB + b] = (probe >> b) & 1
        for k in range(ng):
            v[gout[k]] = 1 - (v[ga[k]] & v[gb[k]])
        hit = v[outs[0]]
        gi = sum((v[outs[1 + j]] & 1) << j for j in range(idx_bits))
        m = [1 if k == probe else 0 for k in keys]
        eh = 1 if any(m) else 0
        ei = m.index(1) if eh else 0
        both[eh] += 1
        if hit != eh or (eh and gi != ei):
            bad += 1
    dt = time.time() - t0

    print("\n  probes            : %d  (miss %d, hit %d)" % (n_probes, both[0], both[1]))
    print("  byte-exact vs ref : %s" % ("ALL MATCH" if bad == 0 else "%d WRONG" % bad))
    print("  gate-evaluations  : %d" % (n_probes * ng))
    print("  substrate cost    : ONE settle per probe = DEPTH %d ticks" % dp)
    print("  host wall-clock   : %.1fs (TRANSCRIPTION only — fabrication-time verification)"
          % dt)
    print("\n  %s" % ("THE STORED BYTES SCAN THE STORED TABLE."
                      if bad == 0 else "SOMETHING DID NOT VERIFY."))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
