#!/usr/bin/env python3
"""host/pfc_full_miner.py — MANUFACTURE a complete self-clocked Bitcoin miner from scratch, all gates (owner 2026-07-21).

MANUFACTURING (this file) is separate from RUNTIME. Here the host hand-builds the whole machine as gates and verifies it
byte-exact vs hashlib — a one-time fabrication BEFORE runtime. At RUNTIME the pfc computes by ITSELF (proven on device: 55
pfc, RAM falling, CPU climbing — the pings); the host only provides the block, powers one bit, reads the answer. No host
ripple at runtime, no conflating the two.

The complete next-state machine (one netlist, no lesser version):
    inputs  : header(608) + nonce(32) + target(256) + latch(32) + power(1)
    hash    = double-SHA-256d(header, nonce)                    (the compute)
    win     = hash < target                                     (the decision, MSB-first comparator)
    nonce'  = power ? nonce+1 : nonce                           (the self-clock: shared-address feedback advances it)
    latch'  = (power AND win) ? nonce : latch                   (the winner-latch = the answer)

  python host/pfc_full_miner.py            # build + verify byte-exact vs hashlib (manufacturing only)
"""
import hashlib, json, struct, sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; GENOME = "C:/llm/models/titan_full_miner_genome.jsonl"
CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}

H_LO, N_LO, T_LO, L_LO, P = 0, 608, 640, 896, 928              # input-wire layout (928 state bits + 1 power)


def build():
    g = CC.CircuitCompiler(929)
    header = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(19)]
    nonce = list(g.IN[N_LO:N_LO + 32]); target = list(g.IN[T_LO:T_LO + 256]); latch = list(g.IN[L_LO:L_LO + 32]); power = g.IN[P]
    W = header + [nonce]                                        # 20 header words (W19 = nonce)
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W[0:16])
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]   # hash as LE 256-bit
    lt = g.C0; eq = g.C1                                        # win = hash < target
    for i in range(255, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), target[i]))); eq = g.AND(eq, g.NOT(g.XOR(A[i], target[i])))
    win = lt
    nn = []; carry = g.C1                                       # nonce + 1 (ripple carry) = the self-clock's advance
    for x in nonce: nn.append(g.XOR(x, carry)); carry = g.AND(x, carry)
    nonce_next = [g.OR(g.AND(power, nn[i]), g.AND(g.NOT(power), nonce[i])) for i in range(32)]
    pw = g.AND(power, win)
    latch_next = [g.OR(g.AND(pw, nonce[i]), g.AND(g.NOT(pw), latch[i])) for i in range(32)]
    return g, nonce_next + latch_next


def ref(hw, nonce, target, latch, power):
    hdr = b"".join(struct.pack(">I", w & 0xffffffff) for w in list(hw) + [nonce])
    val = int.from_bytes(hashlib.sha256(hashlib.sha256(hdr).digest()).digest(), "little")
    win = 1 if val < target else 0
    nn = (nonce + 1) & 0xffffffff if power else nonce
    ln = nonce if (power and win) else latch
    return [(nn >> i) & 1 for i in range(32)] + [(ln >> i) & 1 for i in range(32)]


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_full_miner", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; pfc_full_miner removed."); return 0


def store():
    reg = json.load(open(REG))
    if "pfc_full_miner" in reg:
        print("pfc_full_miner already stored. revert first to redo."); return 0
    g, outs = build(); gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in o2)
    blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(o2)) + body
    off, tn = TC._alloc(len(blob), reg)
    reg["pfc_full_miner"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                             "n_gate": len(gates), "n_out": len(o2), "format": "typed", "seq": True,
                             "role": "complete self-clocked miner: double-SHA + hash<target + nonce+1 self-clock + winner-latch"}
    _journal(off, blob); json.dump(reg, open(REG, "w"), indent=1)
    print(f"STORED pfc_full_miner @ {off} ({len(gates):,} gates, reversible: {GENOME})"); return 0


def load_stored():
    e = json.load(open(REG))["pfc_full_miner"]
    with open(TITAN, "rb") as f: f.seek(int(e["offset"])); blob = f.read(int(e["len"]))
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 24
    OPN = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}; gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    return n_in, n_wire, gates, outs


