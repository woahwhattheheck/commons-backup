#!/usr/bin/env python3
"""Synthetic/read-only MSU Denver beverage QA/QC reconciliation demo.

The adapter deliberately performs no network, provider, customer, production,
billing, regulatory, or report-send action.  It validates an immutable
synthetic fixture, constructs an in-memory reconciliation ledger, and exposes a
copy-only named-human report-release boundary.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


DEMAND_ID = "msudenver-beverage-qaqc-lims-01"

CATALOG: dict[str, dict[str, Any]] = {
    "CORE": {
        "tests": ("ABV", "PH"),
        "matrices": ("BEER", "WINE", "KOMBUCHA"),
    },
    "BEER_EXTENDED": {
        "tests": ("ABV", "PH", "IBU"),
        "matrices": ("BEER",),
    },
}

TEST_META: dict[str, dict[str, Any]] = {
    "ABV": {"unit": "% v/v", "rounding": 1, "method_version": "BA-ABV-v2"},
    "PH": {"unit": "pH", "rounding": 2, "method_version": "BA-PH-v3"},
    "IBU": {"unit": "IBU", "rounding": 0, "method_version": "BA-IBU-v1"},
}

HOLD_REASONS = (
    "MISSING_SAMPLE_TEST_IDENTITY",
    "DUPLICATE_CLIENT_ID",
    "INCOMPATIBLE_PACKAGE_TEST_SELECTION",
    "QC_CONTROL_FAIL",
)

RESERVED_REVIEWER_TOKENS = {
    "ai", "agent", "auto", "automated", "automation",
    "bot", "robot", "service", "system",
}
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class ReconciliationError(RuntimeError):
    """Base exception for a fail-closed reconciliation boundary."""


class ManifestError(ReconciliationError):
    """Raised when the frozen fixture/manifest binding is invalid."""


class ReplayPayloadMismatch(ReconciliationError):
    """Raised when a request ID is replayed with changed content."""


class ReleaseError(ReconciliationError):
    """Raised when a staged report copy cannot be human-released."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    if isinstance(value, bytes):
        data = value
    else:
        data = _canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def _manifest_digest(manifest: dict[str, Any]) -> str:
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    return sha256_hex(unsigned)


def _golden_result(code: str, index: int) -> dict[str, Any]:
    meta = TEST_META[code]
    if code == "ABV":
        value = f"{Decimal('4.0') + Decimal(index % 30) / Decimal(10):.1f}"
    elif code == "PH":
        value = f"{Decimal('3.20') + Decimal(index % 25) / Decimal(100):.2f}"
    elif code == "IBU":
        value = str(20 + (index % 70))
    else:  # pragma: no cover - TEST_META is frozen above
        raise ManifestError(f"unsupported generated test code: {code}")
    return {"method_version": meta["method_version"], "rounding": meta["rounding"], "test_code": code, "unit": meta["unit"], "value": value}


