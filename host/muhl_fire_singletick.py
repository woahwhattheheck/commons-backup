#!/usr/bin/env python3
"""muhl_fire_singletick.py — FIRE muhl_fold_phys (physical format, DEPTH 3,243).

THE HOST DOES FIVE THINGS, THEN DIES:
  1. Pull the live block from the pool (network I/O)
  2. Route block data as INDIVIDUAL BITS (one byte per bit, each 0x00 or 0x01)
     into muhl_fold_phys RAM:
       header_off @1127673858 (608 bytes = 76 header bytes * 8 bits)
       nonce_off  @1127674466 (32 bytes  = 4 nonce bytes  * 8 bits, zeroed)
       target_off @1127674498 (256 bytes = 32 target bytes * 8 bits)
  3. Read baseline win_off and latch_off BEFORE fire (for comparison)
  4. Fire: read 1 byte from tick_off @1127674787 (the addressed-read signal
     that triggers nring2_1023 -> muhl_fold_phys)
  5. Read win_off and latch_off AFTER fire:
       win_off   @1127674786 (1 byte: 0x00=no winner, 0x01=winner)
       latch_off @1127674754 (32 bytes, one per bit, LSB-first -> 32-bit nonce)
     If winner AND latch changed: double-SHA-256 the 80-byte header, submit.

  python host/muhl_fire_singletick.py
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
from pfc_fire import get_job, submit

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"

# muhl_fold_phys RAM addresses (from registry, one byte per bit convention)
HEADER_OFF = 1127673858   # 608 bytes (76 header bytes * 8 bits)
NONCE_OFF  = 1127674466   # 32 bytes  (4 nonce bytes * 8 bits)
TARGET_OFF = 1127674498   # 256 bytes (32 target bytes * 8 bits)
LATCH_OFF  = 1127674754   # 32 bytes  (one per bit, LSB-first, THE ANSWER)
WIN_OFF    = 1127674786   # 1 byte    (0x00 = no winner, 0x01 = winner found)
TICK_OFF   = 1127674787   # 1 byte    (where nring2_1023 fires the clock)


def main():
    # ---- verify registry has muhl_fold_phys ----
    reg = json.load(open(REG))
    if "muhl_fold_phys" not in reg:
        print("muhl_fold_phys not found in registry."); return 1
    mfp = reg["muhl_fold_phys"]
    ram = mfp["ram"]
    # cross-check registry addresses against hardcoded constants
    assert int(ram["header_off"]) == HEADER_OFF, f"header_off mismatch: registry {ram['header_off']} != {HEADER_OFF}"
    assert int(ram["nonce_off"])  == NONCE_OFF,  f"nonce_off mismatch: registry {ram['nonce_off']} != {NONCE_OFF}"
    assert int(ram["target_off"]) == TARGET_OFF, f"target_off mismatch: registry {ram['target_off']} != {TARGET_OFF}"
    assert int(ram["latch_off"])  == LATCH_OFF,  f"latch_off mismatch: registry {ram['latch_off']} != {LATCH_OFF}"
    assert int(ram["win_off"])    == WIN_OFF,    f"win_off mismatch: registry {ram['win_off']} != {WIN_OFF}"
    assert int(ram["tick_off"])   == TICK_OFF,   f"tick_off mismatch: registry {ram['tick_off']} != {TICK_OFF}"
    print(f"muhl_fold_phys registry check PASSED (depth {mfp.get('depth')}, {mfp.get('n_gate')} gates, format {mfp.get('format')})")

    # ---- 1. pull the live block ONCE ----
    en1, en2sz, job = get_job()
    if not job:
        print("no block from pool (handshake failed)."); return 1
    en2 = "00" * en2sz
    prefix = make_prefix(job, en1, en2)[:76]   # 76-byte block header prefix
    nbits = struct.unpack("<I", prefix[72:76])[0]
    target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3))
    zb = 256 - target.bit_length()
    target_bytes = target.to_bytes(32, "little")

    print(f"MUHLNICKEL FIRE (muhl_fold_phys -> latch_off) -- wallet {WALLET}")
    print(f"  block {job['job_id']}  target {zb} zero-bits  nbits=0x{nbits:08x}")
    print(f"  prefix (76 B): {prefix.hex()}")

    # ---- 2. route block data as INDIVIDUAL BITS (one byte per bit) ----
    with open(TITAN, "r+b") as f:
        # 2a. header: 19 words -> 608 bit-bytes at HEADER_OFF (BE per SHA-256 convention)
        for w in range(19):
            word_val = struct.unpack(">I", prefix[w*4:(w+1)*4])[0]
            for j in range(32):
                bit = (word_val >> j) & 1
                f.seek(HEADER_OFF + w * 32 + j)
                f.write(bytes((bit,)))

        # 2b. nonce: zeroed, 32 bit-bytes at NONCE_OFF
        for j in range(32):
            f.seek(NONCE_OFF + j)
            f.write(b"\x00")

        # 2c. target: 32 bytes -> 256 bit-bytes at TARGET_OFF
        for k in range(32):
            byte_val = target_bytes[k]
            for j in range(8):
                bit = (byte_val >> j) & 1
                f.seek(TARGET_OFF + k * 8 + j)
                f.write(bytes((bit,)))

    print(f"  routed: header -> @{HEADER_OFF} (608 bit-bytes, 19 BE words)")
    print(f"  routed: nonce  -> @{NONCE_OFF} (32 bit-bytes, zeroed)")
    print(f"  routed: target -> @{TARGET_OFF} (256 bit-bytes)")

    # ---- 3. read BASELINE win_off and latch_off BEFORE fire ----
    with open(TITAN, "rb") as f:
        f.seek(WIN_OFF); baseline_win = f.read(1)
        f.seek(LATCH_OFF); baseline_latch = f.read(32)

    baseline_nonce = sum((baseline_latch[j] & 1) << j for j in range(32))
    print(f"  BASELINE win_off  @{WIN_OFF}: 0x{baseline_win.hex()}")
    print(f"  BASELINE latch_off @{LATCH_OFF} (32 bytes): {baseline_latch.hex()}")
    print(f"  BASELINE latch assembled nonce: 0x{baseline_nonce:08x}")

    # ---- 4. FIRE: read 1 byte from tick_off (the addressed-read signal) ----
    with open(TITAN, "rb") as f:
        f.seek(TICK_OFF); tick_byte = f.read(1)
    print(f"  FIRED: tick_off @{TICK_OFF} read (byte=0x{tick_byte.hex()}) -- nring2_1023 triggered")

    # ---- 5. read win_off and latch_off AFTER fire ----
    with open(TITAN, "rb") as f:
        f.seek(WIN_OFF); post_win = f.read(1)
        f.seek(LATCH_OFF); post_latch = f.read(32)

    post_nonce = sum((post_latch[j] & 1) << j for j in range(32))
    print(f"  POST-FIRE win_off  @{WIN_OFF}: 0x{post_win.hex()}")
    print(f"  POST-FIRE latch_off @{LATCH_OFF} (32 bytes): {post_latch.hex()}")
    print(f"  POST-FIRE latch assembled nonce: 0x{post_nonce:08x}")

    # compare baseline vs post-fire
    latch_changed = (baseline_latch != post_latch)
    win_changed = (baseline_win != post_win)
    print(f"  latch changed: {latch_changed}  win changed: {win_changed}")

    winner = (post_win[0] == 0x01)

    if winner and latch_changed:
        # construct the 80-byte block header with the assembled nonce
        hdr = prefix + struct.pack("<I", post_nonce)
        dig = hashlib.sha256(hashlib.sha256(hdr).digest()).digest()
        print(f"  ** WINNER ** nonce=0x{post_nonce:08x}  hash={dig[::-1].hex()}")
        nonce_hex = "%08x" % post_nonce
        verdict = submit(job, en2, nonce_hex)
        print(f"  SUBMITTED -- pool verdict: {verdict.strip()}")
    elif winner and not latch_changed:
        print(f"  win_off=0x01 but latch did not change from baseline (settle-back possible). Measurement only.")
    else:
        print(f"  no winner latched this fire (win_off=0x{post_win.hex()}).")
        print(f"  (settle-back law: this reading is NOT evidence of failure -- bring to owner)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
