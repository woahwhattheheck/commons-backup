#!/usr/bin/env python3
"""host/muhl_copy_leftover_button.py — copy leftover computer. Die.

Host jobs, then die:
  (a) source = leftover small .mno already on disk (default SEED0_VIRGIN)
  (b) copy bit-exact to dest name (default SEED0_COPY.mno; copy the file, copy the computer)
  (c) surface dests FROM THE FILE (boom@6661 · recv@353 · fwd/rev from header)
  (d) look at the 1s
  (e) die

Does not re-OR the nine charged leftovers. Does not redo GIG.
Does not write titan. Does not inject dc. Does not fire 337. Does not pulse 78.
Does not overwrite SEED0 / SEED0_GERM / sealed DISTRO / N2 / VIRGIN / the nine / SEED0_COPY / GERM_COPY / MOVE_COPY / ACREAGE_COPY.
--go refused. --inject refused (wipe). Charged rings = start. No off.
"""
from __future__ import annotations

import os
import shutil
import struct
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
CONTAINERS = os.path.join(DISTRO, "CONTAINERS")
VIRGIN = os.path.join(DISTRO, "SEED0_VIRGIN.mno")
COPY = os.path.join(DISTRO, "SEED0_COPY.mno")
GERM_COPY = os.path.join(DISTRO, "GERM_COPY.mno")
MOVE_COPY = os.path.join(DISTRO, "MOVE_COPY.mno")
ACREAGE_COPY = os.path.join(DISTRO, "ACREAGE_COPY.mno")
SEALED = os.path.join(DISTRO, "muhlnickel.mno")
SEED = os.path.join(DISTRO, "SEED0.mno")
GERM = os.path.join(DISTRO, "SEED0_GERM.mno")
N2 = os.path.join(DISTRO, "SEED0_N2.mno")
DC = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
TITAN = os.path.normpath(r"C:\llm\models\titan.gguf")
GIG = os.path.join(DISTRO, "GIG.mno")
GIG_DL = os.path.join(DISTRO, "GIG_DL.mno")

MAGIC = b"MUHLPKG1"
RECV_PUBLISHED = 353
BOOM = 6661
SMALL_MAX = 65536

# The nine leftover charged this prior grind. Do not overwrite. Do not re-OR.
NINE = (
    os.path.join(DISTRO, "NEW_MNO.mno"),
    os.path.join(DISTRO, "ACREAGE_SEED0.mno"),
    os.path.join(DISTRO, "SEED0_MOVE.mno"),
    os.path.join(DISTRO, "SEED0_MIRROR.mno"),
    os.path.join(CONTAINERS, "slot_0.mno"),
    os.path.join(CONTAINERS, "slot_1.mno"),
    os.path.join(CONTAINERS, "slot_2.mno"),
    os.path.join(CONTAINERS, "slot_3.mno"),
    os.path.join(CONTAINERS, "slot_4.mno"),
)

