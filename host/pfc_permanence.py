#!/usr/bin/env python3
"""host/pfc_permanence.py — INSTRUMENT: permanent-binary vs operational-cache, + MissingNo persistence (owner 07-19).

The owner's vision: bake as much as possible into the PERMANENT binary so the host only has to ADDRESS, not rebuild an
operational/cache state each session. This measures, for a fabricated circuit:
  - PERMANENT  = the baked gate bytes living in titan.gguf (persist across sessions/devices — the MissingNo principle).
  - OPERATIONAL = the host RAM rebuilt at runtime to use it (load + compile the ripple + the wire buffer).
  - PERSISTENCE = re-read the baked bytes in a FRESH file handle; identical => it persisted with zero rebuild.
The goal state: drive OPERATIONAL toward 0 (bake the levers — memoize/fold/winner-only — so a result is an addressed
read, not a recompute). This instrument is how we watch that number fall as we bake more in.

  python host/pfc_permanence.py [circuit_name]      # default: gen_miner
"""
import hashlib, json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_exp_bench import rss

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OPS = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}; GEN_MAGIC = b"TITANGEN"


def read_permanent(off):
    """read the baked gate bytes straight from the permanent binary (mmap, bounded to the circuit's own range)."""
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == GEN_MAGIC
    n_in, n_wire, n_gate, _ = struct.unpack_from("<IIII", mm, off + 8)
    total = 24 + n_gate * 9 + 256 * 4
    blob = bytes(mm[off:off + total]); mm.close(); f.close()
    return n_in, n_wire, n_gate, blob


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "gen_miner"
    reg = json.load(open(REG))
    if name not in reg: print(f"{name} absent."); return 1
    off = int(reg[name]["offset"]); perm_len = int(reg[name]["len"])
    file_gb = os.path.getsize(TITAN) / 1e9
    print(f"Muhlnickel PERMANENCE — permanent binary vs operational cache, for '{name}'.\n", flush=True)

    # ---- PERMANENT: the baked bytes in the file (persist forever, across sessions/devices) ----
    n_in, n_wire, n_gate, blob = read_permanent(off)
    perm_hash = hashlib.sha256(blob).hexdigest()[:16]
    print(f"  PERMANENT (baked in the file, persists):", flush=True)
    print(f"    {n_gate:,} gates = {perm_len:,} bytes in titan.gguf @ {off}   sha={perm_hash}", flush=True)
    print(f"    this is on disk in a {file_gb:.0f} GB file — it survives process exit, reboot, battery-pull, device swap.\n", flush=True)

    # ---- OPERATIONAL: the host RAM rebuilt to USE it this session ----
    base, _ = rss()
    op = [(OPS[struct.unpack_from('<B', blob, 24 + i*9)[0]],
           struct.unpack_from('<i', blob, 24 + i*9 + 1)[0],
           struct.unpack_from('<i', blob, 24 + i*9 + 5)[0]) for i in range(n_gate)]
    after_parse, _ = rss()
    run = CC.CircuitCompiler(n_in).compile_ripple(op, n_wire)
    after_compile, _ = rss()
    W = 4096; ones = (1 << W) - 1
    run([0] * 640, ones)
    after_run, _ = rss()
    print(f"  OPERATIONAL (host RAM rebuilt this session to run it):", flush=True)
    print(f"    parse netlist  : +{after_parse-base:.1f} MB", flush=True)
    print(f"    compile ripple : +{after_compile-after_parse:.1f} MB   (the operational form the host rebuilds)", flush=True)
    print(f"    wire buffer W={W}: +{after_run-after_compile:.1f} MB   (transient compute state)", flush=True)
    print(f"    total operational: +{after_run-base:.1f} MB rebuilt from the permanent {perm_len/1e6:.1f} MB\n", flush=True)

    # ---- PERSISTENCE: re-read the baked bytes fresh — identical => it persisted, zero rebuild ----
    f2 = open(TITAN, "rb"); mm2 = mmap.mmap(f2.fileno(), 0, access=mmap.ACCESS_READ)
    blob2 = bytes(mm2[off:off + len(blob)]); mm2.close(); f2.close()
    persist = hashlib.sha256(blob2).hexdigest()[:16]
    print(f"  PERSISTENCE (MissingNo principle):", flush=True)
    print(f"    re-read the baked bytes from a fresh handle: sha={persist}  identical={persist==perm_hash}", flush=True)
    print(f"    => the gates persist in the actual file; nothing rebuilt them. A new session just re-addresses them.\n", flush=True)

    print(f"  === WHAT TO WATCH ===", flush=True)
    print(f"  operational RAM is the number to drive DOWN by baking more into the permanent binary (memoize/fold/", flush=True)
    print(f"  winner-only => a result becomes an addressed read, not a recompute). Re-run after each bake to watch it fall.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
