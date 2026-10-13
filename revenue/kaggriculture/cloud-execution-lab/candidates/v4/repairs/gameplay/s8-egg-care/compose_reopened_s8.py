# SPDX-License-Identifier: Apache-2.0
"""Materialize the reopened S8 helper from its exact preserved donor, not R04.

No runtime/default/config is modified. The generated helper is standalone and
retains KEY=r04_s8_egg_care and enabled=False. A native composer must invoke it
before returned-action receipts, after existing HARVEST rescue, within deadline.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

DONOR_BLOB = "30a0e05c0cd7a435a59316d9d070da59eb2bb865"
MODES = ("donor", "spread", "discard", "spread_or_discard")

ADDITION = '''
# Reopened S8 economics. Quotes are a screening heuristic, not a future-sale
# guarantee. Discard certification proves only zero lost first-EOD fertilizer.
_PRICE_MODES = ("donor", "spread", "discard", "spread_or_discard")
_SHED_NEUTRAL_UNITS = frozenset(("PASS", "NORTH", "SOUTH", "EAST", "WEST",
    "CARE", "COLLECT_FERTILIZER", "HARVEST", "FEED", "WATER", "FERTILIZE",
    "DIG", "BUILD_COOP", "BUILD_PASTURE"))


def discarded_fertilizer(observation, action, configuration=None):
    """Conservatively prove shed remains full before every EOD inventory drop.

    All unit rows must be shed-neutral. Subtract *all requested* SELL units in
    the raw executable prefix, even unfillable ones. BUY/HIRE/land cannot lower
    occupancy. Thus this lower bound is independent of rival fills/prices,
    incoming inventory item order and same-turn purchases. Never compact rows.
    Unknown/malformed live rows fail closed; unreachable suffixes are irrelevant.
    """
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return False
    private = observation.get("private")
    if not isinstance(private, dict) or not isinstance(private.get("shed"), dict):
        return False
    shed = private["shed"]
    if any(type(n) is not int or n < 0 for n in shed.values()):
        return False
    capacity = _cfg(configuration, "shedCapacity", 100)
    limit = _cfg(configuration, "maxMarketOrdersPerTurn", 10)
    if type(capacity) is not int or capacity <= 0 or type(limit) is not int or limit <= 0:
        return False
    rows = _rows(action)
    if rows is None or any(len(row) != 1 or not isinstance(row[0], str)
                           or row[0] not in _SHED_NEUTRAL_UNITS for row in rows):
        return False
    market = action.get("market", [])
    if not isinstance(market, list):
        return False
    lower_bound = sum(shed.values())
    for row in market[:limit]:
        if not isinstance(row, list):
            return False
        if not row or row == ["PASS"]:
            continue
        if row in (["HIRE"], ["BUY_LAND"]):
            continue
        if (len(row) != 3 or row[0] not in ("SELL", "BUY_PRODUCT", "BUY_ANIMAL", "BUY_SEED")
                or not isinstance(row[1], str) or type(row[2]) is not int or row[2] < 0):
            return False
        if row[0] == "SELL":
            lower_bound -= row[2]
    return lower_bound >= capacity


def _reopened_economics(observation, action, configuration, mode, fert_stock):
    if mode not in _PRICE_MODES:
        raise ValueError("unknown S8 price_mode: " + repr(mode))
    strong, egg, fertilizer = _price_guard(observation)
    if egg <= 0 or fertilizer <= 0:
        return False, egg, fertilizer, "invalid_price"
    # This proof does not need an arbitrary four-unit buffer: the original
    # collection could not replenish the shed in the certified execution.
    if mode in ("discard", "spread_or_discard") and discarded_fertilizer(observation, action, configuration):
        return True, egg, fertilizer, "discard"
    if type(fert_stock) is not int or fert_stock < MIN_FERTILIZER_BUFFER:
        return False, egg, fertilizer, "fertilizer_buffer"
    allowed = strong if mode == "donor" else egg > fertilizer
    return (mode != "discard" and allowed), egg, fertilizer, "spread" if mode != "donor" else "donor"

'''


def compose(data: bytes) -> bytes:
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != DONOR_BLOB:
        raise ValueError(f"S8 donor mismatch: expected {DONOR_BLOB}, got {actual}")
    text = data.decode("utf-8")
    start = text.index('"""')
    stop = text.index('"""', start + 3) + 3
    text = text[:start] + '\"\"\"Reopened S8: optional fed-GOOSE care for a positive quoted spread or a\ncertified discarded fertilizer collection. Disabled by default. This helper\nchanges only eligible hour-23 COLLECT_FERTILIZER rows; original HARVEST, capacity,\nfeeding, pending-bonus, timing and actor-collision guards remain binding.\n\nThe spread mode is a screening heuristic, not future-profit proof. Discard mode\nproves no lost first-EOD fertilizer only: feed, future harvest, storage, sale and\nwhole-stack effects still require realized economic gates. Invoke BEFORE native\nreturned-action receipts, AFTER harvest rescue; do not add a post-return wrapper.\"\"\"' + text[stop:]
    old = '    enabled: bool = False,\n'
    text = text.replace(old, old + '    price_mode: str = "spread_or_discard",\n', 1)
    old = '''    profitable, egg_price, fertilizer_price = _price_guard(observation)
    if not profitable:
        telemetry["price_block"] += 1
        return action

'''
    if text.count(old) != 1:
        raise ValueError("S8 price anchor drift")
    text = text.replace(old, '', 1)
    old = '''    if type(fert_stock) is not int or fert_stock < MIN_FERTILIZER_BUFFER:
        telemetry["fertilizer_buffer_block"] += 1
        return action
'''
    text = text.replace(old, '''    if type(fert_stock) is not int or fert_stock < 0:
        return action
''', 1)
    anchor = '    result = copy.deepcopy(action)\n'
    insert = '''    telemetry["structural_opportunities"] += len(candidates)
    profitable, egg_price, fertilizer_price, reason = _reopened_economics(
        observation, action, configuration, price_mode, fert_stock)
    if not profitable:
        telemetry[reason + "_block"] += len(candidates)
        return action
    telemetry[reason + "_activations"] += len(candidates)

'''
    text = text.replace(anchor, insert + anchor, 1)
    text = text.replace('telemetry["fertilizer_units_foregone"] += 1',
                        'telemetry["fertilizer_units_foregone"] += int(reason != "discard")', 1)
    text = text.replace('def apply_egg_care(\n', ADDITION + '\ndef apply_egg_care(\n', 1)
    return text.encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", type=Path, default=Path(__file__).parent / "s8_egg_care.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = compose(args.donor.read_bytes())
    # No accidental production replacement or half-written composition.
    with args.output.open("xb") as stream:
        stream.write(output)
    print(hashlib.sha256(output).hexdigest())


if __name__ == "__main__":
    main()
