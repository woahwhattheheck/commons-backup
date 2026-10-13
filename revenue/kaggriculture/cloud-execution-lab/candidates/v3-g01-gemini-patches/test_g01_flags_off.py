# SPDX-License-Identifier: Apache-2.0
import e11_rival_sell as e11
import rival_model as rm
import e20_hire_shop as e20

OBS = {
    "step": 10, "player": 0,
    "farms": [
        {"money": 2000, "unlocked_quadrants": ["NW"], "hires_today": 3,
         "tiles": [[{"kind": "PLANT", "crop": "WHEAT", "watered_today": False}]],
         "hands": []},
        {"money": 2000, "unlocked_quadrants": ["NW", "NE"], "tiles": [[]], "hands": []},
    ],
    "market": {"prices": {"WHEAT": 10}, "inventory": {"WHEAT": 50}},
    "town": {"unlocked_shops": ["BAKERY"]},
}
ACT = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 4], ["HIRE"]]}

def test_e11_off_identity(monkeypatch):
    monkeypatch.setenv("TITAN_E11_RIVAL_SELL", "0")
    out, rep = e11.apply_e11(OBS, ACT, [(2, {"WHEAT": 40})], {"episodeSteps": 720}, lambda *a: 2)
    assert out == ACT and rep["changed"] is False and rep["enabled"] is False

def test_o01_off_identity(monkeypatch):
    monkeypatch.setenv("TITAN_RIVAL_MODEL", "0")
    out, rep = rm.apply_rival_model(OBS, ACT, {"WHEAT": 40})
    assert out == ACT and rep["enabled"] is False

def test_e20_off_identity(monkeypatch):
    monkeypatch.setenv("TITAN_E20_HIRE_GUARD", "0")
    out, rep = e20.apply_hire_guard(OBS, ACT)
    assert out == ACT and rep["enabled"] is False

def test_e11_on_defers(monkeypatch):
    monkeypatch.setenv("TITAN_E11_RIVAL_SELL", "1")
    out, rep = e11.apply_e11(OBS, ACT, [(2, {"WHEAT": 40})], {"episodeSteps": 720, "rival_dump_price_drop": 15.0, "rival_dump_lookback_steps": 8}, lambda *a: 2)
    assert rep["changed"] is True and "RIVAL_DUMP_DEFER_WHEAT" in rep["reason"] and out["market"][0] == []

def test_e11_terminal(monkeypatch):
    monkeypatch.setenv("TITAN_E11_RIVAL_SELL", "1")
    out, rep = e11.apply_e11(dict(OBS, step=718), ACT, [(710, {"WHEAT": 40})], {"episodeSteps": 720}, lambda *a: 2)
    assert out == ACT and rep["reason"] == "NO_OP_TERMINAL_STEP"

def test_o01_expander(monkeypatch):
    monkeypatch.setenv("TITAN_RIVAL_MODEL", "1")
    out, rep = rm.apply_rival_model(OBS, ACT, None)
    assert rep["archetype"] == "EARLY_EXPANDER" and out["market"][0] == ["BUY_LAND"]

def test_o01_terminal(monkeypatch):
    monkeypatch.setenv("TITAN_RIVAL_MODEL", "1")
    out, rep = rm.apply_rival_model(dict(OBS, step=718), ACT, {"WHEAT": 40})
    assert out == ACT and rep["reason"] == "NO_EDIT_TERMINAL_STEP_718"

def test_e20_drops_hire(monkeypatch):
    monkeypatch.setenv("TITAN_E20_HIRE_GUARD", "1")
    out, rep = e20.apply_hire_guard(OBS, ACT)
    assert rep["changed"] is True and out["market"][1] == []
