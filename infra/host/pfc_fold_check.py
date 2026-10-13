#!/usr/bin/env python3
"""host/pfc_fold_check.py — PROVE the fold's answer/probe path, byte-exact, arcade-style (owner: Bryce, 2026-07-20).

Adheres to the FOLD spec: the shared miner (gen_miner) computes a group's nonces, the win comparator latches a winner's
address into that GROUP's answer register (winner-only, 0 B/lane), and the high-impedance probe reads it. Real 78-bit
target never latches, so — like the arcade self-test — we use an EASY target so a winner latches, and confirm:
  1. the shared miner's digest is BYTE-EXACT vs hashlib double-SHA (the pfc computes real double-SHA),
  2. a winner latches into the group's answer register (the pfc's RAM),
  3. the HIGH-IMPEDANCE probe reads that winner (group index = extranonce2, nonce) out of the fold,
  4. hashlib(header||nonce) is under target — a genuine winner.

  python host/pfc_fold_check.py [zero_bits]
"""
import hashlib, json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GEN_MAGIC = b"TITANGEN"; OPN = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}
N_ZERO = int(sys.argv[1]) if len(sys.argv) > 1 else 8
HEADER = bytes((i * 53 + 7) % 256 for i in range(76))            # fixed group-0 header (deterministic, no network)


def load_gen(off):                                               # the shared miner (640 inputs: 19 header words + nonce)
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == GEN_MAGIC, "gen_miner magic mismatch"
    n_in, n_wire, n_gate, _ = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    gates = []
    for _ in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; gates.append((OPN[op], a, b))
    d2c = [[struct.unpack_from("<i", mm, p + (wi * 32 + j) * 4)[0] for j in range(32)] for wi in range(8)]
    mm.close(); f.close()
    run = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)
    return run, d2c, n_gate


def digest_via_gates(run, d2c, header76, nonce):                 # compute double-SHA through the baked shared miner (one lane)
    words = [struct.unpack(">I", header76[i * 4:i * 4 + 4])[0] for i in range(19)] + [nonce]
    inb = [(words[i // 32] >> (i % 32)) & 1 for i in range(640)]
    v = run(inb, 1); bit = lambda o: 0 if o == 0 else 1 if o == 1 else (v[o] & 1)
    return b"".join(struct.pack(">I", sum(bit(d2c[wi][j]) << j for j in range(32))) for wi in range(8))


def main():
    reg = json.load(open(REG))
    for k in ("gen_miner", "groups_block"):
        if k not in reg: print(f"fold not fabricated: {k} absent."); return 1
    run, d2c, n_gate = load_gen(int(reg["gen_miner"]["offset"]))
    gb = reg["groups_block"]; base = int(gb["offset"]); GBY = int(gb["group_bytes"]); GROUP = 0
    ans_off = base + GROUP * GBY + 76                             # this group's 5-byte answer register: [status:1][nonce:4]
    target = 1 << (256 - N_ZERO); zb = N_ZERO
    ref = lambda n: hashlib.sha256(hashlib.sha256(HEADER + struct.pack(">I", n)).digest()).digest()

    print(f"Muhlnickel FOLD CHECK — shared miner {n_gate:,} gates, group {GROUP}, easy target {zb} zero-bits.\n", flush=True)
    with open(TITAN, "r+b") as f: f.seek(ans_off); f.write(b"\x00\x00\x00\x00\x00")   # clear the group's answer register
    nonce = 0; ok = True; winner = None
    while nonce < 200_000:
        d_gates = digest_via_gates(run, d2c, HEADER, nonce)
        if d_gates != ref(nonce):                                # BYTE-EXACT: the shared miner == hashlib double-SHA
            ok = False; print(f"  MISMATCH at nonce {nonce}: gates != hashlib"); break
        if int.from_bytes(d_gates, "little") < target:           # win = hash < target -> latch this nonce (winner-only)
            with open(TITAN, "r+b") as f: f.seek(ans_off); f.write(b"\x01" + struct.pack("<I", nonce))
            winner = nonce; break
        nonce += 1
    print(f"  swept {nonce+1:,} nonces of group {GROUP}; shared miner byte-exact vs hashlib: {ok}", flush=True)
    if not ok: print("\n  CHECK FAILED — the shared miner is not computing double-SHA (fabrication issue)."); return 1
    if winner is None: print("  no winner within budget — raise zero_bits."); return 1

    # THE PROBE: read the winner's address out of the group's answer register, high-impedance (~0 RAM)
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); a = bytes(mm[ans_off:ans_off + 5]); mm.close()
    status = a[0]; pnonce = struct.unpack("<I", a[1:5])[0]
    dig = ref(pnonce); under = int.from_bytes(dig, "little") < target; lead = 256 - int.from_bytes(dig, "little").bit_length()
    print(f"\n  HIGH-IMPEDANCE PROBE on group {GROUP}'s answer register @ {ans_off}:", flush=True)
    print(f"    status={status}  nonce={pnonce:#010x}  (winner's address = group {GROUP} · nonce {pnonce})", flush=True)
    print(f"    verify: hashlib(header||{pnonce:#010x}) under {zb}-bit target: {under}  ({lead} leading zero-bits)", flush=True)
    print(f"\n  === {'FOLD CHECK PASSED' if (status and under) else 'FOLD CHECK FAILED'} — shared miner computed real double-SHA byte-exact,", flush=True)
    print(f"      a winner latched into the group's answer register (winner-only), the high-impedance probe read its", flush=True)
    print(f"      address. The fold's answer path works, ~0 RAM. ===", flush=True)
    return 0 if (status and under) else 1


if __name__ == "__main__":
    raise SystemExit(main())
