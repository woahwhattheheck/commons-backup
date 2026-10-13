#!/usr/bin/env python3
"""host/decompile.py — THE DECOMPILER: read MEANING out of the BITS (docs/SDC.md, the read-direction).

The SDC decompiles meaning from bits: training COMPILED meaning into the param-bits; inference DECOMPILES it back;
baking RE-COMPILES. This instrument makes the read-direction explicit ON THE WEIGHTS THEMSELVES — no inference server
needed. A token's embedding row IS bits; **decompiling = finding the meaning those bits encode** = the nearest tokens in
embedding space. Bidirectional:
  - COMPILE   : token -> its embedding bits (a weight lookup).
  - DECOMPILE : bits  -> nearest-meaning (cosine over the embedding matrix -> the semantic neighborhood).
  - BIT-EDIT = MEANING-EDIT : nudge the bits toward another token's bits -> the decompiled meaning SHIFTS (why "just edit
    the bits" works: a bit-edit is a meaning-edit, mediated by the decompiler).

Reads token_embd + the tokenizer from a gguf directly (pure gguf-py + numpy). Operates on any pool member (Titan's
material). No downloads, no serving.

Run:  python host/decompile.py [model.gguf] [word]
"""
import sys, os
import numpy as np
import gguf

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODEL = sys.argv[1] if len(sys.argv) > 1 else "C:/llm/models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
WORD = sys.argv[2] if len(sys.argv) > 2 else "king"


def load_embed(path):
    r = gguf.GGUFReader(path)
    kv = {f.name: f for f in r.fields.values()}
    toks = kv.get("tokenizer.ggml.tokens")
    if not toks:
        raise RuntimeError("no tokenizer tokens in this gguf")
    vocab = [bytes(toks.parts[i]).decode("utf-8", "replace") for i in toks.data]   # token decode is cheap
    te = next((t for t in r.tensors if t.name in ("token_embd.weight", "tok_embeddings.weight")), None)
    if te is None:
        raise RuntimeError("no token_embd tensor")
    # The dequant of a 262144xN embedding is the ONE slow step (~100s on the 26B, pure-numpy Q4_0 -> f32).
    # Owner's near-instant rule: pay it ONCE, ever. Cache the dequantized matrix as an f16 sidecar (~half the
    # bytes, lossless for cosine at this scale); every later load is an np.load memmap (~2s). Keyed to the model
    # file + tensor type + shape, and invalidated if the model is newer than the cache (a re-bake changes bits).
    ty = te.tensor_type.name
    side = f"{path}.wbE.{ty}.{'x'.join(str(int(s)) for s in te.shape)}.f16.npy"
    E = None
    try:
        if os.path.exists(side) and os.path.getmtime(side) >= os.path.getmtime(path):
            E = np.load(side).astype(np.float32)   # cached bits, already decompiled
    except Exception:
        E = None
    if E is None:
        E = gguf.quants.dequantize(te.data, te.tensor_type).astype(np.float32)   # [vocab, dim] = the bits -> floats
        try:
            np.save(side, E.astype(np.float16))     # one-time; instant on every subsequent analysis
        except Exception:
            pass
    # normalize rows for cosine (fast; recomputed each load so the f16 cache need only hold E)
    En = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-8)
    return vocab, E, En, ty


