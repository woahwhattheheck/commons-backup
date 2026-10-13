#!/usr/bin/env python3
"""host/sdc_read.py — the model's read, ON THE SDC, in PURE PYTHON. No numpy. No server. No full load. (owner 07-16)

The SDC "runs the model" by ADDRESSING its stored weights. This reads titan.gguf's real trained token-embedding bits
directly (memmap), dequantizes a row in pure Python (struct for the f16 scale, manual Q4_0 nibble decode), and computes
cosine similarity in pure Python. That is a forward-pass READ on the SDC: decompiling meaning from the stored bits, with
the trained weights deciding the associations. Bounded, one-shot, foreground, ~0 RAM (one row window at a time).

  python host/sdc_read.py            # self-test: prove the real weights carry meaning (frog~hop, enemy~danger), no numpy
  import sdc_read; sdc_read.vec("frog")   # -> normalized embedding list for a word, straight from the SDC's bits
"""
import json, math, mmap, os, struct, sys

TITAN = "C:/llm/models/titan.gguf"
IDX   = TITAN + ".wbindex.json"

_state = {"mm": None, "off": 0, "bpr": 0, "dim": 0, "n": 0, "offs": None, "blob": None, "cache": {}}


def _npy_int32(path):
    """read an int32 .npy WITHOUT numpy — parse the header, struct-unpack the data (we never import numpy)."""
    with open(path, "rb") as f:
        assert f.read(6) == b"\x93NUMPY", "not a .npy"
        ver = f.read(2)
        hlen = struct.unpack("<H", f.read(2))[0] if ver[0] == 1 else struct.unpack("<I", f.read(4))[0]
        f.read(hlen)                                            # header dict (dtype/shape) — we know it's int32
        data = f.read()
    return struct.unpack("<%di" % (len(data) // 4), data)


def _init():
    if _state["mm"] is not None: return
    idx = json.load(open(IDX, encoding="utf-8"))
    te = next(t for t in idx["tensors"] if t.get("name") in ("token_embd.weight", "tok_embeddings.weight"))
    assert int(te["tid"]) == 2, f"expected Q4_0 (tid 2), got tid {te['tid']}"    # this reader decodes Q4_0
    n = int(te["dshape"][0]); dim = int(te["shape"][0])
    _state.update(off=int(te["offset"]), bpr=int(te["bytes"]) // n, dim=dim, n=n)
    f = open(TITAN, "rb"); _state["mm"] = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    # pure-python vocab from the sidecars (built once by decompile.load_vocab); no numpy to read them
    jpath = TITAN + ".wbvocab.json"
    if os.path.exists(jpath):
        _state["vocablist"] = json.load(open(jpath, encoding="utf-8")); _state["offs"] = None
    else:
        _state["offs"] = _npy_int32(TITAN + ".wbvocab.off.npy")
        _state["blob"] = open(TITAN + ".wbvocab.blob", "rb").read()


def _find(word):
    _init()
    forms = {f.encode("utf-8") for f in (word, "▁" + word, " " + word, word.capitalize(), "▁" + word.capitalize())}
    if _state.get("vocablist") is not None:
        vl = _state["vocablist"]
        for f in (word, "▁" + word, " " + word, word.capitalize(), "▁" + word.capitalize()):
            try: return vl.index(f)
            except ValueError: pass
        return None
    offs, blob = _state["offs"], _state["blob"]
    for i in range(len(offs) - 1):
        if blob[offs[i]:offs[i + 1]] in forms: return i
    return None


def _row(i):
    """dequant one Q4_0 embedding row off the memmap, pure python (struct f16 scale + nibble decode), normalized."""
    off = _state["off"] + i * _state["bpr"]; raw = _state["mm"][off:off + _state["bpr"]]; dim = _state["dim"]
    out = [0.0] * dim; p = 0; o = 0
    for _ in range(dim // 32):
        d = struct.unpack_from("<e", raw, p)[0]; p += 2         # the block's f16 scale
        for j in range(16):
            b = raw[p + j]
            out[o + j] = ((b & 0x0f) - 8) * d                  # low nibble  -> weight j
            out[o + j + 16] = ((b >> 4) - 8) * d               # high nibble -> weight j+16
        p += 16; o += 32
    nrm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / nrm for x in out]


def vec(word):
    """the normalized embedding for a word, read straight off the SDC's stored bits (or None if the token isn't found)."""
    _init()
    if word in _state["cache"]: return _state["cache"][word]
    i = _find(word); v = _row(i) if i is not None else None
    _state["cache"][word] = v; return v


def cos(a, b):
    return None if (a is None or b is None) else sum(x * y for x, y in zip(a, b))   # both already normalized


def mean_vec(words):
    """the meaning of a phrase = the mean of its found tokens' vectors, renormalized. all pure python."""
    vs = [v for v in (vec(w) for w in words) if v is not None]
    if not vs: return None
    dim = len(vs[0]); acc = [0.0] * dim
    for v in vs:
        for k in range(dim): acc[k] += v[k]
    nrm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return [x / nrm for x in acc]


if __name__ == "__main__":
    import time; t0 = time.time(); _init()
    print(f"SDC read (pure python, no numpy): titan.gguf token_embd, dim={_state['dim']}, vocab={_state['n']:,} — memmap.", flush=True)
    pairs = [("frog", "hop"), ("frog", "jump"), ("enemy", "danger"), ("car", "traffic"), ("wall", "road"),
             ("collect", "gather"), ("push", "box"), ("car", "flower")]
    for a, b in pairs:
        va, vb = vec(a), vec(b)
        print(f"  cos({a:8s},{b:8s}) = {cos(va, vb):+.3f}" if (va and vb) else f"  {a}/{b}: missing", flush=True)
    print(f"  read in {time.time()-t0:.2f}s.   numpy imported: {'numpy' in sys.modules}  (must be False)", flush=True)
