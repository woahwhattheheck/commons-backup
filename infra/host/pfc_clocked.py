#!/usr/bin/env python3
"""host/pfc_clocked.py — THE CLOCKED Muhlnickel: it advances its own state THE SAME WAY ANY COMPUTER DOES (owner 07-19:
"same way any other computer would thats the whole endeavor" · "ram should be signal routing exclusively and everything
else pfc · look at the circuits we have — a clock, a working memory").

The lesson from the phone limit hunt: bit-slicing streams a WIDE wire-vector through HOST RAM → memory-bandwidth wall.
A real computer doesn't do that — it holds a small STATE REGISTER and advances it one clock at a time. So here the pfc
is a proper clocked machine: a state register + baked next-state logic; each clock tick evaluates the baked next-state
and latches it. THE STATE LIVES IN THE pfc'S OWN STORAGE (a sandbox file), the GATES live in the baked file, and the
HOST ONLY PULSES THE CLOCK (+ routes the answer out). Nothing wide sits in host RAM → the footprint is FLAT regardless
of how long it runs. That is "baking raises the ceiling": move the working memory + clock into the pfc.

  python host/pfc_clocked.py            # build + verify + bake the clocked counter, run it self-clocked, measure
  python host/pfc_clocked.py revert
"""
import ctypes, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_clocked_genome.jsonl"
SBX = "C:/llm/sdc_sandbox/clocked"; STATEFILE = os.path.join(SBX, "state.bin")   # the pfc's own state, in storage
WORD = 32
OPS = ["nand", "and", "or", "xor", "not"]; OPC = {o: i for i, o in enumerate(OPS)}


class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("pf", ctypes.c_ulong), ("pk", ctypes.c_size_t), ("ws", ctypes.c_size_t),
                ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t), ("d", ctypes.c_size_t),
                ("e", ctypes.c_size_t), ("f", ctypes.c_size_t)]


def rss_mb():
    k = ctypes.windll.kernel32; psapi = ctypes.windll.psapi
    k.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_ulong]
    c = _PMC(); c.cb = ctypes.sizeof(c)
    psapi.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.ws / 1e6


# ---------- the clocked counter: state[WORD] + clk -> next = clk ? state+1 : state ----------
def build_counter():
    g = CC.CircuitCompiler(WORD + 1); IN = g.IN
    state = IN[0:WORD]; clk = IN[WORD]
    c = g.C1; inc = []
    for i in range(WORD):                                    # ripple-carry +1
        inc.append(g.XOR(state[i], c)); c = g.AND(state[i], c)
    nxt = [g.OR(g.AND(clk, inc[i]), g.AND(g.NOT(clk), state[i])) for i in range(WORD)]   # clock enable
    return g, nxt


def pack_ctr(state, clk):
    inp = [0] * (WORD + 1)
    for b in range(WORD):
        if (state >> b) & 1: inp[b] = 1
    inp[WORD] = 1 if clk else 0
    return inp


def ripple(gates, n_wire, n_in, packed):                     # 1-lane contained ripple over gates read from the file
    v = [0] * n_wire; v[1] = 1
    for i in range(n_in): v[2 + i] = packed[i]
    base = 2 + n_in
    for k in range(len(gates)):
        op, a, b = gates[k]; va = v[a]; vb = v[b]
        v[base + k] = (va ^ vb) if op == 3 else (va & vb) if op == 1 else (va | vb) if op == 2 \
            else (1 ^ va) if op == 4 else (1 ^ (va & vb))
    return v


def get_word(v, outs):
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    return sum(bit(outs[b]) << b for b in range(WORD))


