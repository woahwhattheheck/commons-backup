#!/usr/bin/env python3
"""host/wb_dump_all.py — press EVERY White Box button on EVERY unmodified model, dump all of it to the Desktop.

Owner spec (07-16): "every bit of data the White Box collects on any model that isn't modified by it." So this runs
EVERY read-only op in the worker's OPS table (not just `archive`) on every local model that is NOT Titan and NOT an
SDC-modified file — each op in its own gated ENDING sandbox process (whitebox_worker.py), frozen result copied into the
model's folder under the Desktop archive root. Structural ops always run; embedding ops (decompile/meaning/analogy/
token_neurons/direction) need the index sidecar, which `anatomy` builds first (compute, NO wifi). Metered-wifi safe:
everything is a local mmap read, zero network. Sequential, single worker at a time, nothing lingers.
"""
import json, os, subprocess, sys, time
HOST = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HOST)
sys.stdout.reconfigure(encoding="utf-8")

ARCH_ROOT = "C:/Users/lucys/OneDrive/Desktop/WhiteBox_Research_Archive"
MODELS_DIR = "C:/llm/models"
EXCLUDE = {"titan.gguf", "titan_test.gguf", "titan_sdc.gguf"}      # the files WE modified — not "unmodified"
WORKER = os.path.join(HOST, "whitebox_worker.py")

# every READ-ONLY button. (mutating ops destroy/scale/paste/edittoken/align_edit/revert/create are EXCLUDED — we
# collect data, we do not modify.) kw filled per-model after anatomy tells us layer count / a real tensor name.
def op_plan(nlayers, sample_tensor, expert_tensor, mid):
    plan = [
        ("anatomy", {}), ("precision", {}), ("layerroles", {}), ("osmap", {}),
        ("layerscan", {"role": "ffn_down"}), ("genome", {}),
    ]
    for L in sorted({0, mid, max(0, nlayers - 1)}):
        plan.append((f"circuitry@{L}", {"layer": str(L)}))
        plan.append((f"interconnect@{L}", {"layer": str(L)}))
    if sample_tensor: plan.append(("tensor", {"name": sample_tensor}))
    if expert_tensor: plan.append(("experts", {"name": expert_tensor}))
    # embedding-space buttons (need the index; anatomy built it). words chosen to be universal.
    for w in ("king", "true", "good"):
        plan.append((f"decompile:{w}", {"word": w}))
        plan.append((f"token_neurons:{w}", {"word": w, "layer": str(max(0, nlayers - 1)), "kind": "down"}))
    plan.append(("meaning:king", {"q": "king"}))
    plan.append(("analogy:k-m+w", {"a": "king", "b": "man", "c": "woman"}))
    plan.append(("direction:good-bad", {"right": "good", "wrong": "bad", "layer": str(mid), "kind": "down", "k": "14"}))
    plan.append(("param_scan", {"layer": str(mid), "kind": "down", "n": "48"}))
    return plan


def base_op(label): return label.split("@")[0].split(":")[0]


def run_worker(op, path, kw, result):
    p = subprocess.run([sys.executable, WORKER, "--op", op, "--path", path, "--kw", json.dumps(kw), "--result", result],
                       capture_output=True, text=True, timeout=900)
    try: return json.load(open(result, encoding="utf-8"))
    except Exception: return {"error": "no result", "stderr": (p.stderr or "")[-200:]}


def main():
    only = None
    for i, a in enumerate(sys.argv[1:]):
        if a == "--only": only = sys.argv[i + 2]
    models = sorted((f for f in os.listdir(MODELS_DIR)
                     if f.endswith(".gguf") and f not in EXCLUDE and not f.startswith("titan")),
                    key=lambda f: os.path.getsize(os.path.join(MODELS_DIR, f)))   # small first = fast feedback
    if only: models = [m for m in models if only.lower() in m.lower()]
    os.makedirs(ARCH_ROOT, exist_ok=True)
    print(f"pressing EVERY button on {len(models)} unmodified models -> {ARCH_ROOT}", flush=True)
    grand = {}
    for mi, mf in enumerate(models):
        path = f"{MODELS_DIR}/{mf}"; stem = os.path.splitext(mf)[0]
        adir = os.path.join(ARCH_ROOT, stem); bdir = os.path.join(adir, "buttons")
        os.makedirs(bdir, exist_ok=True)
        print(f"\n[{mi+1}/{len(models)}] {mf}", flush=True)

        # 1) the full archive button (weights + export_all bundle)
        arch = run_worker("archive", path, {"full": "0"}, os.path.join(bdir, "_archive.json"))
        print(f"    archive: {arch.get('ok')} · {arch.get('n_tensors')} tensors · {arch.get('raw_MB')} MB", flush=True)

        # 2) anatomy first (builds the index sidecar the embedding buttons need), learn layers + a tensor name
        ana = run_worker("anatomy", path, {}, os.path.join(bdir, "anatomy.json"))
        nlayers = int(ana.get("layers") or 0) or 32; mid = nlayers // 2
        sample_tensor = expert_tensor = None
        try:
            idx = json.load(open(path + ".wbindex.json", encoding="utf-8"))
            for t in idx.get("tensors", []):
                nm = t.get("name", "")
                if sample_tensor is None and nm.endswith("ffn_down.weight"): sample_tensor = nm
                if expert_tensor is None and "exps" in nm: expert_tensor = nm
            if sample_tensor is None:
                for t in idx.get("tensors", []):
                    if t.get("name", "").endswith(".weight"): sample_tensor = t["name"]; break
        except Exception: pass

        # 3) press every remaining button
        results = {"archive": arch.get("ok"), "anatomy": ("error" not in ana)}
        for label, kw in op_plan(nlayers, sample_tensor, expert_tensor, mid):
            if base_op(label) in ("anatomy",): continue
            safe = label.replace("@", "_L").replace(":", "_").replace("+", "").replace("-", "_")
            out = run_worker(base_op(label), path, kw, os.path.join(bdir, safe + ".json"))
            ok = isinstance(out, dict) and "error" not in out
            results[label] = ok
            print(f"    {'OK ' if ok else 'ERR'} {label}" + ("" if ok else f"  ({str(out.get('error'))[:60]})"), flush=True)
        grand[mf] = {"archive_MB": arch.get("raw_MB"), "layers": nlayers, "buttons": results,
                     "ok_count": sum(1 for v in results.values() if v), "total": len(results)}
        json.dump(grand, open(os.path.join(ARCH_ROOT, "_INDEX.json"), "w"), indent=1)

    # top-level readme
    L = ["# White Box Research Archive — every button, every unmodified model\n",
         "Each model folder holds `buttons/` (every White Box read, frozen to JSON) + the full `_archive.json` bundle",
         "(weights + samples + structure). All read from stored bits — no inference, no model load, pure Python, no",
         "network. The three Titan/SDC files are excluded (they were modified by the White Box).\n", "## Coverage\n",
         "| model | layers | buttons OK | archive MB |", "|---|--:|--:|--:|"]
    for mf, g in grand.items():
        L.append(f"| {mf} | {g['layers']} | {g['ok_count']}/{g['total']} | {g['archive_MB']} |")
    open(os.path.join(ARCH_ROOT, "README.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"\n[done] {len(models)} models pressed. index -> {ARCH_ROOT}/_INDEX.json", flush=True)


if __name__ == "__main__":
    main()
