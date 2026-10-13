"""Small stdlib scorer compatible with the published competition normalization."""

from __future__ import annotations

import re
from collections.abc import Iterable

_BRACKETED = re.compile(r"\[[^\]]+\]")
_UNINTELLIGIBLE = re.compile(r"\(\?+\)")
_PAREN_CONTENT = re.compile(r"\(([^()]*)\)")
_OTHER_PUNCT = re.compile(r'[¿¡";:]+')
_COMMAS = re.compile(r",+")
_SENTENCE_INITIAL = re.compile(r"(^\s*|[.!?—]\s*)([^\W\d_])([^\W\d_]?)")
_SENTENCE_END = re.compile(r"[!?]+")
_MULTISPACE = re.compile(r"  +")


def _lower_initial(match: re.Match[str]) -> str:
    delimiter, first, second = match.group(1), match.group(2), match.group(3)
    if first.isupper() and not (second and second.isupper()):
        first = first.lower()
    return delimiter + first + second


def normalize_text(text: str) -> str:
    """Apply the public scorer's transcript normalization semantics."""
    text = str(text).replace("~", "")
    text = _BRACKETED.sub(" ", text)
    text = _UNINTELLIGIBLE.sub(" ", text)
    text = _PAREN_CONTENT.sub(r"\1", text)
    text = text.replace("#x27;", "'")
    text = _OTHER_PUNCT.sub(" ", text)
    text = _SENTENCE_INITIAL.sub(_lower_initial, text)
    text = text.replace("—", ", ")
    text = _COMMAS.sub(" ", text)
    text = _SENTENCE_END.sub(" ", text)
    sentinel = "\u0000ELLIPSIS\u0000"
    text = text.replace("...", sentinel).replace(".", " ").replace(sentinel, "...")
    while " ... " in text:
        text = text.replace(" ... ", " ")
    text = _MULTISPACE.sub(" ", text)
    return text


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, start=1):
        current = [i]
        for j, hyp_word in enumerate(hypothesis, start=1):
            substitution = previous[j - 1] + (ref_word != hyp_word)
            deletion = previous[j] + 1
            insertion = current[j - 1] + 1
            current.append(min(substitution, deletion, insertion))
        previous = current
    return previous[-1]


def corpus_wer(references: Iterable[str], hypotheses: Iterable[str]) -> float:
    """Compute corpus WER after competition-compatible normalization."""
    refs = list(references)
    hyps = list(hypotheses)
    if len(refs) != len(hyps):
        raise ValueError("references and hypotheses must have equal length")

    total_edits = 0
    total_words = 0
    for reference, hypothesis in zip(refs, hyps, strict=True):
        ref_words = normalize_text(reference).split()
        hyp_words = normalize_text(hypothesis).split()
        total_edits += _edit_distance(ref_words, hyp_words)
        total_words += len(ref_words)

    if total_words == 0:
        return 0.0 if total_edits == 0 else float("inf")
    return total_edits / total_words
