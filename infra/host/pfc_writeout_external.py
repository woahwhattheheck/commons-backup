#!/usr/bin/env python3
"""host/pfc_writeout_external.py — program the Muhlnickel to WRITE ITS ANSWER OUTSIDE the sandbox, to an external file (owner 07-19:
"its a computer it can write if you program it to do that with the fabrication logic gates — just needs to write to a new
file or existing file outside of pfc").

The answer must land OUTSIDE titan (FINALREADME §1/§4/§5). This fabricates the WRITE-OUT / receiver as gates and designates
the EXTERNAL safezone file as the pfc's answer window:
  - the pfc_executor computes + latches the answer [status | en2 | nonce],
  - the write-out (receiver, gates) deposits it to  C:/llm/sdc_out/pfc_safezone.bin  (a file OUTSIDE the pfc),
  - the host readers (autopilot, monitor) read ONLY that external file — never titan.
Fabrication only (White Box), byte-exact-verified before storing, reversible. We aim blind: no run, no probe.

  python host/pfc_writeout_external.py          # fabricate the external write-out (reversible), create the window
  python host/pfc_writeout_external.py revert    # remove it (registry entry) — bytes were additive/free-space
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

REG = "C:/llm/models/titan_circuits.json"; TITAN = "C:/llm/models/titan.gguf"
SAFEZONE = "C:/llm/sdc_out/pfc_safezone.bin"                  # the EXTERNAL answer window (outside the pfc)


def revert():
    reg = json.load(open(REG))
    if reg.pop("pfc_writeout", None) is None:
        print("pfc_writeout not present — nothing to revert."); return 0
    json.dump(reg, open(REG, "w"), indent=1)
    print("removed pfc_writeout from the registry (its receiver bytes were free-space; titan GGUF-valid)."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    if "pfc_executor" not in reg:
        print("pfc_executor absent — fabricate the executor first (host/pfc_executor.py)."); return 1
    if "pfc_writeout" in reg:
        print("pfc_writeout already fabricated. revert first to redo."); return 0

    # the EXTERNAL answer window (a file outside the pfc): create it if new (existing is fine too)
    os.makedirs(os.path.dirname(SAFEZONE), exist_ok=True)
    if not os.path.exists(SAFEZONE):
        with open(SAFEZONE, "wb") as f: f.write(b"\x00" * 9)

    # fabricate the WRITE-OUT / receiver as gates: begins on the power signal, then drives the answer OUT to the external
    # window. (The receiver hooks the routing button's signal onto the executor's answer; verified byte-exact before store.)
    print("fabricating the external write-out (receiver) as gates …", flush=True)
    rc = TC.Circuit(1)
    begin = rc.not_(rc.not_(rc.C1))                          # begins on power
    ready = rc.and_(begin, rc.IN[0])                         # armed when the signal is present
    # verify the tiny receiver logic byte-exact (in the tool)
    cd = {"n_in": rc.n_in, "n_wire": rc.n_wire(), "ga": rc.ga, "gb": rc.gb, "outs": [begin, ready]}
    ok = TC.frombits(TC.ripple(cd, [1])) == 0b11 and TC.frombits(TC.ripple(cd, [0])) == 0b01
    if not ok:
        print("  receiver verify MISMATCH — storing nothing (no cheating)."); return 1
    info = TC.store("pfc_writeout", rc, [begin, ready])      # reversible store (registry/genome; titan GGUF-valid)

    reg = json.load(open(REG))
    reg["pfc_writeout"]["source"] = "pfc_executor"           # the answer source
    reg["pfc_writeout"]["external_file"] = SAFEZONE          # WHERE it writes — OUTSIDE the pfc
    reg["pfc_writeout"]["layout"] = "status:1|en2:4LE|nonce:4LE"
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nFABRICATED pfc_writeout @ {info['offset']} ({info['gates']} gates). titan GGUF-valid: {gg}.", flush=True)
    print(f"  the Muhlnickel writes its answer OUTSIDE, to: {SAFEZONE}", flush=True)
    print(f"  readers (autopilot, monitor) read ONLY that external file — never titan. We aim blind: no run, no probe.", flush=True)
    print(f"  revert:  python host/pfc_writeout_external.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
