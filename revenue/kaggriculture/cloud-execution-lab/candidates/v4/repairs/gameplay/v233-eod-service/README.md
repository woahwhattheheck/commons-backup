# A1 / V233 hour-23 sheep-service donor custody

Canonical V4 custody for the completed-but-unmerged A1 donor from PR #12623. This package preserves exact reviewed donor bytes only; it does **not** wire or execute the legacy V3/R04 materializer/router.

Exact final donor carrier:
- commit `3154b5dc1ae312c095442e86c8c9eaa1c4338126`
- tree `211fd250b074bd902c83d321e21b3f558ca90d80`
- helper blob `72e281d9fbd9298f29e3bd87b3fc4759508e1684`
- focused-test blob `0e4503aadf93d3eb7dcedf72a25bcb48725a5851`

The original composition blocker (A1 running inside `_v3_stack`, where the fert-hand wrapper hid carried inventory) was repaired by moving A1 to the outer `v3_agent()` seam after `_v3_core` / fert-hand reconstruction and after H3c. Read-only source/composition review then reported PASS on repaired head `37890f6c31f628690c4e73948d46406b272131f8`; the later `3154b5dc...` post-B10 donor retained the same A1 source/test bytes and composed `H3c -> A1 -> B10` with the A1 key OFF.

The theorem is narrow: on a non-final hour-23 callback, replace only a same-call V233 cargo-return MOVE that cannot physically deliver before EOD with same-tile FEED or CARE, after proving strict sheep/config/state shape, real actor cardinality, no ambiguous same-tile actor, no current market stock inflow, and a whole-farm EOD capacity upper bound. HARVEST/COLLECT and shed-adjacent PLACE are out of scope.

Disposition: **PRESERVED SOURCE DONOR / NOT CURRENT-ABI INTEGRATED / DEFAULT-OFF**. Any live V4 use must semantically port into the current runtime seam, rerun current-native normal/optimized tests plus exact engine/capacity regressions, and register the resulting blobs/receipt in `INTEGRATION.json`. Do not copy the old `apply_v4.py` postimage or create a sibling V4 root.
