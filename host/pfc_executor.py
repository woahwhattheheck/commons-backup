#!/usr/bin/env python3
"""host/pfc_executor.py — FABRICATE the mining EXECUTOR as a Muhlnickel circuit (owner 07-19).

The owner's spec removed the executor as a PROCESS; it comes back as a pfc CIRCUIT, built from scratch with the
fabrication tool. This is the per-signal mining logic, wired as ONE gate-net:
    header words (routed in) + nonce (from the clock) + group/en2 + target
        -> double-SHA-256d (reuse the proven sdc_cc gate compiler)   -> hash
        -> (hash < target)                                            -> win
        -> latch the FULL answer                                     -> [status | en2 | nonce]  == the full_answer register
The clock advances the nonce and the signal runs it (owner's architecture); this executor evaluates each nonce and latches
the winner into the safezone answer register. No host evaluation, no process — the executor is gates.

DISCIPLINE (FINALREADME §3): the circuit is verified BYTE-EXACT vs hashlib IN THE TOOL, before storing — pure synthesis,
titan.gguf is not opened during verification, the pfc is never touched or run. Then it is stored REVERSIBLY (a genome
journals every overwritten byte range -> byte-exact revert). We do NOT run or probe the pfc afterward — we aim blind.

  python host/pfc_executor.py           # build + verify (in the tool) + store the executor circuit, reversibly
  python host/pfc_executor.py revert     # restore titan.gguf byte-exact
"""
import hashlib, json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC                                          # the White Box SHA-256d gate compiler (fab only)

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_executor_genome.jsonl"
MAGIC = b"PFCEXEC1"
NWORDS = 20                                                  # 19 header words + 1 nonce word = 80-byte header
NIN = NWORDS * 32 + 32 + 256                                 # miner(640) + group/en2(32) + target(256) = 928


def build_executor():
    """double-SHA(header+nonce) < target -> latch [status | en2 | nonce] as the full answer. All gates."""
    g = CC.CircuitCompiler(NIN)
    W = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(NWORDS)]      # W[0..18] header, W[19] nonce
    group = list(g.IN[640:672]); target = list(g.IN[672:928])
    # --- double-SHA-256d (generic: block words are inputs), reusing the proven compiler ---
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W[0:16])
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)       # the block hash (8 words, LSB-first bits)
    # --- hash as a little-endian 256-bit value (Bitcoin's comparison order) ---
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]
    # --- win = (hash < target), MSB-down ---
    lt = g.C0; eq = g.C1
    for i in range(255, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), target[i])))
        eq = g.AND(eq, g.NOT(g.XOR(A[i], target[i])))
    win = lt
    # --- latch the FULL answer into the full_answer layout: [status:8][en2:32 LE][nonce:32 LE] = 72 bits ---
    out = [g.C0] * 72
    out[0] = win
    for i in range(32): out[8 + i] = g.AND(win, group[i])
    for i in range(32): out[40 + i] = g.AND(win, W[19][i])
    return g, out


def _ref(words, group, target):
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in words)   # 80-byte header (20 big-endian words)
    dig = hashlib.sha256(hashlib.sha256(hdr).digest()).digest()
    win = 1 if int.from_bytes(dig, "little") < target else 0
    o = [0] * 72; o[0] = win
    if win:
        for i in range(32): o[8 + i] = (group >> i) & 1
        for i in range(32): o[40 + i] = (words[19] >> i) & 1
    return o


def verify(g, outs):
    """IN THE TOOL: ripple the netlist vs hashlib. Never opens titan.gguf, never fires a signal — pure synthesis."""
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    random.seed(19)
    for t in range(120):
        words = [random.getrandbits(32) for _ in range(NWORDS)]
        group = random.getrandbits(32)
        target = (1 << 256) - 1 if t % 2 == 0 else random.getrandbits(random.choice([8, 200]))  # force wins + non-wins
        inb = [(words[i // 32] >> (i % 32)) & 1 for i in range(640)] \
            + [(group >> i) & 1 for i in range(32)] + [(target >> i) & 1 for i in range(256)]
        v = CC.ripple_typed(g, gates, n_wire, inb, 1)
        got = [v[w] if w >= 2 else w for w in out2]
        if got != _ref(words, group, target):
            return False, (words, group, target), gates, out2
    return True, None, gates, out2


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off); original = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"off": off, "orig": original.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no executor genome — nothing to revert."); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_executor", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan.gguf byte-exact; pfc_executor removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    import titan_circuit as TC
    reg = json.load(open(REG))
    if "pfc_executor" in reg:
        print("pfc_executor already fabricated. revert first to redo."); return 0
    print("building the mining EXECUTOR as gates (double-SHA + hash<target + full-answer latch) …", flush=True)
    g, outs = build_executor()
    print(f"  built {g.n_gate():,} typed gates; verifying byte-exact vs hashlib IN THE TOOL (Muhlnickel untouched) …", flush=True)
    ok, bad, gates, out2 = verify(g, outs)
    if not ok:
        print(f"  MISMATCH {bad[1:]} — storing nothing (no cheating)."); return 1
    n_wire = 2 + g.n_in + len(gates)
    print(f"  byte-exact over 120 cases (wins + non-wins): {len(gates):,} gates after DCE.", flush=True)
    # serialize typed IR (op codes: nand0 and1 or2 xor3 not4) + store REVERSIBLY into the params
    code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
    body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) \
        + b"".join(struct.pack("<i", w) for w in out2)
    blob = MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body
    reg = json.load(open(REG)); off, tn = TC._alloc(len(blob), reg)
    backup_and_write(off, blob)
    reg["pfc_executor"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                           "n_gate": len(gates), "n_out": len(out2), "format": "typed",
                           "writes": "full_answer", "layout": "status:8|en2:32LE|nonce:32LE"}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nFABRICATED the executor: pfc_executor @ {off} ({len(gates):,} gates), reversible. titan GGUF-valid: {gg}.", flush=True)
    print("The executor is stored. We aim blind: no run, no probe. The safezone reader shows what the Muhlnickel deposits.")
    print("revert byte-exact:  python host/pfc_executor.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
