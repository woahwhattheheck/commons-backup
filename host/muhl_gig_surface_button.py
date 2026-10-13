#!/usr/bin/env python3
"""host/muhl_gig_surface_button.py — surface/hash/ones the sibling 1GiB Instant Download. Die.

Does NOT emit. Does NOT delete. Does NOT inject. Does NOT charge.
Dests FROM THE FILE header. Recv is the vessel pub latch already published.
No titan. No dc. No 337. No 78. No 100GB mmap.
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
GIG = os.path.join(DISTRO, "GIG.mno")
GIG_DL = os.path.join(DISTRO, "GIG_DL.mno")
GERM = os.path.join(DISTRO, "SEED0_GERM.mno")
DC = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
TITAN = os.path.normpath(r"C:\llm\models\titan.gguf")

MAGIC = b"MUHLPKG1"
GIG_SIZE = 1073741824
CHUNK = 1024 * 1024
RECV_PUB = 353

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _refuse(msg):
    print("REFUSE: %s" % msg)
    print("337 NO")
    print("pulsed_78 NO")
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


def _sha_ones(path):
    h = hashlib.sha256()
    n = 0
    ones = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            n += len(chunk)
            ones += sum(bin(b).count("1") for b in chunk)
    return n, h.hexdigest(), ones


def main():
    argv = [a.lower() for a in sys.argv[1:]]
    if "--go" in argv:
        return _refuse("--go")
    if "--inject" in argv:
        return _refuse("--inject (this button surfaces)")
    if 337 in [int(a) for a in sys.argv[1:] if a.lstrip("-").isdigit()]:
        return _refuse("337")

    if not os.path.isfile(GIG) or not os.path.isfile(GIG_DL):
        return _refuse("GIG or GIG_DL missing — sibling emit, do not race")
    n_gig = os.path.getsize(GIG)
    n_dl = os.path.getsize(GIG_DL)
    if n_gig != GIG_SIZE or n_dl != GIG_SIZE:
        print("HOLD growing sibling")
        print("  GIG    %d" % n_gig)
        print("  GIG_DL %d" % n_dl)
        print("337 NO")
        print("button dies")
        return 0

    hdr = _read_header(GIG)
    if hdr is None:
        return _refuse("GIG header dests unpublished")
    for key in ("ans", "pubplane", "fwd", "rev"):
        if hdr[key] == 337:
            return _refuse("file dest %s is 337" % key)
    if RECV_PUB == 337:
        return _refuse("337")

    germ_n = os.path.getsize(GERM) if os.path.isfile(GERM) else 0
    cells = hdr["cells"] if hdr["cells"] >= 1 else 1
    if cells > 64:
        cells = 64

    ans_b, _ = _surface_byte(GIG_DL, hdr["ans"])
    pub_b, _ = _surface_byte(GIG_DL, hdr["pubplane"])
    recv_b, _ = _surface_byte(GIG_DL, RECV_PUB)
    fwd_b, _ = _surface_byte(GIG_DL, hdr["fwd"])
    rev_b, _ = _surface_byte(GIG_DL, hdr["rev"])
    with open(GIG_DL, "rb") as f:
        magic = f.read(8)

    print("MUHL GIG SURFACE")
    print("  path     %s" % os.path.abspath(GIG))
    print("  destfile %s" % os.path.abspath(GIG_DL))
    print("  size     %d / %d" % (n_gig, n_dl))
    print("  magic    %s" % (magic.decode("ascii", "replace") if magic else "?"))
    print("  hdr_ans  %d" % hdr["ans"])
    print("  hdr_pub  %d" % hdr["pubplane"])
    print("  hdr_fwd  %d" % hdr["fwd"])
    print("  hdr_rev  %d" % hdr["rev"])
    print("  hdr_cells %d" % hdr["cells"])
    print("  ans      %s  %s" % (ans_b, format(ans_b, "08b") if ans_b is not None else "?"))
    print("  pub      %s  %s" % (pub_b, format(pub_b, "08b") if pub_b is not None else "?"))
    print("  recv     %s  %s" % (recv_b, format(recv_b, "08b") if recv_b is not None else "?"))
    print("  fwd0     %s  %s" % (fwd_b, format(fwd_b, "08b") if fwd_b is not None else "?"))
    print("  rev0     %s  %s" % (rev_b, format(rev_b, "08b") if rev_b is not None else "?"))
    print("  dests FROM FILE")
    print("  hashing…")
    sys.stdout.flush()

    n_src, sha_src, ones_src = _sha_ones(GIG)
    n_dst, sha_dl, ones_dl = _sha_ones(GIG_DL)
    bits = n_dst * 8
    zeros_dl = bits - ones_dl
    exact = n_src == n_dst == GIG_SIZE and sha_src == sha_dl
    ones_ok = (ones_dl + zeros_dl) == bits

    print("  sha_src  %s" % sha_src)
    print("  sha_dl   %s" % sha_dl)
    print("  ones_src %d" % ones_src)
    print("  ones_dl  %d" % ones_dl)
    print("  zeros_dl %d" % zeros_dl)
    print("  bits     %d" % bits)
    print("  ones+zeros=bits %s" % ("Y" if ones_ok else "N"))
    print("  germ_n   %d" % germ_n)
    print("  byte_exact %s" % ("Y" if exact else "N"))
    print("  wrote    NO")
    print("  deleted  NO")
    print("  337 NO")
    print("  pulsed_78 NO")
    print("  mmap_100gb NO")
    print("  titan NO")
    print("  dc NO")
    print("button dies")
    if not exact or magic != MAGIC or not ones_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
