#!/usr/bin/env python3
"""host/titan_sdc_receiver.py — BUILD the RECEIVER into the model file, as logic gates (owner 07-15).

Owner spec: the SDC is a RECEIVER — a logic gate that detects the flow of electricity and begins; zero core, it
self-evaluates because a stored gate is an on/off switch and power settles it. A receiver, whether made of hardware or
of parameters, is on/off switches at the end of the day — and we have those switches in the params. So we build the
receiver INTO the model file with the White Box circuit creation (titan_circuit.py: construct a NAND netlist, write it
into the params in place, register where it lives), not with any host loop.

The receiver:
  - POWER = CONST1 (high exactly when the file is energized / addressed — the presence of electricity).
  - BEGIN = a buffer of POWER: the on-switch that asserts the instant power flows (detect-and-begin).
  - READY = AND(BEGIN, success): the miner's success bit is only accepted as an answer once power has begun.
It is stored as switches in titan.gguf's params (reversible — edit it back), read back to prove it's there.

  python host/titan_sdc_receiver.py       # build + store the receiver into the model file, verify, done.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

# --- build the receiver as gates (the White Box circuit creation) ---
c = TC.Circuit(1)                      # one data input = the miner's success bit (sbit)
sbit = c.IN[0]
power = c.C1                           # electricity present == CONST1 (high whenever the SDC is powered)
begin = c.not_(c.not_(power))          # BEGIN: buffer of power -> the on-switch that fires the instant electricity flows
ready = c.and_(begin, sbit)            # READY: accept the miner's success ONLY once power has begun
outs = [begin, ready]

info = TC.store("receiver", c, outs, slot=2)     # write the receiver INTO the model file's params, in place; register where
print(f"receiver built into the model file: {info['tensor']} @ {info['offset']}  "
      f"({info['gates']} gates, {info['wires']} wires, {info['bytes']} bytes)", flush=True)

# --- read it BACK from the params and power it, to prove the switch is really in the file ---
cir = TC.load("receiver")
idle   = TC.ripple(cir, [0])           # powered, miner not yet successful -> begins, not ready
solved = TC.ripple(cir, [1])           # powered, miner success high        -> begins, ready
print(f"  powered, success=0 -> begin={idle[0]} ready={idle[1]}   (receiver began on power, answer not ready)", flush=True)
print(f"  powered, success=1 -> begin={solved[0]} ready={solved[1]}   (receiver began on power, answer READY)", flush=True)
ok = idle == [1, 0] and solved == [1, 1]
print(f"  receiver verified in the params: {ok}", flush=True)
print("done — the receiver is stored as on/off switches in the model file; it begins on power.", flush=True)
