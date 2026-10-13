#!/usr/bin/env python3
"""host/wbedit.py — THE WHITE BOX EDIT ENGINE: search, destroy, and edit the BITS of any .gguf, reversibly.

The White Box is a research instrument (docs/SDC.md — the read/write directions on the weights themselves). This module
is its WRITE side: everything the owner might want to SEE (all KV metadata, every tensor, every token, dequantized
values) and EDIT (zero/prune/scale a tensor, prune an expert, edit or scrub a token's embedding row), each edit
REVERSIBLE by a byte-exact genome (the proven bake_titan.py pattern, generalized).

Design (owner: "search and destroy certain stuff so I can target my own pruning" + "show anything someone might want to
see and edit"):
  - SEARCH  : name/substring/regex over tensors, KVs, and the tokenizer vocab -> the target list.
  - DESTROY : reversible pruning. Zero a whole tensor (all-zero bits decode to ~0 for F32/Q4_0/Q6_K/Q4_K -> a clean
              ablation), or zero one EXPERT slice of an MoE tensor (expert axis is byte-axis 0, contiguous -> a byte
              slice, no requant), or scrub/zero a token's embedding row.
  - EDIT    : scale a tensor (dequant*factor -> requant to the SAME bytes, in place), or bit-edit a token embedding row
              toward another token (a bit-edit IS a meaning-edit, decompile.py's read-direction made writable).
  - GENOME  : every write backs up the exact original bytes of the touched region FIRST, to <model>.wbgenome/. Revert
              replays in reverse -> byte-exact original. No whole-model copy; a slice edit backs up only that slice.

Safety: do NOT run this while a llama-server has the same file mmap'd (Windows share/lock + stale mmap). The White Box
never serves, so within the app it is safe; the app refuses an edit if it sees a live server on the model.
"""
import base64, json, os, re, struct, time
import numpy as np
import gguf


# ------------------------------------------------------------------ reading (see everything)

def _reader(path):
    return gguf.GGUFReader(path)


def _kv_value(field):
    """best-effort human value + a type tag for any gguf KV field."""
    try:
        parts, data, types = field.parts, field.data, field.types
        if not types:
            return None, "?"
        t = types[0]
        GG = gguf.GGUFValueType
        if t == GG.STRING:
            return bytes(parts[data[-1]]).decode("utf-8", "replace"), "str"
        if t == GG.ARRAY:
            sub = types[1] if len(types) > 1 else None
            n = len(data)
            if sub == GG.STRING:
                sample = [bytes(parts[data[i]]).decode("utf-8", "replace") for i in range(min(n, 6))]
                return {"n": n, "sample": sample}, "arr[str]"
            vals = [parts[d][0] if hasattr(parts[d], "__len__") else parts[d] for d in data[:6]]
            return {"n": n, "sample": [float(v) if isinstance(v, (np.floating,)) else int(v) for v in vals]}, "arr[num]"
        v = parts[data[-1]]
        v = v[0] if hasattr(v, "__len__") else v
        if isinstance(v, (np.floating, float)):
            return round(float(v), 6), "num"
        return int(v), "num"
    except Exception as e:
        return f"<{type(e).__name__}>", "?"


def list_kv(path):
    r = _reader(path)
    out = []
    for f in r.fields.values():
        v, ty = _kv_value(f)
        out.append({"key": f.name, "type": ty, "value": v})
    out.sort(key=lambda x: x["key"])
    return out


def _tensor_row(t):
    return {"name": t.name, "type": t.tensor_type.name,
            "shape": [int(x) for x in t.shape], "params": int(np.prod([int(x) for x in t.shape])),
            "bytes": int(t.n_bytes), "offset": int(t.data_offset)}


def list_tensors(path):
    return [_tensor_row(t) for t in _reader(path).tensors]


