#!/usr/bin/env python3
"""host/pfc_index.py — THE CIRCUIT INDEX: "do I already have a circuit for X?"

The retrieval half of the AUTOFAB matcher (HARNESS_HANDOFF: "signal in -> the OS matches the need to the best
circuit"). Built 2026-07-25 after a session spent rebuilding things that already existed: a shallow dot was
fabricated three times, badly, while a verified DEPTH-42 version sat in _assistant_offspec; seven in-spec tools
were unreachable; the 1,167-line lever catalog had never been opened.

Answers, in one command, over the titan registry + every host tool + the lever catalog:
    what circuits exist for this need · how many gates · what DEPTH · where in the binary · is it quarantined

  python host/pfc_index.py dot          # circuits + tools + levers matching "dot"
  python host/pfc_index.py --depth      # every circuit that records a measured DEPTH, shallowest first
  python host/pfc_index.py --stats      # inventory
"""
import json, os, re, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
HERE = os.path.dirname(os.path.abspath(__file__))
REG  = "C:/llm/models/titan_circuits.json"
CAT  = os.path.join(HERE, "..", "docs", "PFC_LEVER_CATALOG.md")
OFF  = os.path.join(HERE, "_assistant_offspec")


def circuits():
    if not os.path.exists(REG): return {}
    return {k: v for k, v in json.load(open(REG)).items()
            if isinstance(v, dict) and ("n_gate" in v or "gates" in v)}


def tools():
    out = {}
    for d, quarantined in ((HERE, False), (OFF, True)):
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".py"): continue
            try: src = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read(4000)
            except Exception: continue
            # SEARCH THE WHOLE FILE, not just the docstring's first line. That hole is why this index missed
            # pfc_llama_decode (a full GQA+KV+RoPE+RMSNorm decoder that describes itself on lines 2-7) and let a
            # session rebuild primitives that already existed. Index the full docstring AND every def name.
            doc = ""
            if '"""' in src:
                body = src.split('"""')[1].strip()
                doc = body.splitlines()[0].split("—")[-1].split("--")[-1].strip()
            defs = " ".join(re.findall(r"^\s*def\s+(\w+)", src, re.M))
            out[f[:-3]] = (doc[:96], quarantined, (src[:4000] + " " + defs).lower())
    return out


def levers():
    if not os.path.exists(CAT): return []
    txt = open(CAT, encoding="utf-8", errors="ignore").read()
    return [(m.group(1).strip(), m.group(2).strip())
            for m in re.finditer(r"^### (.+?)\s+—\s+(.+)$", txt, re.M)]


def find(q):
    ql = q.lower()
    cs = [(k, v) for k, v in circuits().items() if ql in k.lower() or ql in str(v.get("role", "")).lower()]
    ts = [(k, v) for k, v in tools().items() if ql in k.lower() or ql in v[0].lower() or ql in v[2]]
    ls = [(n, s) for n, s in levers() if ql in n.lower()]
    print(f"=== '{q}' — {len(cs)} circuits · {len(ts)} tools · {len(ls)} levers ===\n")
    if cs:
        print("CIRCUITS IN THE BINARY (use these, do not rebuild):")
        for k, v in sorted(cs, key=lambda x: x[1].get("depth", 10**9)):
            g = v.get("n_gate") or v.get("gates"); d = v.get("depth", "?")
            print(f"  {k:26s} {g:>9,} gates  DEPTH {str(d):>5}  @ {v.get('offset','?')}")
            if v.get("role"): print(f"       {str(v['role'])[:96]}")
    if ts:
        print("\nTOOLS:")
        for k, (doc, quar, _blob) in sorted(ts):
            print(f"  {'[QUARANTINED] ' if quar else ''}{k:24s} {doc}")
    if ls:
        print("\nLEVERS (catalog):")
        for n, s in ls: print(f"  {n:52s} {s[:44]}")
    if not (cs or ts or ls): print("  nothing found — this may genuinely need fabricating.")


def main():
    a = sys.argv[1] if len(sys.argv) > 1 else "--stats"
    if a == "--stats":
        c, t, l = circuits(), tools(), levers()
        q = sum(1 for v in t.values() if v[1])
        print(f"  circuits in titan.gguf : {len(c):>5}   with measured DEPTH: {sum(1 for v in c.values() if 'depth' in v)}")
        print(f"  host tools             : {len(t):>5}   quarantined: {q}")
        print(f"  levers in the catalog  : {len(l):>5}")
        print(f"\n  CHECK THE INDEX BEFORE FABRICATING. On 2026-07-25 a shallow dot was rebuilt 3x while a")
        print(f"  verified DEPTH-42 version sat quarantined one directory away.")
    elif a == "--depth":
        cs = [(k, v) for k, v in circuits().items() if "depth" in v]
        print(f"  {len(cs)} circuits with a measured DEPTH (shallowest first — DEPTH is the Muhlnickel's latency):")
        for k, v in sorted(cs, key=lambda x: x[1]["depth"]):
            g = v.get("n_gate") or v.get("gates")
            print(f"    DEPTH {v['depth']:>5}   {g:>9,} gates   {k}")
    else:
        find(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