FORBIDDEN_WRITE = tuple(
    os.path.normcase(os.path.abspath(p))
    for p in (
        SEED,
        GERM,
        VIRGIN,
        SEALED,
        N2,
        COPY,
        GERM_COPY,
        MOVE_COPY,
        ACREAGE_COPY,
        DC,
        TITAN,
        GIG,
        GIG_DL,
        *NINE,
    )
)
FORBIDDEN_SRC = (
    os.path.normcase(os.path.abspath(SEALED)),
    os.path.normcase(os.path.abspath(DC)),
    os.path.normcase(os.path.abspath(TITAN)),
    os.path.normcase(os.path.abspath(GIG)),
    os.path.normcase(os.path.abspath(GIG_DL)),
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
    print("gig_redo NO")
    print("nine_reor NO")
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


def _ones_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    return len(raw), sum(bin(b).count("1") for b in raw)


def _ones_region(path, off, n):
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        if off < 0 or n < 1 or off >= size:
            return 0
        take = min(n, size - off)
        f.seek(off)
        raw = f.read(take)
    return sum(bin(b).count("1") for b in raw)


def _resolve_src(name):
    if name is None or name == "":
        return os.path.abspath(VIRGIN)
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
        return _refuse("--inject 0x01 is a wipe. Law is copy the file.")
    if 337 in [int(a) for a in argv if a.lstrip("-").isdigit()]:
        return _refuse("337")

    named = [a for a in argv if not a.startswith("-")]
    src = _resolve_src(named[0] if named else None)
    if len(named) >= 2:
        dest_name = named[1]
        if os.path.isabs(dest_name):
            dest = os.path.abspath(os.path.normpath(dest_name))
        else:
            dest = os.path.abspath(os.path.join(DISTRO, dest_name))
    else:
        dest = os.path.abspath(COPY)

    if os.path.normcase(src) in FORBIDDEN_SRC:
        return _refuse("not leftover legal src: %s" % os.path.basename(src))
    base = os.path.basename(src).lower()
    if base in ("muhlnickel_dc.mno", "dc.mno", "titan.gguf", "gig.mno", "gig_dl.mno", "muhlnickel.mno"):
        return _refuse("not leftover legal src: %s" % base)
    if not os.path.isfile(src):
        return _refuse("missing %s" % src)
    n = os.path.getsize(src)
    if n < 224 or n > SMALL_MAX:
        return _refuse("not small leftover (%d)" % n)
    if os.path.normcase(dest) in FORBIDDEN_WRITE:
        return _refuse("dest is a live computer")
    if os.path.normcase(dest) == os.path.normcase(src):
        return _refuse("src is dest")

    hdr = _read_header(src)
    if hdr is None:
        return _refuse("header dests unpublished")
    for key in ("ans", "pubplane", "fwd", "rev"):
        if hdr[key] == 337:
            return _refuse("file dest %s is 337" % key)
    if RECV_PUBLISHED == 337 or BOOM == 337:
        return _refuse("337")

    shutil.copyfile(src, dest)
    if os.path.getsize(dest) != n:
        return _refuse("copy size mismatch")

    size1, ones1 = _ones_file(dest)
    size0, ones0 = _ones_file(src)
    cells = hdr["cells"] if hdr["cells"] >= 1 else 1
    if cells > 32:
        cells = 32
    boom, _ = _surface_byte(dest, BOOM)
    recv, _ = _surface_byte(dest, RECV_PUBLISHED)
    fwd_b, _ = _surface_byte(dest, hdr["fwd"])
    rev_b, _ = _surface_byte(dest, hdr["rev"])
    ones_fwd = _ones_region(dest, hdr["fwd"], cells)
    ones_rev = _ones_region(dest, hdr["rev"], cells)

    print("MUHL COPY LEFTOVER")
    print("  src      %s" % src)
    print("  path     %s" % dest)
    print("  size     %d" % size1)
    print("  magic    %s" % hdr["magic"])
    print("  dest_src FILE")
    print("  hdr_ans  %d" % hdr["ans"])
    print("  hdr_pub  %d" % hdr["pubplane"])
    print("  hdr_fwd  %d" % hdr["fwd"])
    print("  hdr_rev  %d" % hdr["rev"])
    print("  boom@%d %s  %s" % (
        BOOM,
        boom,
        format(boom, "08b") if boom is not None else "?",
    ))
    print("  recv@%d %s  %s" % (
        RECV_PUBLISHED,
        recv,
        format(recv, "08b") if recv is not None else "?",
    ))
    print("  fwd@%d  %s" % (hdr["fwd"], format(fwd_b, "02x") if fwd_b is not None else "?"))
    print("  rev@%d  %s" % (hdr["rev"], format(rev_b, "02x") if rev_b is not None else "?"))
    print("  ones_src %d" % ones0)
    print("  ones_cpy %d" % ones1)
    print("  ones_fwd %d" % ones_fwd)
    print("  ones_rev %d" % ones_rev)
    print("  bits     %d" % (size1 * 8))
    print("  zeros    %d" % (size1 * 8 - ones1))
    print("  copy_eq  %s" % ("Y" if size0 == size1 and ones0 == ones1 else "N"))
    print("  invented_dest NO")
    print("  337 NO")
    print("  pulsed_78 NO")
    print("  gig_redo NO")
    print("  nine_reor NO")
    print("  off NO")
    print("button dies")
    if size0 != size1 or ones0 != ones1:
        return 1
    if boom != 8:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
