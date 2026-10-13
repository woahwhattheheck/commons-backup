#!/usr/bin/env python3
"""host/pfc_map.py — CENSUS OF THE COMPUTERS IN THE FILE (owner: Bryce, 2026-07-21).

A high-impedance, structural instrument: it walks every baked circuit — the typed circuits in titan.gguf (registry) and
the game/render pfc in the sandbox — reads each netlist's gates, and computes its ELECTRON-SPEED DEPTH (critical path) and
gate count. No run, no ripple, no touching a running compute; it only reads stored structure. The output is a map of the
whole rack of computers living in one file, each with its latency in gate-delays.

  python host/pfc_map.py            # census every computer: gates, depth, role
"""
import json, os, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; SBX = "C:/llm/sdc_sandbox"


def depth_of(n_in, n_wire, gates_ab, outs):
    base = 2 + n_in; level = [0] * n_wire
    for k, (a, b) in enumerate(gates_ab):
        la = level[a] if a < n_wire else 0; lb = level[b] if b < n_wire else 0
        level[base + k] = 1 + (la if la >= lb else lb)
    return max((level[o] for o in outs if 2 <= o < n_wire), default=0)


def parse_typed(blob, hdr_extra=0):
    """PFCTYPED / PFCGAME1 / PFCRAY01 share: <8s magic><II..II n_in,n_wire,n_gate,n_out [+extra]> gates(<Bii>) outs(<i>)."""
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", blob, 8)
    p = 8 + 16 + hdr_extra * 4
    gates = []
    for _ in range(n_gate):
        _op, a, b = struct.unpack_from("<Bii", blob, p); p += 9; gates.append((a, b))
    outs = [struct.unpack_from("<i", blob, p + 4 * k)[0] for k in range(n_out)]
    return n_in, n_wire, gates, outs


def census():
    rows = []                                                     # (name, kind, gates, depth)
    # 1) typed circuits baked into titan.gguf, from the registry
    reg = json.load(open(REG))
    with open(TITAN, "rb") as f:
        for name, e in sorted(reg.items()):
            if not isinstance(e, dict): continue
            off, ln = e.get("offset"), e.get("len")
            if off is None or ln is None or int(ln) < 24 or int(ln) > 60_000_000: continue
            try:
                f.seek(int(off)); blob = f.read(int(ln))
                if blob[:8] != b"PFCTYPED": continue
                n_in, n_wire, gates, outs = parse_typed(blob)
                rows.append((name, e.get("role", "typed circuit")[:52], len(gates), depth_of(n_in, n_wire, gates, outs)))
            except Exception:
                continue
    # 2) game / render pfc in the sandbox (.pfc files)
    fmt = {b"PFCGAME1": 2, b"PFCRAY01": 0}                         # PFCGAME1 has 2 extra header words (GW,GH)
    for fn in sorted(os.listdir(SBX)) if os.path.isdir(SBX) else []:
        if not fn.endswith(".pfc"): continue
        try:
            blob = open(os.path.join(SBX, fn), "rb").read()
            if blob[:8] not in fmt: continue
            n_in, n_wire, gates, outs = parse_typed(blob, hdr_extra=fmt[blob[:8]])
            rows.append((fn, "arcade/render pfc", len(gates), depth_of(n_in, n_wire, gates, outs)))
        except Exception:
            continue
    return rows


def main():
    rows = census()
    rows.sort(key=lambda r: r[2])                                 # by gate count
    print(f"Muhlnickel CENSUS — {len(rows)} computers living in the file (structural read, no run):\n", flush=True)
    print(f"  {'name':22s} {'gates':>10s} {'DEPTH':>7s}   role", flush=True)
    print(f"  {'-'*22} {'-'*10} {'-'*7}   {'-'*40}", flush=True)
    for name, role, gates, d in rows:
        print(f"  {name:22s} {gates:>10,} {d:>7,}   {role}", flush=True)
    tg = sum(r[2] for r in rows)
    print(f"\n  {len(rows)} distinct computers, {tg:,} gates total — one file. each runs at its DEPTH in gate-delays", flush=True)
    print(f"  (electron speed), all at flat/falling host RAM (see docs/PFC_PROVEN_BY_MEASUREMENT.md ch.4).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
