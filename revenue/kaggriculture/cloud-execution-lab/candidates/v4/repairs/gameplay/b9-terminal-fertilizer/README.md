# B9 terminal fertilizer recovery

Canonical V4 source-custody recovery from repaired V3.1 PR #12538, exact reviewed head `8032047c70459c7b495241eb9192232a63415394`.

Preserved exact reviewed bytes only:
- helper `terminal_fertilizer.py`: Git blob `ed8d6923541e700c3a0ae4b93695bbd56455a3b6`;
- focused test `test_terminal_fertilizer.py`: Git blob `850f439c764b5b4dfb631d40a04ccc7f1dce2093`.

Historical corrected-V3.1 evidence is relevant custody context, not V4 promotion authority: B9 was selected in the corrected final alongside H3c; the closeout recorded approximately +1.6 margin/game over the field arm with 882 better / 0 worse and +2.0/game live, while the H3c+B9 combined arm was also positive. Those receipts bind the V3.1 final family, not current V4.

The preserved theorem is narrow: on standard 720-step / 24-turn-day games, literal represented-worker PASS at steps 716-717 may become same-tile COLLECT_FERTILIZER only on a shed-adjacent animal with strict public fertilizer availability; at step 718, only after same-episode collection, SELL FERTILIZER rows may be stable-partitioned behind other rows inside the executable market prefix, leaving the raw tail at original indexes. Malformed timing/config/actor envelopes fail closed and clear provenance.

This directory does not add or enable a V4 key, alter config/defaults/router/runtime, copy V3.1 final glue, or execute any legacy materializer. Any future V4 wiring must be reviewed against the then-current terminal liquidator and executable-prefix semantics and remain default-OFF until separately gated.
