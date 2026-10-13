# SPDX-License-Identifier: Apache-2.0
"""Focused contracts for the V5 close-game sale-risk selector."""
from copy import deepcopy

from close_game_sale_risk import transform


def quote(item, inventory, _params):
    if item == "MILK":
        return max(1, 100 - 5 * int(inventory))
    if item == "WOOL":
        return 60
    return 10


def observation(*, step=710, own=5100, rival=5000):
    return {
        "step": step,
        "player": 0,
        "farms": [{"money": own}, {"money": rival}],
        "market": {
            "prices": {"MILK": 100, "WOOL": 60},
            "inventory": {"MILK": 0, "WOOL": 0},
            "params": {},
        },
    }


def config(mode, **extra):
    cfg = {
        "episodeSteps": 720,
        "maxMarketOrdersPerTurn": 10,
        "shedCapacity": 10,
        "titanCloseGameWindow": 48,
        "titanCloseGameSaleRisk": mode,
    }
    cfg.update(extra)
    return cfg


def action(first="MILK", second="WOOL"):
    return {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["SELL", first, 2], ["SELL", second, 2]],
    }


def check(name, condition):
    if not condition:
        raise AssertionError(name)


def main():
    base = action("WOOL", "MILK")

    # Missing opt-in is exact identity and caller isolation is preserved.
    original = deepcopy(base)
    out = transform(base, observation(), config("legacy"), quote=quote)
    check("legacy identity", out == original)
    check("caller untouched", base == original and out is not base)

    # cash_max prioritizes exact current receipts: MILK=195 > WOOL=120.
    out = transform(base, observation(), config("cash_max"), quote=quote)
    check("cash max engages", out["market"][:2] == [["SELL", "MILK", 2], ["SELL", "WOOL", 2]])

    # Fragile public lead: shed-cap stress is $1000.  Under ten rival units,
    # MILK falls to $95 for the lot while WOOL remains $120, so conservative
    # ordering protects the robust cash row first.
    fragile = action("MILK", "WOOL")
    out = transform(fragile, observation(own=5100, rival=5000),
                    config("ahead_conservative"), quote=quote)
    check("fragile lead stressed order",
          out["market"][:2] == [["SELL", "WOOL", 2], ["SELL", "MILK", 2]])

    # A lead above the deliberately coarse rival liquidation bound is secure;
    # conservative mode collapses back to immediate cash ordering.
    out = transform(base, observation(own=7001, rival=5000),
                    config("ahead_conservative"), quote=quote)
    check("secure lead cash order",
          out["market"][:2] == [["SELL", "MILK", 2], ["SELL", "WOOL", 2]])

    # Behind but within the same liquidation bound, exposed MILK receives the
    # aggressive front-run premium and moves ahead of stable WOOL.
    out = transform(base, observation(own=4900, rival=5000),
                    config("behind_aggressive"), quote=quote)
    check("behind aggressive engages",
          out["market"][:2] == [["SELL", "MILK", 2], ["SELL", "WOOL", 2]])

    # Explicit sign-mismatched policies fail closed rather than silently acting.
    out = transform(base, observation(own=4900, rival=5000),
                    config("ahead_conservative"), quote=quote)
    check("ahead mode while behind identity", out == base)
    out = transform(base, observation(own=5100, rival=5000),
                    config("behind_aggressive"), quote=quote)
    check("behind mode while ahead identity", out == base)

    # Adaptive selects the same public-gap branch without hidden-state guesses.
    out = transform(fragile, observation(own=5100, rival=5000),
                    config("adaptive"), quote=quote)
    check("adaptive ahead",
          out["market"][:2] == [["SELL", "WOOL", 2], ["SELL", "MILK", 2]])
    out = transform(base, observation(own=4900, rival=5000),
                    config("adaptive"), quote=quote)
    check("adaptive behind",
          out["market"][:2] == [["SELL", "MILK", 2], ["SELL", "WOOL", 2]])

    # Outside the close window is identity.
    out = transform(base, observation(step=600), config("cash_max"), quote=quote)
    check("outside window identity", out == base)

    # Economic barriers split blocks; nothing crosses BUY/HIRE/input rows.
    barrier = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [
            ["SELL", "WOOL", 2],
            ["BUY_SEED", "CARROT", 1],
            ["SELL", "MILK", 2],
        ],
    }
    out = transform(barrier, observation(), config("cash_max"), quote=quote)
    check("barrier topology", out == barrier)

    # The pinned engine accepts SELL rows with trailing fields and positive
    # int()-coercible quantities.  The close-game objective must classify the
    # same executable rows while preserving the inherited row bytes exactly.
    metadata = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [
            ["SELL", "WOOL", "2", {"tag": "wool"}],
            ["SELL", "MILK", 2.9, "milk-tail"],
        ],
    }
    metadata_original = deepcopy(metadata)
    out = transform(metadata, observation(), config("cash_max"), quote=quote)
    check("engine grammar trailing/coercible reorder",
          out["market"] == [metadata_original["market"][1], metadata_original["market"][0]])
    check("engine grammar raw rows preserved",
          out["market"][0][2:] == [2.9, "milk-tail"]
          and out["market"][1][2:] == ["2", {"tag": "wool"}]
          and metadata == metadata_original)

    # bool and fractional quantities are also int()-coercible in the pinned
    # parser.  Classification follows that parser; no normalization is written.
    coercible = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["SELL", "WOOL", True], ["SELL", "MILK", 1.9]],
    }
    coercible_original = deepcopy(coercible)
    out = transform(coercible, observation(), config("cash_max"), quote=quote)
    check("engine grammar bool/float coercion",
          out["market"] == [coercible_original["market"][1], coercible_original["market"][0]])

    # Engine-inert/nonpositive rows and the deliberate bounded-scoring ceiling
    # remain hard barriers: convergence must not broaden those policy semantics.
    for blocker in (
        ["SELL", "WOOL", "0", "tail"],
        ["SELL", "WOOL", -1],
        ["SELL", "WOOL", "not-an-int"],
        ["SELL", "WOOL", 257],
    ):
        blocked = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "WOOL", 2], blocker, ["SELL", "MILK", 2]],
        }
        check("nonpositive/malformed/bounded barrier",
              transform(blocked, observation(), config("cash_max"), quote=quote) == blocked)

    # Row quantities and multiset are invariant whenever a reorder engages.
    before = sorted(map(tuple, base["market"]))
    after = transform(base, observation(), config("cash_max"), quote=quote)
    check("quantity multiset", sorted(map(tuple, after["market"])) == before)

    print("close-game-sale-risk: PASS")


if __name__ == "__main__":
    main()
