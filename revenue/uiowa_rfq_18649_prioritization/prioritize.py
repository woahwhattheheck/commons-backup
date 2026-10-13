#!/usr/bin/env python3
"""Transparent recommendation prioritization for UIOWA-084.

Scores are synthetic planning inputs, not University findings.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

DIMENSIONS = ("quality", "security", "delivery")
REQUIRED_INPUT_COLUMNS = (
    "id", "title", "quality", "security", "delivery", "complexity",
    "confidence", "owner_role", "dependencies", "assumptions",
)
SCORE_MIN = 0.0
SCORE_MAX = 5.0


def _parse_optional_number(value: str) -> Optional[float]:
    text = (value or "").strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"not a number: {value!r}") from exc


def _number(name: str, value: object) -> float:
    """JSON numbers only: booleans, strings and non-finite values are not estimates."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite JSON number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _validate_range(name: str, value: Optional[float], lo: float, hi: float) -> None:
    if value is not None and not (lo <= _number(name, value) <= hi):
        raise ValueError(f"{name} must be between {lo} and {hi}; got {value}")


def validate_weights(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("weights config must be an object")
    if set(config) - {"profiles", "tie_epsilon"}:
        raise ValueError("weights config contains unknown keys")
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("weights config must contain a non-empty 'profiles' object")
    if _number("tie_epsilon", config.get("tie_epsilon", 0.0)) < 0:
        raise ValueError("tie_epsilon must be >= 0")
    seen = set()
    for profile_name, weights in profiles.items():
        if not isinstance(profile_name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", profile_name):
            raise ValueError("profile name must be a portable 1-64 character identifier")
        if profile_name.casefold() in seen:
            raise ValueError("profile names collide on a case-insensitive filesystem")
        seen.add(profile_name.casefold())
        if not isinstance(weights, dict) or set(weights) != set((*DIMENSIONS, "complexity")):
            raise ValueError(f"profile {profile_name!r} requires exactly quality, security, delivery, complexity")
        values = {key: _number(f"{profile_name}.{key}", value) for key, value in weights.items()}
        if any(value < 0 for value in values.values()):
            raise ValueError(f"profile {profile_name!r} weights must be >= 0")
        if any(values[key] > 1 for key in DIMENSIONS):
            raise ValueError(f"profile {profile_name!r} benefit weights must be <= 1")
        if abs(sum(values[key] for key in DIMENSIONS) - 1.0) > 1e-9:
            raise ValueError(f"profile {profile_name!r} benefit weights must sum to 1.0")


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON number: {value}")


def _weights_from_bytes(raw: bytes) -> dict:
    config = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant)
    validate_weights(config)
    return config


def load_weights(path: Path) -> dict:
    return _weights_from_bytes(Path(path).read_bytes())


def _recommendations_from_bytes(raw: bytes) -> List[dict]:
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    try:
        fields = next(reader, None)
        if not fields:
            raise ValueError("recommendation CSV has no header")
        if len(set(fields)) != len(fields):
            raise ValueError("recommendation CSV has duplicate column names")
        if set(fields) != set(REQUIRED_INPUT_COLUMNS):
            raise ValueError("recommendation CSV requires exactly: " + ", ".join(REQUIRED_INPUT_COLUMNS))
        records: List[dict] = []
        seen: set[str] = set()
        for cells in reader:
            if not cells:  # Empty physical records are not missing estimates.
                continue
            line_no = reader.line_num
            if len(cells) != len(fields):
                raise ValueError(f"record ending at line {line_no}: expected {len(fields)} cells; got {len(cells)}")
            row = dict(zip(fields, cells))
            rec_id = row["id"].strip()
            title = row["title"].strip()
            if not rec_id or not title:
                raise ValueError(f"record ending at line {line_no}: id and title are required")
            if rec_id in seen:
                raise ValueError(f"record ending at line {line_no}: duplicate id {rec_id!r}")
            seen.add(rec_id)
            parsed = {**row, "id": rec_id, "title": title}
            for name in (*DIMENSIONS, "complexity"):
                parsed[name] = _parse_optional_number(row[name])
                _validate_range(name, parsed[name], SCORE_MIN, SCORE_MAX)
            parsed["confidence"] = _parse_optional_number(row["confidence"])
            _validate_range("confidence", parsed["confidence"], 0.0, 1.0)
            records.append(parsed)
    except csv.Error as exc:
        raise ValueError(f"invalid CSV near physical line {reader.line_num}: {exc}") from exc
    if not records:
        raise ValueError("recommendation CSV contains no records")
    return records


def load_recommendations(path: Path) -> List[dict]:
    return _recommendations_from_bytes(Path(path).read_bytes())


def score_record(record: dict, weights: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("recommendation must be an object")
    validate_weights({"profiles": {"score": weights}})
    for name in (*DIMENSIONS, "complexity"):
        _validate_range(name, record.get(name), SCORE_MIN, SCORE_MAX)
    _validate_range("confidence", record.get("confidence"), 0.0, 1.0)
    missing = [name for name in (*DIMENSIONS, "complexity") if record.get(name) is None]
    if missing:
        return {
            **record,
            "status": "HOLD_MISSING_ESTIMATE",
            "missing_estimates": ";".join(missing),
            "benefit_score": None,
            "priority_score": None,
        }
    benefit = sum(float(weights[d]) * float(record[d]) for d in DIMENSIONS)
    complexity_penalty = float(weights["complexity"]) * float(record["complexity"])
    score = benefit - complexity_penalty
    if not math.isfinite(score):
        raise ValueError("priority calculation overflowed; reduce the complexity weight")
    return {
        **record,
        "status": "RANKED",
        "missing_estimates": "",
        "benefit_score": benefit,
        "priority_score": score,
    }


def rank_profile(records: Sequence[dict], profile_name: str, weights: dict, tie_epsilon: float) -> List[dict]:
    validate_weights({"profiles": {profile_name: weights}, "tie_epsilon": tie_epsilon})
    scored = [score_record(r, weights) for r in records]
    eligible = [r for r in scored if r["status"] == "RANKED"]
    held = [r for r in scored if r["status"] != "RANKED"]
    eligible.sort(key=lambda r: (-float(r["priority_score"]), r["id"]))
    held.sort(key=lambda r: r["id"])

    ranked: List[dict] = []
    i = 0
    tie_group_counter = 0
    while i < len(eligible):
        anchor = eligible[i]
        group = [anchor]
        j = i + 1
        while j < len(eligible):
            if abs(float(eligible[j]["priority_score"]) - float(anchor["priority_score"])) <= tie_epsilon:
                group.append(eligible[j])
                j += 1
            else:
                break
        rank = i + 1
        tie_group_counter += 1
        tie_id = f"T{tie_group_counter:02d}" if len(group) > 1 else ""
        if len(group) > 1:
            low = min(float(x["priority_score"]) for x in group)
            high = max(float(x["priority_score"]) for x in group)
            tie_reason = (
                f"{len(group)} recommendations within tie_epsilon={tie_epsilon:.4f}; "
                f"score span={high-low:.4f}"
            )
        else:
            tie_reason = ""
        for rec in group:
            ranked.append({
                **rec,
                "profile": profile_name,
                "rank": rank,
                "tie_group": tie_id,
                "tie_reason": tie_reason,
            })
        i = j

    for rec in held:
        ranked.append({
            **rec,
            "profile": profile_name,
            "rank": "",
            "tie_group": "",
            "tie_reason": "",
        })
    return ranked


def _fmt(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def write_profile_csv(path: Path, rows: Sequence[dict]) -> None:
    fields = [
        "profile", "rank", "tie_group", "id", "title", "status",
        "priority_score", "benefit_score", "quality", "security", "delivery",
        "complexity", "confidence", "missing_estimates", "tie_reason",
        "owner_role", "dependencies", "assumptions",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in fields})


def build_sensitivity(all_profiles: Dict[str, Sequence[dict]]) -> List[dict]:
    ids = sorted({r["id"] for rows in all_profiles.values() for r in rows})
    lookup = {
        (profile, row["id"]): row
        for profile, rows in all_profiles.items()
        for row in rows
    }
    out: List[dict] = []
    profiles = list(all_profiles.keys())
    for rec_id in ids:
        first = lookup[(profiles[0], rec_id)]
        ranked_ranks = [
            int(lookup[(p, rec_id)]["rank"])
            for p in profiles
            if lookup[(p, rec_id)]["rank"] != ""
        ]
        row = {
            "id": rec_id,
            "title": first["title"],
            "status": (
                "RANKED_ALL_PROFILES"
                if len(ranked_ranks) == len(profiles)
                else "HOLD_MISSING_ESTIMATE"
            ),
            "best_rank": min(ranked_ranks) if ranked_ranks else "",
            "worst_rank": max(ranked_ranks) if ranked_ranks else "",
            "rank_span": (max(ranked_ranks) - min(ranked_ranks)) if ranked_ranks else "",
        }
        for p in profiles:
            item = lookup[(p, rec_id)]
            row[f"{p}_rank"] = item["rank"]
            row[f"{p}_score"] = item["priority_score"]
            row[f"{p}_tie_group"] = item["tie_group"]
        out.append(row)
    return out


def write_sensitivity_csv(path: Path, rows: Sequence[dict], profiles: Sequence[str]) -> None:
    fields = ["id", "title", "status", "best_rank", "worst_rank", "rank_span"]
    for p in profiles:
        fields.extend([f"{p}_rank", f"{p}_score", f"{p}_tie_group"])
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _fmt(row.get(k)) for k in fields})