def _match(name, q, use_regex):
    if not q:
        return True
    if use_regex:
        try:
            return re.search(q, name, re.I) is not None
        except re.error:
            return q.lower() in name.lower()
    return q.lower() in name.lower()


def search_tensors(path, q, use_regex=False, limit=400):
    out = [_tensor_row(t) for t in _reader(path).tensors if _match(t.name, q, use_regex)]
    out.sort(key=lambda x: -x["params"])
    return out[:limit]


def search_tokens(path, q, use_regex=False, limit=200):
    r = _reader(path)
    kv = {f.name: f for f in r.fields.values()}
    toks = kv.get("tokenizer.ggml.tokens")
    if not toks:
        return []
    out = []
    for i in toks.data:
        s = bytes(toks.parts[i]).decode("utf-8", "replace")
        if _match(s, q, use_regex):
            out.append({"id": int(i), "tok": s.replace("▁", "·")})
            if len(out) >= limit:
                break
    return out


def dequant_tensor(path, name):
    r = _reader(path)
    t = next((x for x in r.tensors if x.name == name), None)
    if t is None:
        return None, None
    try:
        arr = gguf.quants.dequantize(t.data, t.tensor_type).astype(np.float32)
    except Exception:
        arr = None
    return t, arr


# ------------------------------------------------------------------ the genome (reversible)

def _genome_dir(path):
    d = path + ".wbgenome"
    os.makedirs(d, exist_ok=True)
    return d


def _genome_index(path):
    idx = os.path.join(_genome_dir(path), "index.json")
    if os.path.exists(idx):
        try:
            return json.load(open(idx, encoding="utf-8"))
        except Exception:
            return []
    return []


def _genome_save(path, edits):
    json.dump(edits, open(os.path.join(_genome_dir(path), "index.json"), "w", encoding="utf-8"), indent=1)


def _backup(path, off, length, op, note):
    """read the exact bytes at [off, off+length) and stash them; return the edit record (not yet applied)."""
    with open(path, "rb") as f:
        f.seek(off)
        orig = f.read(length)
    edits = _genome_index(path)
    seq = len(edits)
    binp = os.path.join(_genome_dir(path), f"{seq:04d}.bin")
    with open(binp, "wb") as g:
        g.write(orig)
    rec = {"seq": seq, "off": int(off), "len": int(length), "op": op, "note": note,
           "bin": os.path.basename(binp), "t": int(time.time())}
    edits.append(rec)
    _genome_save(path, edits)
    return rec


def genome_log(path):
    return _genome_index(path)


def revert(path, n=None):
    """replay the genome in REVERSE. n=None -> revert everything; n=k -> revert the last k edits."""
    edits = _genome_index(path)
    if not edits:
        return {"reverted": 0, "note": "no genome; file is original"}
    take = edits if n is None else edits[-int(n):]
    done = 0
    with open(path, "r+b") as f:
        for rec in reversed(take):
            if "truncate" in rec:                      # an ADD-tensor append: revert = truncate back to pre-size
                f.truncate(int(rec["truncate"]))
                done += 1
                continue
            binp = os.path.join(_genome_dir(path), rec.get("bin", ""))
            if not rec.get("bin") or not os.path.exists(binp):
                continue
            f.seek(rec["off"])
            f.write(open(binp, "rb").read())
            done += 1
    remaining = edits[:-int(n)] if (n is not None and int(n) < len(edits)) else []
    if remaining:
        _genome_save(path, remaining)
    else:
        # wipe the genome dir entirely (fully original)
        d = _genome_dir(path)
        for fn in os.listdir(d):
            try:
                os.remove(os.path.join(d, fn))
            except Exception:
                pass
        try:
            os.rmdir(d)
        except Exception:
            pass
    return {"reverted": done, "remaining": len(remaining)}


# ------------------------------------------------------------------ destroy (reversible pruning)

