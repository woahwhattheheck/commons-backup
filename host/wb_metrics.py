#!/usr/bin/env python3
"""WB-METRICS: the White Box metric union, pure stdlib.

Every metric from the White Box instrument family (PATENT_2 M.1-M.10) and
the fable research suite, reimplemented as pure functions over decoded
float rows. No numpy, no inference, no transport: callers fetch bytes and
decode; these functions measure. Transport lives in wb_range.py.

Metric families:
  tensor stats + quant stress (M.5)        entropy crater / magics (audit)
  anisotropy + norm/frequency (explore)    sign/rogue-dim mechanism
  bit-depth ablation (bits)                anisotropy cleanup A/B (clean)
  transistors + latches (M.9/M.10)         attention IPC channels
  per-expert health (M.7)                  axis purity + poles (axis)
  analogy + quant damage (M.2)             concept neighbors (M.2/M.3)
  neuron monosemanticity                   manifold/value-sanity (direction)
  category clustering (practical)          order recovery (lab3)
"""

from __future__ import annotations

from collections import Counter
import heapq
import math
import operator
import random
import re
import struct


SCHEMA_VERSION = "commons-wb-metrics/v1"

PFC_MAGICS = {
    b"PFCAPP01", b"PFCEXEC1", b"PFCGAME1", b"PFCMBUS1", b"PFCMMU01",
    b"PFCONE01", b"PFCOPR01", b"PFCPHYS1", b"PFCPIPE1", b"PFCPROV1",
    b"PFCRAY01", b"PFCSCLK1", b"PFCSMACH", b"PFCSMCLK", b"PFCSUBS1",
    b"PFCTET01", b"PFCTUN01", b"PFCTYPED", b"PFCWINMN",
}

ANTONYMS = [("love", "hate"), ("hot", "cold"), ("light", "dark"),
            ("up", "down"), ("day", "night"), ("fast", "slow"),
            ("war", "peace"), ("rich", "poor"), ("big", "small"),
            ("good", "evil"), ("true", "false"), ("open", "closed"),
            ("full", "empty"), ("life", "death"), ("joy", "grief"),
            ("black", "white"), ("weak", "strong"), ("high", "low")]
RANDOM_WORDS = ["stone", "music", "river", "clock", "bread", "engine",
                "cloud", "letter", "garden", "planet", "market", "window",
                "copper", "harvest", "signal", "anchor", "velvet", "meadow",
                "glass", "ocean", "paper", "mountain", "iron", "silver"]
FREQ_LADDER = ["the", "of", "and", "to", "in", "is", "it", "that",
               "people", "because", "however", "science", "molecule",
               "philosophy", "elephant", "xylophone", "serendipity",
               "onomatopoeia"]
CATEGORIES = {
    "animal": ["dog", "cat", "horse", "lion", "tiger", "wolf", "bear", "rabbit"],
    "color": ["red", "blue", "green", "yellow", "purple", "orange", "pink", "brown"],
    "fruit": ["apple", "banana", "orange", "grape", "peach", "cherry", "lemon", "mango"],
    "country": ["france", "germany", "spain", "japan", "brazil", "canada", "egypt", "india"],
    "emotion": ["joy", "fear", "anger", "sadness", "hope", "love", "grief", "calm"],
    "metal": ["iron", "gold", "silver", "copper", "steel", "bronze", "zinc", "nickel"],
}
ANALOGY_CATS = {
    "capitals": [("france", "paris"), ("japan", "tokyo"), ("italy", "rome"),
                 ("egypt", "cairo"), ("russia", "moscow"), ("spain", "madrid"),
                 ("germany", "berlin"), ("greece", "athens"), ("england", "london")],
    "past_tense": [("walk", "walked"), ("play", "played"), ("jump", "jumped"),
                   ("talk", "talked"), ("open", "opened"), ("cook", "cooked"),
                   ("work", "worked"), ("call", "called")],
    "plural": [("cat", "cats"), ("dog", "dogs"), ("car", "cars"),
               ("book", "books"), ("tree", "trees"), ("hand", "hands"),
               ("king", "kings"), ("day", "days")],
    "comparative": [("big", "bigger"), ("small", "smaller"), ("fast", "faster"),
                    ("slow", "slower"), ("strong", "stronger"), ("weak", "weaker"),
                    ("high", "higher"), ("low", "lower")],
    "gender": [("king", "queen"), ("man", "woman"), ("boy", "girl"),
               ("father", "mother"), ("son", "daughter"),
               ("brother", "sister"), ("uncle", "aunt"), ("prince", "princess")],
}


class WbMetricsError(AssertionError):
    """A metric contract was violated."""


# ----------------------------------------------------------------- primitives

def norm(v):
    n = math.sqrt(sum(x * x for x in v))
    return n


def unit(v):
    n = norm(v) or 1.0
    return [x / n for x in v]


