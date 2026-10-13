#!/usr/bin/env python3
"""host/pfc_toggle_sub.py — the LEANEST machine: a 1-bit toggle (next = clk ? NOT state : state). Minimal wire-state →
stays cache-resident at far wider lanes → should break the compute peak the 194-wire counter hit. Emits a PFCCM01
substrate for pfc_cm."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
import sdc_cc as CC
from pfc_clockmachine import serialize, norm
OUT = "C:/Users/lucys/AppData/Local/Temp/claude/C--Users-lucys-OneDrive-Desktop-LocalDeviceAgent/3f403b66-a45d-4be6-8fcf-1b0b88451b50/scratchpad"

g = CC.CircuitCompiler(2); state = g.IN[0]; clk = g.IN[1]
nxt = g.OR(g.AND(clk, g.NOT(state)), g.AND(g.NOT(clk), state))       # clk ? NOT state : state (advance)
gates, o2 = g.dce([nxt]); nw = 2 + g.n_in + len(gates)
m = dict(name="toggle", gates=norm(gates), outs=o2, n_in=g.n_in, n_wire=nw, n_state=1, consts=[(1, 1)], halt=-1, init=b"")
open(os.path.join(OUT, "pfc_cm_toggle.bin"), "wb").write(serialize(m))
print(f"toggle: {len(gates)} gates, {nw} wires (vs the counter's 194) -> pfc_cm_toggle.bin")