def _md(value: object) -> str:
    text = html.escape(str(value), quote=False).replace("|", "&#124;").replace("\\", "&#92;")
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render_report(config: dict, all_profiles: Dict[str, Sequence[dict]], sensitivity: Sequence[dict]) -> str:
    profiles = list(all_profiles.keys())
    lines: List[str] = []
    lines.append("# Recommendation prioritization sensitivity report")
    lines.append("")
    lines.append("**Synthetic planning output — not a University of Iowa finding or decision.**")
    lines.append("")
    lines.append("## Formula")
    lines.append("")
    lines.append("For a complete recommendation under each profile:")
    lines.append("")
    lines.append("`benefit = quality*w_q + security*w_s + delivery*w_d`")
    lines.append("")
    lines.append("`priority = benefit - complexity*w_complexity`")
    lines.append("")
    lines.append(
        "Quality, security, delivery, and complexity are explicit 0–5 planning estimates. "
        "Missing required estimates produce `HOLD_MISSING_ESTIMATE`; they are never converted to zero."
    )
    lines.append("")
    lines.append(f"Tie epsilon: `{float(config.get('tie_epsilon', 0.0)):.4f}`.")
    lines.append("")
    lines.append("## Weight profiles")
    lines.append("")
    lines.append("| Profile | Quality | Security | Delivery | Complexity penalty |")
    lines.append("|---|---:|---:|---:|---:|")
    for p in profiles:
        w = config["profiles"][p]
        lines.append(
            f"| {p} | {float(w['quality']):.2f} | {float(w['security']):.2f} | "
            f"{float(w['delivery']):.2f} | {float(w['complexity']):.2f} |"
        )
    lines.append("")
    lines.append("## Rankings by profile")
    lines.append("")
    for p in profiles:
        lines.append(f"### {p}")
        lines.append("")
        lines.append("| Rank | ID | Recommendation | Score | Status | Tie |")
        lines.append("|---:|---|---|---:|---|---|")
        for r in all_profiles[p]:
            rank = r["rank"] if r["rank"] != "" else "—"
            score = _fmt(r["priority_score"]) or "—"
            tie = r["tie_group"] or ""
            lines.append(f"| {rank} | {_md(r['id'])} | {_md(r['title'])} | {score} | {r['status']} | {tie} |")
        lines.append("")
    lines.append("## Sensitivity summary")
    lines.append("")
    lines.append("| ID | Recommendation | Best rank | Worst rank | Rank span | Status |")
    lines.append("|---|---|---:|---:|---:|---|")
    for r in sorted(
        sensitivity,
        key=lambda x: (999999 if x["best_rank"] == "" else int(x["best_rank"]), x["id"]),
    ):
        lines.append(
            f"| {_md(r['id'])} | {_md(r['title'])} | {r['best_rank'] or '—'} | "
            f"{r['worst_rank'] or '—'} | {r['rank_span'] if r['rank_span'] != '' else '—'} | "
            f"{r['status']} |"
        )
    lines.append("")
    lines.append("## Interpretation guardrails")
    lines.append("")
    lines.append("- Rankings expose assumptions; they do not replace evidence, judgment, or accountable University decisions.")
    lines.append("- A high score means high priority under the selected synthetic assumptions, not proven impact.")
    lines.append("- Confidence is reported but not silently multiplied into the score; teams may change the formula explicitly if desired.")
    lines.append("- Tied recommendations intentionally retain the same rank when scores fall within the configured epsilon.")
    lines.append("- Recommendations with missing required estimates remain on hold and visible in every output.")
    lines.append("")
    return "\n".join(lines)