def open_embed(path, progress=None, should_cancel=None):
    """Decompiler access for the White Box, CANCELLABLE + progress-reporting, with a NORMALIZED-En cache so re-loads are
    fast. Two sidecars: `.wbEn.` = the normalized f32-in-f16 embedding (the fast path: just load + upcast, no dequant, no
    normalize) and `.wbE.` = the raw f16 (an intermediate that skips the ~200 s dequant when only the En cache is stale).
    `progress(fraction 0..1)` is called as it builds; `should_cancel()` is polled and, if true, aborts with a RuntimeError.
    Returns (vocab, En resident f32 [vocab,dim], dim, type, En-sidecar-path)."""
    def prog(f):
        if progress:
            try: progress(max(0.0, min(1.0, float(f))))
            except Exception: pass
    def stop():
        return bool(should_cancel and should_cancel())

    import json as _json
    enside = f"{path}.wbEn.f16.npy"                                # normalized f16 embedding cache (fast path)
    metaside = f"{path}.wbmeta.json"                               # vocab + type + dim, so the fast path skips GGUFReader
    def fresh(p):
        return os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(path)
    prog(0.01)

    # FAST PATH: both caches fresh -> load them WITHOUT opening the 15 GB gguf metadata (~15 s saved) and copy the f16
    # embedding chunk-by-chunk, so progress + cancel work from the very first moment (no un-cancellable blocking phase).
    if fresh(enside) and fresh(metaside):
        try:
            meta = _json.load(open(metaside, encoding="utf-8"))
            vocab = meta["vocab"]; ty = meta.get("ty", "cached")
            if stop(): raise RuntimeError("cancelled")
            mm = np.load(enside, mmap_mode="r")
            n = mm.shape[0]; dim = int(mm.shape[1]); ch = 16384
            En = np.empty(mm.shape, np.float16)
            for s in range(0, n, ch):
                if stop():
                    del En; raise RuntimeError("cancelled")
                En[s:s + ch] = mm[s:s + ch]                        # f16 -> f16 copy
                prog(0.02 + 0.97 * min(1.0, (s + ch) / n))
            del mm; prog(1.0)
            return vocab, En, dim, ty, enside
        except RuntimeError:
            raise                                                 # a cancel propagates
        except Exception:
            pass                                                  # a corrupt cache -> fall through and rebuild

    # SLOW PATH (once per model): needs the gguf. Reuse an existing raw-f16 sidecar to skip the ~200 s dequant.
    if stop(): raise RuntimeError("cancelled")
    r = gguf.GGUFReader(path)                                     # the ~15 s metadata parse (slow path only)
    kv = {f.name: f for f in r.fields.values()}
    toks = kv.get("tokenizer.ggml.tokens")
    if not toks:
        raise RuntimeError("no tokenizer tokens in this gguf")
    vocab = [bytes(toks.parts[i]).decode("utf-8", "replace") for i in toks.data]
    te = next((t for t in r.tensors if t.name in ("token_embd.weight", "tok_embeddings.weight")), None)
    if te is None:
        raise RuntimeError("no token_embd tensor")
    ty = te.tensor_type.name
    shape = tuple(int(s) for s in te.shape)                       # gguf: (dim, vocab)
    dim = shape[0]
    rawside = f"{path}.wbE.{ty}.{'x'.join(str(s) for s in shape)}.f16.npy"
    prog(0.1)
    if fresh(rawside):
        E_src = np.load(rawside, mmap_mode="r")
    else:
        if stop(): raise RuntimeError("cancelled")
        E_full = gguf.quants.dequantize(te.data, te.tensor_type).astype(np.float16)   # the slow part (~200 s)
        try: np.save(rawside, E_full)
        except Exception: pass
        E_src = E_full
    prog(0.5)
    n = E_src.shape[0]
    En = np.empty((n, E_src.shape[1]), np.float16)               # the ONE resident array (normalized, f16)
    ch = 16384
    for s in range(0, n, ch):
        if stop():
            del En; raise RuntimeError("cancelled")
        blk = np.asarray(E_src[s:s + ch], np.float32)
        blk /= (np.linalg.norm(blk, axis=1, keepdims=True) + 1e-8)
        En[s:s + ch] = blk.astype(np.float16)
        prog(0.5 + 0.45 * min(1.0, (s + ch) / n))
    del E_src
    try:
        np.save(enside, En)                                      # cache normalized f16 + the vocab/type meta
        _json.dump({"ty": ty, "dim": int(dim), "vocab": vocab}, open(metaside, "w", encoding="utf-8"))
    except Exception:
        pass
    prog(1.0)
    return vocab, En, dim, ty, enside


