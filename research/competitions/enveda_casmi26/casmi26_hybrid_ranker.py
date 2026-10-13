from __future__ import annotations

import argparse
import bisect
import json
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import numpy as np

PROTON = 1.007276466621
H2O = 18.01056468403
NH4 = 18.033823
NA_ION = 22.989218
K_ION = 38.963158
FORMIC_ACID_MINUS_H = 44.998201
CL_ION = 34.969402

ADDUCT_DELTA: Mapping[str, float] = {
    "[M+H]+": PROTON,
    "[M+NH4]+": NH4,
    "[M-H2O+H]+": PROTON - H2O,
    "[M-2H2O+H]+": PROTON - 2.0 * H2O,
    "[M+Na]+": NA_ION,
    "[M+K]+": K_ION,
    "[M-H]-": -PROTON,
    "[M-H2O-H]-": -(PROTON + H2O),
    "[M+CH2O2-H]-": FORMIC_ACID_MINUS_H,
    "[M+Cl]-": CL_ION,
}


def neutral_mass(precursor_mz: float, adduct: str) -> Optional[float]:
    delta = ADDUCT_DELTA.get(adduct)
    if delta is None or not math.isfinite(float(precursor_mz)):
        return None
    mass = float(precursor_mz) - delta
    return mass if mass > 0 else None


def ppm_error(observed: float, target: float) -> float:
    return 1e6 * (observed - target) / target


def weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    if not values:
        raise ValueError("weighted_median requires values")
    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    total = sum(max(float(w), 0.0) for _, w in pairs)
    if total <= 0:
        return float(np.median([v for v, _ in pairs]))
    half = total * 0.5
    acc = 0.0
    for value, weight in pairs:
        acc += max(float(weight), 0.0)
        if acc >= half:
            return float(value)
    return float(pairs[-1][0])


@dataclass(frozen=True)
class Spectrum:
    molecule_id: str
    spectrum_id: str
    precursor_mz: float
    adduct: str
    mzs: np.ndarray
    intensities: np.ndarray
    base_peak_intensity: Optional[float] = None
    instrument_type: Optional[str] = None

    @property
    def neutral_mass(self) -> Optional[float]:
        return neutral_mass(self.precursor_mz, self.adduct)


@dataclass
class QueryMolecule:
    molecule_id: str
    spectra: List[Spectrum] = field(default_factory=list)
    target_mass: float = math.nan

    def finalize_mass(self) -> None:
        masses: List[float] = []
        weights: List[float] = []
        for s in self.spectra:
            m = s.neutral_mass
            if m is None:
                continue
            masses.append(m)
            bp = s.base_peak_intensity
            weights.append(math.sqrt(bp) if bp is not None and bp > 0 else 1.0)
        if not masses:
            raise ValueError(f"{self.molecule_id}: no supported adducts")
        self.target_mass = weighted_median(masses, weights)


@dataclass(frozen=True)
class PreparedQuery:
    molecule_id: str
    target_mass: float
    vectors: Tuple[Tuple[str, Mapping[int, float]], ...]


@dataclass(frozen=True)
class MassWindowIndex:
    targets: Tuple[Tuple[float, str], ...]
    masses: Tuple[float, ...]
    ppm: float

    @classmethod
    def from_queries(cls, queries: Mapping[str, PreparedQuery], ppm: float) -> "MassWindowIndex":
        targets = tuple(sorted((q.target_mass, qid) for qid, q in queries.items()))
        return cls(targets=targets, masses=tuple(x[0] for x in targets), ppm=ppm)

    def query_ids(self, mass: float) -> Iterator[str]:
        if not self.targets:
            return
        tol = abs(mass) * self.ppm * 1e-6 * 1.02
        lo = bisect.bisect_left(self.masses, mass - tol)
        hi = bisect.bisect_right(self.masses, mass + tol)
        for target, qid in self.targets[lo:hi]:
            if abs(ppm_error(mass, target)) <= self.ppm:
                yield qid


@dataclass(frozen=True)
class LibraryHit:
    query_id: str
    candidate_key: str
    smiles: str
    score: float
    mass_ppm: float
    source_spectrum_id: str


def preprocess_peaks(
    mzs: Sequence[float],
    intensities: Sequence[float],
    *,
    precursor_mz: Optional[float] = None,
    top_k: int = 128,
    intensity_floor: float = 0.01,
) -> Tuple[np.ndarray, np.ndarray]:
    mz = np.asarray(mzs, dtype=np.float32)
    it = np.asarray(intensities, dtype=np.float32)
    if mz.shape != it.shape:
        raise ValueError("m/z and intensity arrays must align")
    valid = np.isfinite(mz) & np.isfinite(it) & (mz > 0) & (it > 0)
    if precursor_mz is not None and math.isfinite(float(precursor_mz)):
        valid &= mz <= float(precursor_mz) + 2.0
    mz, it = mz[valid], it[valid]
    if len(mz) == 0:
        return mz, it
    mx = float(np.max(it))
    if mx > 0:
        it = it / mx
    keep = it >= intensity_floor
    mz, it = mz[keep], it[keep]
    if len(mz) > top_k:
        idx = np.argpartition(it, -top_k)[-top_k:]
        mz, it = mz[idx], it[idx]
    it = np.sqrt(it, dtype=np.float32)
    norm = float(np.linalg.norm(it))
    if norm > 0:
        it = it / norm
    order = np.argsort(mz)
    return mz[order], it[order]