def cos(a, b):
    na, nb = norm(a), norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def mean_vec(rows):
    if not rows:
        raise WbMetricsError("no rows")
    d = len(rows[0])
    acc = [0.0] * d
    for row in rows:
        for k in range(d):
            acc[k] += row[k]
    return [x / len(rows) for x in acc]


def percentile(sorted_vals, pct):
    if not sorted_vals:
        raise WbMetricsError("no values")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def histogram(vals, bins, lo=None, hi=None):
    if not vals:
        return {"bins": [], "lo": 0.0, "hi": 0.0}
    lo = min(vals) if lo is None else lo
    hi = max(vals) if hi is None else hi
    if hi <= lo:
        hi = lo + 1e-9
    counts = [0] * bins
    for v in vals:
        c = min(max(v, lo), hi)
        idx = int((c - lo) / (hi - lo) * bins)
        counts[min(idx, bins - 1)] += 1
    return {"bins": counts, "lo": lo, "hi": hi}


def byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def strided(n, k):
    if n <= k:
        return list(range(n))
    step = max(1, n // k)
    return list(range(0, n, step))


def role_of(name: str) -> str:
    n = name.lower()
    for key in ("token_embd", "embed_tokens", "ffn_gate_up_exps",
                "ffn_down_exps", "ffn_gate_inp", "attn_q", "attn_k",
                "attn_v", "attn_output", "attn_norm", "ffn_gate", "ffn_up",
                "ffn_down", "ffn_norm", "output_norm", "output",
                "gate_proj", "up_proj", "down_proj", "q_proj", "k_proj",
                "v_proj", "o_proj", "layernorm", "norm"):
        if key in n:
            return key
    return "other"


def layer_of(name: str) -> int:
    m = re.search(r"(?:blk|layers|h)\.(\d+)\.", name)
    return int(m.group(1)) if m else -1


# ------------------------------------------- tensor stats + quant stress (M.5)

def tensor_stats(values, *, block: int = 32, hist_bins: int = 40) -> dict:
    """mean/std/absmean/min/max/sparsity + histogram + per-block quant stress."""
    if not values:
        raise WbMetricsError("no values")
    finite = [v for v in values if math.isfinite(v)]
    insane = len(values) - len(finite)
    if not finite:
        raise WbMetricsError("no finite values")
    n = len(finite)
    mean = sum(finite) / n
    var = sum((v - mean) ** 2 for v in finite) / n
    absvals = [abs(v) for v in finite]
    blocks = [max(absvals[i:i + block]) for i in range(0, n - block + 1, block)]
    if not blocks:
        blocks = [max(absvals)]
    blocks.sort()
    return {
        "mean": mean,
        "std": math.sqrt(var),
        "absmean": sum(absvals) / n,
        "min": min(finite),
        "max": max(finite),
        "sparsity": sum(1 for v in finite if abs(v) < 1e-6) / n,
        "insane": insane,
        "hist": histogram(finite, hist_bins),
        "stress": {
            "block": block,
            "p99": percentile(blocks, 99),
            "max": blocks[-1],
            "hist": histogram(blocks, 30),
        },
        "sampled": n,
    }


def row_norm_stats(rows) -> dict:
    norms = [norm(r) for r in rows]
    if not norms:
        raise WbMetricsError("no rows")
    mean = sum(norms) / len(norms)
    var = sum((x - mean) ** 2 for x in norms) / len(norms)
    cv = math.sqrt(var) / (mean + 1e-12)
    return {"rownorm_mean": mean, "rownorm_cv": cv}


# ------------------------------------------------- entropy crater (audit/scan2)

def entropy_scan(row_bytes, *, drop: float = 0.7) -> dict:
    """row_bytes: list of raw per-row byte strings. Flags rows whose head-byte
    entropy craters below median - drop (the validated baked-circuit signal)."""
    if not row_bytes:
        raise WbMetricsError("no rows")
    ents = [byte_entropy(rb) for rb in row_bytes]
    med = percentile(sorted(ents), 50)
    flagged = [i for i, e in enumerate(ents) if e < med - drop]
    blocks = []
    if flagged:
        start = prev = flagged[0]
        for i in flagged[1:]:
            if i == prev + 1:
                prev = i
            else:
                blocks.append([start, prev])
                start = prev = i
        blocks.append([start, prev])
    return {
        "ent_med": med,
        "ent_min": min(ents),
        "ent_max": max(ents),
        "n_flagged": len(flagged),
        "flagged_blocks": blocks,
        "flagged_rows": flagged[:64],
    }


def entropy_scan_mad(row_bytes, *, mad_mult: float = 6.0) -> dict:
    """scan2 variant: flag rows deviating from median by > mad_mult * MAD."""
    ents = [byte_entropy(rb) for rb in row_bytes]
    med = percentile(sorted(ents), 50)
    deviations = sorted(abs(e - med) for e in ents)
    mad = percentile(deviations, 50) or 1e-9
    flagged = [i for i, e in enumerate(ents) if abs(e - med) > mad_mult * mad]
    return {"ent_med": med, "mad": mad, "n_flagged": len(flagged),
            "flagged_rows": flagged[:64]}


def magic_scan(data: bytes, *, base_offset: int = 0) -> dict:
    """findcircuits: PFC* magic signatures over raw bytes."""
    found = {}
    pos = 0
    while True:
        i = data.find(b"PFC", pos)
        if i < 0:
            break
        tag = data[i:i + 8]
        if tag in PFC_MAGICS:
            entry = found.setdefault(tag.decode(), {"count": 0, "offsets": []})
            entry["count"] += 1
            if len(entry["offsets"]) < 8:
                entry["offsets"].append(base_offset + i)
        pos = i + 1
    return {"hits": sum(v["count"] for v in found.values()), "tags": found}


# --------------------------------------- anisotropy + norm/frequency (explore)

def anisotropy(rows, *, pairs: int = 4000, seed: int = 7) -> dict:
    """random-pair cosine distribution + mean-vector norm (the cone)."""
    rng = random.Random(seed)
    n = len(rows)
    if n < 8:
        raise WbMetricsError("need >= 8 rows")
    units = [unit(r) for r in rows]
    cosines = []
    for _ in range(pairs):
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b:
            cosines.append(sum(x * y for x, y in zip(units[a], units[b])))
    cosines.sort()
    mu = mean_vec(rows)
    return {
        "random_pair_cos_mean": sum(cosines) / len(cosines),
        "p05": percentile(cosines, 5),
        "p50": percentile(cosines, 50),
        "p95": percentile(cosines, 95),
        "mean_vector_norm": norm(mu),
        "rows": n,
    }


def norm_by_frequency(word_rows: dict) -> list:
    """word_rows: {word: row}. Returns [(word, L2 norm)] in ladder order."""
    return [(w, round(norm(r), 4)) for w, r in word_rows.items() if r]


# ------------------------------------------------------- mechanism (sign/rogue)

def sign_agreement(a, b) -> float:
    d = len(a)
    return sum(1 for k in range(d) if (a[k] >= 0) == (b[k] >= 0)) / d


def sign_cos_pearson(rows, *, pairs: int = 2500, seed: int = 11) -> dict:
    rng = random.Random(seed)
    n = len(rows)
    xs, ys = [], []
    # Each sampled row is fixed for this invocation; retain only its scalar norm.
    norms = {}
    for _ in range(pairs):
        a, b = rng.randrange(n), rng.randrange(n)
        if a == b:
            continue
        ra, rb = rows[a], rows[b]
        xs.append(sign_agreement(ra, rb))
        if a not in norms:
            norms[a] = norm(ra)
        if b not in norms:
            norms[b] = norm(rb)
        na, nb = norms[a], norms[b]
        ys.append(sum(x * y for x, y in zip(ra, rb)) / (na * nb)
                  if na != 0.0 and nb != 0.0 else 0.0)
    m = len(xs)
    mx, my = sum(xs) / m, sum(ys) / m
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / m)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / m)
    r = sum((xs[i] - mx) * (ys[i] - my) for i in range(m)) / m / (sx * sy + 1e-12)
    return {"sign_cos_pearson_r": r, "pairs": m}


