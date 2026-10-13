#!/usr/bin/env python3
"""Check agreement across RFQ 18649 output surfaces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from model import (
    Diagnostic,
    canonical_indexes,
    diag_rows,
    index_unique,
    load_csv,
    load_json,
    mismatch,
    optional_number,
    split_ids,
    unknown,
)


def compare_matrix(path: Path, findings: dict[str, dict], diags: list[Diagnostic]) -> None:
    artifact = "matrix.csv"
    rows = load_csv(path)
    index_unique(rows, "cell_id", artifact, diags)
    seen: set[str] = set()
    for row in rows:
        fid = str(row.get("finding_id", "")).strip()
        if not fid:
            continue
        if fid in seen:
            diags.append(Diagnostic(
                "DUPLICATE_REFERENCE", artifact, "finding", fid, "finding_id",
                "one matrix row per synthetic finding", fid,
                f"{artifact} repeats finding_id={fid}",
            ))
        seen.add(fid)
        if fid not in findings:
            unknown(diags, artifact, "finding", fid, "finding_id", fid)
            continue
        src = findings[fid]
        mismatch(diags, artifact, "finding", fid, "service",
                 str(src.get("service", "")), str(row.get("service", "")))
        mismatch(diags, artifact, "finding", fid, "state",
                 str(src.get("state", "")), str(row.get("finding_state", "")))


def compare_recommendations(
    path: Path,
    findings: dict[str, dict],
    recs: dict[str, dict],
    diags: list[Diagnostic],
) -> None:
    artifact = "recommendations.csv"
    rows = index_unique(load_csv(path), "recommendation_id", artifact, diags)
    for rid, row in rows.items():
        if rid not in recs:
            unknown(diags, artifact, "recommendation", rid, "recommendation_id", rid)
            continue
        src = recs[rid]
        actual_findings = sorted(split_ids(row.get("linked_findings")))
        expected_findings = sorted(str(x) for x in src.get("finding_ids", []))
        mismatch(diags, artifact, "recommendation", rid, "linked_findings",
                 expected_findings, actual_findings)
        for fid in actual_findings:
            if fid not in findings:
                unknown(diags, artifact, "recommendation", rid, "linked_findings", fid)
        mismatch(diags, artifact, "recommendation", rid, "phase",
                 str(src.get("phase", "")), str(row.get("phase", "")))
        for field in ("estimate_low", "estimate_high"):
            mismatch(diags, artifact, "recommendation", rid, field,
                     optional_number(src.get(field)), optional_number(row.get(field)))
    for rid in sorted(set(recs) - set(rows)):
        diags.append(Diagnostic(
            "MISSING_ENTITY", artifact, "recommendation", rid, "recommendation_id",
            "present", "absent", f"{artifact} omits canonical recommendation {rid}",
        ))


def compare_claims(
    path: Path,
    artifact: str,
    findings: dict[str, dict],
    recs: dict[str, dict],
    diags: list[Diagnostic],
) -> None:
    data = load_json(path)
    counts = data.get("declared_counts", {})
    expected_counts = {"findings": len(findings), "recommendations": len(recs)}
    for field, expected in expected_counts.items():
        actual = counts.get(field)
        if actual != expected:
            diags.append(Diagnostic(
                "COUNT_MISMATCH", artifact, "bundle", "ALL", field,
                expected, actual,
                f"{artifact} declares {field}={actual!r}; expected {expected}",
            ))

    claims = data.get("claims", [])
    index_unique(claims, "claim_id", artifact, diags)
    for claim in claims:
        cid = str(claim.get("claim_id", "")).strip()
        fid = str(claim.get("finding_id", "")).strip()
        rid = str(claim.get("recommendation_id", "")).strip()

        if fid:
            if fid not in findings:
                unknown(diags, artifact, "claim", cid, "finding_id", fid)
            elif "finding_state" in claim:
                mismatch(
                    diags, artifact, "finding", fid, "finding_state",
                    str(findings[fid].get("state", "")),
                    str(claim.get("finding_state", "")),
                )

        if rid:
            if rid not in recs:
                unknown(diags, artifact, "claim", cid, "recommendation_id", rid)
            else:
                src = recs[rid]
                if "phase" in claim:
                    mismatch(
                        diags, artifact, "recommendation", rid, "phase",
                        str(src.get("phase", "")), str(claim.get("phase", "")),
                    )
                for field in ("estimate_low", "estimate_high"):
                    if field in claim:
                        mismatch(
                            diags, artifact, "recommendation", rid, field,
                            optional_number(src.get(field)),
                            optional_number(claim.get(field)),
                        )


def check_bundle(root: Path) -> dict:
    findings, recs = canonical_indexes(load_json(root / "canonical.json"))
    diags: list[Diagnostic] = []
    compare_matrix(root / "matrix.csv", findings, diags)
    compare_recommendations(root / "recommendations.csv", findings, recs, diags)
    compare_claims(root / "executive-summary.json", "executive-summary.json", findings, recs, diags)
    compare_claims(root / "presentation.json", "presentation.json", findings, recs, diags)
    rows = diag_rows(diags)
    return {
        "status": "PASS" if not rows else "FAIL",
        "diagnostic_count": len(rows),
        "canonical_counts": {"findings": len(findings), "recommendations": len(recs)},
        "diagnostics": rows,
    }


def markdown_report(result: dict) -> str:
    lines = [
        "# Cross-output consistency report",
        "",
        f"Status: **{result['status']}**",
        f"Diagnostics: **{result['diagnostic_count']}**",
        "",
    ]
    if not result["diagnostics"]:
        lines += ["All checked output surfaces agree on the modeled identifiers and fields.", ""]
    else:
        lines += [
            "| Code | Artifact | Entity | ID | Field | Expected | Actual |",
            "|---|---|---|---|---|---|---|",
        ]
        for d in result["diagnostics"]:
            lines.append(
                f"| {d['code']} | {d['artifact']} | {d['entity_type']} | "
                f"{d['entity_id'] or '—'} | {d['field']} | "
                f"{d['expected']!r} | {d['actual']!r} |"
            )
        lines.append("")
    lines += [
        "## Guardrails",
        "",
        "- Synthetic preparation data only; not a University finding.",
        "- UNKNOWN remains a literal state and is never coerced to zero or a gap.",
        "- Disagreements are reported, never auto-resolved.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("bundle", type=Path)
    p.add_argument("--json-out", type=Path)
    p.add_argument("--md-out", type=Path)
    args = p.parse_args()
    result = check_bundle(args.bundle)
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(result, indent=2))
    if args.md_out:
        args.md_out.write_text(markdown_report(result), encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
