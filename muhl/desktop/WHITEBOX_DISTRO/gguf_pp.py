#!/usr/bin/env python3
"""host/gguf_pp.py — a PURE-PYTHON GGUF reader (no numpy). read the tokenizer + the token-embedding weights off any
model's stored bits, so the white-box probes work on ANY model, not just Titan. (fable, 07-16)

Parses the GGUF header/metadata/tensor-index in pure python, memmaps the file, and dequantizes an embedding row
(F32/F16/Q4_0/Q8_0) on demand. Reader is read-only; ~0 RAM (one row window). Honors the numpy ban — struct + mmap only.
"""
import math, mmap, os, struct
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)

_SCALAR = {0: ("<B", 1), 1: ("<b", 1), 2: ("<H", 2), 3: ("<h", 2), 4: ("<I", 4), 5: ("<i", 4),
           6: ("<f", 4), 7: ("<?", 1), 10: ("<Q", 8), 11: ("<q", 8), 12: ("<d", 8)}
# ggml type -> (bytes_per_block, weights_per_block)
_QT = {0: (4, 1), 1: (2, 1), 2: (18, 32), 8: (34, 32),                    # F32, F16, Q4_0, Q8_0
       12: (144, 256), 13: (176, 256), 14: (210, 256)}                    # Q4_K, Q5_K, Q6_K (K-quants, QK_K=256)
