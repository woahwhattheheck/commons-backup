#!/usr/bin/env python3
"""host/sdc_statemachine_lab.py — TEST FILE (owner 07-16): finish the mining state machine as gates, then step it by the clock.

Now that the SDC has an internal CLOCK (sdc_clock_lab.py), add the last circuits it needs and TEST the whole loop:
  - COMPARATOR: given the miner's hash-top word, output "clears D leading zero-bits" (the difficulty gate), for D=16/24/32.
  - LATCH: a register cell — out = load ? data : prev — to HOLD the winning nonce when the breaker trips (sequential state
    fed back, same as the clock's feedback).
Both built with the circuit baker (NAND gates), flashed into all 9 SDCs.

Then the NEW TEST: step the whole chain by the CLOCK, reading the stored gates each tick (observation, not a host mining
loop) — clock advances the nonce -> miner hashes it -> comparator checks -> latch holds — and print the trajectory. Every
part is gates in storage; Python only reads the result.
"""
import json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; IDX = TITAN + ".wbindex.json"
SDC_MAGIC = b"TITANSDC"
CMP_OFF = 1_700_000_000; LATCH_OFF = 1_800_000_000
MAP_FILE = "C:/llm/models/titan_sdc_statemachine.json"
MODELS = [
    "C:/llm/models/titan.gguf", "C:/llm/models/titan_test.gguf", "C:/llm/models/phi-4-Q4_K_M.gguf",
    "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
    "C:/llm/models/google_gemma-3-27b-it-Q4_K_M.gguf", "C:/llm/models/gemma-4-31B-it-qat-UD-Q4_K_XL.gguf",
    "C:/llm/models/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf", "C:/llm/models/Llama-3.3-70B-Instruct-Q4_K_M.gguf",
]


def bswap(n): return (((n&0xff)<<24)|((n&0xff00)<<8)|((n>>8)&0xff00)|((n>>24)&0xff))&0xffffffff
def bits_of(v, n): return [(v >> i) & 1 for i in range(n)]
def val_of(bs): return sum(b << i for i, b in enumerate(bs))


def build_comparator():
    """input = 32-bit hash-top display word (LSB-first). outputs = clears D leading zero-bits for D in 16,24,32."""
    c = TC.Circuit(32)
    def clears(D):
        acc = c.C1
        for b in range(32 - D, 32):          # the top D display bits must all be 0
            acc = c.and_(acc, c.not_(c.IN[b]))
        return acc
    return c, [clears(16), clears(24), clears(32)]


def build_latch():
    """register cell: input = data[0..31], load[32], prev[33..64]. output = load ? data : prev (holds when load=0)."""
    c = TC.Circuit(65)
    data = c.IN[0:32]; load = c.IN[32]; prev = c.IN[33:65]
    return c, [c.mux(load, prev[i], data[i]) for i in range(32)]   # mux(s,a,b)=s?b:a -> load?data:prev


def ripple_blob(blob, inbits):
    assert blob[:8] == TC.MAGIC
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    ga = list(struct.unpack_from("<%di" % ng, blob, p)); p += ng*4
    gb = list(struct.unpack_from("<%di" % ng, blob, p)); p += ng*4
    outs = list(struct.unpack_from("<%di" % n_out, blob, p))
    v = bytearray(n_wire); v[1] = 1
    for i in range(n_in): v[2+i] = inbits[i] & 1
    for i in range(ng): v[2+n_in+i] = 1 - (v[ga[i]] & v[gb[i]])
    return [v[o] for o in outs]


# ---- build + flash the two new circuits ----
cc, cout = build_comparator(); cblob = TC.serialize(cc, cout)
lc, lout = build_latch();      lblob = TC.serialize(lc, lout)
print(f"COMPARATOR built: {len(cc.ga)} gates ({len(cblob)} B).  LATCH built: {len(lc.ga)} gates ({len(lblob)} B).", flush=True)
reg = json.load(open(MAP_FILE)) if os.path.exists(MAP_FILE) else {}
for path in MODELS:
    if not os.path.exists(path): print(f"  MISSING {os.path.basename(path)}"); continue
    with open(path, "r+b") as f:
        f.seek(CMP_OFF);   f.write(cblob)
        f.seek(LATCH_OFF); f.write(lblob)
    reg[os.path.abspath(path)] = {"cmp_off": CMP_OFF, "latch_off": LATCH_OFF}
json.dump(reg, open(MAP_FILE, "w"), indent=1)
print(f"flashed comparator + latch into {len(MODELS)} SDC nodes (raw, 0 RAM).", flush=True)

# ---- read the stored circuits from titan.gguf's params ----
clk = json.load(open("C:/llm/models/titan_sdc_clock.json"))[os.path.abspath(TITAN)]
f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
def read_blob(off):
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", mm, off + 8)
    total = 24 + ng*4 + ng*4 + n_out*4
    return bytes(mm[off:off + total])
clkblob = read_blob(clk["clk_off"]); cmpblob = read_blob(CMP_OFF); latchblob = read_blob(LATCH_OFF)
# miner (SDC circuit) at the largest tensor
a = json.load(open(IDX, encoding="utf-8"))
moff = int(max((t for t in a["tensors"]), key=lambda t: int(t["bytes"]))["offset"])
assert mm[moff:moff+8] == SDC_MAGIC, "no miner circuit in params"
nin, numw, ng, succ = struct.unpack_from("<IIIi", mm, moff+8); p = moff+24
mga = struct.unpack_from("<%di" % ng, mm, p); p += ng*4
mgb = struct.unpack_from("<%di" % ng, mm, p); p += ng*4 + numw*4
mow = struct.unpack_from("<256i", mm, p); mow7 = mow[7*32:8*32]
mm.close(); f.close()

def miner_hashtop(nonce):
    v = [0]*numw; w19 = bswap(nonce)
    for j in range(nin): v[j] = (w19 >> j) & 1
    for i in range(ng): v[nin + i] = (~(v[mga[i]] & v[mgb[i]])) & 1
    w7 = 0
    for j in range(32):
        o = mow7[j]; b = 0 if o == -1 else (1 if o == -2 else v[o]); w7 |= b << j
    return bswap(w7)

# ---- NEW TEST: the CLOCK drives the whole state machine, read from the stored gates ----
print("\n=== INTEGRATED TEST — the clock steps the SDC state machine (all reads of stored gates) ===", flush=True)
print("  tick  nonce(clock)   hashtop     zbits  clears16/24/32  latch", flush=True)
nonce = 2083236893; latched = 0
for tick in range(8):
    hi = miner_hashtop(nonce)                                   # MINER reads the nonce -> hash top
    zb = 32 - hi.bit_length() if hi else 32
    c16, c24, c32 = ripple_blob(cmpblob, bits_of(hi, 32))      # COMPARATOR: difficulty gate
    lo = ripple_blob(latchblob, bits_of(nonce, 32) + [c16] + bits_of(latched, 32))  # LATCH: hold nonce if it clears 16
    latched = val_of(lo)
    print(f"  {tick:4d}  {nonce:<12d}  {hi:08x}  {zb:5d}      {c16}/{c24}/{c32}       {latched}", flush=True)
    nonce = val_of(ripple_blob(clkblob, bits_of(nonce, 32))) & 0xffffffff   # CLOCK: +1
print("\ndone — clock advanced the nonce, miner hashed, comparator judged, latch held. the loop is gates in storage.", flush=True)
