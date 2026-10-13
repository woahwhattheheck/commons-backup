# V5-23 market-inventory underflow

This package executes V5 seed #23 against the pinned official Kaggriculture
engine (git blob `3c202c7e...`, SHA-256 `bc8a5487...`). The integer-wrap and
pricing-crash hypothesis is **falsified**.

Market inventory is a signed Python integer. Town and shop consumption can
legitimately move it below zero, and BUY_PRODUCT can also cross zero. There is
no uint32 wrap. Price refresh computes scarcity distance as `I0 - inventory`;
all supported shape functions therefore receive nonnegative inputs, and
`market_price()` returns a finite positive integer.

The full-interpreter probe starts every product at 1, 0, and -1 while all town
shops and center consumption fire together, verifies every exact decrement, and
checks all resulting prices. A separate two-unit Wheat purchase starts from
inventory 1 and reaches -1 without a crash.

Run from this directory:

```bash
python3 -m unittest -v test_market_underflow.py
python3 verify_market_underflow.py
```

No TITAN runtime, policy/default, archive, opponent, seed panel, or Kaggle state
is changed.
