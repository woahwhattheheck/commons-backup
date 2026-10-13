# TITAN V3 funding-town unlock boundary review

This additive review packet targets draft PR **#12053**, exact review head
`b42e4a0fd2074f3e6002a23a328fbf3e351b278e`, and the pinned official
Kaggriculture engine Git blob
`3c202c7ee921da239356789e266b694635103fc4`.

## Finding

The official interpreter runs `_end_of_day()` after the final town stage of a
day. On each configured unlock day it appends a seed-determined shop to the
public town. That new instance participates in later `_town_consume()` calls.
Therefore a funding trace that replays future town ticks from only the current
`town["unlocked_shops"]` snapshot is not closed when its protected horizon can
cross an unlock boundary.

`town_unlock_witness.py` supplies a strict, deterministic counterexample using
the pinned official engine constants and formulas:

- current step 60, no shops, WHEAT inventory 9999, cash $26;
- end of step 71 advances day 2 -> 3 and seed 0 draws `BAKERY`;
- step 72 BAKERY consumes one WHEAT; center interval is configured to 1000;
- step 73 `BUY_PRODUCT WHEAT 1` quotes post-buy inventory;
- static-current-town projection quotes $26 and says the buy fills;
- official dynamic-town projection quotes $27 and the buy fails;
- retaining one current product sale changes the exact required minimum from 0
  to 1.

The fixture uses a one-cell, fully occupied board for both players, so the
engine's weed loop performs no random draws before the shop choice. It also
includes controls for a horizon ending before the boundary, a non-unlock day,
and the maximum-shop-instance cap.

## Reproduce

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX=/tmp/titan-v3-town-unlock-pycache
python -B town_unlock_witness.py --out /tmp/WITNESS.json > /tmp/stdout.json
cmp /tmp/stdout.json /tmp/WITNESS.json
cmp /tmp/WITNESS.json WITNESS.json
python -m py_compile town_unlock_witness.py
```

Expected canonical receipt digest:

```text
eb2de6a727920116a955f97a4497a98007fe936a2f4e33b0d00122f5c6370691
```

## Review disposition

**HOLD pending one of these closures:** prove every protected horizon ends
before the next unresolved shop unlock; model exact end-of-day RNG and shop
state; or apply a conservative possible-shop product stress. This packet does
not claim the exact PR implementation has the defect until its patch bytes are
read back; it proves the missing proof obligation.

No TITAN source, config, archive, pointer, game, provider, Kaggle, submission,
merge, or promotion state was changed.
