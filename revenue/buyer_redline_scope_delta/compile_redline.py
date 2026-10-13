#!/usr/bin/env python3
"""Hardened facade for the canonical buyer/prime redline compiler.

The Forgeglass #15147 compiler is preserved byte-for-byte in
``_compile_redline_core_20260917.py``.  This facade adds source-custody
chronology holds without changing any existing classification semantics.
"""
from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
from typing import Any

_CORE_PATH = Path(__file__).with_name("_compile_redline_core_20260917.py")
_SPEC = importlib.util.spec_from_file_location("buyer_redline_core_20260917", _CORE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("unable to load frozen buyer-redline core")
_core = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_core)
_ORIGINAL_COMPILE_CASE = _core.compile_case

# Preserve the original module's public surface for callers and the existing suite.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))


def _instant(canonical_timestamp: str) -> datetime:
    return datetime.fromisoformat(canonical_timestamp[:-1] + "+00:00")


def _receipt_for(result: dict[str, Any], packet: str) -> dict[str, Any]:
    baseline = result["baseline"]
    counter = result["counter"]
    return {
        "schema": SCHEMA,
        "truth_state": TRUTH_STATE,
        "decision": result["decision"],
        "as_of": result["as_of"],
        "baseline_document_id": baseline["document_id"],
        "baseline_generation": baseline["generation"],
        "baseline_source_sha256": baseline["source_sha256"],
        "counter_document_id": counter["document_id"],
        "counter_generation": counter["generation"],
        "counter_source_sha256": counter["source_sha256"],
        "normalized_sha256": sha256_bytes(canonical_json(result)),
        "packet_sha256": sha256_bytes(packet.encode("utf-8")),
        "issue_count": len(result["issues"]) + len(result["header_issues"]),
        "hold_count": len(result["holds"]),
    }


def compile_case(raw: Any) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Compile canonically, then fail closed on impossible source chronology."""
    result, packet, receipt = _ORIGINAL_COMPILE_CASE(raw)
    baseline = result["baseline"]
    counter = result["counter"]
    baseline_at = _instant(baseline["observed_at"])
    counter_at = _instant(counter["observed_at"])
    as_of = _instant(result["as_of"])

    chronology_holds: list[dict[str, str]] = []
    if counter_at < baseline_at:
        chronology_holds.append({
            "code": "COUNTER_OBSERVED_BEFORE_BASELINE",
            "ref": counter["generation"],
            "detail": (
                "counter observation predates the baseline observation while claiming "
                "that baseline generation"
            ),
        })
    if as_of < baseline_at:
        chronology_holds.append({
            "code": "AS_OF_BEFORE_BASELINE_OBSERVATION",
            "ref": baseline["generation"],
            "detail": "evaluation as_of predates the retained baseline observation",
        })
    if as_of < counter_at:
        chronology_holds.append({
            "code": "AS_OF_BEFORE_COUNTER_OBSERVATION",
            "ref": counter["generation"],
            "detail": "evaluation as_of predates the retained counter observation",
        })

    if not chronology_holds:
        return result, packet, receipt

    result["holds"] = sorted(
        [*result["holds"], *chronology_holds],
        key=lambda hold: (hold["code"], hold["ref"], hold["detail"]),
    )
    result["decision"] = "HOLD_CONTRADICTION"
    packet = render_packet(result)
    receipt = _receipt_for(result, packet)
    return result, packet, receipt


# Existing core helpers call their module-global compile_case.  Point that seam at the
# hardened wrapper so CLI compile/verify and imported callers share one behavior.
_core.compile_case = compile_case
compile_to_dir = _core.compile_to_dir
verify = _core.verify
parser = _core.parser
main = _core.main


if __name__ == "__main__":
    raise SystemExit(main())
