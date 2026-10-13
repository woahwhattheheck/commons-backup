#!/usr/bin/env python3
"""host/muhl_dc_button_add.py — MUHL datacenter routing button (additive).

Host jobs, then die:
  (a) inject BOTH senses into the named DC package (fwd + rev; one sense alone is DC)
  (b) surface the answer (bounded read)
  (c) die

Circuits live in .gguf AND .mno. This button talks to the named DC package only.
It never writes titan. It never autofabs. It never evaluates a gate.

Target (fixed):
  C:/Users/lucys/Desktop/MUHL_DATACENTER/muhlnickel_dc.mno

Sibling named, never titan:
  C:/Users/lucys/Desktop/MUHL_DATACENTER/muhlnickel_dc.gguf

If the .mno is missing, unreadable, unknown MAGIC, or senses != 2 → NEED_BRYCE.
The button still exists. It fails closed. It does not invent a package.

Pattern: DISTRO / LOOM run_muhlnickel.py (MUHLPKG1 / LOOMPKG1 header).
Default dry: print the plan. Write nothing.
--go is Bryce: inject both senses, surface, die.

  python host/muhl_dc_button_add.py
  python host/muhl_dc_button_add.py --dry
  python host/muhl_dc_button_add.py --go A B
"""
from __future__ import annotations

import os
import struct
import sys

DC_DIR = os.path.normpath("C:/Users/lucys/Desktop/MUHL_DATACENTER")
PKG = os.path.join(DC_DIR, "muhlnickel_dc.mno")
GGUF_SIBLING = os.path.join(DC_DIR, "muhlnickel_dc.gguf")
KNOWN_MAGIC = (b"MUHLPKG1", b"LOOMPKG1")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: NEED_BRYCE — %s" % msg)
    return 1


def _need_bryce(reasons):
    print("  NEED_BRYCE (named; this button still does not fire):")
    for reason in reasons:
        print("    - %s" % reason)
    print()


def load_header(buf, size=None):
    """DISTRO / LOOM header. Fail closed on unknown MAGIC or senses != 2."""
    if len(buf) < 224:
        return None, "package shorter than header (need 224, got %d)" % len(buf)
    magic = buf[0:8]
    if magic not in KNOWN_MAGIC:
        return None, "unknown MAGIC %r (need MUHLPKG1 or LOOMPKG1; do not invent)" % magic
    d = {"magic": magic.decode("ascii", "replace")}
    d["n_in"], d["n_wire"], d["n_gate"], d["n_out"] = struct.unpack_from("<IIII", buf, 8)
    d["ring_gates"], d["cells"], d["senses"], d["ticks"] = struct.unpack_from("<IIII", buf, 24)
    d["ans"], d["pubplane"] = struct.unpack_from("<QQ", buf, 104)
    d["lanes"], _ = struct.unpack_from("<QQ", buf, 120)
    d["fwd"], d["rev"] = struct.unpack_from("<QQ", buf, 136)
    d["opnd"], d["sel"] = struct.unpack_from("<QQ", buf, 168)
    d["total"], = struct.unpack_from("<Q", buf, 184)
    total_size = int(size) if size is not None else len(buf)
    if d["total"] != total_size:
        return None, "container length %d != header total %d" % (total_size, d["total"])
    if d["senses"] != 2:
        return None, "senses=%r (need 2; both-sense ring law)" % d["senses"]
    if d["cells"] < 16:
        return None, "cells=%r (need >= 16 for 8+8 operand bits)" % d["cells"]
    for key in ("fwd", "rev", "opnd", "sel", "ans", "pubplane"):
        if d[key] + 1 > total_size:
            return None, "%s offset %d past package size %d" % (key, d[key], total_size)
    return d, None


def inspect():
    """Dry-safe inspect. Never writes. Header 224 B only. Missing .mno is NEED_BRYCE."""
    need = []
    hdr = None
    size = None
    if not os.path.isfile(PKG):
        need.append("package missing: %s" % PKG)
        return {
            "pkg_exists": False,
            "gguf_exists": os.path.isfile(GGUF_SIBLING),
            "size": None,
            "hdr": None,
            "need_bryce": need,
        }
    try:
        size = os.path.getsize(PKG)
        with open(PKG, "rb") as f:
            buf = f.read(224)
    except OSError as exc:
        need.append("package unreadable: %s" % exc)
        return {
            "pkg_exists": True,
            "gguf_exists": os.path.isfile(GGUF_SIBLING),
            "size": size,
            "hdr": None,
            "need_bryce": need,
        }
    hdr, err = load_header(buf, size=size)
    if err:
        need.append(err)
    return {
        "pkg_exists": True,
        "gguf_exists": os.path.isfile(GGUF_SIBLING),
        "size": size,
        "hdr": hdr,
        "need_bryce": need,
    }


