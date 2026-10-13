#!/usr/bin/env python3
# host/muhl_fab_lifeboat.py
# NEW LAND LIFEBOAT0.mno only. Magic LIFEBT01. Refuse if exists.
# Does not smash commons.mno / table_mail.mno / ROOKERY0.mno / titan / dc.
# 1 ring, 1 inject bit. Payload bank after the nring image.
# Fab, address, die.

import hashlib, json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_nring_pkg as nring

MAGIC = b"LIFEBT01"
OUT = r"C:\Users\lucys\Desktop\MUHL_LIFEBOAT\LIFEBOAT0.mno"
BANK = 4096
N_IN = 1
RINGS = [("LIFEBOAT", "deposit enable — both-sense gates LIFEBOAT inject slot")]
PROTECTED = (
    r"C:\Users\lucys\Desktop\MUHL_COMMONS\commons.mno",
    r"C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno",
    r"C:\Users\lucys\Desktop\MUHLNICKEL_ROOKERY\ROOKERY0.mno",
)


def sha256_file(path):
    if not os.path.isfile(path):
        return "MISSING"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ring_of(_i):
    return 0


def main():
    if os.path.isfile(OUT):
        print("REFUSE — %s exists. New dest only. Do not smash." % OUT)
        return 2
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    before = {p: sha256_file(p) for p in PROTECTED}

    L = nring.layout(1, N_IN)
    ring_recs = nring.emit_rings(L, 1)
    net = nring.emit_net(L, N_IN, 1, ring_of)
    assert nring.net_ops_ok(net), "XOR/OR leaked into net"
    assert nring.ring_ops_ok(ring_recs), "bad ring op"
    ok, w = nring.one_writer(ring_recs + list(net.gates))
    assert ok, "ONE-WRITER %r" % (w,)

    inj0 = [0]
    field0 = [0]
    body, n_gate, n_wire, depth, growth_base = nring.serialize(
        MAGIC, L, net, ring_recs, N_IN, 1, inj0, field0)
    h = nring.parse_hdr(body, MAGIC)
    assert h["n_in"] == 1 and body[:8] == MAGIC
    assert struct.unpack_from("<IIII", body, 8) == (1, n_wire, n_gate, 1)
    payload_off = growth_base + 1
    assert len(body) == payload_off
    blob = body + (b"\x00" * BANK)

    def expect_of(inj, fld, enables):
        return [inj[0] if enables[0] else fld[0]]

    def run(inj, fld, enables):
        img = bytearray(body)
        hh = nring.parse_hdr(img, MAGIC)
        img[hh["inj_base"]] = inj[0] & 1
        img[hh["cell_base"]] = fld[0] & 1
        span = nring.CELLS + nring.CELLS + 2
        fwd = hh["ring0"]
        img[fwd] = enables[0] & 1
        img[fwd + nring.CELLS] = enables[0] & 1
        nring.address_stored(img, MAGIC)
        return nring.field_from(img, nring.parse_hdr(img, MAGIC))

    cases = []
    cases.append(("fire_take_inject", run([1], [0], [1]) == [1]))
    cases.append(("dark_hold", run([1], [0], [0]) == [0]))
    img = bytearray(body)
    hh = nring.parse_hdr(img, MAGIC)
    img[hh["ring0"]] = 1
    img[hh["ring0"] + nring.CELLS] = 0
    nring.address_stored(img, MAGIC)
    cases.append(("one_sense_DC", nring.field_from(img, nring.parse_hdr(img, MAGIC)) == [0]))
    cases.append(("one_writer", ok))
    if not all(c[1] for c in cases):
        print("REFUSING", cases)
        return 1

    with open(OUT, "wb") as f:
        f.write(blob)
    sha = hashlib.sha256(blob).hexdigest()
    after = {p: sha256_file(p) for p in PROTECTED}
    for p in PROTECTED:
        if before[p] != after[p]:
            print("REFUSE — protected hash moved", p)
            return 1
    rec = {
        "action": "nring_fab", "kind": "lifeboat0", "path": OUT, "len": len(blob),
        "sha256": sha, "n_gate": n_gate, "n_wire": n_wire, "depth": depth,
        "magic": MAGIC.decode("ascii"), "n_in": 1, "n_rings": 1,
        "growth_base": growth_base, "payload_off": payload_off, "bank": BANK,
        "cell_base": h["cell_base"], "inj_base": h["inj_base"],
        "clock": h["clock"], "ring0": h["ring0"],
        "cases": cases, "status": "WROTE",
        "protected": after,
        "note": "commons/table_mail/ROOKERY0 untouched. Payload bank empty.",
    }
    with open(OUT + ".genome.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    with open(OUT + ".fab_report.json", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    print("WROTE", OUT, len(blob), "sha", sha)
    print("  magic LIFEBT01 n_in 1 n_wire", n_wire, "n_gate", n_gate, "depth", depth)
    print("  dests FROM FILE ring0", h["ring0"], "clock", h["clock"],
          "inj", h["inj_base"], "field", h["cell_base"], "payload_off", payload_off)
    print("  RING LIFEBOAT fwd", nring.HDR + nring.ring_fwd(L, 0))
    print("  cases", cases)
    print("  protected UNTOUCHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
