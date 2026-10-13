from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from revenue.streaming_rendition_release_gate.gate import HOLD, RELEASE_READY, validate_packets

SCHEMA = "streaming-rendition-qa-pilot/v1"
RECEIPT_SCHEMA = "streaming-rendition-qa-pilot-receipt/v1"
MAX_ASSETS = 250
DIAGNOSTIC_PRICE_USD = 2500
INTEGRATION_PRICE_USD = 7500

EXTERNAL_EFFECTS = {
    "cdn_mutation": False,
    "content_editing": False,
    "drm_secret_access": False,
    "media_release_authority": False,
    "payment_action": False,
    "publishing": False,
    "rights_determination": False,
    "transcoding": False,
}

_ROOT = Path(__file__).resolve().parents[1]
_ENGINE_MANIFEST = _ROOT / "streaming_rendition_release_gate" / "manifest.json"


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _engine_proof() -> dict[str, Any]:
    manifest = json.loads(_ENGINE_MANIFEST.read_text(encoding="utf-8"))
    return {
        "manifest_path": "revenue/streaming_rendition_release_gate/manifest.json",
        "manifest_canonical_sha256": _sha256(canonical_json_bytes(manifest)),
        "source_operation": manifest["operation"],
        "canonical_fixture_sha256": manifest["fixture"]["canonical_sha256"],
        "canonical_fixture_total": manifest["fixture"]["total"],
        "canonical_fixture_release_ready": manifest["fixture"]["release_ready"],
        "canonical_fixture_hold": manifest["fixture"]["hold"],
        "canonical_projection_sha256": manifest["projection_sha256"],
    }


def compile_pilot(packets: Any) -> dict[str, Any]:
    if type(packets) is not list:
        raise ValueError("top-level input must be a JSON array of rendition packets")
    if not packets:
        raise ValueError("pilot input must contain at least one asset packet")
    if len(packets) > MAX_ASSETS:
        raise ValueError(f"pilot input exceeds fixed scope of {MAX_ASSETS} assets")

    canonical_input = canonical_json_bytes(packets)
    validation = validate_packets(packets)
    results = validation.get("results")
    if type(results) is not list or len(results) != len(packets):
        raise RuntimeError("release-gate result cardinality mismatch")

    allowed_statuses = {RELEASE_READY, HOLD}
    if any(row.get("status") not in allowed_statuses for row in results):
        raise RuntimeError("release-gate returned an unknown status")

    ready = sum(row["status"] == RELEASE_READY for row in results)
    hold = sum(row["status"] == HOLD for row in results)
    reason_counts = Counter(
        row["reason"] for row in results if row["status"] == HOLD
    )
    affected_assets: dict[str, list[str]] = {}
    for reason in sorted(reason_counts):
        affected_assets[reason] = sorted(
            row["asset_id"]
            for row in results
            if row["status"] == HOLD and row["reason"] == reason
        )

    return {
        "schema": SCHEMA,
        "offer": {
            "diagnostic_price_usd": DIAGNOSTIC_PRICE_USD,
            "diagnostic_asset_cap": MAX_ASSETS,
            "integration_follow_on_price_usd": INTEGRATION_PRICE_USD,
            "integration_follow_on_requires_paid_diagnostic": True,
            "input_class": "sanitized metadata export only",
            "free_custom_adapter": False,
        },
        "input": {
            "asset_count": len(packets),
            "canonical_sha256": _sha256(canonical_input),
        },
        "engine_proof": _engine_proof(),
        "result": {
            "release_ready": ready,
            "hold": hold,
            "hold_reason_counts": dict(sorted(reason_counts.items())),
            "affected_assets_by_reason": affected_assets,
            "projection_sha256": validation["projection_sha256"],
        },
        "acceptance": {
            "every_input_asset_accounted_for": len(results) == len(packets),
            "deterministic_replay_required": True,
            "stable_reason_codes_required": True,
            "report_and_receipt_hash_bound": True,
        },
        "external_effects": dict(EXTERNAL_EFFECTS),
        "authority_note": (
            "RELEASE_READY means supplied metadata is internally consistent under the "
            "release-gate contract. Media operations retain all rights, release, "
            "transcoding, DRM-secret, CDN, publishing, and production authority."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    result = report["result"]
    lines = [
        "# Streaming Rendition QA Pilot — Diagnostic Report",
        "",
        "## Fixed paid scope",
        "",
        f"- Diagnostic: **${report['offer']['diagnostic_price_usd']:,}** for one sanitized metadata export, up to {report['offer']['diagnostic_asset_cap']} assets.",
        f"- Optional integration follow-on: **${report['offer']['integration_follow_on_price_usd']:,}**, only after the paid diagnostic proves value and adapter scope is known.",
        "- No free custom adapter is included.",
        "",
        "## Result",
        "",
        f"- Assets analyzed: **{report['input']['asset_count']}**",
        f"- `RELEASE_READY`: **{result['release_ready']}**",
        f"- `HOLD`: **{result['hold']}**",
        f"- Canonical input SHA-256: `{report['input']['canonical_sha256']}`",
        f"- Result projection SHA-256: `{result['projection_sha256']}`",
        "",
        "## HOLD inventory",
        "",
    ]

    if result["hold_reason_counts"]:
        lines.extend(["| Reason | Count | Affected assets |", "| --- | ---: | --- |"])
        for reason, count in result["hold_reason_counts"].items():
            assets = ", ".join(result["affected_assets_by_reason"][reason])
            lines.append(f"| `{reason}` | {count} | {assets} |")
    else:
        lines.append("No HOLD findings in the supplied metadata export.")

    lines.extend(
        [
            "",
            "## Acceptance and proof",
            "",
            "- Every supplied asset is represented exactly once in the result set.",
            "- Replay of identical packet bytes must produce the same projection SHA-256.",
            "- Machine JSON and receipt are canonicalized and hash-bound.",
            f"- Engine proof manifest: `{report['engine_proof']['manifest_path']}`",
            f"- Engine manifest canonical SHA-256: `{report['engine_proof']['manifest_canonical_sha256']}`",
            "",
            "## Authority boundary",
            "",
            "`RELEASE_READY` is **not media release authority**.",
            "",
            report["authority_note"],
            "",
            "This diagnostic does **not** inspect media bytes, retrieve DRM secrets, make rights decisions, transcode, mutate a CDN, publish media, charge a customer, or authorize release.",
            "",
        ]
    )
    return "\n".join(lines)


def compile_artifacts(packets: Any) -> dict[str, bytes]:
    report = compile_pilot(packets)
    report_json = canonical_json_bytes(report)
    markdown = render_markdown(report).encode("utf-8")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "input_canonical_sha256": report["input"]["canonical_sha256"],
        "engine_manifest_canonical_sha256": report["engine_proof"][
            "manifest_canonical_sha256"
        ],
        "projection_sha256": report["result"]["projection_sha256"],
        "report_json_sha256": _sha256(report_json),
        "report_markdown_sha256": _sha256(markdown),
        "external_effects": dict(EXTERNAL_EFFECTS),
    }
    receipt_json = canonical_json_bytes(receipt)
    return {
        "report.json": report_json,
        "report.md": markdown,
        "receipt.json": receipt_json,
    }


__all__ = [
    "DIAGNOSTIC_PRICE_USD",
    "EXTERNAL_EFFECTS",
    "INTEGRATION_PRICE_USD",
    "MAX_ASSETS",
    "SCHEMA",
    "compile_artifacts",
    "compile_pilot",
    "render_markdown",
]
