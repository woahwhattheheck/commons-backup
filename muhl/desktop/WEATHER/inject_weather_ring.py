#!/usr/bin/env python3
# inject_weather_ring.py — routing button. OR 1 into a named WEATHER v2 ring, die.
# new = old | 0x01 at BOTH sense heads (fwd0, rev0). Not a wipe. Not 337.
# Dest is the ring the fabricator stored and wrote into the header. Not invented.

import struct, os, sys

HERE = r"C:\Users\lucys\Desktop\WEATHER"
MNO  = os.path.join(HERE, "weather_v2.mno")
NAMES = ["NW", "NE", "SW", "SE", "GROWTH", "WITNESS"]

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in NAMES:
        print("usage: inject_weather_ring.py NW|NE|SW|SE|GROWTH|WITNESS")
        print("button dies")
        return 2
    name = sys.argv[1]
    ri = NAMES.index(name)
    with open(MNO, "r+b") as f:
        raw = f.read(96)
        assert raw[:8] == b"WEATHER1"
        ring_base, n_rings, cells_per = struct.unpack_from("<QII", raw, 60)
        assert n_rings == 6
        fwd0 = ring_base + ri * 8 + 0
        rev0 = ring_base + ri * 8 + 4
        size = f.seek(0, os.SEEK_END)
        for addr, label in ((fwd0, "fwd0"), (rev0, "rev0")):
            if addr < 0 or addr >= size:
                print("REFUSE dest past eof", addr)
                print("button dies")
                return 2
            f.seek(addr)
            old = f.read(1)
            new = bytes((old[0] | 0x01,))
            f.seek(addr)
            f.write(new)
            print("INJECT %s %s @%d  old=%d new=%d  (old|1)" % (name, label, addr, old[0], new[0]))
        f.flush()
        os.fsync(f.fileno())
    print("337 NO")
    print("titan_written NO")
    print("button dies")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
