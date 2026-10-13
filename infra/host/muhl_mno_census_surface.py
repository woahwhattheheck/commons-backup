#!/usr/bin/env python3
"""host/muhl_mno_census_surface.py — sequential bounded header+dest surface. Die.

Look at every reachable .mno. Listing is not looking.
Seek+read <=224 B header (pfc_inspect CAP class). Dest FROM FILE.
No inject. No re-OR. No 337 fire. No titan. No 10-wide. No 100GB mmap.
GIG/dc: header+published mouths only. No whole-file hash.

  python host/muhl_mno_census_surface.py
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.normpath(r"C:\Users\lucys\Desktop")
REPO = os.path.normpath(r"C:\Users\lucys\Desktop\LocalDeviceAgent")
LLM = os.path.normpath(r"C:\llm")
OUT = os.path.join(DESK, "MUHL_GO", "MNO_CENSUS_SURFACE.txt")

ROOTS = (DESK, REPO, LLM)
SKIP_DIR = {".git", "node_modules", "__pycache__", ".cursor"}
DC_NAMES = {"muhlnickel_dc.mno", "dc.mno"}
GIG_NAMES = {"gig.mno", "gig_dl.mno"}
SHA_MAX = 8 * 1024 * 1024
HDR_N = 224
MAGIC_MUHL = b"MUHLPKG1"
MAGIC_WEATHER = b"WEATHER1"
MAGIC_LOOM = b"LOOMPKG1"
RECV_NAMED = 353

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _refuse_go(argv):
    low = [a.lower() for a in argv]
    if "--go" in low or "--inject" in low:
        print("REFUSE: this button surfaces")
        return True
    return False


def _walk_mno(root):
    found = []
    if not os.path.isdir(root):
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
        for name in filenames:
            if name.lower().endswith(".mno"):
                found.append(os.path.normpath(os.path.join(dirpath, name)))
    return found


def _ones(b):
    return sum(bin(x).count("1") for x in b)


def _bits8(x):
    return format(x, "08b")


def _read_at(f, addr, n, size):
    if addr < 0 or addr >= size:
        return None
    take = n if addr + n <= size else size - addr
    f.seek(addr)
    raw = f.read(take)
    return raw


def _sha_cheap(path, size):
    if size > SHA_MAX:
        return "SKIP_SIZE"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _surface_mouth(f, name, addr, size, lines):
    if addr == 337:
        lines.append("  %s @%d SKIP 337 not fired" % (name, addr))
        return
    raw = _read_at(f, addr, 1, size)
    if raw is None:
        lines.append("  %s @%d PAST_EOF size=%d" % (name, addr, size))
        return
    if len(raw) != 1:
        lines.append("  %s @%d SHORT" % (name, addr))
        return
    b = raw[0]
    lines.append("  %s @%d byte=%d bits=%s" % (name, addr, b, _bits8(b)))


def _parse_header(buf, size, lines, f):
    magic = buf[:8]
    lines.append("  magic %r" % magic)
    lines.append("  hdr_ones %d / %d" % (_ones(buf), len(buf) * 8))
    if len(buf) >= 24:
        n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", buf, 8)
        lines.append("  +8_IIII n_in=%d n_wire=%d n_gate=%d n_out=%d" % (n_in, n_wire, n_gate, n_out))
    depth = None
    n_gate = None
    n_in = n_wire = n_out = None
    if len(buf) >= 24:
        n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", buf, 8)
    if magic == MAGIC_WEATHER and len(buf) >= 28:
        g2, w2, i2, o2, d2 = struct.unpack_from("<IIIII", buf, 8)
        lines.append("  +8_IIIII_cairn n_gate=%d n_wire=%d n_in=%d n_out=%d depth=%d" % (g2, w2, i2, o2, d2))
        # HIS order on v2: n_in,n_wire,n_gate,n_out at +8. depth may follow or sit later.
        if n_in == 2048 and n_gate and n_gate > 1000:
            depth = d2 if d2 and d2 < 10000 else None
            if depth is None and len(buf) >= 32:
                maybe = struct.unpack_from("<I", buf, 24)[0]
                lines.append("  +24_I %d" % maybe)
                if 1 <= maybe <= 4096:
                    depth = maybe
        elif g2 and g2 > 1000 and d2 and d2 < 10000:
            # v1 cairn pack: treat depth from cairn, n_gate from cairn slot
            n_gate = g2
            n_in, n_wire, n_out = i2, w2, o2
            depth = d2
            lines.append("  ASSISTANT: v1 cairn slots used for n_gate/DEPTH (HIS v2 order would mis-name)")
    if magic in (MAGIC_MUHL, MAGIC_LOOM) and len(buf) >= 192:
        ans, pubplane = struct.unpack_from("<QQ", buf, 104)
        fwd, rev = struct.unpack_from("<QQ", buf, 136)
        opnd, sel = struct.unpack_from("<QQ", buf, 168)
        total = struct.unpack_from("<Q", buf, 184)[0] if len(buf) >= 192 else 0
        lines.append("  hdr_ans %d" % ans)
        lines.append("  hdr_pubplane %d" % pubplane)
        lines.append("  hdr_fwd %d" % fwd)
        lines.append("  hdr_rev %d" % rev)
        lines.append("  hdr_opnd %d" % opnd)
        lines.append("  hdr_sel %d" % sel)
        lines.append("  hdr_total %d" % total)
        mouths = [
            ("hdr_ans", ans),
            ("hdr_pubplane", pubplane),
            ("hdr_fwd", fwd),
            ("hdr_rev", rev),
            ("hdr_opnd", opnd),
            ("hdr_sel", sel),
        ]
        if ans != 337 and 0 <= ans < size:
            boom = ans + 1283
            if boom != 337:
                mouths.append(("boom_ans+1283", boom))
        mouths.append(("recv_named", RECV_NAMED))
        # SEED0 rings published on cards FROM FILE
        if size >= 321:
            mouths.append(("ring_fwd@288", 288))
            mouths.append(("ring_rev@320", 320))
        for name, addr in mouths:
            _surface_mouth(f, name, addr, size, lines)
    if magic == MAGIC_WEATHER and len(buf) >= 96:
        # published mouths from WEATHER_DISK_TRUTH / leftover button — FROM FILE
        if len(buf) >= 48:
            extra = struct.unpack_from("<IIII", buf, 28)
            lines.append("  +28_IIII %s" % (extra,))
        if len(buf) >= 60:
            q0, q1 = struct.unpack_from("<QQ", buf, 44)
            lines.append("  +44_QQ %d %d" % (q0, q1))
        # v2 named: n_rings/cells/ring0/clock often in header after counts
        if len(buf) >= 80:
            rest = struct.unpack_from("<IIII", buf, 64)
            lines.append("  +64_IIII %s" % (rest,))
        # surface cell/ring mouths only if header published them as small addrs
        for name, addr in (("weather_ring0_104", 104), ("weather_clock_98", 98),
                           ("weather_fwd0_104", 104), ("weather_carry_168", 168),
                           ("weather_pub_169", 169)):
            if addr < size:
                _surface_mouth(f, name, addr, size, lines)
    return n_in, n_wire, n_gate, n_out, depth


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if _refuse_go(argv):
        print("button dies")
        return 2

    paths = []
    for root in ROOTS:
        paths.extend(_walk_mno(root))
    # unique, stable
    seen = set()
    uniq = []
    for p in paths:
        key = os.path.normcase(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    uniq.sort(key=lambda x: os.path.normcase(x))

    lines = []
    lines.append("MNO CENSUS SURFACE 2026-08-16")
    lines.append("button host/muhl_mno_census_surface.py")
    lines.append("sequential bounded header. dest FROM FILE. 337 not fired.")
    lines.append("n_unique %d" % len(uniq))
    lines.append("")

    rows = []
    for i, path in enumerate(uniq, 1):
        rec = {"path": path, "i": i}
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            rec["err"] = str(exc)
            lines.append("=== %d / %d FAIL stat ===" % (i, len(uniq)))
            lines.append("  path %s" % path)
            lines.append("  ERR %s" % exc)
            rows.append(rec)
            continue
        rec["size"] = size
        base = os.path.basename(path).lower()
        lines.append("=== %d / %d ===" % (i, len(uniq)))
        lines.append("  path %s" % path)
        lines.append("  size %d" % size)
        try:
            with open(path, "rb") as f:
                buf = f.read(HDR_N)
                rec["magic"] = buf[:8]
                n_in, n_wire, n_gate, n_out, depth = _parse_header(buf, size, lines, f)
                rec["n_in"] = n_in
                rec["n_wire"] = n_wire
                rec["n_gate"] = n_gate
                rec["n_out"] = n_out
                rec["depth"] = depth
                if base in DC_NAMES:
                    # published DC mouths only — same as muhl_surface_dc
                    for name, off, n in (("HEADER", 0, 8), ("FOLD", 224, 8),
                                         ("carry", 336, 1), ("pub", 337, 1),
                                         ("ring_fwd", 524288, 8), ("7913_pub", 524329, 1)):
                        if off == 337:
                            lines.append("  %s @%d SKIP 337 not fired" % (name, off))
                            continue
                        raw = _read_at(f, off, n, size)
                        if raw is None:
                            lines.append("  %s @%d PAST_EOF" % (name, off))
                        else:
                            lines.append("  %s @%d n=%d hex=%s bits=%s" % (
                                name, off, len(raw), raw.hex(),
                                "".join(_bits8(b) for b in raw[:8])))
                    rec["sha"] = "SKIP_DC"
                    lines.append("  sha SKIP_DC")
                elif base in GIG_NAMES:
                    rec["sha"] = "SKIP_GIG"
                    lines.append("  sha SKIP_GIG")
                else:
                    sha = _sha_cheap(path, size)
                    rec["sha"] = sha
                    lines.append("  sha %s" % sha)
        except OSError as exc:
            rec["err"] = str(exc)
            lines.append("  ERR %s" % exc)
        if rec.get("n_gate") and rec.get("depth"):
            cpt = rec["n_gate"] / float(rec["depth"])
            rec["cpt"] = cpt
            lines.append("  computations_per_tick %s  (n_gate/DEPTH)" % cpt)
            lines.append("  ticks_per_second 1000000000  (pfc_speed labeled 1 ns/stage 1/tau)")
        lines.append("  wrote NO inject NO 337 NO")
        rows.append(rec)
        if i % 25 == 0:
            print("surfaced %d / %d" % (i, len(uniq)), flush=True)

    # ranking table for netlist files
    ranked = [r for r in rows if r.get("cpt")]
    ranked.sort(key=lambda r: r["cpt"], reverse=True)
    lines.append("")
    lines.append("=== RANK computations/tick (n_gate/DEPTH) files with both published ===")
    for j, r in enumerate(ranked, 1):
        lines.append("%d  cpt=%.3f  n_gate=%s DEPTH=%s  size=%s  %s" % (
            j, r["cpt"], r.get("n_gate"), r.get("depth"), r.get("size"), r["path"]))

    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as out:
        out.write(text)
    print("n_unique %d" % len(uniq))
    print("n_with_cpt %d" % len(ranked))
    print("wrote %s" % OUT)
    print("337 NO")
    print("pulsed_78 NO")
    print("button dies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
