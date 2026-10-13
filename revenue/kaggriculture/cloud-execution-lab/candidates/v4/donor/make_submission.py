"""Build the score-facing V3.1 submission archive from the final assembled package.

usage: python make_submission.py <candidates/v3 dir> <canonical tar.gz> <out.tar.gz> [horizon]

Uses build_v3.package_files() and build_v3.build_bytes() so the archive remains the
same deterministic function of (canonical, overlay, apply_v3), then performs only the
reviewed LAST score-facing TITAN-CONFIG transform.

The transform is deliberately fail closed. It will not manufacture upstream gameplay
decisions: the literal assembled input must already carry the held H8/open0/native
ROW_ORDER+flush, cattle-OFF, H4, repaired L3@648, B5 CARROT+JIT, strict row-shed and
fert-hand tuple. Under that theorem the only actual config value delta is
r04_sale_window=false -> true.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections.abc import Mapping


DEFAULT_SUBMISSION_HORIZON = 8
PRESERVED_TRUE_KEYS = (
    "r04_row_order",
    "r04_evening_flush",
    "r04_sale_fertilizer",
    "r04_strawberry_topup",
    "r04_no_late_sale_advance",
    "r04_b5_carrot_fertilizer",
    "r04_b5_jit_fertilize",
    "r04_row_shed",
    "r04_fert_hand",
)
PRESERVED_FALSE_KEYS = (
    "r04_kill_late_water",
    "r04_strawberry_endgame",
)
TRANSFORM_KEYS = frozenset(
    ("r04_sale_window", "r04_sale_horizon", "r04_sale_fertilizer", "r04_cattle_early")
)
SUBMISSION_KEYS = (
    "r03_full_router",
    "r04_sale_window",
    "r04_sale_horizon",
    "r04_open_roundtrip",
    "r04_row_order",
    "r04_evening_flush",
    "r04_sale_fertilizer",
    "r04_cattle_early",
    "r04_kill_late_water",
    "r04_strawberry_endgame",
    "r04_strawberry_max_plants",
    "r04_strawberry_topup",
    "r04_no_late_sale_advance",
    "r04_no_late_sale_advance_step",
    "r04_b5_carrot_fertilizer",
    "r04_b5_jit_fertilize",
    "r04_row_shed",
    "r04_fert_hand",
    "r01_shop_router",
    "r02_route_bank",
)


def _require_exact_bool(config: Mapping[str, object], key: str, expected: bool) -> None:
    if key not in config or type(config[key]) is not bool or config[key] is not expected:
        raise AssertionError(
            f"{key} must be literal {str(expected).lower()} before submission transform"
        )


def _require_exact_int(config: Mapping[str, object], key: str, expected: int) -> None:
    value = config.get(key)
    if type(value) is not int or value != expected:
        raise AssertionError(f"{key} must be exact integer {expected}")


def _require_submission_horizon(horizon: object) -> None:
    if type(horizon) is not int or horizon != DEFAULT_SUBMISSION_HORIZON:
        raise AssertionError(
            f"submission horizon override must equal held H{DEFAULT_SUBMISSION_HORIZON} decision"
        )


def require_final_input(config: Mapping[str, object]) -> None:
    """Fail closed unless the complete held winning assembly is already present."""
    if not isinstance(config, Mapping):
        raise AssertionError("TITAN-CONFIG must be a mapping")

    _require_exact_bool(config, "r04_sale_window", False)
    _require_exact_int(config, "r04_sale_horizon", DEFAULT_SUBMISSION_HORIZON)
    _require_exact_int(config, "r04_open_roundtrip", 0)
    _require_exact_int(config, "r04_strawberry_max_plants", 8)
    _require_exact_int(config, "r04_no_late_sale_advance_step", 648)

    for key in PRESERVED_TRUE_KEYS:
        _require_exact_bool(config, key, True)
    for key in PRESERVED_FALSE_KEYS:
        _require_exact_bool(config, key, False)
    _require_exact_bool(config, "r04_cattle_early", False)


def require_only_transform_keys_changed(
    before: Mapping[str, object], after: Mapping[str, object]
) -> None:
    """Prove the score-facing transform did not consume ownership of upstream lanes."""
    if set(before) != set(after):
        raise AssertionError("submission transform may not add or remove config keys")
    for key in before:
        if key in TRANSFORM_KEYS:
            continue
        if type(before[key]) is not type(after[key]) or before[key] != after[key]:
            raise AssertionError(f"non-score-facing config drift: {key}")


def require_final_output(
    before: Mapping[str, object], after: Mapping[str, object]
) -> None:
    """Bind the exact score-facing post-state and preservation theorem."""
    require_final_input(before)
    if not isinstance(after, Mapping):
        raise AssertionError("transformed TITAN-CONFIG must be a mapping")
    require_only_transform_keys_changed(before, after)
    expected = {
        "r04_sale_window": True,
        "r04_sale_horizon": DEFAULT_SUBMISSION_HORIZON,
        "r04_sale_fertilizer": True,
        "r04_cattle_early": False,
    }
    for key, value in expected.items():
        if key not in after or type(after[key]) is not type(value) or after[key] != value:
            raise AssertionError(
                f"final score tuple drift: {key}={after.get(key)!r}, expected {value!r}"
            )


def apply_submission_config(files, horizon=None):
    """Return detached package files after the exact held LAST score transform."""
    out = dict(files)
    config = json.loads(out["TITAN-CONFIG.json"].decode("utf-8"))
    if not isinstance(config, dict):
        raise AssertionError("TITAN-CONFIG.json must decode to an object")

    require_final_input(config)
    if horizon is not None:
        _require_submission_horizon(horizon)

    before = copy.deepcopy(config)
    config["r04_sale_window"] = True
    config["r04_sale_horizon"] = DEFAULT_SUBMISSION_HORIZON
    config["r04_sale_fertilizer"] = True
    config["r04_cattle_early"] = False
    require_final_output(before, config)

    out["TITAN-CONFIG.json"] = (json.dumps(config, indent=2) + "\n").encode("utf-8")
    if set(out) != set(files):
        raise AssertionError("submission transform may not add or remove package members")
    return out, config


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in (3, 4):
        raise SystemExit(
            "usage: python make_submission.py <candidates/v3 dir> <canonical tar.gz> <out.tar.gz> [horizon]"
        )
    v3, canon, output = argv[:3]

    # Fail closed on caller-controlled score-facing input before changing sys.path,
    # importing the package builder, or touching canonical/package bytes.
    horizon = None
    if len(argv) == 4:
        horizon = int(argv[3])
        _require_submission_horizon(horizon)

    sys.path.insert(0, v3)
    import build_v3  # noqa: E402

    base_files = build_v3.package_files(canon)
    base_digest = hashlib.sha256(build_v3.build_bytes(base_files)).hexdigest()
    files, config = apply_submission_config(base_files, horizon)
    blob = build_v3.build_bytes(files)
    with open(output, "wb") as handle:
        handle.write(blob)

    print("base package", base_digest)
    print(
        "submission  ",
        hashlib.sha256(blob).hexdigest(),
        len(files),
        "files",
        len(blob),
        "bytes ->",
        output,
    )
    print("route keys:", {key: config[key] for key in SUBMISSION_KEYS})


if __name__ == "__main__":
    main()
