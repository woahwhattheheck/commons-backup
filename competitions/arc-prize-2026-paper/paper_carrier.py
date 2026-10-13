from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

SCHEMA = "arc-paper-readiness/v1"
CONSERVATIVE_DEADLINE_UTC = "2026-11-08T23:59:00Z"
ALLOWED_TRACKS = {"ARC-AGI-2", "ARC-AGI-3"}
PINNED_UPSTREAM = {
    "ARC-AGI-3-SAGE": "27613819b157f34907cdfe2d835aa25958fd9a30",
    "ARC-AGI-3-frontier-v2": "accb281bf95acd9a43a97cd5f68738e7095d9fe0",
    "ARC-AGI-2-symbolic": "f7ed68d9c631fa8953f273f05651a0461b92ca22",
}
OFFICIAL_DEADLINE_SOURCES = {
    "kaggle": "https://www.kaggle.com/competitions/arc-prize-2026-paper-track/overview",
    "arc_prize": "https://arcprize.org/competitions/2026",
}
FORBIDDEN_RESULT_LABELS = {
    "winner",
    "finalist",
    "prize_won",
    "award_won",
    "paid",
    "cash_received",
    "revenue_recognized",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def markdown_word_count(text: str) -> int:
    # Deliberately conservative: count words in URLs/code too. If this passes,
    # the rendered prose count cannot be larger because of Markdown stripping.
    return len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))


