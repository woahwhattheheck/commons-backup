from copy import deepcopy

from mirror_sell_queue import (
    ASSIGNMENT_SCHEMA,
    ENGINE_GIT_BLOB,
    FEATURE,
    REPORT_SCHEMA,
    MirrorSellQueue,
)


def _obs():
    return {"market": {"inventory": {"WOOL": 10025, "MELON": 10025, "EGG": 10025}, "params": {}}}


def _action():
    return {
        "farmer": ["PASS"],
        "hands": [["PASS"]],
        "market": [["SELL", "WOOL", 30], ["SELL", "MELON", 60], ["HIRE"], ["SELL", "EGG", 4]],
        "tag": {"keep": True},
    }


def _report(permutation=(1, 0), edge=3012, certified=True, reason="ok"):
    return {
        "schema": REPORT_SCHEMA,
        "engine_git_blob": ENGINE_GIT_BLOB,
        "mirror_assignment": {
            "schema": ASSIGNMENT_SCHEMA,
            "certified": certified,
            "reason": reason,
            "optimal_permutation_indices": list(permutation),
            "predicted_mirror_edge": edge,
        },
    }


def _analyzer_factory(report, captured=None):
    def analyzer(rows, *, price_fn):
        if captured is not None:
            captured.append(deepcopy(rows))
        assert price_fn("WOOL", 10025) == 7
        return deepcopy(report)
    return analyzer


def _price(item, level, params=None):
    assert isinstance(item, str) and type(level) is int
    return 7


def test_feature_off_is_exact_identity_and_does_not_call_analyzer():
    action = _action()
    def explode(*args, **kwargs):
        raise AssertionError("disabled feature called analyzer")
    lane = MirrorSellQueue(price_fn=_price, analyzer=explode)
    out = lane.transform(_obs(), {}, action, post_unit_shed={"WOOL": 30, "MELON": 60})
    assert out == action and out is not action
    assert lane.diagnostics == {"status": "identity", "reason": "feature_off"}


def test_certified_assignment_only_permutes_leading_sell_block():
    action = _action()
    captured = []
    lane = MirrorSellQueue(price_fn=_price, analyzer=_analyzer_factory(_report(), captured))
    out = lane.transform(
        _obs(), {FEATURE: True}, action,
        post_unit_shed={"WOOL": 30, "MELON": 60, "EGG": 4},
    )
    assert out["market"] == [["SELL", "MELON", 60], ["SELL", "WOOL", 30], ["HIRE"], ["SELL", "EGG", 4]]
    assert out["farmer"] == action["farmer"] and out["hands"] == action["hands"]
    assert out["tag"] == action["tag"]
    assert action == _action()
    assert captured == [[
        {"item": "WOOL", "public_inventory": 10025, "fillable": 30},
        {"item": "MELON", "public_inventory": 10025, "fillable": 60},
    ]]
    assert lane.diagnostics["status"] == "applied"
    assert lane.diagnostics["predicted_mirror_edge"] == 3012


def test_engine_prefix_suffix_is_byte_preserved():
    action = _action()
    action["market"] = [["SELL", "WOOL", 30], ["SELL", "MELON", 60], {"suffix": "poison"}]
    lane = MirrorSellQueue(price_fn=_price, analyzer=_analyzer_factory(_report()))
    out = lane.transform(
        _obs(), {FEATURE: True, "maxMarketOrdersPerTurn": 2}, action,
        post_unit_shed={"WOOL": 30, "MELON": 60},
    )
    assert out["market"][:2] == [["SELL", "MELON", 60], ["SELL", "WOOL", 30]]
    assert out["market"][2] == {"suffix": "poison"}


