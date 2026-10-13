#!/usr/bin/env python3
"""host/wb_consolidate.py — fold the per-model White Box dump into ONE doc with EVERY data point, verbatim.

Owner (07-16): "the button to dump all models needs EVERY SINGLE DATA POINT the White Box measures into one doc — ALL of
the data, exact, not summarized." So this does NOT curate or table-ify: it walks WhiteBox_Research_Archive/<model>/buttons/
and emits the FULL exact JSON of every White Box read, for every unmodified model, into one document. Each read is labeled
with what the White Box measures it as (per PATENT_2_WHITEBOX) so a researcher knows what they're looking at, but the DATA
is verbatim — nothing dropped, nothing rounded, nothing summarized. Pure file reads (no model load, no network).

  python host/wb_consolidate.py       # writes WHITEBOX_ALL_MODELS.md (+ .json) with every measurement, exact
"""
import glob, json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
ARCH = "C:/Users/lucys/OneDrive/Desktop/WhiteBox_Research_Archive"
DESK = "C:/Users/lucys/OneDrive/Desktop"
TITAN_JSON = "C:/Users/lucys/OneDrive/Desktop/TitanSDC/whitebox_titan.json"   # the White Box run on Titan itself

# Titan's section names (from whitebox_titan.json) -> what the White Box measures them as
TITAN_WHATIS = {
    "anatomy": "STRUCTURE — architecture, params, dims, experts, vocab, quant histogram",
    "tensors": "TENSOR LIST — every tensor in the file, name + shape + dtype",
    "precision_map": "PRECISION RECIPE — the numeric precision each tensor-role received (what the quantizer protected)",
    "os_map": "OS MAP — the computer in the weights: processor / memory / scheduler / IPC / storage / I-O codec",
    "depth_profile": "DEPTH PROFILE — per-layer std / mean / absmax / near-zero across the stack",
    "expert_health": "EXPERT HEALTH — per-expert std + dead-expert detection (MoE)",
    "tensor_stats": "TENSOR STATS — per-tensor mean/std/min/max/sparsity/histogram + quant-stress",
    "circuit_by_layer": "CIRCUITRY (transistors) — the gated-FFN block as transistors per sampled layer: gate gain, drain drive, rho; amp/inh/dead counts",
    "ipc_by_layer": "IPC BUS — attention as inter-token communication per head + GQA per sampled layer",
    "decompiler": "DECOMPILE — token meanings read as nearest stored neighbors, straight from the bits",
}

# what the White Box measures with each read (PATENT_2_WHITEBOX) — a label only; the DATA below it is verbatim.
WHATIS = {
    "anatomy": "STRUCTURE — architecture, params, dims, experts, vocab, every tensor + name + shape, quant histogram",
    "precision": "PRECISION RECIPE — the numeric precision each tensor-role received in the mixed-quant file (what the quantizer protected)",
    "layerroles": "LAYER ROLES — the tensor-role taxonomy per layer",
    "layerscan": "DEPTH PROFILE — per-layer std / mean / absmax / near-zero fraction across the whole stack",
    "tensor": "TENSOR STATS — per-tensor mean/std/min/max/sparsity/histogram + quant-stress",
    "experts": "EXPERT HEALTH — per-expert std + dead-expert detection (MoE)",
    "circuitry": "CIRCUITRY (transistors) — a gated-FFN block read as a bank of transistors: gate gain, drain drive, gate-source alignment rho; amplifier/inhibitor/dead counts, latches, decoder, histograms",
    "interconnect": "IPC BUS — attention read as inter-token communication per head + the GQA shared-KV structure",
    "osmap": "OS MAP — the computer-in-the-weights: which stored primitive plays processor / memory / scheduler / IPC / storage / I-O codec",
    "decompile": "DECOMPILE — a token's stored meaning read as its nearest stored neighbors, straight from the dequantized bits (no inference)",
    "meaning": "HIDDEN-MEANING SEARCH — the vocabulary ranked toward a concept centroid",
    "analogy": "ANALOGY — a:b::c:? solved in the stored embedding space",
    "direction": "ALIGNMENT AXIS — a right-vs-wrong concept axis and the tokens/params most aligned to it",
    "param_scan": "PARAM SCAN — individual stored parameters (a layer/kind slice) read as values",
    "token_neurons": "TOKEN NEURONS — the FFN neurons a token most activates, read from the weights",
    "genome": "GENOME — the reversible-edit journal (byte-exact undo record); empty = the file is pristine/unmodified",
    "_archive": "ARCHIVE MANIFEST — the export bundle descriptor (tensor count, sampled MB, timing, resident-RAM delta, analysis)",
}


