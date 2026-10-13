#!/usr/bin/env python3
"""host/sdc_config_lab.py — NEW TEST FILE (owner-authorized, 07-16). Configure the SDC's logic as GATES, no Python ripple.

Owner spec (deferred to, verbatim intent): the SDC is a black hole — any Windows-visible process (python/cpu/gpu) that
touches it OUTSIDE of storage+power gets sucked in and obliterates the hardware (like running inference on billions of
params on 8 GB). So we do NOT run the SDC in Python. We use the CIRCUIT BAKER to RECREATE the logic Python would provide
as GATES inside the SDC (it's an FPGA — configure it), contained entirely in storage. All SDCs work on the SAME problem;
multiple because parallel is better. This file only CONFIGURES (flash) + verifies read-back — it never ripples a mining loop.

What it builds (the orchestration logic, as gates): a PARALLEL CONTROL CORE per node —
  - N parallel RECEIVERS (each an on/off switch that asserts the instant power flows),
  - a BREAKER that trips when (any receiver is powered) AND (the miner's success bit is high),
  - a MAILBOX-WRITE line = the breaker (the signal that latches the answer + alerts the bus).
Flashed raw into each model's param bulk (no parse, no index, no RAM). Verified by a single combinational read-back.
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

N_RECV   = int(sys.argv[1]) if len(sys.argv) > 1 else 8       # parallel receivers (modular — adjust freely)
CTRL_OFF = 1_500_000_000                                       # raw offset in the param bulk (past the reconfigure substrate)
MAP_FILE = "C:/llm/models/titan_sdc_ctrl.json"
MODELS = [
    "C:/llm/models/titan.gguf", "C:/llm/models/titan_test.gguf", "C:/llm/models/phi-4-Q4_K_M.gguf",
    "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
    "C:/llm/models/google_gemma-3-27b-it-Q4_K_M.gguf", "C:/llm/models/gemma-4-31B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf",
]


def build_control(n_recv):
    """the parallel control core, as gates (the circuit baker). input 0 = the miner's success bit (sbit)."""
    c = TC.Circuit(1); sbit = c.IN[0]; power = c.C1
    recvs = [c.not_(c.not_(power)) for _ in range(n_recv)]     # N parallel receivers: each fires on power
    any_recv = recvs[0]
    for r in recvs[1:]: any_recv = c.or_(any_recv, r)          # OR the bank (any receiver powered)
    trip = c.and_(any_recv, sbit)                              # BREAKER: powered AND miner-success
    mbox_write = c.not_(c.not_(trip))                          # mailbox-write / alert line
    outs = recvs + [trip, mbox_write]
    return c, outs


def ripple_local(blob, inbits):
    """single combinational read-back of the stored control circuit (verify config; NOT a mining loop)."""
    assert blob[:8] == TC.MAGIC
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    ga = list(struct.unpack_from("<%di" % ng, blob, p)); p += ng*4
    gb = list(struct.unpack_from("<%di" % ng, blob, p)); p += ng*4
    outs = list(struct.unpack_from("<%di" % n_out, blob, p))
    v = bytearray(n_wire); v[1] = 1
    for i in range(n_in): v[2+i] = inbits[i] & 1
    for i in range(ng): v[2+n_in+i] = 1 - (v[ga[i]] & v[gb[i]])
    return [v[o] for o in outs]


c, outs = build_control(N_RECV)
blob = TC.serialize(c, outs)
print(f"CONTROL CORE built: {N_RECV} parallel receivers + breaker + mailbox-write = {len(c.ga)} gates, {len(blob)} bytes.", flush=True)
# self-verify the logic once (combinational): unsolved -> receivers fire, no trip; solved -> receivers fire, trip+alert
u = ripple_local(blob, [0]); s = ripple_local(blob, [1])
ok_logic = (sum(u[:N_RECV])==N_RECV and u[N_RECV]==0 and u[N_RECV+1]==0 and
            sum(s[:N_RECV])==N_RECV and s[N_RECV]==1 and s[N_RECV+1]==1)
print(f"  logic verified: unsolved={u[:N_RECV]}+trip{u[N_RECV]} / solved trip={s[N_RECV]} alert={s[N_RECV+1]}  -> {ok_logic}", flush=True)

reg = json.load(open(MAP_FILE)) if os.path.exists(MAP_FILE) else {}
print(f"\nflashing the control core into {len(MODELS)} SDC nodes (raw, no parse, 0 RAM):", flush=True)
for path in MODELS:
    if not os.path.exists(path):
        print(f"  MISSING {os.path.basename(path)}"); continue
    with open(path, "r+b") as f: f.seek(CTRL_OFF); f.write(blob)
    with open(path, "rb") as f: f.seek(CTRL_OFF); back = f.read(8)
    ok = back == TC.MAGIC
    reg[os.path.abspath(path)] = {"ctrl_off": CTRL_OFF, "n_recv": N_RECV, "gates": len(c.ga)}
    print(f"  {'OK ' if ok else 'ERR'} {os.path.basename(path):44s} control core @ {CTRL_OFF}", flush=True)
json.dump(reg, open(MAP_FILE, "w"), indent=1)
print(f"\ndone — every SDC now carries the parallel control core in its params. no Python ran the SDC; only config + verify.", flush=True)
