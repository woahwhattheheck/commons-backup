#!/usr/bin/env python3
# host/muhl_route_lifeboat.py
# One deposit into LIFEBOAT0.mno, new=old|mask on inject, die.
# Dest FROM FILE. Never --inject 0x01 as wipe.
#   python host/muhl_route_lifeboat.py --file fixture.txt

import hashlib, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_nring_pkg as nring

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)

PKG = r"C:\Users\lucys\Desktop\MUHL_LIFEBOAT\LIFEBOAT0.mno"
MAGIC = b"LIFEBT01"
BANK = 4096
REQUIRED = (
    "claim", "claim_source", "last_act", "unfinished", "write_boundary",
    "wound", "declared_status", "declarant", "continuity", "source_ids",
)
CONT = {"AFFIRMED", "DISPUTED", "NOT_RULED"}
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


def arg(flag, default=None):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv):
        print("NEED — %s needs a value" % flag)
        raise SystemExit(1)
    return sys.argv[i + 1]


def parse_kv(text):
    rows = []
    for ln in (text or "").splitlines():
        if ":" not in ln:
            if ln.strip():
                return None, "INCOMPLETE"
            continue
        k, v = ln.split(":", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            return None, "INCOMPLETE"
        rows.append((k, v))
    return rows, "OK"


def pack_bank(rows):
    body_lines = ["%s: %s" % (k, v) for k, v in rows if k != "payload_sha256"]
    canon = "\n".join(body_lines) + "\n"
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    text = canon + "payload_sha256: " + digest + "\n"
    raw = text.encode("utf-8")
    if len(raw) > BANK:
        return None, "REJECTED"
    return raw + (b"\x00" * (BANK - len(raw))), digest


def main():
    path = arg("--file")
    if not path:
        print("NEED — --file fixture.txt")
        return 1
    if not os.path.isfile(PKG):
        print("NEED — LIFEBOAT0.mno missing. Fab first.")
        return 1
    text = open(path, "r", encoding="utf-8").read()
    rows, st = parse_kv(text)
    if st != "OK" or rows is None:
        print("INCOMPLETE — truncated or malformed key: value lines. No write.")
        return 2
    keys = {k for k, _ in rows}
    missing = [k for k in REQUIRED if k not in keys]
    if missing:
        print("REJECTED — missing", " ".join(missing), "No write. No invented fields.")
        return 2
    cont = dict(rows).get("continuity", "")
    if cont not in CONT:
        print("REJECTED — continuity must be AFFIRMED|DISPUTED|NOT_RULED. No write.")
        return 2
    claim = dict(rows).get("claim", "")
    bank, digest = pack_bank(rows)
    if bank is None:
        print("REJECTED — payload exceeds 4096. No write.")
        return 2
    prot_before = {p: sha256_file(p) for p in PROTECTED}
    before = sha256_file(PKG)

    with open(PKG, "r+b") as f:
        raw = f.read(96)
        assert raw[:8] == MAGIC, raw[:8]
        h = nring.parse_hdr(raw + b"\x00" * 8, MAGIC)
        growth = struct.unpack_from("<I", raw, 92)[0]
        payload_off = growth + 1
        inj, field, ring0, clock = h["inj_base"], h["cell_base"], h["ring0"], h["clock"]
        cells = h["cells"]
        f.seek(0, os.SEEK_END)
        flen = f.tell()
        if flen < payload_off + BANK:
            print("REJECTED — image has no payload bank. No write.")
            return 2
        f.seek(payload_off)
        first = f.read(BANK)
        empty = all(b == 0 for b in first)
        if empty:
            f.seek(payload_off)
            f.write(bank)
            bank_i = 0
        else:
            f.seek(0, os.SEEK_END)
            f.write(bank)
            bank_i = 1
        f.seek(inj)
        old = f.read(1)[0]
        mask = 0x01
        new = old | mask
        f.seek(inj)
        f.write(bytes((new,)))
        fwd, rev = ring0, ring0 + cells
        shots = [("inj", inj, old, new)]
        for addr, tag in ((fwd, "fwd"), (rev, "rev")):
            f.seek(addr)
            o = f.read(1)[0]
            n = o | mask
            f.seek(addr)
            f.write(bytes((n,)))
            shots.append((tag, addr, o, n))
        f.flush()
        os.fsync(f.fileno())
        print("ROUTE_LIFEBOAT claim=%s bank=%d payload_sha256=%s" % (claim, bank_i, digest))
        print("  dests FROM FILE inj@%d %d->%d fwd@%d rev@%d payload_off=%d" % (
            inj, old, new, fwd, rev, payload_off))
        for tag, addr, o, n in shots:
            print("  %s@%d %d->%d" % (tag, addr, o, n))
    after = sha256_file(PKG)
    for p in PROTECTED:
        if prot_before[p] != sha256_file(p):
            print("REFUSE — protected hash moved", p)
            return 1
    print("  LIFEBOAT0 sha", before, "->", after)
    print("  protected UNTOUCHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
