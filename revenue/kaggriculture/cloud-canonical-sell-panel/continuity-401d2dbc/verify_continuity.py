#!/usr/bin/env python3
"""Offline verification of the bounded continuity evidence."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(relative):
    path = HERE / relative
    data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return json.loads(data)


summary = load("results/continuity-summary.json")
ancestor = load("results/ancestor-9922023.json")
current = [load("results/current-9922023-seat0.json.gz"),
           load("results/current-9922023-seat1.json.gz")]
funding = load("results/current-funding-9922023-seat1.json")
receipt = load("source/CURRENT-ARCHIVE.json")
source = load("source/CURRENT-SOURCE.json")
config_path = HERE / "source/TITAN-CONFIG.json"
config = json.loads(config_path.read_text())

assert receipt["sha256"] == summary["current"]["archive_sha256"] == "401d2dbcaf2a089386a145bd0237b79070dfda730d4cf582ad814a59a778a86d"
assert receipt["bytes"] == 275290 and receipt["runtime_files"] == 71
assert hashlib.sha256((HERE / "source/CURRENT-SOURCE.json").read_bytes()).hexdigest() == "051a5eddac522986c5b43f972b1597ef96415c9669f65b17c66c172844c50ca1"
assert hashlib.sha256(config_path.read_bytes()).hexdigest() == "97c68a011f947de06dc2124773c9d224fbb63b2f92bd1e4f8d8e5466925db8da"
assert source["default"] == config
assert config["funding"] is True and config["terminal_history"] is False and config["terminal_route"] is False

for now, old, claimed in zip(current, ancestor["rows"], summary["games"]):
    assert now["steps"] == old["steps"] == 719
    assert now["scores"] == old["scores"] == claimed["scores"]
    assert now["trace_sha256"] == old["trace_sha256"] == claimed["trace_sha256"]
    assert max(step["calls"][now["candidate_seat"]]["rpc_seconds"] for step in now["trace"]) < 1.0

assert summary["divergence"]["full_trace_hash_mismatches"] == 0
assert summary["divergence"]["terminal_score_mismatches"] == 0
assert summary["divergence"]["seat1_direct_action_round_diffs"] == 0
assert summary["divergence"]["seat1_direct_bank_transition_diffs"] == 0
assert summary["external_failures_or_timeouts"] == 0

reached = funding["reached"]
assert funding["total_hook_calls_before_stop"] == reached["hook_calls_this_entry"] == 1
assert reached["step"] == 600 and reached["selected"]["market"][2] == ["BUY_SEED", "WHEAT", 17]
assert reached["returned"]["market"][2] == ["BUY_SEED", "WHEAT", 1]
assert reached["selected"]["market"][3:] == reached["returned"]["market"][3:] == [["HIRE"]] * 7
assert reached["diagnostics"]["parent_calls"] == 1
assert reached["diagnostics"]["seed_funding"]["paired_current_market_cash_delta"] == 160
assert reached["diagnostics"]["seed_funding"]["rival_private_used"] is False
print("verified: current archive/source/config parity, two exact trace continuities, timing boundary, and one reached funding call")