def rogue_dims(rows, *, frac: float = 0.01) -> dict:
    """per-dimension variance; the top-frac 'rogue' dims and their share."""
    if not rows:
        raise WbMetricsError("no rows")
    d = len(rows[0])
    mean = mean_vec(rows)
    var = [0.0] * d
    for row in rows:
        for k in range(d):
            diff = row[k] - mean[k]
            var[k] += diff * diff
    var = [v / len(rows) for v in var]
    total = sum(var) or 1e-12
    order = sorted(range(d), key=lambda k: -var[k])
    k = max(1, int(d * frac))
    return {
        "top1_frac_of_var": var[order[0]] / total,
        "top5_frac": sum(var[order[i]] for i in range(min(5, d))) / total,
        "rogue_frac_share": sum(var[order[i]] for i in range(k)) / total,
        "rogue_dim_ids": order[:k],
        "expected_uniform_top5": 5.0 / d,
        "mean_vector": mean,
        "per_dim_var": var,
    }


def sign_only_ratio(antonym_rows, random_rows) -> dict:
    """antonym/random separation with full weights vs sign-only (+-1)."""
    def ratio(rows_a, rows_b, transform):
        opp = [cos(transform(a), transform(b)) for a, b in antonym_rows]
        rnd = [cos(transform(a), transform(b)) for a, b in random_rows]
        mo = sum(opp) / len(opp) if opp else 0.0
        mr = sum(rnd) / len(rnd) if rnd else 1e-12
        return {"opp": mo, "rand": mr, "ratio": mo / mr if mr else 0.0}
    sign = lambda v: [1.0 if x >= 0 else -1.0 for x in v]
    return {
        "full": ratio(antonym_rows, random_rows, unit),
        "sign_only": ratio(antonym_rows, random_rows, sign),
    }


# ------------------------------------------------------- bit-depth ablation

