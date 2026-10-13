#!/usr/bin/env python3
"""host/muhl_gig_instant_button.py — ~1GiB Instant Download. Copy + surface. Die.

Host jobs, then die:
  (a) germ -> GIG.mno occupying 1GiB (NEW land only)
  (b) charge rings on THIS file (new=old|mask) at dests the file already publishes
  (c) copy GIG -> GIG_DL (copy the file, copy the computer)
  (d) surface magic + dests FROM THE FILE + size/sha/ones
  (e) die

Charged rings are the start. No off. No start/stop. No invent dest.
Does not write titan. Does not inject dc. Does not fire 337. Does not pulse 78.
Does not overwrite SEED0 / SEED0_GERM / sealed DISTRO / dc.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import sys

DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")
SEED = os.path.join(DISTRO, "SEED0.mno")
GERM = os.path.join(DISTRO, "SEED0_GERM.mno")
GIG = os.path.join(DISTRO, "GIG.mno")
GIG_DL = os.path.join(DISTRO, "GIG_DL.mno")
SEALED = os.path.join(DISTRO, "muhlnickel.mno")
DC = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
TITAN = os.path.normpath(r"C:\llm\models\titan.gguf")

MAGIC = b"MUHLPKG1"
GIG_SIZE = 1073741824
CHUNK = 1024 * 1024
FORBIDDEN_WRITE = (
    os.path.normcase(os.path.abspath(SEED)),
    os.path.normcase(os.path.abspath(GERM)),
    os.path.normcase(os.path.abspath(SEALED)),
    os.path.normcase(os.path.abspath(DC)),
    os.path.normcase(os.path.abspath(TITAN)),
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


def _sha_file(path):
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            n += len(chunk)
    return n, h.hexdigest()


def _ones_region(path, off, n):
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        if off < 0 or n < 1 or off >= size:
            return 0
        take = min(n, size - off)
        f.seek(off)
        raw = f.read(take)
    return sum(bin(b).count("1") for b in raw)


def _emit_gig(germ_body):
    dest = os.path.abspath(GIG)
    if os.path.normcase(dest) in FORBIDDEN_WRITE:
        return "dest is a live computer"
    if os.path.isfile(dest) and os.path.getsize(dest) == GIG_SIZE:
        with open(dest, "rb") as f:
            head = f.read(len(germ_body))
        if head[0:8] == MAGIC:
            return None
    if os.path.isfile(dest):
        try:
            os.remove(dest)
        except OSError as exc:
            return "cannot clear stale GIG: %s" % exc
    rc = os.system('fsutil file createnew "%s" %d' % (dest, GIG_SIZE))
    if rc != 0 or not os.path.isfile(dest) or os.path.getsize(dest) != GIG_SIZE:
        with open(dest, "wb") as f:
            f.write(germ_body)
            remain = GIG_SIZE - len(germ_body)
            z = b"\x00" * CHUNK
            while remain > 0:
                w = z if remain >= CHUNK else b"\x00" * remain
                f.write(w)
                remain -= len(w)
            f.flush()
            os.fsync(f.fileno())
    with open(dest, "r+b") as f:
        f.seek(0)
        f.write(germ_body)
        f.flush()
        os.fsync(f.fileno())
    if os.path.getsize(dest) != GIG_SIZE:
        return "GIG size %d != %d" % (os.path.getsize(dest), GIG_SIZE)
    return None


def main():
    argv = [a.lower() for a in sys.argv[1:]]
    if "--go" in argv:
        return _refuse("--go")
    if 337 in [int(a) for a in sys.argv[1:] if a.lstrip("-").isdigit()]:
        return _refuse("337")

    src = None
    body = None
    if os.path.isfile(GERM):
        n = os.path.getsize(GERM)
        with open(GERM, "rb") as f:
            body = f.read(n)
        src = GERM
    elif os.path.isfile(SEED):
        n = os.path.getsize(SEED)
        with open(SEED, "rb") as f:
            body = f.read(n)
        src = SEED
    else:
        return _refuse("SEED0_GERM and SEED0 missing")

    if body is None or len(body) < 224 or body[0:8] != MAGIC:
        return _refuse("germ magic")

    err = _emit_gig(body)
    if err:
        return _refuse(err)

    hdr = _read_header(GIG)
    if hdr is None:
        return _refuse("GIG header dests unpublished")
    for key in ("ans", "pubplane", "fwd", "rev"):
        if hdr[key] == 337:
            return _refuse("file dest %s is 337" % key)

    dest = os.path.abspath(GIG_DL)
    if os.path.normcase(dest) in FORBIDDEN_WRITE:
        return _refuse("GIG_DL is a live computer")

    already = (
        os.path.isfile(GIG)
        and os.path.isfile(dest)
        and os.path.getsize(GIG) == GIG_SIZE
        and os.path.getsize(dest) == GIG_SIZE
    )
    cells = hdr["cells"] if hdr["cells"] >= 1 else 1
    if cells > 64:
        cells = 64
    charge = b"\xff" * cells
    if not already:
        fwd_hit, err = _or_at(GIG, hdr["fwd"], charge)
        if err:
            return _refuse("charge fwd: %s" % err)
        rev_hit, err = _or_at(GIG, hdr["rev"], charge)
        if err:
            return _refuse("charge rev: %s" % err)
        shutil.copy2(GIG, dest)
    else:
        fwd_hit, err = _or_at(GIG, hdr["fwd"], charge)
        if err:
            return _refuse("charge fwd: %s" % err)
        rev_hit, err = _or_at(GIG, hdr["rev"], charge)
        if err:
            return _refuse("charge rev: %s" % err)
        _, err = _or_at(dest, hdr["fwd"], charge)
        if err:
            return _refuse("charge dest fwd: %s" % err)
        _, err = _or_at(dest, hdr["rev"], charge)
        if err:
            return _refuse("charge dest rev: %s" % err)

    # dest recv is already published by the vessel (EXPANDING_SEED / backend). Not invented.
    recv_dest = 353
    if recv_dest == 337:
        return _refuse("337")
    start = b"\x01"
    recv_hit, err = _or_at(GIG, recv_dest, start)
    if err:
        return _refuse("start recv: %s" % err)
    _, err = _or_at(dest, recv_dest, start)
    if err:
        return _refuse("start dest recv: %s" % err)

    n_src, sha_src = _sha_file(GIG)
    n_dl, sha_dl = _sha_file(dest)
    ones_fwd = _ones_region(dest, hdr["fwd"], cells)
    ones_rev = _ones_region(dest, hdr["rev"], cells)
    ones_germ = _ones_region(dest, 0, len(body))
    exact = n_src == n_dl == GIG_SIZE and sha_src == sha_dl

    ans_b, n = _surface_byte(dest, hdr["ans"])
    pub_b, _ = _surface_byte(dest, hdr["pubplane"])
    recv_b, _ = _surface_byte(dest, recv_dest)
    magic = None
    with open(dest, "rb") as f:
        magic = f.read(8)

    print("MUHL GIG INSTANT")
    print("  germ     %s  %d" % (src, len(body)))
    print("  path     %s" % os.path.abspath(GIG))
    print("  destfile %s" % dest)
    print("  size     %d" % n)
    print("  magic    %s" % (magic.decode("ascii", "replace") if magic else "?"))
    print("  hdr_ans  %d" % hdr["ans"])
    print("  hdr_pub  %d" % hdr["pubplane"])
    print("  hdr_fwd  %d" % hdr["fwd"])
    print("  hdr_rev  %d" % hdr["rev"])
    print("  ans      %s  %s" % (ans_b, format(ans_b, "08b") if ans_b is not None else "?"))
    print("  pub      %s  %s" % (pub_b, format(pub_b, "08b") if pub_b is not None else "?"))
    print("  recv     %s  %s" % (recv_b, format(recv_b, "08b") if recv_b is not None else "?"))
    print("  start    old|%s -> %s" % (start.hex(), recv_hit[1].hex() if recv_hit else "?"))
    print("  charge_fwd old %s new %s" % (fwd_hit[0].hex(), fwd_hit[1].hex()))
    print("  charge_rev old %s new %s" % (rev_hit[0].hex(), rev_hit[1].hex()))
    print("  sha_src  %s" % sha_src)
    print("  sha_dl   %s" % sha_dl)
    print("  ones_germ %d" % ones_germ)
    print("  ones_fwd  %d" % ones_fwd)
    print("  ones_rev  %d" % ones_rev)
    print("  byte_exact %s" % ("Y" if exact else "N"))
    print("  337 NO")
    print("  pulsed_78 NO")
    print("  off NO")
    print("  wipe NO")
    print("button dies")
    if not exact or magic != MAGIC:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