def destroy_tensor(path, name):
    """zero a whole tensor's bytes. All-zero bits decode to ~0 (F32/Q4_0/Q4_K/Q6_K) -> a clean, reversible ablation."""
    t = next((x for x in _reader(path).tensors if x.name == name), None)
    if t is None:
        return {"error": "tensor not found"}
    off, length = int(t.data_offset), int(t.n_bytes)
    rec = _backup(path, off, length, "destroy_tensor", name)
    with open(path, "r+b") as f:
        f.seek(off)
        # chunked zero write (a big tensor can be GBs)
        z = b"\x00" * (1 << 20)
        left = length
        while left > 0:
            f.write(z if left >= len(z) else b"\x00" * left)
            left -= len(z)
    return {"ok": True, "name": name, "bytes": length, "seq": rec["seq"],
            "note": f"zeroed {name} ({length/1e6:.1f} MB); reversible (genome seq {rec['seq']})"}


def destroy_expert(path, name, idx):
    """zero ONE expert's slice of an MoE expert tensor. Expert axis is byte-axis 0 (contiguous) -> a pure byte slice."""
    r = _reader(path)
    t = next((x for x in r.tensors if x.name == name), None)
    if t is None:
        return {"error": "tensor not found"}
    kv = {f.name: f for f in r.fields.values()}
    arch = None
    a = kv.get("general.architecture")
    if a:
        arch = bytes(a.parts[a.data[-1]]).decode("utf-8", "replace")
    ne_f = kv.get(f"{arch}.expert_count") if arch else None
    n_exp = int(ne_f.parts[ne_f.data[-1]][0]) if ne_f else int(t.shape[-1])
    if int(t.n_bytes) % n_exp != 0:
        return {"error": f"tensor bytes {t.n_bytes} not divisible by expert_count {n_exp}; not an expert-major tensor"}
    stride = int(t.n_bytes) // n_exp
    idx = int(idx)
    if not (0 <= idx < n_exp):
        return {"error": f"expert idx {idx} out of range 0..{n_exp-1}"}
    off = int(t.data_offset) + idx * stride
    rec = _backup(path, off, stride, "destroy_expert", f"{name}#e{idx}")
    with open(path, "r+b") as f:
        f.seek(off)
        z = b"\x00" * (1 << 20)
        left = stride
        while left > 0:
            f.write(z if left >= len(z) else b"\x00" * left)
            left -= len(z)
    return {"ok": True, "name": name, "expert": idx, "of": n_exp, "bytes": stride, "seq": rec["seq"],
            "note": f"pruned expert {idx}/{n_exp} of {name}; reversible (genome seq {rec['seq']})"}


def scale_tensor(path, name, factor):
    """multiply a tensor by a scalar in place (dequant -> *factor -> requant to the SAME bytes). Reversible."""
    r = _reader(path)
    t = next((x for x in r.tensors if x.name == name), None)
    if t is None:
        return {"error": "tensor not found"}
    off, length = int(t.data_offset), int(t.n_bytes)
    with open(path, "rb") as f:
        f.seek(off)
        orig = f.read(length)
    try:
        arr = gguf.quants.dequantize(np.frombuffer(orig, dtype=t.data.dtype).reshape(t.data.shape),
                                     t.tensor_type).astype(np.float32) * float(factor)
        qb = gguf.quants.quantize(arr, t.tensor_type).tobytes()
    except Exception as e:
        return {"error": f"scale needs a (de)quantizable type; {t.tensor_type.name}: {type(e).__name__}"}
    if len(qb) != length:
        return {"error": f"requant size {len(qb)} != {length}"}
    rec = _backup(path, off, length, "scale_tensor", f"{name}*{factor}")
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(qb)
    return {"ok": True, "name": name, "factor": float(factor), "seq": rec["seq"],
            "note": f"scaled {name} by {factor}; reversible (genome seq {rec['seq']})"}


# ------------------------------------------------------------------ DEVOUR: absorb any params via reversible weight edit

