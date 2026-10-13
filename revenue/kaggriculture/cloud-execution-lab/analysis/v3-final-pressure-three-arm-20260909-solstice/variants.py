"""Exact source/config arm construction for the final-pressure experiment."""
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Mapping

import evidence

VARIANTS = ("pressure_off", "legacy_in_pipeline", "final_boundary")
PAIRINGS = (
    ("final_boundary", "pressure_off"),
    ("final_boundary", "legacy_in_pipeline"),
    ("legacy_in_pipeline", "pressure_off"),
)
LEGACY_FROM = b"return FinalPressureAgent(features, fourth_quadrant_admission=admission)"
LEGACY_TO = b"return TitanAgent(features, fourth_quadrant_admission=admission)"
CONFIG_PRESSURE_TRUE = b'"market_pressure": true'
CONFIG_PRESSURE_FALSE = b'"market_pressure": false'


def _config_with_pressure(config: Mapping[str, Any], enabled: bool) -> dict[str, Any]:
    result = dict(config)
    result["market_pressure"] = enabled
    return result


def patch_pressure_off_config(data: bytes) -> bytes:
    """Flip only the canonical JSON boolean token; retain every other byte."""
    if data.count(CONFIG_PRESSURE_TRUE) != 1:
        raise evidence.EvidenceError(
            "Canonical config must contain one exact market_pressure=true token"
        )
    if CONFIG_PRESSURE_FALSE in data:
        raise evidence.EvidenceError(
            "Canonical config unexpectedly contains market_pressure=false"
        )
    result = data.replace(CONFIG_PRESSURE_TRUE, CONFIG_PRESSURE_FALSE, 1)
    value = evidence.strict_json_bytes(result, label="pressure-off TITAN-CONFIG.json")
    if not isinstance(value, dict) or value.get("market_pressure") is not False:
        raise evidence.EvidenceError(
            "Pressure-off config patch did not produce market_pressure=false"
        )
    return result


def patch_legacy_entrypoint(data: bytes) -> bytes:
    """Replace exactly the final-boundary constructor with plain TitanAgent."""
    if data.count(LEGACY_FROM) != 1:
        raise evidence.EvidenceError(
            "Canonical main.py must contain exactly one FinalPressureAgent constructor return"
        )
    if LEGACY_TO in data:
        raise evidence.EvidenceError(
            "Canonical main.py already contains the legacy constructor"
        )
    result = data.replace(LEGACY_FROM, LEGACY_TO, 1)
    try:
        compile(result.decode("utf-8"), "legacy-main.py", "exec")
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise evidence.EvidenceError(
            f"Legacy entrypoint patch is not valid Python: {exc}"
        ) from exc
    return result


def prepare_variants(
    base: Path, destination: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialize and prove the exact three-arm source/config delta."""
    base = Path(base).resolve()
    destination = Path(destination)
    config_value, config_snap = evidence.read_json(base / "TITAN-CONFIG.json")
    if not isinstance(config_value, dict):
        raise evidence.EvidenceError("TITAN-CONFIG.json must be an object")
    current_flag = config_value.get("market_pressure")
    if not isinstance(current_flag, bool):
        raise evidence.EvidenceError("market_pressure must be a JSON boolean")
    if current_flag is not True:
        raise evidence.EvidenceError(
            "Canonical archive must have market_pressure=true"
        )
    main_snap = evidence.snapshot(base / "main.py", max_bytes=1 << 20)
    legacy_main = patch_legacy_entrypoint(main_snap.data)
    pressure_off_config = patch_pressure_off_config(config_snap.data)
    base_manifest = evidence.tree_manifest(base)

    specs = (
        (
            "pressure_off",
            _config_with_pressure(config_value, False),
            pressure_off_config,
            main_snap.data,
            {"TITAN-CONFIG.json"},
        ),
        (
            "legacy_in_pipeline",
            dict(config_value),
            config_snap.data,
            legacy_main,
            {"main.py"},
        ),
        (
            "final_boundary",
            dict(config_value),
            config_snap.data,
            main_snap.data,
            set(),
        ),
    )
    rows: list[dict[str, Any]] = []
    for name, built_config, config_bytes, main_bytes, expected_changes in specs:
        root = destination / name
        if root.exists():
            raise evidence.EvidenceError(f"Variant destination already exists: {root}")
        shutil.copytree(base, root, symlinks=False)
        (root / "TITAN-CONFIG.json").write_bytes(config_bytes)
        (root / "main.py").write_bytes(main_bytes)

        for key, value in config_value.items():
            if key != "market_pressure" and built_config.get(key) != value:
                raise evidence.EvidenceError(
                    f"Variant {name} changed non-factor config key {key!r}"
                )
        if set(built_config) != set(config_value):
            raise evidence.EvidenceError(
                f"Variant {name} changed the config key set"
            )

        manifest = evidence.tree_manifest(root)
        changes = set(evidence.changed_paths(base_manifest, manifest))
        if changes != expected_changes:
            raise evidence.EvidenceError(
                f"Variant {name} changed {sorted(changes)}, "
                f"expected {sorted(expected_changes)}"
            )
        config_after, config_after_snap = evidence.read_json(
            root / "TITAN-CONFIG.json"
        )
        if config_after != built_config:
            raise evidence.EvidenceError(f"Variant {name} config readback differs")
        rows.append(
            {
                "name": name,
                "candidate": str((root / "main.py").resolve()) + "::agent",
                "root": str(root.resolve()),
                "changed_paths": sorted(changes),
                "main_sha256": evidence.snapshot(root / "main.py").sha256,
                "config_sha256": config_after_snap.sha256,
                "market_pressure": config_after["market_pressure"],
                "tree_file_count": len(manifest),
                "tree_manifest_sha256": evidence.manifest_sha256(manifest),
            }
        )

    if rows[0]["main_sha256"] != rows[2]["main_sha256"]:
        raise evidence.EvidenceError("pressure_off must keep canonical main.py")
    if rows[1]["config_sha256"] != rows[2]["config_sha256"]:
        raise evidence.EvidenceError(
            "legacy_in_pipeline must keep canonical config bytes"
        )
    if rows[1]["main_sha256"] == rows[2]["main_sha256"]:
        raise evidence.EvidenceError(
            "legacy_in_pipeline must differ from canonical main.py"
        )
    return rows, {
        "config": config_value,
        "config_sha256": config_snap.sha256,
        "main_sha256": main_snap.sha256,
        "tree_file_count": len(base_manifest),
        "tree_manifest_sha256": evidence.manifest_sha256(base_manifest),
    }
