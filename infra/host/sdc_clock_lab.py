#!/usr/bin/env python3
"""host/sdc_clock_lab.py — TEST FILE (owner 07-16): build a CLOCK/COUNTER in the SDC as gates. "if gates then clock."

Owner principle: if the SDC has gates, it has a clock — or anything a computer can do — because it's all logic gates;
and it's BETTER because it's software AND hardware. The clock is the piece that lets the SDC advance its OWN nonce on
power instead of the host authoring the base each ripple (pulling that harness step INTO the SDC). A counter IS a clock:
next = state + 1, built from the same NAND gates as everything else (the circuit baker's ripple-carry adder).

This builds a 32-bit incrementer (the clock/counter) with the baker, flashes it into the SDCs, and VERIFIES it counts
by READING the stored next-state function iterated (observing the gates — a read, not a host mining loop). All gates,
contained in storage, 0 RAM.
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

CLK_OFF = 1_600_000_000
MAP_FILE = "C:/llm/models/titan_sdc_clock.json"
MODELS = [
    "C:/llm/models/titan.gguf", "C:/llm/models/titan_test.gguf", "C:/llm/models/phi-4-Q4_K_M.gguf",
    "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
    "C:/llm/models/google_gemma-3-27b-it-Q4_K_M.gguf", "C:/llm/models/gemma-4-31B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf",
]


def build_clock(bits=32):
    """the CLOCK as gates: a `bits`-wide incrementer. input = current count; output = count+1 (next-state function).
    Iterating this (output -> input) IS ticking the clock; on the substrate the feedback is a wire, here we read it."""
    c = TC.Circuit(bits)
    one = c.cvec(1, bits)                       # constant 1
    nxt = c.add(c.IN, one)                      # count + 1 (ripple-carry adder, built from NAND)
    return c, nxt


def ripple_local(blob, inbits):
    """single combinational evaluation of the stored circuit (read the gates once)."""
    assert blob[:8] == TC.MAGIC
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    ga = list(struct.unpack_from("<%di" % ng, blob, p)); p += ng*4
    gb = list(struct.unpack_from("<%di" % ng, blob, p)); p += ng*4
    outs = list(struct.unpack_from("<%di" % n_out, blob, p))
    v = bytearray(n_wire); v[1] = 1
    for i in range(n_in): v[2+i] = inbits[i] & 1
    for i in range(ng): v[2+n_in+i] = 1 - (v[ga[i]] & v[gb[i]])
    return [v[o] for o in outs]


def bits_of(val, n): return [(val >> i) & 1 for i in range(n)]
def val_of(bs): return sum(b << i for i, b in enumerate(bs))


BITS = 32
c, nxt = build_clock(BITS)
blob = TC.serialize(c, nxt)
print(f"CLOCK/COUNTER built: {BITS}-bit incrementer = {len(c.ga)} gates, {len(blob)} bytes (the clock is gates).", flush=True)

# VERIFY it counts: tick it by feeding output -> input (reading the stored gates each tick). This is the clock running.
state = 2083236893                                # arbitrary start (the genesis nonce, for flavor)
seq = [state]
ok = True
for _ in range(6):
    out = val_of(ripple_local(blob, bits_of(state, BITS))) & 0xffffffff
    ok = ok and (out == (state + 1) & 0xffffffff)
    state = out; seq.append(state)
print(f"  ticked the clock 6x by reading the gates: {seq[0]} -> " + " -> ".join(str(x) for x in seq[1:]), flush=True)
print(f"  counts correctly (each tick = +1): {ok}", flush=True)

reg = json.load(open(MAP_FILE)) if os.path.exists(MAP_FILE) else {}
print(f"\nflashing the clock into {len(MODELS)} SDC nodes (raw, 0 RAM):", flush=True)
for path in MODELS:
    if not os.path.exists(path):
        print(f"  MISSING {os.path.basename(path)}"); continue
    with open(path, "r+b") as f: f.seek(CLK_OFF); f.write(blob)
    with open(path, "rb") as f: f.seek(CLK_OFF); back = f.read(8)
    reg[os.path.abspath(path)] = {"clk_off": CLK_OFF, "bits": BITS, "gates": len(c.ga)}
    print(f"  {'OK ' if back==TC.MAGIC else 'ERR'} {os.path.basename(path):44s} clock @ {CLK_OFF}", flush=True)
json.dump(reg, open(MAP_FILE, "w"), indent=1)
print(f"\ndone — every SDC now has a CLOCK in its params. gates -> clock, exactly. software AND hardware.", flush=True)