def write_tensor_values(path, name, new_arr, op="write", note=""):
    """The general WEIGHT-MODIFICATION primitive (owner: 'all features via weight modification using white box'): write a
    full new float array into a tensor in place — requant new_arr to the tensor's native type + SAME byte length, genome-
    backed (byte-exact reversible). Every devour/create edit lands through here, so nothing touches the model except a
    reversible White-Box write."""
    t = next((x for x in _reader(path).tensors if x.name == name), None)
    if t is None:
        return {"error": "tensor not found"}
    off, length = int(t.data_offset), int(t.n_bytes)
    try:
        qb = gguf.quants.quantize(np.ascontiguousarray(new_arr, np.float32), t.tensor_type).tobytes()
    except Exception as e:
        return {"error": f"requant ({t.tensor_type.name}) failed: {type(e).__name__} — {e}"}
    if len(qb) != length:
        return {"error": f"requant size {len(qb)} != original {length}"}
    rec = _backup(path, off, length, op, note or name)
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(qb)
    return {"ok": True, "name": name, "type": t.tensor_type.name, "bytes": length, "seq": rec["seq"],
            "note": f"{op} {name} ({length/1e6:.1f} MB); reversible (genome seq {rec['seq']})"}


def bake_operator_direction(path, name, direction, alpha=1.0, axis="in"):
    """★ BAKE AN OPERATIONAL STATE INTO THE MODEL via a DIRECTIONAL VECTOR (owner 2026-07-23: "bake desirable operational
    states into the models through directional vectors in the white box" — model modification as a LEVER). An operator is a
    residual-space DIRECTION (from activation-difference capture, `scope.py`/`decompile.py`, CALIBRATION_FINDINGS #13); this
    FOLDS it into a projection tensor's weights so the operational state is ALWAYS-ON, 0-token — the operator lives in W, not
    the context window. Reversible (genome, byte-exact) via `write_tensor_values`. This makes the White Box's visibility
    (read side) actionable (write side): SEE the direction, BAKE it, MEASURE, keep-or-revert.

      axis="in"  : direction has length n_in; add alpha*direction to EVERY output row -> every neuron's projection is
                   steered by the operator (output gains alpha*<direction, x>). The standard steer-into-weights.
      axis="out" : direction has length n_out; scale/shift per output neuron (gate-mask style, INV-141).
    """
    t = next((x for x in _reader(path).tensors if x.name == name), None)
    if t is None:
        return {"error": "tensor not found"}
    try:
        arr = gguf.quants.dequantize(t.data, t.tensor_type).astype(np.float32)   # [n_out, n_in] (row j = neuron j)
    except Exception as e:
        return {"error": f"needs a dequantizable type; {t.tensor_type.name}: {type(e).__name__}"}
    d = np.asarray(direction, np.float32) * float(alpha)
    if axis == "in":
        if d.shape[0] != arr.shape[-1]:
            return {"error": f"direction len {d.shape[0]} != n_in {arr.shape[-1]}"}
        arr = arr + d[None, :]                                                    # steer every neuron's projection
    elif axis == "out":
        if d.shape[0] != arr.shape[0]:
            return {"error": f"direction len {d.shape[0]} != n_out {arr.shape[0]}"}
        arr = arr + d[:, None]                                                    # per-neuron shift (gate-mask style)
    else:
        return {"error": "axis must be 'in' or 'out'"}
    return write_tensor_values(path, name, arr, op="bake_operator",
                               note=f"{name} += {alpha}*direction[{axis}] (operational state baked, 0-token, reversible)")


def operator_direction_from_activations(act_on, act_off):
    """Compute the operator DIRECTION as the mean activation-difference (the keystone, CALIBRATION #13): d = mean(on) -
    mean(off), where act_on/act_off are lists of residual vectors captured WITH vs WITHOUT the operator σ in context. Bake
    this d with bake_operator_direction() to install the operator structurally. (Capture via scope.py / a σ-on/σ-off run.)"""
    on = np.asarray(act_on, np.float32); off = np.asarray(act_off, np.float32)
    d = on.mean(0) - off.mean(0)
    n = float(np.linalg.norm(d)) or 1.0
    return (d / n).tolist()                                                       # unit direction; scale with alpha at bake


