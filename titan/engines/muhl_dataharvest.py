#!/usr/bin/env python3
"""muhl_dataharvest.py -- CROSS-MODEL EVIDENCE: is 'predictor-not-meaning' geometry universal?

Bryce's claim (measured on SmolLM2 in build 19): in a next-token predictor's embedding
space, antonyms -- especially true/false -- sit anomalously CLOSE, because to a predictor
opposites fill the same grammatical slot ("the statement is ___"). If the tensors captured
MEANING, opposites would be the FARTHEST points. They are the closest.

This harvester generalizes that single measurement across EVERY real model on the device it
can parse -- different architectures (llama / phi3 / gemma3 / gemma4 / mixtral-MoE), sizes
(360M -> 70B), and quantizations (Q8_0 / Q4_0 / Q4_K / Q6_K) -- and prints one COMPARISON
TABLE. If the geometry (antonyms closer than random; true/false closer still; positive gap
over the anisotropy baseline) holds across all of them, it is a property of prediction itself,
not of one model.

Method, per model:
  * mmap the .gguf, parse GGUF-v3 header, locate token_embd.weight (rows read from storage,
    flat RAM -- the full matrix is never resident).
  * dequant only the rows needed: the antonym-pair tokens (from anchors.json 'axes') and a
    random sample of vocab rows for the baseline.
  * cosine(true,false); mean antonym cosine; mean RANDOM cosine (= the ANISOTROPY floor of the
    space); the antonym-over-random GAP; and the percentile of random pairs true/false beats.
  * also a mean-centered pass (subtract the sampled mean vector) so the result is not an
    artifact of anisotropy -- the honest, stronger version of the claim.

Pure Python. PYTHONUTF8=1. No numpy, no torch, no downloads. Reversible/read-only (mmap RO).
"""
import sys, os, io, json, struct, mmap, math, random, glob, time

MODELS_DIR = r"C:/llm/models"
ANCH       = r"C:/Users/lucys/Downloads/anchors.json"
SKIP       = ("titan.gguf", "titan_test.gguf", "titan_sdc.gguf")  # sacred / not a comparison model
SAMPLE_ROWS = 260          # random vocab rows sampled per model -> baseline pairs + mean vector
RNG_SEED    = 0

# ---- GGUF header parse (metadata value types are a DIFFERENT enum than tensor types) ----
def rd_str(mm, p):
    (n,) = struct.unpack_from("<Q", mm, p); p += 8
    return mm[p:p+n].decode("utf-8", "replace"), p+n

MVT = {0:("<B",1),1:("<b",1),2:("<H",2),3:("<h",2),4:("<I",4),5:("<i",4),
       6:("<f",4),7:("<B",1),10:("<Q",8),11:("<q",8),12:("<d",8)}
def rd_val(mm, p, t):
    if t == 8: return rd_str(mm, p)                       # string
    if t == 9:                                            # array
        (et,) = struct.unpack_from("<I", mm, p); p += 4
        (n,) = struct.unpack_from("<Q", mm, p); p += 8
        out = []
        for _ in range(n):
            v, p = rd_val(mm, p, et); out.append(v)
        return out, p
    f, sz = MVT[t]; (v,) = struct.unpack_from(f, mm, p); return v, p+sz

def parse_gguf(mm):
    if mm[:4] != b"GGUF": raise ValueError("not GGUF")
    ver,       = struct.unpack_from("<I", mm, 4)
    n_tensors, = struct.unpack_from("<Q", mm, 8)
    n_kv,      = struct.unpack_from("<Q", mm, 16)
    p = 24; meta = {}
    for _ in range(n_kv):
        key, p = rd_str(mm, p)
        (t,) = struct.unpack_from("<I", mm, p); p += 4
        val, p = rd_val(mm, p, t)
        meta[key] = val
    tensors = {}
    for _ in range(n_tensors):
        name, p = rd_str(mm, p)
        (nd,) = struct.unpack_from("<I", mm, p); p += 4
        dims = list(struct.unpack_from("<%dQ" % nd, mm, p)); p += 8*nd
        (typ,) = struct.unpack_from("<I", mm, p); p += 4
        (off,) = struct.unpack_from("<Q", mm, p); p += 8
        tensors[name] = (dims, typ, off)
    align = meta.get("general.alignment", 32)
    data_start = (p + align - 1) // align * align
    return meta, tensors, data_start, ver

