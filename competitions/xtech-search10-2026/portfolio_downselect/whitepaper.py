"""Internal xTech Search 10 white-paper source-packet compiler.

The output mirrors the published evaluation areas but is deliberately not the
official ValidEval template and never authorizes submission.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from downselect import (
    CRITERIA_WEIGHTS,
    ContractError,
    compile_portfolio,
    read_regular_json,
    sha256_json,
)

WHITEPAPER_PACKET_VERSION = "xtech.search10.whitepaper-source/v1"

SECTION_TITLES = {
    "introduction": "Introduction",
    "armyBenefits": "Army Benefits",
    "technicalApproach": "Technical Approach",
    "commercialPotential": "Commercial Potential",
    "proposalQuality": "Proposal Quality / Evidence Hygiene",
}


def _claim_lines(claims: list[dict[str, Any]], *, label: str = "") -> list[str]:
    lines: list[str] = []
    for row in claims:
        prefix = f"{label}: " if label else ""
        evidence = row["evidenceRef"] if row["evidenceRef"] is not None else "NO_EVIDENCE"
        lines.append(
            f"- [{row['state']}] {prefix}{row['text']} "
            f"(claim={row['claimId']}; evidence={evidence})"
        )
    return lines


def compile_whitepaper(packet: Any) -> dict[str, Any]:
    report = compile_portfolio(packet)
    selected_id = report["selectedCandidateId"]

    if report["state"] != "SELECTED" or selected_id is None:
        blockers = list(report["globalBlockers"])
        for projection in report["projections"]:
            blockers.extend(
                f"{projection['candidateId']}:{item}"
                for item in projection["hardBlockers"]
            )
        markdown = "\n".join(
            [
                "# xTech Search 10 — Internal White-Paper Source Packet",
                "",
                "> BLOCKED: no unique evidence-qualified internal candidate is selected.",
                "> This is not the official ValidEval template and is not submission-ready.",
                "",
                f"- Down-select state: {report['state']}",
                f"- Hold reason: {report['holdReason']}",
                f"- Evidence manifest: {report['retainedEvidenceManifestSha256']}",
                "",
                "## Blocking evidence",
                *([f"- {item}" for item in sorted(set(blockers))] or ["- No blocker details retained."]),
                "",
            ]
        )
        result = {
            "version": WHITEPAPER_PACKET_VERSION,
            "releaseState": "BLOCKED_NO_INTERNAL_SELECTION",
            "selectedCandidateId": None,
            "downselectReceiptSha256": report["receiptSha256"],
            "evidenceManifestSha256": report["retainedEvidenceManifestSha256"],
            "markdown": markdown,
            "wordCount": len(markdown.split()),
            "officialTemplateApplied": False,
            "pageConformanceDetermined": False,
            "submissionAuthorized": False,
        }
        result["receiptSha256"] = sha256_json(result)
        return result

    selected = next(
        row for row in packet["candidates"] if row["candidateId"] == selected_id
    )
    lines = [
        "# xTech Search 10 — Internal White-Paper Source Packet",
        "",
        "> INTERNAL SOURCE PACKET ONLY.",
        "> Not the official ValidEval template; three-page conformance is not determined.",
        "> Registration and submission are not authorized by this compiler.",
        "",
        f"- Candidate: {selected_id}",
        f"- Priority area: {selected['priorityArea']}",
        f"- Exact source provenance: retained in down-select receipt {report['receiptSha256']}",
        f"- Down-select receipt: {report['receiptSha256']}",
        f"- Evidence manifest: {report['retainedEvidenceManifestSha256']}",
        "",
    ]

    for criterion, weight in CRITERIA_WEIGHTS.items():
        lines.extend(
            [
                f"## {SECTION_TITLES[criterion]} — published weight {weight}%",
                *_claim_lines(selected["criteria"][criterion]),
            ]
        )
        if criterion == "technicalApproach":
            lines.extend(_claim_lines(selected["demonstratedMetrics"], label="Demonstrated metric"))
        if criterion == "commercialPotential":
            lines.extend(_claim_lines(selected["transitionPath"], label="Transition path"))
        lines.append("")

    lines.extend(
        [
            "## Compiler truth boundary",
            f"- {report['readinessMetricMeaning']}",
            f"- {report['evidenceTrustBoundary']}",
            "- Official template applied: false",
            "- Three-page conformance determined: false",
            "- Submission authorized: false",
            "",
        ]
    )
    markdown = "\n".join(lines)
    result = {
        "version": WHITEPAPER_PACKET_VERSION,
        "releaseState": "INTERNAL_SOURCE_PACKET_ONLY",
        "selectedCandidateId": selected_id,
        "downselectReceiptSha256": report["receiptSha256"],
        "evidenceManifestSha256": report["retainedEvidenceManifestSha256"],
        "markdown": markdown,
        "wordCount": len(markdown.split()),
        "officialTemplateApplied": False,
        "pageConformanceDetermined": False,
        "submissionAuthorized": False,
    }
    result["receiptSha256"] = sha256_json(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile an internal evidence-labelled xTech white-paper source packet"
    )
    parser.add_argument("packet")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = compile_whitepaper(read_regular_json(args.packet))
    except ContractError as exc:
        print(
            json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, sort_keys=True),
            flush=True,
        )
        return 2
    if args.markdown:
        print(result["markdown"])
    else:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
