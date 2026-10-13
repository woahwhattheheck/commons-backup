"""Offline consensus and scoring primitives for Mozilla Lost in Transcription.

The module is deliberately dependency-free so its correctness can be exercised outside
of the competition image. Production ASR adapters live in submission_main.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

_BRACKETED = re.compile(r"\[[^\]]+\]")
_UNINTELLIGIBLE = re.compile(r"\(\?+\)")
_WORD_PAREN = re.compile(r"\(([^()]*)\)")
_OTHER_PUNCT = re.compile(r'[¿¡";:]+')
_COMMA = re.compile(r",+")
_SENTENCE_INITIAL = re.compile(r"(^\s*|[.!?—]\s*)([^\W\d_])([^\W\d_]?)")
_SENTENCE_END = re.compile(r"[!?]+")
_MULTISPACE = re.compile(r"  +")


def _sentence_initial(match: re.Match[str]) -> str:
    delimiter, first, second = match.group(1), match.group(2), match.group(3)
    if first.isupper() and not (second and second.isupper()):
        first = first.lower()
    return delimiter + first + second


def normalize_for_score(text: str) -> str:
    """Mirror the organizer's scoring normalization without external packages."""
    if not isinstance(text, str):
        raise TypeError("transcript must be a string")
    text = text.replace("~", "")
    text = _BRACKETED.sub(" ", text)
    text = _UNINTELLIGIBLE.sub(" ", text)
    text = _WORD_PAREN.sub(r"\1", text)
    text = text.replace("#x27;", "'")
    text = _OTHER_PUNCT.sub(" ", text)
    text = _SENTENCE_INITIAL.sub(_sentence_initial, text)
    text = text.replace("—", ", ")
    text = _COMMA.sub(" ", text)
    text = _SENTENCE_END.sub(" ", text)
    sentinel = "\x00ELLIPSIS\x00"
    text = text.replace("...", sentinel).replace(".", " ").replace(sentinel, "...")
    while " ... " in text:
        text = text.replace(" ... ", " ")
    return _MULTISPACE.sub(" ", text)


def tokens(text: str) -> tuple[str, ...]:
    return tuple(normalize_for_score(text).strip().split())


def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    """Unit-cost Levenshtein distance with O(min(n,m)) memory."""
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
    """Corpus WER using the competition normalization contract."""
    if len(predictions) != len(references):
        raise ValueError("predictions and references must have equal length")
    errors = 0
    ref_words = 0
    for pred, ref in zip(predictions, references, strict=True):
        pt = tokens(pred)
        rt = tokens(ref)
        errors += edit_distance(pt, rt)
        ref_words += len(rt)
    if ref_words == 0:
        return 0.0 if errors == 0 else math.inf
    return errors / ref_words


@dataclass(frozen=True)
class Hypothesis:
    text: str
    source: str
    acoustic_logprob: float = 0.0
    reliability: float = 1.0

    def validate(self) -> None:
        if not self.source or not self.source.strip():
            raise ValueError("hypothesis source must be non-empty")
        if not self.text.strip():
            raise ValueError("hypothesis text must be non-empty")
        if not math.isfinite(self.acoustic_logprob):
            raise ValueError("acoustic_logprob must be finite")
        if not math.isfinite(self.reliability) or self.reliability <= 0:
            raise ValueError("reliability must be finite and > 0")


@dataclass(frozen=True)
class NgramPrior:
    """Laplace-smoothed bilingual token prior learned from admitted local text only."""

    order: int
    alpha: float
    unigrams: dict[str, int]
    bigrams: dict[str, int]
    transcript_count: int
    token_count: int
    source_sha256: str

    @classmethod
    def fit(cls, transcripts: Iterable[str], *, alpha: float = 0.25, source_sha256: str = "") -> "NgramPrior":
        if not math.isfinite(alpha) or alpha <= 0:
            raise ValueError("alpha must be finite and > 0")
        uni: Counter[str] = Counter()
        bi: Counter[str] = Counter()
        count = 0
        total = 0
        for text in transcripts:
            seq = ("<s>",) + tokens(text) + ("</s>",)
            if len(seq) <= 2:
                continue
            count += 1
            total += len(seq) - 2
            uni.update(seq[:-1])
            bi.update(f"{a}\t{b}" for a, b in zip(seq, seq[1:]))
        if count == 0:
            raise ValueError("at least one non-empty transcript is required")
        return cls(2, alpha, dict(sorted(uni.items())), dict(sorted(bi.items())), count, total, source_sha256)

    def mean_logprob(self, text: str) -> float:
        seq = ("<s>",) + tokens(text) + ("</s>",)
        vocab = max(1, len(self.unigrams) + 1)
        total = 0.0
        transitions = 0
        for left, right in zip(seq, seq[1:]):
            numerator = self.bigrams.get(f"{left}\t{right}", 0) + self.alpha
            denominator = self.unigrams.get(left, 0) + self.alpha * vocab
            total += math.log(numerator / denominator)
            transitions += 1
        return total / max(1, transitions)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"

    @classmethod
    def from_json(cls, payload: str) -> "NgramPrior":
        raw = json.loads(payload)
        obj = cls(**raw)
        if obj.order != 2 or obj.alpha <= 0 or obj.transcript_count <= 0 or obj.token_count < 0:
            raise ValueError("invalid prior payload")
        return obj


