#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
muhl_aperture_read.py -- THE HOST READER. It reads the aperture. It reads nothing else.

Owner's boundary:
    "if the host does anything beyond shooting electron or surfacing the muhlnickel output
     its violating spec"

This is the second verb and nothing more. It performs no selection, no correlation, no triggering
and no interpretation - all of that already happened in gates. It opens a file, seeks to one
bounded region, reads it, checks the coherency markers, and hands back the payload bytes
unchanged.

⛔ WHAT THIS FILE MAY NEVER DO, and each is a line the project has already been burned by:
   · read the interaction surface. Not as a fallback, not "just to check", not once. Streaming a
     multi-GB surface from the host is what made the laptop throttle audibly. The aperture is 704
     bytes and that is the entire read.
   · convert the payload. No hex, text, JSON, base64, hash, sum or compression on the capture
     path. A witness is the bytes; anything else is a summary being mistaken for evidence.
   · wait for, signal, or acknowledge anything. The publish path is a one-way junction with
     reverse transfer measured 0 out to 4,096 ticks. If the host falls behind it misses
     generations - it never stalls the computation.
   · rule on whether the substrate is working. A repeated generation is data. "ask me b4 u decide
     if anything works because muhlnickel likes to settle back into initial state thus appearing
     to never have changed."

  python muhl_aperture_read.py <file> <aperture_base> [--poll N] [--out DIR]