class StreamE:
    """A ~0-RAM streaming view of a model's token-embedding matrix, read DIRECTLY from the stored quantized bits (memmap +
    per-chunk dequant) — NEVER a resident matrix, NEVER a build, NEVER a sidecar. Rows are normalized on the fly, so it is
    a drop-in for the old normalized `En` array: decompile_mm/sims_mm/row_of detect it and stream instead of slicing. The
    SDC read-direction done right — address the stored bits, hold only a bounded window, probe the result."""
    def __init__(self, path, te):                                  # te = the wbindex tensor entry (offset/tid/dshape/bytes/shape)
        self.path = path; self.tid = int(te["tid"]); self.dshape = tuple(te["dshape"])
        self.off = int(te["offset"]); self.nby = int(te["bytes"])
        self.n = int(self.dshape[0]); self.bpr = self.nby // self.n
        self.dim = int(te["shape"][0]) if te.get("shape") else None
        self.shape = (self.n, self.dim); self.dtype = np.dtype("float16")   # sentinel; not an array

    def _deq(self, s, c):                                          # dequant rows [s:s+c) off the memmap — bounded window
        c = max(0, min(int(c), self.n - int(s)))
        raw = np.memmap(self.path, np.uint8, "r", self.off + int(s) * self.bpr, (c * self.bpr,))
        if self.tid == 0:
            return np.frombuffer(bytes(raw), np.float32).reshape(c, -1)
        if self.tid == 1:
            return np.frombuffer(bytes(raw), np.float16).astype(np.float32).reshape(c, -1)
        blocks = np.frombuffer(bytes(raw), np.uint8).reshape((c,) + self.dshape[1:])
        return gguf.quants.dequantize(blocks, gguf.GGMLQuantizationType(self.tid)).astype(np.float32)

    def row(self, i):                                             # one normalized row (the query/arithmetic base)
        r = self._deq(int(i), 1)[0].astype(np.float32)
        return r / (np.linalg.norm(r) + 1e-8)

    def chunks(self, ch=1024):                                    # (start, normalized f32 rows) — bounded ~a few MB/chunk
        for s in range(0, self.n, ch):
            arr = self._deq(s, ch).astype(np.float32)
            arr /= (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-8)
            yield s, arr


class Vocab:
    """The tokenizer strings as MEMMAP-backed random access (a bytes blob + int32 offsets) — ~0 resident host RAM instead
    of a ~30 MB Python list. Drop-in for the decompiler (len / getitem / find): the strings never all live in host RAM;
    each is read from storage on demand. The SDC discipline applied to the token codec's symbol table too."""
    def __init__(self, blob_path, off_path):
        self.blob = np.memmap(blob_path, dtype=np.uint8, mode="r")
        self.off = np.load(off_path, mmap_mode="r")               # int32, n+1 offsets into the blob
        self.n = int(len(self.off) - 1)

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        i = int(i); a = int(self.off[i]); b = int(self.off[i + 1])
        return bytes(self.blob[a:b]).decode("utf-8", "replace")

    def find(self, word):
        """token id for a word, trying the usual tokenizer forms — a bounded scan over the memmap, no resident list."""
        cset = {c.encode("utf-8") for c in (word, "▁" + word, " " + word, word.capitalize(), "▁" + word.capitalize())}
        off, blob = self.off, self.blob
        for i in range(self.n):                                   # pass 1: exact byte match (no decode — fast)
            if bytes(blob[int(off[i]):int(off[i + 1])]) in cset:
                return i
        for i in range(self.n):                                   # pass 2 (rare): substring match (decodes)
            if bytes(blob[int(off[i]):int(off[i + 1])]).decode("utf-8", "replace").strip("▁ ") == word:
                return i
        return None


