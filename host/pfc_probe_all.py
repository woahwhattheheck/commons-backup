#!/usr/bin/env python3
"""host/pfc_probe_all.py — PROBE EVERY BIT IN THE MUHLNICKEL around one signal (owner 07-19).

Owner: "run it again but with probes on every bit in the pfc" — so the answer to 'what did the receiver's gate bit do'
is a matter of record, not memory. This snapshots EVERY bit of the pfc's fabricated span (high-impedance streaming; the
before-image is held on DISK, not RAM, so containment holds ~0 resident), fires the button (flips the receiver 0->1),
then diffs every byte and lists exactly which bits changed anywhere in the pfc — with the receiver's own gate called out.

  python host/pfc_probe_all.py [receiver_name]     # default: phys_chain's receiver (the gate-hooked-to-receiver test)
"""
import hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SNAP = os.environ.get("PFC_SNAP", "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad/pfc_before.bin")
BUF = 1 << 20                                          # 1 MB streaming buffer (bounded => ~0 resident)


def span(reg):
    lo = None; hi = None
    for e in reg.values():
        if isinstance(e, dict) and "offset" in e and "len" in e:
            o = int(e["offset"]); n = int(e["len"])
            lo = o if lo is None else min(lo, o); hi = (o + n) if hi is None else max(hi, o + n)
    return lo, hi


def stream_snapshot(lo, hi):
    with open(TITAN, "rb") as f, open(SNAP, "wb") as g:
        f.seek(lo); left = hi - lo
        while left > 0:
            b = f.read(min(BUF, left))
            if not b: break
            g.write(b); left -= len(b)


def stream_diff(lo, hi):
    """byte-by-byte diff of the on-disk before-image vs the live file; yields (offset, before, after). Bounded RAM."""
    with open(SNAP, "rb") as g, open(TITAN, "rb") as f:
        f.seek(lo); o = lo; left = hi - lo
        while left > 0:
            n = min(BUF, left); ob = g.read(n); nb = f.read(n)
            if not ob or not nb: break
            if ob != nb:
                for i in range(len(ob)):
                    if ob[i] != nb[i]: yield (o + i, ob[i], nb[i])
            o += n; left -= n


def main():
    reg = json.load(open(REG))
    rname = sys.argv[1] if len(sys.argv) > 1 else "phys_chain"
    if rname == "phys_chain":
        if "phys_chain" not in reg: print("phys_chain absent — run host/pfc_physical_gates.py first."); return 1
        pc = reg["phys_chain"]; recv = int(pc["receiver"]); gate_out = int(pc["wires"][1]); const1 = int(pc["const1"])
        # prefab reset: receiver 0, all wires 0, const1 = 1
        with open(TITAN, "r+b") as f:
            for a in pc["wires"]: f.seek(a); f.write(b"\x00")
            f.seek(const1); f.write(b"\x01")
        label = f"phys_chain receiver @ {recv}; its AND-gate output bit is w1 @ {gate_out}"
    else:
        recv = int(reg[rname]["offset"]); gate_out = None; label = f"{rname} @ {recv}"

    lo, hi = span(reg)
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    print(f"Muhlnickel PROBE-ALL — fabricated span [{lo}, {hi}) = {(hi-lo)/1e6:.1f} MB, every bit. signal: flip {label}.\n", flush=True)
    print(f"  snapshotting every bit of the Muhlnickel (to disk, ~0 RAM) …", flush=True)
    stream_snapshot(lo, hi)

    before_recv = None
    with open(TITAN, "rb") as f: f.seek(recv); before_recv = f.read(1)[0]
    with open(TITAN, "r+b") as f: f.seek(recv); f.write(b"\x01")     # THE BUTTON: one electron -> the receiver (0->1)
    after_recv = None
    with open(TITAN, "rb") as f: f.seek(recv); after_recv = f.read(1)[0]
    print(f"  BUTTON fired: receiver byte {before_recv} -> {after_recv}\n", flush=True)

    print(f"  diffing every bit of the Muhlnickel …", flush=True)
    changes = list(stream_diff(lo, hi)); nbits = sum(bin(o ^ n).count("1") for _, o, n in changes)
    print(f"\n  === EVERY-BIT RECORD ===", flush=True)
    print(f"  bytes changed in the ENTIRE Muhlnickel span: {len(changes)}   (total bits flipped: {nbits})", flush=True)
    for off, ob, nb in changes[:40]:
        who = " <- the receiver" if off == recv else (" <- the receiver's AND-gate OUTPUT bit (w1)" if gate_out is not None and off == gate_out else "")
        print(f"     @ {off}: {ob:#04x} -> {nb:#04x}{who}", flush=True)
    if gate_out is not None:
        with open(TITAN, "rb") as f: f.seek(gate_out); gob = f.read(1)[0]
        moved = any(off == gate_out for off, _, _ in changes)
        print(f"\n  THE GATE HOOKED TO THE RECEIVER (w1 @ {gate_out}) reads: {gob}   (changed by the signal: {moved})", flush=True)
    print(f"\n  interpretation is yours — this is the full high-impedance record of every bit the signal moved.", flush=True)
    try: os.remove(SNAP)
    except OSError: pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