def validate_paper_text(text: str) -> dict[str, Any]:
    count = markdown_word_count(text)
    required = [
        "Abstract",
        "Motivation and Prior Work",
        "Method",
        "Why It Works",
        "Results",
        "Limitations",
        "Reproducibility",
    ]
    missing = [heading for heading in required if f"## {heading}" not in text]
    return {
        "word_count_conservative": count,
        "word_limit": 1500,
        "word_limit_ok": count <= 1500,
        "missing_sections": missing,
        "structure_ok": not missing,
        "paper_sha256": sha256_hex(text),
    }


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _https_public_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.username is None and parsed.password is None


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _safe_score(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0


def validate_experiment_results(results: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if results.get("evidence_scope") != "LOCAL_SYNTHETIC_MECHANISM_ONLY":
        reasons.append("EXPERIMENT_SCOPE_NOT_LOCAL_SYNTHETIC")
    if results.get("claims_kaggle_accuracy") is not False:
        reasons.append("EXPERIMENT_KAGGLE_ACCURACY_OVERREACH")
    variants = results.get("variants")
    if not isinstance(variants, list):
        reasons.append("EXPERIMENT_ABLATIONS_INCOMPLETE")
        variants = []
    elif len(variants) < 4:
        reasons.append("EXPERIMENT_ABLATIONS_INCOMPLETE")
    names = {row.get("name") for row in variants if isinstance(row, dict)}
    required = {"full", "no_skill_reuse", "no_model_update", "no_information_gain"}
    if not required.issubset(names):
        reasons.append("EXPERIMENT_REQUIRED_ABLATIONS_MISSING")
    for row in variants:
        if not isinstance(row, dict):
            reasons.append("EXPERIMENT_VARIANT_INVALID")
            continue
        for key in ("mean_actions", "p95_actions", "success_rate"):
            value = row.get(key)
            if type(value) not in (int, float) or not math.isfinite(float(value)) or float(value) < 0:
                reasons.append(f"EXPERIMENT_METRIC_INVALID:{row.get('name')}:{key}")
    return sorted(set(reasons))


def compile_readiness(
    evidence: dict[str, Any],
    *,
    paper_text: str,
    experiment_results: dict[str, Any],
    now_utc: str,
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise TypeError("evidence must be an object")
    now = _parse_utc(now_utc)
    if now is None:
        raise ValueError("now_utc must be an offset-aware ISO timestamp")

    reasons: list[str] = []
    paper = validate_paper_text(paper_text)
    if not paper["word_limit_ok"]:
        reasons.append("PAPER_WORD_LIMIT_EXCEEDED")
    if not paper["structure_ok"]:
        reasons.append("PAPER_REQUIRED_SECTIONS_MISSING")

    reasons.extend(validate_experiment_results(experiment_results))

    upstream = evidence.get("upstream")
    if not isinstance(upstream, dict):
        reasons.append("UPSTREAM_PROVENANCE_MISSING")
    else:
        for name in ("ARC-AGI-3-SAGE", "ARC-AGI-2-symbolic"):
            if upstream.get(name) != PINNED_UPSTREAM[name]:
                reasons.append(f"UPSTREAM_PIN_MISMATCH:{name}")

    track = evidence.get("kaggle_track")
    if track not in ALLOWED_TRACKS:
        reasons.append("KAGGLE_TRACK_MISSING_OR_INVALID")

    submission_id = evidence.get("kaggle_submission_id")
    if not isinstance(submission_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{4,160}", submission_id):
        reasons.append("KAGGLE_SUBMISSION_ID_MISSING")

    notebook_url = evidence.get("public_notebook_url")
    if not _https_public_url(notebook_url):
        reasons.append("PUBLIC_NOTEBOOK_URL_MISSING")

    score = evidence.get("leaderboard_score")
    if not _safe_score(score):
        reasons.append("LEADERBOARD_SCORE_MISSING_OR_INVALID")

    cover_sha = evidence.get("cover_asset_sha256")
    if not _is_sha256(cover_sha):
        reasons.append("COVER_MEDIA_EVIDENCE_MISSING")

    provider = evidence.get("provider_deadline")
    if not isinstance(provider, dict):
        reasons.append("PROVIDER_DEADLINE_RECONCILIATION_MISSING")
    else:
        if provider.get("reconciled") is not True:
            reasons.append("PROVIDER_DEADLINE_UNRECONCILED")
        observed = provider.get("source_urls")
        if not isinstance(observed, list) or set(observed) != set(OFFICIAL_DEADLINE_SOURCES.values()):
            reasons.append("PROVIDER_DEADLINE_SOURCE_SET_MISMATCH")
        effective = _parse_utc(provider.get("effective_deadline_utc"))
        conservative = _parse_utc(CONSERVATIVE_DEADLINE_UTC)
        if effective is None:
            reasons.append("PROVIDER_EFFECTIVE_DEADLINE_INVALID")
        elif conservative is not None and effective > conservative:
            reasons.append("PROVIDER_DEADLINE_WEAKER_THAN_CONSERVATIVE_FENCE")
        verified_at = _parse_utc(provider.get("verified_at_utc"))
        if verified_at is None or verified_at > now:
            reasons.append("PROVIDER_DEADLINE_VERIFICATION_TIME_INVALID")

    forbidden = [key for key in FORBIDDEN_RESULT_LABELS if evidence.get(key) not in (None, False)]
    if forbidden:
        reasons.append("FORBIDDEN_RESULT_AUTHORITY:" + ",".join(sorted(forbidden)))

    disposition = "READY_FOR_OWNER_KAGGLE_SUBMISSION_REVIEW" if not reasons else "HOLD"
    authority = {
        "kaggle_rules_accepted": False,
        "kaggle_submission_performed": False,
        "leaderboard_result_provider_attested": not reasons and _safe_score(score),
        "award_attested": False,
        "payment_attested": False,
        "revenue_recognized": False,
        "external_mutation_authorized": False,
    }
    payload = {
        "schema": SCHEMA,
        "disposition": disposition,
        "reasons": sorted(set(reasons)),
        "paper": paper,
        "experiment_sha256": sha256_hex(canonical_json(experiment_results)),
        "evidence_sha256": sha256_hex(canonical_json(evidence)),
        "evaluated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "conservative_deadline_utc": CONSERVATIVE_DEADLINE_UTC,
        "authority": authority,
    }
    payload["receipt_sha256"] = sha256_hex(canonical_json(payload))
    return payload


def load_json_strict(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    def hook(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    parsed = json.loads(text, object_pairs_hook=hook, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(parsed, dict):
        raise ValueError("top-level JSON must be an object")
    return parsed


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Compile ARC Prize 2026 paper-track readiness without self-authorizing provider state.")
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--paper", type=Path, default=Path(__file__).with_name("paper.md"))
    parser.add_argument("--results", type=Path, default=Path(__file__).with_name("experiment_results.json"))
    parser.add_argument("--now", required=True, help="Trusted operator-supplied current UTC timestamp for deterministic offline review only")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = compile_readiness(
        load_json_strict(args.evidence),
        paper_text=args.paper.read_text(encoding="utf-8"),
        experiment_results=load_json_strict(args.results),
        now_utc=args.now,
    )
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if receipt["disposition"] != "READY_FOR_OWNER_KAGGLE_SUBMISSION_REVIEW" else 10


if __name__ == "__main__":
    raise SystemExit(main())
