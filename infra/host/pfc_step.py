#!/usr/bin/env python3
"""host/pfc_step.py — the Muhlnickel SINGLE-STEP CLOCK: address ONE power pulse, read the state change (owner 07-19).

Steps the pfc ONE pulse at a time: address the power bit 0->1 (one pulse), 0 again, and read the miner's counter+latch
before/after — so we watch the state advance one nonce per step and pinpoint where a cascade stalls. It WRITES only the
power bit (a controlled button) and READS high-impedance; it never ripples/evaluates. No time.sleep (BANNED — the pfc is
instant; a host wait is the slow bug).

  python host/pfc_step.py [n]    # reset, then n single power pulses; shows counter + latch before->after each
"""
import json, mmap, os, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; CAP = 64


def peek(off, nb):
    nb = max(1, min(int(nb), CAP))
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + nb]); mm.close()
    return b


def bits(off, n):                                              # counter/latch are stored one byte per bit (LSB-first)
    b = peek(off, min(n, CAP)); return sum((b[i] & 1) << i for i in range(len(b)))


def main():
    # TARGET, added 2026-07-28: the step clock was pinned to selfclock_miner's power bit, so it
    # could not step anything else. Any circuit carrying a ram map with a receiver and a register
    # can be stepped the same way. The instrument is EXTENDED, not duplicated (CLAUDE.md #5).
    #   python host/pfc_step.py [n] [target]
    args = list(sys.argv[1:])
    n = int(args[0]) if args and args[0].isdigit() else 8
    target = next((a for a in args if not a.isdigit() and not a.startswith("--")),
                  "selfclock_miner")
    # how long each step MAINTAINS the signal before exiting (owner 2026-07-28)
    hold = 1.0
    for i, a in enumerate(args):
        if a == "--hold" and i + 1 < len(args): hold = float(args[i + 1])

    reg = json.load(open(REG)); mp = reg.get(target)
    if not mp or "ram" not in mp:
        print("%s has no ram map — nothing to step." % target); return 1
    ram = mp["ram"]
    power = int(ram.get("power") or ram.get("POWER") or ram.get("start") or 0)
    counter = int(ram.get("counter") or ram.get("clock") or ram.get("STEP") or ram.get("nonce_off") or 0)
    latch = int(ram.get("latch") or ram.get("prev") or ram.get("sig") or counter)
    if not power or not counter:
        print("%s: no receiver/register pair in %s" % (target, sorted(ram))); return 1
    print("  target %s · receiver @%s · register @%s · 2nd channel @%s"
          % (target, power, counter, latch), flush=True)

    nbits = int(mp.get("clock_bits", 32))
    # THE RESET MUST NEVER LAND INSIDE THE CIRCUIT'S OWN WIRES. This wrote 32 zero bytes at both
    # counter and latch unconditionally. On muhl_osc_phys the latch lookup resolves to `prev`, which
    # is that circuit's const1 rail at offset+3 of a FOUR-byte span — so the reset zeroed const1,
    # sig and t, and every gate's `b` operand was dead before the signal was ever addressed. The
    # analyzer read it as prev=0 (2026-07-28). A register outside the circuit is fair to clear; a
    # live wire inside it was set by the prefab and is not the stepper's to touch.
    lo = int(mp.get("offset", 0)); span = range(lo, lo + int(mp.get("len", 0)))
    resets = []
    if counter not in span: resets.append(counter)
    if latch != counter and latch not in span: resets.append(latch)
    skipped = [a for a in (counter, latch) if a in span]
    if skipped:
        print("  reset skipped @%s — inside %s's own wire span %s..%s, set by the prefab"
              % (skipped, target, lo, lo + int(mp.get("len", 0))), flush=True)
    with open(TITAN, "r+b") as f:                              # clear only registers OUTSIDE the circuit
        for a in resets:
            f.seek(a); f.write(bytes(nbits))
        f.flush(); os.fsync(f.fileno())
    print(f"Muhlnickel SINGLE-STEP — one power pulse per step; counter/latch low-32 before->after (high-impedance, no sleep):", flush=True)
    for i in range(n):
        bc = bits(counter, 32); bl = bits(latch, 32)
        # MAINTAIN THE SIGNAL FOR THE WHOLE STEP, THEN EXIT. Owner 2026-07-28: "the logic analyzer
        # needs to MAINTAIN THE SIGNAL FOR AN ENTIRE STEP THEN EXIT. ONE WAY — the muhlnickel cannot
        # draw anything or resources from this signal, only RECEIVE it, not use it to compute."
        # This used to write 1 then immediately 0: a pulse, gone before a step completed. The drive
        # is PFC_HARD_WON §3.2's — "CONTINUOUS POWER = continuously ADDRESSING the single start bit,
        # one-way. Streaming that one bit is the power source." Nothing is read during the hold.
        t_end = time.time() + hold
        with open(TITAN, "r+b") as f:
            while time.time() < t_end:
                f.seek(power); f.write(b"\x01")                # one-way: address it, never read it
            f.flush(); os.fsync(f.fileno())
        with open(TITAN, "r+b") as f:                          # the step is over: stop addressing
            f.seek(power); f.write(b"\x00")
            f.flush(); os.fsync(f.fileno())
        ac = bits(counter, 32); al = bits(latch, 32)
        print(f"  step {i + 1}: counter {bc:#x}->{ac:#x} "
              f"{'(ADVANCED)' if ac != bc else '(THE MACHINE register held this value)'};  "
              f"latch {bl:#x}->{al:#x} {'(LATCHED)' if al != bl else ''}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