def _build_vocab(path, blobp, offp):
    """Build the two tiny memmap sidecars (blob + int32 offsets) ONCE, from the tokenizer strings (reusing an existing
    `.wbvocab.json` if present, else a one-time header read). TIME, not a resident model load."""
    import json as _json
    toks = None
    jpath = path + ".wbvocab.json"
    try:
        if os.path.exists(jpath) and os.path.getmtime(jpath) >= os.path.getmtime(path):
            toks = _json.load(open(jpath, encoding="utf-8"))
    except Exception:
        toks = None
    if toks is None:
        r = gguf.GGUFReader(path)                                 # one-time header parse for the tokenizer strings
        kv = {f.name: f for f in r.fields.values()}
        tk = kv.get("tokenizer.ggml.tokens")
        if not tk:
            raise RuntimeError("no tokenizer tokens in this gguf")
        toks = [bytes(tk.parts[i]).decode("utf-8", "replace") for i in tk.data]
    offs = np.empty(len(toks) + 1, np.int32); offs[0] = 0
    acc = 0
    with open(blobp, "wb") as f:
        for j, t in enumerate(toks):
            b = t.encode("utf-8"); f.write(b); acc += len(b); offs[j + 1] = acc
    np.save(offp, offs)


def load_vocab(path):
    """Return a MEMMAP-backed Vocab (~0 resident). Builds the blob + offset sidecars once, then memmaps them — the token
    strings are read from storage on demand, never all held in host RAM."""
    blobp = path + ".wbvocab.blob"; offp = path + ".wbvocab.off.npy"
    def fresh(p):
        return os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(path)
    if not (fresh(blobp) and fresh(offp)):
        _build_vocab(path, blobp, offp)
    return Vocab(blobp, offp)


def open_stream(path, te):
    """~0-RAM decompiler access: STREAM the token-embedding bits (StreamE) + the cached vocab. No build, no resident
    matrix, no sidecar dependency — works on any model (Titan included). Returns (vocab, StreamE, dim, type)."""
    vocab = load_vocab(path)
    E = StreamE(path, te)
    ty = "F32" if E.tid == 0 else ("F16" if E.tid == 1 else gguf.GGMLQuantizationType(E.tid).name)
    return vocab, E, E.dim, "stream:" + ty


def decompile_mm(En, qvec, vocab, k=10, exclude=(), chunk=32768):
    """cosine of a query vector against EVERY embedding row → top-k nearest tokens. Streams a StreamE off the stored bits
    (~0 RAM), or upcasts a resident f16 array per chunk (the old path). Same math either way."""
    q = np.asarray(qvec, np.float32)
    q = q / (np.linalg.norm(q) + 1e-8)
    n = En.shape[0]
    if isinstance(En, StreamE):
        sims = np.empty(n, np.float32)
        for s, arr in En.chunks(1024):
            sims[s:s + arr.shape[0]] = arr @ q
    elif En.dtype == np.float32:
        sims = En @ q
    else:
        sims = np.empty(n, np.float32)
        for s in range(0, n, chunk):
            sims[s:s + chunk] = np.asarray(En[s:s + chunk], np.float32) @ q
    m = min(k + len(exclude) + 4, n - 1)
    order = np.argpartition(-sims, m)[:m + 1]
    order = order[np.argsort(-sims[order])]
    out = []
    for i in order:
        i = int(i)
        if i in exclude:
            continue
        out.append((vocab[i].replace("▁", "·"), float(sims[i])))
        if len(out) >= k:
            break
    return out


def row_of(En, i):
    """one (already-normalized) embedding row — the query/arithmetic base on the unit sphere."""
    if isinstance(En, StreamE):
        return En.row(i)
    return np.asarray(En[int(i)], np.float32)


def find_tok(vocab, word):
    if isinstance(vocab, Vocab):
        return vocab.find(word)                                   # memmap-backed bounded scan — no resident list
    # gemma/llama tokenizers use ▁ for a leading space; try a few forms (list path, standalone CLI)
    for cand in (word, "▁" + word, " " + word, word.capitalize(), "▁" + word.capitalize()):
        if cand in vocab:
            return vocab.index(cand)
    for i, t in enumerate(vocab):
        if t.strip("▁ ") == word:
            return i
    return None


