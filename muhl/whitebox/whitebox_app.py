#!/usr/bin/env python3
"""host/whitebox_app.py — THE WHITE BOX: a desktop research instrument to IMPORT a parameter file and SEE + EDIT the bits.

Own UI (port 7862), separate from the lab. Point it at any .gguf and it reads the BITS directly (pure gguf-py + numpy —
no inference, no serving, RAM-safe on an 8 GB box via memmap + chunked math). It is a RESEARCH TOOL: show anything
someone might want to see, and let them edit it — reversibly. Tabs:

  OVERVIEW        — arch/params/dims/experts + the quant-type histogram (the anatomy).
  PRECISION MAP   — the mixed-quant RECIPE: which tensor ROLE (attn_q, ffn_down, token_embd, norms…) got which quant
                    (Q4_K/Q6_K/Q5_K/F32). The actual anatomy of the quantization scheme — no standard tool shows this.
  LAYERS          — go past token_embd into the real layers: per-layer std + near-zero% for a chosen tensor role, a
                    std-vs-depth sparkline (outlier features, dead neurons, layers that barely move).
  DECOMPILER      — bits -> meaning: a token's embedding row -> nearest tokens; VECTOR ARITHMETIC (king-man+woman->queen,
                    noisy on a quantized table = the measurable cost of quantization); BIT-EDIT -> MEASURE (edit a token's
                    stored bits, see the before/after neighbor list = "I changed what this token means at the storage
                    layer; here's the semantic damage"). Reversible.
  TENSOR SCOPE    — dequantize any tensor -> mean/std/min/max, sparsity, value histogram; QUANT STRESS (per-block outlier
                    magnitude — where the quantization hurts most).
  SEARCH+DESTROY  — search tensors/tokens/KV by name; targeted, REVERSIBLE pruning: zero a tensor, prune one MoE expert,
                    scale a tensor, scrub a token. The owner's "search and destroy so I can target my own pruning."
  GENOME          — every edit's byte-exact undo log; revert last / revert all.

Launch: WhiteBox.cmd (desktop) or `python host/whitebox_app.py`.
"""
import glob, json, os, re, subprocess, sys, tempfile, threading, time
import numpy as np
import gguf
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import decompile as _dc      # memmap decompiler: open_embed / decompile_mm / row_of / find_tok
except Exception:
    _dc = None
try:
    import wbedit as _wb         # the write side: search / destroy / scale / edit_token / genome / revert
except Exception:
    _wb = None
try:
    import forge_build as _fb     # CREATE a model from scratch, driven by the White-Box scan data (INV-149)
except Exception:
    _fb = None

MODELS_DIR = "C:/llm/models"
PORT = 7862
STATE = {"path": None, "anat": None, "vocab": None, "E_mm": None, "dim": None, "ety": None,
         "side": None, "loading": False, "err": "", "align_dir": None, "align_desc": ""}
LOCK = threading.Lock()
JOBS = {}                        # background scans: id -> {done, total, result, label}
# the decompiler embedding index is built ONCE per model in a BACKGROUND thread (cancellable) so clicking never blocks
# or stacks concurrent 2.95 GB builds ("ghost" work). EMBED is the single source of truth the UI polls.
EMBED = {"building": False, "ready": False, "err": "", "cancel": False, "progress": 0.0, "path": None}
EMBED_LOCK = threading.Lock()
# Parsing a 15–40 GB gguf's index takes ~20 s; CACHE the reader so anatomy/circuitry/param-decode reuse ONE parse
# instead of re-parsing per call (that re-parse was the 24 s in param_decode). The reader mmaps the file — no big RAM.
_RC = {"path": None, "r": None}


def _reader(path):
    if _RC["path"] == path and _RC["r"] is not None:
        return _RC["r"]
    r = gguf.GGUFReader(path)
    _RC.update(path=path, r=r)
    return r


def elems(shape):
    return int(np.prod([int(x) for x in shape]))


# ------------------------------------------------------------------ anatomy + precision map
# The GGUFReader parse is ~25 s (it decodes the 262 k-token tokenizer) — paid on every Import / model-switch / restart.
# anatomy() returns a serializable dict, so CACHE it to <model>.wbindex.json: a fresh cache makes the read INSTANT (no
# parse). The tensor index (name/type/shape) is stable across a devour (only the quantized values change), so anatomy /
# precision map / the System tab all read the cache. Only the first read of a new/changed model pays the 25 s.
def _index_path(p):
    return p + ".wbindex.json"


_INDEX_V = 3   # v3 caches head_count/head_count_kv so interconnect reads them with no parse; v2 added offset/tid/dshape


def _fresh_index(path):
    ip = _index_path(path)
    try:
        if os.path.exists(ip) and os.path.getmtime(ip) >= os.path.getmtime(path):
            d = json.load(open(ip, encoding="utf-8"))
            if d.get("v") == _INDEX_V:
                return d
    except Exception:
        pass
    return None


def _tinfo(path, name):
    """The cached index entry (name/type/shape/offset/tid/dshape/bytes) for ONE tensor — instant, no parse."""
    return next((x for x in anatomy(path).get("tensors", []) if x["name"] == name), None)


def _deq_mmap(path, t):
    """Read ONE tensor's VALUES directly off the memmap by its cached index entry — NO GGUFReader parse, no model load.
    F32/F16 are already float (a direct frombuffer view — block-dequant throws a size mismatch on them, which is exactly
    the bug that used to silently fall back to the 28 s parse); quantized types dequantize from their stored blocks. This
    IS the novel White-Box read, and keeping every path on it (never _reader) is what makes reads instant. Byte-exact."""
    tid = int(t["tid"]); dshape = tuple(t["dshape"])
    raw = np.memmap(path, dtype=np.uint8, mode="r", offset=int(t["offset"]), shape=(int(t["bytes"]),))
    if tid == 0:                                                    # F32 — already float, view it directly
        return np.frombuffer(bytes(raw), dtype=np.float32).reshape(dshape).astype(np.float32)
    if tid == 1:                                                    # F16
        return np.frombuffer(bytes(raw), dtype=np.float16).reshape(dshape).astype(np.float32)
    blocks = np.frombuffer(bytes(raw), dtype=np.uint8).reshape(dshape)
    return gguf.quants.dequantize(blocks, gguf.GGMLQuantizationType(tid)).astype(np.float32)


def _deq_rows(path, t, start, count):
    """Same direct memmap read as _deq_mmap, but only the block-rows [start, start+count) of axis 0 — so a SAMPLE (or one
    expert's slice) is read without dequantizing the whole tensor. Mirrors `t.data[start:start+count]` then dequantize."""
    tid = int(t["tid"]); dshape = tuple(t["dshape"]); r0 = int(dshape[0]); nby = int(t["bytes"])
    start = max(0, min(int(start), r0)); count = max(0, min(int(count), r0 - start))
    bpr = nby // r0                                                 # bytes per block-row
    raw = np.memmap(path, dtype=np.uint8, mode="r", offset=int(t["offset"]) + start * bpr, shape=(count * bpr,))
    if tid == 0:
        return np.frombuffer(bytes(raw), dtype=np.float32).astype(np.float32)
    if tid == 1:
        return np.frombuffer(bytes(raw), dtype=np.float16).astype(np.float32)
    blocks = np.frombuffer(bytes(raw), dtype=np.uint8).reshape((count,) + dshape[1:])
    return gguf.quants.dequantize(blocks, gguf.GGMLQuantizationType(tid)).astype(np.float32)