def _expand_fixture(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    generator = fixture.get("generator")
    if not isinstance(generator, dict) or generator.get("kind") != "msu-denver-beverage-qaqc-v1":
        raise ManifestError("fixture requests/generator missing")
    if generator != {"kind": "msu-denver-beverage-qaqc-v1", "row_count": 100}:
        raise ManifestError("fixture generator contract changed")
    rows: list[dict[str, Any]] = []
    for index in range(1, 101):
        request_id = f"MSU-{index:03d}"
        client_index = index - 88 if 89 <= index <= 93 else index
        client_request_id = f"CLIENT-{client_index:03d}"
        matrix = ("BEER", "WINE", "KOMBUCHA")[(index - 1) % 3]
        package = "BEER_EXTENDED" if index <= 20 else "CORE"
        selected = list(CATALOG[package]["tests"])
        if index <= 20:
            matrix = "BEER"
        if 81 <= index <= 84:
            sample_id = ""
        else:
            sample_id = f"SAMPLE-{index:03d}"
        if 85 <= index <= 88:
            package = ""
            selected = []
            golden: list[dict[str, Any]] = []
        else:
            if 94 <= index <= 97:
                matrix = "WINE"
                package = "BEER_EXTENDED"
                selected = list(CATALOG[package]["tests"])
            golden = [_golden_result(code, index) for code in selected]
        rows.append({
            "client_request_id": client_request_id,
            "golden_results": golden,
            "matrix": matrix,
            "package": package,
            "qc_control_pass": not (98 <= index <= 100),
            "request_id": request_id,
            "sample_id": sample_id,
            "selected_tests": selected,
        })
    return rows


def load_fixture(fixture_path: Path, manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fixture_path = fixture_path.resolve()
    manifest_path = manifest_path.resolve()
    try:
        fixture_bytes = fixture_path.read_bytes()
        fixture = json.loads(fixture_bytes.decode("utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"fixture/manifest unreadable: {exc}") from exc

    if not isinstance(fixture, dict) or fixture.get("fixture_version") != 1:
        raise ManifestError("unsupported fixture version")
    if fixture.get("synthetic") is not True:
        raise ManifestError("fixture must be explicitly synthetic")
    rows = fixture.get("requests")
    if rows is None:
        rows = _expand_fixture(fixture)
    if not isinstance(rows, list) or len(rows) != 100:
        raise ManifestError("fixture must expand to exactly 100 requests")

    if not isinstance(manifest, dict) or manifest.get("manifest_version") != 1:
        raise ManifestError("unsupported manifest version")
    if manifest.get("demand_id") != DEMAND_ID:
        raise ManifestError("manifest demand_id mismatch")
    if manifest.get("fixture") != fixture_path.name:
        raise ManifestError("manifest fixture filename mismatch")
    expected_fixture_sha = str(manifest.get("fixture_sha256", "")).lower()
    if not HEX64_RE.fullmatch(expected_fixture_sha):
        raise ManifestError("manifest fixture_sha256 malformed")
    if hashlib.sha256(fixture_bytes).hexdigest() != expected_fixture_sha:
        raise ManifestError("fixture SHA-256 mismatch")

    expected_manifest_sha = str(manifest.get("manifest_sha256", "")).lower()
    if not HEX64_RE.fullmatch(expected_manifest_sha):
        raise ManifestError("manifest_sha256 malformed")
    if _manifest_digest(manifest) != expected_manifest_sha:
        raise ManifestError("manifest canonical digest mismatch")

    expected_expanded_sha = str(manifest.get("expanded_requests_sha256", "")).lower()
    if not HEX64_RE.fullmatch(expected_expanded_sha):
        raise ManifestError("manifest expanded_requests_sha256 malformed")
    observed_expanded_sha = sha256_hex(rows)
    if observed_expanded_sha != expected_expanded_sha:
        raise ManifestError("expanded request SHA-256 mismatch")

    if manifest.get("adapters") != "synthetic-read-only":
        raise ManifestError("manifest must bind synthetic-read-only adapters")
    if manifest.get("automatic_release") is not False:
        raise ManifestError("automatic release must remain disabled")
    return rows, manifest


def _strict_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _rounding_matches(value: Any, digits: Any) -> bool:
    if type(digits) is not int or digits < 0 or digits > 9:
        return False
    if not isinstance(value, str) or not value:
        return False
    try:
        observed = Decimal(value)
    except InvalidOperation:
        return False
    quantum = Decimal(1).scaleb(-digits)
    quantized = observed.quantize(quantum, rounding=ROUND_HALF_UP)
    return value == f"{quantized:.{digits}f}"


def _validate_golden_results(row: dict[str, Any], tests: tuple[str, ...]) -> bool:
    results = row.get("golden_results")
    if not isinstance(results, list) or len(results) != len(tests):
        return False
    by_code: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            return False
        code = result.get("test_code")
        if not isinstance(code, str) or code in by_code:
            return False
        by_code[code] = result
    if set(by_code) != set(tests):
        return False

    for code in tests:
        meta = TEST_META.get(code)
        result = by_code[code]
        if meta is None:
            return False
        if result.get("unit") != meta["unit"]:
            return False
        if result.get("method_version") != meta["method_version"]:
            return False
        if result.get("rounding") != meta["rounding"]:
            return False
        if not _rounding_matches(result.get("value"), meta["rounding"]):
            return False
    return True


def _classify(row: dict[str, Any], existing_client_ids: dict[str, str]) -> str:
    sample_id = _strict_text(row.get("sample_id"))
    package = _strict_text(row.get("package"))
    selected_tests = row.get("selected_tests")
    if (
        not sample_id
        or not package
        or not isinstance(selected_tests, list)
        or not selected_tests
        or not all(_strict_text(test) for test in selected_tests)
    ):
        return "MISSING_SAMPLE_TEST_IDENTITY"

    client_request_id = _strict_text(row.get("client_request_id"))
    if not client_request_id:
        return "MISSING_SAMPLE_TEST_IDENTITY"
    if client_request_id in existing_client_ids:
        return "DUPLICATE_CLIENT_ID"

    spec = CATALOG.get(package)
    matrix = _strict_text(row.get("matrix"))
    if (
        spec is None
        or matrix not in spec["matrices"]
        or tuple(selected_tests) != spec["tests"]
        or not _validate_golden_results(row, spec["tests"])
    ):
        return "INCOMPATIBLE_PACKAGE_TEST_SELECTION"

    if row.get("qc_control_pass") is not True:
        return "QC_CONTROL_FAIL"
    return "READY"


def _new_state() -> dict[str, Any]:
    return {
        "processed": {},
        "client_request_ids": {},
        "accessions": {},
        "jobs": {},
        "reports": {},
        "holds": {},
        "events": [],
    }


class BeverageQAQC:
    """In-memory synthetic reconciliation ledger."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = deepcopy(state) if state is not None else _new_state()

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.state)

    def ingest(self, row: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise ReconciliationError("request row must be an object")
        request_id = _strict_text(row.get("request_id"))
        if not request_id:
            raise ReconciliationError("request_id is required")

        payload_sha256 = sha256_hex(row)
        previous = self.state["processed"].get(request_id)
        if previous is not None:
            if previous != payload_sha256:
                raise ReplayPayloadMismatch(
                    f"request_id {request_id} was already bound to different payload bytes"
                )
            return {
                "request_id": request_id,
                "status": "IDEMPOTENT",
                "payload_sha256": payload_sha256,
            }

        reason = _classify(row, self.state["client_request_ids"])
        client_request_id = _strict_text(row.get("client_request_id"))

        # All writes happen only after classification has completed.
        self.state["processed"][request_id] = payload_sha256
        if client_request_id and client_request_id not in self.state["client_request_ids"]:
            self.state["client_request_ids"][client_request_id] = request_id

        if reason != "READY":
            self.state["holds"][request_id] = {
                "request_id": request_id,
                "reason": reason,
                "payload_sha256": payload_sha256,
            }
            self.state["events"].append(
                {"request_id": request_id, "event": "HOLD", "reason": reason}
            )
            return {
                "request_id": request_id,
                "status": "HOLD",
                "reason": reason,
                "payload_sha256": payload_sha256,
            }

        package = row["package"]
        tests = CATALOG[package]["tests"]
        accession_id = f"ACC-{request_id}"
        self.state["accessions"][request_id] = {
            "accession_id": accession_id,
            "request_id": request_id,
            "client_request_id": row["client_request_id"],
            "sample_id": row["sample_id"],
            "matrix": row["matrix"],
            "package": package,
            "payload_sha256": payload_sha256,
        }

        result_by_code = {r["test_code"]: r for r in row["golden_results"]}
        job_ids: list[str] = []
        report_results: list[dict[str, Any]] = []
        for ordinal, test_code in enumerate(tests, start=1):
            job_id = f"{accession_id}-J{ordinal:02d}-{test_code}"
            golden = deepcopy(result_by_code[test_code])
            self.state["jobs"][job_id] = {
                "job_id": job_id,
                "accession_id": accession_id,
                "test_code": test_code,
                "method_version": golden["method_version"],
                "unit": golden["unit"],
                "rounding": golden["rounding"],
                "value": golden["value"],
                "source_payload_sha256": payload_sha256,
            }
            job_ids.append(job_id)
            report_results.append(golden)

        self.state["reports"][request_id] = {
            "report_id": f"RPT-{request_id}",
            "request_id": request_id,
            "accession_id": accession_id,
            "job_ids": job_ids,
            "results": report_results,
            "status": "STAGED_HUMAN_REVIEW",
            "sent": False,
            "source_payload_sha256": payload_sha256,
        }
        self.state["events"].append(
            {"request_id": request_id, "event": "READY", "accession_id": accession_id}
        )
        return {
            "request_id": request_id,
            "status": "READY",
            "accession_id": accession_id,
            "job_ids": job_ids,
            "report_id": f"RPT-{request_id}",
        }

    def ingest_many(self, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.ingest(row) for row in rows]

    def release_report_copy(self, request_id: str, reviewer: str) -> dict[str, Any]:
        report = self.state["reports"].get(request_id)
        if report is None:
            raise ReleaseError("no staged report for request")
        tokens = [token.casefold() for token in re.findall(r"[A-Za-z]+", reviewer)] if isinstance(reviewer, str) else []
        if len(tokens) < 2 or any(token in RESERVED_REVIEWER_TOKENS for token in tokens):
            raise ReleaseError("explicit named-human reviewer is required")
        if report.get("status") != "STAGED_HUMAN_REVIEW" or report.get("sent") is not False:
            raise ReleaseError("report is not in the staged unsent state")
        released = deepcopy(report)
        released["status"] = "RELEASED_BY_NAMED_HUMAN_COPY"
        released["reviewer"] = reviewer.strip()
        released["sent"] = False
        # Deliberately copy-only: this synthetic adapter never mutates the stored
        # staged report into a production/released state.
        return released


def summarize(state: dict[str, Any], first_results: list[dict[str, Any]], replay_results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {"READY": 0, **{reason: 0 for reason in HOLD_REASONS}}
    for result in first_results:
        if result["status"] == "READY":
            counts["READY"] += 1
        else:
            counts[result["reason"]] += 1
    return {
        "demand_id": DEMAND_ID,
        "total": len(first_results),
        **counts,
        "accessions": len(state["accessions"]),
        "jobs": len(state["jobs"]),
        "reports": len(state["reports"]),
        "holds": len(state["holds"]),
        "events": len(state["events"]),
        "replay_idempotent": sum(result["status"] == "IDEMPOTENT" for result in replay_results),
        "automatic_release": False,
        "provider_writes": 0,
        "customer_writes": 0,
        "external_sends": 0,
        "state_sha256": sha256_hex(state),
    }


def validate_acceptance(summary: dict[str, Any], manifest: dict[str, Any]) -> None:
    expected = manifest.get("expected")
    if not isinstance(expected, dict):
        raise ManifestError("manifest expected contract missing")
    for key, wanted in expected.items():
        if summary.get(key) != wanted:
            raise ReconciliationError(
                f"acceptance mismatch for {key}: observed={summary.get(key)!r} expected={wanted!r}"
            )
    if summary["replay_idempotent"] != summary["total"]:
        raise ReconciliationError("full replay was not idempotent")
    if any(summary[key] != 0 for key in ("provider_writes", "customer_writes", "external_sends")):
        raise ReconciliationError("read-only adapter boundary violated")


def run_fixture(fixture_path: Path, manifest_path: Path) -> dict[str, Any]:
    rows, manifest = load_fixture(fixture_path, manifest_path)
    adapter = BeverageQAQC()
    first = adapter.ingest_many(rows)
    frozen = adapter.snapshot()
    replay = adapter.ingest_many(rows)
    if adapter.snapshot() != frozen:
        raise ReconciliationError("replay mutated ledger state")
    summary = summarize(adapter.state, first, replay)
    validate_acceptance(summary, manifest)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthetic MSU Denver beverage QA/QC reconciliation")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_fixture(args.fixture, args.manifest)
    except ReconciliationError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