def open_memmap(path):
    """INSTANT decode access — the fix for the slow Decompiler. If the normalized-f16 sidecar + meta already exist (they
    are built once by open_embed), MEMORY-MAP the sidecar (np.load mmap_mode='r' reads only the header — no 1.5 GB
    resident copy, no build wait) and read the vocab from the meta JSON. Every query then streams the memmap in chunks
    (decompile_mm / sims_mm), so a decode runs in ~ms with a few-hundred-MB transient. Returns (vocab, En_memmap, dim, ty)
    or None if the sidecars are not present/fresh yet (caller falls back to the one-time background build)."""
    import json as _json
    enside = f"{path}.wbEn.f16.npy"
    metaside = f"{path}.wbmeta.json"

    def fresh(p):
        return os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(path)

    if not (fresh(enside) and fresh(metaside)):
        return None
    try:
        meta = _json.load(open(metaside, encoding="utf-8"))
        vocab = meta["vocab"]
        ty = meta.get("ty", "cached")
        mm = np.load(enside, mmap_mode="r")                      # memmap — instant, no resident copy
        dim = int(meta.get("dim") or mm.shape[1])
        return vocab, mm, dim, ty
    except Exception:
        return None


def sims_mm(En, q, chunk=8192):
    """Full cosine/dot similarity of a query vector against EVERY row — memmap-safe (chunked upcast, never materializes the
    whole f16 matrix as f32). Rows are pre-normalized; q is normalized here. Used by meaning-search / alignment / the
    single-parameter decode so they work off the memmap without a resident copy."""
    q = np.asarray(q, np.float32)
    q = q / (np.linalg.norm(q) + 1e-8)
    n = En.shape[0]
    if isinstance(En, StreamE):
        sims = np.empty(n, np.float32)
        for s, arr in En.chunks(1024):
            sims[s:s + arr.shape[0]] = arr @ q
        return sims
    if En.dtype == np.float32:
        return En @ q
    sims = np.empty(n, np.float32)
    for s in range(0, n, chunk):
        sims[s:s + chunk] = np.asarray(En[s:s + chunk], np.float32) @ q
    return sims


def decompile(vec, En, vocab, k=8, exclude=()):
    v = vec / (np.linalg.norm(vec) + 1e-8)
    sims = En @ v
    order = np.argsort(-sims)
    out = []
    for i in order:
        if i in exclude:
            continue
        out.append((vocab[i].replace("▁", "·"), float(sims[i])))
        if len(out) >= k:
            break
    return out


def main():
    print(f"[decompile] reading the BITS of {os.path.basename(MODEL)} — token_embd + tokenizer\n")
    vocab, E, En, ty = load_embed(MODEL)
    print(f"[decompile] embedding matrix: {E.shape[0]} tokens x {E.shape[1]} dims (stored {ty}); the bits.\n")

    tid = find_tok(vocab, WORD)
    if tid is None:
        print(f"[decompile] '{WORD}' not a single token; try another word"); return
    print(f"[decompile] COMPILE:  '{WORD}' -> token {tid} -> its embedding bits (row {tid}, ‖v‖={np.linalg.norm(E[tid]):.3f})")
    print(f"[decompile] DECOMPILE: those bits -> nearest MEANING (cosine over all {len(vocab)} rows):")
    for t, s in decompile(E[tid], En, vocab, k=8, exclude=(tid,)):
        print(f"              {s:+.3f}  {t!r}")

    # BIT-EDIT = MEANING-EDIT: interpolate the bits toward another token, watch the meaning move
    for target in ("queen", "man", "paris"):
        j = find_tok(vocab, target)
        if j is None:
            continue
        print(f"\n[decompile] BIT-EDIT: nudge '{WORD}' bits 60% toward '{target}' bits -> decompiled meaning shifts to:")
        edited = 0.4 * E[tid] + 0.6 * E[j]
        for t, s in decompile(edited, En, vocab, k=5, exclude=(tid, j)):
            print(f"              {s:+.3f}  {t!r}")
        break
    print("\n[decompile] the bits ARE the meaning (decompiled); a bit-edit is a meaning-edit. The SDC read-direction, on the weights.")


if __name__ == "__main__":
    main()
