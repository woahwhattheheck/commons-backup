from __future__ import annotations

from copy import deepcopy
from typing import Any

from .gate import (
    DUPLICATE_ASSIGNMENT,
    ORPHANED_RUN_LINK,
    SOURCE_DESTINATION_MISMATCH,
    STALE_PROTOCOL,
    VOLUME_BALANCE_FAILURE,
    WRONG_POOL_MEMBERSHIP,
)

ROWS = "ABCDEFGHIJKLMNOP"
COLS = tuple(range(1, 25))
CLEAN_COUNT = 360
DEFECT_COUNT = 24
TOTAL_COUNT = CLEAN_COUNT + DEFECT_COUNT


def _well(index: int) -> str:
    return f"{ROWS[(index // 24) % len(ROWS)]}{(index % 24) + 1:02d}"


def build_synthetic_case() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, list[str]]]:
    compounds: dict[str, Any] = {}
    pools: dict[str, list[str]] = {f"POOL-{i:03d}": [] for i in range(1, 31)}
    protocols = {
        "PROTO-HTS-A": {
            "current_version": "7.3",
            "control_well_map_hash": "sha256:control-map-a-v7.3",
        },
        "PROTO-HTS-B": {
            "current_version": "4.1",
            "control_well_map_hash": "sha256:control-map-b-v4.1",
        },
    }
    runs: dict[str, Any] = {}
    transfers: list[dict[str, Any]] = []

    for i in range(1, CLEAN_COUNT + 1):
        compound_id = f"CMP-{i:06d}"
        source_plate = f"SRC-{((i - 1) // 96) + 1:03d}"
        source_well = _well(i - 1)
        source_lot = f"SLOT-{((i - 1) // 48) + 1:03d}"
        concentration = "10" if i % 3 else "25"
        compounds[compound_id] = {
            "source_vial_id": f"VIAL-{i:06d}",
            "source_plate_id": source_plate,
            "source_well": source_well,
            "source_plate_lot": source_lot,
            "source_concentration_um": concentration,
        }
        membership_type = "singleton" if i <= 180 else "pool"
        pool_id = None
        if membership_type == "pool":
            pool_id = f"POOL-{((i - 181) % 30) + 1:03d}"
            pools[pool_id].append(compound_id)

        destination_plate = f"DST-{((i - 1) // 96) + 1:03d}"
        destination_well = _well(i - 1)
        protocol_id = "PROTO-HTS-A" if destination_plate in {"DST-001", "DST-002"} else "PROTO-HTS-B"
        run_id = f"RUN-{destination_plate}"
        runs[run_id] = {
            "destination_plate_id": destination_plate,
            "assay_protocol_id": protocol_id,
        }
        version = protocols[protocol_id]["current_version"]
        control_hash = protocols[protocol_id]["control_well_map_hash"]
        transfer_volume = 1 + (i % 4)
        before = 20 + (i % 7)
        after = before - transfer_volume
        transfers.append(
            {
                "sequence": i,
                "transfer_id": f"XFER-{i:06d}",
                "compound_master_id": compound_id,
                "source_vial_id": f"VIAL-{i:06d}",
                "source_plate_id": source_plate,
                "source_well": source_well,
                "source_plate_lot": source_lot,
                "source_volume_ul_before": str(before),
                "transfer_volume_ul": str(transfer_volume),
                "source_volume_ul_after": str(after),
                "source_concentration_um": concentration,
                "membership_type": membership_type,
                "pool_id": pool_id,
                "destination_plate_id": destination_plate,
                "destination_well": destination_well,
                "destination_plate_lot": f"DLOT-{((i - 1) // 96) + 1:03d}",
                "destination_compound_master_id": compound_id,
                "assay_protocol_id": protocol_id,
                "assay_protocol_version": version,
                "control_well_map_hash": control_hash,
                "instrument_run_id": run_id,
            }
        )

    expected: dict[str, list[str]] = {
        DUPLICATE_ASSIGNMENT: [],
        SOURCE_DESTINATION_MISMATCH: [],
        WRONG_POOL_MEMBERSHIP: [],
        VOLUME_BALANCE_FAILURE: [],
        STALE_PROTOCOL: [],
        ORPHANED_RUN_LINK: [],
    }

    def clone_clean(source_index: int, sequence: int) -> dict[str, Any]:
        row = deepcopy(transfers[source_index])
        row["sequence"] = sequence
        row["transfer_id"] = f"XFER-{sequence:06d}"
        return row

    seq = CLEAN_COUNT
    for source_index in (0, 1, 2, 3):
        seq += 1
        row = clone_clean(source_index, seq)
        transfers.append(row)
        expected[DUPLICATE_ASSIGNMENT].append(row["transfer_id"])

    for source_index in (4, 5, 6, 7):
        seq += 1
        row = clone_clean(source_index, seq)
        row["destination_plate_id"] = "DST-005"
        row["destination_well"] = _well(seq - 1)
        row["destination_plate_lot"] = "DLOT-005"
        row["instrument_run_id"] = "RUN-DST-005"
        row["destination_compound_master_id"] = f"CMP-MISMATCH-{seq:06d}"
        runs["RUN-DST-005"] = {
            "destination_plate_id": "DST-005",
            "assay_protocol_id": row["assay_protocol_id"],
        }
        transfers.append(row)
        expected[SOURCE_DESTINATION_MISMATCH].append(row["transfer_id"])

    for source_index in (180, 181, 182, 183):
        seq += 1
        row = clone_clean(source_index, seq)
        row["destination_plate_id"] = "DST-006"
        row["destination_well"] = _well(seq - 1)
        row["destination_plate_lot"] = "DLOT-006"
        row["instrument_run_id"] = "RUN-DST-006"
        wrong_pool = "POOL-030" if row["pool_id"] != "POOL-030" else "POOL-029"
        row["pool_id"] = wrong_pool
        runs["RUN-DST-006"] = {
            "destination_plate_id": "DST-006",
            "assay_protocol_id": row["assay_protocol_id"],
        }
        transfers.append(row)
        expected[WRONG_POOL_MEMBERSHIP].append(row["transfer_id"])

    for source_index in (8, 9, 10, 11):
        seq += 1
        row = clone_clean(source_index, seq)
        row["destination_plate_id"] = "DST-007"
        row["destination_well"] = _well(seq - 1)
        row["destination_plate_lot"] = "DLOT-007"
        row["instrument_run_id"] = "RUN-DST-007"
        row["source_volume_ul_after"] = str(
            int(row["source_volume_ul_before"]) - int(row["transfer_volume_ul"]) + 1
        )
        runs["RUN-DST-007"] = {
            "destination_plate_id": "DST-007",
            "assay_protocol_id": row["assay_protocol_id"],
        }
        transfers.append(row)
        expected[VOLUME_BALANCE_FAILURE].append(row["transfer_id"])

    for source_index in (12, 13, 14, 15):
        seq += 1
        row = clone_clean(source_index, seq)
        row["destination_plate_id"] = "DST-008"
        row["destination_well"] = _well(seq - 1)
        row["destination_plate_lot"] = "DLOT-008"
        row["instrument_run_id"] = "RUN-DST-008"
        row["assay_protocol_version"] = "0.9"
        runs["RUN-DST-008"] = {
            "destination_plate_id": "DST-008",
            "assay_protocol_id": row["assay_protocol_id"],
        }
        transfers.append(row)
        expected[STALE_PROTOCOL].append(row["transfer_id"])

    for source_index in (16, 17, 18, 19):
        seq += 1
        row = clone_clean(source_index, seq)
        row["destination_plate_id"] = "DST-009"
        row["destination_well"] = _well(seq - 1)
        row["destination_plate_lot"] = "DLOT-009"
        row["instrument_run_id"] = f"RUN-ORPHAN-{seq:03d}"
        transfers.append(row)
        expected[ORPHANED_RUN_LINK].append(row["transfer_id"])

    assert seq == TOTAL_COUNT
    context = {
        "compounds": compounds,
        "pools": pools,
        "protocols": protocols,
        "runs": runs,
    }
    return transfers, context, expected