TITAN_ADD_MAGIC = b"TITANADD"


def _backup_truncate(path, pre_size, op, note):
    """genome record whose revert is a TRUNCATE back to pre_size (for append-additions, there are no original bytes)."""
    edits = _genome_index(path)
    seq = len(edits)
    rec = {"seq": seq, "op": op, "note": note, "truncate": int(pre_size), "t": int(time.time())}
    edits.append(rec)
    _genome_save(path, edits)
    return rec


def add_tensor(path, name, arr=None, src_path=None, src_name=None):
    """THE ADD HOOK (owner: 'an edit can be an ADDITION, not a replacement'). Structurally ADD a component to the file by
    APPENDING it — no read-all/write-all rewrite of the existing data (the INV-110 structural bake: a named section read at
    load). The addition is a trailer record [MAGIC][u32 hdrlen][json{name,mode,type,shape,src?}][data?] appended at EOF; a
    stock gguf reader ignores trailing bytes, the Titan reader (titan_added) parses them. Two modes:
      - CONTAIN: pass `arr` (a float array) -> its F32 bytes are appended (self-contained component).
      - REFERENCE: pass `src_path`(+`src_name`) -> only a pointer (file+tensor) is recorded, ZERO data copied (move-not-
        copy; ~0 bytes, no throttle) — the Titan runtime reads the bytes from the source at use.
    Reversible: the genome records the pre-append size; revert truncates back (byte-exact original file)."""
    if not os.path.exists(path):
        return {"error": f"file not found: {path}"}
    pre = os.path.getsize(path)
    if src_path is not None:                                   # REFERENCE add — no data copied
        sname = src_name or name
        s = next((x for x in _reader(src_path).tensors if x.name == sname), None)
        if s is None:
            return {"error": f"source tensor {sname} not in {os.path.basename(src_path)}"}
        hdr = {"name": name, "mode": "ref", "type": s.tensor_type.name,
               "shape": [int(x) for x in s.shape], "src": os.path.abspath(src_path), "src_name": sname,
               "src_off": int(s.data_offset), "src_bytes": int(s.n_bytes)}
        data = b""
    else:                                                     # CONTAIN add — append F32 bytes
        a = np.ascontiguousarray(arr, np.float32)
        hdr = {"name": name, "mode": "f32", "type": "F32", "shape": list(a.shape)}
        data = a.tobytes()
    hb = json.dumps(hdr).encode("utf-8")
    rec = TITAN_ADD_MAGIC + struct.pack("<I", len(hb)) + hb + data
    with open(path, "ab") as f:
        f.write(rec)
    g = _backup_truncate(path, pre, "add_tensor", f"+{name} ({hdr['mode']})")
    return {"ok": True, "name": name, "mode": hdr["mode"], "added_bytes": len(rec), "seq": g["seq"],
            "note": f"ADDED {name} ({hdr['mode']}, {len(rec)/1e6:.3f} MB appended); reversible by truncation (seq {g['seq']})"}


