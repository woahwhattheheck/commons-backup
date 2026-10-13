#!/usr/bin/env python3
"""AT-GROK-ADAPTER-EVIDENCE-01 — four-instrument OEM evidence ledger.

Official command:
    python3 at_grok_adapter_evidence.py

Prints the machine-readable uncertainty ledger and exits 0 only when
the four buyer instruments are present, UNKNOWN vs documented framing
is honest, Seivers spelling is preserved, and no guessed schema or
invented field names exist.

State remains NOT_READY / HOLD / BUILD-AND-VERIFY. cash_usd=0.
Cite private AquaTrace main e380a58 only. Do not clone aquatrace-lims.
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "AT-GROK-ADAPTER-EVIDENCE-01"
SCHEMA = "commons-at-grok-adapter-evidence/v1"
STATE = "NOT_READY / HOLD / BUILD-AND-VERIFY"
LEDGER_NAME = "uncertainty_ledger.json"
PACK_DIR = Path(__file__).resolve().parent / "at_grok_adapter_evidence"
LEDGER_PATH = PACK_DIR / LEDGER_NAME

BUYER_LABELS = (
    "Metrohm Eco IC",
    "Seivers M5310C",
    "Seal Analytical AQ300",
    "Perkin Elmer PinAAcle 900Z",
)

FRAMING_BY_LABEL = {
    "Metrohm Eco IC": "DOCUMENTED_PARTIAL",
    "Seivers M5310C": "TRANSPORT_NAMED",
    "Seal Analytical AQ300": "TRANSPORT_NAMED",
    "Perkin Elmer PinAAcle 900Z": "UNKNOWN",
}

FORBIDDEN_SCHEMA_KEYS = (
    "export_schema",
    "guessed_schema",
    "sample_record",
    "xml_tags",
    "csv_columns",
    "invented_fields",
    "fixture_bytes",
    "fixture_path",
    "modbus_map",
    "register_map",
)

ALLOWED_INSTRUMENT_KEYS = {
    "buyer_label",
    "schema_status",
    "schema_reason",
    "framing_status",
    "fixture",
    "oem_trademark_spelling",
    "spelling_rule",
    "documented_facts",
    "unknowns",
    "verbatim_names",
    "citations",
}

ALLOWED_VERBATIM_KIND = {
    "filename_option_and_txt_header",
    "filename_option",
    "sample_identification_source",
    "xml_export_section",
}

METROHM_VERBATIM = (
    "Determination ID",
    "Sample identification",
    "Ident",
    "Info 1",
    "Info 2",
    "Info 3",
    "Info 4",
    "Value 1",
    "Value 2",
    "Value 3",
    "Value 4",
    "Determination report",
    "Program name",
    "Program version",
    "Build number",
    "Determination data",
    "Method data",
    "Sample data",
    "Common variables",
    "Component results",
    "Single results",
    "Monitored results",
    "Method parameters",
    "Statistics results",
    "Device data",
    "Analysis data",
    "Columns data",
    "System data",
    "User name (abbreviation)",
    "User name (full name)",
    "Client name",
    "License code",
)

OFF_LIMITS = (
    "AT-GROK-CMDP-EVIDENCE-01",
    "AT-GROK-OPS-ACCEPTANCE-01",
    "corrigan-specialty-fuel-blend-dossier-lims-01",
    "torrent-workorder-commissioning-lims-01",
    "bsk-multilab-accession-parity-lims-01",
    "chemtechford-short-hold-intake-lims-01",
    "aquatrace-work-order-c-reporting-offline-20260831-01",
    "aquatrace-work-order-b-production-foundation-20260831-01",
    "aquatrace-work-order-f-release-readiness-20260831-01",
    "sanair-asbestos-coc-router-lims-01",
    "wadsworth-five-site-consolidation-lims-01",
    "highpower-ssf-receiving-gate-lims-01",
    "westpak-scope-capacity-routing-lims-01",
    "ddl-crosssite-method-proficiency-lims-01",
    "sharp-rtu-vial-isolator-lineage-lims-01",
    "canyon-multisite-regulated-intake-lims-01",
    "pcl-scope-sla-routing-lims-01",
    "organabio-multisite-donor-coa-lims-01",
    "billings-bid-1421-instrument-fixtures-20260831-01",
)


class LedgerError(ValueError):
    """Honest-ledger contract broken."""


def load_ledger(path: Path | None = None) -> dict[str, Any]:
    target = path or LEDGER_PATH
    raw = target.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise LedgerError("ledger is not an object")
    return data


def ledger_sha256(path: Path | None = None) -> str:
    target = path or LEDGER_PATH
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _fail(failures: list[str], message: str) -> None:
    failures.append(message)


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    """Return honesty failures. Empty list means the ledger is fail-closed clean."""
    failures: list[str] = []
    if ledger.get("id") != DEMAND_ID:
        _fail(failures, f"id must stay {DEMAND_ID}")
    if ledger.get("id") in OFF_LIMITS:
        _fail(failures, "this leftover reminted an off-limits id")
    if ledger.get("schema") != SCHEMA:
        _fail(failures, f"schema must stay {SCHEMA}")
    if ledger.get("state") != STATE:
        _fail(failures, "state must remain NOT_READY / HOLD / BUILD-AND-VERIFY")
    if ledger.get("cash_usd") != 0:
        _fail(failures, "cash_usd must be 0")
    if ledger.get("private_aquatrace_lims_cite") != "e380a58":
        _fail(failures, "private AquaTrace cite must stay e380a58")
    if ledger.get("city_contact") is not False:
        _fail(failures, "city_contact must be false")
    if ledger.get("grok_com") != "dry":
        _fail(failures, "grok.com must stay dry")

    labels = ledger.get("buyer_labels")
    if labels != list(BUYER_LABELS):
        _fail(failures, "buyer_labels must be the four exact buyer strings in order")

    instruments = ledger.get("instruments")
    if not isinstance(instruments, list) or len(instruments) != 4:
        _fail(failures, "exactly four instruments are required")
        return failures

    seen: list[str] = []
    schema_unknown = 0
    schema_documented = 0
    framing_partial = 0
    framing_transport = 0
    framing_unknown = 0
    fixtures = 0

    for inst in instruments:
        if not isinstance(inst, dict):
            _fail(failures, "instrument row is not an object")
            continue
        extra = set(inst) - ALLOWED_INSTRUMENT_KEYS
        if extra:
            _fail(failures, f"invented or guessed instrument keys: {sorted(extra)}")
        for banned in FORBIDDEN_SCHEMA_KEYS:
            if banned in inst:
                _fail(failures, f"guessed schema key present: {banned}")
        label = inst.get("buyer_label")
        seen.append(label if isinstance(label, str) else "")
        if inst.get("schema_status") != "UNKNOWN":
            _fail(
                failures,
                f"{label}: schema_status must stay UNKNOWN until a public OEM record schema exists",
            )
            schema_documented += 1
        else:
            schema_unknown += 1
        reason = inst.get("schema_reason")
        if not isinstance(reason, str) or "BUYER OR VENDOR SAMPLE REQUIRED" not in reason:
            _fail(failures, f"{label}: schema_reason must include BUYER OR VENDOR SAMPLE REQUIRED")
        if not isinstance(reason, str) or not reason.startswith("UNKNOWN"):
            _fail(failures, f"{label}: schema_reason must start with UNKNOWN")
        expected_framing = FRAMING_BY_LABEL.get(label)
        if inst.get("framing_status") != expected_framing:
            _fail(failures, f"{label}: framing_status must be {expected_framing}")
        if inst.get("framing_status") == "DOCUMENTED_PARTIAL":
            framing_partial += 1
        elif inst.get("framing_status") == "TRANSPORT_NAMED":
            framing_transport += 1
        elif inst.get("framing_status") == "UNKNOWN":
            framing_unknown += 1
        if inst.get("fixture") is not None:
            _fail(
                failures,
                f"{label}: export fixture is forbidden while schema_status is UNKNOWN",
            )
            fixtures += 1
        names = inst.get("verbatim_names")
        if not isinstance(names, list):
            _fail(failures, f"{label}: verbatim_names must be a list")
            names = []
        citations = inst.get("citations")
        if not isinstance(citations, list) or not citations:
            _fail(failures, f"{label}: at least one OEM citation is required")
            citations = []
        for cite in citations:
            if not isinstance(cite, dict):
                _fail(failures, f"{label}: citation is not an object")
                continue
            url = cite.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                _fail(failures, f"{label}: citation url must be https OEM/public")
            if not cite.get("page_or_section"):
                _fail(failures, f"{label}: citation missing page/section")
            if not cite.get("verbatim"):
                _fail(failures, f"{label}: citation missing verbatim excerpt")
        if label == "Metrohm Eco IC":
            have = [row.get("name") for row in names if isinstance(row, dict)]
            if have != list(METROHM_VERBATIM):
                _fail(failures, "Metrohm Eco IC verbatim names drifted from the cited OEM set")
            for row in names:
                if not isinstance(row, dict):
                    _fail(failures, "Metrohm verbatim row is not an object")
                    continue
                if row.get("kind") not in ALLOWED_VERBATIM_KIND:
                    _fail(failures, f"Metrohm verbatim kind not cited: {row.get('kind')}")
                if not str(row.get("source_url", "")).startswith("https://www.metrohm.com/"):
                    _fail(failures, "Metrohm verbatim names must cite metrohm.com")
                if not row.get("page_or_section"):
                    _fail(failures, "Metrohm verbatim missing page/section")
        else:
            if names:
                _fail(
                    failures,
                    f"{label}: no public export field names are documented; verbatim_names must stay empty",
                )
        if label == "Seivers M5310C":
            if inst.get("oem_trademark_spelling") != "Sievers M5310 C":
                _fail(failures, "OEM trademark spelling must stay Sievers M5310 C as cited")
            if "Seivers" not in str(inst.get("spelling_rule", "")):
                _fail(failures, "Seivers spelling rule missing")

    if seen != list(BUYER_LABELS):
        _fail(failures, "instrument buyer_label order/values drifted from exact buyer labels")
    if any(label == "Sievers M5310C" for label in seen):
        _fail(failures, "buyer spelling Seivers was normalized to Sievers")
    if not any(label == "Seivers M5310C" for label in seen):
        _fail(failures, "buyer label Seivers M5310C is missing")

    counts = ledger.get("counts")
    if not isinstance(counts, dict):
        _fail(failures, "counts object missing")
    else:
        expected = {
            "instruments": 4,
            "schema_unknown": 4,
            "schema_documented": 0,
            "framing_documented_partial": 1,
            "framing_transport_named": 2,
            "framing_unknown": 1,
            "export_fixtures": 0,
        }
        if counts != expected:
            _fail(failures, f"counts drifted from honest UNKNOWN ledger: {counts}")
        if schema_unknown != 4 or schema_documented != 0:
            _fail(failures, "instrument schema counts are not 4 UNKNOWN / 0 documented")
        if framing_partial != 1 or framing_transport != 2 or framing_unknown != 1:
            _fail(failures, "framing honesty counts drifted")
        if fixtures != 0:
            _fail(failures, "export fixtures must stay 0 while schemas are UNKNOWN")

    off = ledger.get("off_limits")
    if not isinstance(off, list) or not set(OFF_LIMITS).issubset(off):
        _fail(failures, "off_limits must keep the named leftover freeze list")
    if DEMAND_ID in (off or []):
        _fail(failures, "this leftover listed itself as off-limits")

    claims = ledger.get("not_claims")
    for banned in ("production", "spend", "certification", "compliance"):
        if not isinstance(claims, list) or banned not in claims:
            _fail(failures, f"not_claims must include {banned}")

    packed = json.dumps(ledger.get("instruments"), sort_keys=True)
    if '"Sievers M5310C"' in packed:
        _fail(failures, "buyer label Seivers was rewritten to Sievers inside instruments")
    return failures


def validate_or_raise(ledger: dict[str, Any]) -> dict[str, Any]:
    failures = validate_ledger(ledger)
    if failures:
        raise LedgerError("; ".join(failures))
    return ledger


def guessed_schema_probe(ledger: dict[str, Any]) -> list[str]:
    """Encode the fail-closed rule: a later guessed schema must not pass."""
    poisoned = deepcopy(ledger)
    row = poisoned["instruments"][1]
    row["schema_status"] = "DOCUMENTED"
    row["export_schema"] = {"fields": ["SampleID", "TOC_ppb", "Timestamp"]}
    row["verbatim_names"] = [
        {
            "name": "SampleID",
            "kind": "guessed",
            "source_url": "https://example.invalid/guessed",
            "page_or_section": "none",
        }
    ]
    return validate_ledger(poisoned)


def sievers_normalization_probe(ledger: dict[str, Any]) -> list[str]:
    poisoned = deepcopy(ledger)
    poisoned["buyer_labels"][1] = "Sievers M5310C"
    poisoned["instruments"][1]["buyer_label"] = "Sievers M5310C"
    return validate_ledger(poisoned)


def render_table(ledger: dict[str, Any]) -> str:
    lines = [
        f"id={ledger['id']}",
        f"state={ledger['state']}",
        f"cash_usd={ledger['cash_usd']}",
        f"private_cite=aquatrace-lims@{ledger['private_aquatrace_lims_cite']}",
        "UNKNOWN vs documented: schema 4 UNKNOWN / 0 documented; framing 1 DOCUMENTED_PARTIAL / 2 TRANSPORT_NAMED / 1 UNKNOWN; fixtures 0",
        "",
        f"{'buyer_label':<28} {'schema':<10} {'framing':<20} fixture verbatim",
        "-" * 88,
    ]
    for inst in ledger["instruments"]:
        names = inst.get("verbatim_names") or []
        lines.append(
            f"{inst['buyer_label']:<28} {inst['schema_status']:<10} {inst['framing_status']:<20} {inst['fixture']!s:<7} {len(names)}"
        )
        lines.append(f"  reason: {inst['schema_reason']}")
    lines.append("")
    lines.append("Official command: python3 at_grok_adapter_evidence.py")
    lines.append("Binary: python3 test_at_grok_adapter_evidence.py")
    return "\n".join(lines)


def run(path: Path | None = None) -> dict[str, Any]:
    ledger = validate_or_raise(load_ledger(path))
    digest = ledger_sha256(path)
    out = deepcopy(ledger)
    out["ledger_sha256"] = digest
    out["ledger_path"] = str((path or LEDGER_PATH).as_posix())
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else None
    try:
        result = run(path)
    except (OSError, json.JSONDecodeError, LedgerError) as exc:
        sys.stderr.write(f"AT-GROK-ADAPTER-EVIDENCE-01 FAIL\n{exc}\n")
        return 1
    sys.stdout.write(render_table(result) + "\n\n")
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
