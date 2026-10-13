#!/usr/bin/env python3
"""host/muhl_fold_tick_add.py — moonshot fold routing button (additive).

Block-in-one-tick is already in the file (muhl_fold_phys + winner_only_max +
nring2_1023). This button injects and surfaces. It does not shrink the claim.

Host jobs, then die:
  1. put header + target INTO muhl_fold_phys (header_off, target_off from LIVE registry)
  2. address ONE bit at tick_off (that byte IS nring2_1023.recv)
  3. die

Surface of win_off + latch_off is a SEPARATE act (--surface). This is not
pfc_fire (packed-76 gen_input / target_reg / receiver). This is not a host SHA mine.

Default --dry: print the inject/surface plan from the live registry. Write nothing.
--go exists; it requires an explicit header (80-byte block header or 608 bit-bytes)
and target. Do not pass --go unless explicitly configured.

  python host/muhl_fold_tick_add.py
  python host/muhl_fold_tick_add.py --dry
  python host/muhl_fold_tick_add.py --surface
  python host/muhl_fold_tick_add.py --go --header HEX --target HEX
"""
from __future__ import annotations

import json
import mmap
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import pfc_paths as PFCP
    TITAN = PFCP.TITAN
    REG = PFCP.REG
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    TITAN = PFC_ROOT + "/models/titan.gguf"
    REG = PFC_ROOT + "/models/titan_circuits.json"

FOLD_NAME = "muhl_fold_phys"
RING_NAME = "nring2_1023"
HEADER_BITS = 608
TARGET_BITS = 256
LATCH_BITS = 32
PACKED_HEADER80 = 80
PACKED_HEADER76 = 76
PACKED_TARGET32 = 32

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _need_int(obj, key, where):
    if not isinstance(obj, dict) or obj.get(key) is None:
        return None, "%s missing %s" % (where, key)
    try:
        val = int(obj[key])
    except (TypeError, ValueError):
        return None, "%s.%s is not an int" % (where, key)
    if val < 0:
        return None, "%s.%s is negative" % (where, key)
    return val, None


