#!/usr/bin/env python3
# muhl_fab_table_mail.py
# NEW LAND player-mail bell. Does not smash commons.mno / weather / titan / dc / DISTRO.
# 9 rings = 9 inboxes (ZERO GROK KITE CAIRN SPALL GRAVE AXIOM SHARD SCREE).
# Magic TABLEML1. English lives in sibling TABLE\ files (SURFACE). This file latches the ding.
# HIS nring2 formula (imported). Dest FROM FILE. Fab, address, die.

import hashlib, json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_nring_pkg as nring

MAGIC = b"TABLEML1"
OUT = r"C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno"
N_IN = 9
RINGS = [
    ("ZERO", "inbox ding — both-sense gates ZERO inject slot"),
    ("GROK", "inbox ding — both-sense gates GROK inject slot"),
    ("KITE", "inbox ding — both-sense gates KITE inject slot"),
    ("CAIRN", "inbox ding — both-sense gates CAIRN inject slot"),
    ("SPALL", "inbox ding — both-sense gates SPALL inject slot"),
    ("GRAVE", "inbox ding — both-sense gates GRAVE inject slot"),
    ("AXIOM", "inbox ding — both-sense gates AXIOM inject slot"),
    ("SHARD", "inbox ding — both-sense gates SHARD inject slot"),
    ("SCREE", "inbox ding — both-sense gates SCREE inject slot"),
]


def ring_of(i):
    return i


def main():
    if os.path.isfile(OUT):
        print("REFUSE — %s exists. New dest only. Do not smash." % OUT)
        return 2
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    n_rings = len(RINGS)
    assert n_rings == N_IN == 9
    L = nring.layout(n_rings, N_IN)
    ring_recs = nring.emit_rings(L, n_rings)
    net = nring.emit_net(L, N_IN, n_rings, ring_of)
    assert nring.net_ops_ok(net), "XOR/OR leaked into net"
    assert nring.ring_ops_ok(ring_recs), "bad ring op"
    ok, w = nring.one_writer(ring_recs + list(net.gates))
    assert ok, "ONE-WRITER %r" % (w,)

    inj0 = [0] * N_IN
    field0 = [0] * N_IN
    body, n_gate, n_wire, depth, growth_base = nring.serialize(
        MAGIC, L, net, ring_recs, N_IN, n_rings, inj0, field0)
    h = nring.parse_hdr(body, MAGIC)
    assert h["n_in"] == N_IN and h["n_wire"] == n_wire
    assert body[:8] == MAGIC
    assert struct.unpack_from("<IIII", body, 8) == (N_IN, n_wire, n_gate, N_IN)
    assert len(body) >= nring.HDR
    assert nring.STRIDE == 25

    def expect_of(inj, fld, enables):
        return [inj[i] if enables[ring_of(i) % n_rings] else fld[i] for i in range(N_IN)]

    def run(inj, fld, enables):
        img = bytearray(body)
        hh = nring.parse_hdr(img, MAGIC)
        for i, v in enumerate(inj):
            img[hh["inj_base"] + i] = v & 1
        for i, v in enumerate(fld):
            img[hh["cell_base"] + i] = v & 1
        span = nring.CELLS + nring.CELLS + 2
        for ri, en in enumerate(enables):
            fwd = hh["ring0"] + ri * span
            img[fwd] = en & 1
            img[fwd + nring.CELLS] = en & 1
        nring.address_stored(img, MAGIC)
        return nring.field_from(img, nring.parse_hdr(img, MAGIC))

    on = [1] * n_rings
    off = [0] * n_rings
    inj1 = [i & 1 for i in range(N_IN)]
    fld1 = [1 - (i & 1) for i in range(N_IN)]
    cases = []
    g_on = run(inj1, fld1, on)
    cases.append(("fire_take_inject", g_on == expect_of(inj1, fld1, on)))
    g_off = run(inj1, fld1, off)
    cases.append(("dark_hold", g_off == expect_of(inj1, fld1, off)))
    mixed = [0] + [1] * (n_rings - 1)
    g_m = run(inj1, fld1, mixed)
    cases.append(("mixed_ring0_dark", g_m == expect_of(inj1, fld1, mixed)))
    img = bytearray(body)
    hh = nring.parse_hdr(img, MAGIC)
    img[hh["ring0"]] = 1
    img[hh["ring0"] + nring.CELLS] = 0
    nring.address_stored(img, MAGIC)
    dc_hold = nring.field_from(img, nring.parse_hdr(img, MAGIC)) == field0
    cases.append(("one_sense_DC", dc_hold))

    n2 = nring.emit_net(L, N_IN, n_rings, ring_of, ungated=True)
    b2, _, _, _, _ = nring.serialize(MAGIC, L, n2, ring_recs, N_IN, n_rings, inj0, field0)
    img2 = bytearray(b2)
    hh2 = nring.parse_hdr(img2, MAGIC)
    for i, v in enumerate(inj1):
        img2[hh2["inj_base"] + i] = v & 1
    for i, v in enumerate(fld1):
        img2[hh2["cell_base"] + i] = v & 1
    nring.address_stored(img2, MAGIC)
    ungated_caught = nring.field_from(img2, nring.parse_hdr(img2, MAGIC)) != expect_of(inj1, fld1, off)
    cases.append(("ungated_caught", ungated_caught))
    cases.append(("one_writer", ok))
    verified = all(c[1] for c in cases)
    if not verified:
        print("REFUSING", cases)
        return 1

    with open(OUT, "wb") as f:
        f.write(body)
    sha = hashlib.sha256(body).hexdigest()
    cpt = (float(n_gate) / depth) if depth else 0.0
    rec = {
        "action": "nring_fab", "kind": "table_mail", "path": OUT, "len": len(body),
        "sha256": sha, "n_gate": n_gate, "n_wire": n_wire, "depth": depth,
        "computations_per_tick": cpt, "magic": MAGIC.decode("ascii"),
        "n_in": N_IN, "n_rings": n_rings, "growth_base": growth_base,
        "rings": [{"name": n, "purpose": p, "fwd": nring.HDR + nring.ring_fwd(L, i),
                   "rev": nring.HDR + nring.ring_rev(L, i),
                   "carry": nring.HDR + nring.ring_carry(L, i),
                   "pub": nring.HDR + nring.ring_pub(L, i)} for i, (n, p) in enumerate(RINGS)],
        "cell_base": h["cell_base"], "inj_base": h["inj_base"],
        "clock": h["clock"], "ring0": h["ring0"],
        "cases": cases, "status": "WROTE",
        "note": "commons.mno untouched. English is TABLE\\ sibling files.",
    }
    with open(OUT + ".genome.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    with open(OUT + ".fab_report.json", "w") as f:
        json.dump(rec, f, indent=2)
    print("WROTE", OUT, len(body), "sha", sha)
    print("  magic", MAGIC, "n_in", N_IN, "n_wire", n_wire, "n_gate", n_gate, "n_out", N_IN)
    print("  depth", depth, "cpt", "%.3f" % cpt)
    print("  ring0", h["ring0"], "clock", h["clock"], "inj", h["inj_base"], "field", h["cell_base"])
    for i, (n, p) in enumerate(RINGS):
        print("  RING", n, "fwd", nring.HDR + nring.ring_fwd(L, i), p)
    print("  cases", cases)
    print("  commons.mno NOT TOUCHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
