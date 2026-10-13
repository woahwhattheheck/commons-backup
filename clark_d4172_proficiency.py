#!/usr/bin/env python3
"""Clark Testing ASTM D4172 Four-Ball wear proficiency + customer-CoA lane.

Demand: clark-d4172-proficiency-lims-01
Buyer pairing: Clark Testing / Paul Heffernan

Blinded participant/sample identities until a named human disposes a
READY_FOR_HUMAN set. Replicate control, method versions, and fixture r/R
limits are evaluated deterministically. Adapters stay simulated/read-only.

HOLD / BUILD-AND-VERIFY. Synthetic/deidentified fixtures only.
No production writes, outreach, prospect-facing demo, or automatic release.

Public method facts used as fixture constants (not a copy of the ASTM text):
- Procedure A: 75 C, 1200 rpm, 60 min, 147 N
- Procedure B: 75 C, 1200 rpm, 60 min, 392 N
- Wear-scar diameter is the mean of six measurements, reported to 0.01 mm
- Fixture QC: r = 0.12 mm, R = 0.28 mm
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any

DEMAND_ID = "clark-d4172-proficiency-lims-01"
SCHEMA = "commons-clark-d4172-proficiency-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
CYCLE = "2026-Q3-SYN"
METHOD_VERSION = "D4172-21"
FORMULA_ID = "d4172-wsd-six-measurement-mean/v1"
FIXTURE_SEED = "clark-d4172-proficiency-lims-01|2026-Q3-SYN|v1"
REQUIRED_REPLICATES = 2
MEASUREMENTS_PER_RUN = 6
QUANT = Decimal("0.01")
R_REPEATABILITY = Decimal("0.12")
R_REPRODUCIBILITY = Decimal("0.28")
HUMAN_RELEASER = "RELEASER"
SET_COUNT = 60
VALID_COUNT = 48
MISSING_REPLICATE_COUNT = 6
QC_REPEATABILITY_COUNT = 3
QC_REPRODUCIBILITY_COUNT = 3
VALID_SET_IDS = [f"D4172-PT-{i:02d}" for i in range(1, 49)]
MISSING_SET_IDS = [f"D4172-PT-{i:02d}" for i in range(49, 55)]
R_BREACH_SET_IDS = [f"D4172-PT-{i:02d}" for i in range(55, 58)]
R_CAP_BREACH_SET_IDS = [f"D4172-PT-{i:02d}" for i in range(58, 61)]

# Tokens that must never appear in a pre-release packet. Buyer pairing lives
# on the public door, not inside blinded proficiency/CoA drafts.
LEAK_TOKENS = (
    "Clark Testing",
    "Paul Heffernan",
    "Heffernan",
    "LAB-SYN-",
    "OIL-SYN-",
)

HOLD_CODES = (
    "HOLD_MISSING_REPLICATE",
    "HOLD_QC_REPEATABILITY",
    "HOLD_QC_REPRODUCIBILITY",
    "HOLD_METHOD_VERSION",
    "HOLD_SAMPLE_SWAP",
    "HOLD_PARTICIPANT_SWAP",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _q(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(QUANT, rounding=ROUND_HALF_EVEN)


def _money(value: Decimal) -> str:
    return f"{_q(value):.2f}"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _digest(parts: dict[str, Any], n: int = 8) -> str:
    return sha256_hex({"seed": FIXTURE_SEED, **parts})[:n]


def blind_id(prefix: str, set_id: str, kind: str) -> str:
    return f"{prefix}-{_digest({'set_id': set_id, 'kind': kind, 'blind': True}, 8)}"


def true_id(prefix: str, set_id: str, kind: str) -> str:
    return f"{prefix}-SYN-{_digest({'set_id': set_id, 'kind': kind, 'sealed': True}, 6).upper()}"


def procedure_for(index: int) -> dict[str, Any]:
    if index % 2 == 1:
        return {"procedure": "A", "load_n": 147}
    return {"procedure": "B", "load_n": 392}


def assigned_wsd(index: int, procedure: str) -> Decimal:
    base = Decimal("0.40") if procedure == "A" else Decimal("0.55")
    return _q(base + Decimal(index % 16) * QUANT)


def six_measurements(target: Decimal, salt: int) -> list[str]:
    hundredths = int(_q(target) * 100)
    if salt % 2 == 0:
        offsets = (0, 1, -1, 0, 1, -1)
    else:
        offsets = (1, -1, 0, -1, 1, 0)
    return [f"{(hundredths + off) / 100:.2f}" for off in offsets]


def set_kind(index: int) -> str:
    if 1 <= index <= 48:
        return "VALID"
    if 49 <= index <= 54:
        return "MISSING_REPLICATE"
    if 55 <= index <= 57:
        return "QC_REPEATABILITY"
    if 58 <= index <= 60:
        return "QC_REPRODUCIBILITY"
    raise ValueError(f"set index out of fixture range: {index}")


def _replicates(index: int, kind: str, assigned: Decimal) -> list[dict[str, Any]]:
    if kind == "MISSING_REPLICATE":
        return [{"run_id": "R1", "measurements_mm": six_measurements(assigned, index)}]
    if kind == "QC_REPEATABILITY":
        run1 = assigned
        run2 = _q(assigned + Decimal("0.20"))
        return [
            {"run_id": "R1", "measurements_mm": six_measurements(run1, index)},
            {"run_id": "R2", "measurements_mm": six_measurements(run2, index + 1)},
        ]
    if kind == "QC_REPRODUCIBILITY":
        shifted = _q(assigned + Decimal("0.40"))
        return [
            {"run_id": "R1", "measurements_mm": six_measurements(shifted, index)},
            {"run_id": "R2", "measurements_mm": six_measurements(_q(shifted + Decimal("0.01")), index + 1)},
        ]
    run1 = assigned
    run2 = _q(assigned + (QUANT if index % 3 == 0 else Decimal("0.00")))
    return [
        {"run_id": "R1", "measurements_mm": six_measurements(run1, index)},
        {"run_id": "R2", "measurements_mm": six_measurements(run2, index + 17)},
    ]


def build_acceptance_fixture() -> dict[str, Any]:
    """60 frozen synthetic proficiency sets plus a sealed identity map."""
    sets: list[dict[str, Any]] = []
    sealed: dict[str, str] = {}
    for index in range(1, SET_COUNT + 1):
        set_id = f"D4172-PT-{index:02d}"
        spec = procedure_for(index)
        kind = set_kind(index)
        assigned = assigned_wsd(index, spec["procedure"])
        participant_blind = blind_id("P", set_id, "participant")
        sample_blind = blind_id("S", set_id, "sample")
        participant_true = true_id("LAB", set_id, "participant")
        sample_true = true_id("OIL", set_id, "sample")
        sealed[participant_blind] = participant_true
        sealed[sample_blind] = sample_true
        sets.append(
            {
                "set_id": set_id,
                "cycle": CYCLE,
                "procedure": spec["procedure"],
                "method_version": METHOD_VERSION,
                "load_n": spec["load_n"],
                "temperature_c": 75,
                "speed_rpm": 1200,
                "duration_min": 60,
                "participant_blind_id": participant_blind,
                "sample_blind_id": sample_blind,
                "assigned_wsd_mm": _money(assigned),
                "r_mm": _money(R_REPEATABILITY),
                "R_mm": _money(R_REPRODUCIBILITY),
                "kind": kind,
                "replicates": _replicates(index, kind, assigned),
                "custody": [
                    {
                        "from_node": "SHIPPER-SYN",
                        "to_node": "BENCH-SYN",
                        "at": f"2026-08-01T12:{index:02d}:00Z",
                    }
                ],
            }
        )
    if len(sets) != SET_COUNT:
        raise RuntimeError(f"acceptance fixture must be exactly {SET_COUNT} sets")
    pack = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "cycle": CYCLE,
        "method_version": METHOD_VERSION,
        "fixture_seed": FIXTURE_SEED,
        "sets": sets,
        "sealed": sealed,
    }
    pack["fixture_sha256"] = sha256_hex(
        {key: value for key, value in pack.items() if key != "fixture_sha256"}
    )
    return pack


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "cycle": CYCLE,
        "records": {},
        "holds": [],
        "events": [],
        "sealed": {},
        "bindings": {},
        "released": {},
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    prev = journal["events"][-1]["event_sha256"] if journal["events"] else "GENESIS"
    body = {
        "seq": len(journal["events"]) + 1,
        "kind": kind,
        "payload": deepcopy(payload),
        "prev_sha256": prev,
    }
    body["event_sha256"] = sha256_hex(body)
    journal["events"].append(body)
    return body


def run_wsd(measurements: list[Any]) -> Decimal:
    if len(measurements) != MEASUREMENTS_PER_RUN:
        raise ValueError("each D4172 run needs six wear-scar measurements")
    total = sum((_q(item) for item in measurements), Decimal("0"))
    return _q(total / Decimal(MEASUREMENTS_PER_RUN))


def calculate_set(row: dict[str, Any]) -> dict[str, Any]:
    replicates = list(row.get("replicates") or [])
    method_version = _text(row.get("method_version"))
    run_results = []
    for item in replicates:
        measurements = list(item.get("measurements_mm") or [])
        if len(measurements) != MEASUREMENTS_PER_RUN:
            continue
        wsd = run_wsd(measurements)
        run_results.append(
            {
                "run_id": _text(item.get("run_id")),
                "measurements_mm": [f"{_q(m):.2f}" for m in measurements],
                "wsd_mm": _money(wsd),
            }
        )

    assigned = _q(row.get("assigned_wsd_mm") or "0")
    r_limit = _q(row.get("r_mm") or R_REPEATABILITY)
    big_r = _q(row.get("R_mm") or R_REPRODUCIBILITY)
    hold = None
    wsd = None
    repeat_delta = None
    repro_delta = None

    if method_version != METHOD_VERSION:
        hold = "HOLD_METHOD_VERSION"
    elif len(run_results) < REQUIRED_REPLICATES:
        hold = "HOLD_MISSING_REPLICATE"
    else:
        first = _q(run_results[0]["wsd_mm"])
        second = _q(run_results[1]["wsd_mm"])
        wsd = _q((first + second) / Decimal(2))
        repeat_delta = _q(abs(first - second))
        repro_delta = _q(abs(wsd - assigned))
        if repeat_delta > r_limit:
            hold = "HOLD_QC_REPEATABILITY"
        elif repro_delta > big_r:
            hold = "HOLD_QC_REPRODUCIBILITY"

    inputs = {
        "formula_id": FORMULA_ID,
        "method_version": method_version,
        "rounding": "0.01/ROUND_HALF_EVEN",
        "replicates": run_results,
        "assigned_wsd_mm": _money(assigned),
        "r_mm": _money(r_limit),
        "R_mm": _money(big_r),
    }
    provenance = {
        "formula_id": FORMULA_ID,
        "method_version": method_version,
        "rounding": "0.01/ROUND_HALF_EVEN",
        "inputs_sha256": sha256_hex(inputs),
        "r_mm": _money(r_limit),
        "R_mm": _money(big_r),
        "wsd_mm": None if wsd is None else _money(wsd),
        "repeatability_delta_mm": None if repeat_delta is None else _money(repeat_delta),
        "reproducibility_delta_mm": None if repro_delta is None else _money(repro_delta),
        "hold": hold,
    }
    provenance["outputs_sha256"] = sha256_hex(
        {key: value for key, value in provenance.items() if key != "outputs_sha256"}
    )
    return {
        "run_results": run_results,
        "wsd_mm": None if wsd is None else _money(wsd),
        "repeatability_delta_mm": None if repeat_delta is None else _money(repeat_delta),
        "reproducibility_delta_mm": None if repro_delta is None else _money(repro_delta),
        "hold": hold,
        "state": hold or "READY_FOR_HUMAN",
        "provenance": provenance,
    }


def public_packet(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "set_id": record["set_id"],
        "cycle": record["cycle"],
        "procedure": record["procedure"],
        "method_version": record["method_version"],
        "load_n": record["load_n"],
        "participant_blind_id": record["participant_blind_id"],
        "sample_blind_id": record["sample_blind_id"],
        "assigned_wsd_mm": record["assigned_wsd_mm"],
        "wsd_mm": record.get("wsd_mm"),
        "unit": "mm",
        "r_mm": record["r_mm"],
        "R_mm": record["R_mm"],
        "repeatability_delta_mm": record.get("repeatability_delta_mm"),
        "reproducibility_delta_mm": record.get("reproducibility_delta_mm"),
        "state": record["state"],
        "hold": record.get("hold"),
        "released": bool(record.get("released")),
        "provenance_sha256": record.get("provenance", {}).get("outputs_sha256"),
    }


def draft_coa(record: dict[str, Any]) -> dict[str, Any]:
    packet = public_packet(record)
    packet["kind"] = "COA_DRAFT"
    packet["released"] = False
    return packet


def leak_tokens_in(value: Any, extra: tuple[str, ...] = ()) -> list[str]:
    blob = _canonical(value)
    found = []
    for token in LEAK_TOKENS + extra:
        if token and token in blob:
            found.append(token)
    return found


def _binding_key(sample_blind_id: str) -> str:
    return f"sample:{sample_blind_id}"


def ingest_set(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    set_id = _text(row.get("set_id"))
    sample_blind = _text(row.get("sample_blind_id"))
    participant_blind = _text(row.get("participant_blind_id"))
    existing = journal["records"].get(set_id)
    if existing is not None:
        _event(journal, "REPLAY_NOOP", {"set_id": set_id, "sample_blind_id": sample_blind})
        return {"kind": "REPLAY_NOOP", "set_id": set_id}

    bind_key = _binding_key(sample_blind)
    bound = journal["bindings"].get(bind_key)
    expected = {
        "set_id": set_id,
        "participant_blind_id": participant_blind,
        "sample_blind_id": sample_blind,
    }
    if bound and bound != expected:
        hold = "HOLD_SAMPLE_SWAP" if bound.get("sample_blind_id") == sample_blind and bound.get("set_id") != set_id else "HOLD_PARTICIPANT_SWAP"
        if bound.get("participant_blind_id") != participant_blind:
            hold = "HOLD_PARTICIPANT_SWAP"
        calc = calculate_set(row)
        record = {
            "set_id": set_id,
            "cycle": _text(row.get("cycle")) or CYCLE,
            "procedure": _text(row.get("procedure")),
            "method_version": _text(row.get("method_version")),
            "load_n": row.get("load_n"),
            "participant_blind_id": participant_blind,
            "sample_blind_id": sample_blind,
            "assigned_wsd_mm": _text(row.get("assigned_wsd_mm")),
            "r_mm": _text(row.get("r_mm")) or _money(R_REPEATABILITY),
            "R_mm": _text(row.get("R_mm")) or _money(R_REPRODUCIBILITY),
            "kind": _text(row.get("kind")),
            "run_results": calc["run_results"],
            "wsd_mm": calc["wsd_mm"],
            "repeatability_delta_mm": calc["repeatability_delta_mm"],
            "reproducibility_delta_mm": calc["reproducibility_delta_mm"],
            "hold": hold,
            "state": hold,
            "released": False,
            "released_by": None,
            "provenance": calc["provenance"],
            "custody": deepcopy(row.get("custody") or []),
            "interface_state": "SIMULATED",
            "interface_live": False,
        }
        journal["records"][set_id] = record
        journal["holds"].append({"set_id": set_id, "code": hold})
        _event(journal, hold, {"set_id": set_id, "bound": bound, "attempted": expected})
        return {"kind": "HOLD", "set_id": set_id, "code": hold}

    journal["bindings"][bind_key] = expected
    calc = calculate_set(row)
    record = {
        "set_id": set_id,
        "cycle": _text(row.get("cycle")) or CYCLE,
        "procedure": _text(row.get("procedure")),
        "method_version": _text(row.get("method_version")),
        "load_n": row.get("load_n"),
        "participant_blind_id": participant_blind,
        "sample_blind_id": sample_blind,
        "assigned_wsd_mm": _text(row.get("assigned_wsd_mm")),
        "r_mm": _text(row.get("r_mm")) or _money(R_REPEATABILITY),
        "R_mm": _text(row.get("R_mm")) or _money(R_REPRODUCIBILITY),
        "kind": _text(row.get("kind")),
        "run_results": calc["run_results"],
        "wsd_mm": calc["wsd_mm"],
        "repeatability_delta_mm": calc["repeatability_delta_mm"],
        "reproducibility_delta_mm": calc["reproducibility_delta_mm"],
        "hold": calc["hold"],
        "state": calc["state"],
        "released": False,
        "released_by": None,
        "provenance": calc["provenance"],
        "custody": deepcopy(row.get("custody") or []),
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    journal["records"][set_id] = record
    _event(
        journal,
        "ACCESSION",
        {
            "set_id": set_id,
            "sample_blind_id": sample_blind,
            "participant_blind_id": participant_blind,
            "custody": record["custody"],
        },
    )
    _event(journal, "CALCULATED", {"set_id": set_id, "provenance": record["provenance"]})
    if record["hold"]:
        journal["holds"].append({"set_id": set_id, "code": record["hold"]})
        _event(journal, record["hold"], {"set_id": set_id, "state": record["state"]})
    else:
        _event(journal, "READY_FOR_HUMAN", {"set_id": set_id, "wsd_mm": record["wsd_mm"]})
    return {"kind": record["state"], "set_id": set_id, "code": record["hold"]}


def dispose(
    journal: dict[str, Any],
    set_id: str,
    *,
    actor_role: str,
    actor: str,
    action: str = "RELEASE_COA",
) -> dict[str, Any]:
    record = journal["records"].get(set_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_SET"}
    role = _text(actor_role).upper()
    act = _text(action).upper()
    if role != HUMAN_RELEASER:
        _event(
            journal,
            "RELEASE_DENIED",
            {"set_id": set_id, "code": "AUTONOMOUS_RELEASE_DENIED", "actor_role": role or None},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "state": record["state"]}
    if act == "RELEASE_COA":
        if record["state"] != "READY_FOR_HUMAN" and record["state"] != "RELEASED":
            _event(
                journal,
                "RELEASE_DENIED",
                {"set_id": set_id, "code": "HOLD_BLOCKS_RELEASE", "state": record["state"]},
            )
            return {"ok": False, "code": "HOLD_BLOCKS_RELEASE", "state": record["state"]}
        if record["released"]:
            return {"ok": True, "duplicate": True, "state": "RELEASED"}
        sample_true = journal["sealed"].get(record["sample_blind_id"])
        record["released"] = True
        record["released_by"] = _text(actor) or "human-releaser"
        record["state"] = "RELEASED"
        record["coa"] = {
            **draft_coa(record),
            "kind": "COA_RELEASED",
            "released": True,
            "released_by": record["released_by"],
            "customer_sample_id": sample_true,
        }
        journal["released"][set_id] = record["coa"]
        _event(journal, "RELEASED", {"set_id": set_id, "released_by": record["released_by"]})
        return {"ok": True, "duplicate": False, "state": "RELEASED"}
    if act in {"VOID", "RETEST"}:
        if not str(record["state"]).startswith("HOLD"):
            return {"ok": False, "code": "NOT_ON_HOLD", "state": record["state"]}
        record["disposition"] = act
        record["disposed_by"] = _text(actor) or "human-releaser"
        _event(journal, "HUMAN_DISPOSITION", {"set_id": set_id, "action": act})
        return {"ok": True, "state": record["state"], "disposition": act}
    return {"ok": False, "code": "UNKNOWN_ACTION"}


def pre_release_views(journal: dict[str, Any]) -> dict[str, Any]:
    records = sorted(journal["records"].values(), key=lambda item: item["set_id"])
    return {
        "cycle_digest": {
            "demand_id": DEMAND_ID,
            "cycle": CYCLE,
            "method_version": METHOD_VERSION,
            "set_ids": [item["set_id"] for item in records],
            "states": {item["set_id"]: item["state"] for item in records},
            "wsd_mm": {item["set_id"]: item.get("wsd_mm") for item in records},
        },
        "public_packets": [public_packet(item) for item in records],
        "coa_drafts": [draft_coa(item) for item in records],
    }


def run_gate(pack: dict[str, Any] | None = None) -> dict[str, Any]:
    inbound = deepcopy(pack if pack is not None else build_acceptance_fixture())
    journal = empty_journal()
    journal["sealed"] = deepcopy(inbound.get("sealed") or {})
    effects = [ingest_set(journal, row) for row in inbound["sets"]]
    autonomous = [
        dispose(journal, set_id, actor_role="SYSTEM", actor="autonomous", action="RELEASE_COA")
        for set_id in journal["records"]
    ]
    records = sorted(journal["records"].values(), key=lambda item: item["set_id"])
    views = pre_release_views(journal)
    extra_true_ids = tuple(sorted(journal["sealed"].values()))
    leaks = leak_tokens_in(views, extra_true_ids)
    hold_codes = sorted({item["code"] for item in journal["holds"]})
    hold_ids = sorted(item["set_id"] for item in journal["holds"])
    ready_ids = [item["set_id"] for item in records if item["state"] == "READY_FOR_HUMAN"]
    golden_stats = {
        item["set_id"]: {
            "wsd_mm": item.get("wsd_mm"),
            "repeatability_delta_mm": item.get("repeatability_delta_mm"),
            "reproducibility_delta_mm": item.get("reproducibility_delta_mm"),
            "state": item["state"],
            "hold": item.get("hold"),
            "provenance_sha256": item["provenance"]["outputs_sha256"],
        }
        for item in records
    }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "truth_gate": TRUTH_GATE,
        "cycle": CYCLE,
        "method_version": METHOD_VERSION,
        "input_sets": len(inbound["sets"]),
        "processed": len(records),
        "ready": len(ready_ids),
        "held": len(hold_ids),
        "ready_ids": ready_ids,
        "hold_ids": hold_ids,
        "hold_codes": hold_codes,
        "released_coas": 0,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "sample_swaps": 0,
        "participant_swaps": 0,
        "identity_leaks": leaks,
        "golden_stats": golden_stats,
        "public_packets": views["public_packets"],
        "coa_drafts": views["coa_drafts"],
        "cycle_digest": views["cycle_digest"],
        "custody_events": len(journal["events"]),
        "custody_head": journal["events"][-1]["event_sha256"] if journal["events"] else None,
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "interface_live": False,
        "interfaces": "SIMULATED",
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "fixture_sha256": inbound.get("fixture_sha256"),
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def replay_into(journal: dict[str, Any], pack: dict[str, Any] | None = None) -> dict[str, Any]:
    inbound = deepcopy(pack if pack is not None else build_acceptance_fixture())
    before = set(journal["records"])
    before_holds = len(journal["holds"])
    effects = [ingest_set(journal, row) for row in inbound["sets"]]
    added = set(journal["records"]) - before
    return {
        "added_set_ids": sorted(added),
        "added_set_count": len(added),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "record_count": len(journal["records"]),
        "hold_count": len(journal["holds"]),
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_sets") != SET_COUNT:
        failures.append("input_sets!=60")
    if result.get("processed") != SET_COUNT:
        failures.append("processed!=60")
    if result.get("ready") != VALID_COUNT:
        failures.append("ready!=48")
    if result.get("held") != SET_COUNT - VALID_COUNT:
        failures.append("held!=12")
    if result.get("ready_ids") != VALID_SET_IDS:
        failures.append("ready_ids")
    if result.get("hold_ids") != MISSING_SET_IDS + R_BREACH_SET_IDS + R_CAP_BREACH_SET_IDS:
        failures.append("hold_ids")
    expected_codes = [
        "HOLD_MISSING_REPLICATE",
        "HOLD_QC_REPEATABILITY",
        "HOLD_QC_REPRODUCIBILITY",
    ]
    if result.get("hold_codes") != expected_codes:
        failures.append("hold_codes")
    stats = result.get("golden_stats") or {}
    for set_id in MISSING_SET_IDS:
        if (stats.get(set_id) or {}).get("hold") != "HOLD_MISSING_REPLICATE":
            failures.append(f"{set_id}_missing")
    for set_id in R_BREACH_SET_IDS:
        if (stats.get(set_id) or {}).get("hold") != "HOLD_QC_REPEATABILITY":
            failures.append(f"{set_id}_r")
    for set_id in R_CAP_BREACH_SET_IDS:
        if (stats.get(set_id) or {}).get("hold") != "HOLD_QC_REPRODUCIBILITY":
            failures.append(f"{set_id}_R")
    if result.get("released_coas") != 0:
        failures.append("released_coas!=0")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("sample_swaps") != 0:
        failures.append("sample_swaps")
    if result.get("participant_swaps") != 0:
        failures.append("participant_swaps")
    if result.get("identity_leaks"):
        failures.append("identity_leaks")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if not result.get("custody_head"):
        failures.append("custody_head")
    if int(result.get("custody_events") or 0) < SET_COUNT * 3:
        failures.append("custody_events")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    pack = build_acceptance_fixture()
    journal = empty_journal()
    journal["sealed"] = deepcopy(pack["sealed"])
    for row in pack["sets"]:
        ingest_set(journal, row)
    replay = replay_into(journal, pack)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    if replay.get("added_set_count") != 0:
        failures.append("replay_added_sets")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "fixture_sha256": first.get("fixture_sha256"),
        "input_sets": first.get("input_sets"),
        "ready": first.get("ready"),
        "held": first.get("held"),
        "hold_codes": first.get("hold_codes"),
        "identity_leaks": first.get("identity_leaks"),
        "released_coas": first.get("released_coas"),
        "replay_added_sets": replay.get("added_set_count"),
        "custody_head": first.get("custody_head"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
