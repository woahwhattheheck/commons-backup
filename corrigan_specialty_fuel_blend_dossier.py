#!/usr/bin/env python3
"""Corrigan Labs specialty / reference-fuel batch dossier LIMS.

Demand: corrigan-specialty-fuel-blend-dossier-lims-01
Buyer: Corrigan Labs / Mike Corrigan

Working runner — not a mock SKU. Joins formula version, ingredient lots,
tank movements, internal lab results, external-result packets, and a
staged Certificate of Analysis into one batch dossier.

Acceptance: replay 80 synthetic blend orders — 64 clean, 8 formula-version
mismatches, 4 missing external-result packets, 4 OOS. PASS only with
exact genealogy for every clean order; the expected HOLD code on all 16
exceptions; zero orphan tank movements or duplicate batches; deterministic
CoA contents and rounding; immutable source lineage; idempotent replay;
and human-only disposition.

HOLD / BUILD-AND-VERIFY. Synthetic / deidentified fixtures only.
Adapters stay simulated / read-only. No live LIMS. No production writes.
No outreach. No prospect-facing demo. No automatic release.
PRE-SALE TRANSPORT: NONE. cash_usd=0.

Official command:
    python3 corrigan_specialty_fuel_blend_dossier.py
Binary:
    python3 test_corrigan_specialty_fuel_blend_dossier.py
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

DEMAND_ID = "corrigan-specialty-fuel-blend-dossier-lims-01"
SCHEMA = "commons-corrigan-specialty-fuel-blend-dossier-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Corrigan Labs / Mike Corrigan"
HUMAN_RELEASER = "mike-corrigan-releaser"
HUMAN_ROLE = "NAMED_HUMAN_RELEASER"
FIXTURE_DATE = "2026-08-31"
OFFICIAL_BINARY = "python3 corrigan_specialty_fuel_blend_dossier.py"
OFFICIAL_TEST = "python3 test_corrigan_specialty_fuel_blend_dossier.py"
PACK_DIR = Path(__file__).resolve().parent / "revenue" / "corrigan_specialty_fuel_blend_dossier"

HOLD_FORMULA = "FORMULA_VERSION_MISMATCH"
HOLD_MISSING_EXT = "MISSING_EXTERNAL_RESULT"
HOLD_OOS = "OOS"
HOLD_CODES = (HOLD_FORMULA, HOLD_MISSING_EXT, HOLD_OOS)

CLEAN_COUNT = 64
FORMULA_MISMATCH_COUNT = 8
MISSING_EXTERNAL_COUNT = 4
OOS_COUNT = 4
HOLD_COUNT = FORMULA_MISMATCH_COUNT + MISSING_EXTERNAL_COUNT + OOS_COUNT
INPUT_COUNT = CLEAN_COUNT + HOLD_COUNT
BLENDED_COUNT = CLEAN_COUNT + MISSING_EXTERNAL_COUNT + OOS_COUNT  # 72 batches
HOLD_FAMILY_COUNTS = {
    HOLD_FORMULA: FORMULA_MISMATCH_COUNT,
    HOLD_MISSING_EXT: MISSING_EXTERNAL_COUNT,
    HOLD_OOS: OOS_COUNT,
}

AUTONOMOUS_NAMES = frozenset({"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE"})

# Eight synthetic specialty / reference-fuel families. Not live recipes.
# vol_pct strings sum to 100.00. Assay bounds are fixture bindings.
FORMULAS: dict[str, dict[str, Any]] = {
    "CRG-RFG-87": {
        "token": "RFG87",
        "family": "reformulated_gasoline",
        "current_version": "3.2.0",
        "stale_version": "2.1.0",
        "blend_tank": "T-BLEND-RFG",
        "finish_tank": "T-FINISH-RFG",
        "ingredients": (
            {"code": "ALK", "name": "alkylate", "vol_pct": "35.00", "tank": "T-ALK-01"},
            {"code": "REF", "name": "reformate", "vol_pct": "28.00", "tank": "T-REF-02"},
            {"code": "NAP", "name": "light_naphtha", "vol_pct": "27.00", "tank": "T-NAP-03"},
            {"code": "ETH", "name": "denatured_ethanol", "vol_pct": "10.00", "tank": "T-ETH-04"},
        ),
        "assays": {
            "aki": {"target": "87.0", "min": "87.0", "max": "88.5", "places": 1, "unit": "AKI"},
            "rvp_psi": {"target": "7.8", "min": "6.4", "max": "9.0", "places": 1, "unit": "psi"},
            "sulfur_ppm": {"target": "8.0", "min": "0.0", "max": "10.0", "places": 1, "unit": "ppm"},
            "density_g_ml": {"target": "0.7420", "min": "0.7200", "max": "0.7600", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "sulfur_ppm",
        "oos_value": "18.0",
    },
    "CRG-ULSD-15": {
        "token": "ULSD",
        "family": "ultra_low_sulfur_diesel",
        "current_version": "4.0.1",
        "stale_version": "3.0.0",
        "blend_tank": "T-BLEND-ULSD",
        "finish_tank": "T-FINISH-ULSD",
        "ingredients": (
            {"code": "HSD", "name": "hydrotreated_diesel", "vol_pct": "92.00", "tank": "T-HSD-11"},
            {"code": "BIO", "name": "biodiesel_b100", "vol_pct": "5.00", "tank": "T-BIO-12"},
            {"code": "CET", "name": "cetane_improver", "vol_pct": "0.20", "tank": "T-CET-13"},
            {"code": "ADD", "name": "cold_flow_additive", "vol_pct": "2.80", "tank": "T-ADD-14"},
        ),
        "assays": {
            "cetane": {"target": "48.0", "min": "40.0", "max": "55.0", "places": 1, "unit": "CN"},
            "sulfur_ppm": {"target": "8.0", "min": "0.0", "max": "15.0", "places": 1, "unit": "ppm"},
            "flash_c": {"target": "62.0", "min": "52.0", "max": "90.0", "places": 1, "unit": "C"},
            "density_g_ml": {"target": "0.8320", "min": "0.8200", "max": "0.8500", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "sulfur_ppm",
        "oos_value": "22.0",
    },
    "CRG-JET-A1": {
        "token": "JETA1",
        "family": "jet_a1_reference",
        "current_version": "1.8.0",
        "stale_version": "1.2.0",
        "blend_tank": "T-BLEND-JET",
        "finish_tank": "T-FINISH-JET",
        "ingredients": (
            {"code": "KER", "name": "straight_run_kerosene", "vol_pct": "70.00", "tank": "T-KER-21"},
            {"code": "HYD", "name": "hydrotreated_kerosene", "vol_pct": "28.50", "tank": "T-HYD-22"},
            {"code": "ANT", "name": "static_dissipator", "vol_pct": "1.50", "tank": "T-ANT-23"},
        ),
        "assays": {
            "flash_c": {"target": "42.0", "min": "38.0", "max": "50.0", "places": 1, "unit": "C"},
            "freeze_c": {"target": "-50.0", "min": "-60.0", "max": "-47.0", "places": 1, "unit": "C"},
            "sulfur_ppm": {"target": "200.0", "min": "0.0", "max": "3000.0", "places": 1, "unit": "ppm"},
            "density_g_ml": {"target": "0.8030", "min": "0.7750", "max": "0.8400", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "freeze_c",
        "oos_value": "-40.0",
    },
    "CRG-E10-W": {
        "token": "E10W",
        "family": "e10_winter_gasoline",
        "current_version": "2.4.0",
        "stale_version": "2.0.0",
        "blend_tank": "T-BLEND-E10",
        "finish_tank": "T-FINISH-E10",
        "ingredients": (
            {"code": "BOB", "name": "blendstock_for_oxygenate", "vol_pct": "90.00", "tank": "T-BOB-31"},
            {"code": "ETH", "name": "denatured_ethanol", "vol_pct": "10.00", "tank": "T-ETH-04"},
        ),
        "assays": {
            "aki": {"target": "87.2", "min": "87.0", "max": "88.8", "places": 1, "unit": "AKI"},
            "rvp_psi": {"target": "13.5", "min": "11.0", "max": "15.0", "places": 1, "unit": "psi"},
            "oxygen_pct": {"target": "3.70", "min": "3.50", "max": "4.00", "places": 2, "unit": "pct"},
            "density_g_ml": {"target": "0.7380", "min": "0.7200", "max": "0.7550", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "rvp_psi",
        "oos_value": "16.8",
    },
    "CRG-B5": {
        "token": "B5",
        "family": "b5_biodiesel_blend",
        "current_version": "5.1.0",
        "stale_version": "4.0.0",
        "blend_tank": "T-BLEND-B5",
        "finish_tank": "T-FINISH-B5",
        "ingredients": (
            {"code": "ULS", "name": "ulsd_base", "vol_pct": "95.00", "tank": "T-ULS-41"},
            {"code": "B100", "name": "fame_b100", "vol_pct": "5.00", "tank": "T-B100-42"},
        ),
        "assays": {
            "fame_pct": {"target": "5.00", "min": "4.50", "max": "5.50", "places": 2, "unit": "pct"},
            "sulfur_ppm": {"target": "9.0", "min": "0.0", "max": "15.0", "places": 1, "unit": "ppm"},
            "flash_c": {"target": "64.0", "min": "52.0", "max": "90.0", "places": 1, "unit": "C"},
            "density_g_ml": {"target": "0.8360", "min": "0.8200", "max": "0.8550", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "fame_pct",
        "oos_value": "8.40",
    },
    "CRG-RACE-100": {
        "token": "RACE",
        "family": "racing_reference_100",
        "current_version": "1.3.0",
        "stale_version": "1.0.0",
        "blend_tank": "T-BLEND-RACE",
        "finish_tank": "T-FINISH-RACE",
        "ingredients": (
            {"code": "ALK", "name": "alkylate", "vol_pct": "55.00", "tank": "T-ALK-01"},
            {"code": "TOL", "name": "toluene", "vol_pct": "30.00", "tank": "T-TOL-51"},
            {"code": "ISO", "name": "isooctane", "vol_pct": "15.00", "tank": "T-ISO-52"},
        ),
        "assays": {
            "aki": {"target": "100.0", "min": "99.0", "max": "102.0", "places": 1, "unit": "AKI"},
            "ron": {"target": "105.0", "min": "103.0", "max": "108.0", "places": 1, "unit": "RON"},
            "oxygen_pct": {"target": "0.00", "min": "0.00", "max": "0.20", "places": 2, "unit": "pct"},
            "density_g_ml": {"target": "0.7550", "min": "0.7400", "max": "0.7700", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "aki",
        "oos_value": "96.0",
    },
    "CRG-HO-2": {
        "token": "HO2",
        "family": "heating_oil_2",
        "current_version": "2.0.2",
        "stale_version": "1.5.0",
        "blend_tank": "T-BLEND-HO",
        "finish_tank": "T-FINISH-HO",
        "ingredients": (
            {"code": "GAS", "name": "gas_oil", "vol_pct": "88.00", "tank": "T-GAS-61"},
            {"code": "KER", "name": "kero_cutter", "vol_pct": "10.00", "tank": "T-KER-21"},
            {"code": "DYE", "name": "red_dye", "vol_pct": "2.00", "tank": "T-DYE-62"},
        ),
        "assays": {
            "flash_c": {"target": "60.0", "min": "52.0", "max": "80.0", "places": 1, "unit": "C"},
            "sulfur_ppm": {"target": "400.0", "min": "0.0", "max": "500.0", "places": 1, "unit": "ppm"},
            "pour_c": {"target": "-18.0", "min": "-30.0", "max": "-6.0", "places": 1, "unit": "C"},
            "density_g_ml": {"target": "0.8450", "min": "0.8300", "max": "0.8600", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "flash_c",
        "oos_value": "40.0",
    },
    "CRG-AVG-100": {
        "token": "AVG",
        "family": "avgas_100ll_analog",
        "current_version": "6.0.0",
        "stale_version": "5.2.0",
        "blend_tank": "T-BLEND-AVG",
        "finish_tank": "T-FINISH-AVG",
        "ingredients": (
            {"code": "ALK", "name": "alkylate", "vol_pct": "72.00", "tank": "T-ALK-01"},
            {"code": "TEL", "name": "lead_alkyl_concentrate", "vol_pct": "0.12", "tank": "T-TEL-71"},
            {"code": "DYE", "name": "blue_dye", "vol_pct": "0.08", "tank": "T-DYE-72"},
            {"code": "ISO", "name": "isooctane", "vol_pct": "27.80", "tank": "T-ISO-52"},
        ),
        "assays": {
            "aki": {"target": "100.0", "min": "99.6", "max": "102.0", "places": 1, "unit": "AKI"},
            "lead_g_l": {"target": "0.560", "min": "0.100", "max": "0.560", "places": 3, "unit": "g/L"},
            "color": {"target": "1.000", "min": "0.800", "max": "1.200", "places": 3, "unit": "blue_index"},
            "density_g_ml": {"target": "0.7100", "min": "0.6900", "max": "0.7300", "places": 4, "unit": "g/mL"},
        },
        "oos_assay": "lead_g_l",
        "oos_value": "0.820",
    },
}

FORMULA_IDS = tuple(FORMULAS)
CLEAN_GALLONS = ("5000.00", "8000.00", "10000.00", "12000.00", "15000.00", "20000.00", "25000.00", "30000.00")
HOLD_GALLONS = "7500.00"

GOLDEN_COUNTS = {
    "input_rows": INPUT_COUNT,
    "clean": CLEAN_COUNT,
    "hold": HOLD_COUNT,
    "hold_formula_version_mismatch": FORMULA_MISMATCH_COUNT,
    "hold_missing_external_result": MISSING_EXTERNAL_COUNT,
    "hold_oos": OOS_COUNT,
    "batches": BLENDED_COUNT,
    "duplicate_batches": 0,
    "orphan_tank_movements": 0,
    "staged_coa": CLEAN_COUNT,
    "genealogy": CLEAN_COUNT,
    "human_disposed": CLEAN_COUNT,
    "autonomous_released": 0,
    "production_writes": 0,
    "replay_added_orders": 0,
    "replay_added_batches": 0,
    "replay_added_movements": 0,
    "replay_added_holds": 0,
}

# Locked after first official fixture run. Do not remint.
GOLDEN_AUDIT_SHA256 = "85f8acfab58b66c1022fffcefeef49bef19cb7c3e36db65c4c912de74ab754fe"
GOLDEN_FIXTURE_SHA256 = "c1c06fb839551eeaaf29ddb3749f1f4911792e108d2de5c5845b274e55a38347"
GOLDEN_CATALOG_SHA256 = "6194d0e01c424a289bb97c0beb3d750e4f32902217b98e87762653cf220ca433"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def qround(value: Any, places: int) -> str:
    quant = Decimal("1").scaleb(-int(places))
    number = Decimal(str(value))
    return format(number.quantize(quant, rounding=ROUND_HALF_EVEN), f".{int(places)}f")


def split_gallons(total: str, ingredients: tuple[dict[str, Any], ...]) -> list[str]:
    remaining = Decimal(total)
    parts: list[str] = []
    last = len(ingredients) - 1
    for index, ingredient in enumerate(ingredients):
        if index == last:
            gallons = remaining
        else:
            gallons = (Decimal(total) * Decimal(ingredient["vol_pct"]) / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_EVEN
            )
            remaining -= gallons
        parts.append(format(gallons, ".2f"))
    return parts


def catalog_payload() -> dict[str, Any]:
    return {
        "demand_id": DEMAND_ID,
        "formulas": {
            formula_id: {
                "token": spec["token"],
                "family": spec["family"],
                "current_version": spec["current_version"],
                "stale_version": spec["stale_version"],
                "blend_tank": spec["blend_tank"],
                "finish_tank": spec["finish_tank"],
                "ingredients": [dict(item) for item in spec["ingredients"]],
                "assays": {key: dict(value) for key, value in spec["assays"].items()},
                "oos_assay": spec["oos_assay"],
                "oos_value": spec["oos_value"],
            }
            for formula_id, spec in FORMULAS.items()
        },
    }


CATALOG_SHA256 = sha256_hex(catalog_payload())


def _order_id(token: str, index: int) -> str:
    return f"CRG-ORD-{token}-{index:02d}"


def _batch_id(token: str, index: int) -> str:
    return f"CRG-BAT-{token}-{index:02d}"


def _target_assays(spec: dict[str, Any]) -> dict[str, str]:
    return {name: qround(assay["target"], assay["places"]) for name, assay in spec["assays"].items()}


def _oos_assays(spec: dict[str, Any]) -> dict[str, str]:
    assays = _target_assays(spec)
    name = spec["oos_assay"]
    places = spec["assays"][name]["places"]
    assays[name] = qround(spec["oos_value"], places)
    return assays


def _base_order(formula_id: str, index: int, gallons: str) -> dict[str, Any]:
    spec = FORMULAS[formula_id]
    token = spec["token"]
    return {
        "order_id": _order_id(token, index),
        "formula_id": formula_id,
        "formula_version": spec["current_version"],
        "family": spec["family"],
        "gallons": gallons,
        "blend_date": FIXTURE_DATE,
        "requested_by": "SYN-CRG-PLANNER",
        "external_packet_present": True,
        "force_oos": False,
        "expected_state": "CLEAN",
        "expected_hold": "",
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """80-row PASS fixture: 64 clean + 8 formula mismatch + 4 missing ext + 4 OOS."""
    rows: list[dict[str, Any]] = []
    for formula_id in FORMULA_IDS:
        for index, gallons in enumerate(CLEAN_GALLONS, start=1):
            rows.append(_base_order(formula_id, index, gallons))
        mismatch = _base_order(formula_id, 9, HOLD_GALLONS)
        mismatch["formula_version"] = FORMULAS[formula_id]["stale_version"]
        mismatch["expected_state"] = "HOLD"
        mismatch["expected_hold"] = HOLD_FORMULA
        rows.append(mismatch)
    for formula_id in FORMULA_IDS[:4]:
        missing = _base_order(formula_id, 10, HOLD_GALLONS)
        missing["external_packet_present"] = False
        missing["expected_state"] = "HOLD"
        missing["expected_hold"] = HOLD_MISSING_EXT
        rows.append(missing)
    for formula_id in FORMULA_IDS[4:]:
        oos = _base_order(formula_id, 10, HOLD_GALLONS)
        oos["force_oos"] = True
        oos["expected_state"] = "HOLD"
        oos["expected_hold"] = HOLD_OOS
        rows.append(oos)
    if len(rows) != INPUT_COUNT:
        raise RuntimeError(f"acceptance fixture must be exactly {INPUT_COUNT} rows, got {len(rows)}")
    return rows


def fixture_manifest() -> dict[str, Any]:
    rows = build_acceptance_fixture()
    return {
        "demand_id": DEMAND_ID,
        "row_count": len(rows),
        "order_ids": [row["order_id"] for row in rows],
        "expected_states": [row["expected_state"] for row in rows],
        "expected_holds": [row["expected_hold"] for row in rows],
        "fixture_sha256": sha256_hex(rows),
        "catalog_sha256": CATALOG_SHA256,
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "orders": {},
        "batches": {},
        "lots": {},
        "movements": {},
        "internal_results": {},
        "external_packets": {},
        "coas": {},
        "genealogies": {},
        "holds": [],
        "events": [],
        "interface_live": False,
        "production_writes": 0,
        "qc_decisions": 0,
        "billing_writes": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def normalize_order(row: dict[str, Any]) -> dict[str, Any]:
    present = row.get("external_packet_present", True)
    if isinstance(present, str):
        present = present.strip().lower() not in {"", "0", "false", "no", "n"}
    force = row.get("force_oos", False)
    if isinstance(force, str):
        force = force.strip().lower() in {"1", "true", "yes", "y"}
    return {
        "order_id": _text(row.get("order_id")),
        "formula_id": _text(row.get("formula_id")),
        "formula_version": _text(row.get("formula_version")),
        "family": _text(row.get("family")),
        "gallons": qround(row.get("gallons") or "0", 2),
        "blend_date": _text(row.get("blend_date")) or FIXTURE_DATE,
        "requested_by": _text(row.get("requested_by")) or "SYN-CRG-PLANNER",
        "external_packet_present": bool(present),
        "force_oos": bool(force),
        "expected_state": _text(row.get("expected_state")),
        "expected_hold": _text(row.get("expected_hold")),
    }


def _hold(
    journal: dict[str, Any],
    *,
    order_id: str,
    code: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hold = {"order_id": order_id, "code": code, "state": "HOLD"}
    if extra:
        hold.update(extra)
    fingerprint = sha256_hex({"order_id": order_id, "code": code})
    existing = {sha256_hex({"order_id": item["order_id"], "code": item["code"]}) for item in journal["holds"]}
    if fingerprint not in existing:
        journal["holds"].append(hold)
        _event(journal, "HOLD", hold)
    return {"kind": "HOLD", "duplicate": fingerprint in existing, **hold}


def _record_order(journal: dict[str, Any], norm: dict[str, Any], state: str, extra: dict[str, Any]) -> None:
    journal["orders"][norm["order_id"]] = {
        "order_id": norm["order_id"],
        "formula_id": norm["formula_id"],
        "formula_version": norm["formula_version"],
        "family": norm["family"],
        "gallons": norm["gallons"],
        "blend_date": norm["blend_date"],
        "state": state,
        **extra,
    }


def _create_blend(journal: dict[str, Any], norm: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    token = spec["token"]
    index = int(norm["order_id"].rsplit("-", 1)[-1])
    batch_id = _batch_id(token, index)
    gallons_parts = split_gallons(norm["gallons"], spec["ingredients"])
    lots: list[dict[str, Any]] = []
    movements: list[dict[str, Any]] = []
    for seq, (ingredient, gallons) in enumerate(zip(spec["ingredients"], gallons_parts), start=1):
        lot_id = f"CRG-LOT-{token}-{index:02d}-{ingredient['code']}"
        movement_id = f"CRG-MOV-{token}-{index:02d}-{seq:02d}"
        lot = {
            "lot_id": lot_id,
            "order_id": norm["order_id"],
            "batch_id": batch_id,
            "ingredient_code": ingredient["code"],
            "ingredient_name": ingredient["name"],
            "tank_id": ingredient["tank"],
            "vol_pct": ingredient["vol_pct"],
            "gallons": gallons,
        }
        movement = {
            "movement_id": movement_id,
            "order_id": norm["order_id"],
            "batch_id": batch_id,
            "kind": "INGREDIENT_TO_BLEND",
            "from_tank": ingredient["tank"],
            "to_tank": spec["blend_tank"],
            "gallons": gallons,
            "lot_id": lot_id,
        }
        lots.append(lot)
        movements.append(movement)
        journal["lots"][lot_id] = lot
        journal["movements"][movement_id] = movement
    finish_id = f"CRG-MOV-{token}-{index:02d}-{len(spec['ingredients']) + 1:02d}"
    finish = {
        "movement_id": finish_id,
        "order_id": norm["order_id"],
        "batch_id": batch_id,
        "kind": "BLEND_TO_FINISH",
        "from_tank": spec["blend_tank"],
        "to_tank": spec["finish_tank"],
        "gallons": norm["gallons"],
        "lot_id": "",
    }
    movements.append(finish)
    journal["movements"][finish_id] = finish
    internal_id = f"CRG-INT-{token}-{index:02d}"
    assays = _oos_assays(spec) if norm["force_oos"] else _target_assays(spec)
    internal = {
        "result_id": internal_id,
        "order_id": norm["order_id"],
        "batch_id": batch_id,
        "lab": "SYN-CRG-INTERNAL",
        "assays": dict(assays),
    }
    journal["internal_results"][internal_id] = internal
    batch = {
        "batch_id": batch_id,
        "order_id": norm["order_id"],
        "formula_id": norm["formula_id"],
        "formula_version": spec["current_version"],
        "family": spec["family"],
        "gallons": norm["gallons"],
        "blend_tank": spec["blend_tank"],
        "finish_tank": spec["finish_tank"],
        "lot_ids": [lot["lot_id"] for lot in lots],
        "movement_ids": [item["movement_id"] for item in movements],
        "internal_result_id": internal_id,
        "state": "BLENDED",
    }
    journal["batches"][batch_id] = batch
    _event(
        journal,
        "BATCH_OPENED",
        {"order_id": norm["order_id"], "batch_id": batch_id, "lots": len(lots), "movements": len(movements)},
    )
    return {
        "batch": batch,
        "lots": lots,
        "movements": movements,
        "internal": internal,
        "assays": assays,
        "token": token,
        "index": index,
    }


def _assay_oos(spec: dict[str, Any], assays: dict[str, str]) -> list[str]:
    failed: list[str] = []
    for name, bound in spec["assays"].items():
        value = Decimal(assays[name])
        if value < Decimal(bound["min"]) or value > Decimal(bound["max"]):
            failed.append(name)
    return failed


def _stage_coa(
    journal: dict[str, Any],
    norm: dict[str, Any],
    spec: dict[str, Any],
    built: dict[str, Any],
    external: dict[str, Any],
) -> dict[str, Any]:
    token = built["token"]
    index = built["index"]
    coa_id = f"CRG-COA-{token}-{index:02d}"
    assays = {
        name: qround(built["assays"][name], bound["places"])
        for name, bound in spec["assays"].items()
    }
    units = {name: bound["unit"] for name, bound in spec["assays"].items()}
    places = {name: bound["places"] for name, bound in spec["assays"].items()}
    coa = {
        "coa_id": coa_id,
        "order_id": norm["order_id"],
        "batch_id": built["batch"]["batch_id"],
        "formula_id": norm["formula_id"],
        "formula_version": spec["current_version"],
        "family": spec["family"],
        "gallons": norm["gallons"],
        "assays": assays,
        "units": units,
        "places": places,
        "internal_result_id": built["internal"]["result_id"],
        "external_packet_id": external["packet_id"],
        "state": "STAGED",
        "released": False,
        "disposed_by": "",
        "disposition": "",
    }
    journal["coas"][coa_id] = coa
    _event(journal, "COA_STAGED", {"order_id": norm["order_id"], "coa_id": coa_id})
    return coa


def _lineage_payload(
    norm: dict[str, Any],
    spec: dict[str, Any],
    built: dict[str, Any],
    external: dict[str, Any] | None,
    coa: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "demand_id": DEMAND_ID,
        "order_id": norm["order_id"],
        "batch_id": built["batch"]["batch_id"],
        "formula_id": norm["formula_id"],
        "formula_version": spec["current_version"],
        "lot_ids": list(built["batch"]["lot_ids"]),
        "movement_ids": list(built["batch"]["movement_ids"]),
        "internal_result_id": built["internal"]["result_id"],
        "external_packet_id": None if external is None else external["packet_id"],
        "coa_id": None if coa is None else coa["coa_id"],
    }


def _store_genealogy(
    journal: dict[str, Any],
    norm: dict[str, Any],
    spec: dict[str, Any],
    built: dict[str, Any],
    external: dict[str, Any] | None,
    coa: dict[str, Any] | None,
) -> dict[str, Any]:
    source = _lineage_payload(norm, spec, built, external, coa)
    genealogy = {
        "order_id": norm["order_id"],
        "batch_id": built["batch"]["batch_id"],
        "formula_id": norm["formula_id"],
        "formula_version": spec["current_version"],
        "lots": deepcopy(built["lots"]),
        "tank_movements": deepcopy(built["movements"]),
        "internal_result": deepcopy(built["internal"]),
        "external_packet": None if external is None else deepcopy(external),
        "coa": None if coa is None else deepcopy(coa),
        "source": source,
        "lineage_sha256": sha256_hex(source),
    }
    journal["genealogies"][norm["order_id"]] = genealogy
    return genealogy


def ingest_order(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_order(row)
    if not norm["order_id"]:
        return _hold(journal, order_id="", code=HOLD_FORMULA, extra={"reason": "MISSING_ORDER_ID"})
    if norm["order_id"] in journal["orders"]:
        _event(journal, "REPLAY_NOOP", {"order_id": norm["order_id"]})
        return {"kind": "REPLAY_NOOP", "order_id": norm["order_id"]}
    spec = FORMULAS.get(norm["formula_id"])
    if spec is None or norm["formula_version"] != spec["current_version"]:
        _record_order(
            journal,
            norm,
            "HOLD",
            {"hold_code": HOLD_FORMULA, "batch_id": ""},
        )
        return _hold(
            journal,
            order_id=norm["order_id"],
            code=HOLD_FORMULA,
            extra={
                "formula_id": norm["formula_id"],
                "formula_version": norm["formula_version"],
                "current_version": None if spec is None else spec["current_version"],
            },
        )
    built = _create_blend(journal, norm, spec)
    if not norm["external_packet_present"]:
        _record_order(
            journal,
            norm,
            "HOLD",
            {"hold_code": HOLD_MISSING_EXT, "batch_id": built["batch"]["batch_id"]},
        )
        _store_genealogy(journal, norm, spec, built, None, None)
        return _hold(
            journal,
            order_id=norm["order_id"],
            code=HOLD_MISSING_EXT,
            extra={"batch_id": built["batch"]["batch_id"]},
        )
    external_id = f"CRG-EXT-{built['token']}-{built['index']:02d}"
    external = {
        "packet_id": external_id,
        "order_id": norm["order_id"],
        "batch_id": built["batch"]["batch_id"],
        "lab": "SYN-CRG-EXTERNAL",
        "assays": dict(built["assays"]),
    }
    journal["external_packets"][external_id] = external
    failed = _assay_oos(spec, built["assays"])
    if failed:
        _record_order(
            journal,
            norm,
            "HOLD",
            {"hold_code": HOLD_OOS, "batch_id": built["batch"]["batch_id"], "oos_assays": failed},
        )
        _store_genealogy(journal, norm, spec, built, external, None)
        return _hold(
            journal,
            order_id=norm["order_id"],
            code=HOLD_OOS,
            extra={"batch_id": built["batch"]["batch_id"], "oos_assays": failed},
        )
    coa = _stage_coa(journal, norm, spec, built, external)
    genealogy = _store_genealogy(journal, norm, spec, built, external, coa)
    _record_order(
        journal,
        norm,
        "CLEAN",
        {"hold_code": "", "batch_id": built["batch"]["batch_id"], "coa_id": coa["coa_id"]},
    )
    _event(journal, "CLEAN", {"order_id": norm["order_id"], "batch_id": built["batch"]["batch_id"]})
    return {
        "kind": "CLEAN",
        "order_id": norm["order_id"],
        "batch_id": built["batch"]["batch_id"],
        "coa_id": coa["coa_id"],
        "lineage_sha256": genealogy["lineage_sha256"],
    }


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    before_orders = len(journal["orders"])
    before_batches = len(journal["batches"])
    before_movements = len(journal["movements"])
    before_holds = len(journal["holds"])
    effects = [ingest_order(journal, row) for row in (rows if rows is not None else build_acceptance_fixture())]
    return {
        "effects": effects,
        "added_orders": len(journal["orders"]) - before_orders,
        "added_batches": len(journal["batches"]) - before_batches,
        "added_movements": len(journal["movements"]) - before_movements,
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
    }


def attempt_autonomous_release(journal: dict[str, Any], actor: str = "SYSTEM") -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for coa in journal["coas"].values():
        effect = {
            "coa_id": coa["coa_id"],
            "order_id": coa["order_id"],
            "actor": actor,
            "ok": False,
            "code": "AUTONOMOUS_RELEASE_DENIED",
        }
        effects.append(effect)
        _event(journal, "AUTONOMOUS_RELEASE_DENIED", effect)
    return effects


def named_human_disposition(journal: dict[str, Any], actor: str = HUMAN_RELEASER) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    if _text(actor).upper() in AUTONOMOUS_NAMES or actor != HUMAN_RELEASER:
        for coa in journal["coas"].values():
            effect = {
                "coa_id": coa["coa_id"],
                "order_id": coa["order_id"],
                "actor": actor,
                "ok": False,
                "code": "NAMED_HUMAN_REQUIRED",
            }
            effects.append(effect)
            _event(journal, "DISPOSITION_DENIED", effect)
        return effects
    for coa in journal["coas"].values():
        if coa["state"] != "STAGED":
            effects.append(
                {
                    "coa_id": coa["coa_id"],
                    "order_id": coa["order_id"],
                    "actor": actor,
                    "ok": False,
                    "code": "NOT_STAGED",
                }
            )
            continue
        coa["disposed_by"] = actor
        coa["disposition"] = "HUMAN_STAGED_ACCEPT"
        coa["released"] = False
        effect = {
            "coa_id": coa["coa_id"],
            "order_id": coa["order_id"],
            "actor": actor,
            "ok": True,
            "code": "HUMAN_STAGED_ACCEPT",
            "released": False,
        }
        effects.append(effect)
        _event(journal, "HUMAN_DISPOSITION", effect)
    return effects


def _orphan_movements(journal: dict[str, Any]) -> list[str]:
    orphans: list[str] = []
    for movement in journal["movements"].values():
        batch_id = movement.get("batch_id")
        if not batch_id or batch_id not in journal["batches"]:
            orphans.append(movement["movement_id"])
            continue
        if movement["movement_id"] not in journal["batches"][batch_id]["movement_ids"]:
            orphans.append(movement["movement_id"])
    return orphans


def _duplicate_batches(journal: dict[str, Any]) -> list[str]:
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for batch in journal["batches"].values():
        owner = seen.get(batch["batch_id"])
        if owner is not None:
            dupes.append(batch["batch_id"])
        else:
            seen[batch["batch_id"]] = batch["order_id"]
    by_order: dict[str, list[str]] = {}
    for batch in journal["batches"].values():
        by_order.setdefault(batch["order_id"], []).append(batch["batch_id"])
    for batch_ids in by_order.values():
        if len(batch_ids) > 1:
            dupes.extend(batch_ids)
    return sorted(set(dupes))


def _count_state(journal: dict[str, Any], input_rows: int, replay: dict[str, Any]) -> dict[str, int]:
    hold_codes = [item["code"] for item in journal["holds"]]
    return {
        "input_rows": input_rows,
        "clean": sum(1 for item in journal["orders"].values() if item["state"] == "CLEAN"),
        "hold": len(journal["holds"]),
        "hold_formula_version_mismatch": hold_codes.count(HOLD_FORMULA),
        "hold_missing_external_result": hold_codes.count(HOLD_MISSING_EXT),
        "hold_oos": hold_codes.count(HOLD_OOS),
        "batches": len(journal["batches"]),
        "duplicate_batches": len(_duplicate_batches(journal)),
        "orphan_tank_movements": len(_orphan_movements(journal)),
        "staged_coa": sum(1 for item in journal["coas"].values() if item["state"] == "STAGED"),
        "genealogy": sum(
            1
            for order_id, order in journal["orders"].items()
            if order["state"] == "CLEAN" and order_id in journal["genealogies"]
        ),
        "human_disposed": sum(1 for item in journal["coas"].values() if item.get("disposition") == "HUMAN_STAGED_ACCEPT"),
        "autonomous_released": 0,
        "production_writes": journal["production_writes"],
        "replay_added_orders": replay["added_orders"],
        "replay_added_batches": replay["added_batches"],
        "replay_added_movements": replay["added_movements"],
        "replay_added_holds": replay["added_holds"],
    }


def _audit_payload(journal: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    holds = sorted(
        ({"order_id": item["order_id"], "code": item["code"]} for item in journal["holds"]),
        key=lambda item: item["order_id"],
    )
    clean_ids = sorted(order_id for order_id, order in journal["orders"].items() if order["state"] == "CLEAN")
    genealogies = {
        order_id: journal["genealogies"][order_id]["lineage_sha256"]
        for order_id in clean_ids
        if order_id in journal["genealogies"]
    }
    coas = {
        item["order_id"]: {
            "coa_id": item["coa_id"],
            "assays": item["assays"],
            "places": item["places"],
            "state": item["state"],
            "disposition": item.get("disposition") or "",
            "released": item["released"],
        }
        for item in sorted(journal["coas"].values(), key=lambda row: row["order_id"])
    }
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "counts": counts,
        "holds": holds,
        "batches": sorted(journal["batches"]),
        "movements": sorted(journal["movements"]),
        "genealogies": genealogies,
        "coas": coas,
        "human_releaser": HUMAN_RELEASER,
        "autonomous_released": 0,
        "production_writes": 0,
        "adapters": {
            "formula": "SIMULATED_READ_ONLY",
            "lots": "SIMULATED_READ_ONLY",
            "tanks": "SIMULATED_READ_ONLY",
            "internal_lab": "SIMULATED_READ_ONLY",
            "external_lab": "SIMULATED_READ_ONLY",
            "coa": "SIMULATED_STAGED",
            "production_write": "NOT_SENT",
            "outreach": "NOT_SENT",
        },
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_order(journal, row) for row in inbound]
    replay = replay_into(journal, inbound)
    autonomous = attempt_autonomous_release(journal)
    human = named_human_disposition(journal, HUMAN_RELEASER)
    counts = _count_state(journal, len(inbound), replay)
    clean_orders = sorted(
        (item for item in journal["orders"].values() if item["state"] == "CLEAN"),
        key=lambda item: item["order_id"],
    )
    audit = _audit_payload(journal, counts)
    audit_sha256 = sha256_hex(audit)
    clean_genealogies = {
        order_id: journal["genealogies"][order_id]
        for order_id in (item["order_id"] for item in clean_orders)
        if order_id in journal["genealogies"]
    }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": counts["input_rows"],
        "clean": counts["clean"],
        "hold": counts["hold"],
        "hold_formula_version_mismatch": counts["hold_formula_version_mismatch"],
        "hold_missing_external_result": counts["hold_missing_external_result"],
        "hold_oos": counts["hold_oos"],
        "hold_codes": [item["code"] for item in journal["holds"]],
        "hold_code_set": sorted({item["code"] for item in journal["holds"]}),
        "hold_records": deepcopy(journal["holds"]),
        "batches": counts["batches"],
        "batch_ids": sorted(journal["batches"]),
        "duplicate_batches": counts["duplicate_batches"],
        "orphan_tank_movements": counts["orphan_tank_movements"],
        "orphan_movement_ids": _orphan_movements(journal),
        "duplicate_batch_ids": _duplicate_batches(journal),
        "staged_coa": counts["staged_coa"],
        "genealogy": counts["genealogy"],
        "genealogies": clean_genealogies,
        "human_disposed": counts["human_disposed"],
        "autonomous_released": 0,
        "production_writes": 0,
        "replay_added_orders": counts["replay_added_orders"],
        "replay_added_batches": counts["replay_added_batches"],
        "replay_added_movements": counts["replay_added_movements"],
        "replay_added_holds": counts["replay_added_holds"],
        "replay_noops": replay["replay_noops"],
        "effects": effects,
        "replay": replay,
        "autonomous_release_effects": autonomous,
        "human_disposition_effects": human,
        "orders": deepcopy(journal["orders"]),
        "batch_records": deepcopy(journal["batches"]),
        "lots": deepcopy(journal["lots"]),
        "movements": deepcopy(journal["movements"]),
        "internal_results": deepcopy(journal["internal_results"]),
        "external_packets": deepcopy(journal["external_packets"]),
        "coas": deepcopy(journal["coas"]),
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "qc_decisions": 0,
        "billing_writes": 0,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "fixture_sha256": sha256_hex(inbound),
        "catalog_sha256": CATALOG_SHA256,
        "audit": audit,
        "audit_sha256": audit_sha256,
        "human_releaser": HUMAN_RELEASER,
        "human_role": HUMAN_ROLE,
    }
    body["manifest_sha256"] = sha256_hex(
        {
            key: value
            for key, value in body.items()
            if key
            not in {
                "manifest_sha256",
                "effects",
                "replay",
                "autonomous_release_effects",
                "human_disposition_effects",
                "orders",
                "batch_records",
                "lots",
                "movements",
                "internal_results",
                "external_packets",
                "coas",
                "events",
                "genealogies",
            }
        }
    )
    return body


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {key: result.get(key) for key in GOLDEN_COUNTS}
    return {"expected": dict(GOLDEN_COUNTS), "actual": actual, "match": actual == GOLDEN_COUNTS}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key, expected in GOLDEN_COUNTS.items():
        if result.get(key) != expected:
            failures.append(f"{key}!={expected} actual={result.get(key)}")
    if result.get("hold_code_set") != sorted(HOLD_CODES):
        failures.append("hold_code_set")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    human = result.get("human_disposition_effects") or []
    if sum(1 for item in human if item.get("ok")) != CLEAN_COUNT:
        failures.append("human_disposed_not_64")
    if any(item.get("released") for item in human):
        failures.append("human_released_production")
    if len(result.get("batch_ids") or []) != BLENDED_COUNT:
        failures.append("batch_ids_count")
    if len(set(result.get("batch_ids") or [])) != BLENDED_COUNT:
        failures.append("batch_ids_not_unique")
    genealogies = result.get("genealogies") or {}
    if len(genealogies) != CLEAN_COUNT:
        failures.append("genealogy_count")
    hashes = [item["lineage_sha256"] for item in genealogies.values()]
    if len(set(hashes)) != CLEAN_COUNT:
        failures.append("lineage_not_unique")
    for order_id, genealogy in genealogies.items():
        if not genealogy.get("lots") or not genealogy.get("tank_movements"):
            failures.append(f"genealogy_incomplete:{order_id}")
            break
        if genealogy.get("coa") is None or genealogy.get("external_packet") is None:
            failures.append(f"genealogy_missing_coa_or_ext:{order_id}")
            break
        if genealogy.get("lineage_sha256") != sha256_hex(genealogy["source"]):
            failures.append(f"lineage_not_self:{order_id}")
            break
    for coa in (result.get("coas") or {}).values():
        if coa.get("released"):
            failures.append("coa_released")
            break
        for name, places in (coa.get("places") or {}).items():
            value = (coa.get("assays") or {}).get(name)
            if value is None or value != qround(value, places):
                failures.append(f"coa_rounding:{coa.get('coa_id')}:{name}")
                break
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if sha256_hex(result.get("audit")) != result.get("audit_sha256"):
        failures.append("audit_hash_not_self")
    return failures


def write_pack(result: dict[str, Any], root: Path | None = None) -> dict[str, str]:
    pack = root or PACK_DIR
    receipts = pack / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    files = {
        receipts / "run.json": {
            "ok": not pass_contract(result),
            "demand_id": DEMAND_ID,
            "buyer": BUYER,
            "counts": expected_actual(result),
            "audit_sha256": result["audit_sha256"],
            "fixture_sha256": result["fixture_sha256"],
            "catalog_sha256": result["catalog_sha256"],
            "manifest_sha256": result["manifest_sha256"],
            "truth_gate": TRUTH_GATE,
            "cash_usd": 0,
        },
        receipts / "holds.json": result["hold_records"],
        receipts / "batches.json": result["batch_records"],
        receipts / "movements.json": result["movements"],
        receipts / "coas.json": result["coas"],
        receipts / "genealogies.json": {
            order_id: {
                "order_id": item["order_id"],
                "batch_id": item["batch_id"],
                "formula_id": item["formula_id"],
                "formula_version": item["formula_version"],
                "lineage_sha256": item["lineage_sha256"],
                "lot_ids": item["source"]["lot_ids"],
                "movement_ids": item["source"]["movement_ids"],
                "coa_id": item["source"]["coa_id"],
            }
            for order_id, item in result["genealogies"].items()
        },
        receipts / "replay.json": {
            "added_orders": result["replay_added_orders"],
            "added_batches": result["replay_added_batches"],
            "added_movements": result["replay_added_movements"],
            "added_holds": result["replay_added_holds"],
            "replay_noops": result["replay_noops"],
        },
        receipts / "audit.json": result["audit"],
        pack / "fixture.json": build_acceptance_fixture(),
        pack / "source.json": catalog_payload(),
    }
    for path, payload in files.items():
        path.write_text(_canonical(payload) + "\n", encoding="utf-8")
        written[str(path.relative_to(pack.parent.parent) if pack.parent.name == "revenue" else path)] = sha256_hex(
            payload
        )
    return written


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_order(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if sha256_hex(first["audit"]) != first.get("audit_sha256"):
        failures.append("audit_hash_not_self")
    if replay.get("added_orders") != 0 or replay.get("added_batches") != 0:
        failures.append("replay_added")
    if replay.get("added_movements") != 0 or replay.get("added_holds") != 0:
        failures.append("replay_added_movements_or_holds")
    write_pack(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "audit_sha256": first.get("audit_sha256"),
        "fixture_sha256": first.get("fixture_sha256"),
        "catalog_sha256": first.get("catalog_sha256"),
        "expected": GOLDEN_COUNTS,
        "actual": expected_actual(first)["actual"],
        "hold_code_set": first.get("hold_code_set"),
        "replay_added_orders": replay.get("added_orders"),
        "official_binary": OFFICIAL_BINARY,
        "truth_gate": TRUTH_GATE,
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
