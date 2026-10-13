#!/usr/bin/env python3
"""CLI and public API for TITAN V5 lean-feed carry economics."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from lean_feed_core import *
from lean_feed_core import EvidenceError, _require, canonical_json_bytes, sha256_file
from lean_feed_gate import *
from lean_feed_hardening import analyze_authoritative_document
from lean_feed_run import *


def render_markdown(report: Mapping[str, Any]) -> str:
    promotion = report["promotion"]
    lines = [
        "# TITAN V5 lean-feed carry economics",
        "",
        f"- Conclusion: **{promotion['conclusion']}**",
        f"- Selected arm: `{promotion['selected_arm'] or 'none'}`",
    ]
    if "candidate_conclusion" in promotion:
        lines += [
            f"- Candidate economics: `{promotion['candidate_conclusion']}`",
            f"- Promotion authority verified: `{str(promotion['authority_verified']).lower()}`",
        ]
    lines += [
        f"- Dev mean delta-M: `{promotion['dev_mean_delta_m']:.6f}`",
        f"- Holdout mean delta-M: `{promotion['holdout_mean_delta_m']:.6f}`",
        "- Dev/holdout downstream liberated-cash use: "
        f"`{promotion['dev_downstream_cash_used']:.6f}` / "
        f"`{promotion['holdout_downstream_cash_used']:.6f}`",
        f"- D2 archive: `{report['authority']['archive_sha256']}`",
        f"- Report digest: `{report['report_sha256']}`",
        "",
        "## Falsifiers",
        "",
    ]
    lines += [f"- {item}" for item in promotion["falsifiers"]] or ["- none"]
    lines += [
        "",
        "## Seat/opponent strata",
        "",
        "| Split | Opponent | Seat | Cells | Mean delta-M | Negative cells |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in promotion["strata"]:
        lines.append(
            f"| {row['split']} | {row['opponent']} | {row['seat']} | "
            f"{row['cells']} | {row['mean_delta_m']:.6f} | "
            f"{row['negative_cells']} |"
        )
    lines += [
        "",
        "This report rejects inventory, ending-cash, and byte-change proxies. "
        "A promotion requires a reachable current-policy excess, explicit cash "
        "liberation, later runtime-ledger use, satisfied feed obligations, "
        "both-seat/opponent stability, untouched holdout survival, and an "
        "independently retained code-trusted evidence root.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    report: Mapping[str, Any], out: Path, force: bool = False
) -> dict[str, str]:
    if out.exists():
        if not force:
            raise EvidenceError(f"output directory already exists: {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    paths = {
        "summary.json": out / "summary.json",
        "census.jsonl": out / "census.jsonl",
        "paired_deltas.csv": out / "paired_deltas.csv",
        "runs.csv": out / "runs.csv",
        "report.md": out / "report.md",
    }
    paths["summary.json"].write_bytes(canonical_json_bytes(report))
    paths["census.jsonl"].write_bytes(
        b"".join(canonical_json_bytes(row) for row in report["census"])
    )
    paths["report.md"].write_text(
        render_markdown(report), encoding="utf-8", newline="\n"
    )
    for name, rows in (
        ("paired_deltas.csv", report["paired_deltas"]),
        ("runs.csv", report["runs"]),
    ):
        with paths[name].open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(rows[0]) if rows else [],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
    artifacts = {name: sha256_file(path) for name, path in paths.items()}
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "report_sha256": report["report_sha256"],
        "artifacts": artifacts,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    artifacts["manifest.json"] = sha256_file(manifest_path)
    return artifacts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.evidence.read_text(encoding="utf-8"))
        _require(isinstance(document, Mapping), "top-level evidence must be an object")
        # Official CLI is a promotion-authority surface, not merely an economics
        # candidate scorer. It therefore always applies the fail-closed wrapper.
        report = analyze_authoritative_document(document)
        artifacts = write_outputs(report, args.out, args.force)
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"promotion": report["promotion"], "artifacts": artifacts},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
