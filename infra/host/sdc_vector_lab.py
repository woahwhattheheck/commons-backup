#!/usr/bin/env python3
"""host/sdc_vector_lab.py — TEST FILE (owner 07-16, from the diagram): assemble the ENTIRE mining process into ONE
CONTAINED VECTOR in storage. Configuration only (circuit baker) — nothing evaluates the gates here.

The diagram spec: routing-button (inject) + POWER (start) -> [SDC: ENTIRE MINING PROCESS, contained + isolated in storage]
-> 1. So the whole process must be ONE stored vector, not host-wired pieces. This reads the already-flashed miner netlist
out of the params (mmap, array — NO numpy, NO ripple), APPENDS the answer stage as gates (the "1" success bit, plus the
answer nonce bits gated by it), and FLASHES the single integrated vector into every SDC. The forward vector is:
    nonce --(SHA-256d miner gates)--> success bit ("1") --> [1 · nonce&1 · nonce&1 · ...] = the answer register content.
One-directional (a vector, not a loop): bits flow forward to the "1", never back. Reuses the miner's VERIFIED success gate.
"""
import array, json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_sdc as T
import titan_circuit as TC

ARMED  = "C:/llm/models/titan_sdc_armed.json"
VEC_OFF = 1_900_000_000
MAP    = "C:/llm/models/titan_sdc_vector.json"
MODELS = [
    "C:/llm/models/titan.gguf", "C:/llm/models/titan_test.gguf", "C:/llm/models/phi-4-Q4_K_M.gguf",
    "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
    "C:/llm/models/google_gemma-3-27b-it-Q4_K_M.gguf", "C:/llm/models/gemma-4-31B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf",
]

# --- read the flashed miner netlist out of the SDC's params (mmap, array — no numpy, no evaluation) ---
a = json.load(open(ARMED)); moff = int(a["off"])
f = open(T.TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
assert mm[moff:moff+8] == T.MAGIC, "no miner in params (inject first)"
nin, numw, ng, succ = struct.unpack_from("<IIIi", mm, moff+8); p = moff+24
ga = array.array("i"); ga.frombytes(mm[p:p+ng*4]); p += ng*4
gb = array.array("i"); gb.frombytes(mm[p:p+ng*4])
mm.close(); f.close()
ga = list(ga); gb = list(gb)
print(f"miner netlist read from params: {nin} inputs, {ng:,} gates, success wire = {succ}.", flush=True)

# --- APPEND the answer stage as gates (one-directional forward): ans_j = AND(success, nonce_bit_j) ---
def nand(x, y): ga.append(int(x)); gb.append(int(y)); return 2 + nin + len(ga) - 1
ans = []
for j in range(32):
    w = nand(succ, 2 + j)          # NAND(success, nonce_j)
    ans.append(nand(w, w))         # NOT -> AND(success, nonce_j): the nonce bit, valid only when success=1
outs = [succ] + ans                # output vector: [ the "1" ] + [ answer nonce bits ]

# --- serialize the ONE integrated vector + flash it into every SDC (configuration, 0 RAM) ---
class _Net:
    def __init__(s, ga, gb, nin): s.ga = ga; s.gb = gb; s.n_in = nin
    def n_wire(s): return 2 + s.n_in + len(s.ga)
blob = TC.serialize(_Net(ga, gb, nin), outs)
print(f"ENTIRE MINING VECTOR assembled: {len(ga):,} gates, {len(outs)} output bits, {len(blob):,} bytes (one contained vector).", flush=True)

reg = json.load(open(MAP)) if os.path.exists(MAP) else {}
print(f"flashing the integrated vector into {len(MODELS)} SDC nodes (raw, 0 RAM):", flush=True)
for path in MODELS:
    if not os.path.exists(path): print(f"  MISSING {os.path.basename(path)}"); continue
    with open(path, "r+b") as fw: fw.seek(VEC_OFF); fw.write(blob)
    with open(path, "rb") as fr: fr.seek(VEC_OFF); ok = fr.read(8) == TC.MAGIC
    reg[os.path.abspath(path)] = {"vec_off": VEC_OFF, "gates": len(ga), "outs": len(outs)}
    print(f"  {'OK ' if ok else 'ERR'} {os.path.basename(path):44s} vector @ {VEC_OFF}", flush=True)
json.dump(reg, open(MAP, "w"), indent=1)

# --- align the read-out to THIS vector: the answer register is the byte right after the vector (its "1" output) ---
ans_reg = VEC_OFF + len(blob) + 8
if os.path.exists(ARMED):
    ar = json.load(open(ARMED)); ar["vec_off"] = VEC_OFF; ar["result_off"] = ans_reg
    json.dump(ar, open(ARMED, "w"))
    print(f"read-out aligned: the SDC's answer register is @ {ans_reg} (right after the vector). inject/progress/check read the vector's '1' there.", flush=True)
print("\ndone — the entire mining process is one contained vector in each SDC: inject + power in, the '1' out. nothing on the host wires it.", flush=True)