def rd(p):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception as e: return {"_read_error": f"{type(e).__name__}: {e}"}


def base_op(fname):
    n = os.path.splitext(fname)[0]
    for k in WHATIS:
        if n == k or n.startswith(k + "_") or n.startswith(k + "L"):
            return k
    return n.split("_")[0].split("L")[0]


def main():
    dirs = sorted((d for d in glob.glob(os.path.join(ARCH, "*")) if os.path.isdir(d)),
                  key=lambda d: (rd(os.path.join(d, "buttons", "anatomy.json")) or {}).get("params_B") or 0)
    everything = {}                                            # model -> {button-file -> full data}, verbatim
    total_reads = 0
    L = ["# White Box — EVERY measurement, every unmodified model, one document",
         "",
         "Every data point the White Box measures, for every unmodified local model, verbatim — nothing summarized,",
         "nothing rounded, nothing dropped. Each read is labeled with what the White Box measures it as (per the White",
         "Box patent); the JSON beneath each label is the exact output. All read straight from the stored bits — no",
         "inference, no model load, pure Python, no network. Titan (the custom model) is read first, then the",
         "unmodified pool, sorted smallest to largest.", ""]

    # index
    titan = rd(TITAN_JSON) if os.path.exists(TITAN_JSON) else None
    L += ["## Models in this document", ""]
    if titan:
        L.append(f"- **titan.gguf** (the custom model — White Box run on Titan itself) — "
                 f"{len(titan.get('sections',{}))} White Box reads")
    for d in dirs:
        ana = rd(os.path.join(d, "buttons", "anatomy.json")) or {}
        nread = len(glob.glob(os.path.join(d, "buttons", "*.json")))
        L.append(f"- **{os.path.basename(d)}** — {ana.get('arch','?')}, {ana.get('params_B','?')}B, "
                 f"{ana.get('layers','?')} layers — {nread} White Box reads")
    L.append("")

    # Titan first — every section of its own White Box run, verbatim
    if titan:
        everything["titan.gguf"] = titan.get("sections", {})
        L += ["", "---", "", "# titan.gguf  (the custom model — White Box run on Titan itself)", "",
              f"*meta: {json.dumps(titan.get('meta', {}), ensure_ascii=False)}*", ""]
        for sec, data in titan.get("sections", {}).items():
            total_reads += 1
            L += [f"## {sec}", f"*{TITAN_WHATIS.get(sec, sec)}*", "", "```json",
                  json.dumps(data, indent=1, ensure_ascii=False), "```", ""]

    for d in dirs:
        model = os.path.basename(d); bdir = os.path.join(d, "buttons")
        files = sorted(glob.glob(os.path.join(bdir, "*.json")),
                       key=lambda p: (base_op(os.path.basename(p)), os.path.basename(p)))
        everything[model] = {}
        L += ["", "---", "", f"# {model}", ""]
        for fp in files:
            fn = os.path.basename(fp)
            data = rd(fp)
            everything[model][fn] = data
            total_reads += 1
            op = base_op(fn)
            label = WHATIS.get(op, op)
            L += [f"## {fn}", f"*{label}*", "", "```json",
                  json.dumps(data, indent=1, ensure_ascii=False),
                  "```", ""]

    md = "\n".join(L) + "\n"
    for out in (os.path.join(ARCH, "WHITEBOX_ALL_MODELS.md"), os.path.join(DESK, "WHITEBOX_ALL_MODELS.md")):
        open(out, "w", encoding="utf-8").write(md)
    json.dump(everything, open(os.path.join(ARCH, "WHITEBOX_ALL_MODELS.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)

    size_mb = len(md.encode("utf-8")) / 1048576
    print(f"consolidated {len(dirs)} models x every read = {total_reads} measurements, VERBATIM, into one doc:")
    print(f"  {os.path.join(DESK, 'WHITEBOX_ALL_MODELS.md')}  ({size_mb:.1f} MB — every data point, exact)")
    print(f"  {os.path.join(ARCH, 'WHITEBOX_ALL_MODELS.json')}  (machine-readable, full nested)")


if __name__ == "__main__":
    main()
