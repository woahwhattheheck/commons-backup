#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact-source repair carrier for E11's unusable terminal absorption tick.

This carrier is deliberately disconnected from canonical TITAN.  It accepts only
one authenticated one-tree source blob, changes exactly one call boundary, and
emits a deterministic receipt for the publisher/integrator.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

OPERATION = "TITAN-V3-E11-LAST-USABLE-ABSORPTION-20260910-01"
PACKET_FILE_ID = "F0C0JPCAAQP"
PACKET_SHA256 = "f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728"
SOURCE_RELATIVE_PATH = "revenue/kaggriculture/cloud-execution-lab/candidates/v3/overlay/e11_rival_sell.py"
SOURCE_SHA256 = "0871703888bfd128a9118c0fd59fa6c6a7b4ce509d22d803b97255622bff4816"
ENGINE_ARTIFACT_ID = 10005621438
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
ENGINE_CONFIG_SHA256 = "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867"

PREIMAGE = b"total, error = _future_absorption(item, step, last, shops, cfg, absorption_fn)"
POSTIMAGE = b"total, error = _future_absorption(item, step, last - 1, shops, cfg, absorption_fn)"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _compile_python(data: bytes, label: str) -> None:
    text = data.decode("utf-8")
    ast.parse(text, filename=label)
    compile(text, label, "exec")


def audit_engine(engine: bytes, engine_config: bytes) -> dict[str, Any]:
    """Bind the official ordering theorem used by this repair.

    On every interpreted step the market executes before town consumption.  The
    terminal reward is assigned after both, so consumption on the final market
    step cannot affect any later executable market order.
    """
    actual = sha256(engine)
    if actual != ENGINE_SHA256:
        raise ValueError(f"engine SHA-256 drift: expected {ENGINE_SHA256}, got {actual}")
    config_actual = sha256(engine_config)
    if config_actual != ENGINE_CONFIG_SHA256:
        raise ValueError(
            f"engine config SHA-256 drift: expected {ENGINE_CONFIG_SHA256}, got {config_actual}"
        )
    config = json.loads(engine_config.decode("utf-8"))
    if config.get("configuration", {}).get("episodeSteps") != 720:
        raise ValueError("official episodeSteps drift")
    text = engine.decode("utf-8")
    ast.parse(text, filename="kaggriculture.py")
    market = text.count("    _process_market(state, env)\n")
    town = text.count("    _town_consume(env, state, step)\n")
    terminal = text.count("    if step >= cfg.episodeSteps - 2:\n")
    if (market, town, terminal) != (1, 1, 1):
        raise ValueError(f"engine seam cardinality drift: market={market}, town={town}, terminal={terminal}")
    market_at = text.index("    _process_market(state, env)\n")
    town_at = text.index("    _town_consume(env, state, step)\n")
    terminal_at = text.index("    if step >= cfg.episodeSteps - 2:\n")
    if not market_at < town_at < terminal_at:
        raise ValueError("official interpreter ordering drift")
    if text.count('s.reward = float(obs0.farms[s.observation.player]["money"])') != 1:
        raise ValueError("terminal cash reward seam drift")
    return {
        "sha256": actual,
        "configuration_sha256": config_actual,
        "episode_steps": 720,
        "market_before_town": True,
        "town_before_terminal_cash": True,
        "final_town_tick_has_later_market": False,
    }


def repair_source(source: bytes) -> bytes:
    actual = sha256(source)
    if actual != SOURCE_SHA256:
        raise ValueError(f"source SHA-256 drift: expected {SOURCE_SHA256}, got {actual}")
    if source.count(PREIMAGE) != 1 or source.count(POSTIMAGE) != 0:
        raise ValueError("E11 terminal-boundary preimage cardinality drift")
    repaired = source.replace(PREIMAGE, POSTIMAGE, 1)
    if repaired.count(PREIMAGE) != 0 or repaired.count(POSTIMAGE) != 1:
        raise AssertionError("repair postcondition failed")
    _compile_python(repaired, "e11_rival_sell.repaired.py")
    return repaired


def build_receipt(source: bytes, repaired: bytes, engine: bytes, engine_config: bytes) -> dict[str, Any]:
    engine_receipt = audit_engine(engine, engine_config)
    return {
        "schema": "titan-v3-e11-last-usable-absorption/v1",
        "operation": OPERATION,
        "transport": {
            "slack_file_id": PACKET_FILE_ID,
            "packet_sha256": PACKET_SHA256,
            "source_relative_path": SOURCE_RELATIVE_PATH,
        },
        "input": {"bytes": len(source), "sha256": sha256(source)},
        "output": {"bytes": len(repaired), "sha256": sha256(repaired)},
        "engine": {"artifact_id": ENGINE_ARTIFACT_ID, "upstream_ref": ENGINE_REF, **engine_receipt},
        "change": {
            "call_boundary_before": "[step, final_market_step]",
            "call_boundary_after": "[step, final_market_step - 1]",
            "reason": "town consumption occurs after each market; the final-step tick has no later market",
            "preimage_count": source.count(PREIMAGE),
            "postimage_count": repaired.count(POSTIMAGE),
        },
        "authority": {
            "canonical_mutation": False,
            "feature_enablement": False,
            "gameplay_strength_claim": False,
            "kaggle_submission": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--engine-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.read_bytes()
    engine = args.engine.read_bytes()
    engine_config = args.engine_config.read_bytes()
    repaired = repair_source(source)
    receipt = build_receipt(source, repaired, engine, engine_config)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(repaired)
    args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