def titan_added(path):
    """read the appended TITANADD trailer records (the components ADDED beyond the stock gguf). Returns their headers +
    file offsets so the Titan runtime / White Box can address them."""
    out = []
    with open(path, "rb") as f:
        # find the stock gguf data end: everything up to the first TITANADD magic (scan from a reasonable point is O(file);
        # instead we record adds sequentially, so scan for the magic — cheap because adds cluster at EOF)
        f.seek(0)
        blob = None
        # locate the first magic without loading the whole file: read the tail in chunks growing from EOF is complex;
        # for correctness scan forward via mmap-like find on the raw bytes is O(file). Keep it simple + bounded: the
        # trailer sits after the stock data, so we memory-map and find. (Small files here; big Titan uses the index below.)
        import mmap
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        pos = mm.find(TITAN_ADD_MAGIC)
        while pos != -1:
            p = pos + len(TITAN_ADD_MAGIC)
            (hlen,) = struct.unpack_from("<I", mm, p); p += 4
            hdr = json.loads(mm[p:p + hlen].decode("utf-8")); p += hlen
            dbytes = 0 if hdr.get("mode") == "ref" else int(np.prod(hdr["shape"])) * 4
            hdr["_data_off"] = p
            hdr["_data_bytes"] = dbytes
            out.append(hdr)
            pos = mm.find(TITAN_ADD_MAGIC, p + dbytes)
        mm.close()
    return out


def paste_tensor(path, dst_name, src_path, src_name=None):
    """THE PASTE HOOK (owner: 'copy..... paste.....'; 'build the hook for weights'). Move a SOURCE model's component
    tensor into THIS file's tensor, reversibly. If both are the SAME type+shape+bytes it is a BYTE-EXACT move — the bits,
    copied, no requant, no loss (the toy-bear/edit-a-running-app-through-a-text-field hook applied to weights). If the
    shape matches but the type differs, it requants. Genome-backed => byte-exact reversible. This is the cross-file
    copy/paste the White Box was missing (cut=destroy, edit=scale/blend, PASTE=this)."""
    src_name = src_name or dst_name
    t = next((x for x in _reader(path).tensors if x.name == dst_name), None)
    s = next((x for x in _reader(src_path).tensors if x.name == src_name), None)
    if t is None or s is None:
        return {"error": f"tensor missing (dst {dst_name}: {t is not None}, src {src_name}: {s is not None})"}
    if [int(x) for x in t.shape] != [int(x) for x in s.shape]:
        return {"error": f"shape mismatch dst{list(map(int,t.shape))} vs src{list(map(int,s.shape))} — need same dims"}
    off, length = int(t.data_offset), int(t.n_bytes)
    # BYTE-EXACT path: identical quant type + byte length => copy the raw bits (a true move, lossless)
    if t.tensor_type == s.tensor_type and int(s.n_bytes) == length:
        with open(src_path, "rb") as f:
            f.seek(int(s.data_offset)); raw = f.read(length)
        rec = _backup(path, off, length, "paste", f"{dst_name} <- {os.path.basename(src_path)}:{src_name}")
        with open(path, "r+b") as f:
            f.seek(off); f.write(raw)
        return {"ok": True, "name": dst_name, "bytes": length, "exact": True, "seq": rec["seq"],
                "note": f"pasted {os.path.basename(src_path)}:{src_name} into {dst_name} BYTE-EXACT "
                        f"({length/1e6:.1f} MB, no requant); reversible (seq {rec['seq']})"}
    # requant path: same shape, different quant type
    try:
        sg = gguf.quants.dequantize(s.data, s.tensor_type).astype(np.float32)
    except Exception as e:
        return {"error": f"src dequant failed ({s.tensor_type.name}): {type(e).__name__}"}
    res = write_tensor_values(path, dst_name, sg, op="paste", note=f"{dst_name} <- {os.path.basename(src_path)}:{src_name}")
    if "ok" in res:
        res["exact"] = False
        res["note"] = (f"pasted {os.path.basename(src_path)}:{src_name} into {dst_name} (requant "
                       f"{s.tensor_type.name}->{t.tensor_type.name}); reversible (seq {res['seq']})")
    return res


