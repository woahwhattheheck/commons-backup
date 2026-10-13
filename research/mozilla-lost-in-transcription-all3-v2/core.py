"""Shared, dependency-free multitrack consensus primitives.

Competition audio/model assets are deliberately absent. Priors may only be built from
explicitly admitted public or authorized-local transcript evidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import unicodedata
from typing import Iterable, Sequence

ALLOWED_EVIDENCE = frozenset({"public", "authorized_local", "synthetic"})
TRACKS = frozenset({"sp-en", "sp-nh", "id-jv"})


def normalize_transcript(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("transcript must be a string")
    text = unicodedata.normalize("NFKC", text).replace("#x27;", "'")
    out: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in {"'", "’"}:
            out.append("'")
        elif ch.isspace():
            out.append(" ")
        elif cat[0] in {"L", "M", "N"}:
            out.append(ch.casefold())
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def tokens(text: str) -> tuple[str, ...]:
    n = normalize_transcript(text)
    return tuple(n.split()) if n else ()


def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j, bj in enumerate(b, 1):
        cur = [j]
        for i, ai in enumerate(a, 1):
            cur.append(min(cur[-1] + 1, prev[i] + 1, prev[i - 1] + (ai != bj)))
        prev = cur
    return prev[-1]


def corpus_wer(predictions: Sequence[str], references: Sequence[str]) -> float:
    if len(predictions) != len(references):
        raise ValueError("predictions and references must have equal length")
    errors = words = 0
    for pred, ref in zip(predictions, references, strict=True):
        pt, rt = tokens(pred), tokens(ref)
        errors += edit_distance(pt, rt)
        words += len(rt)
    if words == 0:
        return 0.0 if errors == 0 else math.inf
    return errors / words


@dataclass(frozen=True)
class TranscriptEvidence:
    track: str
    text: str
    evidence_class: str
    source_id: str

    def validate(self) -> None:
        if self.track not in TRACKS:
            raise ValueError(f"unsupported track: {self.track}")
        if self.evidence_class not in ALLOWED_EVIDENCE:
            raise ValueError(f"inadmissible evidence class: {self.evidence_class}")
        if not self.source_id.strip() or not tokens(self.text):
            raise ValueError("source_id and normalized text must be non-empty")


@dataclass(frozen=True)
class TrackPrior:
    track: str
    alpha: float
    unigrams: dict[str, int]
    bigrams: dict[str, int]
    transcript_count: int
    token_count: int
    evidence_sha256: str

    @classmethod
    def fit(cls, track: str, evidence: Iterable[TranscriptEvidence], *, alpha: float = 0.25) -> "TrackPrior":
        if track not in TRACKS:
            raise ValueError(f"unsupported track: {track}")
        if not math.isfinite(alpha) or alpha <= 0:
            raise ValueError("alpha must be finite and > 0")
        rows: list[TranscriptEvidence] = []
        uni: Counter[str] = Counter()
        bi: Counter[str] = Counter()
        total = 0
        for row in evidence:
            row.validate()
            if row.track != track:
                continue
            rows.append(row)
            seq = ("<s>",) + tokens(row.text) + ("</s>",)
            total += len(seq) - 2
            uni.update(seq[:-1])
            bi.update(f"{a}\t{b}" for a, b in zip(seq, seq[1:]))
        if not rows:
            raise ValueError(f"no admitted transcripts for {track}")
        canonical = [asdict(r) for r in sorted(rows, key=lambda r: (r.source_id, r.text, r.evidence_class))]
        digest = sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(track, alpha, dict(sorted(uni.items())), dict(sorted(bi.items())), len(rows), total, digest)

    def mean_logprob(self, text: str) -> float:
        seq = ("<s>",) + tokens(text) + ("</s>",)
        vocab = max(1, len(self.unigrams) + 1)
        total = 0.0
        steps = 0
        for left, right in zip(seq, seq[1:]):
            num = self.bigrams.get(f"{left}\t{right}", 0) + self.alpha
            den = self.unigrams.get(left, 0) + self.alpha * vocab
            total += math.log(num / den)
            steps += 1
        return total / max(1, steps)


@dataclass(frozen=True)
class Hypothesis:
    text: str
    source: str
    rank: int = 0
    reliability: float = 1.0

    def validate(self) -> None:
        if not self.source.strip() or not tokens(self.text):
            raise ValueError("hypothesis source/text must be non-empty")
        if self.rank < 0:
            raise ValueError("rank must be >= 0")
        if not math.isfinite(self.reliability) or self.reliability <= 0:
            raise ValueError("reliability must be finite and > 0")


@dataclass(frozen=True)
class ConsensusConfig:
    prior_weight: float = 0.08
    disagreement_abstain: float = 0.55
    margin_abstain: float = 0.015
    rank_decay: float = 0.72

    def validate(self) -> None:
        if not (0 <= self.prior_weight <= 1):
            raise ValueError("prior_weight must be in [0,1]")
        if not (0 <= self.disagreement_abstain <= 1):
            raise ValueError("disagreement_abstain must be in [0,1]")
        if self.margin_abstain < 0 or not math.isfinite(self.margin_abstain):
            raise ValueError("margin_abstain must be finite and >= 0")
        if not (0 < self.rank_decay <= 1):
            raise ValueError("rank_decay must be in (0,1]")


@dataclass(frozen=True)
class ConsensusResult:
    track: str
    text: str
    chosen_source: str
    chosen_index: int
    disagreement: float
    score_margin: float
    abstain: bool
    candidate_scores: tuple[float, ...]
    evidence_sha256: str


def choose_consensus(track: str, hypotheses: Sequence[Hypothesis], *, prior: TrackPrior | None = None,
                     config: ConsensusConfig = ConsensusConfig()) -> ConsensusResult:
    if track not in TRACKS:
        raise ValueError(f"unsupported track: {track}")
    config.validate()
    if len(hypotheses) < 2:
        raise ValueError("at least two hypotheses are required")
    for h in hypotheses:
        h.validate()
    if prior is not None and prior.track != track:
        raise ValueError("prior track mismatch")
    seqs = [tokens(h.text) for h in hypotheses]
    weights = [h.reliability * (config.rank_decay ** h.rank) for h in hypotheses]
    total_weight = sum(weights)
    pair = [[0.0] * len(seqs) for _ in seqs]
    for i in range(len(seqs)):
        for j in range(i + 1, len(seqs)):
            d = edit_distance(seqs[i], seqs[j]) / max(1, len(seqs[i]), len(seqs[j]))
            pair[i][j] = pair[j][i] = d
    scores: list[float] = []
    for i, h in enumerate(hypotheses):
        risk = sum(weights[j] * pair[i][j] for j in range(len(seqs))) / total_weight
        prior_cost = -prior.mean_logprob(h.text) if prior else 0.0
        scores.append(risk + config.prior_weight * prior_cost)
    order = sorted(range(len(scores)), key=lambda i: (scores[i], hypotheses[i].rank, i))
    winner = order[0]
    margin = scores[order[1]] - scores[winner]
    disagreement = sum(weights[j] * pair[winner][j] for j in range(len(seqs))) / total_weight
    abstain = disagreement > config.disagreement_abstain or margin < config.margin_abstain
    evidence = {
        "track": track,
        "config": asdict(config),
        "hypotheses": [asdict(h) for h in hypotheses],
        "normalized": [" ".join(s) for s in seqs],
        "scores": scores,
        "winner": winner,
        "prior_evidence_sha256": prior.evidence_sha256 if prior else "",
    }
    digest = sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ConsensusResult(track, hypotheses[winner].text, hypotheses[winner].source, winner,
                           disagreement, margin, abstain, tuple(scores), digest)


def canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
