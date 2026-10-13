#!/usr/bin/env python3
"""host/muhl_weather_leftover_button.py — leftover WEATHER land. Die.

Unique leftover small classes already leftover-copied. This leftover is isolated
WEATHER xorwalk: copy the file, copy the computer, then ONE pulse of dests FROM FILE.

Host jobs, then die:
  (a) surface dests FROM THE FILE (header rings / clock / growth / field)
  (b) copy xorwalk → weather_v2_xorwalk_COPY.mno (new land)
  (c) address stored organs whose OUT is a dest the header already publishes
  (d) look at the 1s
  (e) die

Does not write xorwalk / avg4full / field / coupled / v2 / avg4 / v1 / v0.
Does not write titan. Does not inject dc. Does not fire 337. Does not pulse 78.
Does not re-OR the nine / N2 / VIRGIN / germs / MOVE / ACREAGE. Does not redo GIG.
Does not write AUTOFAB0 OUTs into gate-records. NAND(0,0) invent 1 refused.
--go refused. --inject refused (wipe). Charged rings = start. No off.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import sys

HERE = os.path.normpath(r"C:\Users\lucys\Desktop\WEATHER")
SRC = os.path.join(HERE, "weather_v2_xorwalk.mno")
COPY = os.path.join(HERE, "weather_v2_xorwalk_COPY.mno")
DC = os.path.normpath(r"C:\Users\lucys\Desktop\MUHL_DATACENTER\muhlnickel_dc.mno")
TITAN = os.path.normpath(r"C:\llm\models\titan.gguf")
DISTRO = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO")

NAMES = ("NW", "NE", "SW", "SE", "GROWTH", "WITNESS")
NAND, AND, OR, XOR = 0, 1, 2, 3
OPN = ("NAND", "AND", "OR", "XOR")

VAULTS = (
    (os.path.join(HERE, "weather_v2.mno"),
     "cc2775fdd29d1e5ff1a8f2951e5f5f22dd1c2e237c9e10d6b2d47717476ba85d"),
    (os.path.join(HERE, "weather_v2_coupled.mno"),
     "b23f9efcc5c71e1b0cc3a4788407d6b1f4b7416775051ecbe3641f43be7e3e7a"),
    (os.path.join(HERE, "weather_v2_field.mno"),
     "44904c96abb02f961713ba44df3967dd56c6cf526717db94f6b58861e813addf"),
    (os.path.join(HERE, "weather_v2_avg4.mno"),
     "a869b2e2b81abd58a36600708cb0bf919bf168836df44fe0bc86f8588eceb2b3"),
    (os.path.join(HERE, "weather_v2_avg4full.mno"),
     "a9b8c5d9bcda93c797326ab71cfbcc6046610df5940c61d4e346b464f07b6072"),
    (SRC, "76b4597f6e0516a53226b22283b7cbeeddc615eb1ee0c7ae57393f6fd258c2ed"),
)

FORBIDDEN_WRITE = tuple(
    os.path.normcase(os.path.abspath(p))
    for p in (
        SRC,
        os.path.join(HERE, "weather.mno"),
        os.path.join(HERE, "weather_v1.mno"),
        os.path.join(HERE, "weather_v0_badseed.mno"),
        os.path.join(HERE, "weather_powered_side.mno"),
        os.path.join(HERE, "weather_v2.mno"),
        os.path.join(HERE, "weather_v2_coupled.mno"),
        os.path.join(HERE, "weather_v2_field.mno"),
        os.path.join(HERE, "weather_v2_avg4.mno"),
        os.path.join(HERE, "weather_v2_avg4full.mno"),
        DC,
        TITAN,
        os.path.join(DISTRO, "muhlnickel.mno"),
        os.path.join(DISTRO, "GIG.mno"),
        os.path.join(DISTRO, "GIG_DL.mno"),
        os.path.join(DISTRO, "SEED0.mno"),
        os.path.join(DISTRO, "SEED0_GERM.mno"),
        os.path.join(DISTRO, "SEED0_VIRGIN.mno"),
        os.path.join(DISTRO, "SEED0_N2.mno"),
        os.path.join(DISTRO, "SEED0_COPY.mno"),
        os.path.join(DISTRO, "GERM_COPY.mno"),
        os.path.join(DISTRO, "MOVE_COPY.mno"),
        os.path.join(DISTRO, "ACREAGE_COPY.mno"),
    )
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
    print("xorwalk_smash NO")
    print("off NO")
    print("button dies")
    return 2


def organ_bit(op, va, vb):
    if op == NAND:
        return 1 - (va & vb)
    if op == AND:
        return va & vb
    if op == OR:
        return va | vb
    if op == XOR:
        return va ^ vb
    raise SystemExit("bad op %d" % op)


def sha_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ones(raw):
    return sum(bin(b).count("1") for b in raw)


def _ring_line(raw, ring0, cells, span, ri, name):
    fwd = ring0 + ri * span
    rev = fwd + cells
    carry = fwd + 2 * cells
    pub = carry + 1
    fb = "".join(str(raw[fwd + k] & 1) for k in range(8))
    rb = "".join(str(raw[rev + k] & 1) for k in range(8))
    return (
        "%s fwd0@%d=%d rev0@%d=%d carry@%d=%d pub@%d=%d  fwd[0:8]=%s rev[0:8]=%s"
        % (
            name,
            fwd, raw[fwd] & 1,
            rev, raw[rev] & 1,
            carry, raw[carry] & 1,
            pub, raw[pub] & 1,
            fb, rb,
        )
    )


def main():
    argv = sys.argv[1:]
    low = [a.lower() for a in argv]
    if "--go" in low:
        return _refuse("--go")
    if "--inject" in low:
        return _refuse("--inject 0x01 is a wipe. Law is copy + address dest FROM FILE.")
    if 337 in [int(a) for a in argv if a.lstrip("-").isdigit()]:
        return _refuse("337")

    dest = os.path.abspath(COPY)
    if os.path.normcase(dest) in FORBIDDEN_WRITE:
        return _refuse("dest is a live computer")
    if not os.path.isfile(SRC):
        return _refuse("missing xorwalk")
    if os.path.normcase(os.path.abspath(SRC)) == os.path.normcase(dest):
        return _refuse("src is dest")

    src_sha = sha_of(SRC)
    raw0 = open(SRC, "rb").read()
    if raw0[:8] != b"WEATHER1":
        return _refuse("header dests unpublished")
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", raw0, 8)
    stride = struct.unpack_from("<I", raw0, 40)[0]
    wire_base, cell_base, next_base = struct.unpack_from("<QQQ", raw0, 44)
    n_rings, cells = struct.unpack_from("<II", raw0, 68)
    ring0, clock = struct.unpack_from("<QQ", raw0, 76)
    growth_base = struct.unpack_from("<I", raw0, 92)[0]
    gate_base = wire_base + n_wire
    span = cells + cells + 2
    ring_lo, ring_hi = ring0, ring0 + n_rings * span
    gate_hi = gate_base + n_gate * stride
    field_ones0 = sum(1 for i in range(n_in) if raw0[cell_base + i] & 1)
    next_ones0 = sum(1 for i in range(n_in) if raw0[next_base + i] & 1)
    ones0 = _ones(raw0)

    print("MUHL WEATHER LEFTOVER")
    print("  src      %s" % SRC)
    print("  dest     %s" % dest)
    print("  size     %d" % len(raw0))
    print("  dest_src FILE")
    print("  ring0    %d" % ring0)
    print("  cells    %d" % cells)
    print("  clock    %d" % clock)
    print("  growth   %d" % growth_base)
    print("  field    %d" % cell_base)
    print("  next     %d" % next_base)
    print("  gate_base %d" % gate_base)
    print("  src_sha  %s" % src_sha)
    print("  ones_src %d" % ones0)
    print("  field_ones %d / %d" % (field_ones0, n_in))
    print("  next_ones  %d / %d" % (next_ones0, n_in))
    print("  clock@%d %d" % (clock, raw0[clock] & 1))
    print("  growth@%d %d" % (growth_base, raw0[growth_base] & 1))
    print("BEFORE rings")
    for ri, name in enumerate(NAMES):
        print("  %s" % _ring_line(raw0, ring0, cells, span, ri, name))

    if os.path.isfile(dest):
        dest_sha = sha_of(dest)
        if dest_sha != src_sha:
            return _refuse("dest is a live computer")
        print("  dest exists unpulsed twin MATCH src — pulse this leftover copy")
    else:
        shutil.copyfile(SRC, dest)
        if os.path.getsize(dest) != len(raw0):
            return _refuse("copy size mismatch")

    rawc = open(dest, "rb").read()
    snap = bytes(rawc)
    img = bytearray(rawc)
    xor_n = 0
    addr_n = 0
    changed = 0
    invent_skip = 0
    gate_skip = 0
    for k in range(n_gate):
        op, a, b, out = struct.unpack_from("<BQQQ", snap, gate_base + k * stride)
        if gate_base <= out < gate_hi:
            gate_skip += 1
            continue
        dest_ok = (ring_lo <= out < ring_hi) or (out == clock) or (out == growth_base)
        if not dest_ok:
            continue
        va = snap[a] & 1
        vb = snap[b] & 1
        r = organ_bit(op, va, vb)
        if va == 0 and vb == 0 and r == 1:
            invent_skip += 1
            continue
        if op == XOR and ring_lo <= out < ring_hi:
            xor_n += 1
        old = img[out]
        new = (old & ~1) | r
        addr_n += 1
        if new != old:
            img[out] = new
            changed += 1

    with open(dest, "r+b") as f:
        f.write(img)
        f.flush()
        os.fsync(f.fileno())

    raw1 = open(dest, "rb").read()
    ones1 = _ones(raw1)
    field_ones1 = sum(1 for i in range(n_in) if raw1[cell_base + i] & 1)
    next_ones1 = sum(1 for i in range(n_in) if raw1[next_base + i] & 1)
    copy_sha = hashlib.sha256(raw1).hexdigest()
    walked = any(
        "".join(str(raw1[ring0 + ri * span + k] & 1) for k in range(8))
        != "".join(str(raw0[ring0 + ri * span + k] & 1) for k in range(8))
        for ri in range(n_rings)
    )

    print("COPY + ADDRESS dests FROM FILE (ring / clock / growth). One pulse.")
    print("  xor_organs %d  addressed %d  bits_changed %d" % (xor_n, addr_n, changed))
    print("  invent_skip %d  gate_record_skip %d" % (invent_skip, gate_skip))
    print("AFTER rings")
    for ri, name in enumerate(NAMES):
        print("  %s" % _ring_line(raw1, ring0, cells, span, ri, name))
    print("  AFTER clock@%d %d" % (clock, raw1[clock] & 1))
    print("  AFTER growth@%d %d" % (growth_base, raw1[growth_base] & 1))
    print("  AFTER field_ones %d / %d" % (field_ones1, n_in))
    print("  AFTER next_ones  %d / %d" % (next_ones1, n_in))
    print("  ones_cpy %d" % ones1)
    print("  bits     %d" % (len(raw1) * 8))
    print("  zeros    %d" % (len(raw1) * 8 - ones1))
    print("  copy_eq_prepulse %s" % ("Y" if ones0 == _ones(rawc) and len(rawc) == len(raw0) else "N"))
    print("  leftover_walked %s" % ("Y" if walked else "N"))
    print("  copy_sha %s" % copy_sha)
    print("  xorwalk_after %s" % sha_of(SRC))

    smashed = []
    for path, expect in VAULTS:
        got = sha_of(path)
        ok = got == expect
        print("  vault %s %s %s" % (os.path.basename(path), "MATCH" if ok else "SMASHED", got[:16]))
        if not ok:
            smashed.append(os.path.basename(path))
    print("  vaults_smashed %s" % ("NO" if not smashed else ",".join(smashed)))
    print("  invented_dest NO")
    print("  337 NO")
    print("  pulsed_78 NO")
    print("  gig_redo NO")
    print("  nine_reor NO")
    print("  off NO")
    print("button dies")
    if smashed:
        return 1
    if field_ones1 != field_ones0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