def sparse_binned_vector(
    mzs: np.ndarray,
    intensities: np.ndarray,
    *,
    neutral: Optional[float] = None,
    bin_width: float = 0.02,
    neutral_loss_weight: float = 0.35,
) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for mz, it in zip(mzs, intensities):
        b = int(round(float(mz) / bin_width))
        out[b] = max(out.get(b, 0.0), float(it))
        if neutral is not None and neutral > mz:
            loss = neutral - float(mz)
            lb = 10_000_000 + int(round(loss / bin_width))
            out[lb] = max(out.get(lb, 0.0), float(it) * neutral_loss_weight)
    norm = math.sqrt(sum(v * v for v in out.values()))
    if norm > 0:
        for k in list(out):
            out[k] /= norm
    return out


def sparse_cosine(a: Mapping[int, float], b: Mapping[int, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def group_queries(spectra: Iterable[Spectrum]) -> Dict[str, QueryMolecule]:
    q: Dict[str, QueryMolecule] = {}
    for s in spectra:
        q.setdefault(s.molecule_id, QueryMolecule(s.molecule_id)).spectra.append(s)
    for mol in q.values():
        mol.finalize_mass()
    return q


def prepare_queries(
    queries: Mapping[str, QueryMolecule],
    *,
    bin_width: float = 0.02,
) -> Dict[str, PreparedQuery]:
    prepared: Dict[str, PreparedQuery] = {}
    for qid, query in queries.items():
        vectors: List[Tuple[str, Mapping[int, float]]] = []
        for qs in query.spectra:
            qmz, qit = preprocess_peaks(qs.mzs, qs.intensities, precursor_mz=qs.precursor_mz)
            qv = sparse_binned_vector(qmz, qit, neutral=qs.neutral_mass, bin_width=bin_width)
            vectors.append((qs.adduct, qv))
        prepared[qid] = PreparedQuery(qid, query.target_mass, tuple(vectors))
    return prepared


def score_library_spectrum(
    query: PreparedQuery,
    lib_mzs: Sequence[float],
    lib_intensities: Sequence[float],
    lib_precursor_mz: float,
    lib_adduct: str,
    *,
    bin_width: float = 0.02,
) -> float:
    lm = neutral_mass(lib_precursor_mz, lib_adduct)
    lmz, lit = preprocess_peaks(lib_mzs, lib_intensities, precursor_mz=lib_precursor_mz)
    lv = sparse_binned_vector(lmz, lit, neutral=lm, bin_width=bin_width)
    scores: List[float] = []
    for query_adduct, qv in query.vectors:
        s = sparse_cosine(qv, lv)
        if query_adduct == lib_adduct:
            s *= 1.08
        scores.append(s)
    if not scores:
        return 0.0
    best = max(scores)
    mean = sum(scores) / len(scores)
    return 0.78 * best + 0.22 * mean


def retain_and_score_rows(
    queries: Mapping[str, QueryMolecule],
    train_rows: Iterable[Mapping[str, object]],
    *,
    ppm: float = 15.0,
    max_hits_per_query: int = 4000,
) -> Dict[str, List[LibraryHit]]:
    prepared = prepare_queries(queries)
    mass_index = MassWindowIndex.from_queries(prepared, ppm)
    retained: Dict[str, List[LibraryHit]] = {qid: [] for qid in queries}
    for row in train_rows:
        adduct = str(row.get("adduct") or "")
        try:
            prec = float(row["precursor_mz"])
        except (KeyError, TypeError, ValueError):
            continue
        nm = neutral_mass(prec, adduct)
        if nm is None:
            continue
        qids = tuple(mass_index.query_ids(nm))
        if not qids:
            continue
        key = str(row.get("inchikey14") or row.get("inchikey") or row.get("normalized_smiles") or "")[:14]
        smiles = str(row.get("normalized_smiles") or "")
        if not key or not smiles:
            continue
        mzs = row.get("ms2_mzs")
        ints = row.get("ms2_normalized_intensities")
        if mzs is None or ints is None:
            continue
        sid = str(row.get("spectrum_id") or "train")
        for qid in qids:
            if len(retained[qid]) >= max_hits_per_query:
                continue
            score = score_library_spectrum(prepared[qid], mzs, ints, prec, adduct)
            pe = abs(ppm_error(nm, prepared[qid].target_mass))
            score *= math.exp(-0.5 * (pe / max(ppm / 2.5, 1e-6)) ** 2)
            retained[qid].append(LibraryHit(qid, key, smiles, float(score), float(pe), sid))
    return retained


def collapse_structure_hits(
    hits: Sequence[LibraryHit],
    *,
    top_k: int = 25,
) -> List[Tuple[str, float, str]]:
    by_key: Dict[str, List[LibraryHit]] = {}
    for h in hits:
        by_key.setdefault(h.candidate_key, []).append(h)
    ranked: List[Tuple[str, float, str]] = []
    for key, hs in by_key.items():
        hs = sorted(hs, key=lambda x: x.score, reverse=True)
        best = hs[0].score
        corroboration = sum(h.score for h in hs[1:4])
        score = best + 0.12 * corroboration
        ranked.append((hs[0].smiles, float(score), key))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def make_submission(
    queries: Mapping[str, QueryMolecule],
    hits: Mapping[str, Sequence[LibraryHit]],
) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    for qid in sorted(queries):
        ranked = collapse_structure_hits(hits.get(qid, ()))
        rows.append((qid, ";".join(smiles for smiles, _, _ in ranked)))
    return rows


def synthetic_benchmark(seed: int = 7, n_library: int = 12000, n_queries: int = 80) -> dict:
    rng = np.random.default_rng(seed)
    base_masses = np.sort(rng.uniform(220.0, 470.0, size=n_queries))
    qspecs: List[Spectrum] = []
    fingerprints: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for i, mass in enumerate(base_masses):
        qid = f"q{i:04d}"
        peaks = np.sort(rng.uniform(50, min(mass, 450), size=72)).astype(np.float32)
        ints = rng.random(72).astype(np.float32)
        fingerprints[qid] = (peaks, ints)
        for j in range(3):
            noise = rng.normal(0, 0.006, size=72).astype(np.float32)
            qspecs.append(Spectrum(qid, f"{qid}-{j}", mass + PROTON, "[M+H]+", peaks + noise, ints, 5e4, "timsTOF"))
    queries = group_queries(qspecs)

    rows: List[dict] = []
    for i in range(n_library - n_queries):
        mass = float(rng.uniform(220, 470))
        p = np.sort(rng.uniform(50, min(mass, 450), size=72)).astype(np.float32)
        it = rng.random(72).astype(np.float32)
        rows.append({
            "spectrum_id": f"noise-{i}", "precursor_mz": mass + PROTON,
            "adduct": "[M+H]+", "inchikey14": f"N{i:013d}"[:14],
            "normalized_smiles": f"N{i}", "ms2_mzs": p,
            "ms2_normalized_intensities": it,
        })
    for i, (qid, q) in enumerate(queries.items()):
        p, it = fingerprints[qid]
        rows.append({
            "spectrum_id": f"truth-{i}", "precursor_mz": q.target_mass + PROTON,
            "adduct": "[M+H]+", "inchikey14": f"T{i:013d}"[:14],
            "normalized_smiles": f"TRUTH_{qid}", "ms2_mzs": p,
            "ms2_normalized_intensities": it,
        })
    rng.shuffle(rows)
    t0 = time.perf_counter()
    hits = retain_and_score_rows(queries, rows, ppm=15.0)
    elapsed = time.perf_counter() - t0
    top1 = 0
    retained = 0
    for qid in queries:
        collapsed = collapse_structure_hits(hits[qid])
        retained += len(hits[qid])
        if collapsed and collapsed[0][0] == f"TRUTH_{qid}":
            top1 += 1
    return {
        "library_rows": len(rows),
        "query_molecules": len(queries),
        "retained_spectra": retained,
        "retained_fraction": retained / max(len(rows), 1),
        "top1_synthetic": top1 / max(len(queries), 1),
        "elapsed_seconds": elapsed,
        "rows_per_second": len(rows) / max(elapsed, 1e-9),
    }


def _selftest() -> None:
    neutral = 350.123456
    for adduct, delta in ADDUCT_DELTA.items():
        got = neutral_mass(neutral + delta, adduct)
        assert got is not None and abs(got - neutral) < 1e-7, (adduct, got)
    mz = np.array([100.0, 150.0, 200.0], dtype=np.float32)
    it = np.array([1.0, 0.5, 0.25], dtype=np.float32)
    pmz, pit = preprocess_peaks(mz, it)
    v = sparse_binned_vector(pmz, pit, neutral=300.0)
    assert sparse_cosine(v, v) > 0.999
    v2 = sparse_binned_vector(np.array([80.0, 90.0]), np.array([1.0, 1.0]), neutral=300.0)
    assert sparse_cosine(v, v2) < 0.2
    dummy = {
        "a": PreparedQuery("a", 300.0, ()),
        "b": PreparedQuery("b", 350.0, ()),
    }
    mw = MassWindowIndex.from_queries(dummy, 10.0)
    assert list(mw.query_ids(350.0)) == ["b"]


def main() -> None:
    ap = argparse.ArgumentParser(description="CASMI26 query-conditioned hybrid library ranker core")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--library-rows", type=int, default=12000)
    ap.add_argument("--queries", type=int, default=80)
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        print("selftest: PASS")
    if args.benchmark:
        print(json.dumps(synthetic_benchmark(n_library=args.library_rows, n_queries=args.queries), indent=2))
    if not args.selftest and not args.benchmark:
        ap.print_help()


if __name__ == "__main__":
    main()