@dataclass(frozen=True)
class ConsensusConfig:
    acoustic_weight: float = 0.20
    prior_weight: float = 0.08
    disagreement_abstain: float = 0.55
    margin_abstain: float = 0.015

    def validate(self) -> None:
        vals = (self.acoustic_weight, self.prior_weight, self.disagreement_abstain, self.margin_abstain)
        if not all(math.isfinite(x) and x >= 0 for x in vals):
            raise ValueError("consensus config values must be finite and nonnegative")


@dataclass(frozen=True)
class ConsensusResult:
    text: str
    chosen_source: str
    chosen_index: int
    disagreement: float
    score_margin: float
    abstain: bool
    candidate_scores: tuple[float, ...]
    evidence_sha256: str


def _quality_weight(h: Hypothesis) -> float:
    n = max(1, len(tokens(h.text)))
    mean_lp = max(-12.0, min(0.0, h.acoustic_logprob / n))
    return h.reliability * math.exp(mean_lp)


def choose_consensus(
    hypotheses: Sequence[Hypothesis],
    *,
    prior: NgramPrior | None = None,
    config: ConsensusConfig = ConsensusConfig(),
) -> ConsensusResult:
    """Weighted minimum-Bayes-risk selection over complete ASR hypotheses."""
    config.validate()
    if len(hypotheses) < 2:
        raise ValueError("at least two independent hypotheses are required")
    for h in hypotheses:
        h.validate()
    seqs = [tokens(h.text) for h in hypotheses]
    if any(not seq for seq in seqs):
        raise ValueError("normalized hypotheses must not be empty")
    weights = [_quality_weight(h) for h in hypotheses]
    total_weight = sum(weights)
    if total_weight <= 0 or not math.isfinite(total_weight):
        raise ValueError("invalid aggregate hypothesis weight")

    pair_dist: list[list[float]] = [[0.0] * len(seqs) for _ in seqs]
    for i in range(len(seqs)):
        for j in range(i + 1, len(seqs)):
            denom = max(1, len(seqs[i]), len(seqs[j]))
            d = edit_distance(seqs[i], seqs[j]) / denom
            pair_dist[i][j] = pair_dist[j][i] = d

    scores: list[float] = []
    for i, hyp in enumerate(hypotheses):
        risk = sum(weights[j] * pair_dist[i][j] for j in range(len(seqs))) / total_weight
        n = max(1, len(seqs[i]))
        acoustic_cost = -max(-12.0, min(0.0, hyp.acoustic_logprob / n))
        prior_cost = -prior.mean_logprob(hyp.text) if prior is not None else 0.0
        scores.append(risk + config.acoustic_weight * acoustic_cost + config.prior_weight * prior_cost)

    order = sorted(range(len(scores)), key=lambda idx: (scores[idx], idx))
    winner = order[0]
    margin = scores[order[1]] - scores[winner]
    disagreement = sum(weights[j] * pair_dist[winner][j] for j in range(len(seqs))) / total_weight
    abstain = disagreement > config.disagreement_abstain or margin < config.margin_abstain

    evidence = {
        "config": asdict(config),
        "hypotheses": [asdict(h) for h in hypotheses],
        "normalized": [" ".join(s) for s in seqs],
        "scores": scores,
        "winner": winner,
        "prior_source_sha256": prior.source_sha256 if prior else "",
    }
    digest = sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ConsensusResult(
        text=hypotheses[winner].text,
        chosen_source=hypotheses[winner].source,
        chosen_index=winner,
        disagreement=disagreement,
        score_margin=margin,
        abstain=abstain,
        candidate_scores=tuple(scores),
        evidence_sha256=digest,
    )


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