def requantize_row(row, kbits: int):
    """round each value to the nearest of 2^kbits grid points spanning
    +-max|row| (read-time quant; at 1 bit the grid is exactly {-peak, +peak})."""
    if kbits >= 16:
        return list(row)
    levels = 1 << kbits
    peak = max(abs(v) for v in row) or 1.0
    span = 2 * peak
    out = []
    for v in row:
        idx = int(round((v + peak) / span * (levels - 1)))
        idx = max(0, min(levels - 1, idx))
        out.append(-peak + idx * span / (levels - 1))
    return out


def bitdepth_curve(antonym_rows, random_rows, probe_rows: dict,
                   ks=(8, 6, 5, 4, 3, 2, 1)) -> list:
    """antonym/random separation as a function of read-time bit depth."""
    out = []
    for k in ks:
        def rq(v, _k=k):
            return unit(requantize_row(v, _k))
        opp = [cos(rq(a), rq(b)) for a, b in antonym_rows]
        rnd = [cos(rq(a), rq(b)) for a, b in random_rows]
        mo = sum(opp) / len(opp) if opp else 0.0
        mr = sum(rnd) / len(rnd) if rnd else 1e-12
        probes = {name: round(cos(rq(r[0]), rq(r[1])), 4)
                  for name, r in probe_rows.items()}
        out.append({"bits": k, "levels": 1 << k, "opp": mo, "rand": mr,
                    "ratio": mo / mr if mr else 0.0, "probes": probes})
    return out


# ------------------------------------------------------- anisotropy cleanup A/B

def cleanup_ab(antonym_rows, random_rows, sample_rows, *, rogue_frac=0.01) -> dict:
    """raw vs mean-centered + rogue-dim-zeroed separation (fable_clean)."""
    rd = rogue_dims(sample_rows, frac=rogue_frac)
    mean = rd["mean_vector"]
    rogue = set(rd["rogue_dim_ids"])

    def clean(v):
        w = [v[i] - mean[i] for i in range(len(v))]
        for d in rogue:
            w[d] = 0.0
        return unit(w)

    def ratio(transform):
        opp = [cos(transform(a), transform(b)) for a, b in antonym_rows]
        rnd = [cos(transform(a), transform(b)) for a, b in random_rows]
        mo = sum(opp) / len(opp) if opp else 0.0
        mr = sum(rnd) / len(rnd) if rnd else 1e-12
        return {"opp": mo, "rand": mr, "ratio": mo / mr if mr else 0.0}

    return {
        "raw": ratio(unit),
        "cleaned": ratio(clean),
        "mean_offset_norm": norm(mean),
        "rogue_share": rd["rogue_frac_share"],
        "rogue_dims": len(rogue),
    }


# ------------------------------------------- transistors + latches (M.9/M.10)

