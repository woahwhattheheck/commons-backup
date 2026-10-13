#!/usr/bin/env python3
# WEATHER/muhl_couple_weather_v2.py
# BYTE CHECK (Bryce): shared address is the wire.
# AND/enable/avg4 INPUT addrs must equal ring dests 104/136/… or the
# electron on fwd0/rev0 is not on that gate.
# Miss: carry AND inputs already ARE 104/136; 256 enable AND outs are
# temps (87796…); mux/avg4 readers of those temps are different numbers.
# Patch: those readers' a/b retarget to the ring dest (fwd0) of that AND.
# Gates not deleted. Rails not re-ORed (1→1 is not a new address).
# NEW file weather_v2_coupled.mno. Do not smash v2. No titan/337/wipe.

import hashlib
import json
import os
import struct
import sys

HERE = r"C:\Users\lucys\Desktop\WEATHER"
SRC = os.path.join(HERE, "weather_v2.mno")
OUT = os.path.join(HERE, "weather_v2_coupled.mno")
JRNL = os.path.join(HERE, "weather_genome.jsonl")
V2_SHA = "cc2775fdd29d1e5ff1a8f2951e5f5f22dd1c2e237c9e10d6b2d47717476ba85d"
AND = 1
STRIDE = 25

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE.")
    raise SystemExit(2)


def main():
    raw = open(SRC, "rb").read()
    src_sha = hashlib.sha256(raw).hexdigest()
    assert raw[:8] == b"WEATHER1"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw, 8)
    stride = struct.unpack_from("<I", raw, 40)[0]
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw, 44)
    n_rings, cells = struct.unpack_from("<II", raw, 68)
    ring0, clock = struct.unpack_from("<QQ", raw, 76)
    gate_base = wire_base + n_wire
    span = cells + cells + 2
    assert n_in == 2048 and n_rings == 6 and cells == 32 and stride == STRIDE

    fwds = [ring0 + ri * span for ri in range(n_rings)]
    revs = [f + cells for f in fwds]
    carries = [f + 2 * cells for f in fwds]
    rail_pairs = set(zip(fwds, revs))
    carryset = set(carries)
    ring_dests = set(fwds + revs + carries + [c + 1 for c in carries])

    recs = [list(struct.unpack_from("<BQQQ", raw, gate_base + k * STRIDE))
            for k in range(n_gate)]

    # enable AND: both-rail inputs, out is NOT a ring dest (the temps)
    temp_to_fwd = {}
    en_and = 0
    for op, a, b, out in recs:
        pair = (a, b) if a <= b else (b, a)
        if op == AND and pair in rail_pairs and out not in carryset:
            temp_to_fwd[out] = pair[0]  # fwd dest from file
            en_and += 1
    assert en_and == 256, "enable AND temps %d" % en_and

    patched = 0
    for rec in recs:
        op, a, b, out = rec
        na, nb = a, b
        if a in temp_to_fwd:
            na = temp_to_fwd[a]
            patched += 1
        if b in temp_to_fwd:
            nb = temp_to_fwd[b]
            patched += 1
        rec[1], rec[2] = na, nb

    img = bytearray(raw)
    for k, rec in enumerate(recs):
        struct.pack_into("<BQQQ", img, gate_base + k * STRIDE, *rec)

    # rails / field / carry untouched — 1→1 is not a new address
    for dest in fwds + revs:
        assert img[dest] == raw[dest]
    assert img[cell_base:cell_base + n_in] == raw[cell_base:cell_base + n_in]
    for c in carries:
        assert img[c] == raw[c]

    v2_now = hashlib.sha256(open(SRC, "rb").read()).hexdigest()
    assert v2_now == src_sha, "v2 smashed during patch"
    with open(OUT, "wb") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())
    out_sha = hashlib.sha256(img).hexdigest()
    v2_after = hashlib.sha256(open(SRC, "rb").read()).hexdigest()

    # prove coupled mux/enable inputs now share ring dests
    recs2 = [struct.unpack_from("<BQQQ", img, gate_base + k * STRIDE)
             for k in range(n_gate)]
    mux_share = 0
    still_temp = 0
    for op, a, b, out in recs2:
        if a in temp_to_fwd or b in temp_to_fwd:
            still_temp += 1
        if a in ring_dests or b in ring_dests:
            mux_share += 1

    with open(JRNL, "a") as f:
        f.write(json.dumps({
            "action": "weather_v2_coupled_shared_addr",
            "src": SRC, "src_sha256": src_sha, "v2_still": v2_after,
            "out": OUT, "sha256": out_sha,
            "enable_AND_temps": en_and,
            "reader_inputs_retargeted_to_fwd": patched,
            "records_now_sharing_ring_dest": mux_share,
            "readers_still_on_temp": still_temp,
            "rails_re_ored": False,
            "v2_smashed": False,
        }) + "\n")

    print("COUPLE", OUT)
    print("  v2_sha", src_sha, "MATCH" if src_sha == V2_SHA else "DRIFT")
    print("  v2_smashed", "NO" if v2_after == src_sha else "YES")
    print("  enable_AND_temps", en_and, "reader_inputs_to_fwd", patched)
    print("  records_sharing_ring_dest", mux_share, "still_on_temp", still_temp)
    print("  coupled_sha", out_sha)
    print("  rails_re_ored NO  carry_written NO")
    print("  337 NO  titan NO")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