def test_duplicate_product_is_identity_without_analyzer():
    action = _action()
    action["market"][:2] = [["SELL", "WOOL", 10], ["SELL", "WOOL", 20]]
    lane = MirrorSellQueue(price_fn=_price, analyzer=lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    out = lane.transform(_obs(), {FEATURE: True}, action, post_unit_shed={"WOOL": 30})
    assert out == action
    assert lane.diagnostics["reason"] == "duplicate_product_rows_outside_assignment_theorem"


def test_zero_fill_is_identity():
    lane = MirrorSellQueue(price_fn=_price, analyzer=lambda *a, **k: None)
    action = _action()
    out = lane.transform(
        _obs(), {FEATURE: True}, action,
        post_unit_shed={"WOOL": 0, "MELON": 60},
    )
    assert out == action
    assert lane.diagnostics["reason"] == "zero_fill_in_sell_block"


def test_non_sell_is_hard_barrier():
    action = _action()
    action["market"] = [["SELL", "WOOL", 30], ["HIRE"], ["SELL", "MELON", 60]]
    lane = MirrorSellQueue(price_fn=_price, analyzer=lambda *a, **k: None)
    out = lane.transform(
        _obs(), {FEATURE: True}, action,
        post_unit_shed={"WOOL": 30, "MELON": 60},
    )
    assert out == action
    assert lane.diagnostics["reason"] == "leading_sell_block_lt_2"


def test_uncertified_or_zero_edge_is_identity():
    action = _action()
    lane = MirrorSellQueue(price_fn=_price, analyzer=_analyzer_factory(_report(certified=False, reason="duplicate")))
    out = lane.transform(_obs(), {FEATURE: True}, action, post_unit_shed={"WOOL": 30, "MELON": 60})
    assert out == action and lane.diagnostics["reason"] == "duplicate"
    lane = MirrorSellQueue(price_fn=_price, analyzer=_analyzer_factory(_report(permutation=(0, 1), edge=0)))
    out = lane.transform(_obs(), {FEATURE: True}, action, post_unit_shed={"WOOL": 30, "MELON": 60})
    assert out == action and lane.diagnostics["reason"] == "no_positive_assignment_edge"


def test_bad_permutation_falls_back_to_explicit_fallback():
    action = _action()
    fallback = {"farmer": ["PASS"], "hands": [], "market": []}
    lane = MirrorSellQueue(price_fn=_price, analyzer=_analyzer_factory(_report(permutation=(0, 0))))
    out = lane.transform(
        _obs(), {FEATURE: True}, action,
        post_unit_shed={"WOOL": 30, "MELON": 60}, fallback_action=fallback,
    )
    assert out == fallback and out is not fallback
    assert "complete SELL-block permutation" in lane.diagnostics["reason"]


def test_bool_counts_fail_closed():
    action = _action()
    action["market"][0][2] = True
    lane = MirrorSellQueue(price_fn=_price, analyzer=lambda *a, **k: None)
    out = lane.transform(_obs(), {FEATURE: True}, action, post_unit_shed={"WOOL": 30, "MELON": 60})
    assert out == action
    action = _action()
    obs = _obs(); obs["market"]["inventory"]["WOOL"] = True
    out = lane.transform(obs, {FEATURE: True}, action, post_unit_shed={"WOOL": 30, "MELON": 60})
    assert out == action
    assert "plain nonnegative int" in lane.diagnostics["reason"]


def test_price_typeerror_fails_closed_without_abi_retry():
    action = _action()
    calls = []
    def bad_price(*args):
        calls.append(args)
        raise TypeError("poisoned market params")
    lane = MirrorSellQueue(price_fn=bad_price, analyzer=_analyzer_factory(_report()))
    fallback = {"farmer": ["PASS"], "hands": [], "market": []}
    out = lane.transform(
        _obs(), {FEATURE: True}, action,
        post_unit_shed={"WOOL": 30, "MELON": 60}, fallback_action=fallback,
    )
    assert out == fallback
    assert len(calls) == 1 and len(calls[0]) == 3
    assert "poisoned market params" in lane.diagnostics["reason"]
