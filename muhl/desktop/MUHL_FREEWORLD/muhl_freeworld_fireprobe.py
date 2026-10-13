#!/usr/bin/env python3
"""muhl_freeworld_fireprobe.py -- an HONEST measurement of the in-spec fire, to bring to Bryce.

Not part of the experiment (no field writes). It answers one structural question with numbers:
when the host injects DISTINCT inputs at fwd_input and powers fwd_receiver in-spec (no gate-walk,
no safezone), does reg6/reg7 TRACK the input, or hold?

It writes only fwd_input (journaled + reverted at the end, so the register is left as found). It
never touches the field or any circuit. It renders NO verdict -- settle-back law: a register
reading the same proves nothing; the meaning is the owner's. This just tabulates input -> reg.

  python muhl_freeworld_fireprobe.py [n]     # default 16 distinct inputs
"""
import sys, os, json, struct, time, mmap

sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
import pfc_paths as PFCP
TITAN = PFCP.TITAN; REG = PFCP.REG
POWER_WINDOW = 0.02
N = next((int(a) for a in sys.argv[1:] if a.isdigit()), 16)


def probe(off, n):
    with open(TITAN, "rb") as f:
        f.seek(off); return f.read(n)


def u16(b):
    return struct.unpack("<H", (b + b"\x00\x00")[:2])[0]


def power(addr):
    with open(TITAN, "rb") as f:
        m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        end = time.perf_counter() + POWER_WINDOW
        while time.perf_counter() < end:
            _ = m[addr]
        m.close()


def main():
    reg = json.load(open(REG))
    io = int(reg["fwd_input"]["offset"]); rc = int(reg["fwd_receiver"]["offset"])
    ao = int(reg["fwd_answer"]["offset"]); ap = ao + 2

    orig_input = probe(io, 5)                              # capture, restore at the end
    print("  FIRE-PROBE -- in-spec fire (inject fwd_input + power receiver + read reg6/reg7).")
    print("  distinct inputs: %d. no field/circuit touched. fwd_input restored at the end.\n" % N)
    print("    %-5s %-6s %-6s | %-6s %-6s %-10s" % ("op", "A", "B", "reg6", "reg7", "out32"))
    rows = []
    for i in range(N):
        op, A, B = (i & 7), (i * 4099) & 0xFFFF, (i * 271 + 7) & 0xFFFF   # distinct spread
        with open(TITAN, "r+b") as f:
            f.seek(io); f.write(struct.pack("<BHH", op, A, B)); f.flush(); os.fsync(f.fileno())
        power(rc)
        r6 = u16(probe(ao, 2)); r7 = u16(probe(ap, 2))
        out = r6 | (r7 << 16)
        rows.append((op, A, B, r6, r7, out))
        print("    %-5d %-6d %-6d | %-6d %-6d %-10d" % (op, A, B, r6, r7, out))

    # restore fwd_input to exactly what it was
    with open(TITAN, "r+b") as f:
        f.seek(io); f.write(orig_input); f.flush(); os.fsync(f.fileno())

    r6set = sorted({r[3] for r in rows}); r7set = sorted({r[4] for r in rows})
    print("\n  distinct reg6 across %d inputs: %d  -> %s" % (N, len(r6set), r6set[:12]))
    print("  distinct reg7 across %d inputs: %d  -> %s" % (N, len(r7set), r7set[:12]))
    print("  fwd_input restored to original (%s)." % orig_input.hex())
    print("  (numbers only; whether reg6 'tracks' or 'settles back' is the owner's ruling)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