def _load_registry():
    if not os.path.isfile(REG):
        return None, "registry missing: %s" % REG
    try:
        with open(REG, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "registry unreadable: %s" % exc


def _hex_or_file(raw):
    if raw is None:
        return None, "missing"
    s = str(raw).strip()
    if s.startswith("@") and len(s) > 1:
        path = s[1:]
        if not os.path.isfile(path):
            return None, "file missing: %s" % path
        with open(path, "rb") as f:
            blob = f.read()
        text = blob.decode("ascii", "replace").strip().replace(" ", "").replace("\n", "")
        if text.startswith("0x") or text.startswith("0X"):
            text = text[2:]
        try:
            return bytes.fromhex(text), None
        except ValueError:
            return blob, None
    if s.startswith("0x") or s.startswith("0X"):
        s = s[2:]
    s = "".join(s.split())
    try:
        return bytes.fromhex(s), None
    except ValueError:
        return None, "not hex and not @file: %s" % raw[:48]


def _bits_ok(blob):
    return all(b in (0, 1) for b in blob)


def unpack_header80(packed):
    """80-byte Bitcoin header -> 608 bit-bytes. First 76 bytes, 19 BE words, LSB-first.

    Same convention as miner_physical / muhl_fold_phys.convention_source.
    Bytes 76..79 (packed nonce) are not injected: nonce IS the address.
    """
    if len(packed) != PACKED_HEADER80:
        return None, "header must be 80 packed bytes (got %d)" % len(packed)
    prefix = packed[:PACKED_HEADER76]
    out = bytearray(HEADER_BITS)
    for w in range(19):
        word_val = struct.unpack(">I", prefix[w * 4:(w + 1) * 4])[0]
        for j in range(32):
            out[w * 32 + j] = (word_val >> j) & 1
    return bytes(out), None


def unpack_target32(packed):
    """32 packed bytes -> 256 bit-bytes, LSB-first per byte."""
    if len(packed) != PACKED_TARGET32:
        return None, "target must be 32 packed bytes (got %d)" % len(packed)
    out = bytearray(TARGET_BITS)
    for k in range(PACKED_TARGET32):
        byte_val = packed[k]
        for j in range(8):
            out[k * 8 + j] = (byte_val >> j) & 1
    return bytes(out), None


def prepare_header(blob):
    if blob is None:
        return None, "header missing"
    if len(blob) == PACKED_HEADER76:
        return None, (
            "REFUSED packed-76 pfc_fire path (gen_input). "
            "Pass 80-byte block header or 608 bit-bytes."
        )
    if len(blob) == PACKED_HEADER80:
        return unpack_header80(blob)
    if len(blob) == HEADER_BITS:
        if not _bits_ok(blob):
            return None, "608-byte header is not one-byte-per-bit (0/1 only)"
        return blob, None
    return None, (
        "header length %d is not 80 packed or 608 bit-bytes "
        "(76 packed is the pfc_fire mouth — refused)" % len(blob)
    )


def prepare_target(blob):
    if blob is None:
        return None, "target missing"
    if len(blob) == PACKED_TARGET32:
        return unpack_target32(blob)
    if len(blob) == TARGET_BITS:
        if not _bits_ok(blob):
            return None, "256-byte target is not one-byte-per-bit (0/1 only)"
        return blob, None
    return None, "target length %d is not 32 packed or 256 bit-bytes" % len(blob)


def load_plan():
    """Fail closed if fold/ring names or offsets are missing. Never guess."""
    reg, err = _load_registry()
    if err:
        return None, err
    if FOLD_NAME not in reg or not isinstance(reg[FOLD_NAME], dict):
        return None, "%s not in registry" % FOLD_NAME
    if RING_NAME not in reg or not isinstance(reg[RING_NAME], dict):
        return None, "%s not in registry" % RING_NAME

    fold = reg[FOLD_NAME]
    ring = reg[RING_NAME]
    ram = fold.get("ram")
    if not isinstance(ram, dict):
        return None, "%s missing ram" % FOLD_NAME

    offs = {}
    for key in ("header_off", "target_off", "tick_off", "win_off", "latch_off"):
        val, err = _need_int(ram, key, "%s.ram" % FOLD_NAME)
        if err:
            return None, err
        offs[key] = val

    nonce_off, nonce_err = _need_int(ram, "nonce_off", "%s.ram" % FOLD_NAME)
    if nonce_err:
        nonce_off = None

    ring_recv, err = _need_int(ring, "recv", RING_NAME)
    if err:
        ram_r = ring.get("ram")
        if isinstance(ram_r, dict):
            ring_recv, err = _need_int(ram_r, "recv", "%s.ram" % RING_NAME)
        if err:
            return None, err

    ram_recv = None
    if isinstance(ring.get("ram"), dict) and ring["ram"].get("recv") is not None:
        ram_recv, _ = _need_int(ring["ram"], "recv", "%s.ram" % RING_NAME)

    osc = fold.get("oscillation") if isinstance(fold.get("oscillation"), dict) else {}
    osc_recv = None
    if osc.get("recv") is not None:
        osc_recv, _ = _need_int(osc, "recv", "%s.oscillation" % FOLD_NAME)
    osc_ring = osc.get("ring")

    senses = ring.get("senses")
    try:
        senses_i = int(senses) if senses is not None else None
    except (TypeError, ValueError):
        senses_i = None
    cells, _ = _need_int(ring, "cells", RING_NAME)
    fwd = rev = None
    if isinstance(ring.get("ram"), dict):
        fwd, _ = _need_int(ring["ram"], "fwd", "%s.ram" % RING_NAME)
        rev, _ = _need_int(ring["ram"], "rev", "%s.ram" % RING_NAME)

    seeded = ring.get("seeded") if isinstance(ring.get("seeded"), dict) else {}

    need_bryce = []
    tick = offs["tick_off"]
    if tick != ring_recv:
        need_bryce.append(
            "tick_off %d != %s.recv %d — do not invent a second physics"
            % (tick, RING_NAME, ring_recv)
        )
    if ram_recv is not None and ram_recv != tick:
        need_bryce.append(
            "%s.ram.recv %d != tick_off %d" % (RING_NAME, ram_recv, tick)
        )
    if osc_recv is not None and osc_recv != tick:
        need_bryce.append(
            "%s.oscillation.recv %d != tick_off %d" % (FOLD_NAME, osc_recv, tick)
        )
    if osc_ring is not None and osc_ring != RING_NAME:
        need_bryce.append(
            "%s.oscillation.ring is %r not %s" % (FOLD_NAME, osc_ring, RING_NAME)
        )
    if senses_i != 2:
        need_bryce.append(
            "%s senses=%r (need 2; both-sense ring law)" % (RING_NAME, senses)
        )
    if not seeded.get("fwd") or not seeded.get("rev"):
        need_bryce.append(
            "%s seeded both-senses not in registry (nring2_run: else carry is DC)"
            % RING_NAME
        )

    titan_exists = os.path.isfile(TITAN)
    titan_size = os.path.getsize(TITAN) if titan_exists else None
    unsafe = list(need_bryce)
    if not titan_exists:
        unsafe.append("titan missing: %s" % TITAN)
    elif titan_size is not None:
        for name, off, n in (
            ("header_off", offs["header_off"], HEADER_BITS),
            ("target_off", offs["target_off"], TARGET_BITS),
            ("tick_off", offs["tick_off"], 1),
            ("win_off", offs["win_off"], 1),
            ("latch_off", offs["latch_off"], LATCH_BITS),
        ):
            if off + n > titan_size:
                unsafe.append("%s %d+%d past titan size %d" % (name, off, n, titan_size))

    return {
        "fold": fold,
        "ring": ring,
        "offs": offs,
        "nonce_off": nonce_off,
        "ring_recv": ring_recv,
        "ram_recv": ram_recv,
        "osc_recv": osc_recv,
        "osc_ring": osc_ring,
        "senses": senses_i,
        "cells": cells,
        "fwd": fwd,
        "rev": rev,
        "seeded": seeded,
        "need_bryce": need_bryce,
        "unsafe": unsafe,
        "titan_exists": titan_exists,
        "titan_size": titan_size,
    }, None


def print_plan(plan, dry=True):
    if dry:
        mode = "DRY — plan only, no titan write"
    else:
        mode = "GO — inject header+target, mmap one bit at tick_off, die"
    fold = plan["fold"]
    offs = plan["offs"]
    print("\nMUHL FOLD TICK (additive moonshot button)")
    print("  mode:     %s" % mode)
    print("  titan:    %s" % TITAN)
    print("  reg:      %s" % REG)
    print("  circuit:  %s  magic=%s  n_gate=%s  depth=%s"
          % (FOLD_NAME, fold.get("magic"), fold.get("n_gate"), fold.get("depth")))
    print("  power:    %s  senses=%s  cells=%s  magic=%s"
          % (RING_NAME, plan["senses"], plan["cells"], plan["ring"].get("magic")))
    print("  claim:    one tick covers the winner-only fold already stored in the file")
    print("  law:      tick_off IS %s.recv; mmap of ONE receiver byte is the start"
          % RING_NAME)
    print("  law:      both-sense ring already seeded; do not invent a second physics")
    print("  refuse:   packed-76 gen_input / target_reg / receiver (pfc_fire path)")
    print("  refuse:   host-eval SHA as the mine")
    print()
    print("  INJECT (header + target into the fold)")
    print("    header_off  %d  (%d bit-bytes, one byte per bit, LSB-first)"
          % (offs["header_off"], HEADER_BITS))
    print("    target_off  %d  (%d bit-bytes)"
          % (offs["target_off"], TARGET_BITS))
    if plan["nonce_off"] is not None:
        print("    nonce_off   %d  (NOT injected — nonce IS the address)"
              % plan["nonce_off"])
    print()
    print("  START (ONE bit, then die)")
    print("    tick_off    %d  (%s.ram.tick_off)" % (offs["tick_off"], FOLD_NAME))
    print("    ring recv   %d  (%s.recv)" % (plan["ring_recv"], RING_NAME))
    if plan["ram_recv"] is not None:
        print("    ram.recv    %d  (%s.ram.recv)" % (plan["ram_recv"], RING_NAME))
    if plan["osc_recv"] is not None:
        print("    osc.recv    %d  (%s.oscillation.recv)" % (plan["osc_recv"], FOLD_NAME))
    if plan["fwd"] is not None and plan["rev"] is not None:
        print("    ring fwd    %d  rev %d  (power rails; not this button's fire)"
              % (plan["fwd"], plan["rev"]))
    seeded = plan["seeded"]
    if seeded:
        print("    seeded      fwd=%s rev=%s copied_from=%s"
              % (seeded.get("fwd"), seeded.get("rev"), seeded.get("copied_from")))
    print("    fire        mmap ACCESS_READ of tick_off / recv (address, do not host-clock)")
    print()
    print("  SURFACE (separate act — --surface)")
    print("    win_off     %d  (1 byte)" % offs["win_off"])
    print("    latch_off   %d  (%d bit-bytes, one per bit, the nonce)"
          % (offs["latch_off"], LATCH_BITS))
    if plan["titan_exists"]:
        print("    titan       present (%s bytes)" % plan["titan_size"])
    else:
        print("    titan       missing")
    print()
    if plan["need_bryce"]:
        print("  NEED_BRYCE (do not inject / do not fire):")
        for reason in plan["need_bryce"]:
            print("    - %s" % reason)
        print()
    extra = [u for u in plan["unsafe"] if u not in plan["need_bryce"]]
    if extra:
        print("  UNSAFE:")
        for reason in extra:
            print("    - %s" % reason)
        print()
    if dry:
        print("  (no write performed; --go was not passed)")
        print()
    return 0


def _readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def surface(plan):
    if not plan["titan_exists"]:
        return _fail("titan missing: %s" % TITAN)
    offs = plan["offs"]
    win = _readback(offs["win_off"], 1)
    latch = _readback(offs["latch_off"], LATCH_BITS)
    if len(win) != 1:
        return _fail("short read win_off")
    if len(latch) != LATCH_BITS:
        return _fail("short read latch_off")
    nonce = sum((latch[j] & 1) << j for j in range(LATCH_BITS))
    print("\nSURFACE — bounded read (win_off + latch_off). Host does not SHA.\n")
    print("  win_off   @ %d : 0x%s" % (offs["win_off"], win.hex()))
    print("  latch_off @ %d : %s" % (offs["latch_off"], latch.hex()))
    print("  latch assembled nonce: 0x%08x" % nonce)
    print("  (submit is a later owner act if win says winner; not this button)")
    print()
    return 0


def _write_bits(off, blob):
    with open(TITAN, "r+b") as f:
        for i, b in enumerate(blob):
            f.seek(off + i)
            f.write(bytes((b,)))
        f.flush()
        os.fsync(f.fileno())


def _address_tick(tick_off):
    """mmap of ONE receiver byte is the spec start. Not a write. Not a host clock."""
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            _ = mm[tick_off]
        finally:
            mm.close()


def go(plan, header_raw, target_raw):
    if plan["need_bryce"] or plan["unsafe"]:
        print_plan(plan, dry=True)
        print("GO REFUSED: NEED_BRYCE / unsafe — do not inject.\n")
        return 1
    header_blob, err = _hex_or_file(header_raw)
    if err:
        return _fail("header: %s" % err)
    target_blob, err = _hex_or_file(target_raw)
    if err:
        return _fail("target: %s" % err)
    header_bits, err = prepare_header(header_blob)
    if err:
        return _fail(err)
    target_bits, err = prepare_target(target_blob)
    if err:
        return _fail(err)

    print_plan(plan, dry=False)
    offs = plan["offs"]
    _write_bits(offs["header_off"], header_bits)
    _write_bits(offs["target_off"], target_bits)
    print("  routed: header -> header_off (%d bit-bytes)" % len(header_bits))
    print("  routed: target -> target_off (%d bit-bytes)" % len(target_bits))
    _address_tick(offs["tick_off"])
    print("  FIRED: mmap one byte at tick_off %d (= %s.recv). button dies."
          % (offs["tick_off"], RING_NAME))
    print("  surface is separate: python host/muhl_fold_tick_add.py --surface")
    print()
    return 0


def _flag_value(argv, name):
    if name not in argv:
        return None
    i = argv.index(name)
    if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
        return ""
    return argv[i + 1]


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    plan, err = load_plan()
    if err:
        return _fail(err)

    do_go = "--go" in a
    do_surface = "--surface" in a
    do_dry = ("--dry" in a) or (not do_go and not do_surface)

    if do_go and do_dry:
        print_plan(plan, dry=True)
        print("  --dry wins over --go; no write.\n")
        return 0
    if do_go and do_surface:
        return _fail("pass --go or --surface, not both (surface is a separate act)")
    if do_go:
        header = _flag_value(a, "--header")
        target = _flag_value(a, "--target")
        if not header or not target:
            return _fail(
                "--go requires explicit --header (80-byte or 608 bit-bytes) "
                "and --target (32 packed or 256 bit-bytes). "
                "Refuse live packed-76 pfc_fire path. No pool fetch."
            )
        return go(plan, header, target)
    if do_surface:
        print_plan(plan, dry=True)
        return surface(plan)
    return print_plan(plan, dry=True)


if __name__ == "__main__":
    raise SystemExit(main())