def _deq_head(path, t, max_bytes=2_000_000):
    """A BOUNDED window read: dequant only the first block-rows that fit in ~max_bytes of RAW STORED bytes, then STOP —
    so a giant OR expert-major tensor (where one row = a whole 2 MB expert) is never fully materialized (the SDC one-way
    rule: address the stored bits, hold only a small window, probe the result). Minimum one row; peak ~a few MB."""
    r0 = int(t["dshape"][0]); nby = int(t["bytes"]); bpr = max(1, nby // r0)   # bytes per block-row
    rows = max(1, min(r0, int(max_bytes) // bpr))
    return _deq_rows(path, t, 0, rows).ravel()


def _deq_expert_head(path, t, e, k_subrows=8):
    """Bounded per-EXPERT sample from an expert-major tensor whose dshape is [n_expert, rows_per_expert, row_bytes]:
    read only the first k sub-rows of expert e (block-aligned), not its whole ~2 MB slab — enough to measure its std /
    detect a dead expert, at ~0 RAM. Falls back to the whole row for non-3D layouts."""
    ds = t["dshape"]
    tid = int(t["tid"])
    if len(ds) < 3:
        return _deq_rows(path, t, e, 1)                             # not expert-major-3D → read expert row e (small here)
    rows, rb = int(ds[1]), int(ds[2])
    k = max(1, min(int(k_subrows), rows))
    off = int(t["offset"]) + int(e) * rows * rb
    raw = np.memmap(path, dtype=np.uint8, mode="r", offset=off, shape=(k * rb,))
    if tid == 0:
        return np.frombuffer(bytes(raw), dtype=np.float32).astype(np.float32)
    if tid == 1:
        return np.frombuffer(bytes(raw), dtype=np.float16).astype(np.float32)
    blocks = np.frombuffer(bytes(raw), dtype=np.uint8).reshape(k, rb)
    return gguf.quants.dequantize(blocks, gguf.GGMLQuantizationType(tid)).astype(np.float32)


def _deq_cached(path, name):
    """Dequantize ONE tensor WITHOUT the 24 s GGUFReader parse: look up its type/offset/block-shape in the cached index,
    memory-map its bytes, and dequantize (verified byte-identical to GGUFReader). Falls back to GGUFReader ONLY if the
    tensor isn't in a v2+ cache. Returns (float32 array, meta dict) or (None, error-dict); never raises."""
    a = anatomy(path)
    t = next((x for x in a.get("tensors", []) if x["name"] == name), None)
    if t is None:
        return None, {"error": f"no tensor {name}"}
    if "offset" in t and "tid" in t and "dshape" in t:
        try:
            return _deq_mmap(path, t), {"shape": t["shape"], "type": t["type"]}
        except Exception:
            pass
    try:
        tt = next((x for x in _reader(path).tensors if x.name == name), None)   # last-resort fallback: the parse
        if tt is None:
            return None, {"error": f"no tensor {name}"}
        return gguf.quants.dequantize(tt.data, tt.tensor_type).astype(np.float32), {"shape": t["shape"], "type": t["type"]}
    except Exception as e:
        return None, {"error": f"deq failed for {name}: {e}"}


def anatomy(path):
    cached = _fresh_index(path)
    if cached is not None:
        return cached                                            # INSTANT — no 25 s GGUFReader parse
    r = _reader(path)
    kv = {f.name: f for f in r.fields.values()}

    def gi(k):
        x = kv.get(k)
        try:
            return int(x.parts[x.data[-1]][0]) if x else None
        except Exception:
            return None

    def gs(k):
        x = kv.get(k)
        try:
            return bytes(x.parts[x.data[-1]]).decode("utf-8", "replace") if x else None
        except Exception:
            return None

    arch = gs("general.architecture") or "?"
    hid = gi(f"{arch}.embedding_length") or gi(f"{arch}.hidden_size")
    n_layer = gi(f"{arch}.block_count")
    n_exp = gi(f"{arch}.expert_count")
    n_used = gi(f"{arch}.expert_used_count")
    n_head = gi(f"{arch}.attention.head_count")            # cached in v3 so interconnect reads it without a parse
    n_head_kv = gi(f"{arch}.attention.head_count_kv")
    tok = kv.get("tokenizer.ggml.tokens")
    n_vocab = len(tok.data) if tok else None
    types = {}
    tens = []
    total = 0
    for t in r.tensors:
        types[t.tensor_type.name] = types.get(t.tensor_type.name, 0) + 1
        p = elems(t.shape)
        total += p
        tens.append({"name": t.name, "type": t.tensor_type.name,
                     "shape": [int(x) for x in t.shape], "params": p, "bytes": int(t.n_bytes),
                     "offset": int(t.data_offset), "tid": int(t.tensor_type), "dshape": [int(x) for x in t.data.shape]})
    # ── TITAN SDC: merge the REFERENCED components (the wiring over cold storage) — an mmap read, ZERO host RAM ──
    n_ref = 0
    if arch == "titan" and _wb is not None:
        try:
            for a in _wb.titan_added(path):
                p = 1
                for x in a["shape"]:
                    p *= int(x)
                total += p
                n_ref += 1
                types[a["type"]] = types.get(a["type"], 0) + 1
                tens.append({"name": a["name"], "type": a["type"], "shape": [int(x) for x in a["shape"]],
                             "params": p, "bytes": int(a.get("src_bytes", 0)), "offset": int(a.get("src_off", 0)),
                             "ref": os.path.basename(a.get("src", "")), "mode": a.get("mode", "ref")})
        except Exception:
            pass
    pc = total if n_ref else (gi("general.parameter_count") or total)
    tens.sort(key=lambda x: -x["params"])
    result = {"v": _INDEX_V, "file": os.path.basename(path), "path": path.replace("\\", "/"), "arch": arch,
              "params_B": round(pc / 1e9, 2), "hidden": hid, "layers": n_layer, "experts": n_exp,
              "expert_used": n_used, "head_count": n_head, "head_count_kv": n_head_kv,
              "vocab": n_vocab, "n_tensors": len(tens), "referenced": n_ref,
              "size_GB": round(os.path.getsize(path) / 1e9, 2),
              "types": [{"t": k, "n": v} for k, v in sorted(types.items(), key=lambda x: -x[1])],
              "tensors": tens}
    try:
        json.dump(result, open(_index_path(path), "w", encoding="utf-8"))   # cache so future reads skip the 25 s parse
    except Exception:
        pass
    return result


def _role(name):
    """collapse blk.N.<role> -> <role> so we can see the quant recipe by tensor ROLE, not per-layer copy."""
    m = re.sub(r"blk\.\d+\.", "", name)
    return m.replace(".weight", "").replace(".bias", "")


def precision_map(path):
    """the mixed-quant RECIPE: for each tensor role, which quant type(s) it got + how many params. Reads the CACHED index
    (via anatomy) — instant, no GGUFReader parse."""
    roles = {}
    for t in anatomy(path).get("tensors", []):
        rl = _role(t["name"])
        d = roles.setdefault(rl, {"role": rl, "types": {}, "params": 0, "n": 0})
        d["types"][t["type"]] = d["types"].get(t["type"], 0) + 1
        d["params"] += t["params"]
        d["n"] += 1
    # a bits-per-weight rank so the UI can color "which role got the better precision"
    BPW = {"F32": 32, "F16": 16, "BF16": 16, "Q8_0": 8.5, "Q6_K": 6.6, "Q5_K": 5.5, "Q5_0": 5.5,
           "Q4_K": 4.5, "Q4_0": 4.5, "Q3_K": 3.4, "Q2_K": 2.6}
    out = []
    for d in roles.values():
        main = max(d["types"].items(), key=lambda x: x[1])[0]
        out.append({"role": d["role"], "params": d["params"], "n": d["n"],
                    "types": [{"t": k, "n": v} for k, v in sorted(d["types"].items(), key=lambda x: -x[1])],
                    "bpw": BPW.get(main, 0), "main": main})
    out.sort(key=lambda x: -x["params"])
    return {"roles": out}


# ------------------------------------------------------------------ per-layer scan (into the real layers)

def _layer_roles(path):
    """distinct tensor roles that appear per-layer (blk.N.*), for the LAYERS tab dropdown. From the cached index — no parse."""
    roles = {}
    for t in anatomy(path).get("tensors", []):
        if re.search(r"blk\.\d+\.", t["name"]):
            rl = _role(t["name"])
            roles[rl] = roles.get(rl, 0) + 1
    return sorted(roles.keys())


def layer_scan(path, role, sample_rows=256):
    """std + near-zero% for a chosen role across ALL layers. Dequant a SAMPLE of each layer's tensor by DIRECT memmap
    (the cached index → _deq_rows) — no GGUFReader parse, instant."""
    per = {}
    for t in anatomy(path).get("tensors", []):
        m = re.search(r"blk\.(\d+)\.", t["name"])
        if not m or _role(t["name"]) != role:
            continue
        layer = int(m.group(1))
        try:
            arr = _deq_head(path, t, max_bytes=max(4, sample_rows) * 4096).ravel()   # byte-bounded: never a whole expert bank
        except Exception:
            continue
        per[layer] = {"layer": layer, "std": round(float(arr.astype(np.float64).std()), 5),
                      "mean": round(float(arr.mean()), 5),
                      "absmax": round(float(np.abs(arr).max()), 4),
                      "zero": round(float(np.mean(np.abs(arr) < 1e-6)), 4),
                      "type": t["type"]}
    rows = [per[k] for k in sorted(per)]
    return {"role": role, "layers": rows}


# ------------------------------------------------------------------ tensor scope + quant stress

def tensor_stats(name):
    if not STATE["path"]:
        return {"error": "no file loaded"}
    path = STATE["path"]
    info = _tinfo(path, name)                                       # cached index entry — no parse
    if info is None:
        return {"error": "tensor not found"}
    typ = info["type"]; shape = [int(x) for x in info["shape"]]
    try:
        sample = _deq_head(path, info, 1_000_000)                  # BOUNDED window — never the whole tensor (SDC one-way read)
        sample = sample[np.isfinite(sample)]                       # a bad quant block can dequant to NaN/Inf — drop them
    except Exception:
        sample = None
    if sample is None or sample.size == 0:
        try:
            raw = np.memmap(path, dtype=np.uint8, mode="r", offset=int(info["offset"]), shape=(int(info["bytes"]),))
            bmean = round(float(raw.mean()), 2)                     # streams the memmap; no big copy
        except Exception:
            bmean = None
        return {"name": name, "type": typ,
                "note": "this quant type isn't dequantizable by the library (edit as raw bytes in Search+Destroy); raw byte stats only",
                "shape": shape, "byte_mean": bmean}
    arr = sample
    if arr.size > 2_000_000:
        arr = arr[:: max(1, arr.size // 2_000_000)]
    hist, edges = np.histogram(arr, bins=40)
    zero = float(np.mean(np.abs(arr) < 1e-6))
    # QUANT STRESS: per-block absmax (outlier concentration = where quant hurts). Block size by quant family.
    bs = 256 if "K" in typ else 32
    stress = None
    try:
        f = sample[: (sample.size // bs) * bs].reshape(-1, bs)
        babs = np.abs(f).max(axis=1)
        if babs.size > 4000:
            babs = babs[:: babs.size // 4000]
        sh, se = np.histogram(babs, bins=30)
        stress = {"block": bs, "hist": sh.tolist(), "edges": [round(float(e), 4) for e in se],
                  "p99": round(float(np.percentile(babs, 99)), 4), "max": round(float(babs.max()), 4)}
    except Exception:
        pass
    return {"name": name, "type": typ, "shape": shape,
            "mean": round(float(arr.mean()), 5), "std": round(float(arr.astype(np.float64).std()), 5),
            "min": round(float(arr.min()), 4), "max": round(float(arr.max()), 4),
            "sparsity": round(zero, 4), "hist": hist.tolist(),
            "edges": [round(float(e), 3) for e in edges], "stress": stress,
            "sampled": bool(sample.size < elems(shape))}


# ------------------------------------------------------------------ decompiler (memmap, RAM-safe)

def _embed_worker(path):
    """attach the decompiler index for `path` in a background thread; cancellable; updates EMBED progress.
    FAST+LIGHT: if a fresh sidecar exists, MEMORY-MAP it directly (no 1.5 GB resident build/spike) — this is the common
    case (the 26B/phi-4 have sidecars), so a model attaches instantly with a few-hundred-MB working set, not a 1.5 GB
    load. Only when no fresh sidecar exists do we pay the one-time open_embed build, then swap to the memmap."""
    try:
        mm = _dc.open_memmap(path)                                   # header-only load — no resident copy
        if mm is not None:
            if EMBED["cancel"] or STATE["path"] != path:
                EMBED["err"] = "cancelled"
            else:
                v, En, dim, ty = mm
                STATE.update(vocab=v, E_mm=En, dim=dim, ety=ty, side=f"{path}.wbEn.f16.npy")
                EMBED.update(ready=True, err="", progress=1.0)
            return

        def prog(f):
            EMBED["progress"] = round(float(f), 3)
        def cancelled():
            return EMBED["cancel"] or STATE["path"] != path
        v, En, dim, ty, side = _dc.open_embed(path, progress=prog, should_cancel=cancelled)   # slow, once per model
        if EMBED["cancel"] or STATE["path"] != path:
            del En                                                   # discard — model changed or user cancelled
            EMBED["err"] = "cancelled"
        else:
            mm = _dc.open_memmap(path)                               # swap the transient resident for the MEMMAP
            if mm is not None:
                del En
                v, En, dim, ty = mm
            STATE.update(vocab=v, E_mm=En, dim=dim, ety=ty, side=side)
            EMBED.update(ready=True, err="", progress=1.0)
    except Exception as e:
        EMBED["err"] = "cancelled" if "cancel" in str(e).lower() else f"embed build failed: {e}"
    finally:
        EMBED["building"] = False


def start_embed_build():
    """Attach the decompiler over the STORED token-embedding bits — STREAMING, ~0 resident host RAM, NO build, NO model
    load (owner: NEVER LOAD ANY MODEL, EVER). Each query's cosine is computed by streaming the stored token_embd off the
    memmap in bounded chunks (`decompile.StreamE`); the only held data is the tokenizer vocab (cached, lazy). If a
    pre-built normalized sidecar happens to already exist it is memory-mapped instead (also ~0 resident) — either way
    NOTHING is built or residented, and it works on ANY model (Titan included, no sidecar needed)."""
    if _dc is None or not STATE["path"]:
        return False
    with EMBED_LOCK:
        if STATE["E_mm"] is not None and EMBED.get("path") == STATE["path"]:
            EMBED["ready"] = True
            return True
        try:
            mm = _dc.open_memmap(STATE["path"])                      # a pre-built normalized sidecar, if present (memmap, ~0)
            if mm is not None:
                v, En, dim, ty = mm
                side = STATE["path"] + ".wbEn.f16.npy"
            else:                                                    # else STREAM the stored bits directly — no build, no sidecar
                te = _tinfo(STATE["path"], "token_embd.weight") or _tinfo(STATE["path"], "tok_embeddings.weight")
                if te is None:
                    EMBED.update(building=False, ready=False, progress=0.0, path=STATE["path"],
                                 err="no token_embd tensor in this model")
                    return False
                v, En, dim, ty = _dc.open_stream(STATE["path"], te)
                side = None
            with LOCK:
                STATE.update(vocab=v, E_mm=En, dim=dim, ety=ty, side=side)
            EMBED.update(building=False, ready=True, err="", progress=1.0, path=STATE["path"])
            return True
        except Exception as e:
            EMBED.update(building=False, ready=False, progress=0.0, path=STATE["path"],
                         err=f"decompiler attach failed: {e}")
            return False


def ensure_embed():
    """True if the decompiler is attached (streaming the stored bits, or a memmap sidecar). Attaches on demand and
    SYNCHRONOUSLY — the very first attach on a new model reads the tokenizer once (TIME, cached to .wbvocab.json), NOT a
    resident model load. ~0 RAM: it streams the stored token_embd and holds only the vocab list."""
    if STATE["E_mm"] is not None:
        return True
    return bool(start_embed_build())


def _embed_guard():
    """for query endpoints: None if the decompiler is ready; else attach it (streaming). Returns an error dict only if the
    attach genuinely failed (no token_embd / no tokenizer)."""
    if STATE["E_mm"] is not None:
        return None
    if start_embed_build() and STATE["E_mm"] is not None:
        return None
    if EMBED["err"] and EMBED["err"] != "cancelled":
        return {"error": EMBED["err"]}
    return {"error": EMBED["err"] or "decompiler could not attach for this model"}


def do_decompile(word):
    t0 = time.time()
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    i = _dc.find_tok(v, word)
    if i is None:
        return {"error": f"'{word}' is not a single token in this tokenizer"}
    near = _dc.decompile_mm(E, _dc.row_of(E, i), v, k=10, exclude=(i,))
    return {"word": word, "idx": int(i), "dim": int(STATE["dim"]), "type": STATE["ety"],
            "near": [{"tok": t, "sim": round(s, 3)} for t, s in near], "ms": int((time.time() - t0) * 1000)}


def do_meaning_search(query, k=26):
    """HIDDEN MEANING SEARCH: give a concept (one or more words); build its centroid direction from the stored bits and
    find every token that carries that meaning — then flag the HIDDEN ones, whose STRING is unrelated to the query (a
    text search would never find them: cross-lingual, morphological, connotative neighbors). The meaning is decompiled
    out of the weights, not matched on characters (docs/SDC.md — bits carry meaning; this searches by meaning)."""
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    words = [w for w in re.split(r"[,\s]+", query.strip()) if w]
    idx = [(_dc.find_tok(v, w), w) for w in words]
    found = [(i, w) for i, w in idx if i is not None]
    missing = [w for i, w in idx if i is None]
    if not found:
        return {"error": f"none of these are single tokens: {', '.join(words[:8]) or '(empty)'}"}
    centroid = np.mean([_dc.row_of(E, i) for i, _ in found], axis=0)
    centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
    scores = _dc.sims_mm(E, centroid)                    # chunked — memmap-safe (never materializes the f16 as f32)
    order = np.argpartition(-scores, min(k + 40, len(scores) - 1))[:k + 40]
    order = order[np.argsort(-scores[order])]
    qset = [w.lower() for _, w in found]
    exclude = set(i for i, _ in found)
    res = []
    for i in order:
        i = int(i)
        if i in exclude:
            continue
        tok = v[i]
        surf = tok.replace("▁", "").strip().lower()
        hidden = bool(surf) and not any((qw in surf or surf in qw) for qw in qset)
        res.append({"tok": tok.replace("▁", "·"), "sim": round(float(scores[i]), 3), "hidden": hidden})
        if len(res) >= k:
            break
    return {"query": " + ".join(w for _, w in found), "missing": missing, "results": res,
            "n_hidden": sum(1 for r in res if r["hidden"])}


def do_edit_preview(a, b):
    """the interpolation preview (does NOT write): nudge a's bits 60% toward b, decompile."""
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    ia, ib = _dc.find_tok(v, a), _dc.find_tok(v, b)
    if ia is None or ib is None:
        return {"error": "both words must be single tokens"}
    edited = 0.4 * _dc.row_of(E, ia) + 0.6 * _dc.row_of(E, ib)
    near = _dc.decompile_mm(E, edited, v, k=8, exclude=(ia, ib))
    return {"a": a, "b": b, "near": [{"tok": t, "sim": round(s, 3)} for t, s in near]}


def do_analogy(a, b, c):
    """vector arithmetic: a - b + c -> nearest token (king - man + woman -> queen). Noisy on a quantized table = signal."""
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    ia, ib, ic = _dc.find_tok(v, a), _dc.find_tok(v, b), _dc.find_tok(v, c)
    miss = [w for w, i in ((a, ia), (b, ib), (c, ic)) if i is None]
    if miss:
        return {"error": f"not single tokens: {', '.join(miss)}"}
    vec = _dc.row_of(E, ia) - _dc.row_of(E, ib) + _dc.row_of(E, ic)
    near = _dc.decompile_mm(E, vec, v, k=10, exclude=(ia, ib, ic))
    return {"expr": f"{a} - {b} + {c}", "near": [{"tok": t, "sim": round(s, 3)} for t, s in near]}


def do_vec(text):
    """embed an arbitrary string DIRECTLY from the token-embedding matrix (mean of its char/token rows) — a pure weight
    read off the memmap, ZERO inference. This is the project method (address the circuitry), not a full forward pass."""
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    rows = []
    for ch in text:
        i = _dc.find_tok(v, ch)
        if i is not None:
            rows.append(_dc.row_of(E, i))
    if not rows:
        return {"error": "no embeddable tokens in text"}
    vec = np.mean(np.stack(rows), axis=0)
    return {"vec": [float(x) for x in vec], "n_tok": len(rows), "dim": int(STATE["dim"])}


def _patch_sidecar(i, vec):
    """after a token bit-edit: update the resident normalized En row + the f16 sidecar file (touch mtime) so the
    decompiler reflects the new bits instantly AND survives a restart, WITHOUT a 3-min full rebuild."""
    v = np.asarray(vec, np.float32)
    vn = v / (np.linalg.norm(v) + 1e-8)                # the NORMALIZED row (both the resident En and the sidecar hold En)
    if STATE["E_mm"] is not None and not isinstance(STATE["E_mm"], _dc.StreamE):
        STATE["E_mm"][int(i)] = vn.astype(STATE["E_mm"].dtype)   # StreamE reads LIVE bits → the edit shows on the next query, no patch
    side = STATE.get("side")
    if side and os.path.exists(side):
        try:
            mm = np.load(side, mmap_mode="r+")
            mm[int(i)] = vn.astype(np.float16)
            mm.flush(); del mm
            mt = os.path.getmtime(STATE["path"]) + 1
            os.utime(side, (mt, mt))
        except Exception:
            pass


def do_edit_token(word, toward, amount, zero):
    """PERSIST a bit-edit to a token's embedding row (reversible), then return before/after neighbors — the measure loop."""
    if _wb is None:
        return {"error": "editor unavailable"}
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    i = _dc.find_tok(v, word)
    if i is None:
        return {"error": f"'{word}' is not a single token"}
    before = _dc.decompile_mm(E, _dc.row_of(E, i), v, k=8, exclude=(i,))
    res = _wb.edit_token(STATE["path"], word, toward=(None if zero else toward), amount=amount, zero=zero)
    if "error" in res:
        return res
    if res.get("vec") is not None:
        _patch_sidecar(res["id"], res["vec"])
    if not ensure_embed():
        return {"error": STATE.get("err") or "embed reopen failed"}
    E = STATE["E_mm"]
    after = _dc.decompile_mm(E, _dc.row_of(E, i), v, k=8, exclude=(i,))
    STATE["anat"] = None  # bytes changed
    return {"ok": True, "token": word, "seq": res.get("seq"), "note": res.get("note"),
            "before": [{"tok": t, "sim": round(s, 3)} for t, s in before],
            "after": [{"tok": t, "sim": round(s, 3)} for t, s in after]}


# ------------------------------------------------------------------ targeted alignment (sighted, not blind)

def do_align_axis(pos, neg, k=14):
    """Define an ALIGNMENT AXIS from contrasting concept tokens (pos − neg) and SEE what it captures: project the whole
    vocab onto it and return the most-aligned and most-anti-aligned tokens. This is the SIGHT that makes alignment
    targeted — you watch which meanings the axis moves before you touch a single weight (CAPTURED_CIRCUIT §7 de-warp)."""
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    posl = [w.strip() for w in pos.split(",") if w.strip()]
    negl = [w.strip() for w in neg.split(",") if w.strip()]
    pi = [_dc.find_tok(v, w) for w in posl]
    ni = [_dc.find_tok(v, w) for w in negl]
    miss = [w for w, i in list(zip(posl, pi)) + list(zip(negl, ni)) if i is None]
    if miss:
        return {"error": f"not single tokens: {', '.join(miss[:6])}"}
    if not pi or not ni:
        return {"error": "give at least one positive and one negative concept word"}
    d = np.mean([_dc.row_of(E, i) for i in pi], axis=0) - np.mean([_dc.row_of(E, i) for i in ni], axis=0)
    d = d / (np.linalg.norm(d) + 1e-8)
    STATE["align_dir"] = d
    STATE["align_desc"] = f"({', '.join(posl)}) − ({', '.join(negl)})"
    scores = _dc.sims_mm(E, d)          # chunked projection onto the axis — memmap-safe (E is normalized)
    order = np.argsort(-scores)
    exclude = set(pi) | set(ni)
    top, bot = [], []
    for i in order:
        i = int(i)
        if i in exclude:
            continue
        top.append({"tok": v[i].replace("▁", "·"), "score": round(float(scores[i]), 3)})
        if len(top) >= k:
            break
    for i in order[::-1]:
        i = int(i)
        if i in exclude:
            continue
        bot.append({"tok": v[i].replace("▁", "·"), "score": round(float(scores[i]), 3)})
        if len(bot) >= k:
            break
    return {"desc": STATE["align_desc"], "aligned": top, "anti": bot}


# ------------------------------------------------------------------ SINGLE-PARAMETER decode (down to the param)

def param_decode(layer, kind, j, k=12):
    """Decode ONE parameter's meaning — down to the param (owner). Dequantize just one FFN row/column of a layer (bounded,
    fast, no inference) and PROJECT it through the token embedding (the memmap E) → nearest tokens. This is the meaning a
    single parameter READS (gate/up rows g_j/u_j: which inputs turn transistor j on) or WRITES (down column d_j: which
    concepts it drives into the residual). kind ∈ {gate,up,down,embed}. The transistor's read/write vocabulary from the bits."""
    t0 = time.time()
    if STATE["E_mm"] is None:
        g = _embed_guard()
        return g or {"error": "embedding index not ready"}
    E, v = STATE["E_mm"], STATE["vocab"]
    j = int(j); layer = int(layer)
    if kind == "embed":
        if j < 0 or j >= E.shape[0]:
            return {"error": f"token index {j} out of range (vocab={E.shape[0]})"}
        vec = _dc.row_of(E, j); label = f"token[{j}] = {v[j].replace('▁', '·')}"
    else:
        pre = f"blk.{layer}."
        tmap = {"gate": pre + "ffn_gate.weight", "up": pre + "ffn_up.weight", "down": pre + "ffn_down.weight"}
        W, meta = _deq_cached(STATE["path"], tmap.get(kind, ""))   # cached-index dequant — no 24 s parse
        if W is None:
            return {"error": meta.get("error", f"no dense {kind} tensor at layer {layer} (pure-MoE — try another model/layer)")}
        if kind in ("gate", "up"):                       # (n_ff, n_embd): row j = transistor j's READ direction
            if j >= W.shape[0]:
                return {"error": f"unit {j} out of range (n_ff={W.shape[0]})"}
            vec = np.array(W[j]); label = f"{kind} row [{j}] — what turns transistor {j} ON (reads)"
        else:                                            # down (n_embd, n_ff): column j = transistor j's WRITE direction
            if j >= W.shape[1]:
                return {"error": f"unit {j} out of range (n_ff={W.shape[1]})"}
            vec = np.array(W[:, j]); label = f"down col [{j}] — what transistor {j} WRITES to the residual"
        del W
    if int(vec.shape[0]) != int(E.shape[1]):
        return {"error": f"dim mismatch: param {vec.shape[0]} vs embedding {E.shape[1]}"}
    scores = _dc.sims_mm(E, vec)
    m = min(k + 4, len(scores) - 1)
    order = np.argpartition(-scores, m)[:m + 1]
    order = order[np.argsort(-scores[order])]
    near = [{"tok": v[int(i)].replace("▁", "·"), "sim": round(float(scores[int(i)]), 3)} for i in order[:k]]
    return {"label": label, "kind": kind, "layer": layer, "j": j, "near": near, "ms": int((time.time() - t0) * 1000)}


def param_scan(layer, kind="down", n=48, k=5):
    """Find the INTERPRETABLE neurons of a layer — decode N transistors in ONE embedding pass (not N passes) and rank each
    by how cleanly it projects to token space (top-1 sim). A HIGH top-1 = a clean, near-monosemantic neuron (e.g. a 'font'
    neuron); a LOW top-1 = a superposed/polysemantic direction. Surfaces the meaningful params. No inference. RAM-safe
    (one chunked pass over the embedding + N small neuron vectors)."""
    t0 = time.time()
    if STATE["E_mm"] is None:
        g = _embed_guard()
        return g or {"error": "index not ready"}
    E, v = STATE["E_mm"], STATE["vocab"]
    layer = int(layer); n = int(n)
    pre = f"blk.{layer}."
    tmap = {"gate": pre + "ffn_gate.weight", "up": pre + "ffn_up.weight", "down": pre + "ffn_down.weight"}
    W, meta = _deq_cached(STATE["path"], tmap.get(kind, ""))   # cached-index dequant — no 24 s parse
    if W is None:
        return {"error": meta.get("error", f"no dense {kind} tensor at layer {layer}")}
    if kind in ("gate", "up"):
        nff = W.shape[0]; sel = np.linspace(0, nff - 1, min(n, nff)).astype(int); P = np.array(W[sel])       # (N, n_embd)
    else:
        nff = W.shape[1]; sel = np.linspace(0, nff - 1, min(n, nff)).astype(int); P = np.array(W[:, sel].T)  # (N, n_embd)
    del W
    if P.shape[1] != E.shape[1]:
        return {"error": f"dim mismatch: {P.shape[1]} vs {E.shape[1]}"}
    P = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-8)
    N = P.shape[0]; V = E.shape[0]; chunk = 8192
    best_sim = np.full((N, k), -1e9, np.float32); best_idx = np.zeros((N, k), np.int64)
    for s in range(0, V, chunk):                            # ONE pass over the embedding, all N neurons at once
        Ec = np.asarray(E[s:s + chunk], np.float32)
        sims = P @ Ec.T                                     # (N, c)
        cat_sim = np.concatenate([best_sim, sims], axis=1)
        span = np.broadcast_to(np.arange(s, s + Ec.shape[0], dtype=np.int64), (N, Ec.shape[0]))
        cat_idx = np.concatenate([best_idx, span], axis=1)
        keep = np.argpartition(-cat_sim, k - 1, axis=1)[:, :k]
        best_sim = np.take_along_axis(cat_sim, keep, axis=1)
        best_idx = np.take_along_axis(cat_idx, keep, axis=1)
    out = []
    for a in range(N):
        o = np.argsort(-best_sim[a])
        toks = [{"tok": v[int(best_idx[a, i])].replace("▁", "·"), "sim": round(float(best_sim[a, i]), 3)} for i in o]
        out.append({"j": int(sel[a]), "top": round(float(best_sim[a, o[0]]), 3), "near": toks})
    out.sort(key=lambda x: -x["top"])
    return {"layer": layer, "kind": kind, "n": N, "ms": int((time.time() - t0) * 1000), "neurons": out}


def token_neurons(word, layer, kind="down", n=256, k=14):
    """Type a TOKEN → which neurons of a layer carry its concept (the reverse of param_scan). Rank the layer's neurons by
    how strongly each projects onto the token's stored embedding direction: +sim = a neuron that WRITES/READS this concept,
    −sim = one that opposes it. No inference; cached-index dequant + one memmap row."""
    t0 = time.time()
    if STATE["E_mm"] is None:
        return _embed_guard() or {"error": "embedding index not ready"}
    E, v = STATE["E_mm"], STATE["vocab"]
    tid = _dc.find_tok(v, word)
    if tid is None:
        return {"error": f"'{word}' is not a single token in this model's vocab"}
    tvec = np.asarray(_dc.row_of(E, tid), np.float32)          # the token's (normalized) embedding direction
    layer = int(layer); n = int(n)
    pre = f"blk.{layer}."
    tmap = {"gate": pre + "ffn_gate.weight", "up": pre + "ffn_up.weight", "down": pre + "ffn_down.weight"}
    W, meta = _deq_cached(STATE["path"], tmap.get(kind, ""))
    if W is None:
        return {"error": meta.get("error", f"no dense {kind} tensor at layer {layer}")}
    if kind in ("gate", "up"):
        nff = W.shape[0]; sel = np.linspace(0, nff - 1, min(n, nff)).astype(int); P = np.array(W[sel])
    else:
        nff = W.shape[1]; sel = np.linspace(0, nff - 1, min(n, nff)).astype(int); P = np.array(W[:, sel].T)
    del W
    if P.shape[1] != E.shape[1]:
        return {"error": f"dim mismatch {P.shape[1]} vs {E.shape[1]}"}
    P = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-8)
    sims = P @ tvec
    order = np.argsort(-np.abs(sims))[:k]
    out = [{"j": int(sel[i]), "sim": round(float(sims[i]), 3)} for i in order]
    return {"word": word, "layer": layer, "kind": kind, "n": len(sel), "ms": int((time.time() - t0) * 1000), "neurons": out}


def _str_vec_row(text):
    """embed a string: if it's a whole single token use its real embedding (meaning); else mean of its char-token rows
    (surface). Direct memmap reads, no inference."""
    v, E = STATE["vocab"], STATE["E_mm"]
    whole = _dc.find_tok(v, text)
    if whole is not None:
        return np.asarray(_dc.row_of(E, whole), np.float32)
    rows = []
    for ch in text:
        i = _dc.find_tok(v, ch)
        if i is not None:
            rows.append(_dc.row_of(E, i))
    return np.mean(np.stack(rows), axis=0) if rows else None


def do_direction(right, wrong, layer, kind, k=14, norm=0, strip=0):
    """CONTRASTIVE-CONSTRAINT DIRECTION (owner 07-15): feed two piles of arbitrary strings (right vs wrong). Build the
    difference vector mean(right)-mean(wrong), report its RAW NORM (≈0 = the two classes are indistinguishable to the
    model => no hidden 'seed'; large = a real separating direction), decompile what the direction MEANS (nearest tokens),
    and DEEP-READ it by projecting through a layer's FFN transistors (which deep neurons write/read that direction). All
    weight reads off the memmap — the approximation of a contextual probe with zero inference.
    NON-JUNK DIALS (each still ONE bounded read): `strip` removes the top-N principal (surface) axes before the
    difference (peel the digit/hex-length axis → does any hidden seed survive?); `norm` L2-normalizes each string so
    long strings don't dominate (orientation vs magnitude). Also returns `cohesion` (are the RIGHT answers a coherent
    cluster? within-right vs within-wrong vs cross mean cosine) and `near_deep` (the MEANS with pure-digit tokens
    filtered out — what the direction points at UNDER the surface)."""
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    R = [s.strip() for s in re.split(r"[\n|]+", right) if s.strip()]
    Wr = [s.strip() for s in re.split(r"[\n|]+", wrong) if s.strip()]
    rv = [x for x in (_str_vec_row(s) for s in R) if x is not None]
    wv = [x for x in (_str_vec_row(s) for s in Wr) if x is not None]
    if not rv or not wv:
        return {"error": "need at least one right and one wrong string"}
    nr = len(rv)
    k = int(k)                                                       # arrives as a query string; used to slice below
    M = np.stack(rv + wv).astype(np.float32)
    norm = int(norm); strip = int(strip)
    if norm:
        M = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-8)   # orientation, not magnitude
    stripped = 0
    if strip > 0 and M.shape[0] > strip + 1:
        mu = M.mean(0); Mc = M - mu                                  # the SURFACE axes = the top principal dirs of the set
        try:
            _, _, Vt = np.linalg.svd(Mc, full_matrices=False)       # small (n×d) SVD — instant
            comp = Vt[:strip]
            M = Mc - (Mc @ comp.T) @ comp                           # residual with the top-N surface axes removed
            stripped = strip
        except Exception:
            pass
    RV, WV = M[:nr], M[nr:]
    draw = RV.mean(0) - WV.mean(0)
    rawnorm = float(np.linalg.norm(draw))
    d = draw / (rawnorm + 1e-8)

    def _coh(A, B=None):                                             # mean pairwise cosine (unit-normed) — cluster measure
        An = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-8)
        if B is None:
            if An.shape[0] < 2:
                return None
            S = An @ An.T
            return round(float(S[np.triu_indices(An.shape[0], 1)].mean()), 3)
        Bn = B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-8)
        return round(float((An @ Bn.T).mean()), 3)
    cohesion = {"within_right": _coh(RV), "within_wrong": _coh(WV), "cross": _coh(RV, WV)}

    near_all = _dc.decompile_mm(E, d, v, k=48)

    def _surface(tok):                                              # pure digits / empty / lone punctuation = surface
        s = tok.replace("▁", "").replace("·", "").strip()
        return (s == "") or bool(re.fullmatch(r"\d{1,3}", s))
    near = [{"tok": t.replace("▁", "·"), "sim": round(s, 3)} for t, s in near_all[:k]]
    near_deep = [{"tok": t.replace("▁", "·"), "sim": round(s, 3)} for t, s in near_all if not _surface(t)][:k]

    neurons = []
    layer = int(layer)
    pre = f"blk.{layer}."
    tmap = {"gate": pre + "ffn_gate.weight", "up": pre + "ffn_up.weight", "down": pre + "ffn_down.weight"}
    W, meta = _deq_cached(STATE["path"], tmap.get(kind, ""))
    if W is not None:
        if kind in ("gate", "up"):
            nff = W.shape[0]; sel = np.linspace(0, nff - 1, min(256, nff)).astype(int); P = np.array(W[sel])
        else:
            nff = W.shape[1]; sel = np.linspace(0, nff - 1, min(256, nff)).astype(int); P = np.array(W[:, sel].T)
        del W
        if P.shape[1] == E.shape[1]:
            P = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-8)
            sims = P @ d
            order = np.argsort(-np.abs(sims))[:int(k)]
            neurons = [{"j": int(sel[i]), "sim": round(float(sims[i]), 3)} for i in order]
    return {"n_right": nr, "n_wrong": len(wv), "raw_norm": round(rawnorm, 4),
            "stripped": stripped, "norm": norm, "cohesion": cohesion,
            "near": near, "near_deep": near_deep,
            "layer": layer, "kind": kind, "neurons": neurons}


def do_manifold(tokens):
    """CONCEPT MANIFOLD + HUBS (owner 07-15): embed a set of tokens, return each one's nearest OTHER member and the
    HUB ranking (in-degree = how many members call it their nearest neighbor). Reveals ordinal manifolds (digits form a
    number line) and attractors (the '2' hub arithmetic collapses toward). Pure weight reads, no inference."""
    g = _embed_guard()
    if g:
        return g
    toks = [t for t in re.split(r"[,\s]+", tokens.strip()) if t]
    vs, keep = [], []
    for t in toks:
        v = _str_vec_row(t)
        if v is not None:
            vs.append(np.asarray(v, np.float32) / (np.linalg.norm(v) + 1e-9)); keep.append(t)
    if len(keep) < 2:
        return {"error": "give at least 2 embeddable tokens"}
    M = np.stack(vs); C = M @ M.T
    near = []; indeg = {t: 0 for t in keep}
    for i, t in enumerate(keep):
        row = sorted(((keep[j], float(C[i, j])) for j in range(len(keep)) if j != i), key=lambda x: -x[1])
        near.append({"tok": t, "nearest": row[0][0], "sim": round(row[0][1], 3)})
        indeg[row[0][0]] += 1
    hubs = sorted(indeg.items(), key=lambda x: -x[1])
    return {"n": len(keep), "near": near, "hubs": [{"tok": t, "indeg": d} for t, d in hubs]}


def do_relation(pairs, apply):
    """RELATION TESTER (owner 07-15): given a:b example pairs, measure whether the relation is a CONSISTENT DIRECTION
    (the model can COMPUTE it by vector arithmetic — like gender in king:queen) or NOT (it only PATTERN-MATCHES — like
    +1 on digits). Consistency = mean pairwise cosine of the individual b−a vectors. Then apply the mean relation to a
    new token and decompile the prediction. Pure weight reads, no inference."""
    g = _embed_guard()
    if g:
        return g
    v, E = STATE["vocab"], STATE["E_mm"]
    P = []
    for p in re.split(r"[,\n]+", pairs or ""):
        p = p.strip()
        if ":" in p:
            a, b = p.split(":", 1); P.append((a.strip(), b.strip()))
    R, used = [], []
    for a, b in P:
        va, vb = _str_vec_row(a), _str_vec_row(b)
        if va is not None and vb is not None:
            R.append(np.asarray(vb, np.float32) - np.asarray(va, np.float32)); used.append([a, b])
    if len(R) < 2:
        return {"error": "give at least 2 valid a:b pairs (both sides must be embeddable)"}
    Rn = [d / (np.linalg.norm(d) + 1e-9) for d in R]
    sims = [float(Rn[i] @ Rn[j]) for i in range(len(Rn)) for j in range(i + 1, len(Rn))]
    consistency = round(float(np.mean(sims)), 3)
    verdict = ("COMPUTABLE — a consistent direction; the model can do this relation by vector math" if consistency > 0.25
               else "WEAK / PATTERN-MATCHED — inconsistent direction; the model matches, it doesn't compute" if consistency > 0.08
               else "NOT A DIRECTION — pattern-match only; no algebra here (like arithmetic on digits)")
    Rmean = np.mean(np.stack(R), axis=0)
    pred = None
    if apply:
        vx = _str_vec_row(apply)
        if vx is not None:
            ai = _dc.find_tok(v, apply)
            near = _dc.decompile_mm(E, np.asarray(vx, np.float32) + Rmean, v, k=8, exclude=(ai,) if ai is not None else ())
            pred = [{"tok": t.replace("▁", "·"), "sim": round(s, 3)} for t, s in near]
    return {"pairs": used, "consistency": consistency, "verdict": verdict, "apply": apply, "prediction": pred}


def do_align_edit(word, strength):
    """TARGETED realignment: move one token ALONG the sighted axis, reversibly, and MEASURE it — the token's projection
    before/after + its neighbor list before/after. Sighted (you defined the axis + saw its readout) and targeted (one
    token, measured), the opposite of a blind global RLHF nudge."""
    if _wb is None:
        return {"error": "editor unavailable"}
    if STATE["align_dir"] is None:
        return {"error": "define an alignment axis first (Analyze axis)"}
    g = _embed_guard()
    if g:
        return g
    v, E, d = STATE["vocab"], STATE["E_mm"], STATE["align_dir"]
    i = _dc.find_tok(v, word)
    if i is None:
        return {"error": f"'{word}' is not a single token"}
    proj_before = float(_dc.row_of(E, i) @ d)
    before = _dc.decompile_mm(E, _dc.row_of(E, i), v, k=8, exclude=(i,))
    res = _wb.edit_token_delta(STATE["path"], word, d.tolist(), float(strength))
    if "error" in res:
        return res
    if res.get("vec") is not None:
        _patch_sidecar(res["id"], res["vec"])
    if not ensure_embed():
        return {"error": STATE.get("err") or "embed reopen failed"}
    E = STATE["E_mm"]
    proj_after = float(_dc.row_of(E, i) @ d)
    after = _dc.decompile_mm(E, _dc.row_of(E, i), v, k=8, exclude=(i,))
    STATE["anat"] = None
    return {"ok": True, "token": word, "seq": res.get("seq"), "note": res.get("note"),
            "proj_before": round(proj_before, 3), "proj_after": round(proj_after, 3),
            "before": [{"tok": t, "sim": round(s, 3)} for t, s in before],
            "after": [{"tok": t, "sim": round(s, 3)} for t, s in after]}


def do_experts(name):
    """per-expert std for an MoE expert tensor (expert-major axis 0) — SEE dead/collapsed experts to target for pruning.
    Direct memmap read of each expert's first blocks (the cached index → _deq_rows) — no GGUFReader parse."""
    if not STATE["path"]:
        return {"error": "no file"}
    path = STATE["path"]
    info = _tinfo(path, name)                                       # cached index entry — no parse
    if info is None:
        return {"error": "tensor not found"}
    n_exp = anatomy(path).get("experts") or int(info["shape"][-1])
    r0 = int(info["dshape"][0])
    if r0 % n_exp != 0:
        return {"error": f"{name} is not an expert-major tensor (shape0 {r0} % {n_exp})"}
    ds = info["dshape"]; per = r0 // n_exp
    stds = []
    for e in range(n_exp):
        try:
            if len(ds) >= 3:                                        # expert-major [n_exp, rows, bytes] → bounded sub-row sample
                arr = _deq_expert_head(path, info, e, 8).ravel()
            else:
                arr = _deq_rows(path, info, e * per, min(per, 8)).ravel()
            stds.append(round(float(arr.astype(np.float64).std()), 6))
        except Exception:
            stds.append(0.0)
    dead = [i for i, s in enumerate(stds) if s < 1e-5]
    return {"name": name, "n_expert": n_exp, "stds": stds, "dead": dead,
            "min": round(min(stds), 6), "max": round(max(stds), 6)}


# ------------------------------------------------------------------ search + destroy + genome (wbedit)
# NEVER add a llama-server / model-runner probe or hook here. The White Box does not know or care whether any server is
# running — it only reads/edits the stored BITS off the memmap. The old `_server_holds_file()` (a `tasklist` probe for
# llama-server.exe, used only to print a warning) was DELETED 07-15 along with every model-running path. This build works
# and this exact session has USED it purely as a weight reader — keep it that way. No subprocess, no server, no inference,
# no forward pass. Ever. (SUPERREADMESTUPID rule 1 + memory: never-load-run-the-model.)


def do_search(kind, q, rx):
    if _wb is None or not STATE["path"]:
        return {"error": "no file / editor unavailable"}
    p, use_rx = STATE["path"], (rx in ("1", "true", "True"))
    if kind == "token":
        return {"kind": kind, "hits": _wb.search_tokens(p, q, use_rx)}
    if kind == "kv":
        kvs = _wb.list_kv(p)
        if q:
            kvs = [k for k in kvs if q.lower() in k["key"].lower()]
        return {"kind": kind, "hits": kvs}
    return {"kind": "tensor", "hits": _wb.search_tensors(p, q, use_rx)}


def _touch_sidecar_valid():
    """a write to a NON-embedding tensor bumped the model mtime; keep the embedding sidecar trusted (it's unchanged)."""
    side = STATE.get("side")
    if side and os.path.exists(side):
        try:
            mt = os.path.getmtime(STATE["path"]) + 1
            os.utime(side, (mt, mt))
        except Exception:
            pass


def _after_write(name=""):
    """invalidate the decompiler cache ONLY if the write touched token_embd; otherwise keep En resident (fast)."""
    if name and ("token_embd" in name or "tok_embeddings" in name):
        EMBED["cancel"] = True
        STATE["E_mm"] = None
        EMBED.update(building=False, ready=False, err="", cancel=False, progress=0.0, path=None)
        side = STATE.get("side")
        if side and os.path.exists(side):
            try:
                os.remove(side)
            except Exception:
                pass
    else:
        _touch_sidecar_valid()


def do_destroy(name, expert):
    if _wb is None or not STATE["path"]:
        return {"error": "no file / editor unavailable"}
    res = (_wb.destroy_expert(STATE["path"], name, expert) if expert not in (None, "", "-1")
           else _wb.destroy_tensor(STATE["path"], name))
    if "error" not in res:
        _after_write(name)
    return res


def do_scale(name, factor):
    if _wb is None or not STATE["path"]:
        return {"error": "no file / editor unavailable"}
    res = _wb.scale_tensor(STATE["path"], name, factor)
    if "error" not in res:
        _after_write(name)
    return res


def do_paste(dst, src, srcname):
    """PASTE HOOK: copy a component tensor FROM a source model (src) INTO the loaded file's tensor (dst), reversibly —
    byte-exact when the quant type+shape match, else same-shape requant. The cross-file copy/paste the White Box was
    missing (owner: 'copy..... paste.....'; 'build the hook for weights')."""
    if _wb is None or not STATE["path"]:
        return {"error": "no file / editor unavailable"}
    if not src:
        return {"error": "source model required: ?src=<file.gguf>"}
    sp = src if os.path.isabs(src) else os.path.join(MODELS_DIR, src)
    if not os.path.exists(sp):
        return {"error": f"source not found: {sp}"}
    res = _wb.paste_tensor(STATE["path"], dst, sp, srcname or dst)
    if "error" not in res:
        _after_write(dst)
    return res


def do_genome():
    if _wb is None or not STATE["path"]:
        return {"log": []}
    return {"log": _wb.genome_log(STATE["path"])}


# ==================================================================================================================
# NOTE — HOOK TO THE MODEL: the White Box NEVER LOADS THE MODEL, NEVER DOES INFERENCE, NEVER DOES A FORWARD PASS.
# Every tool here (do_vec, do_direction, do_analogy, do_meaning_search, token_neurons, param_decode, circuitry, ...)
# reads the WEIGHTS directly off the memmap and does linear algebra on the stored numbers. That is the whole point:
# address the circuitry, don't run the computer. A prior session wrongly wired a llama-server in here for "generation"
# — that loaded the entire model into RAM and ran inference, the exact antithesis of this project (SUPERREADMESTUPID
# rule 1). It has been DELETED. Do NOT re-add it. If you want a "deep read", project a concept/DIRECTION *through* a
# layer's stored FFN tensor (see do_direction / token_neurons) — weights read, not model run. No llama-server. Ever.
# ==================================================================================================================


def do_revert(n):
    if _wb is None or not STATE["path"]:
        return {"error": "no file"}
    alln = n in (None, "", "all")
    log = _wb.genome_log(STATE["path"])
    take = log if alln else log[-int(n):]
    touched_embed = any(e.get("op") == "edit_token" or "token_embd" in (e.get("note") or "")
                        or "tok_embeddings" in (e.get("note") or "") for e in take)
    res = _wb.revert(STATE["path"], None if alln else int(n))
    if touched_embed:
        _after_write("token_embd.weight")   # force embedding-cache rebuild
    else:
        _touch_sidecar_valid()
    return res


# ------------------------------------------------------------------ CIRCUITRY: the weights AS TRANSISTORS (no inference)
# CAPTURED_CIRCUIT.md §2 + INV-141/145/151: a trained model is a captured electronic circuit. In a SwiGLU FFN block the
# per-neuron computation is  y_j = SiLU(g_j·x) · (u_j·x)  routed to the residual by the drain column d_j — which is exactly
# a TRANSISTOR: the gate row g_j is the GATE terminal (SiLU(g_j·x) is the switch — the only conditional in a forward pass,
# INV-141), the up row u_j is the SOURCE (the signal u_j·x it passes when open), and the down column d_j is the DRAIN
# (drives the residual bus = the interconnect). The transistor's static electrical character is recoverable FROM THE
# WEIGHTS ALONE, no inference: gate gain ‖g_j‖ (transconductance — how sharply it switches), source gain ‖u_j‖, drain
# drive ‖d_j‖ (fan-out into the residual), and the gate↔source alignment ρ_j = cos(g_j,u_j) (a self-gating amplifier when
# ρ>0: the gate opens for the same input the source amplifies; an inhibitor/clamp when ρ<0). This is the white-box read
# turned into a component-level schematic of the model's circuitry.
def _find_tensor(r, name):
    return next((t for t in r.tensors if t.name == name), None)


def _free_mb():
    try:
        import ctypes
        class M(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong)] + [(c, ctypes.c_ulonglong) for c in "abcdefg"]
        m = M(); m.l = ctypes.sizeof(M); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.b) // 1048576
    except Exception:
        return 4096


