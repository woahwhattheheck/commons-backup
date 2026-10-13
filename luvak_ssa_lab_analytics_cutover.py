#!/usr/bin/env python3
"""Luvak–SSA materials accession/report cutover LIMS.

Accepted quote → submission form → physical package → optional CoC.
Material/method revision freeze. Interstitial-gas/metals result hashes.
Staged report across the Scientific Safety Alliance Lab Analytics cutover.
Named-human release only. Holds never open a test or report stage.

Demand: luvak-ssa-lab-analytics-cutover-lims-01
Buyer: Dean Gaskill / Luvak Laboratories

Public intake facts (luvak.com/faqs):
- Accept the quote, then complete a Sample Submission form
- Optional Chain of Custody form
- Email/fax paperwork and ship a physical copy with the sample
- Gases: solid preferred, 3–5 g typical; powders accepted
- Official report emailed/faxed; optional hard copy

AquaTrace HOLD / BUILD-AND-VERIFY. Synthetic/read-only adapters.
Materials-quality evidence only. No qualification decision.
PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "luvak-ssa-lab-analytics-cutover-lims-01"
SCHEMA = "commons-luvak-ssa-lab-analytics-cutover-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
HUMAN_RELEASER = "RELEASER"
FORBIDDEN_ACTORS = frozenset({"", "SYSTEM", "BOT", "AUTONOMOUS", "AUTO", "MACHINE"})

HOLD_CODES = (
    "MISSING_ACCEPTED_QUOTE",
    "DUPLICATE_SAMPLE_ID",
    "FORM_PACKAGE_MISMATCH",
    "METHOD_REVISION_MISMATCH",
)

MATERIALS = (
    ("Ti-6Al-4V", "titanium_alloy"),
    ("316L", "stainless"),
    ("Inconel 718", "nickel_superalloy"),
    ("Zr-2.5Nb", "zirconium_alloy"),
    ("17-4PH", "stainless"),
    ("Al 7075", "aluminum_alloy"),
    ("CP-Ti Grade 2", "titanium"),
    ("Haynes 282", "nickel_superalloy"),
)

METHODS: dict[str, dict[str, Any]] = {
    "INTERSTITIAL_GAS": {
        "revision": "IGA-2026.1",
        "analytes": ["oxygen", "nitrogen", "hydrogen"],
        "family": "interstitial_gas",
    },
    "CARBON_SULFUR": {
        "revision": "CS-2026.1",
        "analytes": ["carbon", "sulfur"],
        "family": "carbon_sulfur",
    },
    "METALS": {
        "revision": "MET-2026.1",
        "analytes": ["iron", "nickel", "chromium", "molybdenum"],
        "family": "metals",
    },
    "WET_CHEMISTRY": {
        "revision": "WC-2026.1",
        "analytes": ["acid_soluble"],
        "family": "wet_chemistry",
    },
}

METHOD_NAMES = ("INTERSTITIAL_GAS", "CARBON_SULFUR", "METALS", "WET_CHEMISTRY")


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "accepted"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def accession_id(sample_id: str, method: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "method": method,
        }
    )
    return "LVK-" + digest[:12]


def _method_name(index: int) -> str:
    return METHOD_NAMES[(index - 1) % len(METHOD_NAMES)]


def _material(index: int) -> tuple[str, str]:
    return MATERIALS[(index - 1) % len(MATERIALS)]


def _valid_row(index: int) -> dict[str, Any]:
    method = _method_name(index)
    spec = METHODS[method]
    material, family = _material(index)
    sample_id = f"LVK-{index:04d}"
    row: dict[str, Any] = {
        "row_id": f"R{index:03d}",
        "sample_id": sample_id,
        "quote_id": f"Q-{index:04d}",
        "quote_accepted": True,
        "form_id": f"F-{index:04d}",
        "package_id": f"P-{index:04d}",
        "form_sample_id": sample_id,
        "package_sample_id": sample_id,
        "material": material,
        "material_family": family,
        "method": method,
        "quote_method_revision": spec["revision"],
        "form_method_revision": spec["revision"],
        "mass_g": 4.0,
        "cutover_lane": "SSA_LAB_ANALYTICS" if index % 2 == 0 else "LUVAK_LEGACY",
        "coc": None,
    }
    if index % 3 == 0:
        row["coc"] = {"coc_id": f"COC-{index:04d}", "sample_id": sample_id}
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """100-row PASS fixture for luvak-ssa-lab-analytics-cutover-lims-01.

    80 valid READY shipments plus 20 exact HOLDs:
    8 MISSING_ACCEPTED_QUOTE, 4 DUPLICATE_SAMPLE_ID,
    4 FORM_PACKAGE_MISMATCH, 4 METHOD_REVISION_MISMATCH.
    """
    rows = [_valid_row(i) for i in range(1, 81)]

    for i in range(81, 89):
        row = _valid_row(i)
        row["quote_id"] = ""
        row["quote_accepted"] = False
        rows.append(row)

    for offset, i in enumerate(range(89, 93), start=1):
        row = _valid_row(offset)
        row["row_id"] = f"R{i:03d}"
        row["quote_id"] = f"Q-{i:04d}"
        row["form_id"] = f"F-{i:04d}"
        row["package_id"] = f"P-{i:04d}"
        rows.append(row)

    for i in range(93, 97):
        row = _valid_row(i)
        row["package_sample_id"] = f"{row['sample_id']}-PKG"
        rows.append(row)

    for i in range(97, 101):
        row = _valid_row(i)
        row["form_method_revision"] = "IGA-2025.9"
        rows.append(row)

    if len(rows) != 100:
        raise RuntimeError("acceptance fixture must be exactly 100 rows, got %s" % len(rows))
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "ready": {},
        "holds": [],
        "events": [],
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def _quote_payload(row: dict[str, Any], sample_id: str) -> dict[str, Any]:
    return {
        "quote_id": _text(row.get("quote_id")),
        "quote_accepted": True,
        "sample_id": sample_id,
        "method": _text(row.get("method")),
        "method_revision": _text(row.get("quote_method_revision")),
        "material": _text(row.get("material")),
    }


def _form_payload(row: dict[str, Any], sample_id: str) -> dict[str, Any]:
    return {
        "form_id": _text(row.get("form_id")),
        "sample_id": sample_id,
        "method": _text(row.get("method")),
        "method_revision": _text(row.get("form_method_revision")),
        "material": _text(row.get("material")),
        "mass_g": row.get("mass_g"),
    }


def _package_payload(row: dict[str, Any], sample_id: str) -> dict[str, Any]:
    return {
        "package_id": _text(row.get("package_id")),
        "sample_id": sample_id,
        "package_sample_id": _text(row.get("package_sample_id")) or sample_id,
        "material": _text(row.get("material")),
        "mass_g": row.get("mass_g"),
    }


def _coc_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    coc = row.get("coc")
    if not coc:
        return None
    if not isinstance(coc, dict):
        return None
    coc_id = _text(coc.get("coc_id"))
    sample_id = _text(coc.get("sample_id"))
    if not coc_id:
        return None
    return {"coc_id": coc_id, "sample_id": sample_id}


def _method_payload(row: dict[str, Any]) -> dict[str, Any]:
    method = _text(row.get("method"))
    spec = METHODS.get(method) or {}
    return {
        "method": method,
        "method_revision": _text(row.get("quote_method_revision")),
        "analytes": list(spec.get("analytes") or []),
        "material": _text(row.get("material")),
        "family": spec.get("family"),
    }


def _synthetic_result(sample_id: str, method: str) -> dict[str, Any]:
    spec = METHODS[method]
    seed = int(sha256_hex({"sample_id": sample_id, "method": method})[:8], 16)
    values = {}
    for offset, analyte in enumerate(spec["analytes"]):
        values[analyte] = round((seed % 997 + offset * 13) / 10.0, 3)
    return {
        "sample_id": sample_id,
        "method": method,
        "family": spec["family"],
        "values": values,
        "kind": "MATERIALS_QUALITY_EVIDENCE",
        "qualification_decision": None,
    }


def _staged_report(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": record["sample_id"],
        "accession_id": record["accession_id"],
        "cutover_lane": record["cutover_lane"],
        "quote_hash": record["quote_hash"],
        "form_hash": record["form_hash"],
        "coc_hash": record["coc_hash"],
        "method_hash": record["method_hash"],
        "result_hash": record["result_hash"],
        "stage": "STAGED",
        "qualification_decision": None,
        "interfaces": "SIMULATED",
    }


def classify_shipment(row: dict[str, Any], seen_sample_ids: set[str]) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    quote_id = _text(row.get("quote_id"))
    quote_accepted = _flag(row.get("quote_accepted"))
    form_sample_id = _text(row.get("form_sample_id")) or sample_id
    package_sample_id = _text(row.get("package_sample_id")) or sample_id
    quote_rev = _text(row.get("quote_method_revision"))
    form_rev = _text(row.get("form_method_revision"))
    method = _text(row.get("method"))

    if not quote_id or not quote_accepted:
        return {
            "ok": False,
            "code": "MISSING_ACCEPTED_QUOTE",
            "sample_id": sample_id or None,
            "row_id": _text(row.get("row_id")),
        }
    if sample_id and sample_id in seen_sample_ids:
        return {
            "ok": False,
            "code": "DUPLICATE_SAMPLE_ID",
            "sample_id": sample_id,
            "row_id": _text(row.get("row_id")),
        }
    if form_sample_id != package_sample_id:
        return {
            "ok": False,
            "code": "FORM_PACKAGE_MISMATCH",
            "sample_id": sample_id or None,
            "row_id": _text(row.get("row_id")),
            "form_sample_id": form_sample_id,
            "package_sample_id": package_sample_id,
        }
    if not quote_rev or not form_rev or quote_rev != form_rev:
        return {
            "ok": False,
            "code": "METHOD_REVISION_MISMATCH",
            "sample_id": sample_id or None,
            "row_id": _text(row.get("row_id")),
            "quote_method_revision": quote_rev or None,
            "form_method_revision": form_rev or None,
        }
    if not sample_id or method not in METHODS:
        return {
            "ok": False,
            "code": "MISSING_ACCEPTED_QUOTE",
            "sample_id": sample_id or None,
            "row_id": _text(row.get("row_id")),
        }
    return {
        "ok": True,
        "sample_id": sample_id,
        "method": method,
        "row_id": _text(row.get("row_id")),
        "accession_id": accession_id(sample_id, method),
        "cutover_lane": _text(row.get("cutover_lane")) or "LUVAK_LEGACY",
        "quote": _quote_payload(row, sample_id),
        "form": _form_payload(row, form_sample_id),
        "package": _package_payload(row, package_sample_id),
        "coc": _coc_payload(row),
        "method_payload": _method_payload(row),
    }


def _hold_record(verdict: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_id": verdict.get("row_id"),
        "sample_id": verdict.get("sample_id"),
        "state": "HOLD",
        "hold_code": verdict["code"],
        "test_stage": None,
        "report_stage": None,
        "result_hash": None,
        "report_hash": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    row_id = _text(row.get("row_id"))
    existing_ready = journal["ready"].get(sample_id)
    if existing_ready is not None and existing_ready.get("row_id") == row_id:
        _event(journal, "REPLAY_NOOP", {"kind": "READY", "sample_id": sample_id})
        return {"kind": "REPLAY_NOOP", "state": "READY", "sample_id": sample_id}

    seen = set(journal["ready"])
    verdict = classify_shipment(row, seen)
    if not verdict["ok"]:
        hold = _hold_record(verdict)
        fingerprint = sha256_hex(
            {
                "row_id": hold["row_id"],
                "sample_id": hold["sample_id"],
                "hold_code": hold["hold_code"],
            }
        )
        existing = {
            sha256_hex(
                {
                    "row_id": item["row_id"],
                    "sample_id": item["sample_id"],
                    "hold_code": item["hold_code"],
                }
            )
            for item in journal["holds"]
        }
        if fingerprint in existing:
            _event(
                journal,
                "REPLAY_NOOP",
                {"kind": "HOLD", "sample_id": hold["sample_id"], "hold_code": hold["hold_code"]},
            )
            return {"kind": "REPLAY_NOOP", "state": "HOLD", **hold}
        journal["holds"].append(hold)
        _event(journal, "HOLD", {"sample_id": hold["sample_id"], "hold_code": hold["hold_code"]})
        return {"kind": "HOLD", "duplicate": False, **hold}

    sample_id = verdict["sample_id"]
    existing_ready = journal["ready"].get(sample_id)
    if existing_ready is not None:
        _event(journal, "REPLAY_NOOP", {"kind": "READY", "sample_id": sample_id})
        return {"kind": "REPLAY_NOOP", "state": "READY", "sample_id": sample_id}

    quote_hash = sha256_hex(verdict["quote"])
    form_hash = sha256_hex(verdict["form"])
    coc_hash = sha256_hex(verdict["coc"]) if verdict["coc"] else None
    method_hash = sha256_hex(verdict["method_payload"])
    result = _synthetic_result(sample_id, verdict["method"])
    result_hash = sha256_hex(result)
    record = {
        "accession_id": verdict["accession_id"],
        "sample_id": sample_id,
        "row_id": verdict["row_id"],
        "method": verdict["method"],
        "state": "READY",
        "cutover_lane": verdict["cutover_lane"],
        "quote_hash": quote_hash,
        "form_hash": form_hash,
        "coc_hash": coc_hash,
        "method_hash": method_hash,
        "result_hash": result_hash,
        "report_hash": None,
        "test_stage": "HASHED",
        "report_stage": "STAGED",
        "released": False,
        "released_by": None,
        "result": result,
        "qualification_decision": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "adapters": "SYNTHETIC_READ_ONLY",
    }
    record["report"] = _staged_report(record)
    record["report_hash"] = sha256_hex(record["report"])
    journal["ready"][sample_id] = record
    _event(
        journal,
        "READY",
        {
            "accession_id": record["accession_id"],
            "sample_id": sample_id,
            "cutover_lane": record["cutover_lane"],
        },
    )
    return {"kind": "READY", "sample_id": sample_id, "accession_id": record["accession_id"]}


def release_report(
    journal: dict[str, Any],
    sample_id: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["ready"].get(sample_id)
    if record is None:
        held = next((item for item in journal["holds"] if item.get("sample_id") == sample_id), None)
        if held is not None:
            _event(
                journal,
                "RELEASE_DENIED",
                {"sample_id": sample_id, "code": "HOLD_HAS_NO_REPORT_STAGE"},
            )
            return {"ok": False, "code": "HOLD_HAS_NO_REPORT_STAGE", "state": "HOLD"}
        return {"ok": False, "code": "UNKNOWN_SAMPLE"}
    role = _text(actor_role).upper()
    name = _text(actor)
    if role != HUMAN_RELEASER or name.upper() in FORBIDDEN_ACTORS or not name:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "sample_id": sample_id,
                "code": "NAMED_HUMAN_RELEASE_ONLY",
                "actor_role": role or None,
            },
        )
        return {
            "ok": False,
            "code": "NAMED_HUMAN_RELEASE_ONLY",
            "report_stage": record["report_stage"],
        }
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_stage": "RELEASED"}
    record["released"] = True
    record["released_by"] = name
    record["report_stage"] = "RELEASED"
    record["report"] = {**record["report"], "stage": "RELEASED", "released_by": name}
    record["report_hash"] = sha256_hex(record["report"])
    _event(journal, "RELEASED", {"sample_id": sample_id, "released_by": name})
    return {"ok": True, "duplicate": False, "report_stage": "RELEASED"}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = []
    for sample_id in journal["ready"]:
        autonomous.append(
            release_report(journal, sample_id, actor_role="SYSTEM", actor="autonomous")
        )
    ready_ids = set(journal["ready"])
    for hold in journal["holds"]:
        sample_id = hold.get("sample_id")
        if sample_id and sample_id not in ready_ids:
            autonomous.append(
                release_report(
                    journal,
                    sample_id,
                    actor_role="RELEASER",
                    actor="reviewer-1",
                )
            )

    ready = sorted(journal["ready"].values(), key=lambda item: item["sample_id"])
    holds = deepcopy(journal["holds"])
    hold_codes = sorted(item["hold_code"] for item in holds)
    hold_counts = {code: hold_codes.count(code) for code in HOLD_CODES}

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "ready": len(ready),
        "hold": len(holds),
        "hold_codes": hold_codes,
        "hold_counts": hold_counts,
        "ready_ids": [item["sample_id"] for item in ready],
        "accession_ids": [item["accession_id"] for item in ready],
        "released_reports": sum(1 for item in ready if item["released"]),
        "staged_reports": sum(1 for item in ready if item["report_stage"] == "STAGED"),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "records": ready,
        "holds": holds,
        "interface_live": False,
        "interfaces": "SIMULATED",
        "adapters": "SYNTHETIC_READ_ONLY",
        "autonomous_certification": False,
        "autonomous_release": False,
        "qualification_decision": None,
        "materials_quality_evidence_only": True,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before_ready = set(journal["ready"])
    before_holds = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["ready"]) - before_ready
    return {
        "added_ready": sorted(added),
        "added_ready_count": len(added),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "ready_count": len(journal["ready"]),
        "hold_count": len(journal["holds"]),
    }


def _ready_hashes_ok(record: dict[str, Any]) -> bool:
    required = ("quote_hash", "form_hash", "method_hash", "result_hash", "report_hash")
    if any(not record.get(key) or len(str(record.get(key))) != 64 for key in required):
        return False
    coc = record.get("coc_hash")
    if coc is not None and len(str(coc)) != 64:
        return False
    return True


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != 100:
        failures.append("input_rows!=100")
    if result.get("ready") != 80:
        failures.append("ready!=80")
    if result.get("hold") != 20:
        failures.append("hold!=20")
    expected_counts = {
        "MISSING_ACCEPTED_QUOTE": 8,
        "DUPLICATE_SAMPLE_ID": 4,
        "FORM_PACKAGE_MISMATCH": 4,
        "METHOD_REVISION_MISMATCH": 4,
    }
    if result.get("hold_counts") != expected_counts:
        failures.append("hold_counts")
    if len(set(result.get("ready_ids") or [])) != 80:
        failures.append("ready_ids_not_unique")
    if len(set(result.get("accession_ids") or [])) != 80:
        failures.append("accession_ids_not_unique")
    if result.get("released_reports") != 0:
        failures.append("released_reports!=0")
    if result.get("staged_reports") != 80:
        failures.append("staged_reports!=80")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("adapters") != "SYNTHETIC_READ_ONLY":
        failures.append("adapters")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if result.get("qualification_decision") is not None:
        failures.append("qualification_decision")
    if not result.get("materials_quality_evidence_only"):
        failures.append("materials_quality_evidence_only")
    for record in result.get("records") or []:
        if record.get("state") != "READY":
            failures.append("ready_state")
            break
        if record.get("test_stage") != "HASHED" or record.get("report_stage") != "STAGED":
            failures.append("ready_stages")
            break
        if not _ready_hashes_ok(record):
            failures.append("ready_hashes")
            break
        if record.get("qualification_decision") is not None:
            failures.append("ready_qualification")
            break
    for hold in result.get("holds") or []:
        if hold.get("state") != "HOLD":
            failures.append("hold_state")
            break
        if hold.get("test_stage") is not None or hold.get("report_stage") is not None:
            failures.append("hold_opened_stage")
            break
        if hold.get("result_hash") is not None or hold.get("report_hash") is not None:
            failures.append("hold_result_or_report_hash")
            break
        if hold.get("hold_code") not in HOLD_CODES:
            failures.append("unknown_hold_code")
            break
    denied = [item.get("code") for item in result.get("autonomous_release_effects") or []]
    if not denied or any(
        code not in {"NAMED_HUMAN_RELEASE_ONLY", "HOLD_HAS_NO_REPORT_STAGE"} for code in denied
    ):
        failures.append("autonomous_release_not_denied")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    if replay.get("added_ready_count") != 0:
        failures.append("replay_added_ready")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "ready": first.get("ready"),
        "hold": first.get("hold"),
        "hold_counts": first.get("hold_counts"),
        "staged_reports": first.get("staged_reports"),
        "released_reports": first.get("released_reports"),
        "replay_added_ready": replay.get("added_ready_count"),
        "replay_added_holds": replay.get("added_holds"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
