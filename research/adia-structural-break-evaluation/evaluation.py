"""Complete-trace evaluation for causal structural-break detectors.

Metric semantics are pinned to Crunch's public scorer, not to a leaderboard run.
No I/O or detector execution occurs in this module. Bootstrap requires NumPy.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable, Sequence

SCHEMA = "adia-evaluation-v1"
SCORER = {
    "repository": "crunchdao/competitions",
    "commit": "5a24c2413122942eae97b6bad376ef0ec143ce22",
    "path": "competitions/structural-break-real-time/scoring/scoring.py",
    "git_blob": "708a6433fc7275bbda7093c242abd41ee67e73f3",
}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value or len(value) > 160:
        raise ValueError(f"{name}: expected nonempty bounded string")
    if any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise ValueError(f"{name}: expected printable ASCII")
    return value


def _sha(value: object) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected lowercase SHA-256")
    return value


def _integer(value: object, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name}: expected integer in [{lo}, {hi}]")
    return value


@dataclass(frozen=True)
class Trace:
    case_id: str
    cluster: int
    scenario: str
    case_sha256: str
    break_index: int | None
    scores: tuple[float, ...]

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _text(self.scenario, "scenario")
        _integer(self.cluster, "cluster", 0, 2**63 - 1)
        _sha(self.case_sha256)
        if type(self.scores) is not tuple or not 1 <= len(self.scores) <= 10000:
            raise ValueError("scores: expected tuple of 1..10000 complete online scores")
        if self.break_index is not None:
            _integer(self.break_index, "break_index", 0, len(self.scores) - 1)
        for score in self.scores:
            if type(score) not in (int, float) or not 0 <= score <= 1 or not math.isfinite(score):
                raise ValueError("scores must be finite real values in [0,1], not booleans")

    def label(self, time: int) -> int:
        return int(self.break_index is not None and time >= self.break_index)

    def identity(self) -> tuple:
        return (self.case_id, self.cluster, self.scenario, self.case_sha256,
                self.break_index, len(self.scores))

    def record(self) -> dict:
        return {"case_id": self.case_id, "cluster": self.cluster,
                "scenario": self.scenario, "case_sha256": self.case_sha256,
                "break_index": self.break_index, "scores": list(self.scores)}

    @classmethod
    def from_record(cls, record: dict) -> Trace:
        keys = {"case_id", "cluster", "scenario", "case_sha256", "break_index", "scores"}
        if type(record) is not dict or set(record) != keys or type(record["scores"]) is not list:
            raise ValueError("trace must have exactly the documented fields")
        return cls(**{**record, "scores": tuple(record["scores"])})


def validate(traces: Iterable[Trace]) -> tuple[Trace, ...]:
    result = tuple(traces)
    if not result or len(result) > 100000 or any(type(t) is not Trace for t in result):
        raise ValueError("expected 1..100000 Trace objects")
    if len({t.case_id for t in result}) != len(result):
        raise ValueError("duplicate case_id, even when its scores agree")
    return tuple(sorted(result, key=lambda t: t.case_id))


def _components(rows: Sequence[tuple[int, float]]) -> tuple[float, int]:
    """Pairwise concordance via tied ranks; O(n log n), half credit for ties."""
    ordered = sorted(rows, key=lambda row: row[1])
    positives = sum(label for label, _ in rows)
    negatives = len(rows) - positives
    if not positives or not negatives:
        return 0.0, 0
    wins, negatives_before, i = 0.0, 0, 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:
            j += 1
        p = sum(label for label, _ in ordered[i:j])
        n = j - i - p
        wins += p * (negatives_before + 0.5 * n)
        negatives_before += n
        i = j
    return wins, positives * negatives


def ts_auc(traces: Iterable[Trace]) -> dict:
    """Weight each online-time AUC by n_positive*n_negative, as upstream does.

    Step is position in each complete online trace, not global historical time.
    Single-class steps contribute zero weight. Entirely degenerate panels get
    0.5 AND an explicit no-comparable-pairs flag; they are not evidence of quality.
    """
    items = validate(traces)
    steps: dict[int, list] = defaultdict(list)
    for trace in items:
        for time, score in enumerate(trace.scores):
            steps[time].append((trace.label(time), score))
    wins, pairs, used = 0.0, 0, 0
    for rows in steps.values():
        numerator, denominator = _components(rows)
        wins += numerator
        pairs += denominator
        used += int(denominator > 0)
    return {"ts_auc": wins / pairs if pairs else 0.5,
            "concordance": wins, "comparable_pairs": pairs,
            "scored_steps": used, "skipped_steps": len(steps) - used,
            "no_comparable_pairs": pairs == 0, "series": len(items)}


def diagnostics(traces: Iterable[Trace], threshold: float = 0.5) -> dict:
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("threshold must lie strictly between zero and one")
    groups: dict[str, list] = defaultdict(list)
    for trace in validate(traces):
        groups[trace.scenario].append(trace)
    result = {}
    for scenario, items in sorted(groups.items()):
        nulls = [t for t in items if t.break_index is None]
        changed = [t for t in items if t.break_index is not None]
        delays = []
        early = 0
        for trace in changed:
            tau = trace.break_index
            early += int(any(s >= threshold for s in trace.scores[:tau]))
            delay = next((i for i, s in enumerate(trace.scores[tau:]) if s >= threshold), None)
            if delay is not None:
                delays.append(delay)
        ordered = sorted(delays)
        median = None if not ordered else (ordered[(len(ordered)-1)//2] + ordered[len(ordered)//2]) / 2
        result[scenario] = {
            "series": len(items), "null_series": len(nulls),
            "null_false_alarms": sum(any(s >= threshold for s in t.scores) for t in nulls),
            "changed_series": len(changed), "prebreak_false_alarms": early,
            "postbreak_hits": len(delays), "postbreak_delay_median": median,
            "delay_is_conditional_on_hit": True,
        }
    return result


def matched(left: Iterable[Trace], right: Iterable[Trace]) -> tuple[tuple[Trace, ...], tuple[Trace, ...]]:
    a, b = validate(left), validate(right)
    if tuple(t.identity() for t in a) != tuple(t.identity() for t in b):
        raise ValueError("panels differ: case IDs, source bytes, clusters, scenarios, labels, or lengths")
    return a, b


def paired_bootstrap(left: Iterable[Trace], right: Iterable[Trace], *,
                     replicates: int = 500, seed: int = 1729) -> dict:
    """Resample entire matched seed/scenario clusters, never individual points.

    Pair kernels count cross-series comparisons by the clusters of the positive
    and negative traces. Applying the same multinomial weights to both kernels
    is exactly the TS-AUC of a panel with those whole clusters duplicated.
    """
    import numpy as np

    a, b = matched(left, right)
    _integer(replicates, "replicates", 1, 10000)
    _integer(seed, "seed", 0, 2**63 - 1)
    clusters = sorted({t.cluster for t in a})
    if len(clusters) < 2:
        raise ValueError("bootstrap requires at least two independent clusters")
    if len(clusters) > 512 or len(a) > 10000:
        raise ValueError("bootstrap supports at most 512 clusters and 10000 series")
    indices = {c: i for i, c in enumerate(clusters)}
    size = len(clusters)
    denominators = np.zeros((size, size), dtype=np.float64)
    numerators = [np.zeros_like(denominators), np.zeros_like(denominators)]
    for time in range(max(len(t.scores) for t in a)):
        pos = [i for i, t in enumerate(a) if time < len(t.scores) and t.label(time)]
        neg = [i for i, t in enumerate(a) if time < len(t.scores) and not t.label(time)]
        if not pos or not neg:
            continue
        pi = np.array([indices[a[i].cluster] for i in pos])
        ni = np.array([indices[a[i].cluster] for i in neg])
        # Bound temporary pair matrices; never materialize all series squared.
        for start in range(0, len(pos), 64):
            chunk = pos[start:start + 64]
            ci = pi[start:start + 64]
            np.add.at(denominators, (ci[:, None], ni[None, :]), 1.0)
            for panel, kernel in zip((a, b), numerators):
                ps = np.array([panel[i].scores[time] for i in chunk])[:, None]
                ns = np.array([panel[i].scores[time] for i in neg])[None, :]
                credit = (ps > ns).astype(np.float64) + 0.5 * (ps == ns)
                np.add.at(kernel, (ci[:, None], ni[None, :]), credit)
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(size, [1 / size] * size, size=replicates).astype(np.float64)
    den = np.einsum("bi,ij,bj->b", weights, denominators, weights)
    values = []
    for kernel in numerators:
        num = np.einsum("bi,ij,bj->b", weights, kernel, weights)
        values.append(np.divide(num, den, out=np.full(replicates, 0.5), where=den > 0))
    differences = values[1] - values[0]
    return {"method": "paired_percentile_bootstrap_whole_seed_clusters",
            "clusters": size, "replicates": replicates, "seed": seed,
            "candidate_minus_reference": ts_auc(b)["ts_auc"] - ts_auc(a)["ts_auc"],
            "ci95": np.quantile(differences, [0.025, 0.975]).tolist(),
            "degenerate_replicates": int((den == 0).sum()),
            "numpy_version": np.__version__}


def complete(traces: Iterable[Trace], case_manifest: Sequence[dict]) -> tuple[tuple[Trace, ...], list[dict]]:
    """Require every expected case, its truth/source identity, and every step."""
    items = validate(traces)
    keys = {"case_id", "cluster", "scenario", "case_sha256", "break_index", "online_length"}
    if type(case_manifest) not in (list, tuple) or any(type(r) is not dict or set(r) != keys for r in case_manifest):
        raise ValueError("invalid case manifest")
    if len(case_manifest) != len(items):
        raise ValueError("missing or additional cases")
    manifest = sorted(case_manifest, key=lambda r: r["case_id"])
    actual = [{"case_id": t.case_id, "cluster": t.cluster, "scenario": t.scenario,
               "case_sha256": t.case_sha256, "break_index": t.break_index,
               "online_length": len(t.scores)} for t in items]
    # Canonical equality distinguishes bool/int and other Python equality aliases.
    if canonical(actual) != canonical(manifest):
        raise ValueError("trace does not match the complete expected corpus manifest")
    return items, manifest


def report(traces: Iterable[Trace], *, candidate_sha256: str, case_manifest: Sequence[dict]) -> dict:
    items, manifest = complete(traces, case_manifest)
    _sha(candidate_sha256)
    corpus_sha256 = digest(manifest)
    payload = {"schema": SCHEMA, "evidence_class": "LOCAL_SYNTHETIC_DIAGNOSTIC",
               "organizer_score": False, "provider_submission": False,
               "scorer_source": dict(SCORER), "candidate_sha256": candidate_sha256,
               "corpus_sha256": corpus_sha256,
               "trace_sha256": digest([t.record() for t in items]),
               "metric": ts_auc(items), "diagnostics": diagnostics(items)}
    return {**payload, "report_sha256": digest(payload)}


def verify_report(value: dict, traces: Iterable[Trace], *,
                  candidate_sha256: str, case_manifest: Sequence[dict]) -> bool:
    """Recompute from the supplied complete traces, not a self-hash alone.

    The caller retains the corpus and source identity; this is reproducibility
    validation, not cryptographic proof that an arbitrary detector was executed.
    """
    try:
        expected = report(traces, candidate_sha256=candidate_sha256, case_manifest=case_manifest)
        return canonical(value) == canonical(expected)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return False
