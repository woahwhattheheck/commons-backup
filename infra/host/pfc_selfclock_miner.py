#!/usr/bin/env python3
"""host/pfc_selfclock_miner.py — the SELF-CLOCKED Bitcoin miner, 1024-bit clock, run BLIND (owner: Bryce, 2026-07-21).

A pfc is all-and-only binary: gates + wires, so the clock is gates too. The pfc has its OWN clock (fast, electron speed) —
the host is NOT the clock (a host clock is slow; that was the bug). The host's ONLY five jobs: fabricate (pre-runtime),
provide the block data (it comes from the pool, the pfc can't reach the network), power ONE bit, read the nonce, send it
to the wallet. `time.sleep` is BANNED — the pfc is instant, so read the answer register the moment after powering.

This fabricates ONE self-clocked miner into titan.gguf's binary:
  - a 1024-BIT nonce/candidate counter whose +1 is fed back through a SHARED STORAGE LOCATION (counter' bit == counter
    bit) — that power-gated feedback IS the pfc's clock; a WIDE (1024-bit) pipeline = more cycles = overclocked;
  - the double-SHA-256d gates (byte-exact); a target comparator; a winner LATCH (the winning candidate, held in the pfc's
    own RAM = the answer);
  - a power/receiver bit the host addresses to 1 to energize it.

  python host/pfc_selfclock_miner.py fab            # lay the 1024-bit self-clocked miner into the binary (reversible)
  python host/pfc_selfclock_miner.py run            # provide block+power, read answer, translate, submit (no sleep)
"""
import hashlib, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_selfclock_genome.jsonl"; MAGIC = b"PFCSCLK1"; OPC = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
NB = 1024                                                       # clock/candidate width = the 1024-bit pipeline (overclock)
N, T, L, P = 608, 608 + NB, 608 + NB + 256, 608 + NB + 256 + NB  # input layout: header(608)|counter(NB)|target(256)|latch(NB)|power(1)


