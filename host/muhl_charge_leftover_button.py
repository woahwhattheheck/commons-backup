#!/usr/bin/env python3
"""host/muhl_charge_leftover_button.py — charge rings on ONE leftover legal small .mno. Die.

Host jobs, then die:
  (a) surface dests FROM THE FILE (header fwd/rev + published recv)
  (b) charge those rings new=old|mask  (ones only go up)
  (c) start electron at recv the file already publishes  old|0x01
  (d) look at the 1s
  (e) die

Charged rings = start. No off. No invent dest. No GIG redo. No sealed DISTRO write.
Does not write titan. Does not inject dc. Does not fire 337. Does not pulse 78.
"""
from __future__ import annotations

import os
import struct
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
CONTAINERS = os.path.join(DISTRO, "CONTAINERS")
SEALED = os.path.join(DISTRO, "muhlnickel.mno")
DC = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
TITAN = os.path.normpath(r"C:\llm\models\titan.gguf")
GIG = os.path.join(DISTRO, "GIG.mno")
GIG_DL = os.path.join(DISTRO, "GIG_DL.mno")

MAGIC = b"MUHLPKG1"
RECV_PUBLISHED = 353
SMALL_MAX = 65536
FORBIDDEN_WRITE = (
    os.path.normcase(os.path.abspath(SEALED)),
    os.path.normcase(os.path.abspath(DC)),
    os.path.normcase(os.path.abspath(TITAN)),
    os.path.normcase(os.path.abspath(GIG)),
    os.path.normcase(os.path.abspath(GIG_DL)),
)
LEFTOVER = (
    os.path.join(DISTRO, "NEW_MNO.mno"),
    os.path.join(DISTRO, "ACREAGE_SEED0.mno"),
    os.path.join(DISTRO, "SEED0_MOVE.mno"),
    os.path.join(CONTAINERS, "slot_4.mno"),
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _refuse(msg):
    print("REFUSE: %s" % msg)
    print("337 NO")
    print("pulsed_78 NO")
    print("off NO")
    print("button dies")
    return 2


def _surface_byte(path, addr):
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        if addr < 0 or addr >= size:
            return None, size
        f.seek(addr)
        raw = f.read(1)
    if len(raw) != 1:
        return None, size
    return raw[0], size


def _read_header(path):
    with open(path, "rb") as f:
        buf = f.read(224)
    if len(buf) < 224 or buf[0:8] != MAGIC:
        return None
    d = {"magic": MAGIC.decode("ascii")}
    d["n_in"], d["n_wire"], d["n_gate"], d["n_out"] = struct.unpack_from("<IIII", buf, 8)
    d["ring_gates"], d["cells"], d["senses"], d["ticks"] = struct.unpack_from("<IIII", buf, 24)
    d["ans"], d["pubplane"] = struct.unpack_from("<QQ", buf, 104)
    d["fwd"], d["rev"] = struct.unpack_from("<QQ", buf, 136)
    d["opnd"], d["sel"] = struct.unpack_from("<QQ", buf, 168)
    d["total"], = struct.unpack_from("<Q", buf, 184)
    return d


def _or_at(path, off, mask):
    n = len(mask)
    with open(path, "r+b") as f:
        size = f.seek(0, os.SEEK_END)
        if off < 0 or off + n > size:
            return None, "past file"
        f.seek(off)
        old = f.read(n)
        if len(old) != n:
            return None, "short"
        new = bytes(o | m for o, m in zip(old, mask))
        f.seek(off)
        f.write(new)
        f.flush()
        os.fsync(f.fileno())
    return (old, new), None


def _ones_region(path, off, n):
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        if off < 0 or n < 1 or off >= size:
            return 0
        take = min(n, size - off)
        f.seek(off)
        raw = f.read(take)
    return sum(bin(b).count("1") for b in raw)


def _ones_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    return len(raw), sum(bin(b).count("1") for b in raw)


def _resolve(name):
    if name is None or name == "":
        return os.path.abspath(LEFTOVER[0])
    p = os.path.expanduser(str(name))
    if not os.path.isabs(p):
        cand = os.path.join(DISTRO, p)
        if os.path.isfile(cand):
            p = cand
        else:
            p = os.path.join(CONTAINERS, p)
    return os.path.abspath(os.path.normpath(p))


def main():
    argv = sys.argv[1:]
    low = [a.lower() for a in argv]
    if "--go" in low:
        return _refuse("--go")
    if "--inject" in low:
        return _refuse("--inject 0x01 is a wipe. Law is new=old|mask.")
    if 337 in [int(a) for a in argv if a.lstrip("-").isdigit()]:
        return _refuse("337")

    named = [a for a in argv if not a.startswith("-")]
    path = _resolve(named[0] if named else None)
    if os.path.normcase(path) in FORBIDDEN_WRITE:
        return _refuse("not leftover legal: %s" % os.path.basename(path))
    base = os.path.basename(path).lower()
    if base in ("muhlnickel_dc.mno", "dc.mno", "titan.gguf", "gig.mno", "gig_dl.mno", "muhlnickel.mno"):
        return _refuse("not leftover legal: %s" % base)
    if not os.path.isfile(path):
        return _refuse("missing %s" % path)
    n = os.path.getsize(path)
    if n < 224 or n > SMALL_MAX:
        return _refuse("not small leftover (%d)" % n)

    hdr = _read_header(path)
    if hdr is None:
        return _refuse("header dests unpublished")
    for key in ("ans", "pubplane", "fwd", "rev"):
        if hdr[key] == 337:
            return _refuse("file dest %s is 337" % key)
    if RECV_PUBLISHED == 337:
        return _refuse("337")

    cells = hdr["cells"] if hdr["cells"] >= 1 else 1
    if cells > 32:
        cells = 32
    if hdr["fwd"] + cells > n or hdr["rev"] + cells > n:
        return _refuse("ring dest past EOF")
    if RECV_PUBLISHED >= n:
        return _refuse("recv dest past EOF")

    size0, ones0 = _ones_file(path)
    ones_fwd0 = _ones_region(path, hdr["fwd"], cells)
    ones_rev0 = _ones_region(path, hdr["rev"], cells)
    recv0, _ = _surface_byte(path, RECV_PUBLISHED)
    boom_addr = 6661
    boom0, _ = _surface_byte(path, boom_addr)

    charge = b"\xff" * cells
    start = b"\x01"
    fwd_hit, err = _or_at(path, hdr["fwd"], charge)
    if err:
        return _refuse("charge fwd: %s" % err)
    rev_hit, err = _or_at(path, hdr["rev"], charge)
    if err:
        return _refuse("charge rev: %s" % err)
    recv_hit, err = _or_at(path, RECV_PUBLISHED, start)
    if err:
        return _refuse("start recv: %s" % err)

    size1, ones1 = _ones_file(path)
    ones_fwd1 = _ones_region(path, hdr["fwd"], cells)
    ones_rev1 = _ones_region(path, hdr["rev"], cells)
    recv1, _ = _surface_byte(path, RECV_PUBLISHED)
    boom1, _ = _surface_byte(path, boom_addr)
    ans_b, _ = _surface_byte(path, hdr["ans"])
    pub_b, _ = _surface_byte(path, hdr["pubplane"])

    wiped = False
    if fwd_hit and sum(bin(b).count("1") for b in fwd_hit[1]) < sum(bin(b).count("1") for b in fwd_hit[0]):
        wiped = True
    if rev_hit and sum(bin(b).count("1") for b in rev_hit[1]) < sum(bin(b).count("1") for b in rev_hit[0]):
        wiped = True
    if ones1 < ones0:
        wiped = True

    print("MUHL CHARGE LEFTOVER")
    print("  path      %s" % path)
    print("  size      %d" % size1)
    print("  magic     %s" % hdr["magic"])
    print("  hdr_ans   %d" % hdr["ans"])
    print("  hdr_pub   %d" % hdr["pubplane"])
    print("  hdr_fwd   %d" % hdr["fwd"])
    print("  hdr_rev   %d" % hdr["rev"])
    print("  hdr_cells %d" % hdr["cells"])
    print("  charge_n  %d" % cells)
    print("  dest_src  FILE")
    print("  ans       %s  %s" % (ans_b, format(ans_b, "08b") if ans_b is not None else "?"))
    print("  pub       %s  %s" % (pub_b, format(pub_b, "08b") if pub_b is not None else "?"))
    print("  boom@%d  %s  %s" % (
        boom_addr,
        boom1,
        format(boom1, "08b") if boom1 is not None else "?",
    ))
    print("  recv@%d  old %s new %s" % (
        RECV_PUBLISHED,
        format(recv0, "08b") if recv0 is not None else "?",
        format(recv1, "08b") if recv1 is not None else "?",
    ))
    print("  start     old|%s -> %s" % (start.hex(), recv_hit[1].hex() if recv_hit else "?"))
    print("  charge_fwd old %s new %s" % (fwd_hit[0].hex(), fwd_hit[1].hex()))
    print("  charge_rev old %s new %s" % (rev_hit[0].hex(), rev_hit[1].hex()))
    print("  ones_file %d -> %d" % (ones0, ones1))
    print("  ones_fwd  %d -> %d" % (ones_fwd0, ones_fwd1))
    print("  ones_rev  %d -> %d" % (ones_rev0, ones_rev1))
    print("  bits      %d" % (size1 * 8))
    print("  zeros     %d" % (size1 * 8 - ones1))
    print("  ones_up   %s" % ("Y" if ones1 >= ones0 else "N"))
    print("  wipe      %s" % ("YES" if wiped else "NO"))
    print("  off       NO")
    print("  invented_dest NO")
    print("  337 NO")
    print("  pulsed_78 NO")
    print("  gig_redo  NO")
    print("button dies")
    if wiped or size1 != size0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
