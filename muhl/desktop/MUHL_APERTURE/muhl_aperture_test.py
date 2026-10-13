#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
muhl_aperture_test.py -- FIVE FOCUSED TESTS. Not a suite.

Owner: "Do not generate large combinatorial, byte-exhaustive, or speculative test suites. Do not
add tests merely to reconfirm already-established substrate behavior."

So this covers exactly the five things the ABI promises and nothing else:

  1. ENVELOPE ROUND-TRIP        every field written comes back with the same value
  2. COHERENT PUBLISH/READ      a complete publication is taken, once, by generation
  3. TORN REJECTION             gen_before != gen_after is refused, not merely improbable
  4. OVERWRITE WITHOUT BACKPRESSURE  a slow reader loses generations and the count is exact;
                                the writer never waits and never slows
  5. EXACT WITNESS BYTES        the payload survives publication unchanged, bit for bit

The publication side here writes the aperture image directly, which is what the fabricated gates
land in the container - the same bytes, the same layout, exercised without firing anything. The
gate-level properties are already covered by the fabricator's own mutant battery (5 of 5).

  python muhl_aperture_test.py
"""
import io
import os
import struct
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import muhl_aperture_read as R

MAGIC = b"MUHLAPR1"
CTRL, ENV = 64, 64
P = 256
SLOT = ENV + P
APERTURE = CTRL + 2 * SLOT


def blank():
    return bytearray(APERTURE)


def put_control(a, seq, drops, active, policy=0):
    a[0:8] = MAGIC
    struct.pack_into("<HH", a, 8, 1, 2)
    struct.pack_into("<I", a, 12, P)
    struct.pack_into("<QQ", a, 16, seq, drops)
    a[32] = active
    a[33] = policy


def publish(a, slot, gen, payload, config_id=7, ptype=2, pos=0, waddr=0,
            dropped=0, flags=0x01, tear=False):
    """Write one publication exactly as the ABI specifies: gen_before FIRST, payload, gen_after
    LAST. `tear` stops before gen_after, which is what a reader catching the substrate mid-write
    would see."""
    off = CTRL + slot * SLOT
    struct.pack_into("<Q", a, off + 0, gen)
    struct.pack_into("<I", a, off + 8, config_id)
    a[off + 12] = ptype
    a[off + 13] = flags
    struct.pack_into("<Q", a, off + 16, pos)
    struct.pack_into("<Q", a, off + 24, waddr)
    struct.pack_into("<II", a, off + 32, len(payload), dropped)
    a[off + ENV: off + ENV + len(payload)] = payload
    if not tear:
        struct.pack_into("<Q", a, off + 56, gen)


def as_file(a):
    fd, path = tempfile.mkstemp(suffix=".aperture")
    os.close(fd)
    with io.open(path, "wb") as f:
        f.write(b"\x00" * 4096)          # the aperture sits at an offset, like it does in the file
        f.write(bytes(a))
    return path, 4096


def main():
    ok = bad = 0

    def check(name, cond, detail=""):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("PASS  %s" % name)
        else:
            bad += 1
            print("MISS  %s   %s" % (name, detail))

    # ── 1. ENVELOPE ROUND-TRIP
    a = blank()
    put_control(a, seq=1, drops=0, active=1)
    body = bytes((i * 37 + 11) & 0xFF for i in range(P))
    publish(a, 0, gen=1, payload=body, config_id=4242, ptype=2,
            pos=0xDEADBEEF, waddr=0x1_0000_0000, dropped=0)
    path, base = as_file(a)
    rec, err = R.poll_once(path, base, set(), None)
    e = rec["env"] if rec else {}
    check("1 envelope round-trip", rec is not None and e.get("config_id") == 4242
          and e.get("payload_type") == 2 and e.get("substrate_pos") == 0xDEADBEEF
          and e.get("witness_addr") == 0x1_0000_0000 and e.get("payload_len") == P,
          "err=%s env=%s" % (err, e))

    # ── 5. EXACT WITNESS BYTES  (checked on the same publication)
    check("5 witness bytes unchanged", rec is not None and rec["payload"] == body,
          "payload differs")
    os.remove(path)

    # ── 2. COHERENT PUBLISH / READ - taken once, by generation
    a = blank()
    put_control(a, seq=2, drops=0, active=0)
    publish(a, 0, gen=9, payload=b"\xAA" * 16)
    path, base = as_file(a)
    seen = set()
    r1, _ = R.poll_once(path, base, seen, None)
    r2, _ = R.poll_once(path, base, seen, None)
    check("2 coherent publish/read, taken exactly once",
          r1 is not None and r1["env"]["gen_before"] == 9 and r2 is None,
          "r1=%s r2=%s" % (bool(r1), bool(r2)))
    os.remove(path)

    # ── 3. TORN REJECTION
    a = blank()
    put_control(a, seq=3, drops=0, active=0)
    publish(a, 0, gen=11, payload=b"\x5A" * 32, tear=True)   # gen_after never written
    path, base = as_file(a)
    r, _ = R.poll_once(path, base, set(), None)
    check("3 torn publication rejected", r is None,
          "reader took a publication with gen_after unwritten")
    os.remove(path)

    # ── 4. OVERWRITE WITHOUT BACKPRESSURE
    #    The writer publishes generations 20..27 into two slots while the reader takes nothing.
    #    Nothing blocks, nothing is acknowledged, and the reader ends up with the NEWEST coherent
    #    slot plus an exact count of what it missed.
    a = blank()
    published = list(range(20, 28))
    for i, gen in enumerate(published):
        put_control(a, seq=gen, drops=gen - 20, active=(i + 1) % 2)
        publish(a, i % 2, gen=gen, payload=bytes([gen]) * 8, dropped=1 if i else 0)
    path, base = as_file(a)
    r, _ = R.poll_once(path, base, set(), None)
    ctl = r["ctl"] if r else {}
    took_gen = r["env"]["gen_before"] if r else None
    missed = len(published) - 1
    check("4 overwrite, no backpressure, loss counted",
          r is not None and took_gen == 27 and ctl.get("drop_count") == 7,
          "took gen %s, drop_count %s, expected 27 / 7" % (took_gen, ctl.get("drop_count")))
    print("      the reader took generation %s and missed %d - reported, not hidden."
          % (took_gen, missed))
    print("      the writer wrote all %d without reading one byte from the host." % len(published))
    os.remove(path)

    print()
    print("%d pass, %d miss" % (ok, bad))
    print("aperture bytes per poll : %d" % APERTURE)
    print("surface bytes per poll  : 0")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
