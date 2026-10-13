#!/usr/bin/env python3
"""host/pfc_modelbuild.py — host routing for the Muhlnickel-native foundry request.

Host addresses a source GGUF, writes a foundry-request manifest, and displays
already-present tiles. Host does not import pfc_forward (that name collides with
quarantined offspec compute) and does not dequant, preslice, or fold. Offline
foundry: infra/host/pfc_modelbuild.py.

  python host/pfc_modelbuild.py <src.gguf> [name]     # write a foundry request
  python host/pfc_modelbuild.py <src.gguf> --status   # tiles already on disk
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

MODELS_DIR = "C:/llm/models/pfc"


def _cache_dir(src):
    stem = os.path.basename(src).replace(".gguf", "")
    return os.path.join(MODELS_DIR, stem)


def status(src):
    cache = _cache_dir(src)
    if not os.path.isdir(cache):
        print(f"{os.path.basename(src)}: no tile cache at {cache}")
        print("offline foundry: infra/host/pfc_modelbuild.py")
        return 0, 0
    tiles = [n for n in os.listdir(cache) if n.endswith(".wc")]
    bytes_ = sum(os.path.getsize(os.path.join(cache, n)) for n in tiles)
    print(f"{os.path.basename(src)}: {len(tiles)} tiles on disk · {bytes_/1e9:.2f} GB · cache {cache}")
    return len(tiles), len(tiles)


def fabricate(src, name=None, tile=2560, limit=None):
    """Write a foundry REQUEST. Host does not preslice or dequant."""
    if not os.path.exists(src):
        print(f"source not found: {src}")
        return 1
    name = name or os.path.basename(src)
    os.makedirs(MODELS_DIR, exist_ok=True)
    man = {
        "name": name,
        "source_gguf": src,
        "format": "pfc-native-foundry-request",
        "tile": tile,
        "limit": limit,
        "host": "address-only",
        "offline_foundry": "infra/host/pfc_modelbuild.py",
        "note": "host names the source; the foundry fabricates. No pfc_forward import.",
    }
    mp = os.path.join(MODELS_DIR, name + ".pfcmodel.json")
    json.dump(man, open(mp, "w"), indent=1)
    print(f"=== Muhlnickel FOUNDRY request: {name} ===")
    print(f"  source={src} tile={tile} limit={limit}")
    print(f"  request manifest {mp}")
    print("  host did not preslice, dequant, or fold. Offline foundry: infra/host/pfc_modelbuild.py")
    status(src)
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    src = sys.argv[1]; rest = sys.argv[2:]
    tile = 2560; limit = None; name = None
    if "--status" in rest:
        status(src); return 0
    i = 0
    while i < len(rest):
        if rest[i] == "--tile": tile = int(rest[i+1]); i += 2
        elif rest[i] == "--limit": limit = int(rest[i+1]); i += 2
        else: name = rest[i]; i += 1
    return fabricate(src, name=name, tile=tile, limit=limit)


if __name__ == "__main__":
    raise SystemExit(main())
