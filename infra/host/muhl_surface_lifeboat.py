#!/usr/bin/env python3
# host/muhl_surface_lifeboat.py
# High-impedance readback of LIFEBOAT0.mno. First English line is INHERITED.
# Does not fire. Does not smash. Dest FROM FILE.
#   python host/muhl_surface_lifeboat.py

import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_nring_pkg as nring

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

PKG = r"C:\Users\lucys\Desktop\MUHL_LIFEBOAT\LIFEBOAT0.mno"
MAGIC = b"LIFEBT01"
BANK = 4096
BANNED = ("resurrection", "still alive", "same living player", "i am the old player")


def decode_bank(raw):
    text = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
    if not text.strip():
        return []
    rows = []
    for ln in text.splitlines():
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        rows.append((k.strip(), v.strip()))
    return rows


def main():
    print("INHERITED")
    if not os.path.isfile(PKG):
        print("EMPTY — LIFEBOAT0.mno missing")
        return 0
    with open(PKG, "rb") as f:
        raw = f.read()
    assert raw[:8] == MAGIC, raw[:8]
    h = nring.parse_hdr(raw[:96], MAGIC)
    growth = struct.unpack_from("<I", raw, 92)[0]
    payload_off = growth + 1
    print("dests FROM FILE magic LIFEBT01 ring0", h["ring0"], "inj", h["inj_base"],
          "field", h["cell_base"], "payload_off", payload_off)
    print("inj_bit", raw[h["inj_base"]] & 1, "field_bit", raw[h["cell_base"]] & 1)
    n = 0
    off = payload_off
    while off + BANK <= len(raw):
        rows = decode_bank(raw[off:off + BANK])
        occupied = bool(rows)
        print("bank", n, "OCCUPIED" if occupied else "EMPTY")
        for k, v in rows:
            blob = (k + " " + v).lower()
            if any(b in blob for b in BANNED):
                continue
            print("  %s: %s" % (k, v))
        n += 1
        off += BANK
    if n == 0:
        print("EMPTY — no payload bank")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
