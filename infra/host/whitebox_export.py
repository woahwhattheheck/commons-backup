#!/usr/bin/env python3
"""whitebox_export.py — CLI wrapper: scrape ONE model into a per-model White Box artifact (json + md). All logic lives
in whitebox_app.export_all() — the SAME code path the White Box app's Export tab uses. No inference, no model load;
every read is a bounded window off the cached index + direct memmap (~0 RAM).

  python host/whitebox_export.py [--model C:/llm/models/titan.gguf] [--layers 0,mid,last]
                                 [--full-circuit] [--all-experts] [--decompile]
"""
import os, sys
HOST = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOST)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import whitebox_app as wb


def main():
    args = sys.argv[1:]
    model, layers, result = "C:/llm/models/titan.gguf", "0,mid,last", None
    for i, a in enumerate(args):
        if a == "--model" and i + 1 < len(args):
            model = args[i + 1].replace("\\", "/")
        if a == "--layers" and i + 1 < len(args):
            layers = args[i + 1]
        if a == "--result" and i + 1 < len(args):     # where to FREEZE the static handoff before this process ENDS
            result = args[i + 1]
    r = wb.export_all(model, layers=layers,
                      full_circuit="--full-circuit" in args,
                      all_experts="--all-experts" in args,
                      decompile="--decompile" in args,
                      log=lambda m: print(m, flush=True))
    # FREEZE: write the static result handoff, then this process EXITS (frees all compute — nothing keeps running).
    if result:
        import json
        try:
            with open(result, "w", encoding="utf-8") as f:
                json.dump(r, f)
        except Exception as e:
            print("[export] result-write failed:", e)
    if r.get("error"):
        print("[export] ERROR:", r["error"]); return 2
    print(f"\n[export] DONE {r['seconds']}s · system free-RAM drop {r['free_ram_drop_MB']} MB · {len(r['sections'])} sections"
          + (f" · errored: {', '.join(r['errors'])}" if r.get("errors") else "")
          + f"\n[export] wrote:\n  {r['json']}\n  {r['md']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