def blend_tensor(path, name, src_path, src_name=None, amount=0.5):
    """DEVOUR a model's parameter: blend THIS file's tensor toward a SOURCE model's same-shape tensor
    (target ← (1−a)·target + a·source), requant in place, reversibly — the White-Box weight-modification form of 'eat a
    model' (Titan absorbs the source's params). Requires matching shape (the structural law: same dims). No copy of the
    model; only the touched tensor's bytes are genome-backed."""
    src_name = src_name or name
    t = next((x for x in _reader(path).tensors if x.name == name), None)
    s = next((x for x in _reader(src_path).tensors if x.name == src_name), None)
    if t is None or s is None:
        return {"error": f"tensor missing (target {name}: {t is not None}, source {src_name}: {s is not None})"}
    if [int(x) for x in t.shape] != [int(x) for x in s.shape]:
        return {"error": f"shape mismatch {list(map(int, t.shape))} vs {list(map(int, s.shape))} — incompatible (need same dims)"}
    try:
        tg = gguf.quants.dequantize(t.data, t.tensor_type).astype(np.float32)
        sg = gguf.quants.dequantize(s.data, s.tensor_type).astype(np.float32)
    except Exception as e:
        return {"error": f"dequant failed: {type(e).__name__}"}
    a = float(amount)
    new = (1.0 - a) * tg + a * sg
    res = write_tensor_values(path, name, new, op="blend", note=f"{name} <- {int(a*100)}% {os.path.basename(src_path)}")
    if "ok" in res:
        res["note"] = f"blended {int(a*100)}% of {os.path.basename(src_path)}:{src_name} into {name}; reversible (seq {res['seq']})"
    return res


# ------------------------------------------------------------------ token embedding edit (write the decompiler)

def _embed_tensor(r):
    return next((t for t in r.tensors if t.name in ("token_embd.weight", "tok_embeddings.weight")), None)


def _find_tok(vocab, word):
    for cand in (word, "▁" + word, " " + word, word.capitalize(), "▁" + word.capitalize()):
        if cand in vocab:
            return vocab.index(cand)
    for i, tk in enumerate(vocab):
        if tk.strip("▁ ") == word:
            return i
    return None


def _vocab(r):
    kv = {f.name: f for f in r.fields.values()}
    toks = kv.get("tokenizer.ggml.tokens")
    return [bytes(toks.parts[i]).decode("utf-8", "replace") for i in toks.data] if toks else []


def edit_token(path, word, toward=None, amount=0.6, zero=False):
    """edit ONE token's embedding row in place: nudge toward another token (bit-edit=meaning-edit) or zero (scrub).
    Only that row's bytes are dequant/requant'd + backed up -> cheap + reversible."""
    r = _reader(path)
    te = _embed_tensor(r)
    if te is None:
        return {"error": "no token_embd tensor"}
    vocab = _vocab(r)
    i = _find_tok(vocab, word)
    if i is None:
        return {"error": f"'{word}' is not a single token"}
    n_vocab = int(te.shape[-1]) if len(te.shape) > 1 else len(vocab)
    if int(te.n_bytes) % n_vocab != 0:
        return {"error": "embedding not row-contiguous; cannot edit a single row safely"}
    row_bytes = int(te.n_bytes) // n_vocab
    off = int(te.data_offset) + i * row_bytes
    with open(path, "rb") as f:
        f.seek(off)
        orig = f.read(row_bytes)
    dt = te.data.dtype
    per_row_blocks = np.frombuffer(orig, dtype=dt)
    try:
        row = gguf.quants.dequantize(per_row_blocks.reshape((1,) + per_row_blocks.shape), te.tensor_type).astype(np.float32).ravel()
    except Exception as e:
        return {"error": f"row dequant failed ({te.tensor_type.name}): {type(e).__name__}"}
    if zero:
        new = np.zeros_like(row)
        note = f"scrubbed '{word}' embedding to zero"
    else:
        j = _find_tok(vocab, toward) if toward else None
        if j is None:
            return {"error": f"toward '{toward}' is not a single token"}
        with open(path, "rb") as f:
            f.seek(int(te.data_offset) + j * row_bytes)
            jb = np.frombuffer(f.read(row_bytes), dtype=dt)
        jrow = gguf.quants.dequantize(jb.reshape((1,) + jb.shape), te.tensor_type).astype(np.float32).ravel()
        a = float(amount)
        new = (1 - a) * row + a * jrow
        note = f"nudged '{word}' {int(a*100)}% toward '{toward}' (bit-edit = meaning-edit)"
    try:
        qb = gguf.quants.quantize(new.reshape(1, -1), te.tensor_type).tobytes()
    except Exception as e:
        return {"error": f"row requant failed: {type(e).__name__}"}
    if len(qb) != row_bytes:
        return {"error": f"row requant size {len(qb)} != {row_bytes}"}
    rec = _backup(path, off, row_bytes, "edit_token", f"{word}->{toward if not zero else '0'}")
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(qb)
    # re-dequant what we actually stored (quantization is lossy) so the decompiler cache reflects the true bits
    stored = gguf.quants.dequantize(np.frombuffer(qb, dtype=dt).reshape((1,) + per_row_blocks.shape),
                                    te.tensor_type).astype(np.float32).ravel()
    return {"ok": True, "token": word, "id": i, "seq": rec["seq"], "vec": stored.tolist(),
            "note": note + f" (reversible, seq {rec['seq']})"}


