#!/usr/bin/env python3
"""Recompute all published claims without running any game."""
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


stage4 = load("results/stage-4.json.gz")
stage12 = load("results/stage-12.json.gz")
games = stage4["games"] + stage12["games"]
assert [g["seed"] for g in stage4["games"]][::2] == list(range(9922013, 9922017))
assert [g["seed"] for g in stage12["games"]][::2] == list(range(9922017, 9922029))
assert all(g["status"] == "complete" and g["failure"] is None for g in games)
assert all(g["steps"] == 719 for g in games)
margins = [g["scores"][g["candidate_seat"]] - g["scores"][1-g["candidate_seat"]] for g in games]
assert (sum(m > 0 for m in margins), sum(m == 0 for m in margins), sum(m < 0 for m in margins)) == (27, 4, 1)
assert (sum(m > 0 for m in margins) + .5 * sum(m == 0 for m in margins)) / 32 == .90625
assert sum(margins) == 6740 and sorted(margins)[15:17] == [240, 240]
assert sum(g["scores"][g["candidate_seat"]] for g in games) == 2713097
assert sum(g["scores"][1-g["candidate_seat"]] for g in games) == 2706357
assert max(g["actors"][g["candidate_seat"]]["max_call_seconds"] for g in games) == 0.5230610849976074
assert max(g["actors"][g["candidate_seat"]]["max_rpc_seconds"] for g in games) == 0.5795723509945674
assert max(a["peak_rss_kib"] for g in games for a in g["actors"]) == 24428

loss = next(g for g in games if g["seed"] == 9922023 and g["candidate_seat"] == 1)
assert loss["scores"] == [56495.0, 56109.0]
assert loss["trace_sha256"] == "3d68450e97a956e3b258af71ded86ca66d46bbf0bac9af0877c0a040c886c5e3"
trace = json.loads(gzip.decompress((HERE / "results/loss-9922023-seat1-trace.json.gz").read_bytes()))
assert trace["scores"] == loss["scores"] and trace["trace_sha256"] == loss["trace_sha256"]
assert len(trace["trace"]) == 719

selfplay = load("results/diagnostic-frozen-self-9922023.json")
assert [g["scores"] for g in selfplay["games"]] == [[56495.0, 55859.0], [56495.0, 55859.0]]
paired_win = next(g for g in games if g["seed"] == 9922023 and g["candidate_seat"] == 0)
assert paired_win["scores"] == [56735.0, 55859.0]

for name, quantity in (("funding-entry-probe.json", 2), ("loss-9922023-seat1-funding-probe.json", 1)):
    probe = load("results/" + name)
    reached = probe["reached"]
    assert reached["hook_calls_this_entry"] == probe["total_hook_calls_before_stop"] == 1
    before, after = reached["selected"]["market"], reached["returned"]["market"]
    assert before[2] == ["BUY_SEED", "WHEAT", 17]
    assert after[2] == ["BUY_SEED", "WHEAT", quantity]
    assert before[3:] == after[3:] == [["HIRE"]] * 7
    assert reached["diagnostics"]["parent_calls"] == 1
    assert reached["diagnostics"]["seed_funding"]["rival_private_used"] is False

source = load("source/canonical-SOURCE.json")
config_path = HERE / "source/TITAN-CONFIG.json"
assert source["official_engine"]["commit"] == stage4["engine_ref"]
assert hashlib.sha256(config_path.read_bytes()).hexdigest() == "a186bec191d4e11908ffd805e86203e16f3ee30804c61887afd629af2e72470f"
assert json.loads(config_path.read_text()) == source["default"]
assert stage4["candidate"]["sha256"] == stage12["candidate"]["sha256"] == "d9a830bd42b19cc2a1c2b644fff064307de039cb058000c2d6aece7d5389f818"
assert stage4["opponents"]["frozen_sell"]["sha256"] == stage12["opponents"]["frozen_sell"]["sha256"] == "ecab25dcc87805f77eb1772acb53e7fb985150c7a6988cdb77ffcb7faf59f51b"
print("verified: 32 panel games, 27/4/1, exact loss replay, self-play attribution, and two one-call funding probes")
