# SPDX-License-Identifier: Apache-2.0
"""Synthetic dependency probe, NOT a copy of or replacement for the callback.

Both mechanics calls were read in funded_payback.py blob
5acb8ddff8d27106d9500d8357e78b4ca662f4f1, PR10487 head
ddbd5c56e3ebb7cee578476bd81eaed0ac3177cc (first 240 source lines).
Use --alias mechanics. This probe deliberately reproduces the missing-API
contract of that proposal; it makes no claim about later callback revisions.
"""

def required_payback_api(mechanics, order, market):
    parsed = mechanics._parse_order(order)
    mechanics._refresh_prices(market)
    return parsed
