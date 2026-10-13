"""Bind the two observed public T07 responses and normalize their exact V7 source.

Consumes ELM's existing intake artifact; does not make requests, execute notebook
cells, run games, or infer a license. See README.md for the artifact and provenance.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import shutil

from normalize import SourceError, canonical, digest, normalize, source_text, strict_json

PULL_URL = "https://www.kaggle.com/api/v1/kernels/pull/romanrozen/strong-barnyard-economist"
FIXED_URL = "https://www.kaggle.com/kernels/scriptcontent/341074820/download"
MAIN_SHA256 = "997e6bfc5234534e246e945bc61c87858ebf997ab85b0a5c9427dd4ed710f1b6"


def read_json(path: Path):
    return strict_json(path.read_text(encoding="utf-8"))


def bind_intake(intake: Path) -> dict:
    """Check exact recorded bytes, source identity, and fixed/latest correspondence."""
    receipt = read_json(intake / "INTAKE.json")
    if not isinstance(receipt, dict) or not isinstance(receipt.get("requests"), list):
        raise SourceError("Intake receipt has no requests array")
    sources = {}
    for name, url in (("barnyard-pull.json", PULL_URL), ("barnyard-v7-download", FIXED_URL)):
        rows = [r for r in receipt["requests"] if isinstance(r, dict) and r.get("path") == name]
        if len(rows) != 1:
            raise SourceError(f"Expected exactly one intake record for {name}")
        row = rows[0]
        raw = (intake / name).read_bytes()
        if row.get("status") != 200 or row.get("requested_url") != url or row.get("final_url") != url:
            raise SourceError(f"Unexpected public response identity for {name}")
        if row.get("bytes") != len(raw) or row.get("sha256") != digest(raw):
            raise SourceError(f"Intake bytes differ from recorded response: {name}")
        sources[name] = {"url": url, "bytes": len(raw), "sha256": digest(raw)}
    pull = read_json(intake / "barnyard-pull.json")
    if not isinstance(pull, dict) or not isinstance(pull.get("metadata"), dict):
        raise SourceError("Pull response lacks metadata")
    meta = pull["metadata"]
    if meta.get("ref") != "romanrozen/strong-barnyard-economist" or meta.get("id") != 129253091:
        raise SourceError("Pull response belongs to another notebook")
    if meta.get("isPrivate") is not False:
        raise SourceError("Public-source status is absent or different")
    if type(meta.get("currentVersionNumber")) is not int or meta["currentVersionNumber"] != 7:
        raise SourceError("Latest pull is not the observed V7; do not silently substitute it")
    blob = pull.get("blob")
    if not isinstance(blob, dict) or not isinstance(blob.get("source"), str):
        raise SourceError("Pull response lacks /blob/source notebook string")
    latest = strict_json(blob["source"])
    fixed = read_json(intake / "barnyard-v7-download")
    for value in (fixed, latest):
        if not isinstance(value, dict) or value.get("nbformat") != 4 or not isinstance(value.get("cells"), list):
            raise SourceError("Both responses must contain version-4 notebooks")
    if len(fixed["cells"]) != len(latest["cells"]):
        raise SourceError("Fixed download and latest pull have different cell counts")
    cells = []
    for index, (a, b) in enumerate(zip(fixed["cells"], latest["cells"])):
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise SourceError("Malformed notebook cell")
        left, right = source_text(a.get("source")), source_text(b.get("source"))
        if a.get("cell_type") != b.get("cell_type") or left != right:
            raise SourceError(f"Fixed download and pull differ at cell {index}")
        cells.append({"index": index, "cell_type": a.get("cell_type"),
                      "source_sha256": digest(left.encode("utf-8"))})
    return {"schema": "titan.barnyard-v7-source-binding.v1", "notebook_id": 129253091,
            "ref": meta["ref"], "author": meta.get("author"), "public": True,
            "version_number_observed": 7, "fixed_download_script_version_id": 341074820,
            "sources": sources, "cell_sources_equal": True, "cell_count": len(cells),
            "cells": cells, "intake_sha256": digest((intake / "INTAKE.json").read_bytes()),
            "intake_run": receipt.get("run_id"), "intake_attempt": receipt.get("run_attempt"),
            "execution_performed": False,
            "limit": "Transport receipt and source comparison; not runtime, strength, or license evidence."}


def normalize_intake(intake: Path, output: Path, licenses: list[Path] | None = None) -> dict:
    binding = bind_intake(intake)
    manifest = normalize(intake / "barnyard-v7-download", intake / "barnyard-pull.json", output,
                         input_format="json", source_url=FIXED_URL,
                         version_pointer="/metadata/currentVersionNumber", expected_version="7",
                         licenses=licenses)
    try:
        if manifest["files"].get("main.py", {}).get("sha256") != MAIN_SHA256:
            raise SourceError("Extracted main.py differs from the reviewed V7 source pin")
        binding["main_sha256"] = MAIN_SHA256
        binding["main_bytes"] = manifest["files"]["main.py"]["bytes"]
        binding["normalization_manifest_sha256"] = digest((output / "provenance/MANIFEST.json").read_bytes())
        (output / "provenance/INTAKE.json").write_bytes((intake / "INTAKE.json").read_bytes())
        (output / "provenance/BINDING.json").write_bytes(canonical(binding))
    except BaseException:
        shutil.rmtree(output)
        raise
    return binding


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--license", action="append", type=Path, default=[], dest="licenses")
    args = parser.parse_args()
    try:
        binding = normalize_intake(args.intake, args.output, args.licenses)
    except (SourceError, OSError, ValueError) as exc:
        parser.exit(2, f"BINDING_ERROR: {exc}\n")
    print(json.dumps({"output": str(args.output), "cells_matched": binding["cell_count"],
                      "main_sha256": binding["main_sha256"], "execution_performed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