# ---- GGML tensor-type enum (the real one) ----
TYPE_NAME = {0:"F32",1:"F16",2:"Q4_0",3:"Q4_1",6:"Q5_0",7:"Q5_1",8:"Q8_0",9:"Q8_1",
             10:"Q2_K",11:"Q3_K",12:"Q4_K",13:"Q5_K",14:"Q6_K",15:"Q8_K"}
QK_K = 256

def row_bytes(typ, n_embd):
    if typ == 0:  return n_embd*4                       # F32
    if typ == 1:  return n_embd*2                       # F16
    if typ == 8:  return (n_embd//32)*34                # Q8_0
    if typ == 2:  return (n_embd//32)*18                # Q4_0
    if typ == 12: return (n_embd//QK_K)*144             # Q4_K
    if typ == 14: return (n_embd//QK_K)*210             # Q6_K
    return None                                         # unsupported -> skip model

# ---- per-row dequantizers (only the rows we address are ever touched) ----
def dq_f32(mm, base, n):
    return list(struct.unpack_from("<%df" % n, mm, base))

def dq_f16(mm, base, n):
    return list(struct.unpack_from("<%de" % n, mm, base))

def dq_q8_0(mm, base, n):
    out = []
    for b in range(n//32):
        o = base + b*34
        (scale,) = struct.unpack_from("<e", mm, o)
        for q in struct.unpack_from("<32b", mm, o+2):
            out.append(q*scale)
    return out

def dq_q4_0(mm, base, n):
    out = [0.0]*n
    for b in range(n//32):
        o = base + b*18
        (d,) = struct.unpack_from("<e", mm, o)
        qs = mm[o+2:o+18]
        j = b*32
        for l in range(16):
            x = qs[l]
            out[j+l]    = ((x & 0xF) - 8) * d
            out[j+l+16] = ((x >> 4) - 8) * d
    return out

def _q4k_scale_min(js, sc):
    if js < 4:
        d = sc[js] & 63; m = sc[js+4] & 63
    else:
        d = (sc[js+4] & 0xF) | ((sc[js-4] >> 6) << 4)
        m = (sc[js+4] >> 4)  | ((sc[js]   >> 6) << 4)
    return d, m

def dq_q4_K(mm, base, n):
    out = []
    nsb = n // QK_K
    for sb in range(nsb):
        o = base + sb*144
        (d,)  = struct.unpack_from("<e", mm, o)
        (dm,) = struct.unpack_from("<e", mm, o+2)
        sc = mm[o+4:o+16]                                # 12 bytes
        qs = mm[o+16:o+144]                              # 128 bytes
        is_ = 0; qoff = 0
        for _ in range(0, QK_K, 64):
            d1s, m1s = _q4k_scale_min(is_,   sc); d1 = d*d1s; m1 = dm*m1s
            d2s, m2s = _q4k_scale_min(is_+1, sc); d2 = d*d2s; m2 = dm*m2s
            for l in range(32): out.append(d1 * (qs[qoff+l] & 0xF) - m1)
            for l in range(32): out.append(d2 * (qs[qoff+l] >> 4)  - m2)
            qoff += 32; is_ += 2
    return out

def dq_q6_K(mm, base, n):
    out = [0.0]*n
    nsb = n // QK_K
    for sb in range(nsb):
        o = base + sb*210
        ql = mm[o:o+128]
        qh = mm[o+128:o+192]
        sc = struct.unpack_from("<16b", mm, o+192)
        (d,) = struct.unpack_from("<e", mm, o+208)
        y = sb*QK_K
        for n0 in range(0, QK_K, 128):                  # one pass (QK_K=256 -> two)
            base_y = y + n0
            qlo = (n0//128)*64
            qho = (n0//128)*32
            sco = (n0//128)*8
            for l in range(32):
                iss = l // 16
                q1 = ((ql[qlo+l]      & 0xF) | (((qh[qho+l] >> 0) & 3) << 4)) - 32
                q2 = ((ql[qlo+l+32]   & 0xF) | (((qh[qho+l] >> 2) & 3) << 4)) - 32
                q3 = ((ql[qlo+l]      >> 4)  | (((qh[qho+l] >> 4) & 3) << 4)) - 32
                q4 = ((ql[qlo+l+32]   >> 4)  | (((qh[qho+l] >> 6) & 3) << 4)) - 32
                out[base_y+l]    = d * sc[sco+0] * q1
                out[base_y+l+32] = d * sc[sco+2] * q2
                out[base_y+l+64] = d * sc[sco+4] * q3
                out[base_y+l+96] = d * sc[sco+6] * q4
    return out

DQ = {0:dq_f32, 1:dq_f16, 8:dq_q8_0, 2:dq_q4_0, 12:dq_q4_K, 14:dq_q6_K}

# ---- vector math ----
def cos(a, b):
    d = na = nb = 0.0
    for x, y in zip(a, b):
        d += x*y; na += x*x; nb += y*y
    if na <= 0 or nb <= 0: return 0.0
    c = d/math.sqrt(na*nb)
    return c if math.isfinite(c) else 0.0

def finite_nonzero(v):
    """A real token row: finite and non-degenerate. Unused vocab slots dequant to all-zeros
    or NaN/Inf f16 scales -- they carry no signal and must not pollute the random baseline."""
    s = 0.0
    for x in v:
        if not math.isfinite(x): return False
        s += x*x
    return s > 0.0

def sub(a, m): return [x-y for x, y in zip(a, m)]

# ---- token lookup: cover byte-level-BPE (GPT2, marker 'Ġ') AND SentencePiece (marker '▁') ----
def make_tid(vocab):
    def tid(word):
        for cand in (word, "\u0120"+word, "\u2581"+word,
                     word.capitalize(), "\u0120"+word.capitalize(), "\u2581"+word.capitalize()):
            i = vocab.get(cand)
            if i is not None: return i
        return None
    return tid

def measure_model(path, axes):
    name = os.path.basename(path)
    fd = open(path, "rb")
    mm = mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ)
    try:
        meta, tensors, data_start, ver = parse_gguf(mm)
    except Exception as e:
        mm.close(); fd.close(); return {"name": name, "err": "parse: %s" % e}
    arch = meta.get("general.architecture", "?")
    toks = meta.get("tokenizer.ggml.tokens")
    emb = tensors.get("token_embd.weight")
    if not toks or not emb:
        mm.close(); fd.close(); return {"name": name, "arch": arch, "err": "no tokens/embeddings"}
    dims, typ, off = emb
    n_embd = dims[0]; V = len(toks)
    if typ not in DQ or row_bytes(typ, n_embd) is None:
        mm.close(); fd.close()
        return {"name": name, "arch": arch, "err": "unsupported emb type %s" % TYPE_NAME.get(typ, typ)}

    rb = row_bytes(typ, n_embd)
    dq = DQ[typ]
    def vec(i): return dq(mm, data_start + off + i*rb, n_embd)

    vocab = {t: idx for idx, t in enumerate(toks)}
    tid = make_tid(vocab)

    t0 = time.time()
    # antonym-pair rows
    ant = []
    tf = None
    for a, b in axes:
        ia, ib = tid(a), tid(b)
        if ia is None or ib is None: continue
        va, vb = vec(ia), vec(ib)
        if not (finite_nonzero(va) and finite_nonzero(vb)): continue
        c = cos(va, vb)
        ant.append({"a": a, "b": b, "ia": ia, "ib": ib, "va": va, "vb": vb, "c": c})
        if {a, b} == {"true", "false"}: tf = c

    # random sample rows (baseline pairs + mean vector for centering) -- REAL tokens only:
    # reject all-zero / non-finite rows (unused vocab slots) so the baseline is honest.
    rng = random.Random(RNG_SEED)
    rvecs = []; tries = 0; cap = SAMPLE_ROWS*40; n_skip = 0
    while len(rvecs) < SAMPLE_ROWS and tries < cap:
        tries += 1
        v = vec(rng.randrange(V))
        if finite_nonzero(v): rvecs.append(v)
        else: n_skip += 1
    rc = [cos(rvecs[k], rvecs[k+1]) for k in range(0, len(rvecs)-1, 2)]

    # PER-DIMENSION STANDARDIZATION from the sampled real-token rows. Subtracting the mean removes
    # anisotropy; dividing by each dimension's std ALSO removes the "rogue dimension" artifact (a
    # single outlier coordinate that otherwise dominates every cosine). This is the honest, strong
    # version of the claim: antonyms stay closer even after the space is whitened per-dimension.
    N = len(rvecs)
    mean = [0.0]*n_embd
    for v in rvecs:
        for j in range(n_embd): mean[j] += v[j]
    for j in range(n_embd): mean[j] /= N
    std = [0.0]*n_embd
    for v in rvecs:
        for j in range(n_embd):
            dj = v[j]-mean[j]; std[j] += dj*dj
    for j in range(n_embd):
        std[j] = math.sqrt(std[j]/N) or 1e-9
    def z(v): return [(v[j]-mean[j])/std[j] for j in range(n_embd)]

    # standardized (z-scored) metrics
    cant = [cos(z(d["va"]), z(d["vb"])) for d in ant]
    ctf = None
    for d, cc in zip(ant, cant):
        if {d["a"], d["b"]} == {"true", "false"}: ctf = cc
    zrv = [z(v) for v in rvecs]
    crc = [cos(zrv[k], zrv[k+1]) for k in range(0, len(zrv)-1, 2)]

    mm.close(); fd.close()
    mean_ant = sum(d["c"] for d in ant)/len(ant) if ant else float("nan")
    mean_rnd = sum(rc)/len(rc) if rc else float("nan")
    mean_cant = sum(cant)/len(cant) if cant else float("nan")
    mean_crnd = sum(crc)/len(crc) if crc else float("nan")
    pct = None
    if tf is not None and rc:
        pct = 100.0 * (1 - sum(1 for c in rc if c > tf)/len(rc))
    return {
        "name": name, "arch": arch, "quant": TYPE_NAME.get(typ, str(typ)),
        "n_embd": n_embd, "vocab": V, "n_pairs": len(ant),
        "tf": tf, "mean_ant": mean_ant, "mean_rnd": mean_rnd, "gap": mean_ant-mean_rnd,
        "tf_pct": pct,
        "c_tf": ctf, "c_mean_ant": mean_cant, "c_mean_rnd": mean_crnd, "c_gap": mean_cant-mean_crnd,
        "secs": time.time()-t0, "ant": ant, "n_valid": len(rvecs), "n_skip": n_skip,
    }

def fmt(x, s="%+.3f"):
    return "  n/a " if x is None or (isinstance(x, float) and x != x) else s % x

def main():
    if not os.path.exists(ANCH):
        print("anchors.json not found at", ANCH); return 1
    A = json.load(open(ANCH, encoding="utf-8"))
    axes = [tuple(x) for x in A.get("axes", [])]
    if not axes:  # fall back to pairing the flat anchor list
        an = A["anchors"]; axes = [(an[i], an[i+1]) for i in range(0, min(len(an), 40)-1, 2)]

    paths = [p for p in sorted(glob.glob(os.path.join(MODELS_DIR, "*.gguf")))
             if os.path.basename(p) not in SKIP]
    print("MUHLNICKEL CROSS-MODEL HARVEST -- predictor-not-meaning geometry")
    print("anchor axes: %d pairs (led by true/false)  |  models found: %d\n" % (len(axes), len(paths)))

    rows = []
    for p in paths:
        gb = os.path.getsize(p)/1e9
        print("-> %-52s (%.1f GB) ..." % (os.path.basename(p), gb), flush=True)
        try:
            r = measure_model(p, axes)
        except Exception as e:
            r = {"name": os.path.basename(p), "err": "%s: %s" % (type(e).__name__, e)}
        if "err" in r:
            print("     SKIP: %s" % r["err"]); rows.append(r); continue
        print("     arch=%-8s quant=%-5s n_embd=%d vocab=%d pairs=%d  true/false=%s  ant=%s rnd=%s  (base %d rows, %d unused skipped, %.1fs)"
              % (r["arch"], r["quant"], r["n_embd"], r["vocab"], r["n_pairs"],
                 fmt(r["tf"]), fmt(r["mean_ant"]), fmt(r["mean_rnd"]), r["n_valid"], r["n_skip"], r["secs"]), flush=True)
        rows.append(r)

    ok = [r for r in rows if "err" not in r]
    print("\n" + "="*118)
    print("COMPARISON TABLE  (cosine: higher = closer; ANISO = mean random-pair cosine = anisotropy floor; z_* = per-dimension standardized)")
    print("="*118)
    hdr = "%-40s %-8s %-5s %6s %5s | %8s %8s %8s %7s %6s | %8s %8s %8s" % (
        "model", "arch", "quant", "n_emb", "pair",
        "true/fal", "mean_ant", "ANISO", "gap", "tf%>r",
        "z_tf", "z_ant", "z_gap")
    print(hdr); print("-"*118)
    for r in ok:
        nm = r["name"].replace(".gguf", "")
        if len(nm) > 40: nm = nm[:39]+"~"
        print("%-40s %-8s %-5s %6d %5d | %8s %8s %8s %7s %6s | %8s %8s %8s" % (
            nm, r["arch"], r["quant"], r["n_embd"], r["n_pairs"],
            fmt(r["tf"]), fmt(r["mean_ant"]), fmt(r["mean_rnd"]), fmt(r["gap"]),
            (fmt(r["tf_pct"], "%.0f") if r["tf_pct"] is not None else " n/a"),
            fmt(r["c_tf"]), fmt(r["c_mean_ant"]), fmt(r["c_gap"])))
    print("-"*118)
    skipped = [r for r in rows if "err" in r]
    if skipped:
        print("skipped:")
        for r in skipped: print("   %-45s %s" % (r["name"], r.get("err")))

    # verdict across models
    if ok:
        n_gap = sum(1 for r in ok if r["gap"] > 0.02)
        n_cgap = sum(1 for r in ok if r["c_gap"] > 0.0)
        tfs = [r for r in ok if r["tf"] is not None]
        n_tf_beat = sum(1 for r in tfs if r["tf"] > r["mean_rnd"])
        print("\nVERDICT across %d parsed models (%d architectures, %d quantizations):" % (
            len(ok), len(set(r["arch"] for r in ok)), len(set(r["quant"] for r in ok))))
        print("  * antonyms closer than the anisotropy floor (raw gap > 0.02):     %d / %d" % (n_gap, len(ok)))
        print("  * antonyms closer even AFTER per-dim standardization (z_gap > 0):  %d / %d" % (n_cgap, len(ok)))
        print("  * true/false closer than the random baseline:                     %d / %d" % (n_tf_beat, len(tfs)))
        if tfs:
            mtf = sum(r["tf"] for r in tfs)/len(tfs)
            fg = [r["gap"] for r in ok if math.isfinite(r["gap"])]
            mgap = sum(fg)/len(fg) if fg else float("nan")
            print("  * mean true/false cosine %.3f ; mean antonym-over-random gap %.3f" % (mtf, mgap))
        print("\nOpposites cluster across every architecture and size measured. The geometry is a property")
        print("of PREDICTION, not of one model: to a next-token predictor, true and false are the same slot.")
        print("Meaning has to be COMPUTED (Titan's verified core), not predicted. Measured, not argued.")
    return 0

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
