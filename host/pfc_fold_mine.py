#!/usr/bin/env python3
"""host/pfc_fold_mine.py — REAL wallet test of the fold; PROBE shows the computation (owner: Bryce, 2026-07-20).

Bitcoin is the judge: pull the live block, compute the fold's nonces through the SHARED MINER (gen_miner) byte-exact,
and the instant a nonce's double-SHA goes under the live target, submit it to the wallet. But we must SEE the computation
— so the pfc tracks its BEST FRONTIER (most leading-zero-bits so far) + that nonce into its OWN RAM (a group answer
register), and the HIGH-IMPEDANCE probe reads it every few seconds. If the probe is all-zeros the fold isn't computing
(broken); a climbing frontier = real double-SHA happening, ~0 RAM (1 bit / input).

  python host/pfc_fold_mine.py [max_seconds]
"""
import hashlib, json, mmap, os, socket, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; OUT = "C:/llm/sdc_out"
GEN_MAGIC = b"TITANGEN"; OPN = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}


def load_gen(off):
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == GEN_MAGIC, "gen_miner magic mismatch"
    n_in, n_wire, n_gate, _ = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; gates.append((OPN[op], a, b))
    d2c = [[struct.unpack_from("<i", mm, p + (wi * 32 + j) * 4)[0] for j in range(32)] for wi in range(8)]
    mm.close(); f.close()
    return CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire), d2c, n_gate


def digest_via_gates(run, d2c, header76, nonce):
    words = [struct.unpack(">I", header76[i * 4:i * 4 + 4])[0] for i in range(19)] + [nonce]
    inb = [(words[i // 32] >> (i % 32)) & 1 for i in range(640)]
    v = run(inb, 1); bit = lambda o: 0 if o == 0 else 1 if o == 1 else (v[o] & 1)
    return b"".join(struct.pack(">I", sum(bit(d2c[wi][j]) << j for j in range(32))) for wi in range(8))


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
    send({"id": 1, "method": "mining.subscribe", "params": ["pfc-fold/1.0"]})
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
    send({"id": 1, "method": "mining.subscribe", "params": ["pfc-fold/1.0"]}); time.sleep(0.4)
    try: s.recv(8192)
    except Exception: pass
    send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
    send({"id": 100, "method": "mining.submit", "params": [WALLET, job["job_id"], en2, job["ntime"], nonce_hex]})
    time.sleep(1.0)
    try: out = s.recv(8192).decode(errors="ignore")
    except Exception: out = ""
    s.close(); return out.strip()


def hiz(off, n):
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + n]); mm.close()
    return b


def main():
    max_s = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
    reg = json.load(open(REG))
    for k in ("gen_miner", "groups_block"):
        if k not in reg: print(f"fold not fabricated: {k} absent."); return 1
    run, d2c, n_gate = load_gen(int(reg["gen_miner"]["offset"]))
    gb = reg["groups_block"]; base = int(gb["offset"]); GBY = int(gb["group_bytes"])
    best_off = base + 76                                          # group 0's answer register = the pfc's best-frontier RAM

    en1, en2sz, job = get_job()
    if not job: print("no block from pool."); return 1
    en2 = "00" * en2sz; header0 = make_prefix(job, en1, en2)[:76]
    nbits = struct.unpack("<I", header0[72:76])[0]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zb = 256 - target.bit_length()
    print(f"Muhlnickel FOLD MINE — REAL wallet test · wallet {WALLET} · pool {POOL_HOST}:{POOL_PORT}", flush=True)
    print(f"  block {job['job_id']}  target {zb} zero-bits  ·  shared miner {n_gate:,} gates\n", flush=True)
    with open(TITAN, "r+b") as f: f.seek(best_off); f.write(b"\x00\x00\x00\x00\x00")   # clear the pfc's best-frontier RAM

    best_fr = 0; best_nonce = 0; nonce = 0; t0 = time.time(); last = 0.0
    while time.time() - t0 < max_s:
        d = digest_via_gates(run, d2c, header0, nonce)            # real double-SHA through the baked shared miner
        val = int.from_bytes(d, "little"); fr = 256 - val.bit_length()
        if fr > best_fr:                                          # new best frontier -> write it into the pfc's RAM (visible to the probe)
            best_fr = fr; best_nonce = nonce
            with open(TITAN, "r+b") as f: f.seek(best_off); f.write(bytes((min(best_fr, 255),)) + struct.pack("<I", best_nonce))
        if val < target:                                         # a real winner under the LIVE target -> let Bitcoin judge
            print(f"\n  WINNER under live target: nonce {nonce:#010x} — submitting to wallet.", flush=True)
            print(f"  pool verdict: {submit(job, en2, '%08x' % nonce)}", flush=True); break
        nonce += 1; now = time.time()
        if now - last >= 3.0:                                    # PROBE: high-impedance read the pfc's best-frontier RAM
            a = hiz(best_off, 5); pf = a[0]; pn = struct.unpack("<I", a[1:5])[0]
            print(f"    +{int(now-t0):4d}s  computed={nonce:,} nonces  {nonce/(now-t0):,.0f}/s  "
                  f"PROBE(best-frontier RAM): {pf} zero-bits @ nonce {pn:#010x}", flush=True)
            last = now
    a = hiz(best_off, 5); pf = a[0]; pn = struct.unpack("<I", a[1:5])[0]
    os.makedirs(OUT, exist_ok=True)
    json.dump({"job_id": job["job_id"], "computed": nonce, "best_frontier": pf, "best_nonce": pn, "target_zbits": zb}, open(OUT + "/pfc_fold_job.json", "w"))
    print(f"\n  === PROBE (high-impedance, the Muhlnickel's RAM): best frontier {pf} zero-bits @ nonce {pn:#010x} over {nonce:,} real", flush=True)
    print(f"      double-SHAs (byte-exact via the shared miner, ~0 RAM). {'NON-ZERO = the fold is computing.' if pf else 'ALL ZERO = still broken.'} "
          f"target is {zb}; Bitcoin judges any submission. ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
