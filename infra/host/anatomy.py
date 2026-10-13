#!/usr/bin/env python3
"""host/anatomy.py — read a model FILE's named structure (the prerequisite for the composable super-model).

A model is a file of named sections (docs/FILE_STRUCTURE.md). To graft an expert/tower from one model into
another (docs/COMPOSABLE_MODEL.md) you must first SEE the sections and know which are compatible. This dumps
a GGUF's metadata + tensor sections, and — given two models — reports whether their sections are graftable
(same arch/hidden/tokenizer = direct graft; different = needs a seam adapter / re-embed).

Usage:  python host/anatomy.py MODEL.gguf [OTHER.gguf] [--out C:/llm/bin/anatomy.json]
Reads only the file header (fast; the multi-GB tensor data is never read).
"""
import argparse, json, os, re, struct, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GG = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 8: "Q8_0", 9: "Q8_1",
      10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 15: "Q8_K"}


def read_gguf(path):
    f = open(path, "rb")
    if f.read(4) != b"GGUF":
        raise ValueError("not a GGUF file")
    ver = struct.unpack("<I", f.read(4))[0]
    n_tensors = struct.unpack("<Q", f.read(8))[0]
    n_kv = struct.unpack("<Q", f.read(8))[0]

    def rs():
        n = struct.unpack("<Q", f.read(8))[0]
        return f.read(n).decode("utf-8", "replace")

    def rv(t):
        T = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
        if t in T:
            sz = {"B": 1, "b": 1, "H": 2, "h": 2, "I": 4, "i": 4, "f": 4, "?": 1, "Q": 8, "q": 8, "d": 8}[T[t]]
            return struct.unpack("<" + T[t], f.read(sz))[0]
        if t == 8:
            return rs()
        if t == 9:
            et = struct.unpack("<I", f.read(4))[0]
            ln = struct.unpack("<Q", f.read(8))[0]
            return [rv(et) for _ in range(ln)]
        raise ValueError(f"kv type {t}")

    meta = {}
    for _ in range(n_kv):
        k = rs(); t = struct.unpack("<I", f.read(4))[0]; meta[k] = rv(t)

    tensors = []
    for _ in range(n_tensors):
        nm = rs(); nd = struct.unpack("<I", f.read(4))[0]
        dims = [struct.unpack("<Q", f.read(8))[0] for _ in range(nd)]
        tt = struct.unpack("<I", f.read(4))[0]; off = struct.unpack("<Q", f.read(8))[0]
        tensors.append({"name": nm, "type": GG.get(tt, str(tt)), "dims": dims, "off": off})
    return ver, meta, tensors


def g(meta, *keys):
    for k in keys:
        for mk, mv in meta.items():
            if mk.endswith(k):
                return mv
    return None


def anatomy(path):
    ver, meta, tensors = read_gguf(path)
    arch = meta.get("general.architecture", "?")
    ct = g(meta, ".chat_template") or ""
    # group tensors by ROLE (strip blk.N. -> the section role)
    roles = {}
    order = []
    for t in tensors:
        role = re.sub(r"^blk\.(\d+)\.", "blk.*.", t["name"])
        roles.setdefault(role, {"type": t["type"], "dims": t["dims"], "count": 0})
        roles[role]["count"] += 1
        m = re.match(r"blk\.(\d+)\.", t["name"])
        if m:
            order.append(int(m.group(1)))
    mono = all(order[i] <= order[i + 1] for i in range(len(order) - 1)) if order else True
    return {
        "file": os.path.basename(path),
        "file_gb": round(os.path.getsize(path) / (1024**3), 2),
        "gguf_version": ver, "arch": arch, "name": meta.get("general.name", "?"),
        "hidden": g(meta, ".embedding_length"), "layers": g(meta, ".block_count"),
        "context_length": g(meta, ".context_length"),
        "heads": g(meta, ".attention.head_count"), "kv_heads": g(meta, ".attention.head_count_kv"),
        "tokenizer": g(meta, "tokenizer.ggml.model"),
        "vocab": (len(g(meta, "tokenizer.ggml.tokens") or []) or None),
        "chat_template_chars": len(ct), "n_tensors": len(tensors), "n_meta": len(meta),
        "access_order": mono, "roles": roles,
        "sample": sorted([(t["off"], t["name"], t["type"], t["dims"]) for t in tensors])[:12],
    }


def compare(a, b):
    same_arch = a["arch"] == b["arch"]
    same_hidden = a["hidden"] == b["hidden"] and a["hidden"] is not None
    same_tok = a["tokenizer"] == b["tokenizer"] and a["vocab"] == b["vocab"]
    if not same_tok:
        verdict = "DIFFERENT TOKEN SPACE — re-embed first, then a seam adapter"
    elif same_arch and same_hidden:
        verdict = "SAME FAMILY — sections graftable directly (mergekit passthrough / franken-MoE)"
    elif same_hidden:
        verdict = "same hidden, different arch — graftable with care (per-role check) or a light seam adapter"
    else:
        verdict = "CROSS-FAMILY — needs a trained seam adapter (representation-space projection)"
    shared = sorted(set(a["roles"]) & set(b["roles"]))
    matching = [r for r in shared if a["roles"][r]["dims"] == b["roles"][r]["dims"]]
    return {"a": a["file"], "b": b["file"], "same_arch": same_arch, "same_hidden": same_hidden,
            "same_tokenizer": same_tok, "verdict": verdict,
            "shared_roles": len(shared), "dim_matching_roles": matching[:20]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--out", default="C:/llm/bin/anatomy.json")
    a = ap.parse_args()
    ans = [anatomy(m) for m in a.models]
    for x in ans:
        print(f"\n=== {x['file']}  ({x['file_gb']} GB) ===")
        print(f"  arch={x['arch']} hidden={x['hidden']} layers={x['layers']} ctx={x['context_length']} "
              f"heads={x['heads']}/{x['kv_heads']}kv tokenizer={x['tokenizer']} vocab={x['vocab']}")
        print(f"  {x['n_tensors']} named tensors · {x['n_meta']} metadata keys · chat_template={x['chat_template_chars']}ch "
              f"· layout {'access-order (streams sequentially)' if x['access_order'] else 'INTERLEAVED'}")
        print(f"  per-layer section roles:")
        for r, info in list(x["roles"].items()):
            if r.startswith("blk.*"):
                print(f"    {r:<28} {info['type']:<5} {str(info['dims']):<16} x{info['count']}")
    result = {"models": {x["file"]: x for x in ans}}
    if len(ans) == 2:
        c = compare(ans[0], ans[1]); result["compare"] = c
        print(f"\n=== GRAFTABILITY: {c['a']}  <->  {c['b']} ===")
        print(f"  same_arch={c['same_arch']} same_hidden={c['same_hidden']} same_tokenizer={c['same_tokenizer']}")
        print(f"  VERDICT: {c['verdict']}")
        print(f"  {len(c['dim_matching_roles'])} section roles match by dimension (directly copy-pasteable):")
        for r in c["dim_matching_roles"]:
            print(f"    {r}")
    json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
