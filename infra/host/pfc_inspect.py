#!/usr/bin/env python3
"""host/pfc_inspect.py — the Muhlnickel SCHEMATIC / BOARD INSPECTOR: read a stored circuit's structure from the params (owner 07-19).

See what actually got baked — MAGIC, gate/in/out counts, format, and the recorded I/O map/binding — so we can check the
wiring is right without loading or running the pfc. Max impedance: reads only the small header window (<= 64 B).

  python host/pfc_inspect.py           # overview of the miner parts
  python host/pfc_inspect.py <name>    # inspect one stored circuit / register in detail
"""
import json, mmap, struct, sys
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
sys.stdout.reconfigure(encoding="utf-8")

TITAN = PFCP.TITAN; REG = PFCP.REG
CAP = 64                                              # max impedance: only the header window


def header(off):
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + CAP]); mm.close()
    magic = b[:8]
    try: hdr = struct.unpack_from("<IIII", b, 8)          # (n_in, n_wire, n_gate, n_out) for TITANCIR/typed formats
    except Exception: hdr = None
    return magic, hdr


def main():
    reg = json.load(open(REG))
    if len(sys.argv) > 1:
        name = sys.argv[1]
        if name not in reg:
            print(f"{name} not in registry."); return 1
        e = reg[name]
        print(f"Muhlnickel INSPECT — {name}:", flush=True)
        for k, v in e.items():
            print(f"    {k}: {v}", flush=True)
        if isinstance(e, dict) and "offset" in e:
            magic, hdr = header(int(e["offset"]))
            print(f"    [params header] MAGIC={magic}  (n_in,n_wire,n_gate,n_out)={hdr}", flush=True)
        return 0
    print("Muhlnickel INSPECT — miner parts (registry + params headers, high-impedance, Muhlnickel not loaded):", flush=True)
    for name in ("pfc_mine", "pfc_exec_input", "nonce_reg", "loop_bit", "pfc_on", "receiver"):
        if name in reg and isinstance(reg[name], dict):
            e = reg[name]; off = e.get("offset")
            mg = ""
            if off is not None:
                magic, _ = header(int(off)); mg = f"  MAGIC={magic}"
            print(f"  {name:16s} off={off} len={e.get('len')} n_gate={e.get('n_gate')} "
                  f"n_in={e.get('n_in')} n_out={e.get('n_out')}{mg}", flush=True)
    if "pfc_mine" in reg:
        pm = reg["pfc_mine"]
        print("  pfc_mine I/O map:", {k: pm[k] for k in ("in_map", "out_map", "power_wire", "safezone") if k in pm}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