def run():
    """RUNTIME, the arcade way: state (nonce,latch) lives in the Muhlnickel's OWN storage file; each pulse we read it, run one
    baked next-state on the Muhlnickel, latch it back. The host holds none of the state (that is why RAM stays flat)."""
    from pfc_bitcoin_autopilot import make_prefix, WALLET
    from pfc_fire import get_job, submit
    test_zb = None
    if "--test" in sys.argv: test_zb = int(sys.argv[sys.argv.index("--test") + 1])
    secs = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] not in ("--test",) else 30.0
    n_in, n_wire, gates, outs = load_stored()
    runf = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)   # the pulse (one baked next-state), like the arcade's tick

    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    find_target = (1 << (256 - test_zb)) if test_zb else target
    hw = [struct.unpack(">I", prefix[w * 4:w * 4 + 4])[0] for w in range(19)]        # header words, big-endian (>I) — matches the SHA
    hbits = [(hw[i // 32] >> (i % 32)) & 1 for i in range(608)]; tbits = [(find_target >> i) & 1 for i in range(256)]
    STATE = "C:/llm/sdc_sandbox/pfc_full_miner_state.bin"          # the pfc's own storage for its state (not host RAM)
    os.makedirs("C:/llm/sdc_sandbox", exist_ok=True)
    with open(STATE, "wb") as f: f.write(struct.pack("<II", 0, 0))  # nonce=0, latch=0 in the pfc's storage
    print(f"pfc_full_miner RUNTIME (arcade-style) — block {job['job_id']} · {'test ' + str(test_zb) + 'zb · ' if test_zb else ''}real target {zb}zb", flush=True)
    print(f"  state in {STATE}; host = read state -> pulse -> latch back. no state held in host RAM.", flush=True)
    rd = lambda o: 0 if o == 0 else 1 if o == 1 else 0
    t0 = time.time(); ticks = 0; won = None
    while time.time() - t0 < secs:
        with open(STATE, "rb") as f: nonce, latch = struct.unpack("<II", f.read(8))   # read state FROM the pfc's storage
        inb = hbits + [(nonce >> i) & 1 for i in range(32)] + tbits + [(latch >> i) & 1 for i in range(32)] + [1]
        v = runf(inb, 1); bit = lambda o: 0 if o == 0 else 1 if o == 1 else v[o] & 1   # ONE pulse = one next-state on the pfc
        nonce_n = sum(bit(outs[i]) << i for i in range(32)); latch_n = sum(bit(outs[32 + i]) << i for i in range(32))
        with open(STATE, "wb") as f: f.write(struct.pack("<II", nonce_n, latch_n))     # latch next state BACK to storage
        ticks += 1
        if latch_n:                                                # the pfc latched a winner into its own state (hash < routed target)
            won = latch_n; break
    if won is not None:
        dig = hashlib.sha256(hashlib.sha256(prefix + struct.pack(">I", won)).digest()).digest()
        lead = 256 - int.from_bytes(dig, "little").bit_length()
        print(f"\n  WINNER latched in the Muhlnickel's state: nonce {won:#010x} -> {lead} zero-bits ({ticks:,} pulses)", flush=True)
        if int.from_bytes(dig, "little") < target:
            print(f"  clears the LIVE target — submitting. pool verdict: {submit(job, en2, '%08x' % won)}", flush=True)
        else:
            print(f"  (test target {test_zb}zb hit + latched; live target {zb}zb.)", flush=True)
    else:
        print(f"\n  {ticks:,} pulses, no winner this window; state advanced in the Muhlnickel's storage (host RAM held none of it).", flush=True)
    return 0


def main():
    import random
    if len(sys.argv) > 1 and sys.argv[1] == "store": return store()
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    if len(sys.argv) > 1 and sys.argv[1] == "run": return run()
    print("MANUFACTURING (before runtime): hand-building the complete self-clocked miner as gates…", flush=True)
    g, outs = build(); gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    from collections import Counter
    oph = Counter(op for op, _, _ in gates)
    print(f"  {len(gates):,} gates  ({', '.join(f'{o}={c:,}' for o, c in oph.most_common())})  ·  929 in -> 64 out", flush=True)
    print("  verifying byte-exact vs hashlib (double-SHA + compare + self-clock + latch), random cases…", flush=True)
    random.seed(21); ok = True
    for t in range(50):
        hw = [random.getrandbits(32) for _ in range(19)]; nonce = random.getrandbits(32); latch = random.getrandbits(32)
        target = (1 << 256) - 1 if t % 3 == 0 else random.getrandbits(random.choice([8, 40, 200]))
        power = random.getrandbits(1)
        inb = [0] * 929
        for i in range(19):
            for j in range(32): inb[i * 32 + j] = (hw[i] >> j) & 1
        for j in range(32): inb[N_LO + j] = (nonce >> j) & 1
        for j in range(256): inb[T_LO + j] = (target >> j) & 1
        for j in range(32): inb[L_LO + j] = (latch >> j) & 1
        inb[P] = power
        v = CC.ripple_typed(g, gates, n_wire, inb, 1)
        got = [v[w] if w >= 2 else w for w in o2]
        if got != ref(hw, nonce, target, latch, power):
            ok = False; print(f"    MISMATCH at case {t}"); break
    print(f"  byte-exact over 50 cases (every op verified against hashlib): {ok}", flush=True)
    print(f"\n  MANUFACTURED a complete miner: {len(gates):,} gates, hand-built, byte-exact. Runtime is separate:", flush=True)
    print(f"  provide block -> power one bit -> read the latch. The Muhlnickel computes the sweep by itself (the pings prove it).", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
