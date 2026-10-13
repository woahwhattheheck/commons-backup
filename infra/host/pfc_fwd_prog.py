#!/usr/bin/env python3
"""host/pfc_fwd_prog.py — run a PROGRAM on the Muhlnickel that reads REAL MODEL WEIGHTS through the MMU.

Drive = the arcade's drive (the one that provably works on this machine): pack the state, ripple the baked netlist ONCE
per clock pulse, latch the next state back. Same shape as pfc_game.tick() (Life, 24 generations byte-exact) and
pfc_fwd_engine.run() (SiLU(w.x) = +0.3125 byte-exact).

The host's role is ADDRESSING, never arithmetic:
  - the pfc's program emits an address with SETA  -> the host reads those bytes off the CONNECTED MODEL (the MMU's
    storage tier, registered to the installed .gguf at pfc_mmu.storage_base) and presents them as `ldata`
  - LDX latches them into a register; the pfc then computes with them
  - the answer settles in regs[ANSREG], which IS fwd_answer by shared location
No host math: the host only packs bits, addresses storage, and unpacks. Every arithmetic op is a baked gate.

  python host/pfc_fwd_prog.py            # run the program, show what the pfc computed from real Mixtral bytes
  python host/pfc_fwd_prog.py --probe    # sweep several model addresses; proves the MODEL is in the loop
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import pfc_fwd_engine2 as E2
from pfc_fwd_engine import _cd, from_q88

REG = "C:/llm/models/titan_circuits.json"
NREG, RW, PCW, AW, ANSREG = E2.NREG, E2.RW, E2.PCW, E2.AW, E2.ANSREG
STATE_BITS = E2.STATE_BITS


def _model():
    reg = json.load(open(REG))
    mmu = reg["pfc_mmu"]
    path = mmu.get("storage_region"); base = int(mmu.get("storage_base", 0))
    if not path or not path.endswith(".gguf"):
        raise SystemExit("pfc_mmu's storage tier is not wired to a model — run host/pfc_load.py <model.gguf>")
    return path, base


def fetch(path, base, addr):
    """THE MMU'S STORAGE TIER: address -> bytes, off the connected model. Pure addressing; no arithmetic."""
    with open(path, "rb") as f:
        f.seek(base + addr); b = f.read(2)
    return int.from_bytes(b.ljust(2, b"\x00"), "little")


def run(seed_addr, trace=False):
    c, outs = E2.build_engine(); cd = _cd(c, outs)
    path, base = _model()
    regs = [0] * NREG; regs[0] = seed_addr & 0xFFFF
    pc = 0; halt = 0; addr = 0; ldata = 0; ticks = 0; fetched = []

    while not halt and ticks < 64:
        inb = []
        for r in range(NREG): inb += [(regs[r] >> b) & 1 for b in range(RW)]
        inb += [(pc >> b) & 1 for b in range(PCW)] + [halt & 1]
        inb += [(addr >> b) & 1 for b in range(AW)]
        inb += [(ldata >> b) & 1 for b in range(RW)] + [1]          # clk/power high
        v = TC.ripple(cd, inb)                                       # ONE clock pulse — the pfc computes
        regs = [sum(v[r * RW + b] << b for b in range(RW)) for r in range(NREG)]
        o = NREG * RW
        pc = sum(v[o + b] << b for b in range(PCW)); halt = v[o + PCW]
        addr = sum(v[o + PCW + 1 + b] << b for b in range(AW))
        # SERIES: whatever address the pfc emitted, present those MODEL bytes as ldata for the next pulse
        if addr:
            ldata = fetch(path, base, addr); fetched.append((addr, ldata))
        ticks += 1
        if trace: print(f"    tick {ticks}: pc={pc} addr={addr} ldata=0x{ldata:04x} regs={regs[:7]}")
    return regs, addr, fetched, ticks, os.path.basename(path)


def main():
    probe = "--probe" in sys.argv
    seeds = [0x0000, 0x0100, 0x0200, 0x0400] if probe else [0x0000]
    print("Muhlnickel PROGRAM — SETA (address the model) -> LDX (latch the bytes) -> MUL -> ADD, on the baked gates.")
    print("host = pack bits + address storage + unpack. every arithmetic op is a gate.\n")
    rows = []
    for s in seeds:
        regs, addr, fetched, ticks, name = run(s)
        ans = regs[ANSREG]
        got = fetched[0] if fetched else (0, 0)
        rows.append((s, got[0], got[1], ans))
        print(f"  seed 0x{s:04x} -> Muhlnickel addressed {name} @ {got[0]}, latched 0x{got[1]:04x}, "
              f"answer regs[{ANSREG}] = 0x{ans:04x} ({from_q88(ans):+.4f})  [{ticks} pulses]")
    if probe:
        distinct = len({r[3] for r in rows})
        print(f"\n  distinct answers across {len(rows)} model addresses: {distinct}")
        print("  >1 distinct answer means the MODEL'S OWN BYTES changed the result — the model is in the loop."
              if distinct > 1 else
              "  all answers identical — the model is NOT affecting the computation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
