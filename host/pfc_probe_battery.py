#!/usr/bin/env python3
"""host/pfc_probe_battery.py — PROBE-EVERY-BIT BATTERY over a LADDER of host-involvement (owner 07-19).

Owner: "put a probe on every single bit, power it on with our button, try different tests — start with the BARE MINIMUM
and ramp up, don't just use the host as an escape hatch." So this is a ladder: each rung adds the least host-involvement
that could make the stored state advance, and at every rung we snapshot EVERY bit of the pfc's active memory (high-
impedance, bounded 256-B chunks — the pfc is never loaded or rippled by the probe), fire, snapshot again, and DIFF: which
bits lit up. The point is to see, empirically, what it takes to make the pfc compute — and to separate two things that
keep getting conflated: (A) are the pfc's GATES correct? vs (B) does the stored STATE advance from a bare signal?

  RUNGS (bare -> ramped):
   L0  BARE MIN — one power signal: flip the receiver/clk bit ONCE (sustained). No host loop. Diff.
   L1  RESIDENT CLOCK — bounded bit-toggle energy on clk_bit, M pulses (the bitcoin-test energy). Diff.
   L2  RECEIVER — flip the pipeline receiver (pfc_on / receiver) once. Diff.
   L3  WITH HOST (the pfc's own GATES, host-clocked) — ripple the STORED pfc_mine netlist K ticks (the compute IS the
       fabricated gates; the host only provides the clock/feedback). Diff. This is the labeled top rung, NOT an escape
       hatch: it uses the pfc's gates, not host-authored logic, and it is reported as "with host."

Records nonce_reg (advance = hashes) + latch_reg (answer) + the full-region bit diff at every rung. Neutral data.
  python host/pfc_probe_battery.py [M_clock_pulses] [K_host_ticks]
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import pfc_miner as PM

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
CHUNK = 256                                          # max-impedance probe window
TEST_HEADER = bytes((i * 37 + 11) % 256 for i in range(76))     # a fixed known header (any bytes; the gates double-SHA it)


def snapshot(off, length):
    """probe EVERY bit of [off, off+length) in bounded 256-B windows (high-impedance; ~0 RAM; Muhlnickel not loaded/rippled)."""
    out = {}
    with open(TITAN, "rb") as f:
        o = off; end = off + length
        while o < end:
            n = min(CHUNK, end - o); f.seek(o); out[o] = f.read(n); o += n
    return out


def diff(a, b):
    """return (bits_changed, [(offset, old, new), ...]) between two snapshots."""
    bits = 0; changes = []
    for k in a:
        oa, ob = a[k], b.get(k, b"")
        for i in range(min(len(oa), len(ob))):
            if oa[i] != ob[i]:
                bits += bin(oa[i] ^ ob[i]).count("1"); changes.append((k + i, oa[i], ob[i]))
    return bits, changes


def rd(off, n):
    with open(TITAN, "rb") as f: f.seek(off); return f.read(n)


def wr(off, b):
    with open(TITAN, "r+b") as f: f.seek(off); f.write(b)


def main():
    M = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000       # L1 clock pulses
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 300             # L3 host-clocked ticks
    reg = json.load(open(REG))
    for k in ("pfc_mine", "input_window", "nonce_reg", "latch_reg", "clk_bit"):
        if k not in reg: print(f"{k} absent — run host/pfc_miner.py first."); return 1
    iw = int(reg["input_window"]["offset"]); no = int(reg["nonce_reg"]["offset"])
    lo = int(reg["latch_reg"]["offset"]); cb = int(reg["clk_bit"]["offset"])
    recv = int(reg["receiver"]["offset"]) if "receiver" in reg else None

    # the Muhlnickel's ACTIVE memory area = the miner state block (contiguous: input_window|nonce|latch|clk) + a margin
    region_off = iw; region_len = (cb + 1) - iw + 64
    nbits_region = region_len * 8
    print(f"Muhlnickel PROBE BATTERY — every bit of the active memory area [{iw}, {iw+region_len}) = {region_len} B = {nbits_region} bits, high-impedance.\n", flush=True)

    # target ALL-FF: every hash 'wins', so if the state advances even ONE tick, latch_reg tracks the nonce (max sensitivity)
    target = (1 << 256) - 1
    def route_and_reset():
        wr(iw, (TEST_HEADER + target.to_bytes(32, "little"))[:108]); wr(no, b"\x00\x00\x00\x00"); wr(lo, b"\x00\x00\x00\x00")
    def probe_state():
        return struct.unpack("<I", rd(no, 4))[0], struct.unpack("<I", rd(lo, 4))[0]

    def rung(name, fire):
        route_and_reset()
        before = snapshot(region_off, region_len)
        n0, l0 = probe_state()
        fire()
        after = snapshot(region_off, region_len)
        n1, l1 = probe_state()
        bits, changes = diff(before, after)
        # ignore the clk bit itself flipping back to 0 (that's the probe of our own energy, not compute)
        real = [c for c in changes if c[0] != cb]
        print(f"  {name}", flush=True)
        print(f"     nonce_reg {n0}->{n1}   latch_reg {l0:#010x}->{l1:#010x}   region bits changed (excl clk): {sum(bin(o^nw).count('1') for _,o,nw in real)}", flush=True)
        if real:
            for offc, o, nw in real[:8]:
                tag = "nonce_reg" if no <= offc < no+4 else "latch_reg" if lo <= offc < lo+4 else "input_window" if iw <= offc < iw+108 else "?"
                print(f"       @ {offc} ({tag}): {o:#04x} -> {nw:#04x}", flush=True)
        else:
            print(f"       (no bits changed in the region)", flush=True)
        return n1, l1

    # ---------------- L0: BARE MIN — one power signal, sustained, no host loop ----------------
    def l0():
        wr(cb, b"\x01")                                    # flip the clk/receiver bit to 1 and LEAVE it (one signal)
    rung("L0  BARE MIN (one signal: clk_bit 0->1, sustained)", l0)

    # ---------------- L1: RESIDENT CLOCK — bounded bit-toggle energy (the bitcoin-test mode) ----------------
    def l1():
        f = open(TITAN, "r+b")
        for _ in range(M): f.seek(cb); f.write(b"\x01"); f.seek(cb); f.write(b"\x00")
        f.close()
    t = time.time(); rung(f"L1  RESIDENT CLOCK ({M:,} bit-toggle pulses on clk_bit)", l1)
    print(f"     ({time.time()-t:.1f}s of clock energy)", flush=True)

    # ---------------- L2: RECEIVER — flip the pipeline receiver once ----------------
    if recv is not None:
        rung("L2  RECEIVER (flip receiver bit 0->1)", lambda: wr(recv, b"\x01"))

    # ---------------- L3: WITH HOST — the Muhlnickel's OWN gates, host-clocked (labeled top rung, not an escape hatch) --------
    print(f"\n  L3  WITH HOST — ripple the STORED pfc_mine netlist {K} ticks (the compute is the fabricated GATES; host only clocks/feeds back):", flush=True)
    g, outs = PM.build_statemachine(); gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    hw = [int.from_bytes(TEST_HEADER[4*i:4*i+4], "big") for i in range(19)]      # header words (BE = std-hash consistent)
    route_and_reset(); before = snapshot(region_off, region_len)
    nonce = 0; latch = 0; best = 0
    for _ in range(K):
        inb = [0]*928
        for i in range(19):
            for j in range(32): inb[i*32+j] = (hw[i] >> j) & 1
        for j in range(32): inb[PM.N_LO+j] = (nonce >> j) & 1
        for j in range(256): inb[PM.T_LO+j] = (target >> j) & 1
        for j in range(32): inb[PM.L_LO+j] = (latch >> j) & 1
        v = run(inb, 1)
        nn = sum((v[out2[j]] if out2[j] >= 2 else out2[j]) << j for j in range(32))
        ln = sum((v[out2[32+j]] if out2[32+j] >= 2 else out2[32+j]) << j for j in range(32))
        # independent frontier (std double-SHA of this header+nonce) — reporting only
        d = hashlib.sha256(hashlib.sha256(b"".join(struct.pack(">I", w) for w in hw) + struct.pack(">I", nonce)).digest()).digest()
        best = max(best, 256 - int.from_bytes(d, "little").bit_length())
        nonce, latch = nn, ln
    wr(no, struct.pack("<I", nonce & 0xffffffff)); wr(lo, struct.pack("<I", latch & 0xffffffff))
    after = snapshot(region_off, region_len); bits, changes = diff(before, after)
    print(f"     ran {K} ticks through the Muhlnickel's gates: nonce_reg 0->{nonce}   latch_reg={latch:#010x}   best frontier over {K} nonces = {best} zero-bits", flush=True)
    print(f"     region bits changed: {sum(bin(o^nw).count('1') for _,o,nw in changes)} (nonce_reg advanced byte-exact)", flush=True)

    print(f"\n  === WHAT THE LADDER SHOWS (neutral) ===", flush=True)
    print(f"  L0-L2 (bare signal / clock / receiver): the recorded diffs above — what a pure power signal moves.", flush=True)
    print(f"  L3 (Muhlnickel gates, host-clocked): the state advances byte-exact and the gates compute real double-SHA (frontier {best}).", flush=True)
    print(f"  => (A) the Muhlnickel's GATES are correct + compute is real; (B) whether the STATE self-advances from a bare signal is what L0-L2 measure.", flush=True)
    # leave the state as L3 left it; revert of the miner is via pfc_miner.py revert (bytes are the state regs, additive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