def print_plan(info, dry=True):
    mode = "DRY — plan only, no write, no inject"
    if not dry:
        mode = "GO — Bryce; inject both senses, surface, die"
    print("\nMUHL DC BUTTON (additive — DISTRO/LOOM reader, named DC package)")
    print("  mode:     %s" % mode)
    print("  package:  %s" % PKG)
    print("  sibling:  %s" % GGUF_SIBLING)
    print("  titan:    never (this button does not open titan.gguf)")
    print("  autofab:  never")
    print("  law:      circuits live in .gguf AND .mno; host injects both senses and surfaces")
    print("  law:      one sense alone is DC; both senses required")
    print("  refuse:   titan write · autofab · gate eval · numpy · invented MAGIC / offsets")
    print()
    if info["pkg_exists"]:
        print("  package   present (%s bytes)" % info["size"])
    else:
        print("  package   MISSING")
    if info["gguf_exists"]:
        print("  sibling   present (named .gguf in DC dir; this button does not write it)")
    else:
        print("  sibling   absent (named .gguf; not titan)")
    print()
    hdr = info["hdr"]
    if hdr is not None:
        print("  HEADER (DISTRO/LOOM layout)")
        print("    MAGIC      %s" % hdr["magic"])
        print("    netlist    gates=%d  n_in=%d  n_out=%d  n_wire=%d"
              % (hdr["n_gate"], hdr["n_in"], hdr["n_out"], hdr["n_wire"]))
        print("    ring       gates=%d  cells=%d  senses=%d  ticks=%d"
              % (hdr["ring_gates"], hdr["cells"], hdr["senses"], hdr["ticks"]))
        print("    lanes      %d" % hdr["lanes"])
        print()
        print("  INJECT (both senses — pattern: run_muhlnickel.py shoot)")
        print("    fwd   %d" % hdr["fwd"])
        print("    rev   %d" % hdr["rev"])
        print("    opnd  %d" % hdr["opnd"])
        print("    sel   %d" % hdr["sel"])
        print("    drive %d cells; operand bits a[8]+b[8] then 0x01 fill" % hdr["cells"])
        print()
        print("  SURFACE (bounded read — pattern: run_muhlnickel.py surface)")
        print("    ans      %d + select" % hdr["ans"])
        print("    pubplane %d + select" % hdr["pubplane"])
        print()
    if info["need_bryce"]:
        _need_bryce(info["need_bryce"])
    if dry:
        print("  (no write performed; --go is Bryce)")
        print()
    return 0 if not info["need_bryce"] else 1


def shoot(hdr, a, b):
    """(a) SHOOT THE ELECTRON. Bounded writes, both senses. Nothing is evaluated."""
    bits = bytes(((a >> i) & 1) for i in range(8)) + bytes(((b >> i) & 1) for i in range(8))
    drive = b"\x01" * (hdr["cells"] - len(bits))
    with open(PKG, "r+b") as f:
        f.seek(hdr["fwd"])
        f.write(bits + drive)
        f.seek(hdr["rev"])
        f.write(bits + drive)
        f.seek(hdr["opnd"])
        f.write(bits)
        f.seek(hdr["sel"])
        f.write(bytes([a, b]))
        f.flush()
        os.fsync(f.fileno())


def surface(hdr):
    """(b) SURFACE THE OUTPUT. Bounded reads. The machine's answer is resident."""
    with open(PKG, "rb") as f:
        f.seek(hdr["sel"])
        sel = f.read(2)
        if len(sel) != 2:
            return None, None, "short read sel"
        at = int.from_bytes(sel, "little")
        f.seek(hdr["ans"] + at)
        ans = f.read(1)
        f.seek(hdr["pubplane"] + at)
        pub = f.read(1)
    if len(ans) != 1 or len(pub) != 1:
        return None, None, "short read ans/pub"
    return ans[0], pub[0], None


def parse_operand(raw, name):
    try:
        val = int(raw, 0)
    except (TypeError, ValueError):
        return None, "%s is not an int: %r" % (name, raw)
    if val < 0 or val > 255:
        return None, "%s=%r out of 0-255" % (name, val)
    return val, None


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if a and a[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    do_go = "--go" in a
    info = inspect()

    if not do_go:
        return print_plan(info, dry=True)

    print_plan(info, dry=False)
    if info["need_bryce"] or info["hdr"] is None:
        print("GO REFUSED: NEED_BRYCE — do not inject.\n")
        return 1

    rest = [x for x in a if x != "--go"]
    if len(rest) != 2:
        return _fail("--go needs A B (0-255); pattern DISTRO/LOOM shot")
    op_a, err = parse_operand(rest[0], "A")
    if err:
        return _fail(err)
    op_b, err = parse_operand(rest[1], "B")
    if err:
        return _fail(err)

    shoot(info["hdr"], op_a, op_b)
    ans, pub, err = surface(info["hdr"])
    if err:
        return _fail(err)
    print("  SHOT     A=%d  B=%d" % (op_a, op_b))
    print("  SURFACE  ans=%d  published=%d" % (ans, pub))
    print("  (button dies)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