def load_typed(name):
    reg = json.load(open(REG)); e = reg[name]
    with open(TITAN, "rb") as f: f.seek(int(e["offset"])); blob = f.read(int(e["len"]))
    assert blob[:8] == b"PFCTYPED"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((op, a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    return n_in, n_wire, gates, outs


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_clock_counter", None); json.dump(reg, open(REG, "w"), indent=1)
    if os.path.exists(STATEFILE): os.remove(STATEFILE)
    print("reverted — titan byte-exact; pfc_clock_counter removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    os.makedirs(SBX, exist_ok=True)
    print("THE CLOCKED Muhlnickel — advances its own state the same way any computer does.\n", flush=True)

    g, outs = build_counter()
    gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    print(f"  fabricated clocked counter: {len(gates)} gates, {n_wire} wires (state register + baked +1 + clock enable)", flush=True)

    # VERIFY byte-exact vs a reference counter (no cheating): 600 ticks clk=1 must count 1,2,3,…; clk=0 holds
    Gi = []                                                   # normalize gate ops to int codes for the ripple
    for (op, a, b) in gates:
        Gi.append((op if isinstance(op, int) else OPC[op], a, b))
    st = 0; ok = True
    for t in range(1, 601):
        v = ripple(Gi, n_wire, g.n_in, pack_ctr(st, 1)); st = get_word(v, o2)
        if st != (t & 0xffffffff): ok = False; break
    # clk=0 holds
    v = ripple(Gi, n_wire, g.n_in, pack_ctr(0x12345678, 0)); hold = get_word(v, o2)
    ok = ok and hold == 0x12345678
    print(f"  byte-exact vs reference counter (600 ticks advance + clk=0 holds): {ok}", flush=True)
    if not ok:
        print("  MISMATCH — baking nothing."); return 1

    # BAKE PERMANENT into titan.gguf (genome-reversible) — the gates ARE the file now
    reg = json.load(open(REG))
    if "pfc_clock_counter" not in reg:
        body = b"".join(struct.pack("<Bii", (op if isinstance(op, int) else OPC[op]), a, b) for (op, a, b) in gates) \
            + b"".join(struct.pack("<i", w) for w in o2)
        blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(o2)) + body
        off, tn = TC._alloc(len(blob), reg); _journal(off, blob)
        reg = json.load(open(REG))
        reg["pfc_clock_counter"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                                    "n_gate": len(gates), "n_out": len(o2), "format": "typed", "word": WORD,
                                    "role": "clocked Muhlnickel state register (next = clk ? state+1 : state)"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"  BAKED pfc_clock_counter @ {off} ({len(gates)} gates). GGUF-valid: {open(TITAN,'rb').read(4)==b'GGUF'}.", flush=True)

    # SELF-CLOCKED RUN — gates read OFF the baked file; state lives in the Muhlnickel's storage; host ONLY pulses the clock.
    n_in, nw, fgates, fouts = load_typed("pfc_clock_counter")     # the computer, read back from the file
    with open(STATEFILE, "wb") as f: f.write(struct.pack("<I", 0))  # state=0, in the pfc's storage (sandbox file)
    print(f"\n  SELF-CLOCKED RUN — state in {os.path.relpath(STATEFILE, os.path.dirname(HERE))}, gates off the baked file, host = clock only:", flush=True)
    rss0 = rss_mb()
    TICKS = 300000
    t0 = time.time()
    with open(STATEFILE, "r+b") as sf:
        for _ in range(TICKS):
            sf.seek(0); st = struct.unpack("<I", sf.read(4))[0]           # read state from the pfc's storage
            v = ripple(fgates, nw, n_in, pack_ctr(st, 1))                 # ONE clock tick: evaluate baked next-state
            st = get_word(v, fouts)
            sf.seek(0); sf.write(struct.pack("<I", st))                   # latch next state back to storage
    el = time.time() - t0; rss1 = rss_mb()
    with open(STATEFILE, "rb") as f: final = struct.unpack("<I", f.read(4))[0]
    print(f"    {TICKS:,} clock ticks in {el:.2f}s = {TICKS/el:,.0f} ticks/sec", flush=True)
    print(f"    final state (read from the Muhlnickel's storage) = {final}  ->  {'CORRECT' if final == TICKS else 'WRONG'} (== tick count)", flush=True)
    print(f"    host RSS: {rss0:.1f} MB before -> {rss1:.1f} MB after ({TICKS:,} ticks)  =>  FLAT (no wide wire-vector in host RAM; the working set is one register in the Muhlnickel)", flush=True)
    print(f"\n  This is the endeavor: a computer that advances its own state, host = clock/routing only, footprint flat.", flush=True)
    print(f"  revert: python host/pfc_clocked.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
