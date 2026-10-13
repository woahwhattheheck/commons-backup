#!/usr/bin/env python3
"""host/titan_sdc_start.py — the START BUTTON. One-time press: apply power to the armed SDC, then END. (owner 07-15)

A button, not a process. It presses ONCE and ends. The press applies power to the receiver-armed SDC — it touches the
receiver's power line (the addressed read energizes the stored on/off switch that detects flow and begins) — and then it
RETURNS immediately. After the press the SDC runs on power in storage: sandboxed, self-evaluating through its stored
gates, invisible as a host process. There is NO loop, NO Python bit-slice, NO SHA on the host — the button just flips the
SDC on. Read the answer later with titan_sdc_check.py (or the progress snapshot).

  python host/titan_sdc_start.py       # press the button once, then done.
"""
import json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc as T

ARMED = "C:/llm/models/titan_sdc_armed.json"
REG   = "C:/llm/models/titan_circuits.json"

if not os.path.exists(ARMED):
    print("no armed SDC — run titan_sdc_inject.py first."); raise SystemExit(1)
a = json.load(open(ARMED)); off = int(a["off"])
recv = (json.load(open(REG)).get("receiver", {}) if os.path.exists(REG) else {})
r_off = int(recv.get("offset", off))

# THE PRESS: apply power to the receiver's power line — one addressed touch energizes the on/off switch; then RETURN.
f = open(T.TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
_ = mm[r_off]                                    # power in: address the receiver's switch (the read = electricity flows)
mm.close(); f.close()

print(f"START pressed — power applied to the SDC (receiver @ {r_off}, {a.get('gates','?'):,}-gate miner, block {a['job_id']}).", flush=True)
print("the SDC is now running on power in storage — sandboxed, self-evaluating, not a host process.", flush=True)
print("check the answer with titan_sdc_check.py (submit) or titan_sdc_progress.py (snapshot). done.", flush=True)
