#!/usr/bin/env python3
"""host/pfc_atlas.py — THE TITAN SILICON ATLAS (enumerate + categorize). Reads the authoritative circuit registry
(titan_circuits.json) and turns the flat list of 100+ baked gate-netlists into a legible map: family census, exact
total gate count, the CPU->program hierarchy, and floorplan (by offset). Read-only; opens no model, pulses nothing.

  python host/pfc_atlas.py            # print the census + write host/pfc_atlas_data.json
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import wb_config as _cfg                                       # PORTABILITY (distro)
REG = _cfg.circuits_registry()                                 # was C:/llm/models/titan_circuits.json
TITAN = _cfg.titan_model()                                     # was C:/llm/models/titan.gguf
OUT = os.path.join(HERE, "pfc_atlas_data.json")

# family classifier — ordered rules, first match wins. keyed on the registry name + role text + structural fields.
FAMILIES = ["CPU", "stored-program", "ALU / arithmetic", "crypto / miner", "memory / MMU",
            "demo / graphics", "ML / inference", "infra / register", "other"]


def classify(name, e):
    n = name.lower(); role = str(e.get("role", "")).lower(); isa = e.get("isa")
    has = lambda *ks: any(k in n or k in role for k in ks)
    if "runs_on" in e:                                             # a program that executes on a CPU
        return "stored-program"
    if isa or n in ("pfc_cpu", "pfc_cpu32", "pfc_cpu32r") or "stored-program cpu" in role or "processor" in role:
        return "CPU"
    if has("aes", "cipher", "sha", "mine", "miner", "nonce", "target", "winner", "fold", "lane", "hash", "merkle") \
       or n.startswith(("gen_", "miner", "selfclock", "clock_wide", "fanout", "header_from_index", "win_")):
        return "crypto / miner"
    if has("raycast", "doom", "life", "ca_rule", "tess", "gamegen", "rule", "ant", "brain") \
       or n.startswith(("gg_", "pix", "fly", "doom")):
        return "demo / graphics"
    if has("forward", "fwd", "lut", "silu", "exp_", "rsqrt", "dot", "matmul", "audio", "policy") \
       or n in ("mm_text", "mm_audio", "vm_step", "mz", "wb_fwd"):
        return "ML / inference"
    if has("mmu", "ram", "membus", "memo", "cache", "groups", "replication", "storage") \
       or n.startswith(("mmu_", "mem")):
        return "memory / MMU"
    if has("alu", "adder", "add", "sub", "mul", "mod", "mux", "min8", "max8", "cmp", "eq", "inc", "dec",
           "neg", "shl", "shr", "sat", "crc", "isqrt", "attest", "arith") \
       or n.startswith(("lib_", "g_", "r_", "prog_", "b_", "v_", "fp_")):
        return "ALU / arithmetic"
    if has("executor", "eval", "clock", "counter", "provenance", "breaker", "receiver", "input", "answer",
           "register", "reg", "window", "bit", "output", "sweep", "os_", "bitslice", "physical", "mbox", "seal") \
       or n.endswith(("_reg", "_input", "_answer", "_bit")):
        return "infra / register"
    return "other"


def main():
    reg = json.load(open(REG, encoding="utf-8"))
    fsize = os.path.getsize(TITAN) if os.path.exists(TITAN) else 40_028_316_800

    entries = []
    for name, e in reg.items():
        if not isinstance(e, dict):
            continue
        fam = classify(name, e)
        entries.append({
            "name": name, "family": fam,
            "n_gate": int(e.get("n_gate") or 0), "n_in": e.get("n_in"), "n_out": e.get("n_out"),
            "n_wire": e.get("n_wire"), "offset": e.get("offset"), "len": e.get("len"),
            "isa": e.get("isa"), "role": e.get("role"), "runs_on": e.get("runs_on"),
            "words": e.get("words"), "word": e.get("word"), "format": e.get("format"),
        })

    # family aggregates
    fam_stats = {}
    for f in FAMILIES:
        fe = [x for x in entries if x["family"] == f]
        fam_stats[f] = {"count": len(fe), "gates": sum(x["n_gate"] for x in fe),
                        "computers": sum(1 for x in fe if x["n_gate"] >= 1000)}
    total_gates = sum(x["n_gate"] for x in entries)
    computers = [x for x in entries if x["n_gate"] >= 1000]

    # CPU -> program hierarchy
    hierarchy = {}
    for x in entries:
        if x["runs_on"]:
            hierarchy.setdefault(x["runs_on"], []).append({"name": x["name"], "role": x["role"], "words": x["words"]})

    # gate-byte footprint (sum of registered lens that carry a circuit) vs file size
    circ_bytes = sum(int(e.get("len") or 0) for e in reg.values() if isinstance(e, dict) and e.get("n_gate"))

    out = {"file": os.path.basename(TITAN), "file_bytes": fsize, "n_registry": len(entries),
           "total_gates": total_gates, "n_computers": len(computers),
           "circuit_bytes": circ_bytes, "density_pct": round(circ_bytes / fsize * 100, 4),
           "families": fam_stats, "hierarchy": hierarchy, "entries": entries}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)

    # ---- readable census ----
    print(f"THE TITAN SILICON ATLAS  —  {os.path.basename(TITAN)}  ({fsize/1e9:.1f} GB)\n")
    print(f"  {len(entries)} registered circuits · {total_gates:,} total baked gates · "
          f"{len(computers)} are computers (>=1000 gates)")
    print(f"  circuit footprint {circ_bytes/1e6:.1f} MB = {out['density_pct']}% of the file "
          f"(the whole 40 GB is one chip; the logic is a rounding error)\n")
    print("  BY FAMILY:")
    for f in FAMILIES:
        s = fam_stats[f]
        if s["count"]:
            print(f"    {f:20s} {s['count']:>3} circuits · {s['gates']:>10,} gates · {s['computers']} computers")
    print("\n  THE BIGGEST COMPUTERS:")
    for x in sorted(computers, key=lambda x: -x["n_gate"])[:14]:
        tag = f" [{x['isa']}]" if x["isa"] else (f" — {x['role'][:48]}" if x["role"] else "")
        print(f"    {x['name']:18s} {x['n_gate']:>9,} gates  {x['family']}{tag}")
    print("\n  CPU -> PROGRAM HIERARCHY (stored programs that run on a baked CPU):")
    for cpu, progs in hierarchy.items():
        print(f"    {cpu}:  " + ", ".join(p["name"] for p in progs))
    print(f"\n  -> {OUT}")


if __name__ == "__main__":
    raise SystemExit(main())
