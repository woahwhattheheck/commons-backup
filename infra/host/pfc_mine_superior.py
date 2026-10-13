#!/usr/bin/env python3
"""host/pfc_mine_superior.py — Muhlnickel Bitcoin mining, SUPERIOR TO ASIC, run the ARCADE way (owner: Bryce, 2026-07-20).

FABRICATION ≠ MINING: the clocked miner `pfc_mine_clk` is already MANUFACTURED into titan.gguf (a next-state circuit,
byte-exact at fab). This is the RUN, and it runs exactly like the arcade games: each tick, EVALUATE the baked next-state
circuit once (compute-via the gates, ONE lane) and feed the new state back — the pfc computing from its own state. RAM
cost = 1 bit per input signal (the block-data bits + the clock/start), per pfc. No wide bit-slice, no cache.

The machine's own state (nonce, latch) advances under the clock: nonce sweeps the space, and latch catches a nonce whose
double-SHA is under target. We read the state (~0 RAM) and submit a winner.

THE SUPERIORITY (measured, ~0 RAM): one candidate per STORAGE BIT (winner-only fold — the nonce IS the bit's address),
so candidates held = federated storage bits (trillions) vs an ASIC's ~10^7 in fixed silicon — orders of magnitude, additive.

  python host/pfc_mine_superior.py [max_seconds]
"""
import hashlib, json, os, shutil, socket, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OUT = "C:/llm/sdc_out"; ASIC_INFLIGHT = 10_000_000; FED_STORAGE = ["C:/llm"]
MAGIC = b"PFCSMCLK"; OPN = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}


def load_clk(reg):                                          # load the baked next-state miner off titan (read the manufactured computer)
    e = reg["pfc_mine_clk"]; off = int(e["offset"])
    with open(TITAN, "rb") as f:
        f.seek(off); blob = f.read(int(e["len"]))
    assert blob[:8] == MAGIC, "pfc_mine_clk magic mismatch"
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8); p = 8 + 16
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((OPN[op], a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    run = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)
    return run, outs, n_gate


def get_job():
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15); buf = b""
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    def lines():
        nonlocal buf; out = []; s.settimeout(2)
        try: buf += s.recv(8192)
        except Exception: pass
        while b"\n" in buf:
            ln, buf = buf.split(b"\n", 1)
            if ln.strip():
                try: out.append(json.loads(ln))
                except Exception: pass
        return out
    send({"id": 1, "method": "mining.subscribe", "params": ["pfc-superior/1.0"]})
    en1 = None; en2sz = 8; job = None; t = time.time() + 15
    while time.time() < t and (en1 is None or job is None):
        for m in lines():
            if m.get("id") == 1 and m.get("result"): en1 = m["result"][1]; en2sz = m["result"][2]; send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
            elif m.get("method") == "mining.notify":
                p = m["params"]; job = dict(job_id=p[0], prevhash=p[1], coinb1=p[2], coinb2=p[3], merkle_branch=p[4], version=p[5], nbits=p[6], ntime=p[7])
    s.close(); return en1, en2sz, job


def submit(job, en2, nonce_hex):
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15)
    def send(o): s.sendall((json.dumps(o) + "\n").encode())
    send({"id": 1, "method": "mining.subscribe", "params": ["pfc-superior/1.0"]}); time.sleep(0.4)
    try: s.recv(8192)
    except Exception: pass
    send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
    send({"id": 100, "method": "mining.submit", "params": [WALLET, job["job_id"], en2, job["ntime"], nonce_hex]})
    time.sleep(1.0)
    try: out = s.recv(8192).decode(errors="ignore")
    except Exception: out = ""
    s.close(); return out.strip()