def circuitry(path, layer=0, draw=36):
    """Map one FFN block as a BANK OF TRANSISTORS, from the stored bits — RAM-safe (one small layer, dequant ~tens of MB).
    Returns per-transistor static electrical metrics + an aggregate characterization + a sample for the schematic."""
    if not path:
        return {"error": "no file"}
    pre = f"blk.{int(layer)}."
    gt = _tinfo(path, pre + "ffn_gate.weight")                     # cached index entries — no parse
    ut = _tinfo(path, pre + "ffn_up.weight")
    dt = _tinfo(path, pre + "ffn_down.weight")
    kind = "dense SwiGLU"
    if not (gt and ut and dt):
        return {"error": f"layer {layer} has no dense ffn_gate/up/down (pure-MoE layer — pick a dense model or another layer)"}
    # the transient dequant working-set (three f32 tensors held to compute the transistor norms) — guard the COMPUTE
    # allocation, not the SDC storage (the weights themselves are addressed at ~0 via memmap)
    pf = sum(elems(t["shape"]) for t in (gt, ut, dt)) * 4 / 1e6
    if pf > _free_mb() - 350:
        return {"error": f"dense layer {layer} dequant working-set ~{pf:.0f} MB; pick another layer or a lighter tensor"}
    G = _deq_mmap(path, gt)   # (n_ff, n_embd) — gate rows (the gate terminals)
    U = _deq_mmap(path, ut)   # (n_ff, n_embd) — up rows (the sources)
    D = _deq_mmap(path, dt)   # (n_embd, n_ff) — down cols (the drains)
    n_ff, n_embd = G.shape[0], G.shape[1]
    ga = np.linalg.norm(G, axis=1)                       # gate gain  ‖g_j‖  (transconductance / switch sharpness)
    ua = np.linalg.norm(U, axis=1)                       # source gain ‖u_j‖
    da = np.linalg.norm(D, axis=0)                       # drain drive ‖d_j‖ (fan-out into the residual bus)
    dot = np.einsum("ij,ij->i", G, U)
    rho = dot / (ga * ua + 1e-8)                         # gate↔source alignment (self-gating amplifier vs inhibitor)
    infl = ga * ua * da                                  # static throughput (how much this transistor can move the residual)
    # --- LATCHES (memory): does a transistor WRITE BACK to the residual in the direction it READS FROM? ---
    # λ_j = cos(g_j, d_j): both g_j (gate, reads x from the residual) and d_j (drain, writes to the residual) live in the
    # SAME n_embd space, so their cosine is defined. λ>0 = positive feedback: activating neuron j raises the very residual
    # component its gate reads → it re-triggers itself at the next layer = a self-sustaining HOLD = a LATCH (a memory
    # cell). λ<0 = it damps its own input = a RESET/transient. "memory is just transistors" — the hold cells ARE Titan's
    # native latches, recovered from the weights. (INV-157.)
    lam = np.einsum("je,ej->j", G, D) / (ga * da + 1e-8)          # gate↔drain feedback = the latch polarity
    lam_su = np.einsum("je,ej->j", U, D) / (ua * da + 1e-8)       # source↔drain feedback (the passed signal's self-drive)
    hold = int((lam > 0.15).sum()); reset = int((lam < -0.15).sum())
    # --- DECODER + gate wiring: how cleanly the gate projection decodes an input to a DISTINCT neuron (address decode) ---
    K = min(512, n_ff)
    idx = np.linspace(0, n_ff - 1, K).astype(int)
    Gs = G[idx]; Gs = Gs / (np.linalg.norm(Gs, axis=1, keepdims=True) + 1e-8)
    off = (Gs @ Gs.T)[~np.eye(K, dtype=bool)]
    decode_orth = float(np.abs(off).mean())                      # low = sharp address decoder (each input selects a distinct neuron)
    Ds = D[:, idx].T; Ds = Ds / (np.linalg.norm(Ds, axis=1, keepdims=True) + 1e-8)
    drain_conv = float(np.abs((Ds @ Ds.T)[~np.eye(K, dtype=bool)]).mean())   # drains converging onto shared output dirs (fan-in)
    del G, U, D
    # classify each transistor
    conduct = ga * da
    dead_th = max(1e-9, 0.02 * float(np.median(conduct)))
    dead = conduct < dead_th
    amp = (rho > 0.15) & ~dead
    inh = (rho < -0.15) & ~dead
    passl = ~dead & ~amp & ~inh
    order = np.argsort(-infl)
    # gate-energy concentration (echoes INV-142 "restraint": how few transistors carry the block)
    e = np.sort(ga * ga)[::-1]
    top5 = float(e[:max(1, n_ff // 20)].sum() / (e.sum() + 1e-9))

    def hist(v, lo, hi, nb=24):
        h, edges = np.histogram(np.clip(v, lo, hi), bins=nb, range=(lo, hi))
        return {"bins": h.tolist(), "lo": float(lo), "hi": float(hi)}

    sample = []
    for j in order[:int(draw)]:
        j = int(j)
        cls = "dead" if dead[j] else ("amp" if amp[j] else ("inh" if inh[j] else "pass"))
        sample.append({"j": j, "gate": round(float(ga[j]), 4), "src": round(float(ua[j]), 4),
                       "drain": round(float(da[j]), 4), "rho": round(float(rho[j]), 3),
                       "lam": round(float(lam[j]), 3), "latch": bool(lam[j] > 0.15),
                       "infl": round(float(infl[j]), 4), "cls": cls})
    return {"file": os.path.basename(path), "layer": int(layer), "kind": kind, "n_ff": n_ff, "n_embd": n_embd,
            "counts": {"amp": int(amp.sum()), "inh": int(inh.sum()), "pass": int(passl.sum()), "dead": int(dead.sum())},
            "agg": {"gate_mean": round(float(ga.mean()), 4), "gate_max": round(float(ga.max()), 4),
                    "drain_mean": round(float(da.mean()), 4), "rho_mean": round(float(rho.mean()), 3),
                    "rho_pos_frac": round(float((rho > 0).mean()), 3), "top5_gate_energy": round(top5, 3)},
            "logic": {"latch_hold": hold, "latch_reset": reset, "lam_mean": round(float(lam.mean()), 3),
                      "lam_su_mean": round(float(lam_su.mean()), 3), "decode_orth": round(decode_orth, 3),
                      "drain_conv": round(drain_conv, 3), "lam_hist": hist(lam, -1, 1)},
            "hist": {"gate": hist(ga, 0, float(np.percentile(ga, 99))),
                     "drain": hist(da, 0, float(np.percentile(da, 99))),
                     "rho": hist(rho, -1, 1)},
            "sample": sample}


# ------------------------------------------------------------------ IPC (attention) + the OS-capability map
# CAPTURED_CIRCUIT.md marks attention as the "wires / interconnect — routes information between positions (to map)".
# That IS interprocess communication: each token/position is a process, and attention is the BUS that moves data between
# them. Per attention head, from the weights (no inference): the query projection W_Q_h is how selectively the head
# ADDRESSES which positions to read (read/address strength ‖W_Q_h‖), and the output projection W_O_h is how much it WRITES
# back to the shared residual bus (write bandwidth ‖W_O_h‖); their product is the head's IPC channel strength. GQA groups
# the query heads onto a few shared key/value lines (the shared bus). (INV-158.)
def _meta_int(r, *keys):
    kv = {f.name: f for f in r.fields.values()}
    for k in keys:
        x = kv.get(k)
        if x is not None:
            try:
                return int(x.parts[x.data[-1]][0])
            except Exception:
                pass
    return None


def interconnect(path, layer=0):
    """Map attention as the IPC bus of the model — per-head read/write channel strengths, from the weights. RAM-safe."""
    if not path:
        return {"error": "no file"}
    a = anatomy(path)                                                     # arch + head counts from the cached index — no parse
    arch = a.get("arch")
    nh = a.get("head_count") or 0
    nkv = a.get("head_count_kv") or nh
    pre = f"blk.{int(layer)}."
    qt = _tinfo(path, pre + "attn_q.weight")
    ot = _tinfo(path, pre + "attn_output.weight") or _tinfo(path, pre + "attn_o.weight")
    vt = _tinfo(path, pre + "attn_v.weight")
    if not (qt and ot and nh):
        return {"error": f"layer {layer}: no attn_q/attn_output or head_count (arch={arch})"}
    Q = _deq_mmap(path, qt)                                               # (n_head*hd, n_embd)
    qd = Q.shape[0]; hd = qd // nh
    qn = np.array([np.linalg.norm(Q[h * hd:(h + 1) * hd]) for h in range(nh)])   # read/address strength per head
    del Q
    O = _deq_mmap(path, ot)                                               # (n_embd, n_head*hd)
    on = np.array([np.linalg.norm(O[:, h * hd:(h + 1) * hd]) for h in range(nh)])  # write bandwidth per head
    del O
    chan = qn * on                                                        # IPC channel strength per head
    kvn = None
    if vt is not None:
        V = _deq_mmap(path, vt)
        kvn = float(np.linalg.norm(V)); del V
    order = np.argsort(-chan)
    heads = [{"h": int(i), "read": round(float(qn[i]), 3), "write": round(float(on[i]), 3),
              "chan": round(float(chan[i]), 3)} for i in order]
    return {"file": os.path.basename(path), "layer": int(layer), "arch": arch, "n_head": nh, "n_kv": nkv,
            "head_dim": hd, "gqa_group": (nh // nkv if nkv else 1),
            "chan_mean": round(float(chan.mean()), 3), "chan_max": round(float(chan.max()), 3),
            "chan_top": [int(order[0]), int(order[1]) if nh > 1 else int(order[0])],
            "kv_bus_norm": round(kvn, 3) if kvn is not None else None,
            "heads": heads, "hist": {"chan": None}}


def os_map(path):
    """Look for GENERAL-PURPOSE OS CAPABILITIES in the model, measured from the weights (no inference). Maps each measured
    structure onto an OS primitive: compute (FFN transistors), memory (latches), scheduler/decoder (gate decoder),
    IPC bus (attention), storage (the file), and the I/O codec (embed/unembed)."""
    if not path:
        return {"error": "no file"}
    a = anatomy(path)
    ck = circuitry(path, 0)
    ic = interconnect(path, 0)
    rows = []
    if "error" not in ck:
        c = ck["counts"]; lo = ck["logic"]
        rows.append({"os": "PROCESSOR / ALU (compute)", "titan": "FFN transistors (SwiGLU gate neurons)",
                     "measure": f"{ck['n_ff']} transistors/block · {c['amp']} amplifiers · {c['inh']} inhibitors · {c['dead']} dead"})
        rows.append({"os": "MEMORY (registers / RAM cells)", "titan": "latches — drain writes where the gate reads",
                     "measure": f"{lo['latch_hold']} hold cells (memory) · {lo['latch_reset']} reset · λ̄={lo['lam_mean']}"})
        rows.append({"os": "SCHEDULER / ADDRESS DECODER", "titan": "gate projection decodes input→neuron",
                     "measure": f"decoder orthogonality {lo['decode_orth']} (lower = sharper one-of-many select)"})
    if "error" not in ic:
        rows.append({"os": "IPC BUS (interprocess comm.)", "titan": "attention routes data between positions",
                     "measure": f"{ic['n_head']} channels over {ic['n_kv']} shared KV lines (GQA×{ic['gqa_group']}) · mean channel {ic['chan_mean']}"})
    rows.append({"os": "STORAGE (disk / DRAM cells)", "titan": "the parameter file (weights = stored charge)",
                 "measure": f"{a['params_B']} B params · {a['size_GB']} GB on disk · {a['layers']} layers"})
    rows.append({"os": "I/O CODEC (in / out)", "titan": "token_embd (decode-in) + output head (encode-out)",
                 "measure": f"vocab {a['vocab']} × hidden {a['hidden']} (the tokenizer bus)"})
    return {"file": a["file"], "arch": a["arch"], "rows": rows,
            "summary": "Titan's weights already implement the primitives of a general-purpose computer — compute, memory, "
                       "a scheduler/decoder, an IPC bus, storage, and an I/O codec — all readable from the file, no inference."}


def export_all(path, layers="0,mid,last", full_circuit=False, all_experts=False, decompile=False, out_dir=None, log=None):
    """Scrape EVERYTHING the White Box can read from ONE model into a single per-model artifact (json + md). Uses the
    app's OWN index+memmap reads (no GGUFReader parse, no model load); every read is a bounded window (SDC one-way rule).
    Returns a summary dict {ok, json, md, md_text, seconds, free_ram_drop_MB, sections, errors} and writes the two files."""
    if log is None:
        log = lambda *a: None
    if not path or not os.path.exists(path):
        return {"error": f"model not found: {path}"}
    base = os.path.basename(path)
    if out_dir is None:
        out_dir = "C:/Users/lucys/OneDrive/Desktop/TitanSDC"
        if not os.path.isdir(out_dir):
            out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whitebox_out")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    stem = os.path.join(out_dir, "whitebox_" + os.path.splitext(base)[0])

    art = {"model": base, "path": path.replace("\\", "/"), "sections": {}, "errors": {}}
    t0 = time.time(); free0 = _free_mb(); minfree = [free0]

    def sect(key, fn):
        try:
            art["sections"][key] = fn()
        except Exception as e:
            art["errors"][key] = f"{type(e).__name__}: {e}"
        f = _free_mb(); minfree[0] = min(minfree[0], f)
        log(f"[export] {key}: free={f}MB")

    a = anatomy(path); tens = a.get("tensors", [])
    art["sections"]["anatomy"] = {k: v for k, v in a.items() if k != "tensors"}
    art["sections"]["tensors"] = [{k: t.get(k) for k in ("name", "type", "shape", "params", "bytes")} for t in tens]
    sect("precision_map", lambda: precision_map(path))
    sect("os_map", lambda: os_map(path))

    roles = [r for r in _layer_roles(path) if not r.endswith("_exps")]   # expert banks covered by expert_health
    sect("depth_profile", lambda: {rl: layer_scan(path, rl).get("layers", []) for rl in roles})

    STATE["path"] = path
    exp_names = [t["name"] for t in tens if "exps" in t["name"] and not t["name"].endswith(".scale")]
    if not all_experts:
        exp_names = exp_names[:8]

    def _experts():
        out = {}
        for nm in exp_names:
            r = do_experts(nm)
            out[nm] = ({"n_expert": r["n_expert"], "dead": r["dead"], "n_dead": len(r["dead"]),
                        "min": r["min"], "max": r["max"]} if "error" not in r else {"error": r["error"]})
        return out
    sect("expert_health", _experts)

    def _tstats():
        seen, out = set(), {}
        for t in tens:                                              # tens sorted biggest-first → first per role = biggest
            rl = _role(t["name"])
            if rl in seen:
                continue
            seen.add(rl); out[t["name"]] = tensor_stats(t["name"])
        return out
    sect("tensor_stats", _tstats)

    nl = a.get("layers") or 0

    def _resolve(tok):
        tok = tok.strip()
        if tok == "mid":
            return nl // 2
        if tok == "last":
            return nl - 1
        return int(tok) if tok.isdigit() else 0
    sel = list(range(nl)) if full_circuit else sorted(set(_resolve(x) for x in layers.split(",") if x.strip() and nl))

    def _circuit():
        out = {}
        for L in sel:
            c = circuitry(path, L)
            out[L] = ({"error": c["error"]} if "error" in c else
                      {"n_ff": c["n_ff"], "n_embd": c["n_embd"], "counts": c["counts"], "agg": c["agg"],
                       "logic": {k: c["logic"][k] for k in c["logic"] if k != "lam_hist"}})
        return out
    sect("circuit_by_layer", _circuit)

    def _ipc():
        out = {}
        for L in sel:
            ic = interconnect(path, L)
            out[L] = ({"error": ic["error"]} if "error" in ic else
                      {k: ic[k] for k in ("n_head", "n_kv", "gqa_group", "head_dim", "chan_mean", "chan_max",
                                          "chan_top", "kv_bus_norm")})
        return out
    sect("ipc_by_layer", _ipc)

    if decompile:
        def _decompile():
            if _dc is None:
                return {"status": "decompiler module unavailable"}
            STATE["path"] = path                                    # the decompiler STREAMS the stored token_embd bits — no load
            if not ensure_embed():                                 # attaches the streaming source (or a memmap sidecar) — no build
                return {"status": "decompiler could not attach (no token_embd/tokenizer) — skipped"}
            out = {"words": {}, "analogy": None}
            for w in ("king", "queen", "bitcoin"):
                try:
                    out["words"][w] = do_decompile(w)
                except Exception as e:
                    out["words"][w] = {"error": str(e)}
            try:
                out["analogy"] = do_analogy("king", "man", "woman")
            except Exception as e:
                out["analogy"] = {"error": str(e)}
            return out
        sect("decompiler", _decompile)

    art["meta"] = {"seconds": round(time.time() - t0, 1),
                   "free_ram_drop_MB": round(max(0.0, free0 - minfree[0]), 1),
                   "sampled_layers": sel, "n_layers": nl}
    md = _export_md(art)
    try:
        with open(stem + ".json", "w", encoding="utf-8") as f:
            json.dump(art, f, indent=1)
        open(stem + ".md", "w", encoding="utf-8").write(md)
    except Exception as e:
        return {"error": f"scrape ok but write failed: {e}", "md_text": md}
    return {"ok": True, "model": base, "json": stem + ".json", "md": stem + ".md", "md_text": md,
            "seconds": art["meta"]["seconds"], "free_ram_drop_MB": art["meta"]["free_ram_drop_MB"],
            "sections": list(art["sections"].keys()), "errors": art["errors"]}


# ── RESEARCHER ARCHIVE — one folder: the weights + ALL White Box data, for researchers to dig through (owner 07-16) ──
# PURE PYTHON, NO NUMPY (standing rule): analysis reuses export_all; the weight dump reads the cached index and mmaps the
# stored bytes, writing them RAW (the weights ARE bits) plus a bounded pure-python-dequant f32 sample per tensor. Streamed
# to disk (~0 RAM), runs in the gated sandbox (ends). Keep it the most-data-possible dump as new reads land (owner).
_ARCH_ROOT = "C:/Users/lucys/OneDrive/Desktop/WhiteBox_Research_Archive"


def _pp_dequant(tid, blob):
    """pure-python dequant of a raw byte blob for the common types -> list of floats (NO numpy). None if unsupported."""
    import struct
    if tid == 0:                                                  # F32
        n = len(blob) // 4; return list(struct.unpack("<%df" % n, blob[:n * 4]))
    if tid == 1:                                                  # F16
        n = len(blob) // 2; return list(struct.unpack("<%de" % n, blob[:n * 2]))
    if tid == 2:                                                  # Q4_0: 18-byte block (f16 scale + 16 bytes of nibbles) -> 32
        out = []; p = 0
        while p + 18 <= len(blob):
            d = struct.unpack_from("<e", blob, p)[0]; p += 2
            for j in range(16): out.append(((blob[p + j] & 0x0f) - 8) * d)   # low nibbles -> weights 0..15
            for j in range(16): out.append(((blob[p + j] >> 4) - 8) * d)     # high nibbles -> weights 16..31
            p += 16
        return out
    if tid == 8:                                                 # Q8_0: 34-byte block (f16 scale + 32 int8) -> 32
        out = []; p = 0
        while p + 34 <= len(blob):
            d = struct.unpack_from("<e", blob, p)[0]; p += 2
            for j in range(32):
                q = blob[p + j]; out.append((q - 256 if q >= 128 else q) * d)
            p += 32
        return out
    return None


def research_archive(path, full=False, layers="0,mid,last", all_experts=False, decompile=False,
                     raw_cap_mb=4, sample_rows=128, log=None):
    """Dump ONE model's WEIGHTS + all White Box analysis into a single folder for researchers. Pure python, no numpy.
    weights: each tensor's raw stored bytes (bounded, or full) + a pure-python f32 sample; analysis: export_all's json+md."""
    import mmap as _mmap, struct as _struct, shutil as _shutil
    if log is None: log = lambda *a: None
    if not path or not os.path.exists(path):
        return {"error": f"model not found: {path}"}
    base = os.path.basename(path); stem = os.path.splitext(base)[0]
    root = _ARCH_ROOT if os.path.isdir(os.path.dirname(_ARCH_ROOT)) else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "whitebox_out", "research_archive")
    adir = os.path.join(root, stem); wdir = os.path.join(adir, "weights"); sdir = os.path.join(adir, "sidecars")
    for d in (adir, wdir, sdir): os.makedirs(d, exist_ok=True)
    t0 = time.time(); free0 = _free_mb()

    ana = export_all(path, layers=layers, all_experts=all_experts, decompile=decompile, out_dir=adir, log=log)
    log(f"[archive] analysis: {ana.get('sections') if ana.get('ok') else ana.get('error')}")

    anatomy(path)                                                # ensure the cached index exists (name->offset/tid/dshape)
    try:
        idx = json.load(open(_index_path(path), encoding="utf-8"))
    except Exception as e:
        return {"error": f"could not read index: {e}", "analysis": ana}
    tens = idx.get("tensors", [])
    cap = None if full else int(raw_cap_mb * 1024 * 1024)
    manifest = []; total_raw = 0; nsamp = 0
    f = open(path, "rb"); mm = _mmap.mmap(f.fileno(), 0, access=_mmap.ACCESS_READ)
    try:
        for t in tens:
            if "offset" not in t or "bytes" not in t:
                continue
            off = int(t["offset"]); nby = int(t["bytes"]); tid = int(t.get("tid", -1))
            safe = "".join(c if (c.isalnum() or c in ".-_") else "_" for c in t["name"])[:120]
            take = nby if cap is None else min(nby, cap)
            with open(os.path.join(wdir, safe + ".qbin"), "wb") as o:      # raw stored bytes = the weights, verbatim
                p = 0
                while p < take:
                    n = min(1 << 20, take - p); o.write(mm[off + p:off + p + n]); p += n
            total_raw += take
            ent = {"name": t["name"], "type": t.get("type"), "tid": tid, "shape": t.get("shape"),
                   "dshape": t.get("dshape"), "bytes": nby, "raw_dumped": take, "raw_full": (take == nby),
                   "qbin": "weights/" + safe + ".qbin"}
            r0 = int(t["dshape"][0]) if t.get("dshape") else 1; bpr = nby // max(1, r0)
            sbytes = min(min(sample_rows, r0) * bpr, 2 << 20)
            vals = _pp_dequant(tid, mm[off:off + sbytes]) if sbytes else None
            if vals:                                                       # a decoded float32 sample (pure python)
                with open(os.path.join(wdir, safe + ".sample.f32"), "wb") as o:
                    o.write(_struct.pack("<%df" % len(vals), *vals))
                ent["sample"] = {"file": "weights/" + safe + ".sample.f32", "count": len(vals),
                                 "min": round(min(vals), 6), "max": round(max(vals), 6),
                                 "mean": round(sum(vals) / len(vals), 6), "absmax": round(max(abs(x) for x in vals), 6)}
                nsamp += 1
            manifest.append(ent)
    finally:
        mm.close(); f.close()

    for suf in (".wbindex.json", ".wbmeta.json", ".wbvocab.json"):
        src = path + suf
        if os.path.exists(src):
            try: _shutil.copy2(src, os.path.join(sdir, os.path.basename(src)))
            except Exception: pass

    json.dump({"model": base, "path": path.replace("\\", "/"), "n_tensors": len(manifest), "raw_bytes": total_raw,
               "sampled": nsamp, "full": bool(full), "tensors": manifest},
              open(os.path.join(adir, "weights_manifest.json"), "w"), indent=1)
    open(os.path.join(adir, "README.md"), "w", encoding="utf-8").write(
        _archive_readme(base, ana, manifest, total_raw, full))
    return {"ok": True, "model": base, "dir": adir.replace("\\", "/"), "n_tensors": len(manifest),
            "raw_MB": round(total_raw / 1e6, 1), "sampled": nsamp, "seconds": round(time.time() - t0, 1),
            "free_ram_drop_MB": round(max(0.0, free0 - _free_mb()), 1),
            "analysis": ({"json": ana.get("json"), "md": ana.get("md")} if ana.get("ok") else {"error": ana.get("error")})}


def _archive_readme(base, ana, manifest, total_raw, full):
    stem = os.path.splitext(base)[0]
    L = [f"# White Box Research Archive — {base}\n",
         "A complete, self-contained dump of this model for research: the **weights** (the stored bits) plus **every "
         "White Box read** we compute over them — no inference, no model load; the values are addressed straight from "
         "the stored bits.\n",
         "## Folder layout",
         "- `README.md` — this file.",
         f"- `whitebox_{stem}.json` / `.md` — the full White Box analysis (structure, precision map, per-layer depth "
         "profile, tensor stats, expert health, captured-circuit read, attention/IPC bus, OS-primitive map).",
         "- `weights/` — per tensor: `<name>.qbin` = the RAW stored bytes (the weights, exactly as quantized), and "
         "`<name>.sample.f32` = a pure-Python dequantized float32 sample (little-endian) where the quant type is one we "
         "decode (F32/F16/Q4_0/Q8_0).",
         "- `weights_manifest.json` — for every tensor: name, quant type (`tid`), shape, byte size, how much was dumped, "
         "and the sample's min/max/mean/absmax.",
         "- `sidecars/` — the White Box index (`.wbindex.json`: tensor name → offset / type / shape) so the raw bytes "
         "are fully self-describing.\n",
         "## Dequantizing the raw weights",
         "Each `.qbin` is the tensor's bytes copied verbatim from the model file. Use `weights_manifest.json` (and "
         "`sidecars/*.wbindex.json`) for the quant type + shape. `tid`: 0=F32, 1=F16, 2=Q4_0, 8=Q8_0 (others: the ggml "
         "spec). Reference pure-Python decoders (no numpy) for Q4_0 / Q8_0 are in `host/sdc_read.py`.\n",
         "## This dump",
         f"- tensors: **{len(manifest)}**  ·  raw weight bytes: **{round(total_raw/1e6,1)} MB**"
         + ("  (FULL tensors)" if full else "  (bounded per-tensor slice of the raw bytes)"),
         f"- float32-sampled tensors: **{sum(1 for m in manifest if 'sample' in m)}**",
         "\n_Generated by the White Box — reads from stored bits, no inference, no model load, pure Python._\n"]
    return "\n".join(L)


def _export_md(art):
    a = art["sections"].get("anatomy", {})
    L = [f"# White Box readout — {art['model']}\n",
         f"> Read from stored bits, **no inference, no model load**. system free-RAM drop "
         f"{art['meta']['free_ram_drop_MB']} MB in {art['meta']['seconds']}s (Titan addressed via mmap; the rest is the "
         f"Python skin + bounded windows).\n",
         "## Structure",
         f"- arch **{a.get('arch')}** · **{a.get('params_B')}B** params · {a.get('size_GB')} GB on disk · "
         f"{a.get('layers')} layers · hidden {a.get('hidden')} · vocab {a.get('vocab')}",
         f"- experts **{a.get('experts')}** (used {a.get('expert_used')}) · attention heads **{a.get('head_count')}** "
         f"over {a.get('head_count_kv')} KV lines · {a.get('n_tensors')} tensors"]
    if a.get("types"):
        L.append("- quant mix: " + " · ".join(f"{t['t']}×{t['n']}" for t in a["types"]))
    pm = art["sections"].get("precision_map", {})
    if isinstance(pm, dict) and pm.get("roles"):
        L.append("\n## Precision map (mixed-quant recipe by role)")
        for r in pm["roles"]:
            L.append(f"- {r.get('role')}: **{r.get('main')}** (~{r.get('bpw')} bpw · {(r.get('params') or 0)/1e6:.0f}M params)")
    cir = art["sections"].get("circuit_by_layer", {})
    if isinstance(cir, dict) and cir:
        L.append("\n## Captured circuit across depth (transistors / latches / decoder)")
        L.append("| layer | transistors | amp | inh | dead | latch hold | latch reset | decoder orth |")
        L.append("|--:|--:|--:|--:|--:|--:|--:|--:|")
        for lyr in sorted(cir, key=lambda x: int(x)):
            c = cir[lyr]
            if "error" in c:
                L.append(f"| {lyr} | — | | | | | | _{c['error'][:40]}_ |")
            else:
                cc, lo = c["counts"], c["logic"]
                L.append(f"| {lyr} | {c['n_ff']} | {cc['amp']} | {cc['inh']} | {cc['dead']} | "
                         f"{lo['latch_hold']} | {lo['latch_reset']} | {lo['decode_orth']} |")
    ipc = art["sections"].get("ipc_by_layer", {})
    if isinstance(ipc, dict) and ipc:
        L.append("\n## IPC bus (attention) — per sampled layer")
        L.append("| layer | heads | KV lines | GQA | head_dim | chan_mean | chan_max |")
        L.append("|--:|--:|--:|--:|--:|--:|--:|")
        for lyr in sorted(ipc, key=lambda x: int(x)):
            c = ipc[lyr]
            if "error" not in c:
                L.append(f"| {lyr} | {c['n_head']} | {c['n_kv']} | ×{c['gqa_group']} | {c['head_dim']} | "
                         f"{c['chan_mean']} | {c['chan_max']} |")
    eh = art["sections"].get("expert_health", {})
    if isinstance(eh, dict) and eh:
        L.append("\n## Expert health (dead / collapsed experts)")
        for nm, r in eh.items():
            L.append(f"- {nm}: _{r['error'][:60]}_" if "error" in r else
                     f"- {nm}: {r['n_expert']} experts · **{r['n_dead']} dead** · std {r['min']}–{r['max']}")
    dc = art["sections"].get("decompiler")
    if isinstance(dc, dict):
        L.append("\n## Decompiler (bits → meaning)")
        if dc.get("status"):
            L.append(f"- _{dc['status']}_")
        for w, r in (dc.get("words") or {}).items():
            near = r.get("near") if isinstance(r, dict) else None
            if near:
                L.append(f"- **{w}** → " + ", ".join(str(t.get("tok")) for t in near[:8]))
    om = art["sections"].get("os_map", {})
    if isinstance(om, dict) and om.get("rows"):
        L.append("\n## Computer-in-the-weights (OS-primitive map)")
        for r in om["rows"]:
            L.append(f"- **{r['os']}** ← {r['titan']} — {r['measure']}")
    if art.get("errors"):
        L.append("\n## Sections that errored (recorded, not fatal)")
        for k, v in art["errors"].items():
            L.append(f"- {k}: {v}")
    return "\n".join(L) + "\n"


# ── THE GATED SANDBOX (docs/WHITEBOX_SANDBOX.md — owner spec, NON-NEGOTIABLE) ─────────────────────────────────────────
# The server NEVER touches the model. EVERY model operation runs in an isolated child process (whitebox_worker.py):
# one-way argv in (no channel back), read the stored bits over mmap, FREEZE the result to a file, EXIT (a dead process
# draws zero compute). The server reads the static frozen file only AFTER the child has ended, then renders. Do NOT
# reintroduce any in-process model call in this server — that is the exact violation this whole design removes.
_WORKER_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whitebox_worker.py")
_WRITE_OPS = {"edittoken", "align_edit", "destroy", "scale", "paste", "revert"}
_WRITE_LOCK = threading.Lock()
_JOB_SEQ = [0]


def _launch(op, path, kw):
    """Spawn the gated sandbox child for one op: input one-way via argv (no pipe read back), it reads the stored bits,
    FREEZES its result to a temp file and EXITS. Returns (Popen, result_path)."""
    _JOB_SEQ[0] += 1
    res = os.path.join(tempfile.gettempdir(), f"wbop_{_JOB_SEQ[0]}_{int(time.time() * 1000)}.json")
    argv = [sys.executable, _WORKER_PY, "--op", op, "--path", path or "", "--kw", json.dumps(kw or {}), "--result", res]
    proc = subprocess.Popen(argv, cwd=os.path.dirname(_WORKER_PY),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)   # one-way: no pipe read back
    return proc, res


def _read_frozen(res, proc):
    """Open the sandbox's STATIC frozen result — only ever called AFTER the child has exited. Cleans up the temp file."""
    if res and os.path.exists(res):
        try:
            out = json.load(open(res, encoding="utf-8"))
        except Exception as e:
            out = {"error": f"result read failed: {e}"}
        try:
            os.remove(res)
        except Exception:
            pass
        return out
    return {"error": f"sandbox exited ({proc.returncode if proc else '?'}) with no result"}


def _sandboxed(op, path, kw=None):
    """Blocking gated-sandbox call: launch the child, WAIT for it to END, then read the static frozen result. The server
    itself runs none of the compute. Edit ops are serialized so two writers never overlap (ThreadingHTTPServer keeps
    other requests responsive meanwhile)."""
    kw = kw or {}
    lock = _WRITE_LOCK if op in _WRITE_OPS else None
    if lock:
        lock.acquire()
    try:
        proc, res = _launch(op, path, kw)
        try:
            proc.wait(timeout=300)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            return {"error": "sandbox timed out"}
        return _read_frozen(res, proc)
    finally:
        if lock:
            lock.release()


# path → worker op. Every one of these runs in the gated sandbox (a child that ends), never in this server process.
_SANDBOX_ROUTES = {
    "/precision": "precision", "/layerroles": "layerroles", "/decompile": "decompile", "/meaning": "meaning",
    "/analogy": "analogy", "/vec": "vec", "/editpreview": "editpreview", "/edittoken": "edittoken",
    "/tensor": "tensor", "/experts": "experts", "/align_axis": "align_axis", "/align_edit": "align_edit",
    "/direction": "direction", "/circuitry": "circuitry", "/interconnect": "interconnect", "/osmap": "osmap",
    "/param_decode": "param_decode", "/param_scan": "param_scan", "/token_neurons": "token_neurons",
    "/search": "search", "/destroy": "destroy", "/scale": "scale", "/paste": "paste", "/genome": "genome",
    "/revert": "revert", "/create": "create",
}


def load_file(path):
    with LOCK:
        EMBED["cancel"] = True                                    # abort any in-flight build for the previous model
        STATE.update(path=path, anat=None, vocab=None, E_mm=None, dim=None, ety=None, err="", loading=True)
        EMBED.update(building=False, ready=False, err="", cancel=False, progress=0.0, path=None)
    try:
        STATE["anat"] = anatomy(path)
    except Exception as e:
        STATE["err"] = f"read failed: {e}"
    STATE["loading"] = False
    # NEVER LOAD A MODEL, EVER (owner). Opening a model READS THE INDEX (anatomy) and nothing else — ~0 host RAM.
    # No embedding memmap-attach here, no resident copy, and above all NO BUILD of the 1.5 GB decompiler matrix.
    # The decompiler attaches its index LAZILY + MEMMAP-ONLY, on demand, only when its own tab/read is invoked
    # (start_embed_build) — and it never constructs a resident embedding. See start_embed_build / SUPERREADMESTUPID.


# ------------------------------------------------------------------ background layer scan (can be slow on the 70B)

def _scan_job(job_id, path, role):
    try:
        JOBS[job_id]["result"] = layer_scan(path, role)
    except Exception as e:
        JOBS[job_id]["result"] = {"error": str(e)}
    JOBS[job_id]["done"] = True


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>White Box - parameter analyzer</title>
<meta name=viewport content="width=device-width,initial-scale=1"><style>
:root{--ink:#0A0D13;--panel:#121722;--panel2:#0E131C;--line:#232A38;--text:#E7EBF3;--muted:#8A94A8;--dim:#5B6579;
--amber:#FFB020;--cyan:#3AD6C6;--good:#0ca30c;--warn:#fab219;--crit:#d03b3b;--bad:#F0803C;
/* categorical (dataviz-validated dark order); sequential blue; diverging blue<->red + neutral */
--s1:#3987e5;--s2:#199e70;--s3:#c98500;--s4:#e66767;--s5:#9085e9;--s6:#d95926;--pos:#3987e5;--neg:#e66767;--midn:#383835;
--mono:ui-monospace,"Cascadia Code",Consolas,monospace;--sans:system-ui,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--ink);color:var(--text);font-family:var(--sans);font-size:15px}
.top{display:flex;align-items:center;gap:14px;padding:13px 22px;border-bottom:1px solid var(--line);background:var(--panel2);position:sticky;top:0;z-index:5;flex-wrap:wrap}
.brand{font-family:var(--mono);font-weight:700;letter-spacing:.02em}.brand .b{color:var(--amber)}
.top .muted{color:var(--muted);font-size:12.5px}
select,input,button{font-family:var(--mono);font-size:13px;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 11px}
button{cursor:pointer;color:var(--amber);border-color:#3a3320}button:hover{background:rgba(255,176,32,.08)}
button.danger{color:var(--bad);border-color:#5a2f1a}button.danger:hover{background:rgba(240,128,60,.1)}
.tabs{display:flex;gap:4px;padding:0 22px;border-bottom:1px solid var(--line);background:var(--panel2);position:sticky;top:53px;z-index:4;overflow-x:auto}
.tab{padding:11px 15px;font-family:var(--mono);font-size:12.5px;color:var(--muted);border-bottom:2px solid transparent;cursor:pointer;white-space:nowrap}
.tab:hover{color:var(--text)}.tab.on{color:var(--amber);border-bottom-color:var(--amber)}
.wrap{max-width:1180px;margin:0 auto;padding:22px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:860px){.grid{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:18px}
.card h2{margin:0 0 4px;font-size:15px;font-family:var(--mono);letter-spacing:.04em;color:var(--amber);text-transform:uppercase}
.card .sub{color:var(--muted);font-size:12.5px;margin-bottom:14px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-family:var(--mono);font-size:13px}
.kv .k{color:var(--muted)}.kv .v{color:var(--text);font-variant-numeric:tabular-nums}
.pill{display:inline-block;font-family:var(--mono);font-size:11.5px;border:1px solid var(--line);border-radius:100px;padding:3px 9px;margin:2px 4px 2px 0;color:var(--muted)}
.pill b{color:var(--text)}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:500}
td.mdl{color:var(--text)}td .t{color:var(--cyan)}tr.click{cursor:pointer}tr.click:hover td{background:rgba(255,255,255,.02)}
.tok{display:inline-block;font-family:var(--mono);font-size:13px;border:1px solid var(--line);border-radius:8px;padding:5px 10px;margin:3px 4px 0 0;color:var(--text)}
.tok.hot{border-color:#7a5410;color:var(--amber);background:rgba(255,176,32,.07)}
.tok.hid{border-color:#4d4488;color:var(--s5);background:rgba(144,133,233,.08)}
.tok .s{color:var(--dim);font-size:11px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
canvas{width:100%;height:120px;display:block;background:#05070C;border:1px solid var(--line);border-radius:8px}
.note{color:var(--dim);font-size:12px;margin-top:8px}.err{color:var(--bad)}
.stat{display:inline-block;margin-right:22px}.stat .n{font-family:var(--mono);font-size:20px;color:var(--text)}.stat .l{color:var(--muted);font-size:11px}
.bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden}.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--amber))}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:640px){.two{grid-template-columns:1fr}}
.mut{color:var(--muted);font-size:12px;font-family:var(--mono)}
.hide{display:none}
.leg{display:flex;flex-wrap:wrap;gap:6px 14px;margin:8px 0 2px}.lg{font-family:var(--mono);font-size:11.5px;color:var(--muted);display:flex;align-items:center;gap:5px}
.lg i{width:10px;height:10px;border-radius:2px;display:inline-block}
canvas.tall{height:auto}
</style></head><body>
<div class=top>
  <div class=brand>WHITE<span class=b>BOX</span></div>
  <div class=muted>parameter research instrument &mdash; see &amp; edit the bits (no inference)</div>
  <div style="flex:1"></div>
  <select id=models></select>
  <input id=path placeholder="or a full path to a .gguf" style="width:210px">
  <button onclick=loadFile()>Import</button>
</div>
<div class=tabs id=tabs></div>
<div class=wrap id=main><div class=card><div class=sub>Pick a parameter file above and click Import.</div></div></div>

<script>
const TABS=['Overview','Precision map','Layers','Circuitry','System','Decompiler','Tokens','Align','Tensor scope','Search + destroy','Genome','Create','Export'];
let A=null, TAB=0;
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function post(u){return j(u,{method:'POST'})}
function esc(s){return (s+'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function el(id){return document.getElementById(id)}
/* the decompiler index builds once per model in the background; show progress + Cancel, auto-run the query when ready */
let EMBPOLL=null;
function cancelEmbed(){fetch('/embed_cancel');}
function embedWait(outId,rerun){const o=el(outId);if(!o)return;
  async function tick(){let s;try{s=await j('/embed_status');}catch(e){return;}
    if(s.ready){if(EMBPOLL){clearInterval(EMBPOLL);EMBPOLL=null;}rerun();return;}
    if(!s.building){if(EMBPOLL){clearInterval(EMBPOLL);EMBPOLL=null;}
      o.innerHTML='<div class="note'+(s.err&&s.err!=='cancelled'?' err':'')+'">'+esc(s.err==='cancelled'?'index build cancelled — run again to rebuild':(s.err||'index not ready'))+'</div>';return;}
    const pct=Math.round((s.progress||0)*100);
    o.innerHTML=`<div class=note>Building the decompiler index (once per model) &mdash; <b>${pct}%</b> <button onclick=cancelEmbed()>Cancel</button><div class=bar style="margin-top:6px"><i style="width:${pct}%"></i></div></div>`;}
  if(EMBPOLL)clearInterval(EMBPOLL);tick();EMBPOLL=setInterval(tick,600);}
function building(r){return r&&r.building===true;}
async function init(){const m=await j('/models');const s=el('models');
  s.innerHTML=m.models.map(f=>`<option value="${f}">${f}</option>`).join('')||'<option>no .gguf found</option>';}
function tabsBar(){el('tabs').innerHTML=TABS.map((t,i)=>`<div class="tab${i==TAB?' on':''}" onclick=go(${i})>${t}</div>`).join('');}
function go(i){TAB=i;tabsBar();draw();}
async function loadFile(){const p=el('path').value.trim()||el('models').value;
  el('main').innerHTML='<div class=card><div class=sub>Reading '+esc(p)+' &hellip;</div></div>';
  A=await j('/load?path='+encodeURIComponent(p));TAB=0;tabsBar();draw();}

function draw(){if(!A){return;} if(A.error){el('main').innerHTML='<div class=card><div class="sub err">'+esc(A.error)+'</div></div>';return;}
  ({0:tOverview,1:tPrecision,2:tLayers,3:tCircuit,4:tSystem,5:tDecompile,6:tTokens,7:tAlign,8:tScope,9:tDestroy,10:tGenome,11:tCreate,12:tExport}[TAB]||tOverview)();}

/* ---- chart library (canvas, self-contained; dataviz palette; one axis per chart; direct-labeled) ---- */
const CSS=getComputedStyle(document.documentElement);
function cvar(n){return CSS.getPropertyValue(n).trim();}
const QCOL={F32:'--s1',BF16:'--s2',F16:'--s2',Q8_0:'--s2',Q6_K:'--s3',Q5_K:'--s5',Q5_0:'--s5',Q4_K:'--s6',Q4_0:'--s4',Q3_K:'--pos',Q2_K:'--neg'};
function qcol(t){return cvar(QCOL[t]||'--muted');}
function ctx2(id){const c=el(id),g=c.getContext('2d'),d=devicePixelRatio||1,rc=c.getBoundingClientRect();
  c.width=rc.width*d;c.height=rc.height*d;g.setTransform(d,0,0,d,0,0);g.clearRect(0,0,rc.width,rc.height);
  g.font='11px ui-monospace,Consolas,monospace';return {g,W:rc.width,H:rc.height};}
function legend(items){return '<div class=leg>'+items.map(x=>`<span class=lg><i style="background:${x.c}"></i>${esc(x.l)}</span>`).join('')+'</div>';}
/* horizontal bars: items=[{label,value,color,tag}]; one axis (value); direct value labels */
function hbars(id,items,opt){opt=opt||{};const {g,W,H}=ctx2(id);const n=items.length;if(!n)return;
  const gut=opt.gutter||140,rowH=Math.min(opt.rowH||22,(H-6)/n),bh=Math.max(6,rowH-7),plot=W-gut-52;
  const mx=opt.max||Math.max(...items.map(i=>i.value))||1;
  items.forEach((it,i)=>{const y=i*rowH+3;g.fillStyle=cvar('--muted');g.textAlign='left';g.textBaseline='middle';
    g.fillText((it.label+'').slice(0,20),2,y+bh/2);
    const w=Math.max(1,it.value/mx*plot);g.fillStyle=it.color||cvar('--s1');
    if(g.roundRect){g.beginPath();g.roundRect(gut,y,w,bh,3);g.fill();}else g.fillRect(gut,y,w,bh);
    g.fillStyle=cvar('--text');g.textAlign='left';g.fillText(opt.fmt?opt.fmt(it.value):(''+it.value),gut+w+6,y+bh/2);
    if(it.tag){g.fillStyle=cvar('--dim');g.textAlign='right';g.fillText(it.tag,W-2,y+bh/2);}});}
/* single-series line vs index (one axis) */
function linechart(id,ys,opt){opt=opt||{};const {g,W,H}=ctx2(id);if(!ys.length)return;
  const mn=opt.min!=null?opt.min:Math.min(...ys),mx=opt.max!=null?opt.max:Math.max(...ys),sp=(mx-mn)||1,pad=18;
  g.strokeStyle=cvar('--line');g.lineWidth=1;g.beginPath();g.moveTo(pad,H-pad);g.lineTo(W-4,H-pad);g.stroke();
  g.strokeStyle=opt.color||cvar('--s1');g.lineWidth=1.8;g.beginPath();
  ys.forEach((v,i)=>{const x=pad+i/(ys.length-1||1)*(W-pad-6),y=(H-pad)-((v-mn)/sp)*(H-pad-8);i?g.lineTo(x,y):g.moveTo(x,y);});g.stroke();
  g.fillStyle=opt.color||cvar('--s1');ys.forEach((v,i)=>{const x=pad+i/(ys.length-1||1)*(W-pad-6),y=(H-pad)-((v-mn)/sp)*(H-pad-8);g.beginPath();g.arc(x,y,1.7,0,7);g.fill();});
  g.fillStyle=cvar('--muted');g.textAlign='left';g.textBaseline='top';g.fillText((opt.ylab||'')+' '+(''+mx).slice(0,7),2,2);g.fillText((''+mn).slice(0,7),2,H-12);}
/* diverging bars around a center: rows sorted by signed score (blue + / red -) */
function diverge(id,rows){const {g,W,H}=ctx2(id);if(!rows.length)return;
  const gut=96,rowH=Math.min(20,(H-4)/rows.length),bh=Math.max(5,rowH-7),cx=gut+(W-gut-8)/2,half=(W-gut-8)/2;
  const mx=Math.max(...rows.map(r=>Math.abs(r.score)))||1;
  g.strokeStyle=cvar('--midn');g.lineWidth=1;g.beginPath();g.moveTo(cx,0);g.lineTo(cx,H);g.stroke();
  rows.forEach((r,i)=>{const y=i*rowH+2;g.fillStyle=cvar('--muted');g.textAlign='left';g.textBaseline='middle';
    g.fillText((r.tok+'').slice(0,13),2,y+bh/2);
    const w=Math.abs(r.score)/mx*half,pos=r.score>=0;g.fillStyle=pos?cvar('--pos'):cvar('--neg');
    const x=pos?cx:cx-w;if(g.roundRect){g.beginPath();g.roundRect(x,y,w,bh,3);g.fill();}else g.fillRect(x,y,w,bh);
    g.fillStyle=cvar('--dim');g.textAlign=pos?'left':'right';g.fillText((r.score>0?'+':'')+r.score,pos?cx+w+4:cx-w-4,y+bh/2);});}

/* ---- Export (scrape everything this model has → one per-model artifact) ---- */
let EXPPOLL=null;
function tExport(){const a=A;const stem=(a.file||'model').replace('.gguf','');
  el('main').innerHTML=`<div class=grid>
    <div class=card><h2>Export &mdash; scrape this model into one artifact</h2>
      <div class=sub>${esc(a.file||'')} &mdash; reads everything from the stored bits (no inference, no model load) and writes
        <b>whitebox_${esc(stem)}.md</b> + <b>.json</b> to your TitanSDC folder.</div>
      <div class=note>Structure &middot; precision recipe &middot; depth profile &middot; expert health &middot; value
        distributions &middot; the captured transistor / latch / decoder circuit &middot; the attention IPC bus &middot;
        the OS-primitive map. Every read is a bounded window &mdash; ~0 RAM, no parse.</div>
      <div class=row style="margin-top:10px;gap:18px;flex-wrap:wrap">
        <label><input type=checkbox id=exfull> full circuit (every layer, not 3 sampled)</label>
        <label><input type=checkbox id=exall> all experts (full dead-expert map)</label>
        <label><input type=checkbox id=exdec> include decompiler (bits&rarr;meaning; needs the f16 index)</label>
      </div>
      <div style="margin-top:12px"><button onclick=runExport()>Scrape &rarr; artifact</button>
        <span id=exstat class=mut></span></div>
      <div id=exout style="margin-top:12px"></div>
    </div>
    <div class=card><h2>Researcher Archive &mdash; the weights + all White Box data</h2>
      <div class=sub>Pick any installed model and dump <b>everything</b> into one folder for researchers: the raw weights
        (the stored bits, per tensor) + a pure-Python float32 sample + the full White Box analysis + a self-describing
        index. Pure python, no numpy, ~0 RAM (streamed), gated sandbox.</div>
      <div class=row style="margin-top:10px;gap:12px;flex-wrap:wrap">
        <span class=mut>model</span><select id=arcmodel></select>
        <label><input type=checkbox id=arcfull> full tensors (huge; default = a bounded slice per tensor)</label>
        <label><input type=checkbox id=arcdec> include decompiler</label>
      </div>
      <div style="margin-top:12px"><button onclick=runArchive()>Build archive</button>
        <span id=arcstat class=mut></span></div>
      <div id=arcout style="margin-top:12px"></div>
    </div></div>`;
  arcModels();}
let ARCPOLL=null;
async function arcModels(){try{const m=await j('/models');el('arcmodel').innerHTML=(m.models||[]).map(f=>`<option>${esc(f)}</option>`).join('')||'<option>no .gguf found</option>';
  const cur=A&&A.file;if(cur&&m.models&&m.models.includes(cur))el('arcmodel').value=cur;}catch(e){}}
async function runArchive(){
  const model=el('arcmodel').value, full=el('arcfull').checked?1:0, dec=el('arcdec').checked?1:0;
  el('arcstat').textContent=' reading the weights off the stored bits…'; el('arcout').innerHTML='';
  let r; try{r=await post('/archive?model='+encodeURIComponent(model)+'&full='+full+'&decompile='+dec);}catch(e){el('arcstat').textContent=''+e;return;}
  if(r.error){el('arcstat').textContent=r.error;return;}
  if(!r.job){el('arcstat').textContent='no job';return;}
  if(ARCPOLL)clearInterval(ARCPOLL);
  ARCPOLL=setInterval(async()=>{
    let s; try{s=await j('/archivepoll?job='+r.job);}catch(e){return;}
    if(!s.done){el('arcstat').textContent=' dumping weights + analysis…';return;}
    clearInterval(ARCPOLL);ARCPOLL=null;const d=s.result||{};
    if(d.error){el('arcstat').textContent=d.error;return;}
    el('arcstat').textContent=' done in '+d.seconds+'s · '+d.n_tensors+' tensors · '+d.raw_MB+' MB weights · '+d.sampled+' sampled · free-RAM drop '+d.free_ram_drop_MB+' MB';
    el('arcout').innerHTML='<div class=note>archive folder:<br><b>'+esc(d.dir||'')+'</b><br>weights/ &middot; weights_manifest.json &middot; sidecars/ &middot; README.md &middot; '+esc((d.analysis&&d.analysis.md)||'')+'</div>';
  },1000);}
async function runExport(){
  const full=el('exfull').checked?1:0, allexp=el('exall').checked?1:0, dec=el('exdec').checked?1:0;
  el('exstat').textContent=' scraping the bits…'; el('exout').innerHTML='';
  let r; try{r=await post('/export?full='+full+'&allexp='+allexp+'&decompile='+dec);}catch(e){el('exstat').textContent=''+e;return;}
  if(r.error){el('exstat').textContent=r.error;return;}
  if(!r.job){el('exstat').textContent='no job';return;}
  if(EXPPOLL)clearInterval(EXPPOLL);
  EXPPOLL=setInterval(async()=>{
    let s; try{s=await j('/exportpoll?job='+r.job);}catch(e){return;}
    if(!s.done){el('exstat').textContent=' scraping the bits…';return;}
    clearInterval(EXPPOLL);EXPPOLL=null;
    const d=s.result||{};
    if(d.error){el('exstat').textContent=d.error;return;}
    el('exstat').textContent=' done in '+d.seconds+'s · free-RAM drop '+d.free_ram_drop_MB+' MB · '+(d.sections||[]).length+' sections';
    const errs=Object.keys(d.errors||{}).length?('<div class="note err">errored: '+esc(Object.keys(d.errors).join(', '))+'</div>'):'';
    el('exout').innerHTML='<div class=note>wrote <b>'+esc(d.md)+'</b><br>and <b>'+esc(d.json)+'</b></div>'+errs+
      '<pre style="max-height:440px;overflow:auto;padding:11px;border:1px solid var(--line);border-radius:6px;font:12px ui-monospace,Consolas,monospace;white-space:pre-wrap">'+esc(d.md_text||'')+'</pre>';
  },800);}

/* ---- Overview ---- */
function tOverview(){const a=A;
  // param mass per quant type (the storage the precision costs)
  const byq={};a.tensors.forEach(t=>{byq[t.type]=(byq[t.type]||0)+t.params;});
  const qitems=Object.entries(byq).sort((x,y)=>y[1]-x[1]).map(([t,p])=>({label:t,value:p/1e6,color:qcol(t)}));
  el('main').innerHTML=`<div class=grid>
    <div class=card><h2>Anatomy</h2><div class=sub>${esc(a.file)} &mdash; structure from metadata</div>
      <div class=kv>
        <div class=k>architecture</div><div class=v>${a.arch}</div>
        <div class=k>parameters</div><div class=v>${a.params_B} B</div>
        <div class=k>file size</div><div class=v>${a.size_GB} GB</div>
        <div class=k>hidden dim</div><div class=v>${a.hidden}</div>
        <div class=k>layers</div><div class=v>${a.layers}</div>
        <div class=k>experts (used)</div><div class=v>${a.experts?(a.experts+' ('+a.expert_used+' active)'):'dense'}</div>
        <div class=k>vocab</div><div class=v>${a.vocab}</div>
        <div class=k>tensors</div><div class=v>${a.n_tensors}</div>
      </div>
      <div class=note>Params live in storage; only what an operator reads costs energy (the read-energy law, docs/SDC.md).</div></div>
    <div class=card><h2>Where the params live</h2><div class=sub>param mass by quant type &mdash; the storage each precision costs</div>
      <canvas id=qc style="height:${Math.max(80,qitems.length*26)}px"></canvas>
      ${legend(qitems.map(i=>({c:i.color,l:i.label})))}</div></div>`;
  hbars('qc',qitems,{fmt:v=>(v/1e3>=1?(v/1e3).toFixed(1)+'B':v.toFixed(0)+'M')});}

/* ---- Precision map ---- */
async function tPrecision(){el('main').innerHTML='<div class=card><div class=sub>reading the quant recipe &hellip;</div></div>';
  const r=await j('/precision');if(r.error){el('main').innerHTML='<div class=card><div class="sub err">'+esc(r.error)+'</div></div>';return;}
  const roles=r.roles.slice(0,22);
  const bars=roles.map(x=>({label:x.role,value:x.params/1e6,color:qcol(x.main),tag:(x.bpw||'?')+'bpw · '+x.main}));
  const present=[...new Set(roles.map(x=>x.main))];
  const rows=roles.map(x=>{const ty=x.types.map(t=>`<span class=pill><b>${t.t}</b>&times;${t.n}</span>`).join('');
    return `<tr><td class=mdl>${esc(x.role)}</td><td>${(x.params/1e6).toFixed(1)}M</td><td class=t>${x.bpw||'?'} bpw</td><td>${ty}</td></tr>`;}).join('');
  el('main').innerHTML=`<div class=card><h2>Precision map</h2>
    <div class=sub>the mixed-quant RECIPE &mdash; each role's param mass, colored by the precision it got. No standard tool shows this.</div>
    <canvas id=pc style="height:${Math.max(120,roles.length*24)}px"></canvas>
    ${legend(present.map(t=>({c:qcol(t),l:t})))}
    <div class=note>Bar color = the quant type; a higher-bit color on a role means the quantizer PROTECTED it (often attention-value, ffn_down, the output head). The recipe is the model's real anatomy.</div>
    <div style="overflow-x:auto;margin-top:12px"><table><tr><th>role</th><th>params</th><th>bits/wt</th><th>quant types</th></tr>${rows}</table></div></div>`;
  hbars('pc',bars,{fmt:v=>(v/1e3>=1?(v/1e3).toFixed(1)+'B':v.toFixed(0)+'M'),gutter:150});}

/* ---- Layers ---- */
let LR=null;
async function tLayers(){if(!LR){LR=(await j('/layerroles')).roles||[];}
  el('main').innerHTML=`<div class=card><h2>Layers</h2><div class=sub>go past token_embd into the real layers &mdash; per-layer std &amp; near-zero across depth</div>
    <div class=row><span class=mut>role</span><select id=lrole>${LR.map(r=>`<option>${esc(r)}</option>`).join('')}</select>
      <button onclick=runLayers()>Scan depth</button><span id=lstat class=mut></span></div>
    <div id=lout class=note>Pick a role (e.g. ffn_down, attn_q) and scan. Dequantizes a sample of each layer &mdash; RAM-safe.</div></div>`;}
async function runLayers(){const role=el('lrole').value;el('lstat').textContent='scanning &hellip;';el('lout').innerHTML='';
  const st=await j('/layerscan?role='+encodeURIComponent(role));const id=st.job;
  let r=null;for(let k=0;k<600;k++){await new Promise(z=>setTimeout(z,400));const p=await j('/scanpoll?job='+id);if(p.done){r=p.result;break;}el('lstat').textContent='scanning &hellip; '+(p.note||'');}
  el('lstat').textContent='';if(!r||r.error){el('lout').innerHTML='<span class="err">'+esc(r?r.error:'timeout')+'</span>';return;}
  const L=r.layers;if(!L.length){el('lout').textContent='no per-layer tensors for this role';return;}
  const stds=L.map(x=>x.std),zeros=L.map(x=>x.zero*100);
  const rows=L.map(x=>`<tr><td>${x.layer}</td><td class=t>${x.type}</td><td>${x.std}</td><td>${x.absmax}</td><td>${(x.zero*100).toFixed(2)}%</td></tr>`).join('');
  el('lout').innerHTML=`<div class=two>
      <div><div class=mut>std vs layer depth (0 &rarr; ${L.length-1})</div><canvas id=lc1 style="height:150px"></canvas></div>
      <div><div class=mut>near-zero % vs layer depth</div><canvas id=lc2 style="height:150px"></canvas></div></div>
    <div class=note>${esc(r.role)}: flat = uniform across depth; a trend = features concentrating or neurons dying deeper. Two axes, so two charts.</div>
    <div style="overflow-x:auto;margin-top:10px"><table><tr><th>layer</th><th>type</th><th>std</th><th>absmax</th><th>near-zero</th></tr>${rows}</table></div>`;
  linechart('lc1',stds,{color:cvar('--s1'),ylab:'std'});linechart('lc2',zeros,{color:cvar('--s3'),ylab:'%',min:0});}

/* ---- Circuitry: the weights AS TRANSISTORS (CAPTURED_CIRCUIT.md, INV-141/145/151) ---- */
function transColor(cls){return cvar({amp:'--s1',inh:'--neg',pass:'--muted',dead:'--dim'}[cls]||'--muted');}
function vhist(id,h,color,lab){const o=ctx2(id),g=o.g,W=o.W,H=o.H,b=h.bins,n=b.length;if(!n)return;
  const mx=Math.max(...b)||1,pad=16,bw=(W-pad-4)/n;
  g.strokeStyle=cvar('--line');g.lineWidth=1;g.beginPath();g.moveTo(pad,H-14);g.lineTo(W-2,H-14);g.stroke();
  b.forEach((v,i)=>{const hh=(v/mx)*(H-24),x=pad+i*bw;g.fillStyle=color;
    if(g.roundRect){g.beginPath();g.roundRect(x,H-14-hh,Math.max(1,bw-1.5),hh,1);g.fill();}else g.fillRect(x,H-14-hh,Math.max(1,bw-1),hh);});
  g.fillStyle=cvar('--muted');g.textAlign='left';g.textBaseline='top';g.fillText(lab,2,2);
  g.fillText((''+h.lo).slice(0,5),pad,H-12);g.textAlign='right';g.fillText((''+h.hi).slice(0,5),W-2,H-12);}
function circuitSchem(id,d){const o=ctx2(id),g=o.g,W=o.W,H=o.H,s=d.sample;if(!s||!s.length)return;const busY=24;
  g.strokeStyle=cvar('--cyan');g.lineWidth=2;g.beginPath();g.moveTo(10,busY);g.lineTo(W-10,busY);g.stroke();
  g.fillStyle=cvar('--muted');g.textAlign='left';g.textBaseline='bottom';g.fillText('residual bus  (attention = interconnect)',12,busY-4);
  const n=s.length,cw=(W-20)/n,mI=Math.max(...s.map(t=>t.infl))||1,mG=Math.max(...s.map(t=>t.gate))||1,mD=Math.max(...s.map(t=>t.drain))||1;
  s.forEach((t,i)=>{const cx=10+cw*(i+0.5),sz=10+26*Math.sqrt(t.infl/mI),col=transColor(t.cls),chY=busY+30,chH=sz,chW=Math.max(8,sz*0.66);
    g.globalAlpha=t.cls==='dead'?0.4:1;
    g.strokeStyle=col;g.lineWidth=1+3.5*(t.drain/mD);g.beginPath();g.moveTo(cx,busY);g.lineTo(cx,chY);g.stroke();       /* drain wire to bus */
    g.fillStyle=col;if(g.roundRect){g.beginPath();g.roundRect(cx-chW/2,chY,chW,chH,2);g.fill();}else g.fillRect(cx-chW/2,chY,chW,chH); /* channel body */
    g.strokeStyle=cvar('--amber');g.lineWidth=1+2.5*(t.gate/mG);const gl=6+12*(t.gate/mG);
    g.beginPath();g.moveTo(cx-chW/2-gl,chY+chH*0.5);g.lineTo(cx-chW/2,chY+chH*0.5);g.stroke();                          /* gate stub (the switch) */
    g.strokeStyle=col;g.lineWidth=1.4;g.beginPath();g.moveTo(cx,chY+chH);g.lineTo(cx,chY+chH+7);g.stroke();            /* source stub */
    g.globalAlpha=1;
    if(t.cls!=='dead'){g.fillStyle=t.rho>=0?cvar('--s1'):cvar('--neg');g.textAlign='center';g.textBaseline='top';g.fillText(t.rho>=0?'+':'−',cx,chY+chH+9);}});}
let CKT=null;
function tCircuit(){const nl=(A&&A.layers)||1;
  el('main').innerHTML=`<div class=card><h2>Circuitry &mdash; the weights as transistors</h2>
    <div class=sub>A trained model is a captured electronic circuit. In a SwiGLU FFN each hidden unit is a TRANSISTOR: the gate row switches it (SiLU(g&middot;x)), the up row is the source it passes, the down column is the drain into the residual bus. Recovered straight from the stored bits &mdash; no inference.</div>
    <div class=row><span class=mut>layer</span><input id=cklayer value="0" style="width:56px"><span class=mut>of ${nl}</span>
      <button onclick=runCircuit()>Map the circuit</button><span id=ckstat class=mut></span></div>
    <div id=ckout class=note>Pick a layer and map it. Dequantizes one FFN block's gate/up/down &mdash; RAM-safe.</div></div>
  <div class=card style="background:var(--panel2)"><h2>The transistor &mdash; math (separate from the picture)</h2>
    <div class=sub>the same components, stated formally</div>
    <div class=mut style="line-height:1.85;font-size:12.5px">
      y&#8323; = SiLU(g&#8323;&middot;x) &middot; (u&#8323;&middot;x)&nbsp; &rarr; &nbsp;residual &#43;= y&#8323;&middot;d&#8323;&nbsp;&nbsp;<span style="color:var(--dim)">&mdash; SwiGLU neuron j is one transistor</span><br>
      &bull; <b>GATE</b> g&#8323;: SiLU(g&#8323;&middot;x) is the switch &mdash; the only conditional in a forward pass (INV-141). Gate gain = &#8214;g&#8323;&#8214; (transconductance / switch sharpness).<br>
      &bull; <b>SOURCE</b> u&#8323;: the signal u&#8323;&middot;x it passes when open. Source gain = &#8214;u&#8323;&#8214;.<br>
      &bull; <b>DRAIN</b> d&#8323;: the down-column; drives the residual bus. Drain drive = &#8214;d&#8323;&#8214; (fan-out).<br>
      &bull; <b>&rho;&#8323; = cos(g&#8323;, u&#8323;)</b>: self-gating &mdash; &rho;&gt;0 = AMPLIFIER (gate opens for the very input the source amplifies), &rho;&lt;0 = INHIBITOR (clamp).<br>
      &bull; <b>DEAD</b> &hArr; &#8214;g&#8323;&#8214;&middot;&#8214;d&#8323;&#8214; &asymp; 0 (never conducts, or never drives). &nbsp; Influence = &#8214;g&#8323;&#8214;&middot;&#8214;u&#8323;&#8214;&middot;&#8214;d&#8323;&#8214;.<br>
      &bull; The 1/0 switch has a noise-margin tolerance band; the analog spread inside it IS the inference variance (INV-145).
    </div></div>
  <div class=card><h2>Parameter decode &mdash; down to the param</h2>
    <div class=sub>project a SINGLE parameter through the embedding &rarr; the meaning it reads (gate/up row) or writes (down column), no inference. Or scan a layer for its INTERPRETABLE neurons (the cleanest = near-monosemantic concept cells).</div>
    <div class=row>
      <span class=mut>layer</span><input id=pdl value="29" style="width:52px">
      <span class=mut>kind</span><select id=pdk><option>down</option><option>gate</option><option>up</option></select>
      <span class=mut>neuron</span><input id=pdj value="577" style="width:64px">
      <button onclick=pdDecode()>Decode this param</button>
      <button onclick=pdScan()>Find interpretable neurons</button><span id=pdstat class=mut></span></div>
    <div id=pdout class=note>Late layers (near the last) decode cleaner &mdash; try layer 29 down, then click a found neuron to decode it.</div></div>`;}
async function pdDecode(){const L=el('pdl').value||'0',K=el('pdk').value,J=el('pdj').value||'0';el('pdstat').textContent='decoding …';
  const r=await j(`/param_decode?layer=${encodeURIComponent(L)}&kind=${K}&j=${encodeURIComponent(J)}`);el('pdstat').textContent='';
  if(r.error){el('pdout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('pdout').innerHTML=`<div class=mut style="margin-bottom:6px">${esc(r.label)} &mdash; ${r.ms}ms</div>`+
    r.near.map(n=>`<span class="tok${n.sim>0.25?' hot':''}">${esc(n.tok)} <span class=s>${n.sim}</span></span>`).join('');}
async function pdScan(){const L=el('pdl').value||'0',K=el('pdk').value;el('pdstat').textContent='scanning the layer (one embedding pass) …';
  const r=await j(`/param_scan?layer=${encodeURIComponent(L)}&kind=${K}&n=96`);el('pdstat').textContent='';
  if(r.error){el('pdout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('pdout').innerHTML=`<div class=mut style="margin-bottom:4px">${r.n} neurons scanned in ${r.ms}ms &mdash; the cleanest (highest top-1 sim) are the interpretable ones. Click one to decode it.</div>`+
    '<div style="overflow-x:auto"><table><tr><th>neuron</th><th>top sim</th><th>concept (nearest tokens)</th></tr>'+
    r.neurons.slice(0,20).map(nu=>`<tr class=click onclick="el('pdj').value=${nu.j};pdDecode()"><td class=t>#${nu.j}</td><td>${nu.top}</td><td>${esc(nu.near.map(x=>x.tok).join(', '))}</td></tr>`).join('')+'</table></div>';}
/* ---- Tokens: the token associations stored in the parameters (dedicated, findable) ---- */
function tkLayers(){return (A&&A.layers)?A.layers:30;}
function tTokens(){const nl=tkLayers();el('main').innerHTML=`
  <div class=card><h2>Type a token &rarr; the neurons that carry it</h2>
    <div class=sub>Type any token and see which parameters (neurons) of a layer store its concept &mdash; the concept associates, straight from the weights, no inference. +sim = a neuron that carries the concept, &minus;sim = one that opposes it.</div>
    <div class=row><input id=tnw value="king" style="width:130px" placeholder="a token">
      <span class=mut>layer</span><input id=tnl value="${nl-1}" style="width:52px"><span class=mut>of 0&ndash;${nl-1}</span>
      <span class=mut>kind</span><select id=tnk><option>down</option><option>gate</option><option>up</option></select>
      <button onclick=tnFind()>Find its neurons</button><span id=tnstat class=mut></span></div>
    <div id=tnout class=note>e.g. type <b>king</b> at layer ${nl-1} &mdash; the neurons whose stored concept is closest to it.</div></div>
  <div class=card><h2>Decode a token &mdash; its stored associations</h2><div class=sub>a word &rarr; its nearest stored tokens (what it is associated with in the weights)</div>
    <div class=row><input id=tkw value="king" style="width:130px"><button onclick=tkTok()>Decode</button></div>
    <div id=tkwout></div></div>
  <div class=card><h2>Scan a layer &mdash; its cleanest concept neurons</h2>
    <div class=sub>which parameters are near-monosemantic concept cells (ranked by clarity). Late layers (near ${nl-1}) decode cleanest.</div>
    <div class=row><span class=mut>layer</span><input id=tkl value="${nl-1}" style="width:52px"><span class=mut>of 0&ndash;${nl-1}</span>
      <span class=mut>kind</span><select id=tkk><option>down</option><option>gate</option><option>up</option></select>
      <button onclick=tkScan()>Find concept neurons</button><span id=tkstat class=mut></span></div>
    <div id=tkout class=note>Each row is one parameter and the token concept it carries.</div></div>`;}
async function tnFind(){const w=el('tnw').value.trim(),L=el('tnl').value||'0',K=el('tnk').value;el('tnstat').innerHTML='searching the layer &hellip;';
  const r=await j(`/token_neurons?word=${encodeURIComponent(w)}&layer=${encodeURIComponent(L)}&kind=${K}`);el('tnstat').textContent='';
  if(building(r)){embedWait('tnout',tnFind);return;} if(r.error){el('tnout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('tnout').innerHTML=`<div class=mut style="margin-bottom:4px">neurons of layer ${r.layer} (${r.kind}) carrying &lsquo;${esc(r.word)}&rsquo; &mdash; ${r.n} scanned in ${r.ms}ms, ranked by concept match. Click one to decode it fully in Circuitry &rarr; Parameter decode.</div>`+
    '<div style="overflow-x:auto"><table><tr><th>parameter</th><th>concept match (sim)</th></tr>'+
    r.neurons.map(nu=>`<tr><td class=t>L${r.layer}.${r.kind}#${nu.j}</td><td style="color:${nu.sim>=0?'var(--s1)':'var(--neg)'}">${nu.sim>=0?'+':''}${nu.sim}</td></tr>`).join('')+'</table></div>';}
async function tkScan(){const L=el('tkl').value||'29',K=el('tkk').value;el('tkstat').innerHTML='scanning the layer (one embedding pass) &hellip;';
  const r=await j(`/param_scan?layer=${encodeURIComponent(L)}&kind=${K}&n=128`);el('tkstat').textContent='';
  if(building(r)){embedWait('tkout',tkScan);return;} if(r.error){el('tkout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('tkout').innerHTML=`<div class=mut style="margin-bottom:4px">${r.n} parameters scanned in ${r.ms}ms &mdash; ranked by how cleanly each maps to a concept (clarity = top-1 similarity).</div>`+
    '<div style="overflow-x:auto"><table><tr><th>parameter</th><th>clarity</th><th>token concept (nearest)</th></tr>'+
    r.neurons.slice(0,30).map(nu=>`<tr><td class=t>L${L}.${K}#${nu.j}</td><td>${nu.top}</td><td>${esc(nu.near.map(x=>x.tok).join(', '))}</td></tr>`).join('')+'</table></div>';}
async function tkTok(){const w=el('tkw').value.trim();el('tkwout').innerHTML='<div class=note>decoding &hellip;</div>';
  const r=await j('/decompile?word='+encodeURIComponent(w));if(building(r)){embedWait('tkwout',tkTok);return;}
  if(r.error){el('tkwout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  const nb=r.neighbors||r.near||r.results||[];
  el('tkwout').innerHTML=nb.length?nb.map(n=>`<span class="tok hot">${esc(n.tok)} <span class=s>${n.sim}</span></span>`).join(''):'<div class=note>no neighbors</div>';}

/* ---- Create: describe a model, Titan composes it from the White-Box pool data ---- */
function tCreate(){el('main').innerHTML=`
  <div class=card><h2>Create a model from scratch</h2>
    <div class=sub>Describe what you want &mdash; Titan proposes a build from the measured POOL (best-source-per-role from the scan, precision recipe, dim-compatibility). Same-dim roles graft as reversible White-Box weight blends; cross-arch experts route reference-based (the SGS folder, no copy).</div>
    <div class=row><input id=cdesc value="a 200B reasoning giant" style="width:320px" placeholder="e.g. a fast tiny coder"><button onclick=runCreate()>Propose the build</button><span id=cstat class=mut></span></div>
    <div id=cout class=note>Describe a model (size + specialty) and Titan composes a spec from the measured pool.</div></div>`;}
async function runCreate(){const d=el('cdesc').value.trim();el('cstat').innerHTML='composing from the scan &hellip;';
  const r=await j('/create?desc='+encodeURIComponent(d));el('cstat').textContent='';
  if(r.error){el('cout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  const gr=r.grafts.map(g=>`<tr><td class=t>${esc(g.role)}</td><td>${esc(g.source)}</td><td>${g.hidden}</td></tr>`).join('');
  const rt=r.routed_experts.map(g=>`<tr><td class=t>${esc(g.role)}</td><td>${esc(g.source)}</td><td>${g.hidden}</td></tr>`).join('');
  el('cout').innerHTML=`<div class=note style="border:1px solid #3a3320;border-radius:8px;padding:8px 11px;color:var(--amber)">This is the BUILD RECIPE (a proposal) &mdash; composed from the measured pool. No model file is written yet: applying it (the reversible weight blends + reference routes below) is the build step, which is heavy on a small box and stays owner-gated. Nothing was output to disk when you clicked.</div>
    <div class=row style="margin-top:8px">
      <span class=stat><span class=n>${esc(r.specialty)}</span><span class=l>specialty</span></span>
      <span class=stat><span class=n style="font-size:13px">${esc(r.base)}</span><span class=l>base (hidden ${r.base_hidden})</span></span>
      <span class=stat><span class=n style="color:var(--s2)">${r.n_graftable}</span><span class=l>same-dim grafts (weight blend)</span></span>
      <span class=stat><span class=n>${r.n_routed}</span><span class=l>routed experts (reference)</span></span></div>
    <div class=mut style="margin:8px 0 2px">operators to bake: <b>${r.operators.join(', ')}</b></div>
    <div class=note>${esc(r.note)}</div>
    <div class=two style="margin-top:10px">
      <div><div class=mut>same-dim grafts (reversible weight blends)</div><div style="overflow-x:auto"><table><tr><th>role</th><th>best source</th><th>dim</th></tr>${gr||'<tr><td colspan=3>none same-dim as base</td></tr>'}</table></div></div>
      <div><div class=mut>routed experts (reference, no copy)</div><div style="overflow-x:auto"><table><tr><th>role</th><th>best source</th><th>dim</th></tr>${rt}</table></div></div></div>
    <div class=note>${esc(r.how)}</div>`;}
async function runCircuit(){const L=el('cklayer').value||'0';el('ckstat').innerHTML='dequantizing the layer &hellip;';
  const r=await j('/circuitry?layer='+encodeURIComponent(L));el('ckstat').textContent='';
  if(r.error){el('ckout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  CKT=r;const c=r.counts;
  el('ckout').innerHTML=`<div class=row style="margin-top:4px">
      <span class=stat><span class=n>${r.n_ff}</span><span class=l>transistors &middot; layer ${r.layer}</span></span>
      <span class=stat><span class=n style="color:var(--s1)">${c.amp}</span><span class=l>amplifiers &rho;&gt;0</span></span>
      <span class=stat><span class=n style="color:var(--neg)">${c.inh}</span><span class=l>inhibitors &rho;&lt;0</span></span>
      <span class=stat><span class=n>${c.pass}</span><span class=l>pass</span></span>
      <span class=stat><span class=n style="color:var(--dim)">${c.dead}</span><span class=l>dead</span></span>
      <span class=stat><span class=n>${(r.agg.top5_gate_energy*100).toFixed(0)}%</span><span class=l>gate energy in top 5%</span></span></div>
    <div class=mut style="margin:8px 0 2px">Schematic &mdash; the ${r.sample.length} highest-throughput transistors (glyph size &prop; influence, gate stub &prop; gate gain, drain wire &prop; drain drive, +/&minus; = &rho; sign)</div>
    <canvas id=cksch style="height:150px"></canvas>
    ${legend([{c:cvar('--s1'),l:'amplifier'},{c:cvar('--neg'),l:'inhibitor'},{c:cvar('--muted'),l:'pass'},{c:cvar('--dim'),l:'dead'},{c:cvar('--cyan'),l:'residual bus'}])}
    <div class=two style="margin-top:12px">
      <div><div class=mut>gate gain &#8214;g&#8214; (transconductance)</div><canvas id=ckg style="height:120px"></canvas></div>
      <div><div class=mut>drain drive &#8214;d&#8214; (fan-out)</div><canvas id=ckd style="height:120px"></canvas></div></div>
    <div style="margin-top:12px"><div class=mut>gate&harr;source alignment &rho; &mdash; left = inhibitors, right = amplifiers</div><canvas id=ckr style="height:120px"></canvas></div>
    <div class=card style="margin-top:14px;background:var(--panel2)"><h2>Logic &amp; memory &mdash; latches, decoder, wiring (from the weights)</h2>
      <div class=sub>a neuron that writes back to the residual where its gate reads is a LATCH &mdash; it holds a bit. Memory is just transistors, so Titan is not stateless.</div>
      <div class=row>
        <span class=stat><span class=n style="color:var(--s2)">${r.logic.latch_hold}</span><span class=l>LATCHES &mdash; hold cells (&lambda;&gt;0)</span></span>
        <span class=stat><span class=n style="color:var(--neg)">${r.logic.latch_reset}</span><span class=l>reset cells (&lambda;&lt;0)</span></span>
        <span class=stat><span class=n>${r.logic.decode_orth}</span><span class=l>decoder orthogonality (lower = sharper)</span></span>
        <span class=stat><span class=n>${r.logic.drain_conv}</span><span class=l>drain convergence (fan-in)</span></span></div>
      <div class=mut style="margin:8px 0 2px">&lambda; = cos(gate, drain) over all transistors &mdash; right lobe = LATCHES (self-hold = memory), left = reset</div>
      <canvas id=cklam style="height:120px"></canvas>
      <div class=note>&lambda;&#8323; = cos(g&#8323;, d&#8323;): the gate reads x from the residual, the drain writes back to it &mdash; same space, so a positive cosine is positive feedback = a held bit. Titan holds <b>${r.logic.latch_hold} latch-like cells in layer ${r.layer} alone</b> &mdash; native memory in the weights (INV-157). The gate projection is also an address DECODER (orthogonality ${r.logic.decode_orth} &mdash; it selects a distinct neuron per input): the gates are already built in.</div></div>
    <div class=note>Every glyph and bar is measured from the stored weights of layer ${r.layer} &mdash; no inference. The model's circuitry, recovered from the bits.</div>`;
  circuitSchem('cksch',r);vhist('ckg',r.hist.gate,cvar('--amber'),'count');vhist('ckd',r.hist.drain,cvar('--s2'),'count');vhist('ckr',r.hist.rho,cvar('--s5'),'count');vhist('cklam',r.logic.lam_hist,cvar('--s2'),'count');}

/* ---- System: OS capabilities + the IPC bus (from the weights) ---- */
function tSystem(){el('main').innerHTML=`
  <div class=card><h2>System &mdash; OS capabilities in the weights</h2>
    <div class=sub>Titan's weights already implement the primitives of a general-purpose computer &mdash; compute, memory, a scheduler/decoder, an IPC bus, storage, and an I/O codec. Measured from the file, no inference.</div>
    <div class=row><button onclick=runOs()>Map the OS capabilities</button><span id=osstat class=mut></span></div>
    <div id=osout class=note>Click to read the OS-primitive map straight from the stored weights.</div></div>
  <div class=card><h2>IPC bus &mdash; attention as interprocess communication</h2>
    <div class=sub>each position is a process; attention is the BUS that moves data between them. Per head: read/address strength &times; write bandwidth = the channel.</div>
    <div class=row><span class=mut>layer</span><input id=iclayer value="0" style="width:56px"><button onclick=runIpc()>Map the IPC bus</button><span id=icstat class=mut></span></div>
    <div id=icout class=note>Map the attention interconnect of a layer.</div></div>`;}
async function runOs(){el('osstat').innerHTML='measuring &hellip;';const r=await j('/osmap');el('osstat').textContent='';
  if(r.error){el('osout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  const rows=r.rows.map(x=>`<tr><td class=mdl><b>${esc(x.os)}</b></td><td class=t>${esc(x.titan)}</td><td>${esc(x.measure)}</td></tr>`).join('');
  el('osout').innerHTML=`<div style="overflow-x:auto"><table><tr><th>OS primitive</th><th>Titan structure</th><th>measured (from the weights)</th></tr>${rows}</table></div>
    <div class=note>${esc(r.summary)}</div>`;}
async function runIpc(){const L=el('iclayer').value||'0';el('icstat').innerHTML='dequantizing attention &hellip;';
  const r=await j('/interconnect?layer='+encodeURIComponent(L));el('icstat').textContent='';
  if(r.error){el('icout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  const bars=r.heads.map(h=>({label:'head '+h.h,value:h.chan,color:cvar('--s1'),tag:'r'+h.read+' w'+h.write}));
  el('icout').innerHTML=`<div class=row style="margin-top:4px">
      <span class=stat><span class=n>${r.n_head}</span><span class=l>IPC channels (heads)</span></span>
      <span class=stat><span class=n>${r.n_kv}</span><span class=l>shared KV lines (GQA&times;${r.gqa_group})</span></span>
      <span class=stat><span class=n>${r.chan_mean}</span><span class=l>mean channel</span></span>
      <span class=stat><span class=n>#${r.chan_top[0]}</span><span class=l>strongest channel</span></span></div>
    <div class=mut style="margin:8px 0 2px">per-head IPC channel strength = read(address) &times; write(bandwidth), layer ${r.layer}</div>
    <canvas id=icc style="height:${Math.max(120,r.n_head*20)}px"></canvas>
    <div class=note>${r.n_head} attention heads = ${r.n_head} IPC channels routing data between positions over ${r.n_kv} shared key/value lines (GQA). The model's interconnect, read from the weights.</div>`;
  hbars('icc',bars,{fmt:v=>v.toFixed(2),gutter:74});}

/* ---- Decompiler ---- */
function tDecompile(){el('main').innerHTML=`
  <div class=card><h2>Hidden meaning search</h2><div class=sub>give a concept (one or more words) &mdash; it builds the meaning's centroid from the bits and finds every token that carries it. HIDDEN matches (violet) are semantically close but string-unrelated: cross-lingual, morphological, connotative &mdash; the meaning a text search can't see.</div>
    <div class=row><input id=mq value="royal, monarch" style="width:260px"><button onclick=ms()>Search meaning</button></div>
    <div id=msout></div></div>
  <div class=card><h2>Decompiler &mdash; bits &rarr; meaning</h2><div class=sub>the meaning stored in a single token's embedding bits</div>
    <div class=row><input id=word value="king" style="width:130px"><button onclick=dc()>Decompile</button></div>
    <div id=dcout></div></div>
  <div class=card><h2>Vector arithmetic</h2><div class=sub>king &minus; man + woman &rarr; queen. On a quantized table it gets NOISY &mdash; that noise IS the measured cost of quantization.</div>
    <div class=row><input id=aa value="king" style="width:90px"><span class=mut>&minus;</span><input id=ab value="man" style="width:90px"><span class=mut>+</span><input id=ac value="woman" style="width:90px"><button onclick=an()>Solve</button></div>
    <div id=anout></div></div>
  <div class=card><h2>Bit-edit &rarr; measure</h2><div class=sub>edit a token's STORED bits, watch its meaning move. "I changed what this token means at the storage layer &mdash; here's the damage." Reversible.</div>
    <div class=row><input id=ew value="king" style="width:90px"><span class=mut>&rarr;</span><input id=et value="queen" style="width:90px">
      <span class=mut>amt</span><input id=eamt value="0.6" style="width:52px">
      <button onclick=edPrev()>Preview</button><button class=danger onclick=edWrite()>Write bits</button><button class=danger onclick=edZero()>Scrub</button></div>
    <div id=edout></div></div>`;}
function toks(arr,hot){return arr.map((n,i)=>`<span class="tok${i<hot?' hot':''}">${esc(n.tok)} <span class=s>${n.sim}</span></span>`).join('');}
async function ms(){const q=el('mq').value.trim();el('msout').innerHTML='<div class=note>decompiling the meaning &hellip;</div>';
  const r=await j('/meaning?q='+encodeURIComponent(q));if(building(r)){embedWait('msout',ms);return;}if(r.error){el('msout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  const chips=r.results.map(n=>`<span class="tok${n.hidden?' hid':''}">${esc(n.tok)} <span class=s>${n.sim}</span></span>`).join('');
  el('msout').innerHTML=`<div class=note>meaning of [${esc(r.query)}] &rarr; ${r.results.length} carriers, <b>${r.n_hidden} HIDDEN</b> (violet: string-unrelated)${r.missing.length?'; skipped (not single tokens): '+esc(r.missing.join(', ')):''}</div>`+chips+
    `<canvas id=msc style="height:${Math.max(90,r.results.length*20)}px;margin-top:10px"></canvas>
     ${legend([{c:cvar('--s1'),l:'surface (string matches)'},{c:cvar('--s5'),l:'hidden (meaning only)'}])}`;
  hbars('msc',r.results.map(n=>({label:n.tok,value:n.sim,color:n.hidden?cvar('--s5'):cvar('--s1')})),{max:1,fmt:v=>v.toFixed(3),gutter:120});}
async function dc(){const w=el('word').value.trim();el('dcout').innerHTML='<div class=note>decompiling &hellip;</div>';
  const r=await j('/decompile?word='+encodeURIComponent(w));if(building(r)){embedWait('dcout',dc);return;}if(r.error){el('dcout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('dcout').innerHTML=`<div class=note>'${esc(w)}' (${r.dim}-dim ${r.type}) &rarr; nearest meaning:</div>`+toks(r.near,3)+
    `<canvas id=dcc style="height:${Math.max(80,r.near.length*22)}px;margin-top:10px"></canvas>`;
  hbars('dcc',r.near.map(n=>({label:n.tok,value:n.sim,color:cvar('--s1')})),{max:1,fmt:v=>v.toFixed(3),gutter:120});}
async function an(){const a=el('aa').value.trim(),b=el('ab').value.trim(),c=el('ac').value.trim();el('anout').innerHTML='<div class=note>solving &hellip;</div>';
  const r=await j(`/analogy?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&c=${encodeURIComponent(c)}`);
  if(building(r)){embedWait('anout',an);return;}if(r.error){el('anout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('anout').innerHTML=`<div class=note>${esc(r.expr)} &rarr;</div>`+toks(r.near,3);}
async function edPrev(){const a=el('ew').value.trim(),b=el('et').value.trim();el('edout').innerHTML='<div class=note>previewing &hellip;</div>';
  const r=await j(`/editpreview?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  if(building(r)){embedWait('edout',edPrev);return;}if(r.error){el('edout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('edout').innerHTML=`<div class=note>preview: '${esc(a)}' 60% &rarr; '${esc(b)}' (not written):</div>`+toks(r.near,2);}
async function edWrite(){const w=el('ew').value.trim(),t=el('et').value.trim(),amt=el('eamt').value.trim();
  if(!confirm(`Write bits: nudge '${w}' ${Math.round(amt*100)}% toward '${t}' in the REAL file? (reversible via Genome)`))return;
  measureEdit(`/edittoken?word=${encodeURIComponent(w)}&toward=${encodeURIComponent(t)}&amount=${amt}&zero=0`);}
async function edZero(){const w=el('ew').value.trim();
  if(!confirm(`Scrub '${w}' embedding to zero in the REAL file? (reversible via Genome)`))return;
  measureEdit(`/edittoken?word=${encodeURIComponent(w)}&zero=1`);}
async function measureEdit(u){el('edout').innerHTML='<div class=note>writing + measuring &hellip;</div>';const r=await post(u);
  if(building(r)){el('edout').innerHTML='<div class=note>the decompiler index is still building — try again in a moment.</div>';return;}
  if(r.error){el('edout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('edout').innerHTML=`<div class=note>${esc(r.note)}</div>
    <div class=two style="margin-top:10px">
      <div><div class=mut>BEFORE</div>${toks(r.before,2)}</div>
      <div><div class=mut>AFTER (written bits)</div>${toks(r.after,2)}</div></div>
    <div class=note>a bit-edit is a meaning-edit. Revert in the Genome tab.</div>`;}

/* ---- Align (targeted, sighted alignment) ---- */
function tAlign(){el('main').innerHTML=`
  <div class=card><h2>Alignment axis &mdash; define it, SEE it</h2>
    <div class=sub>Blind alignment (a global RLHF nudge you can't inspect) warps the semantic-pattern logic. Here alignment is SIGHTED: build a direction from contrasting concepts, then watch exactly which meanings it moves — before touching a weight.</div>
    <div class=row><span class=mut>toward</span><input id=apos value="honest, accurate, grounded" style="width:200px">
      <span class=mut>away from</span><input id=aneg value="fabricated, fake, guessed" style="width:200px"><button onclick=axis()>Analyze axis</button></div>
    <div id=axout></div></div>
  <div class=card><h2>Targeted realignment</h2>
    <div class=sub>move ONE token along the axis (targeted, not global), reversibly, and MEASURE it: the token's projection + neighbors before/after. Define an axis above first.</div>
    <div class=row><span class=mut>token</span><input id=aw value="king" style="width:110px">
      <span class=mut>strength</span><input id=astr value="0.3" style="width:52px">
      <button class=danger onclick="realign(1)">Realign toward +</button><button class=danger onclick="realign(-1)">Realign against −</button></div>
    <div id=arout></div></div>`;}
async function axis(){const pos=el('apos').value.trim(),neg=el('aneg').value.trim();el('axout').innerHTML='<div class=note>projecting the vocab onto the axis &hellip;</div>';
  const r=await j(`/align_axis?pos=${encodeURIComponent(pos)}&neg=${encodeURIComponent(neg)}`);
  if(building(r)){embedWait('axout',axis);return;}if(r.error){el('axout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  const rows=[...r.aligned.slice(0,10),...r.anti.slice(0,10)];
  el('axout').innerHTML=`<div class=note>axis ${esc(r.desc)} &mdash; the tokens it most moves (blue = toward, red = away). This is the SIGHT: you see what the direction captures.</div>
    <canvas id=axc style="height:${rows.length*20+8}px"></canvas>
    ${legend([{c:cvar('--pos'),l:'toward (aligned)'},{c:cvar('--neg'),l:'away (anti-aligned)'}])}`;
  diverge('axc',rows);}
async function realign(sign){const w=el('aw').value.trim(),s=(parseFloat(el('astr').value)||0.3)*sign;
  if(!confirm(`Realign '${w}' by ${s>0?'+':''}${s} along the axis in the REAL file? Reversible via Genome.`))return;
  el('arout').innerHTML='<div class=note>realigning + measuring &hellip;</div>';
  const r=await post(`/align_edit?word=${encodeURIComponent(w)}&strength=${s}`);
  if(building(r)){el('arout').innerHTML='<div class=note>the decompiler index is still building — try again in a moment.</div>';return;}
  if(r.error){el('arout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  el('arout').innerHTML=`<div class=note>${esc(r.note)}</div>
    <div class=note>projection on the axis: <b>${r.proj_before}</b> &rarr; <b>${r.proj_after}</b> (moved ${(r.proj_after-r.proj_before>=0?'+':'')}${(r.proj_after-r.proj_before).toFixed(3)} &mdash; the targeted, measured shift)</div>
    <div class=two style="margin-top:10px">
      <div><div class=mut>BEFORE</div>${toks(r.before,2)}</div>
      <div><div class=mut>AFTER (realigned bits)</div>${toks(r.after,2)}</div></div>
    <div class=note>sighted + targeted + reversible. Revert in the Genome tab.</div>`;}

/* ---- Tensor scope ---- */
function tScope(){const rows=A.tensors.slice(0,120).map(t=>`<tr class=click onclick="scope('${esc(t.name)}')"><td class=mdl>${esc(t.name)}</td><td class=t>${t.type}</td><td>${JSON.stringify(t.shape)}</td><td>${(t.params/1e6).toFixed(1)}M</td></tr>`).join('');
  el('main').innerHTML=`<div class=card><h2>Tensor scope</h2><div class=sub>click a tensor &mdash; dequantize the bits, watch the stored values + where quant hurts</div>
    <div id=scopeout class=note>Click a tensor below.</div>
    <div style="overflow-x:auto;margin-top:12px"><table><tr><th>tensor</th><th>type</th><th>shape</th><th>params</th></tr>${rows}</table></div></div>`;}
async function scope(name){el('scopeout').innerHTML='<div class=note>dequantizing '+esc(name)+' &hellip;</div>';
  const r=await j('/tensor?name='+encodeURIComponent(name));const o=el('scopeout');
  if(r.error){o.innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  if(r.note){o.innerHTML=`<div class=note>${esc(name)} (${r.type}) &mdash; ${esc(r.note)}</div>`;return;}
  let stress='';if(r.stress){stress=`<div class=note style="margin-top:14px">Quant stress &mdash; per-${r.stress.block} block absmax (p99 ${r.stress.p99}, max ${r.stress.max}); the right tail is the outlier weights quantization hurts most:</div><canvas id=hs></canvas>`;}
  const exps=name.includes('exps.weight')?`<div style="margin-top:14px"><button onclick="experts('${esc(name)}')">Show expert health (find dead experts)</button><div id=exout></div></div>`:'';
  o.innerHTML=`<div style="margin-bottom:10px"><span class=stat><span class=n>${r.mean}</span><div class=l>mean</div></span>
    <span class=stat><span class=n>${r.std}</span><div class=l>std</div></span>
    <span class=stat><span class=n>${r.min} / ${r.max}</span><div class=l>min / max</div></span>
    <span class=stat><span class=n>${(r.sparsity*100).toFixed(1)}%</span><div class=l>near-zero</div></span>
    <span class=stat><span class=n style="color:var(--cyan)">${esc(name)}</span><div class=l>${r.type} ${JSON.stringify(r.shape)}</div></span></div>
    <div class=note>value distribution:</div><canvas id=hist></canvas>${stress}${exps}`;
  histc('hist',r.hist,r.edges);if(r.stress)histc('hs',r.stress.hist,r.stress.edges);}
async function experts(name){el('exout').innerHTML='<div class=note>measuring per-expert std &hellip;</div>';
  const r=await j('/experts?name='+encodeURIComponent(name));if(r.error){el('exout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  const items=r.stds.map((s,i)=>({label:'e'+i,value:s,color:s<1e-5?cvar('--crit'):cvar('--s2')}));
  el('exout').innerHTML=`<div class=note>${r.n_expert} experts, std ${r.min} &rarr; ${r.max}. ${r.dead.length} DEAD (red): [${r.dead.join(', ')||'none'}] &mdash; prune these in Search + destroy (prune expert #).</div>
    <canvas id=exc style="height:${Math.max(120,r.n_expert*7)}px"></canvas>
    ${legend([{c:cvar('--s2'),l:'active'},{c:cvar('--crit'),l:'dead (std≈0)'}])}`;
  hbars('exc',items,{fmt:v=>v.toFixed(4),gutter:44,rowH:Math.max(5,Math.min(16,700/r.n_expert))});}
function histc(id,hist,edges){const c=el(id),g=c.getContext('2d'),d=devicePixelRatio||1,rc=c.getBoundingClientRect();
  c.width=rc.width*d;c.height=rc.height*d;g.setTransform(d,0,0,d,0,0);const H=rc.height,Wd=rc.width,mx=Math.max(...hist),bw=Wd/hist.length;
  g.fillStyle='#FFB020';hist.forEach((v,i)=>{const h=(v/mx)*(H-16);g.globalAlpha=.85;g.fillRect(i*bw+1,H-h-2,bw-2,h);});
  g.globalAlpha=1;g.strokeStyle='#3AD6C6';g.beginPath();const zx=(0-edges[0])/(edges[edges.length-1]-edges[0])*Wd;g.moveTo(zx,0);g.lineTo(zx,H);g.stroke();}

/* ---- Search + destroy ---- */
function tDestroy(){el('main').innerHTML=`<div class=card><h2>Search + destroy</h2>
    <div class=sub>find tensors / tokens / metadata by name, then target REVERSIBLE pruning. Every edit is byte-exact-undoable in Genome.</div>
    <div class=row><select id=skind><option value=tensor>tensors</option><option value=token>tokens</option><option value=kv>metadata (KV)</option></select>
      <input id=sq placeholder="name / substring / regex" style="width:220px"><label class=mut><input type=checkbox id=srx> regex</label>
      <button onclick=doSearch()>Search</button><span id=sstat class=mut></span></div>
    <div id=sout></div></div>`;el('sq').addEventListener('keydown',e=>{if(e.key=='Enter')doSearch();});}
async function doSearch(){const kind=el('skind').value,q=el('sq').value.trim(),rx=el('srx').checked?1:0;
  el('sout').innerHTML='<div class=note>searching &hellip;</div>';
  const r=await j(`/search?kind=${kind}&q=${encodeURIComponent(q)}&rx=${rx}`);
  if(r.error){el('sout').innerHTML='<div class="note err">'+esc(r.error)+'</div>';return;}
  if(kind=='tensor'){el('sout').innerHTML=`<div class=note>${r.hits.length} tensors</div><div style="overflow-x:auto"><table><tr><th>tensor</th><th>type</th><th>shape</th><th>params</th><th>destroy</th></tr>`+
    r.hits.map(t=>`<tr><td class=mdl>${esc(t.name)}</td><td class=t>${t.type}</td><td>${JSON.stringify(t.shape)}</td><td>${(t.params/1e6).toFixed(1)}M</td>
      <td><button class=danger onclick="destroy('${esc(t.name)}','')">zero</button>
      ${t.name.includes('exps')?`<input id="ex_${cssid(t.name)}" placeholder=e# style="width:44px"><button class=danger onclick="destroy('${esc(t.name)}',el('ex_${cssid(t.name)}').value)">prune expert</button>`:''}
      <input id="sc_${cssid(t.name)}" placeholder="x" style="width:44px"><button onclick="scaleT('${esc(t.name)}')">scale</button></td></tr>`).join('')+`</table></div>`;}
  else if(kind=='token'){el('sout').innerHTML=`<div class=note>${r.hits.length} tokens</div>`+r.hits.map(t=>`<span class=tok>${esc(t.tok)} <span class=s>#${t.id}</span></span>`).join('');}
  else{el('sout').innerHTML=`<div class=note>${r.hits.length} keys</div><div style="overflow-x:auto"><table><tr><th>key</th><th>type</th><th>value</th></tr>`+
    r.hits.map(k=>`<tr><td class=mdl>${esc(k.key)}</td><td class=t>${esc(k.type)}</td><td>${esc(JSON.stringify(k.value)).slice(0,140)}</td></tr>`).join('')+`</table></div>`;}}
function cssid(s){return s.replace(/[^a-z0-9]/gi,'_');}
async function destroy(name,expert){const what=expert!==''?`expert ${expert} of ${name}`:name;
  if(!confirm(`DESTROY ${what} (zero its bits) in the REAL file? Reversible via Genome.`))return;
  el('sstat').textContent='destroying &hellip;';const r=await post(`/destroy?name=${encodeURIComponent(name)}&expert=${encodeURIComponent(expert)}`);
  el('sstat').innerHTML=r.error?`<span class=err>${esc(r.error)}</span>`:esc(r.note);}
async function scaleT(name){const f=el('sc_'+cssid(name)).value.trim();if(!f)return;
  if(!confirm(`Scale ${name} by ${f} in the REAL file? Reversible via Genome.`))return;
  el('sstat').textContent='scaling &hellip;';const r=await post(`/scale?name=${encodeURIComponent(name)}&factor=${encodeURIComponent(f)}`);
  el('sstat').innerHTML=r.error?`<span class=err>${esc(r.error)}</span>`:esc(r.note);}

/* ---- Genome ---- */
async function tGenome(){const r=await j('/genome');
  const rows=(r.log||[]).map(e=>`<tr><td>${e.seq}</td><td class=t>${esc(e.op)}</td><td class=mdl>${esc(e.note)}</td><td>${(e.len/1e3).toFixed(0)} KB</td></tr>`).join('');
  el('main').innerHTML=`<div class=card><h2>Genome &mdash; undo log</h2><div class=sub>every edit backs up the exact original bytes first. Revert = byte-exact restore.</div>
    <div class=row><button onclick=revertN(1)>Revert last</button><button class=danger onclick="revertN('all')">Revert ALL</button><span id=gstat class=mut></span></div>
    ${rows?`<div style="overflow-x:auto"><table><tr><th>#</th><th>op</th><th>target</th><th>backup</th></tr>${rows}</table></div>`:'<div class=note>no edits yet &mdash; the file is original.</div>'}</div>`;}
async function revertN(n){if(!confirm('Revert '+(n=='all'?'ALL edits':'the last edit')+'?'))return;
  el('gstat').textContent='reverting &hellip;';const r=await post('/revert?n='+n);el('gstat').textContent=`reverted ${r.reverted}, ${r.remaining||0} remain`;setTimeout(tGenome,600);}

init();
</script></body></html>"""


DIRLAB_PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>Direction Lab</title>
<style>
 body{background:#0b0e14;color:#dfe7f0;font:14px/1.5 system-ui,sans-serif;margin:0;padding:18px}
 h1{font-size:20px;margin:0 0 2px} h1 b{color:#f7a41d}
 .sub{color:#8b97a7;font-size:12px;margin-bottom:14px}
 .row{display:flex;gap:14px;flex-wrap:wrap}
 .card{background:#131823;border:1px solid #232b3a;border-radius:10px;padding:14px;margin-bottom:14px}
 .col{flex:1;min-width:270px}
 textarea{width:100%;height:88px;background:#05070b;color:#dfe7f0;border:1px solid #232b3a;border-radius:8px;padding:8px;font:12px monospace;box-sizing:border-box}
 label{display:block;color:#8b97a7;font-size:12px;margin:10px 0 2px}
 input[type=range]{width:100%}
 select,button{background:#1b2130;color:#dfe7f0;border:1px solid #232b3a;border-radius:7px;padding:7px 12px;font-size:13px;cursor:pointer}
 button.on{background:#f7a41d;color:#0b0e14;font-weight:700}
 .big{font-size:34px;font-weight:800;color:#37c98b} .big.zero{color:#e5534b}
 .n{display:flex;justify-content:space-between;font:12px monospace;margin-top:6px}
 .bar{height:6px;border-radius:3px;margin-bottom:2px}
 .tok{display:inline-block;background:#1b2130;border-radius:5px;padding:2px 7px;margin:2px;font:12px monospace}
 .hint{color:#5c6675;font-size:11px;font-weight:400;display:block;margin-top:3px}
</style></head><body>
<h1>Direction <b>Lab</b></h1>
<div class=sub>build a direction from a RIGHT pile vs a WRONG pile, then drag the dials and watch the model's own weights answer. zero inference.</div>
<div class=card><select id=model></select> <button onclick=loadM()>Load</button> <span id=mstat style=color:#8b97a7></span></div>
<div class=row>
  <div class="card col"><label>RIGHT (one per line) &mdash; saved across reloads</label><textarea id=right oninput=onpile()></textarea></div>
  <div class="card col"><label>WRONG (one per line) &mdash; saved across reloads</label><textarea id=wrong oninput=onpile()></textarea></div>
</div>
<div class=card>
  <label>layer <b id=lv>24</b></label><input id=layer type=range min=0 max=63 value=24 oninput="lv.textContent=this.value;go()">
  <label>top-k neurons <b id=kv>14</b></label><input id=k type=range min=4 max=40 value=14 oninput="kv.textContent=this.value;go()">
  <label>strip surface &mdash; remove the top-N principal (surface) axes before the direction <b id=sv>0</b>
    <span class=hint>peel the digit/length axis &mdash; if raw_norm survives, there's a seed UNDER the surface</span></label>
  <input id=strip type=range min=0 max=8 value=0 oninput="sv.textContent=this.value;go()">
  <label>projection</label>
  <button id=kdown class=on onclick="setKind('down')">down · writes</button>
  <button id=kgate onclick="setKind('gate')">gate · switch</button>
  <button id=kup onclick="setKind('up')">up · reads</button>
  <button id=normb onclick=toggleNorm()>per-string normalize: off</button>
</div>
<div class=row>
 <div class="card col"><label>raw_norm — the SEED DETECTOR (near 0 = classes look identical, no direction)</label>
   <div id=norm class=big>&mdash;</div><div id=meta style=color:#8b97a7;font-size:12px></div></div>
 <div class="card col"><label>cohesion &mdash; are the RIGHT answers a coherent cluster? (mean pairwise cosine)</label><div id=coh></div>
   <div class=hint>a real cluster: within-RIGHT high AND above cross. all three &asymp; equal = one blob (surface only).</div></div>
 <div class="card col"><label>deep neurons the direction fires (j : alignment)</label><div id=neurons></div></div>
</div>
<div class=row>
 <div class="card col"><label>what the direction MEANS (nearest tokens)</label><div id=near></div></div>
 <div class="card col"><label>meaning UNDER the surface (pure-digit tokens removed)</label><div id=deep></div></div>
</div>
<script>
let kind='down', busy=false, timer=null, norm=0;
const $=id=>document.getElementById(id);
const DEF_R="bitcoin\nethereum\ncrypto\nblockchain\nsatoshi", DEF_W="dollar\neuro\nbank\ncash\nfiat";
$('right').value=localStorage.getItem('dl_right')||DEF_R;      /* the two constraints persist across reloads — never wiped */
$('wrong').value=localStorage.getItem('dl_wrong')||DEF_W;
function onpile(){localStorage.setItem('dl_right',$('right').value);localStorage.setItem('dl_wrong',$('wrong').value);go();}
async function models(){let r=await fetch('/models').then(x=>x.json());$('model').innerHTML=(r.models||[]).map(m=>`<option>${m}</option>`).join('')}
async function loadM(){$('mstat').textContent='loading…';
  let a=await fetch('/load?path='+encodeURIComponent($('model').value)).then(x=>x.json());
  if(a&&a.layers){$('layer').max=a.layers-1;if(+$('layer').value>a.layers-1){$('layer').value=a.layers-1;lv.textContent=$('layer').value;}}
  for(let i=0;i<400;i++){let s=await fetch('/embed_status').then(x=>x.json());if(s.ready){$('mstat').textContent='ready ('+(a.arch||'')+', '+(a.layers||'?')+' layers)';go();return}await new Promise(r=>setTimeout(r,800));}
  $('mstat').textContent='(index still building…)'}
function setKind(k){kind=k;['down','gate','up'].forEach(x=>$('k'+x).className=x==k?'on':'');go()}
function toggleNorm(){norm=norm?0:1;$('normb').textContent='per-string normalize: '+(norm?'on':'off');$('normb').className=norm?'on':'';go()}
function go(){clearTimeout(timer);timer=setTimeout(compute,250)}
async function compute(){if(busy)return;busy=true;
  let u='/direction?right='+encodeURIComponent($('right').value)+'&wrong='+encodeURIComponent($('wrong').value)
       +'&layer='+$('layer').value+'&kind='+kind+'&k='+$('k').value+'&strip='+$('strip').value+'&norm='+norm;
  try{let d=await fetch(u).then(x=>x.json());render(d)}catch(e){$('meta').textContent=''+e}
  busy=false;}
function means(a){return (a||[]).map(t=>'<span class=tok>'+t.tok+' <b style=color:#8b97a7>'+t.sim+'</b></span>').join('')||'<span class=hint>none</span>'}
function crow(l,val){let v=(val==null?'—':(+val).toFixed(3));return '<div class=n><span>'+l+'</span><span>'+v+'</span></div>'}
function render(d){
  if(d.error){$('norm').textContent='—';$('meta').textContent=d.error;return}
  $('norm').textContent=(+d.raw_norm).toFixed(4);$('norm').className='big'+(d.raw_norm<0.05?' zero':'');
  $('meta').textContent=d.n_right+' right vs '+d.n_wrong+' wrong · layer '+d.layer+' · '+d.kind
    +(d.stripped?' · stripped '+d.stripped+' PC':'')+(d.norm?' · normed':'');
  let c=d.cohesion||{};
  $('coh').innerHTML=crow('within RIGHT',c.within_right)+crow('within WRONG',c.within_wrong)+crow('cross R×W',c.cross);
  let ns=d.neurons||[], mx=Math.max(0.001,...ns.map(n=>Math.abs(n.sim)));
  $('neurons').innerHTML=ns.map(n=>'<div class=n><span>j='+n.j+'</span><span>'+(n.sim>=0?'+':'')+n.sim+'</span></div>'
    +'<div class=bar style="width:'+(Math.abs(n.sim)/mx*100)+'%;background:'+(n.sim<0?'#e5534b':'#37c98b')+'"></div>').join('');
  $('near').innerHTML=means(d.near);
  $('deep').innerHTML=means(d.near_deep);
}
models();
fetch('/embed_status').then(x=>x.json()).then(s=>{if(s.ready)go()}).catch(()=>{});   /* warm model already attached → show instantly */
</script></body></html>"""


# ── FABLE TOOLS (additive port of the fable_* structure/security suite into 1.0, 2026-07-23) ──────────────────
# Each Run launches an ENDING child (argv in, stdout captured); the server never touches a model. Read-only. Same
# gated-sandbox law as the rest of this app. Served at /fable (page) + /fable_run (exec). Nothing existing is modified.
_FABLE_TOOLS = [
    ("fable_audit",     "Audit · backdoor scan",      "every tensor -> entropy-crater baked-circuit flags",       "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf"),
    ("fable_sweep",     "Sweep · full tensor stats",  "every tensor: stats + anomaly -> fable_sweep_data.json",   "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf"),
    ("fable_scan2",     "Scan · structural",          "per-row entropy anomaly localizer for one tensor",         "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf blk.0.ffn_gate.weight"),
    ("fable_direction", "Direction · manifold+value", "manifold-residual + NaN/Inf value-sanity on one tensor",   "C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf blk.0.ffn_gate.weight"),
    ("fable_ffndepth",  "FFN depth census",           "amp/inh/pass per layer -> the compute depth U-shape",      ""),
    ("fable_neurons",   "Neurons · monosemantic",     "rank a layer's neurons by token-projection monosemanticity","16 down 60 C:/llm/models/SmolLM2-360M-Instruct-Q8_0-CLEAN.gguf"),
    ("fable_concept",   "Concept · cross-lingual",    "nearest embedding neighbors of a word; flags other-script", "university"),
    ("fable_clean",     "Clean · free win?",          "anisotropy cleanup: does it help analogies + antonyms?",   ""),
    ("pfc_forge",       "Forge · build computers",    "build adders/ALUs from NAND gates and PROVE they compute", ""),
    ("wf_pfc_summary",  "PFC census · titan",         "how many computers + total gates baked into titan blk.1",  ""),
    ("wf_titancir_cells","TITANCIR · decode designs", "the 65 distinct baked circuit designs + tiling",           ""),
    ("wf_titancir_graph","TITANCIR · one gate graph", "reconstruct one baked circuit to a gate graph (expert nth)","0 0"),
    ("pfc_atlas",       "Silicon Atlas · census",     "enumerate + categorize every computer baked into titan",   ""),
    ("pfc_atlas_verify","Silicon Atlas · verify",     "prove a representative set of baked computers actually RUN",""),
    ("pfc_langton",     "Langton's Ant (forged)",     "forge Langton's Ant as a gate netlist, verify byte-exact", "--test"),
    ("pfc_turing",      "Turing machine (forged)",    "busy-beaver Turing machine as gates, runs to HALT byte-exact","--test"),
    ("pfc_cyclic",      "Cyclic CA (forged)",         "spiral-forming cyclic cellular automaton as gates, byte-exact","--test"),
]
_FABLE_LOCK = threading.Lock()


def _fable_run(mod, argstr):
    import shlex
    if mod not in [t[0] for t in _FABLE_TOOLS]:
        return {"ok": False, "out": "unknown tool"}
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, mod + ".py")
    if not os.path.exists(path):
        return {"ok": False, "out": f"not found: {mod}.py"}
    try: args = shlex.split(argstr or "", posix=False)
    except Exception: args = (argstr or "").split()
    t0 = time.time()
    try:
        with _FABLE_LOCK:                                      # one ending child at a time (gated sandbox)
            pr = subprocess.run([sys.executable, path] + args, cwd=here, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=300)
        out = (pr.stdout or "") + (("\n[stderr]\n" + pr.stderr) if pr.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        return {"ok": False, "out": "(timed out after 300s — run heavy models from the CLI)"}
    return {"ok": pr.returncode == 0, "out": out or "(no output)", "secs": round(time.time() - t0, 1)}


_FABLE_PAGE = """<!doctype html><html><head><meta charset=utf-8><title>White Box 1.0 - fable tools</title>
<style>
 body{background:#0b0f14;color:#d7dde5;font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;margin:0;padding:22px}
 h1{font-size:18px;margin:0 0 4px;color:#eaf2ff}.s{color:#8aa0b8;margin:0 0 16px;font-size:12.5px}a{color:#3fd0c4}
 .g{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
 .c{background:#121821;border:1px solid #223042;border-radius:10px;padding:13px;display:flex;flex-direction:column}
 .t{font-weight:600;color:#eaf2ff}.d{color:#9fb2c8;font-size:12px;margin:5px 0 9px;flex:1}.r{display:flex;gap:7px}
 input{flex:1;min-width:0;background:#0a0e13;border:1px solid #1b2635;border-radius:6px;color:#cde;padding:6px 7px;font:11.5px ui-monospace,monospace}
 button{background:#1b6feb;color:#fff;border:0;border-radius:6px;padding:6px 12px;cursor:pointer;font:inherit}
 button:hover{background:#2f81f7}button:disabled{background:#2a3646}
 pre{white-space:pre-wrap;background:#0a0e13;border:1px solid #1b2635;border-radius:7px;padding:9px;margin:9px 0 0;max-height:320px;overflow:auto;font-size:11.5px;color:#c8d4e2;display:none}
 .meta{color:#6f8296;font-size:11.5px;margin-top:5px}
</style></head><body>
<h1>White Box 1.0 &mdash; fable tools</h1>
<p class=s>the fable_* structure/security suite, ported in &middot; read-only ending-child runs &middot; <a href="/">&larr; back to White Box</a></p>
<div class=g>__CARDS__</div>
<script>
async function run(m){const b=event.target,o=document.getElementById('o_'+m),mt=document.getElementById('m_'+m),a=document.getElementById('a_'+m);
 b.disabled=true;b.textContent='...';mt.textContent='';
 try{const r=await fetch('/fable_run?tool='+m+'&args='+encodeURIComponent(a.value));const j=await r.json();
  o.style.display='block';o.textContent=j.out||'(no output)';mt.textContent=(j.ok?'\\u2713 ':'\\u2717 ')+(j.secs!=null?j.secs+'s':'');}
 catch(e){o.style.display='block';o.textContent='error: '+e;}
 b.disabled=false;b.textContent='Run';}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _q(self, key, default=""):
        return (self._qs.get(key) or [default])[0]

    def _route(self):
        u = urlparse(self.path); self._qs = parse_qs(u.query); p = u.path
        # STATIC pages (no model touch)
        if p == "/":
            return self._send(PAGE, "text/html; charset=utf-8")
        if p == "/dirlab":
            return self._send(DIRLAB_PAGE, "text/html; charset=utf-8")
        if p == "/models":
            fs = [os.path.basename(f) for f in sorted(glob.glob(MODELS_DIR + "/*.gguf"))]
            return self._send(json.dumps({"models": fs}))
        # SELECT a file — the server holds ONLY the path string; the index read (25 s if uncached) runs in the sandbox
        if p == "/load":
            fp = self._q("path")
            if fp and not os.path.isabs(fp):
                fp = os.path.join(MODELS_DIR, fp)
            if not fp or not os.path.exists(fp):
                return self._send(json.dumps({"error": f"file not found: {fp}"}))
            STATE.update(path=fp, anat=None, vocab=None, E_mm=None, dim=None, ety=None, err="")
            return self._send(json.dumps(_sandboxed("anatomy", fp)))
        # the decompiler self-attaches (streaming) inside each op's sandbox now — no persistent server-side build
        if p == "/embed_status":
            return self._send(json.dumps({"building": False, "ready": True, "progress": 1.0, "err": ""}))
        if p == "/embed_cancel":
            return self._send(json.dumps({"ok": True}))
        # ── ASYNC gated-sandbox JOBS (long ops) — launch the child, then poll proc.poll() and read the frozen file AFTER it ENDS ──
        if p in ("/export", "/layerscan"):
            if not STATE["path"]:
                return self._send(json.dumps({"error": "no file loaded — Import a model first"}))
            for j in JOBS.values():                              # one sandbox job at a time — never stack processes (ghost-process lesson)
                pr = j.get("proc")
                if pr is not None and pr.poll() is None:
                    return self._send(json.dumps({"error": "a job is already running — wait for it to finish"}))
            jid = str(len(JOBS) + 1)
            if p == "/export":
                kw = {"full": self._q("full", "0"), "allexp": self._q("allexp", "0"), "decompile": self._q("decompile", "0")}
                proc, res = _launch("export", STATE["path"], kw)
            else:
                proc, res = _launch("layerscan", STATE["path"], {"role": self._q("role")})
            JOBS[jid] = {"proc": proc, "result_path": res}
            return self._send(json.dumps({"job": jid}))
        if p in ("/exportpoll", "/scanpoll"):
            jb = JOBS.get(self._q("job"))
            if not jb:
                return self._send(json.dumps({"done": True, "result": {"error": "no job"}}))
            proc = jb["proc"]
            if proc.poll() is None:                              # still running IN THE SANDBOX — do not touch it, do not measure it
                return self._send(json.dumps({"done": False, "result": None}))
            return self._send(json.dumps({"done": True, "result": _read_frozen(jb["result_path"], proc)}))
        # ── RESEARCHER ARCHIVE: select a model (dropdown), dump its weights + all White Box data into a folder ──
        if p == "/archive":
            model = self._q("model") or (os.path.basename(STATE["path"]) if STATE["path"] else "")
            fp = model if os.path.isabs(model) else os.path.join(MODELS_DIR, model)
            if not fp or not os.path.exists(fp):
                return self._send(json.dumps({"error": f"model not found: {fp}"}))
            for j in JOBS.values():                              # one sandbox job at a time (no stacked processes)
                pr = j.get("proc")
                if pr is not None and pr.poll() is None:
                    return self._send(json.dumps({"error": "a job is already running — wait for it to finish"}))
            jid = str(len(JOBS) + 1)
            kw = {"full": self._q("full", "0"), "allexp": self._q("allexp", "0"), "decompile": self._q("decompile", "0")}
            proc, res = _launch("archive", fp, kw)
            JOBS[jid] = {"proc": proc, "result_path": res}
            return self._send(json.dumps({"job": jid}))
        if p == "/archivepoll":
            jb = JOBS.get(self._q("job"))
            if not jb:
                return self._send(json.dumps({"done": True, "result": {"error": "no job"}}))
            proc = jb["proc"]
            if proc.poll() is None:                              # still running IN THE SANDBOX — do not touch it
                return self._send(json.dumps({"done": False, "result": None}))
            return self._send(json.dumps({"done": True, "result": _read_frozen(jb["result_path"], proc)}))
        # ── every other model op: BLOCKING gated sandbox (launch → wait for the child to END → read the STATIC frozen result) ──
        if p in _SANDBOX_ROUTES:
            op = _SANDBOX_ROUTES[p]
            if not STATE["path"] and op != "create":
                return self._send(json.dumps({"error": "no file — Import a model first"}))
            kw = {k: (v[0] if v else "") for k, v in self._qs.items()}
            return self._send(json.dumps(_sandboxed(op, STATE["path"], kw)))
        # ── FABLE TOOLS (additive; isolated from every route above) ──
        if p == "/fable":
            cards = "".join(
                f'<div class=c><div class=t>{ti}</div><div class=d>{de}</div>'
                f'<div class=r><input id="a_{m}" value="{ar}"><button onclick="run(\'{m}\')">Run</button></div>'
                f'<span class=meta id="m_{m}"></span><pre id="o_{m}"></pre></div>'
                for (m, ti, de, ar) in _FABLE_TOOLS)
            return self._send(_FABLE_PAGE.replace("__CARDS__", cards), "text/html; charset=utf-8")
        if p == "/fable_run":
            return self._send(json.dumps(_fable_run(self._q("tool"), self._q("args"))))
        if p == "/atlas":                                         # additive: serve the Titan Silicon Atlas (pre-built)
            ap = os.path.join(os.path.dirname(os.path.abspath(__file__)), "titan-silicon-atlas.html")
            if os.path.exists(ap):
                return self._send(open(ap, encoding="utf-8").read(), "text/html; charset=utf-8")
            return self._send("atlas not built — run: python host/pfc_atlas.py && python host/pfc_atlas_verify.py",
                              "text/plain; charset=utf-8")
        return self._send(json.dumps({"error": "not found"}))

    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()


if __name__ == "__main__":
    import socket, webbrowser
    # SINGLE-INSTANCE GUARD: if a White Box is already serving on the port, don't spawn a duplicate process — just open
    # the existing one in the browser and exit. (Prevents the "ghost processes" from re-launching the app.)
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.4)
    already = probe.connect_ex(("127.0.0.1", PORT)) == 0
    probe.close()
    if already:
        print(f"White Box already running on http://127.0.0.1:{PORT} — opening it, not starting a second copy.")
        try: webbrowser.open(f"http://127.0.0.1:{PORT}")
        except Exception: pass
        sys.exit(0)
    print(f"White Box on http://127.0.0.1:{PORT}  (import a .gguf, see + edit the bits)")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.allow_reuse_address = False                              # a second copy fails to bind rather than co-binding
    srv.serve_forever()
