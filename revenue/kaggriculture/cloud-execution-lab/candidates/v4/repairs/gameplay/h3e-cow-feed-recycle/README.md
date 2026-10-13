# H3e COW feed-recycle recovery

Canonical V4 source-custody recovery from PR #12618, exact source head `de7719d2314cc3acbbbfc9010a503069dac94a01`.

Preserved exact reviewed bytes only:
- helper `r04_h3e_cow_feed_recycle.py`: Git blob `6ca7c2e150f40f4deb68d9244b53a30342f33493`;
- focused test `test_v4_h3e_cow_feed_recycle.py`: Git blob `6a7b130fce439269b9eb896de0c5fe47dbda93a9`.

The stale PR's shared `apply_v4.py` is intentionally not carried because it encoded an old whole-agent seam against a superseded composition. This recovery does not add/enable the key, alter defaults/config/runtime/router, execute a legacy materializer, or make an economics/promotion claim.

The preserved theorem is narrow: at a real hour-23 EOD callback, exactly one provably dead CARE/HARVEST/COLLECT_FERTILIZER action may become same-tile FEED only for an escape-imminent COW when that actor already carries WHEAT. Multiple candidates, stacked active actors, productive service, malformed/nonstandard state, wrong hour, and terminal partial-day callbacks fail closed. Future wiring must re-prove the outer-seam ordering against the current canonical hidden-hand reconstruction before activation and remain default-OFF until separately promoted.