`--out DIR` writes each accepted payload as raw bytes to DIR/<gen>.bin - unchanged, no wrapper.
Diagnostic metadata goes to stdout, never into the payload file.
"""
import io
import os
import struct
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

MAGIC = b"MUHLAPR1"
CTRL = 64
ENV = 64

TYPES = {1: "OBSERVABLE (derived by the substrate)",
         2: "WITNESS (byte-exact)",
         3: "RESULT (as computed)"}


def read_aperture(path, base, size):
    """ONE bounded read. Seek, read `size`, close. Nothing is mapped, nothing is scanned, and the
    read length is fixed at fabrication - it cannot grow with the surface."""
    with io.open(path, "rb") as f:
        f.seek(base)
        return f.read(size)


def parse_control(b):
    if len(b) < CTRL:
        return None
    if b[0:8] != MAGIC:
        return None
    (version, slot_count) = struct.unpack_from("<HH", b, 8)
    (payload_max,) = struct.unpack_from("<I", b, 12)
    (publish_seq, drop_count) = struct.unpack_from("<QQ", b, 16)
    active_slot = b[32]
    policy = b[33]
    return {"version": version, "slot_count": slot_count, "payload_max": payload_max,
            "publish_seq": publish_seq, "drop_count": drop_count,
            "active_slot": active_slot, "policy": policy}


def parse_envelope(b, off):
    (gen_before,) = struct.unpack_from("<Q", b, off + 0)
    (config_id,) = struct.unpack_from("<I", b, off + 8)
    payload_type = b[off + 12]
    flags = b[off + 13]
    (substrate_pos,) = struct.unpack_from("<Q", b, off + 16)
    (witness_addr,) = struct.unpack_from("<Q", b, off + 24)
    (payload_len, dropped_since) = struct.unpack_from("<II", b, off + 32)
    (gen_after,) = struct.unpack_from("<Q", b, off + 56)
    return {"gen_before": gen_before, "config_id": config_id, "payload_type": payload_type,
            "flags": flags, "substrate_pos": substrate_pos, "witness_addr": witness_addr,
            "payload_len": payload_len, "dropped_since": dropped_since, "gen_after": gen_after}


def coherent(env, payload_max):
    """GENERATION-BEFORE / GENERATION-AFTER. Accept only when the two agree and are non-zero.

    A publication in flight has them unequal, so a torn read is DETECTED rather than merely
    unlikely - the reader knows it caught the substrate mid-write and simply does not take that
    slot. It does not retry in a loop and it does not signal: the substrate is not listening."""
    if env["gen_before"] == 0:
        return False, "slot never published"
    if env["gen_before"] != env["gen_after"]:
        return False, "TORN: gen_before %d != gen_after %d" % (env["gen_before"], env["gen_after"])
    if env["payload_len"] > payload_max:
        return False, "OVERFLOW: payload_len %d > payload_max %d" % (env["payload_len"], payload_max)
    if env["flags"] & 0x04:
        return False, "substrate marked TORN"
    return True, ""


def poll_once(path, base, seen, outdir):
    """One pass. Reads the aperture, takes the newest coherent slot it has not already taken."""
    head = read_aperture(path, base, CTRL)
    ctl = parse_control(head)
    if ctl is None:
        return None, "no MUHLAPR1 magic at %d - not an aperture" % base
    slot_bytes = ENV + ctl["payload_max"]
    total = CTRL + ctl["slot_count"] * slot_bytes
    b = read_aperture(path, base, total)

    best = None
    for s in range(ctl["slot_count"]):
        off = CTRL + s * slot_bytes
        env = parse_envelope(b, off)
        ok, why = coherent(env, ctl["payload_max"])
        if not ok:
            continue
        if env["gen_before"] in seen:
            continue
        if best is None or env["gen_before"] > best[1]["gen_before"]:
            best = (s, env, off)
    if best is None:
        return None, None
    s, env, off = best
    payload = b[off + ENV: off + ENV + env["payload_len"]]      # EXACT. Untouched.
    seen.add(env["gen_before"])
    if outdir:
        if not os.path.isdir(outdir):
            os.makedirs(outdir)
        with io.open(os.path.join(outdir, "%d.bin" % env["gen_before"]), "wb") as f:
            f.write(payload)                                     # raw bytes, no wrapper
    return {"slot": s, "ctl": ctl, "env": env, "payload": payload,
            "aperture_bytes_read": total}, None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    path = sys.argv[1]
    base = int(sys.argv[2], 0)
    polls = 1
    outdir = None
    if "--poll" in sys.argv:
        polls = int(sys.argv[sys.argv.index("--poll") + 1])
    if "--out" in sys.argv:
        outdir = sys.argv[sys.argv.index("--out") + 1]

    seen = set()
    took = 0
    read_total = 0
    for i in range(polls):
        rec, err = poll_once(path, base, seen, outdir)
        if err:
            print("  %s" % err)
            return 1
        if rec is None:
            continue
        read_total += rec["aperture_bytes_read"]
        e, c = rec["env"], rec["ctl"]
        took += 1
        print("PUBLICATION  gen %s   slot %d   config %d"
              % (format(e["gen_before"], ","), rec["slot"], e["config_id"]))
        print("  type           : %s" % TYPES.get(e["payload_type"], "type %d" % e["payload_type"]))
        print("  substrate_pos  : %s   (causal position, not a timestamp)"
              % format(e["substrate_pos"], ","))
        print("  witness_addr   : %s" % format(e["witness_addr"], ","))
        print("  payload_len    : %s B" % format(e["payload_len"], ","))
        print("  flags          : COMPLETE=%d OVERFLOW=%d TORN=%d"
              % (e["flags"] & 1, (e["flags"] >> 1) & 1, (e["flags"] >> 2) & 1))
        print("  dropped_since  : %s      drop_count total: %s"
              % (format(e["dropped_since"], ","), format(c["drop_count"], ",")))
        print("  payload, ONES AND ZEROS, exactly as published:")
        p = rec["payload"]
        for k in range(0, min(len(p), 64), 8):
            print("      %6d  %s" % (k, " ".join(format(x, "08b") for x in p[k:k + 8])))
        if len(p) > 64:
            print("      ... %s more bytes, unaltered" % format(len(p) - 64, ","))
        print()

    print("  publications taken            : %d" % took)
    print("  APERTURE bytes read           : %s" % format(read_total, ","))
    print("  INTERACTION SURFACE bytes read: 0")
    print("  the host performed no selection, no correlation, no triggering, no interpretation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