def circuitry(gate_rows, up_rows, down_cols, *, threshold: float = 0.15,
              sample: int = 36) -> dict:
    """One FFN block as a bank of transistors. gate_rows/up_rows: per-unit row
    vectors; down_cols: per-unit drain vectors (same residual space as gates)."""
    n_ff = len(gate_rows)
    if n_ff == 0 or len(up_rows) != n_ff or len(down_cols) != n_ff:
        raise WbMetricsError("gate/up/down unit counts disagree")
    ga = [norm(g) for g in gate_rows]
    ua = [norm(u) for u in up_rows]
    da = [norm(d) for d in down_cols]
    rho = []
    for j in range(n_ff):
        denom = ga[j] * ua[j] + 1e-8
        rho.append(sum(x * y for x, y in zip(gate_rows[j], up_rows[j])) / denom)
    lam = []
    lam_su = []
    for j in range(n_ff):
        denom_gd = ga[j] * da[j] + 1e-8
        denom_ud = ua[j] * da[j] + 1e-8
        lam.append(sum(x * y for x, y in zip(gate_rows[j], down_cols[j])) / denom_gd)
        lam_su.append(sum(x * y for x, y in zip(up_rows[j], down_cols[j])) / denom_ud)
    infl = [ga[j] * ua[j] * da[j] for j in range(n_ff)]
    conduct = [ga[j] * da[j] for j in range(n_ff)]
    dead_th = max(1e-9, 0.02 * percentile(sorted(conduct), 50))
    dead = [c < dead_th for c in conduct]
    amp = [rho[j] > threshold and not dead[j] for j in range(n_ff)]
    inh = [rho[j] < -threshold and not dead[j] for j in range(n_ff)]
    pas = [not dead[j] and not amp[j] and not inh[j] for j in range(n_ff)]
    energies = sorted((g * g for g in ga), reverse=True)
    top5 = sum(energies[:max(1, n_ff // 20)]) / (sum(energies) + 1e-9)
    order = sorted(range(n_ff), key=lambda j: -infl[j])
    ga_sorted = sorted(ga)
    da_sorted = sorted(da)
    return {
        "n_ff": n_ff,
        "counts": {"amp": sum(amp), "inh": sum(inh),
                   "pass": sum(pas), "dead": sum(dead)},
        "agg": {
            "gate_mean": sum(ga) / n_ff,
            "gate_max": max(ga),
            "drain_mean": sum(da) / n_ff,
            "rho_mean": sum(rho) / n_ff,
            "rho_pos_frac": sum(1 for r in rho if r > 0) / n_ff,
            "top5_gate_energy": top5,
        },
        "logic": {
            "latch_hold": sum(1 for v in lam if v > threshold),
            "latch_reset": sum(1 for v in lam if v < -threshold),
            "lam_mean": sum(lam) / n_ff,
            "lam_su_mean": sum(lam_su) / n_ff,
            "lam_hist": histogram(lam, 24, -1, 1),
        },
        "hist": {
            "gate": histogram(ga, 24, 0, percentile(ga_sorted, 99)),
            "drain": histogram(da, 24, 0, percentile(da_sorted, 99)),
            "rho": histogram(rho, 24, -1, 1),
        },
        "sample": [
            {"j": j, "gate": ga[j], "src": ua[j], "drain": da[j],
             "rho": rho[j], "lam": lam[j], "latch": lam[j] > threshold,
             "infl": infl[j],
             "cls": ("dead" if dead[j] else "amp" if amp[j]
                     else "inh" if inh[j] else "pass")}
            for j in order[:sample]
        ],
    }


def decoder_sharpness(rows, *, sample: int = 512) -> dict:
    """mean |off-diagonal cosine| over a strided row sample (address decoder)."""
    idx = strided(len(rows), sample)
    units = [unit(rows[i]) for i in idx]
    k = len(units)
    if k < 2:
        raise WbMetricsError("need >= 2 rows")
    total = 0.0
    count = 0
    for i in range(k):
        for j in range(i + 1, k):
            total += abs(sum(x * y for x, y in zip(units[i], units[j])))
            count += 1
    return {"decode_orth": total / count, "sampled_rows": k}


# ------------------------------------------------------- attention IPC channels

def ipc_channels(q_head_rows, o_head_cols, *, kv_norm: float | None = None,
                 gqa_group: int = 1) -> dict:
    """per-head read strength ||W_Q_h||, write strength ||W_O_h||, channel product."""
    nh = len(q_head_rows)
    if nh == 0 or len(o_head_cols) != nh:
        raise WbMetricsError("q/o head counts disagree")
    qn = [norm([x for row in q_head_rows[h] for x in row]) for h in range(nh)]
    on = [norm([x for row in o_head_cols[h] for x in row]) for h in range(nh)]
    chan = [qn[h] * on[h] for h in range(nh)]
    order = sorted(range(nh), key=lambda h: -chan[h])
    return {
        "n_head": nh,
        "gqa_group": gqa_group,
        "chan_mean": sum(chan) / nh,
        "chan_max": max(chan),
        "chan_top": order[:2],
        "kv_bus_norm": kv_norm,
        "heads": [{"h": h, "read": qn[h], "write": on[h], "chan": chan[h]}
                  for h in order],
    }


# ------------------------------------------------------- per-expert health (M.7)

def expert_health(expert_samples, *, dead_eps: float = 1e-6) -> dict:
    """expert_samples: {expert_id: [decoded sample values]}. std per expert."""
    rows = []
    dead = 0
    for expert in sorted(expert_samples):
        vals = [v for v in expert_samples[expert] if math.isfinite(v)]
        if not vals:
            rows.append({"expert": expert, "std": 0.0, "dead": True})
            dead += 1
            continue
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        is_dead = std < dead_eps
        dead += is_dead
        rows.append({"expert": expert, "std": std, "dead": bool(is_dead)})
    stds = sorted(r["std"] for r in rows)
    return {
        "experts": len(rows),
        "dead": dead,
        "std_median": percentile(stds, 50),
        "std_min": stds[0],
        "std_max": stds[-1],
        "per_expert": rows,
    }


# ------------------------------------------------------- axis purity + poles

def axis_with_purity(pair_rows, *, place_row=None) -> dict:
    """pair_rows: [(neg_row, pos_row)]. Purity = mean pairwise cos of the
    normalized per-pair directions (is this one axis or noise?)."""
    if len(pair_rows) < 1:
        raise WbMetricsError("need pairs")
    dirs = []
    for neg, pos in pair_rows:
        diff = [p - n for p, n in zip(pos, neg)]
        if norm(diff) > 0:
            dirs.append(unit(diff))
    if not dirs:
        raise WbMetricsError("all pair directions are zero")
    purity = None
    if len(dirs) >= 2:
        n = len(dirs)
        sims = (sum(x * y for x, y in zip(dirs[i], dirs[j]))
                for i in range(n) for j in range(i + 1, n))
        purity = sum(sims) / (n * (n - 1) // 2)
    mean_dir = mean_vec(dirs)
    axis = unit(mean_dir)
    result = {
        "pairs": len(dirs),
        "purity": purity,
        "verdict": ("CLEAN AXIS" if purity is not None and purity > 0.25
                    else "weak / noisy" if purity is not None and purity > 0.1
                    else "single pair" if purity is None else "NOT an axis"),
        "axis_norm_before_unit": norm(mean_dir),
    }
    if place_row is not None:
        result["place_projection"] = sum(x * y for x, y in zip(unit(place_row), axis))
    result["_axis"] = axis
    return result


def pole_readout(axis, vocab_rows: dict, *, k: int = 14) -> dict:
    """vocab_rows: {label: row}. Top-k tokens at each pole of the axis."""
    scored = [(label, sum(x * y for x, y in zip(unit(row), axis)))
              for label, row in vocab_rows.items() if row]
    scored.sort(key=lambda item: -item[1])
    return {
        "pos_pole": scored[:k],
        "neg_pole": [(label, -score) for label, score in scored[-k:][::-1]],
    }


# ------------------------------------------------------- analogy + quant damage

def analogy(a_row, b_row, c_row, candidates: dict, *, project_out: bool = True) -> dict:
    """a:b :: c:? over {label: row}, source directions projected out (3CosAdd)."""
    r = unit([bb - aa + cc for aa, bb, cc in zip(a_row, b_row, c_row)])
    if project_out:
        for source in (a_row, b_row, c_row):
            u = unit(source)
            d = sum(x * y for x, y in zip(r, u))
            r = [r[i] - d * u[i] for i in range(len(r))]
        r = unit(r)
    scored = sorted(
        ((label, sum(x * y for x, y in zip(unit(row), r)))
         for label, row in candidates.items() if row),
        key=lambda item: -item[1],
    )
    return {"ranking": scored, "answer": scored[0][0] if scored else None}


def analogy_battery(word_rows: dict, cats=None) -> dict:
    """word_rows: {word: row}. Per-category and overall analogy accuracy."""
    cats = cats or ANALOGY_CATS
    per_cat = {}
    hits = tot = 0
    for cat, pairs in cats.items():
        pool = {b: word_rows.get(b) for _, b in pairs}
        h = t = 0
        for i, (a, b) in enumerate(pairs):
            sa, sb = pairs[(i + 1) % len(pairs)]
            rows = [word_rows.get(w) for w in (sa, sb, a)]
            if not all(rows):
                continue
            cands = {w: r for w, r in pool.items()
                     if r and w not in (sa, sb, a)}
            if not cands:
                continue
            result = analogy(rows[0], rows[1], rows[2], cands)
            t += 1
            h += result["answer"] == b
        if t:
            per_cat[cat] = {"hits": h, "total": t, "acc": h / t}
            hits += h
            tot += t
    return {"per_category": per_cat,
            "overall": {"hits": hits, "total": tot,
                        "acc": hits / tot if tot else None}}


# ------------------------------------------------------- concept neighbors (M.3)

def concept_neighbors(query_row, vocab_rows: dict, *, k: int = 30,
                      query_word: str = "") -> dict:
    """nearest rows + cross-script fraction + hidden-match partition."""
    q = unit(query_row)
    scored = sorted(
        ((label, sum(x * y for x, y in zip(unit(row), q)))
         for label, row in vocab_rows.items() if row),
        key=lambda item: -item[1],
    )
    latin = lambda t: all(ord(c) < 0x0250 or c in "▁· \t" for c in t)
    neighbors = []
    hidden = []
    cross = 0
    for label, score in scored:
        if label == query_word:
            continue
        is_cross = not latin(label)
        cross += is_cross
        is_hidden = query_word and not (
            query_word.lower() in label.lower()
            or label.lower() in query_word.lower())
        neighbors.append({"token": label, "cos": score,
                          "cross_script": bool(is_cross)})
        if is_hidden:
            hidden.append({"token": label, "cos": score})
        if len(neighbors) >= k:
            break
    return {
        "neighbors": neighbors,
        "cross_script": cross,
        "shown": len(neighbors),
        "hidden_matches": hidden[:12],
    }


# ------------------------------------------------------- neuron monosemanticity

def neuron_cleanliness(neuron_rows, vocab_rows: dict, *, k: int = 5) -> dict:
    """project each neuron direction onto token rows; top-1 cos = cleanliness."""
    vocab_units = [(label, unit(row)) for label, row in vocab_rows.items() if row]
    if not vocab_units:
        raise WbMetricsError("empty vocab")
    # Keep legacy slicing and NaN ordering outside the finite top-k path.
    bounded = type(k) is int and 0 < k < len(vocab_units)
    finite_vocab = bounded and all(
        math.isfinite(value) for _, row in vocab_units for value in row)
    out = []
    for j, nrow in enumerate(neuron_rows):
        u = unit(nrow)
        scores = ((label, sum(map(operator.mul, u, v)))
                  for label, v in vocab_units)
        if finite_vocab and all(math.isfinite(value) for value in u):
            # nsmallest retains encounter order for equal scores, like sorted.
            scored = heapq.nsmallest(k, scores, key=lambda item: -item[1])
        else:
            scored = sorted(scores, key=lambda item: -item[1])[:k]
        out.append({"neuron": j, "top1": scored[0][1],
                    "top": [{"token": t, "cos": s} for t, s in scored]})
    out.sort(key=lambda item: -item["top1"])
    tops = sorted((item["top1"] for item in out), reverse=True)
    return {
        "neurons": len(out),
        "clean_top15": sum(tops[:15]) / min(15, len(tops)),
        "mean_all": sum(tops) / len(tops),
        "cleanest": out[:16],
    }


# ------------------------------------------- manifold + value sanity (direction)

def value_sanity(rows, *, clip: float = 1e4) -> dict:
    insane = []
    for i, row in enumerate(rows):
        finite = [v for v in row if math.isfinite(v)]
        if len(finite) != len(row) or (finite and max(abs(v) for v in finite) > clip):
            insane.append(i)
    return {"insane_rows": insane, "insane_count": len(insane)}


def manifold_residual(rows, *, k: int = 8, sample: int = 192,
                      iterations: int = 12, seed: int = 5) -> dict:
    """off-manifold residual per row via power-iteration top-k directions of a
    robust sample; flag rows beyond median + 8*MAD. Pure-python, bounded."""
    rng = random.Random(seed)
    n = len(rows)
    if n < 16:
        raise WbMetricsError("need >= 16 rows")
    idx = list(range(n)) if n <= sample else sorted(rng.sample(range(n), sample))
    S = [rows[i] for i in idx]
    mu = mean_vec(S)
    Sc = [[v[d] - mu[d] for d in range(len(v))] for v in S]
    d = len(S[0])
    # orthogonal iteration for top-k directions (no numpy, no full Gram)
    basis = []
    vecs = [[rng.gauss(0, 1) for _ in range(d)] for _ in range(k)]
    for _ in range(iterations):
        new_vecs = []
        for v in vecs:
            # covariance application: S^T (S v) without forming S^T S
            coeffs = [sum(x * y for x, y in zip(row, v)) for row in Sc]
            cv = [0.0] * d
            for c, row in zip(coeffs, Sc):
                for dd in range(d):
                    cv[dd] += c * row[dd]
            for b in new_vecs:
                proj = sum(x * y for x, y in zip(cv, b))
                cv = [cv[dd] - proj * b[dd] for dd in range(d)]
            nv = norm(cv)
            if nv > 0:
                cv = [x / nv for x in cv]
            new_vecs.append(cv)
        basis = new_vecs
        vecs = new_vecs
    def residual(row):
        rc = [v - mu[dd] for dd, v in enumerate(row)]
        rn = norm(rc) + 1e-9
        proj = [0.0] * d
        for b in basis:
            c = sum(x * y for x, y in zip(rc, b))
            for dd in range(d):
                proj[dd] += c * b[dd]
        return norm([rc[dd] - proj[dd] for dd in range(d)]) / rn
    sample_res = sorted(residual(row) for row in S)
    med = percentile(sample_res, 50)
    mad = percentile(sorted(abs(r - med) for r in sample_res), 50) or 1e-9
    threshold = med + 8 * mad
    flagged = [i for i, row in enumerate(rows) if residual(row) > threshold]
    return {
        "residual_median": med,
        "residual_mad": mad,
        "threshold": threshold,
        "flagged_rows": flagged[:64],
        "flagged_count": len(flagged),
        "directions": k,
        "sample_rows": len(idx),
    }


# ------------------------------------------------------- category clustering

def category_purity(word_rows: dict, cats=None) -> dict:
    """is each word's nearest neighbor in its own category? (fable_practical)"""
    cats = cats or CATEGORIES
    labels = {w: c for c, ws in cats.items() for w in ws}
    have = [(w, unit(r)) for w, r in word_rows.items()
            if r and w in labels]
    neighbors = [None] * len(have)
    scores = [-2.0] * len(have)
    # Visit each pair once. Candidates still arrive in insertion order for
    # either word, so equal scores retain the same first neighbor.
    for i, (w, vec) in enumerate(have):
        for j in range(i + 1, len(have)):
            x, other = have[j]
            s = sum(a * b for a, b in zip(vec, other))
            if s > scores[i]:
                scores[i], neighbors[i] = s, x
            if s > scores[j]:
                scores[j], neighbors[j] = s, w
    hits = tot = 0
    misses = []
    for (w, _), best, bs in zip(have, neighbors, scores):
        if best is None:
            continue
        tot += 1
        if labels[best] == labels[w]:
            hits += 1
        else:
            misses.append({"word": w, "cat": labels[w],
                           "nearest": best, "nearest_cat": labels[best],
                           "cos": bs})
    return {
        "hits": hits,
        "total": tot,
        "acc": hits / tot if tot else None,
        "misses": sorted(misses, key=lambda m: -m["cos"])[:12],
    }


# ------------------------------------------------------- order recovery (lab3)

def order_recovery(axis, word_rows: dict, truth: list) -> dict:
    """project words onto an axis; fraction of correctly ordered pairs vs truth."""
    rank = {w: i for i, w in enumerate(truth)}
    proj = {w: sum(x * y for x, y in zip(unit(r), axis))
            for w, r in word_rows.items() if r and w in rank}
    got = [w for w, _ in sorted(proj.items(), key=lambda item: item[1])]
    n = len(got)
    pairs = n * (n - 1) // 2
    ok = 0
    if n <= 8:
        # Avoid tree setup for short word lists.
        for i in range(n):
            for j in range(i + 1, n):
                ok += rank[got[i]] < rank[got[j]]
    else:
        # Index only recovered ranks, even when truth positions are sparse.
        positions = {r: i for i, r in
                     enumerate(sorted(rank[w] for w in got), 1)}
        counts = [0] * (n + 1)
        for w in got:
            position = positions[rank[w]]
            previous = position - 1
            while previous:
                ok += counts[previous]
                previous -= previous & -previous
            while position <= n:
                counts[position] += 1
                position += position & -position
    return {
        "order": got,
        "pair_accuracy": ok / pairs if pairs else None,
        "pairs": pairs,
        "projections": proj,
    }


def semantic_walk(start_row, vocab_rows: dict, *, steps: int = 8,
                  start_label: str = "") -> dict:
    """greedy nearest-unvisited-neighbor walk; watch the meaning drift."""
    seen = {start_label}
    path = [start_label or "<start>"]
    cur = unit(start_row)
    # Cache scalar norms lazily without retaining another normalized matrix.
    row_norms = {}
    for _ in range(steps):
        best, bs = None, -2.0
        for label, row in vocab_rows.items():
            if label in seen or not row:
                continue
            row_norm = row_norms.get(label)
            if row_norm is None:
                row_norm = norm(row) or 1.0
                row_norms[label] = row_norm
            s = sum(x * (y / row_norm) for x, y in zip(cur, row))
            if s > bs:
                bs, best = s, label
        if best is None:
            break
        path.append("%s(%+.3f)" % (best, bs))
        seen.add(best)
        cur = unit(vocab_rows[best])
    return {"path": path}


def constellations(vocab_rows: dict, *, threshold: float = 0.18) -> dict:
    """greedy cosine clustering; the groupings the weights actually hold."""
    have = {w: unit(r) for w, r in vocab_rows.items() if r}
    used = set()
    groups = []
    for w, vec in have.items():
        if w in used:
            continue
        grp = [w]
        used.add(w)
        for x, other in have.items():
            if x in used:
                continue
            if sum(a * b for a, b in zip(vec, other)) >= threshold:
                grp.append(x)
                used.add(x)
        groups.append(grp)
    groups.sort(key=len, reverse=True)
    return {"groups": groups, "n_groups": len(groups)}


# ------------------------------------------------------- precision recipe (M.5)

def precision_recipe(tensors: dict) -> dict:
    """tensors: {name: {dtype, bytes}} from an index. Role -> dtype mass."""
    roles = {}
    for name, info in tensors.items():
        role = role_of(name)
        entry = roles.setdefault(role, {})
        dtype = info.get("dtype", "?")
        mass = entry.setdefault(dtype, 0)
        entry[dtype] = mass + (info.get("bytes") or 0)
    return {
        "roles": {
            role: {
                "dtypes": dict(sorted(dtypes.items(), key=lambda kv: -kv[1])),
                "protected": max(dtypes, key=lambda d: _bpw(d)),
                "total_bytes": sum(dtypes.values()),
            }
            for role, dtypes in sorted(roles.items())
        }
    }


def _bpw(dtype: str) -> float:
    table = {"F64": 64, "F32": 32, "BF16": 16, "F16": 16, "Q8_0": 8.5,
             "Q8_1": 8.5, "I64": 64, "I32": 32, "I16": 16, "I8": 8,
             "U8": 8, "Q6_K": 6.5625, "Q5_K": 5.5, "Q5_0": 5.5,
             "Q5_1": 5.5, "Q4_K": 4.5, "Q4_0": 4.5, "Q4_1": 4.5,
             "Q3_K": 3.4375, "Q2_K": 2.625, "F8_E4M3": 8, "F8_E5M2": 8,
             "F8_E8M0": 8, "F4": 4.5, "MXFP4": 4.25}
    return table.get(dtype.upper(), 0.0)


# ------------------------------------------------------- layer depth profile

def depth_profile(layer_stats: dict) -> dict:
    """layer_stats: {layer: {std, zero, ...}} — trend + extremes across depth."""
    if not layer_stats:
        raise WbMetricsError("no layers")
    layers = sorted(layer_stats)
    stds = [layer_stats[l].get("std", 0.0) for l in layers]
    zeros = [layer_stats[l].get("zero", 0.0) for l in layers]
    peak = layers[stds.index(max(stds))]
    floor = layers[stds.index(min(stds))]
    return {
        "layers": layers,
        "std_by_layer": stds,
        "zero_by_layer": zeros,
        "std_peak_layer": peak,
        "std_floor_layer": floor,
        "std_range": max(stds) - min(stds),
    }
