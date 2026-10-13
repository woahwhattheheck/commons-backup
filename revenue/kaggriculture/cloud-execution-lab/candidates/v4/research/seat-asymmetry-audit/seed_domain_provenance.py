#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound episode-seed provenance and finite-panel inference for TITAN V4.

Research only. This module distinguishes source-complete fallback provenance from
externally supplied seeds, and lets an explicitly byte-bound offline panel seed
set be filtered using the already-merged SEEDSTREAM public-evidence semantics.
It never converts panel uniqueness into hosted/global hidden-seed authority.
"""
from __future__ import annotations

import argparse
import hashlib
import types
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

UTILS_GIT_BLOB = "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87"
ENGINE_CONFIG_GIT_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
EVALUATOR_GIT_BLOB = "1fb6b655bb4ca1e1684be165a8ef513e2e6c2325"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SEEDSTREAM_GIT_BLOB = "c02ab05ed7684508f02e383fa3281f29e2f60fa6"
FALLBACK_STOP_EXCLUSIVE = 2**31

HERE = Path(__file__).resolve()
LAB_ROOT = HERE.parents[4] if len(HERE.parents) > 4 else HERE.parent
DEFAULT_UTILS = LAB_ROOT / "reference" / "evaluator" / "upstream" / "utils.py"
DEFAULT_ENGINE = LAB_ROOT / "reference" / "engine" / "kaggriculture.py"
DEFAULT_ENGINE_CONFIG = LAB_ROOT / "reference" / "engine" / "kaggriculture.json"
DEFAULT_EVALUATOR = LAB_ROOT / "reference" / "evaluator" / "evaluate.py"
DEFAULT_SEEDSTREAM = HERE.with_name("seed_stream_identifiability.py")


class ProvenanceError(ValueError):
    pass


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _read_bound(path: Path, expected_blob: str, label: str) -> tuple[bytes, str]:
    raw = path.read_bytes()
    actual = git_blob(raw)
    if actual != expected_blob:
        raise ProvenanceError(f"{label} git blob mismatch: expected {expected_blob}, got {actual}")
    return raw, actual


def _strict_json(raw: bytes, label: str) -> Any:
    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ProvenanceError(f"{label} has duplicate JSON key {key!r}")
            out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=hook)
    except ProvenanceError:
        raise
    except Exception as exc:
        raise ProvenanceError(f"{label} is not strict JSON: {exc}") from exc


def authenticate_source_contract(
    *,
    utils_path: Path = DEFAULT_UTILS,
    engine_path: Path = DEFAULT_ENGINE,
    engine_config_path: Path = DEFAULT_ENGINE_CONFIG,
    evaluator_path: Path = DEFAULT_EVALUATOR,
    seedstream_path: Path = DEFAULT_SEEDSTREAM,
) -> dict:
    """Authenticate the exact pinned provenance closure and derive its theorem."""
    utils_raw, utils_blob = _read_bound(Path(utils_path), UTILS_GIT_BLOB, "upstream utils")
    _, engine_blob = _read_bound(Path(engine_path), ENGINE_GIT_BLOB, "official engine")
    cfg_raw, cfg_blob = _read_bound(Path(engine_config_path), ENGINE_CONFIG_GIT_BLOB, "engine config")
    evaluator_raw, evaluator_blob = _read_bound(Path(evaluator_path), EVALUATOR_GIT_BLOB, "offline evaluator")
    _, seedstream_blob = _read_bound(Path(seedstream_path), SEEDSTREAM_GIT_BLOB, "merged SEEDSTREAM")

    utils = utils_raw.decode("utf-8")
    evaluator = evaluator_raw.decode("utf-8")
    required_utils = (
        'seed = env.info.get("seed")',
        'seed = getattr(config, config_key, None)',
        'seed = fallback() if fallback is not None else random.randrange(2**31)',
        'setattr(config, config_key, None)',
        'env.info["seed"] = seed',
    )
    if any(anchor not in utils for anchor in required_utils):
        raise ProvenanceError("pinned upstream utils missing required resolve_episode_seed chronology")

    required_evaluator = (
        "cfg.seed = seed",
        "env = Struct(configuration=cfg, done=False, info={})",
        "engine.interpreter(state, env)",
        'if cfg.get("seed") is not None:',
        'raise ValueError("Environment seed must not be exposed to agents")',
    )
    if any(anchor not in evaluator for anchor in required_evaluator):
        raise ProvenanceError("pinned offline evaluator missing seed-injection/scrub chronology")

    config = _strict_json(cfg_raw, "engine config")
    try:
        seed_schema = config["configuration"]["seed"]
    except (KeyError, TypeError) as exc:
        raise ProvenanceError("engine config missing configuration.seed") from exc
    if type(seed_schema) is not dict:
        raise ProvenanceError("configuration.seed must be an object")
    if seed_schema.get("type") != ["integer", "null"] or seed_schema.get("default") is not None:
        raise ProvenanceError("engine seed schema type/default changed")
    if "minimum" in seed_schema or "maximum" in seed_schema:
        raise ProvenanceError("engine seed schema unexpectedly gained a finite bound")

    return {
        "schema": "titan.v4.seed-domain-source-contract/v1",
        "source_blobs": {
            "utils": utils_blob,
            "engine_config": cfg_blob,
            "evaluator": evaluator_blob,
            "engine": engine_blob,
            "seedstream": seedstream_blob,
        },
        "precedence": ["preserved_env_info", "explicit_config", "fallback"],
        "implicit_fallback": {
            "kind": "SOURCE_COMPLETE_FINITE_INTERVAL",
            "start": 0,
            "stop_exclusive": FALLBACK_STOP_EXCLUSIVE,
            "size": FALLBACK_STOP_EXCLUSIVE,
            "complete_by_pinned_source": True,
            "enumeration_or_production_cracking_authorized": False,
        },
        "explicit_config": {
            "kind": "NO_FINITE_BOUND_IN_PINNED_ENGINE_SCHEMA",
            "complete_by_pinned_source": False,
        },
        "preserved_env_info": {
            "kind": "EXTERNAL_PROVENANCE_NO_ENGINE_BOUND",
            "complete_by_pinned_source": False,
        },
        "offline_evaluator": {
            "kind": "CALLER_SUPPLIED_EXACT_SEED_THEN_SCRUBBED",
            "agent_seed_visibility": False,
            "finite_domain_requires_external_panel_provenance": True,
            "byte_binding_alone_proves_precommit": False,
        },
        "global_identifiability_proved": False,
        "production_seed_cracker_authorized": False,
    }


def _plain_seed(value: Any, label: str = "seed") -> int:
    if type(value) is not int:
        raise ProvenanceError(f"{label} must be a plain integer")
    return value


def validate_seed_set(values: Sequence[int], *, label: str = "seed set") -> tuple[int, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ProvenanceError(f"{label} must be a non-empty list/tuple")
    out = tuple(_plain_seed(value, f"{label}[{index}]") for index, value in enumerate(values))
    if len(set(out)) != len(out):
        raise ProvenanceError(f"{label} must contain unique seeds")
    return out


def _sha256_hex(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise ProvenanceError(f"{label} must be a lowercase 64-hex SHA-256")
    if value.lower() != value:
        raise ProvenanceError(f"{label} must be a lowercase 64-hex SHA-256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ProvenanceError(f"{label} must be a lowercase 64-hex SHA-256") from exc
    return value


def bind_panel_manifest(path: Path, expected_sha256: str) -> dict:
    """Bind a declared offline seed panel by complete bytes; this proves immutability only."""
    expected = _sha256_hex(expected_sha256, "expected manifest SHA-256")
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ProvenanceError(f"panel manifest SHA-256 mismatch: expected {expected}, got {actual}")
    obj = _strict_json(raw, "panel manifest")
    required = {"schema", "seeds", "evaluator_git_blob", "engine_git_blob", "seedstream_git_blob"}
    if type(obj) is not dict or set(obj) != required:
        raise ProvenanceError("panel manifest must contain exactly the five seed-domain fields")
    if obj["schema"] != "titan.v4.byte-bound-offline-seed-panel/v1":
        raise ProvenanceError("unsupported panel manifest schema")
    if obj["evaluator_git_blob"] != EVALUATOR_GIT_BLOB:
        raise ProvenanceError("panel evaluator blob does not match pinned offline evaluator")
    if obj["engine_git_blob"] != ENGINE_GIT_BLOB:
        raise ProvenanceError("panel engine blob does not match pinned engine")
    if obj["seedstream_git_blob"] != SEEDSTREAM_GIT_BLOB:
        raise ProvenanceError("panel SEEDSTREAM blob does not match merged authority")
    seeds = validate_seed_set(obj["seeds"], label="panel seeds")
    return {
        "manifest_sha256": actual,
        "seeds": seeds,
        "seed_count": len(seeds),
        "domain_kind": "BYTE_BOUND_DECLARED_OFFLINE_PANEL_SET_ONLY",
        "panel_precommit_proved": False,
        "panel_origin_authenticated": False,
        "finite_domain_authority_proved": False,
        "hosted_seed_domain_proved": False,
        "global_identifiability_proved": False,
    }


def _load_seedstream(path: Path):
    raw, _ = _read_bound(Path(path), SEEDSTREAM_GIT_BLOB, "merged SEEDSTREAM")
    module = types.ModuleType("titan_v4_seedstream_bound")
    module.__file__ = str(path)
    try:
        code = compile(raw, str(path), "exec")
        exec(code, module.__dict__)
    except Exception as exc:
        raise ProvenanceError(f"cannot execute captured SEEDSTREAM bytes: {exc}") from exc
    return module


def _history_rows(seedstream, history: Sequence[dict]) -> list[dict]:
    if not isinstance(history, (list, tuple)) or not history:
        raise ProvenanceError("history must be a non-empty list/tuple")
    try:
        rows = [seedstream.normalize_evidence(row) for row in history]
    except Exception as exc:
        raise ProvenanceError(f"SEEDSTREAM evidence rejected: {exc}") from exc
    for left, right in zip(rows, rows[1:]):
        if right["day"] != left["day"] + 1:
            raise ProvenanceError("history days must be contiguous")
        if left["shops_after"] != right["shops_before"]:
            raise ProvenanceError("public shop history must join exactly")
    return rows


def filter_byte_bound_panel(
    history: Sequence[dict],
    manifest_path: Path,
    expected_manifest_sha256: str,
    *,
    seedstream_path: Path = DEFAULT_SEEDSTREAM,
    weed_chance: float = 0.005,
) -> dict:
    """Re-bind manifest bytes, then filter only that exact finite panel set."""
    panel = bind_panel_manifest(Path(manifest_path), expected_manifest_sha256)
    seeds = panel["seeds"]
    seedstream = _load_seedstream(Path(seedstream_path))
    rows = _history_rows(seedstream, history)
    survivors = list(seeds)
    counts = []
    for row in rows:
        observed = (row["weed_bits"], row["appended_shop"])
        try:
            survivors = [seed for seed in survivors if seedstream.signature(seed, row, weed_chance=weed_chance) == observed]
        except Exception as exc:
            raise ProvenanceError(f"SEEDSTREAM signature evaluation failed: {exc}") from exc
        counts.append({"day": row["day"], "candidate_count": len(survivors), "candidates": list(survivors)})
        if not survivors:
            break
    verdict = (
        "NO_MATCH_IN_DECLARED_PANEL_SET" if not survivors
        else "DECLARED_PANEL_SET_UNIQUE_NOT_GLOBAL" if len(survivors) == 1
        else "AMBIGUOUS_IN_DECLARED_PANEL_SET"
    )
    return {
        "manifest_sha256": panel["manifest_sha256"],
        "panel_seed_count": len(seeds),
        "survivor_counts": counts,
        "candidates": survivors,
        "candidate_count": len(survivors),
        "verdict": verdict,
        "authority": "BYTE_BOUND_DECLARED_OFFLINE_PANEL_SET_ONLY",
        "panel_precommit_proved": False,
        "panel_origin_authenticated": False,
        "finite_domain_authority_proved": False,
        "hosted_seed_domain_proved": False,
        "global_identifiability_proved": False,
        "production_seed_cracker_authorized": False,
    }


def consensus_forecast_for_panel(
    history: Sequence[dict],
    manifest_path: Path,
    expected_manifest_sha256: str,
    *,
    day: int,
    empty_counts,
    shops_before,
    seedstream_path: Path = DEFAULT_SEEDSTREAM,
    weed_chance: float = 0.005,
) -> dict:
    filtered = filter_byte_bound_panel(
        history, manifest_path, expected_manifest_sha256,
        seedstream_path=seedstream_path, weed_chance=weed_chance,
    )
    candidates = validate_seed_set(filtered.get("candidates"), label="surviving panel seeds")
    seedstream = _load_seedstream(Path(seedstream_path))
    try:
        forecast = seedstream.consensus_forecast(
            candidates,
            day=day,
            empty_counts=empty_counts,
            shops_before=shops_before,
            weed_chance=weed_chance,
        )
    except Exception as exc:
        raise ProvenanceError(f"SEEDSTREAM consensus rejected: {exc}") from exc
    forecast = dict(forecast)
    forecast.update(
        authority="BYTE_BOUND_DECLARED_OFFLINE_PANEL_CONSENSUS_ONLY",
        manifest_sha256=filtered["manifest_sha256"],
        panel_precommit_proved=False,
        panel_origin_authenticated=False,
        finite_domain_authority_proved=False,
        hosted_seed_domain_proved=False,
        global_identifiability_proved=False,
        production_seed_cracker_authorized=False,
    )
    return forecast


def write_manifest(path: Path, seeds: Iterable[int]) -> str:
    """Developer fixture convenience only; does not create panel provenance authority."""
    values = validate_seed_set(list(seeds), label="panel seeds")
    payload = {
        "schema": "titan.v4.byte-bound-offline-seed-panel/v1",
        "seeds": list(values),
        "evaluator_git_blob": EVALUATOR_GIT_BLOB,
        "engine_git_blob": ENGINE_GIT_BLOB,
        "seedstream_git_blob": SEEDSTREAM_GIT_BLOB,
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    Path(path).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--utils", type=Path, default=DEFAULT_UTILS)
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--engine-config", type=Path, default=DEFAULT_ENGINE_CONFIG)
    parser.add_argument("--evaluator", type=Path, default=DEFAULT_EVALUATOR)
    parser.add_argument("--seedstream", type=Path, default=DEFAULT_SEEDSTREAM)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    report = authenticate_source_contract(
        utils_path=args.utils,
        engine_path=args.engine,
        engine_config_path=args.engine_config,
        evaluator_path=args.evaluator,
        seedstream_path=args.seedstream,
    )
    if args.manifest is not None:
        if args.manifest_sha256 is None:
            raise ProvenanceError("--manifest requires --manifest-sha256")
        report["panel"] = bind_panel_manifest(args.manifest, args.manifest_sha256)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
