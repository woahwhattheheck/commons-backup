# SPDX-License-Identifier: Apache-2.0
"""Lossless clone for plain R04 tape actions, with deepcopy fallback.

Recovered from the unused V3.1 #12414 / #12431 fast-clone proof. The V4
caller owns the default-OFF switch; this helper does not alter game policy.
Unlike the predecessor, repeated list identities and unusual key layouts
fall back so deepcopy's alias graph and dictionary order are preserved.
"""
import copy

_NONE_TYPE = type(None)
_KEYS = ("farmer", "hands", "market")


def is_fast_tape_action(template):
    """Accept only the canonical, alias-free shallow JSON action shape."""
    if type(template) is not dict or len(template) != 3:
        return False
    # Exact keys and insertion order matter to lossless clone semantics too.
    for actual, expected in zip(template, _KEYS):
        if type(actual) is not str or actual != expected:
            return False
    farmer, hands, market = (template[key] for key in _KEYS)
    if type(farmer) is not list or type(hands) is not list or type(market) is not list:
        return False
    seen = {id(farmer), id(hands), id(market)}
    if len(seen) != 3:
        return False
    for value in farmer:
        kind = type(value)
        if kind is not str and kind is not int and kind is not float and kind is not bool and kind is not _NONE_TYPE:
            return False
    for rows in (hands, market):
        for row in rows:
            if type(row) is not list or id(row) in seen:
                return False
            seen.add(id(row))
            for value in row:
                kind = type(value)
                if kind is not str and kind is not int and kind is not float and kind is not bool and kind is not _NONE_TYPE:
                    return False
    return True


def apply_fast_tape_clone(template):
    """Return a detached clone, retaining deepcopy on every unproved shape."""
    if not is_fast_tape_action(template):
        return copy.deepcopy(template)
    farmer_key, hands_key, market_key = template
    return {
        farmer_key: list(template[farmer_key]),
        hands_key: [list(row) for row in template[hands_key]],
        market_key: [list(row) for row in template[market_key]],
    }
