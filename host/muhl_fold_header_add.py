#!/usr/bin/env python3
"""host/muhl_fold_header_add.py — moonshot fold header routing button (additive).

Fetches and prints a live 80-byte Bitcoin header + 32-byte target for
muhl_fold_phys. Does not write titan. Does not fire. Does not SHA as the mine.

The 80-byte header is the inject payload for host/muhl_fold_tick_add.py
(76-byte prefix + 4-byte nonce field; nonce IS the address, so nonce bytes
print as zeros). Packed-76 gen_input is a different mouth — refused.

Default --dry: registry plan only, no network, no write.
--fetch: one pool handshake, print 80-byte header hex + target hex, die.
--go is refused. This button never writes titan.

  python host/muhl_fold_header_add.py
  python host/muhl_fold_header_add.py --dry
  python host/muhl_fold_header_add.py --fetch
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import pfc_paths as PFCP
    TITAN = PFCP.TITAN
    REG = PFCP.REG
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    TITAN = PFC_ROOT + "/models/titan.gguf"
    REG = PFC_ROOT + "/models/titan_circuits.json"

try:
    from pfc_bitcoin_autopilot import make_prefix, WALLET, POOL_HOST, POOL_PORT
except ImportError:
    make_prefix = None
    WALLET = None
    POOL_HOST = None
    POOL_PORT = None

from bitcoin_compact import target_for_job

FOLD_NAME = "muhl_fold_phys"
RING_NAME = "nring2_1023"
HEADER_BITS = 608
TARGET_BITS = 256
PACKED_HEADER80 = 80
PACKED_HEADER76 = 76
PACKED_TARGET32 = 32

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _need_int(obj, key, where):
    if not isinstance(obj, dict) or obj.get(key) is None:
        return None, "%s missing %s" % (where, key)
    try:
        val = int(obj[key])
    except (TypeError, ValueError):
        return None, "%s.%s is not an int" % (where, key)
    if val < 0:
        return None, "%s.%s is negative" % (where, key)
    return val, None


def _load_registry():
    if not os.path.isfile(REG):
        return None, "registry missing: %s" % REG
    try:
        with open(REG, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "registry unreadable: %s" % exc


def load_plan():
    """Fail closed if fold/ring names or offsets are missing. Never guess."""
    if make_prefix is None:
        return None, "pfc_bitcoin_autopilot missing (make_prefix / pool constants)"
    reg, err = _load_registry()
    if err:
        return None, err
    if FOLD_NAME not in reg or not isinstance(reg[FOLD_NAME], dict):
        return None, "%s not in registry" % FOLD_NAME
    if RING_NAME not in reg or not isinstance(reg[RING_NAME], dict):
        return None, "%s not in registry" % RING_NAME

    fold = reg[FOLD_NAME]
    ring = reg[RING_NAME]
    ram = fold.get("ram")
    if not isinstance(ram, dict):
        return None, "%s missing ram" % FOLD_NAME

    offs = {}
    for key in ("header_off", "target_off"):
        val, err = _need_int(ram, key, "%s.ram" % FOLD_NAME)
        if err:
            return None, err
        offs[key] = val

    for key in ("tick_off", "win_off", "latch_off", "nonce_off"):
        val, err = _need_int(ram, key, "%s.ram" % FOLD_NAME)
        if err:
            offs[key] = None
        else:
            offs[key] = val

    ring_recv, err = _need_int(ring, "recv", RING_NAME)
    if err:
        ram_r = ring.get("ram")
        if isinstance(ram_r, dict):
            ring_recv, err = _need_int(ram_r, "recv", "%s.ram" % RING_NAME)
        if err:
            return None, err

    need_bryce = []
    tick = offs.get("tick_off")
    if tick is not None and tick != ring_recv:
        need_bryce.append(
            "tick_off %d != %s.recv %d — do not invent a second physics"
            % (tick, RING_NAME, ring_recv)
        )
    if tick is None:
        need_bryce.append("%s.ram.tick_off missing (surface/start named on the tick button)"
                          % FOLD_NAME)

    return {
        "fold": fold,
        "ring": ring,
        "offs": offs,
        "ring_recv": ring_recv,
        "need_bryce": need_bryce,
        "titan_exists": os.path.isfile(TITAN),
        "titan_size": os.path.getsize(TITAN) if os.path.isfile(TITAN) else None,
    }, None


def print_plan(plan):
    fold = plan["fold"]
    offs = plan["offs"]
    print("\nMUHL FOLD HEADER (additive routing button — print only)")
    print("  mode:     DRY — plan only, no titan write")
    print("  titan:    %s" % TITAN)
    print("  reg:      %s" % REG)
    print("  circuit:  %s  magic=%s  n_gate=%s  depth=%s"
          % (FOLD_NAME, fold.get("magic"), fold.get("n_gate"), fold.get("depth")))
    print("  power:    %s  recv=%s" % (RING_NAME, plan["ring_recv"]))
    print("  wallet:   %s" % WALLET)
    print("  pool:     %s:%s" % (POOL_HOST, POOL_PORT))
    print("  payload:  80 packed header bytes (76 prefix + 4 nonce field = 0)")
    print("  law:      nonce IS the address — nonce bytes are not the mine")
    print("  refuse:   packed-76 gen_input / target_reg / receiver (pfc_fire path)")
    print("  refuse:   titan write / --go / host-eval SHA as the mine")
    print()
    print("  INJECT MOUTH (named fields; this button does not write them)")
    print("    header_off  %s  (%d bit-bytes after unpack, LSB-first)"
          % (offs["header_off"], HEADER_BITS))
    print("    target_off  %s  (%d bit-bytes after unpack)"
          % (offs["target_off"], TARGET_BITS))
    if offs.get("nonce_off") is not None:
        print("    nonce_off   %s  (NOT injected — nonce IS the address)"
              % offs["nonce_off"])
    print()
    print("  START / SURFACE (the tick button; named here, not fired here)")
    if offs.get("tick_off") is not None:
        print("    tick_off    %s  (IS %s.recv %s)"
              % (offs["tick_off"], RING_NAME, plan["ring_recv"]))
    if offs.get("win_off") is not None:
        print("    win_off     %s  (1 byte)" % offs["win_off"])
    if offs.get("latch_off") is not None:
        print("    latch_off   %s  (32 bit-bytes)" % offs["latch_off"])
    print()
    if plan["need_bryce"]:
        print("  NEED_BRYCE (do not inject / do not fire):")
        for reason in plan["need_bryce"]:
            print("    - %s" % reason)
        print()
    print("  --fetch  one pool handshake, print header80 + target32 hex, still no write")
    print("  next     python host/muhl_fold_tick_add.py --dry")
    print("  (no write performed)")
    print()
    return 0


def get_job():
    """ONE pool handshake: pull the live block, then disconnect. No titan."""
    s = socket.create_connection((POOL_HOST, POOL_PORT), timeout=15)
    buf = b""

    def send(o):
        s.sendall((json.dumps(o) + "\n").encode())

    def lines():
        nonlocal buf
        out = []
        s.settimeout(2)
        try:
            buf += s.recv(8192)
        except Exception:
            pass
        while b"\n" in buf:
            ln, buf = buf.split(b"\n", 1)
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
        return out

    send({"id": 1, "method": "mining.subscribe", "params": ["muhl-fold-header/1.0"]})
    en1 = None
    en2sz = 8
    job = None
    t = time.time() + 15
    while time.time() < t and (en1 is None or job is None):
        for m in lines():
            if m.get("id") == 1 and m.get("result"):
                en1 = m["result"][1]
                en2sz = m["result"][2]
                send({"id": 2, "method": "mining.authorize", "params": [WALLET, "x"]})
            elif m.get("method") == "mining.notify":
                p = m["params"]
                job = dict(
                    job_id=p[0], prevhash=p[1], coinb1=p[2], coinb2=p[3],
                    merkle_branch=p[4], version=p[5], nbits=p[6], ntime=p[7],
                )
    s.close()
    return en1, en2sz, job


def fetch_print(plan):
    if plan["need_bryce"]:
        print_plan(plan)
        print("FETCH REFUSED: NEED_BRYCE — do not invent offsets.\n")
        return 1
    print_plan(plan)
    en1, en2sz, job = get_job()
    if not job:
        return _fail("no block from pool (handshake failed)")
    en2 = "00" * int(en2sz)
    prefix = make_prefix(job, en1, en2)
    if len(prefix) < PACKED_HEADER76:
        return _fail("prefix shorter than 76 bytes (got %d)" % len(prefix))
    prefix76 = prefix[:PACKED_HEADER76]
    header80 = prefix76 + struct.pack("<I", 0)
    if len(header80) != PACKED_HEADER80:
        return _fail("header assembly is not 80 bytes (got %d)" % len(header80))
    try:
        nbits, target_int = target_for_job(job, prefix76)
    except ValueError as exc:
        return _fail("invalid same-job compact target: %s" % exc)
    target32 = target_int.to_bytes(PACKED_TARGET32, "little")
    zb = 256 - target_int.bit_length()
    print("FETCH — live 80-byte header (print only, no titan write)\n")
    print("  block     %s" % job["job_id"])
    print("  nbits     0x%08x  target zero-bits %s" % (nbits, zb))
    print("  header80  %s" % header80.hex())
    print("  header80  %d packed bytes (76 prefix + 4 nonce field = 0)" % len(header80))
    print("  target32  %s" % target32.hex())
    print("  target32  %d packed bytes" % len(target32))
    print("  unpack    80 packed -> %d bit-bytes at header_off; 32 packed -> %d bit-bytes at target_off"
          % (HEADER_BITS, TARGET_BITS))
    print("  refuse    this hex is not a packed-76 gen_input write")
    print("  next dry  python host/muhl_fold_tick_add.py --dry")
    print("  Bryce fire uses the existing tick button with --header / --target; this scan does not pass --go")
    print()
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if "--go" in a:
        return _fail("--go refused on the header button (never writes titan)")
    plan, err = load_plan()
    if err:
        return _fail(err)
    if "--fetch" in a:
        return fetch_print(plan)
    return print_plan(plan)


if __name__ == "__main__":
    raise SystemExit(main())