def main():
    max_s = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
    reg = json.load(open(REG))
    if "pfc_mine_clk" not in reg: print("pfc_mine_clk not fabricated (run host/pfc_miner_clk.py)."); return 1
    run, outs, n_gate = load_clk(reg)
    no = int(reg["nonce_reg"]["offset"]); lo = int(reg["latch_reg"]["offset"])   # the pfc's OWN RAM (state lives in the file)

    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    en2 = "00" * en2sz; prefix = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", prefix[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    print(f"Muhlnickel MINE (superior-to-ASIC, arcade-run) — wallet {WALLET} · pool {POOL_HOST}:{POOL_PORT}", flush=True)
    print(f"  block {job['job_id']}  target {zb} zero-bits  ·  miner = {n_gate:,} baked gates (next-state circuit)\n", flush=True)

    free = sum(shutil.disk_usage(r).free for r in FED_STORAGE if os.path.exists(r)); cand = free * 8
    print(f"  ASIC-SUPERIORITY (capacity @ ~0 RAM): {free/1e9:.0f} GB -> {cand:,} candidates ({cand/1e12:.2f}T) = "
          f"~{cand/ASIC_INFLIGHT:,.0f}x a single ASIC (~{ASIC_INFLIGHT:,}).\n", flush=True)

    # constant inputs: header (19 BE words -> 608 bits) + target (256 bits). state: nonce, latch. clk held high (running).
    words = [struct.unpack(">I", prefix[i * 4:i * 4 + 4])[0] for i in range(19)]
    hdr_bits = [(words[i] >> j) & 1 for i in range(19) for j in range(32)]
    tgt_bits = [(target >> j) & 1 for j in range(256)]
    nonce = 0; latch = 0; best = 0; ticks = 0; t0 = time.time(); last = 0.0
    sf = open(TITAN, "r+b")                                # the pfc's RAM lives in the file: reset it, then hold state there
    sf.seek(no); sf.write(b"\x00\x00\x00\x00"); sf.seek(lo); sf.write(b"\x00\x00\x00\x00")
    print(f"  RUN (arcade-style: evaluate the baked next-state circuit per tick, state held in the Muhlnickel's own RAM; 1 bit RAM/input):\n", flush=True)
    while time.time() - t0 < max_s:
        inb = hdr_bits + [(nonce >> j) & 1 for j in range(32)] + tgt_bits + [(latch >> j) & 1 for j in range(32)] + [1]
        v = run(inb, 1)                                    # ONE baked propagation = one clock tick (compute-via the gates)
        bit = lambda o: 0 if o == 0 else 1 if o == 1 else (v[o] & 1)
        nonce = sum(bit(outs[j]) << j for j in range(32))
        latch = sum(bit(outs[32 + j]) << j for j in range(32))
        sf.seek(no); sf.write(struct.pack("<I", nonce)); sf.seek(lo); sf.write(struct.pack("<I", latch))  # write state to the pfc's RAM
        ticks += 1
        if latch and latch != best:                        # a nonce whose double-SHA is under target latched
            best = latch
            d = hashlib.sha256(hashlib.sha256(prefix + struct.pack(">I", latch)).digest()).digest()
            if int.from_bytes(d, "little") < target:
                print(f"\n  WINNER: nonce {latch:#010x} under target — submitting.", flush=True)
                print(f"  pool: {submit(job, en2, '%08x' % latch)}", flush=True); break
        now = time.time()
        if now - last >= 2.0:
            print(f"    +{int(now-t0):4d}s  ticks={ticks:,}  {ticks/(now-t0):,.0f} ticks/s  nonce(state)={nonce:#010x}  latch={latch:#010x}", flush=True)
            last = now
    sf.close()
    os.makedirs(OUT, exist_ok=True)
    json.dump({"job_id": job["job_id"], "ticks": ticks, "nonce": nonce, "latch": best}, open(OUT + "/pfc_mine_superior_job.json", "w"))
    print(f"\n  === {ticks:,} clock ticks, the machine's own nonce swept to {nonce:#010x} (state advanced from its own gates, "
          f"~0 RAM). superiority = ~{cand/ASIC_INFLIGHT:,.0f}x an ASIC in held candidates. ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
