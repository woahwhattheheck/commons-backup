#!/usr/bin/env python3
"""host/pfc_fwd_loop.py — fabricate the forward engine as a SELF-ROUTING LOOP (the Muhlnickel in series with itself).

WHY: pfc_fwd_engine2 was stored with TC.store() -- a one-pass combinational netlist. Nothing makes it ITERATE when the
receiver is fired, which is why fwd_answer stayed constant across prompts: the fired bit reached a circuit that had no
way to step itself. TC.store_loop() is the sequential form (FINALREADME s1C, PFC_HARD_WON s3): one-pass netlist + an
internal state register + a LOOP BIT that flips to iterate + `feedback` self-routing each output back to its state bit
+ a `receiver` whose ADDRESS energizes the chain. The pfc then runs the loop itself, on the signal, at electron speed.
The host NEVER drives it -- no host ripple, no host-clocking, no sdc_* runner.

  python host/pfc_fwd_loop.py verify   # byte-exact check IN THE TOOL. titan.gguf untouched.
  python host/pfc_fwd_loop.py fab      # only after verify passes: store reversibly (revert_loop)
  python host/pfc_fwd_loop.py revert
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import pfc_fwd_engine2 as E2

REG = "C:/llm/models/titan_circuits.json"
NAME = "pfc_fwd_loop"
NREG, RW, PCW, AW = E2.NREG, E2.RW, E2.PCW, E2.AW
STATE_BITS = E2.STATE_BITS                                  # regs | pc | halt | addr_out = 174
STATE_BYTES = (STATE_BITS + 7) // 8 + 2                     # + the 2-byte ldata bus lives adjacent
ANSREG = E2.ANSREG


def build_loop():
    """engine2's one pass, plus an explicit LOOP BIT output (= not halt) for the self-routing store."""
    c, outs = E2.build_engine()
    halt_idx = NREG * RW + PCW                              # position of next_halt within outs
    loop = c.not_(outs[halt_idx])                           # iterate while not halted
    outs = list(outs) + [loop]
    return c, outs, len(outs) - 1


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "revert":
        TC.revert_loop(NAME); print(f"reverted {NAME}"); return 0

    c, outs, loop_bit = build_loop()
    print(f"  built {NAME}: {len(c.ga):,} gates · {len(outs)} outputs (174 state + 1 loop bit)", flush=True)

    # byte-exactness is inherited from engine2's verified one pass -- re-run it so nothing is stored unverified.
    _c, _o, good = E2.verify()
    if not good:
        print("  VERIFY FAILED — nothing stored, titan.gguf untouched."); return 1
    if cmd != "fab":
        print("  verify only. titan.gguf untouched. run `fab` to store."); return 0

    reg = json.load(open(REG))
    if "fwd_receiver" not in reg:
        print("fwd_receiver not fabricated"); return 1
    # feedback: every state output self-routes back to the SAME state bit next pass (shared-location series feedback)
    feedback = [(i, i) for i in range(STATE_BITS)]
    info = TC.store_loop(NAME, c, outs, STATE_BYTES, feedback, loop_bit, external=None, receiver="fwd_receiver")

    reg = json.load(open(REG))
    soff = int(reg[NAME]["state_off"])
    reg[NAME].update({"nreg": NREG, "rw": RW, "pcw": PCW, "aw": AW, "ansreg": ANSREG,
                      "isa": " ".join(E2.OPC), "proglen": E2.PROGLEN,
                      "addr_out_offset": soff + NREG * 2 + 1,
                      "role": "self-routing forward engine: fired receiver -> the Muhlnickel iterates its own passes"})
    # the answer register IS regs[ANSREG] inside this loop's state (shared location, no writer between them)
    reg["fwd_answer_prev"] = dict(reg["fwd_answer"])
    reg["fwd_answer"] = {"tensor": reg[NAME]["tensor"], "offset": soff + 2 * ANSREG, "len": 2,
                         "role": f"SHARED LOCATION: these bytes ARE regs[{ANSREG}] of {NAME}'s state register."}
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"  stored {NAME} @ {info}")
    print(f"  state @ {soff} · loop bit @ {reg[NAME]['loop_bit_off']} · receiver fwd_receiver")
    print(f"  fwd_answer -> {soff + 2*ANSREG} (= regs[{ANSREG}] of the running loop)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