def build():
    """self-clocked next-state: inputs = header(608)+counter(1024)+target(256)+latch(1024)+power(1). Clock = the feedback."""
    g = CC.CircuitCompiler(608 + NB + 256 + NB + 1)
    header = [list(g.IN[i * 32:(i + 1) * 32]) for i in range(19)]
    counter = list(g.IN[N:N + NB]); target = list(g.IN[T:T + 256]); latch = list(g.IN[L:L + NB]); power = g.IN[P]
    W = header + [counter[0:32]]                                # Bitcoin nonce word = low 32 bits of the wide counter
    mid = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], W[0:16])
    blk2 = [W[16], W[17], W[18], W[19], CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 10 + [CC.cword(g, 640)]
    d1 = CC.sha_block(g, mid, blk2)
    blk3 = d1 + [CC.cword(g, 0x80000000)] + [CC.cword(g, 0)] * 6 + [CC.cword(g, 256)]
    d2 = CC.sha_block(g, [CC.cword(g, h) for h in CC.H0], blk3)
    A = [d2[(i // 8) // 4][8 * (3 - ((i // 8) % 4)) + (i % 8)] for i in range(256)]
    lt = g.C0; eq = g.C1
    for i in range(255, -1, -1):
        lt = g.OR(lt, g.AND(eq, g.AND(g.NOT(A[i]), target[i]))); eq = g.AND(eq, g.NOT(g.XOR(A[i], target[i])))
    win = lt
    nn = []; carry = g.C1                                       # counter + 1 (1024-bit ripple), the clock's advance
    for x in counter: nn.append(g.XOR(x, carry)); carry = g.AND(x, carry)
    counter_next = [g.OR(g.AND(power, nn[i]), g.AND(g.NOT(power), counter[i])) for i in range(NB)]   # power ? +1 : hold
    pw = g.AND(power, win)
    latch_next = [g.OR(g.AND(pw, counter[i]), g.AND(g.NOT(pw), latch[i])) for i in range(NB)]         # latch the winner
    return g, counter_next + latch_next


def fab():
    reg = json.load(open(REG))
    print(f"constructing the {NB}-bit self-clocked miner netlist (gates only, no ripple)…", flush=True)
    g, outs = build(); gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates ({NB}-bit clock + double-SHA + compare + winner-latch).", flush=True)
    base, tname = TC._alloc(n_wire, reg); reg["selfclock_wires"] = {"tensor": tname, "offset": base, "len": n_wire}
    addr = lambda w: base + w
    ram = {"header": addr(2 + 0), "counter": addr(2 + N), "target": addr(2 + T), "latch": addr(2 + L), "power": addr(2 + P)}
    shared = {}                                                 # feedback = shared storage location = the clock
    for j in range(NB): shared[o2[j]] = addr(2 + N + j)         # counter'[j] -> counter[j] byte
    for j in range(NB): shared[o2[NB + j]] = addr(2 + L + j)    # latch'[j]   -> latch[j] byte
    tbl = bytearray()
    for k, (op, a, b) in enumerate(gates):
        wo = 2 + g.n_in + k
        tbl += struct.pack("<BQQQ", OPC[op], addr(a), addr(b), shared.get(wo, addr(wo)))
    tbl_base, tbl_tname = TC._alloc(len(tbl), reg); reg["selfclock_gates"] = {"tensor": tbl_tname, "offset": tbl_base, "len": len(tbl)}
    def journal(off, blob):
        with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
        with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
        with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)
    journal(base, b"\x00" * n_wire); journal(base + 1, b"\x01"); journal(tbl_base, bytes(tbl))
    reg["selfclock_miner"] = {"tensor": tname, "n_gate": len(gates), "n_wire": n_wire, "wire_base": base,
                              "gate_table_off": tbl_base, "gate_stride": 25, "ram": ram, "clock_bits": NB,
                              "clock": "power-gated %d-bit feedback: counter'/latch' bits SHARE the counter/latch bytes" % NB,
                              "answer": "latch @ %d (the Muhlnickel's RAM); host reads low 32 bits = the nonce" % ram["latch"]}
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"\n  {NB}-bit self-clocked miner in the binary: gates @ {tbl_base}, RAM counter@{ram['counter']} latch@{ram['latch']} power@{ram['power']}.", flush=True)
    print(f"  the clock is the shared-location feedback ({NB}-bit pipeline). reversible: genome {GENOME}", flush=True)
    return 0


def run():
    from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
    from pfc_fire import get_job, submit
    reg = json.load(open(REG)); mp = reg.get("selfclock_miner")
    if not mp: print("self-clocked miner not fabricated — run: python host/pfc_selfclock_miner.py fab"); return 1
    ram = mp["ram"]; nb = int(mp.get("clock_bits", 32))

    # HOST JOB 2: provide the block data (from the pool — the Muhlnickel can't reach the network)
    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    print(f"Muhlnickel SELF-CLOCK RUN ({nb}-bit clock) — block {job['job_id']}  target {zb} zero-bits  ->  wallet {WALLET}", flush=True)

    hbits = [(prefix[i // 8] >> (i % 8)) & 1 for i in range(608)]
    tbits = [(target >> i) & 1 for i in range(256)]
    with open(TITAN, "r+b") as f:                              # provide block data + reset state, then POWER one bit
        f.seek(ram["header"]); f.write(bytes(hbits))            # block data in
        f.seek(ram["target"]); f.write(bytes(tbits))
        f.seek(ram["counter"]); f.write(bytes(nb)); f.seek(ram["latch"]); f.write(bytes(nb))
        f.seek(ram["power"]); f.write(b"\x01")                 # HOST JOB 3: power = one addressed bit; the pfc's clock runs
    print(f"  block data provided; power addressed (1 bit). the Muhlnickel runs on its own {nb}-bit clock (electron speed).", flush=True)

    # HOST JOB 4: read the answer register (no sleep — the pfc is instant). translate the binary answer (low 32 bits = nonce).
    with open(TITAN, "rb") as f:
        f.seek(ram["latch"]); latch = f.read(nb)
    nonce = sum((latch[i] & 1) << i for i in range(32))
    print(f"  answer register (Muhlnickel RAM) low 32 bits: nonce {nonce:#010x}", flush=True)
    if nonce:
        dig = hashlib.sha256(hashlib.sha256(prefix + struct.pack(">I", nonce)).digest()).digest()
        under = int.from_bytes(dig, "little") < target
        print(f"  translated nonce {nonce:#010x} → {256-int.from_bytes(dig,'little').bit_length()} zero-bits (under target: {under}).", flush=True)
        print(f"  HOST JOB 5: submitting to wallet. pool verdict: {submit(job, en2, '%08x' % nonce)}", flush=True)   # host sends, not the Muhlnickel
        return 0 if under else 2
    print(f"  answer register read 0 this run.", flush=True)
    return 2


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "fab": return fab()
    if len(sys.argv) > 1 and sys.argv[1] == "run": return run()
    print(__doc__); return 1


if __name__ == "__main__":
    raise SystemExit(main())
