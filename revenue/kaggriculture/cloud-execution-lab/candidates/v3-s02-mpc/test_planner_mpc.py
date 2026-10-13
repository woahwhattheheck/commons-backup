# SPDX-License-Identifier: Apache-2.0
"""Unit tests for candidate generation and disable flag. No engine required."""
import os
import planner_mpc as p


def test_generate_candidates_includes_canonical_and_hire():
    obs = {"player": 0, "farms": [{"farmer": [0, 0], "tiles": [[None]], "hands": []}]}
    cfg = {"maxMarketOrdersPerTurn": 10}
    can = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"], ["SELL", "WHEAT", 4]]}
    cands = p.generate_candidates(can, obs, cfg, limit=8)
    assert cands[0] == can
    assert 1 <= len(cands) <= 8
    assert any(sum(1 for o in c.get("market") or [] if o and o[0] == "HIRE") == 2 for c in cands)


def test_disable_flag_returns_canonical(monkeypatch):
    monkeypatch.setenv("TITAN_MPC", "0")
    seen = {}
    def canon(obs, cfg=None):
        seen["n"] = seen.get("n", 0) + 1
        return {"farmer": ["PASS"], "hands": [], "market": []}
    pl = p.Planner(canon, horizon=6, budget_s=0.1)
    out = pl.act({"player": 0, "step": 1, "farms": [{"farmer": [0, 0], "tiles": [[None]], "hands": []}], "market": {}, "town": {}, "private": {}}, {})
    assert out["farmer"] == ["PASS"]
    assert seen["n"] == 1