def run(input_csv: Path, weights_path: Path, out_dir: Path) -> Dict[str, Sequence[dict]]:
    """Publish into a fresh/empty directory without replacing any operator file.

    Inputs are captured once. Rendering finishes before destination mutation.
    A publication I/O failure leaves .incomplete; never consume that bundle as
    complete. This is not a process sandbox or an atomic multi-file transaction.
    """
    input_bytes = Path(input_csv).read_bytes()
    weights_bytes = Path(weights_path).read_bytes()
    config = _weights_from_bytes(weights_bytes)
    records = _recommendations_from_bytes(input_bytes)
    epsilon = float(config.get("tie_epsilon", 0.0))
    all_profiles = {
        name: rank_profile(records, name, weights, epsilon)
        for name, weights in config["profiles"].items()
    }
    sensitivity = build_sensitivity(all_profiles)
    report = render_report(config, all_profiles, sensitivity)
    out_dir = Path(out_dir)
    if out_dir.is_symlink() or (out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir()))):
        raise ValueError("output directory must be fresh or empty and not a symlink")

    # Existing CSV writers are retained; only this private staging tree is replaced.
    with tempfile.TemporaryDirectory(prefix="uiowa084-") as temp:
        stage = Path(temp)
        for name, rows in all_profiles.items():
            write_profile_csv(stage / f"ranking_{name}.csv", rows)
        write_sensitivity_csv(stage / "sensitivity.csv", sensitivity, list(all_profiles))
        (stage / "report.md").write_text(report, encoding="utf-8")
        outputs = {file.name: file.read_bytes() for file in sorted(stage.iterdir())}
        manifest = {
            "schema": "uiowa084-output-v1",
            "formula": "weighted_benefit_minus_weighted_complexity",
            "source_sha256": {
                "recommendations": hashlib.sha256(input_bytes).hexdigest(),
                "weights": hashlib.sha256(weights_bytes).hexdigest(),
            },
            "record_count": len(records),
            "profile_count": len(all_profiles),
            "outputs": {name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        out_dir.mkdir(parents=True, exist_ok=True)
        if out_dir.is_symlink() or any(out_dir.iterdir()):
            raise ValueError("output directory changed or is nonempty; no files replaced")
        incomplete = out_dir / ".incomplete"
        with incomplete.open("x", encoding="utf-8") as stream:
            stream.write("Publication incomplete. Do not consume this directory as a completed bundle.\n")
        for name, data in outputs.items():
            with (out_dir / name).open("xb") as stream:
                stream.write(data)
        with (out_dir / "manifest.json").open("xb") as stream:
            stream.write(manifest_bytes)
        incomplete.unlink()
    return all_profiles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank recommendations with transparent assumptions.")
    parser.add_argument("recommendations", type=Path, help="Input recommendation CSV")
    parser.add_argument("weights", type=Path, help="JSON weight-profile config")
    parser.add_argument("--out-dir", type=Path, default=Path("out"), help="Output directory")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run(args.recommendations, args.weights, args.out_dir)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
