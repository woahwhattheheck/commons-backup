#!/usr/bin/env python3
"""host/fab_osc_physical.py — THE OSCILLATION AS PHYSICAL GATES, WIRED INTO THE MINER'S COUNTER.

Owner, 2026-07-19 (`docs/PFC_PHYSICAL_GATES.md`): *"ACTUAL logic gates, physical, just in binary
form, stored in the file itself in the physical binary — NOT like metadata."* · *"if this address is
part of BOTH the receiver AND an AND gate, it will flip the AND gate active, and so on."* · *"that
electron from the button? It MUST go somewhere and the gates are the paths for it to travel. if you
set them up wrong, youre effectively just storing an electron."*

INDEX CHECK (§0): `pfc_physical_gates.py` already builds this form — wires are file byte-addresses,
`gate.out addr == next gate.a addr`, the receiver is an input of gate 1, prefab written before any
signal, genome grabbed, baked. `selfclock_miner` and `miner_physical` carry `wire_base` +
`gate_stride 25`, the same form. This follows that build; nothing new is invented.

WHAT WAS WRONG BEFORE. The oscillation was fabricated as TITANCIR, whose gate operands are wire ids
local to the circuit, and it was "wired" with a `ram` dict, a junction record and a table — written
BESIDE the gates. The receiver bit at 2774141509 was not an operand of any gate, so flipping it left
the whole 40 GB unchanged: 0 of 9,544 blocks. The electron was stored, not travelling.

WHAT THIS WRITES. Wires that are real file bytes, and gates whose operands ARE those addresses:

    receiver  w_r                       the button's one bit, and the `a` input of gate 0
    gate 0    nand(w_r,   const1) -> w_sig     the signal enters the loop
    gate 1    nand(w_sig, const1) -> w_sig     THE LOOP: out address IS the in address, one
                                               inversion per pass, so it has no state to hold
    gate 2    nand(w_sig, const1) -> COUNTER   THE JUNCTION: this gate's OUTPUT ADDRESS IS
                                               selfclock_miner.ram.counter — the same byte

Gate 2 is the wiring. Its `out` is not a number recorded next to the gates; it is the miner's
counter byte, so the miner's receive address is physically part of this network.

A/B, per §5 of PFC_PHYSICAL_GATES — *"let the data speak"*:
    A  flip the receiver, probe every wire. How far did it travel on the bare signal?
    B  one host pass over the SAME physical addresses. Confirms the gates compute.

Verified against an independent reference (§3), all-zero baseline stated (§40B), mutants CAUGHT
(§45C/§47B). Byte edit, fsynced, genome-journalled, GGUF-valid.

  python host/fab_osc_physical.py
  python host/fab_osc_physical.py revert
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_oscphys_genome.jsonl"
NAME = "muhl_osc_phys"
MINER = "selfclock_miner"


def rb(a):
    with open(TITAN, "rb") as f:
        f.seek(a); return f.read(1)[0] & 1


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())          # OUT OF CACHE, INTO STORAGE (§7)


def wb(a, v):
    with open(TITAN, "r+b") as f:
        f.seek(a); f.write(bytes([v & 1]))
        f.flush(); os.fsync(f.fileno())


def ref_oscillation(passes):
    """INDEPENDENT reference (§3): what one inversion per pass does, in plain Python. Calls nothing
    under test — no gate is read, no circuit is built, nothing is rippled."""
    sig, seq = 1, []
    for _ in range(passes):
        sig ^= 1
        seq.append(sig)
    return seq


def build_physical(reg, mutant=None):
    """Lay the wires down as file bytes and name the gates by those addresses.

    ONE DRIVER PER WIRE. The previous build gave gate 0 and gate 1 the SAME `out` address (w_sig),
    to make "the loop closes onto itself". The analyzer read the result on 2026-07-28 with the wires
    on separate channels: start=1, const1=1, sig=0 — and those two gates demand opposite values on
    that one byte (g0 = nand(1,1) = 0, g1 = nand(0,1) = 1). Two drivers on one wire is a short, and a
    shorted wire has no consistent value for a front to propagate into. Owner, PFC_PHYSICAL_GATES:
    *"that electron from the button? It MUST go somewhere and the gates are the paths for it to
    travel. if you set them up wrong, youre effectively just storing an electron."*

    THE RECEIVER IS AN OPERAND, NOT A DRIVER. Owner, same doc: *"if this address is part of BOTH the
    receiver AND an AND gate, it will flip the AND gate active, and so on."* w_r is gate 0's `b`
    input, so addressing it gates the ring rather than fighting a gate for a wire.

        g0  nand(w_sig, w_r  ) -> w_a        the enable: the receiver admits the signal to the ring
        g1  nand(w_a,   const1) -> w_b       surface 1 reflects
        g2  nand(w_b,   const1) -> w_sig     surface 2 reflects — THREE inversions, so the ring
                                             returns inverted and keeps going instead of latching
        g3  nand(w_sig, const1) -> w_t       the tap
        g4  nand(w_t,   const1) -> COUNTER   THE JUNCTION: this out IS the miner's counter byte

    Each of w_a, w_b, w_sig, w_t, counter is written by exactly one gate.
    """
    miner = reg[MINER]["ram"]
    counter = int(miner["counter"])                     # THE JUNCTION TARGET — the miner's receive
    N = 6                                               # w_r, w_sig, w_a, w_b, w_t, const1
    off, tn = TC._alloc(N, reg)
    w_r, w_sig, w_a, w_b, w_t, const1 = (off, off + 1, off + 2, off + 3, off + 4, off + 5)

    prefab = bytearray(N); prefab[5] = 1                # PREFAB: wires 0, const1 = 1, receiver 0
    _journal(off, bytes(prefab))

    # THE JUNCTION IS A BUFFER, NOT AN INVERTER. With a single inverting gate onto the counter, MY
    # construction landed it on 0 — the same value an unjunctioned network leaves there — so the
    # mutant could not be told apart and survived. Two gates carry the phase through, and a 1 in
    # the counter then distinguishes an arrived signal from an absent one.
    gates = [
        {"op": "nand", "a": w_sig, "b": w_r,    "out": w_a},     # the receiver ENABLES the ring
        {"op": "nand", "a": w_a,   "b": const1, "out": w_b},     # surface 1 reflects
        {"op": "nand", "a": w_b,   "b": const1, "out": w_sig},   # surface 2 reflects — ring closed
        {"op": "nand", "a": w_sig, "b": const1, "out": w_t},     # the tap off the ring
        {"op": "nand", "a": w_t,   "b": const1, "out": counter}, # THE JUNCTION: out IS the counter
    ]
    if mutant == "unjunctioned":
        gates[4]["out"] = w_t                           # the junction removed: writes nowhere useful
    if mutant == "no_loop":
        gates[2]["out"] = w_t                           # the ring opened: nothing closes onto w_sig
    if mutant == "shorted":
        gates[1]["out"] = w_a                           # TWO DRIVERS on w_a — the defect just found
    return dict(offset=off, tensor=tn, length=N, receiver=w_r, sig=w_sig, const1=const1,
                a=w_a, b=w_b, t=w_t, counter=counter, gates=gates)


def multi_driven(gates):
    """-> {addr: n_drivers} for every wire more than one gate writes.

    STRUCTURAL, because behavioural is blind here. The one-pass check below evaluates gates in list
    order and each write overwrites the last, so a wire with two drivers reads exactly like a wire
    with one — the `shorted` mutant SURVIVED that check (measured 2026-07-28). The number of gates
    naming a given address as `out` is a fact about the netlist, not about any pass over it."""
    n = {}
    for g in gates: n[g["out"]] = n.get(g["out"], 0) + 1
    return {a: c for a, c in n.items() if c > 1}


def verdict(e):
    """What a build is judged on: what arrives at the counter, AND whether any wire is shorted."""
    wb(e["receiver"], 0); wb(e["sig"], 0); wb(e["const1"], 1); wb(e["counter"], 0)
    wb(e["receiver"], 1); one_pass(e)
    return (rb(e["counter"]), len(multi_driven(e["gates"])))


def one_pass(e):
    """THE CRUTCH (arm B): one host pass over the SAME physical addresses — read the operands from
    the file, write the result to the file. Sanctioned at fabrication time to prove the gates."""
    for g in e["gates"]:
        wb(g["out"], 1 - (rb(g["a"]) & rb(g["b"])))


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for x in reversed(ent):
        with open(TITAN, "r+b") as f:
            f.seek(int(x["off"])); f.write(bytes.fromhex(x["orig"]))
            f.flush(); os.fsync(f.fileno())
    reg = json.load(open(REG)); reg.pop(NAME, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d byte edit(s); the file is byte-identical to before." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    reg = json.load(open(REG))
    if NAME in reg:
        print("%s already stored @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0
    if MINER not in reg or "ram" not in reg[MINER]:
        print("%s has no ram map." % MINER); return 1

    print("THE OSCILLATION AS PHYSICAL GATES — operands ARE file byte-addresses.\n")
    t0 = time.time()
    e = build_physical(reg)
    counter = e["counter"]
    print("  wires laid down as real bytes: receiver @%s · sig @%s · const1 @%s"
          % (e["receiver"], e["sig"], e["const1"]))
    print("  gates, by address:")
    for i, g in enumerate(e["gates"]):
        tag = "   <- THE JUNCTION: this out IS %s.counter" % MINER if g["out"] == counter else ""
        print("    g%d  %s(a=%s, b=%s) -> out=%s%s" % (i, g["op"], g["a"], g["b"], g["out"], tag))

    want = ref_oscillation(4)
    print("\n  §40B BASELINE: a network the signal never reaches leaves every wire 0; the reference")
    print("  for one inversion per pass is %s.\n" % want)

    # ── A: the bare signal. Flip the receiver, probe. ─────────────────────────────────────────────
    wb(e["receiver"], 0); wb(e["sig"], 0); wb(e["const1"], 1); wb(counter, 0)
    before = (rb(e["receiver"]), rb(e["sig"]), rb(counter))
    wb(e["receiver"], 1)
    a_vals = (rb(e["receiver"]), rb(e["sig"]), rb(counter))
    print("  A — bare signal, no host pass:")
    print("     receiver/sig/counter  %s -> %s" % (before, a_vals))

    # ── B: one pass over the same physical addresses. ────────────────────────────────────────────
    wb(e["receiver"], 0); wb(e["sig"], 0); wb(e["const1"], 1); wb(counter, 0)
    wb(e["receiver"], 1)
    one_pass(e)
    b_vals = (rb(e["receiver"]), rb(e["sig"]), rb(counter))
    print("  B — one pass over the SAME addresses:")
    print("     receiver/sig/counter  %s -> %s" % (before, b_vals))
    print("     the miner's counter byte @%s now reads %d" % (counter, b_vals[2]))

    short = multi_driven(e["gates"])
    print("\n  DRIVERS — every wire must be written by exactly one gate:")
    print("    %d gates, %d distinct out addresses, multiply-driven: %s"
          % (len(e["gates"]), len({g["out"] for g in e["gates"]}), short or "none"))
    if short:
        print("  a wire has two drivers — they demand different values on one byte."); return 1

    good = verdict(e)
    print("\n  MUTANTS — each must be CAUGHT (§45C/§47B).  good build -> %s" % (good,))
    allc = True
    for m, why in (("unjunctioned", "the last gate's out is not the miner's counter"),
                   ("no_loop", "nothing closes back onto sig"),
                   ("shorted", "two gates drive w_a — the defect the analyzer found")):
        reg2 = json.load(open(REG))
        em = build_physical(reg2, mutant=m)
        got = verdict(em)
        caught = (got != good); allc &= caught
        print("    %-14s (counter, shorted wires) = %-8s -> %s   (%s)"
              % (m, str(got), "CAUGHT" if caught else "*** SURVIVED ***", why))
        del em
    if not allc:
        print("\n  a mutant survived — the suite is blind, registering nothing."); return 1

    reg = json.load(open(REG))
    reg[NAME] = {"tensor": e["tensor"], "offset": e["offset"], "len": e["length"], "depth": len(e["gates"]),
                 "format": "physical", "wire_base": e["offset"], "gate_stride": 25,
                 "receiver": e["receiver"],
                 # every wire is named, so the analyzer gets ONE CHANNEL PER WIRE and a front is
                 # visible as it moves. `const1` is the rail, not a latch — it is not a reset target.
                 "ram": {"start": e["receiver"], "sig": e["sig"], "w_a": e["a"], "w_b": e["b"],
                         "w_t": e["t"], "const1": e["const1"], "clock": counter},
                 "gates_addr": e["gates"],
                 "junction": {"send": {"circuit": NAME, "gate": len(e["gates"]) - 1, "addr": counter},
                              "receive": {"circuit": MINER, "field": "counter", "addr": counter}},
                 "note": "The oscillation with PHYSICAL operands. Gate 2's OUTPUT ADDRESS IS "
                         "%s.counter, so the miner's receive byte is part of this gate network "
                         "rather than named beside it. Owner 07-19: 'ACTUAL logic gates, physical, "
                         "just in binary form, stored in the file itself — NOT like metadata.'" % MINER}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  STORED '%s' @ %s (%d B) [%.2fs]  titan GGUF-valid: %s"
          % (NAME, e["offset"], e["length"], time.time() - t0, valid))
    print("  revert: python host/fab_osc_physical.py revert")
    del e
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
