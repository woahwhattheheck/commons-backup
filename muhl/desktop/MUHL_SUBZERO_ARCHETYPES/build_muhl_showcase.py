#!/usr/bin/env python3
"""build_muhl_showcase.py — rebuild MUHLNICKEL.html from the stored circuits in titan.gguf.

MANUFACTURING STEP (offline, one-and-done). Reads stored circuits, embeds them as JSON in a
self-contained HTML file. Same pattern as host/export_doom_html.py.

  python build_muhl_showcase.py          # rebuild the showcase to the Desktop
  python build_muhl_showcase.py --check  # verify circuits exist without rebuilding
"""
import json, os, sys
sys.path.insert(0, "C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
import titan_circuit as TC
import titan_doom as D

DESK = "C:/Users/lucys/OneDrive/Desktop"
OUT = os.path.join(DESK, "MUHLNICKEL.html")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MUHLNICKEL_SHOWCASE.html")


def circuit_json(name):
    c = TC.load(name)
    return {"nin": c["n_in"], "nw": c["n_wire"], "ga": c["ga"], "gb": c["gb"], "outs": c["outs"]}


def main():
    mv, outs = D.build_movement()
    TC.store("doom_move", mv, outs, slot=3)
    import sdc_doom as SD
    SD.build_map()

    MOVE = circuit_json("doom_move")
    MAP = circuit_json("doom_map")
    print(f"circuits: movement {len(MOVE['ga'])} gates, map {len(MAP['ga'])} gates")

    cfg = {"TURN": D.TURN, "SPEED": D.SPEED, "CELL": D.CELL, "MAP": D.MAP,
           "MOVE": MOVE, "MAP_CIR": MAP,
           "moveGates": len(MOVE["ga"]), "mapGates": len(MAP["ga"])}

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    marker = "const CFG="
    idx = html.index(marker)
    end = html.index(";", idx)
    html = html[:idx] + marker + json.dumps(cfg, separators=(",", ":")) + html[end:]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {OUT}  ({len(html):,} bytes)")
    print("double-click MUHLNICKEL.html or MUHLNICKEL.bat on the Desktop.")


if __name__ == "__main__":
    if "--check" in sys.argv:
        for name in ("doom_move", "doom_map"):
            try:
                c = TC.load(name)
                print(f"  {name}: {len(c['ga'])} gates, {c['n_in']} inputs")
            except Exception as e:
                print(f"  {name}: NOT FOUND ({e})")
        sys.exit(0)
    main()