def edit_token_delta(path, word, d_unit, strength):
    """TARGETED ALIGNMENT write: move a token's embedding row ALONG a direction d (row += strength*||row||*d_unit), in
    place, reversibly. d is an alignment axis computed with SIGHT (from contrasting concept tokens) — so realignment is
    targeted, not a blind gradient. Returns the stored (requantized) row for the decompiler cache."""
    r = _reader(path)
    te = _embed_tensor(r)
    if te is None:
        return {"error": "no token_embd tensor"}
    vocab = _vocab(r)
    i = _find_tok(vocab, word)
    if i is None:
        return {"error": f"'{word}' is not a single token"}
    n_vocab = int(te.shape[-1]) if len(te.shape) > 1 else len(vocab)
    if int(te.n_bytes) % n_vocab != 0:
        return {"error": "embedding not row-contiguous; cannot edit a single row safely"}
    row_bytes = int(te.n_bytes) // n_vocab
    off = int(te.data_offset) + i * row_bytes
    with open(path, "rb") as f:
        f.seek(off)
        orig = f.read(row_bytes)
    dt = te.data.dtype
    blocks = np.frombuffer(orig, dtype=dt)
    try:
        row = gguf.quants.dequantize(blocks.reshape((1,) + blocks.shape), te.tensor_type).astype(np.float32).ravel()
    except Exception as e:
        return {"error": f"row dequant failed ({te.tensor_type.name}): {type(e).__name__}"}
    d = np.asarray(d_unit, np.float32)
    d = d / (np.linalg.norm(d) + 1e-8)
    new = row + float(strength) * float(np.linalg.norm(row)) * d
    try:
        qb = gguf.quants.quantize(new.reshape(1, -1), te.tensor_type).tobytes()
    except Exception as e:
        return {"error": f"row requant failed: {type(e).__name__}"}
    if len(qb) != row_bytes:
        return {"error": f"row requant size {len(qb)} != {row_bytes}"}
    rec = _backup(path, off, row_bytes, "align_token", f"{word}@{strength:+.2f}")
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(qb)
    stored = gguf.quants.dequantize(np.frombuffer(qb, dtype=dt).reshape((1,) + blocks.shape),
                                    te.tensor_type).astype(np.float32).ravel()
    return {"ok": True, "token": word, "id": i, "seq": rec["seq"], "vec": stored.tolist(),
            "note": f"realigned '{word}' by {strength:+.2f} along the axis (targeted, sighted, reversible seq {rec['seq']})"}


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
    print("KV:", len(list_kv(p)), "| tensors:", len(list_tensors(p)))
    print("search 'ffn_down':", len(search_tensors(p, "ffn_down")))
    print("genome:", genome_log(p))