_TYNAME = {0: "F32", 1: "F16", 2: "Q4_0", 8: "Q8_0", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K"}


def row_bytes(tid, n):
    bpb, wpb = _QT[tid]; return n // wpb * bpb


def _sm_k4(j, q):
    """get_scale_min_k4 (ggml): unpack a 6-bit scale + min from the packed 12-byte K-quant scales."""
    if j < 4:
        return q[j] & 63, q[j + 4] & 63
    return (q[j + 4] & 0xF) | ((q[j - 4] >> 6) << 4), (q[j + 4] >> 4) | ((q[j] >> 6) << 4)


def dequant(raw, tid, n):
    """Dequantize n weights from a raw block-aligned byte row. Pure python. F32/F16/Q4_0/Q8_0/Q4_K/Q5_K/Q6_K."""
    if tid == 0: return list(struct.unpack_from("<%df" % n, raw, 0))
    if tid == 1: return list(struct.unpack_from("<%de" % n, raw, 0))
    out = [0.0] * n
    if tid == 2:                                                          # Q4_0
        p = 0; o = 0
        while o < n:
            s = struct.unpack_from("<e", raw, p)[0]; p += 2
            for j in range(16): out[o + j] = ((raw[p + j] & 0xf) - 8) * s
            for j in range(16): out[o + j + 16] = ((raw[p + j] >> 4) - 8) * s
            p += 16; o += 32
        return out
    if tid == 8:                                                         # Q8_0
        p = 0; o = 0
        while o < n:
            s = struct.unpack_from("<e", raw, p)[0]; p += 2
            for j in range(32):
                q = raw[p + j]; out[o + j] = (q - 256 if q >= 128 else q) * s
            p += 32; o += 32
        return out
    if tid == 12:                                                        # Q4_K (144 B / 256 w)
        p = 0; o = 0
        while o < n:
            d = struct.unpack_from("<e", raw, p)[0]; dmin = struct.unpack_from("<e", raw, p + 2)[0]
            sc = raw[p + 4:p + 16]; qs = raw[p + 16:p + 144]; qo = 0; isb = 0
            for j in range(0, 256, 64):
                s1, m1 = _sm_k4(isb, sc); s2, m2 = _sm_k4(isb + 1, sc)
                d1 = d * s1; o1 = dmin * m1; d2 = d * s2; o2 = dmin * m2
                for l in range(32): out[o + j + l] = d1 * (qs[qo + l] & 0xF) - o1
                for l in range(32): out[o + j + 32 + l] = d2 * (qs[qo + l] >> 4) - o2
                qo += 32; isb += 2
            p += 144; o += 256
        return out
    if tid == 13:                                                        # Q5_K (176 B / 256 w)
        p = 0; o = 0
        while o < n:
            d = struct.unpack_from("<e", raw, p)[0]; dmin = struct.unpack_from("<e", raw, p + 2)[0]
            sc = raw[p + 4:p + 16]; qh = raw[p + 16:p + 48]; qs = raw[p + 48:p + 176]
            qo = 0; isb = 0; u1 = 1; u2 = 2
            for j in range(0, 256, 64):
                s1, m1 = _sm_k4(isb, sc); s2, m2 = _sm_k4(isb + 1, sc)
                d1 = d * s1; o1 = dmin * m1; d2 = d * s2; o2 = dmin * m2
                for l in range(32): out[o + j + l] = d1 * ((qs[qo + l] & 0xF) + (16 if qh[l] & u1 else 0)) - o1
                for l in range(32): out[o + j + 32 + l] = d2 * ((qs[qo + l] >> 4) + (16 if qh[l] & u2 else 0)) - o2
                qo += 32; isb += 2; u1 <<= 2; u2 <<= 2
            p += 176; o += 256
        return out
    if tid == 14:                                                        # Q6_K (210 B / 256 w)
        p = 0; o = 0
        while o < n:
            ql = raw[p:p + 128]; qh = raw[p + 128:p + 192]
            sc = [(x - 256 if x >= 128 else x) for x in raw[p + 192:p + 208]]
            d = struct.unpack_from("<e", raw, p + 208)[0]
            for nn in range(0, 256, 128):
                qlo = nn // 128 * 64; qho = nn // 128 * 32; sco = nn // 128 * 8
                for l in range(32):
                    isb = l // 16
                    q1 = ((ql[qlo + l] & 0xF) | (((qh[qho + l] >> 0) & 3) << 4)) - 32
                    q2 = ((ql[qlo + l + 32] & 0xF) | (((qh[qho + l] >> 2) & 3) << 4)) - 32
                    q3 = ((ql[qlo + l] >> 4) | (((qh[qho + l] >> 4) & 3) << 4)) - 32
                    q4 = ((ql[qlo + l + 32] >> 4) | (((qh[qho + l] >> 6) & 3) << 4)) - 32
                    out[o + nn + l] = d * sc[sco + isb + 0] * q1
                    out[o + nn + l + 32] = d * sc[sco + isb + 2] * q2
                    out[o + nn + l + 64] = d * sc[sco + isb + 4] * q3
                    out[o + nn + l + 96] = d * sc[sco + isb + 6] * q4
            p += 210; o += 256
        return out
    raise RuntimeError(f"quant type {tid} not decodable by gguf_pp")


def _rstr(mm, off):
    ln = struct.unpack_from("<Q", mm, off)[0]; off += 8
    return bytes(mm[off:off + ln]), off + ln


def _read_value(mm, off, vt, keep):
    if vt == 8:
        return _rstr(mm, off)
    if vt == 9:                                              # array
        et = struct.unpack_from("<I", mm, off)[0]; off += 4
        cnt = struct.unpack_from("<Q", mm, off)[0]; off += 8
        if keep:
            arr = []
            for _ in range(cnt):
                v, off = _read_value(mm, off, et, True); arr.append(v)
            return arr, off
        for _ in range(cnt):                                # skip fast
            off = _read_value(mm, off, et, False)[1] if et in (8, 9) else off + _SCALAR[et][1]
        return None, off
    f, sz = _SCALAR[vt]; return struct.unpack_from(f, mm, off)[0], off + sz


class GGUF:
    def __init__(self, path):
        if not os.path.exists(path):                        # model may have been tidied into _removed/ — follow it
            alt = os.path.join(os.path.dirname(path), "_removed", os.path.basename(path))
            if os.path.exists(alt): path = alt
        self.path = path
        self.f = open(path, "rb"); self.mm = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        mm = self.mm
        assert mm[:4] == b"GGUF", "not a GGUF file"
        ver = struct.unpack_from("<I", mm, 4)[0]
        n_tensors = struct.unpack_from("<Q", mm, 8)[0]
        n_kv = struct.unpack_from("<Q", mm, 16)[0]
        off = 24
        align = 32; tokens = None; merges = None; ttypes = None; self.kv = {}
        for _ in range(n_kv):
            key, off = _rstr(mm, off)
            ks = bytes(key).decode("utf-8", "replace")
            vt = struct.unpack_from("<I", mm, off)[0]; off += 4
            if vt == 9:                                      # array — keep tokenizer tokens + merges + token_type
                want = key in (b"tokenizer.ggml.tokens", b"tokenizer.ggml.merges", b"tokenizer.ggml.token_type")
                val, off = _read_value(mm, off, vt, want)
                if key == b"tokenizer.ggml.tokens": tokens = val
                elif key == b"tokenizer.ggml.merges": merges = val
                elif key == b"tokenizer.ggml.token_type": ttypes = val
            else:                                            # scalar/string — keep them all (arch hyperparams live here)
                val, off = _read_value(mm, off, vt, True)
                if isinstance(val, (bytes, bytearray)):
                    try: val = bytes(val).decode("utf-8", "replace")
                    except Exception: pass
                self.kv[ks] = val
                if key == b"general.alignment": align = int(val)
        tensors = {}
        for _ in range(n_tensors):
            name, off = _rstr(mm, off)
            nd = struct.unpack_from("<I", mm, off)[0]; off += 4
            dims = list(struct.unpack_from("<%dQ" % nd, mm, off)); off += 8 * nd
            ttype = struct.unpack_from("<I", mm, off)[0]; off += 4
            toff = struct.unpack_from("<Q", mm, off)[0]; off += 8
            tensors[bytes(name).decode("utf-8", "replace")] = {"dims": dims, "type": ttype, "off": toff}
        data0 = (off + align - 1) // align * align          # tensor data section start (aligned)
        self.tensors = tensors; self.data0 = data0          # keep the full table (any tensor readable later)
        te = tensors.get("token_embd.weight") or tensors.get("tok_embeddings.weight")
        if te is None:
            raise RuntimeError("no token_embd tensor")
        self.tid = te["type"]; self.n_embd = int(te["dims"][0]); self.n_vocab = int(te["dims"][1])
        bpb, wpb = _QT.get(self.tid, (None, None))
        if bpb is None:
            raise RuntimeError(f"embedding quant type {self.tid} not decodable by gguf_pp (F32/F16/Q4_0/Q8_0 only)")
        self.row_bytes = self.n_embd // wpb * bpb
        self.data_off = data0 + te["off"]
        self.tyname = _TYNAME.get(self.tid, str(self.tid))
        self.ver = ver
        # vocab index: pretty-token bytes -> id (byte-level BPE uses 'Ġ' for space; sentencepiece uses '▁')
        self.tokens = [bytes(t) for t in (tokens or [])]
        self.merges = [bytes(m).decode("utf-8", "replace") if isinstance(m, (bytes, bytearray)) else str(m) for m in (merges or [])]
        self.token_type = list(ttypes or [])
        self.vindex = {}
        for i, t in enumerate(self.tokens):
            self.vindex.setdefault(t, i)
        self.cache = {}

    def deq_row(self, i):
        """the RAW (un-normalized) dequantized embedding row for token i — the norm carries info the unit view drops."""
        off = self.data_off + i * self.row_bytes
        return dequant(self.mm[off:off + self.row_bytes], self.tid, self.n_embd)

    def rownorm(self, i):
        v = self.deq_row(i); return math.sqrt(sum(x * x for x in v))

    def _deq_bytes(self, raw, tid, n):
        """dequant n weights from a raw byte row. F32/F16/Q4_0/Q8_0/Q4_K/Q5_K/Q6_K. pure python."""
        return dequant(raw, tid, n)

    def tensor(self, name):
        """dequantize a whole tensor. 1-D → a flat list (norms). 2-D weight [in,out] → list of `out` rows of length `in`
        (row j = output neuron j's weights, so y[j] = dot(row_j, x)). Q8_0 / F32 / F16 only."""
        t = self.tensors[name]; tid = int(t["type"]); dims = t["dims"]; base = self.data0 + int(t["off"])
        if len(dims) == 1:
            n = int(dims[0]); rb = n * (4 if tid == 0 else 2 if tid == 1 else (n // 32 * 34) and 0)
            return self._deq_bytes(self.mm[base:base + (n * 4 if tid == 0 else n * 2)], tid, n)
        n_in = int(dims[0]); n_out = int(dims[1])
        rb = row_bytes(tid, n_in)
        rows = []
        for j in range(n_out):
            o = base + j * rb
            rows.append(self._deq_bytes(self.mm[o:o + rb], tid, n_in))
        return rows

    def _row(self, i):
        out = self.deq_row(i)
        n = math.sqrt(sum(x * x for x in out)) or 1.0
        return [x / n for x in out]

    def _find(self, word):
        forms = [word, "Ġ" + word, "▁" + word, " " + word, word.capitalize(),
                 "Ġ" + word.capitalize(), "▁" + word.capitalize()]
        for fm in forms:
            i = self.vindex.get(fm.encode("utf-8"))
            if i is not None:
                return i
        return None

    def vec(self, word):
        if word in self.cache:
            return self.cache[word]
        i = self._find(word); v = self._row(i) if i is not None else None
        self.cache[word] = v; return v


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) if (a and b) else None


if __name__ == "__main__":
    import sys, time
    path = sys.argv[1] if len(sys.argv) > 1 else PFCP.p("models/SmolLM2-360M-Instruct-Q8_0.gguf")
    t0 = time.time(); g = GGUF(path)
    print(f"gguf_pp (pure python, no numpy): {os.path.basename(path)}")
    print(f"  gguf v{g.ver} · embd dim {g.n_embd} · vocab {g.n_vocab:,} · token_embd {g.tyname} · loaded {time.time()-t0:.2f}s")
    for a, b in [("frog", "hop"), ("enemy", "danger"), ("silence", "stillness"), ("love", "hate"), ("car", "flower")]:
        va, vb = g.vec(a), g.vec(b)
        print(f"  cos({a:8s},{b:9s}) = {cos(va, vb):+.3f}" if (va and vb) else f"  {a}/{b}: missing")
