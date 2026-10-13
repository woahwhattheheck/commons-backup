# Development results — checkpoint 2

No held-out seeds have been run. No submission recommendation yet.

| Experiment | Games | vs Kaito mean margin | vs Igor mean margin | Interpretation |
|---|---:|---:|---:|---|
| Igor reconstructed + immediate sale, truncated slots | 8 | -17,812 | -2,146.75 | Rejected |
| Above + route-prefix commitment | 8 | -17,812 | -2,146.75 | Identical; route-switch diagnosis unsupported |
| Actual Igor baseline | 4 | -13,175 | 0 | Control |
| Actual Igor + route-only | 4 | -13,175 | 0 | Matched control exactly |
| Actual Igor + slot-preserving sales-only | 4 | -13,174 | +121 | Still loses to Kaito |
| Kaito + immediate sale, truncated slots | 8 | -57,785.5 | -38,019.5 | Rejected |
| Actual Kaito baseline | 8 | 0 | +14,824.75 | Four ties against self; four Igor wins |
| Kaito + slot-preserving sales-only | 8 | +4,556.25 | +11,352.5 | Eight wins; lower Igor margin than parent |

Controls use development seed9400109 for Igor and seeds9400109/9400123 for Kaito. Raw reports retain candidate hashes, both seats, per-game cash/action/transaction/runtime and final state. First-stage variants are retained as failed evidence, not recommended agents. Clean standalone candidate removes unused Igor routes and calls the ACTUAL Kaito entrypoint once; its production actions/router/repair state remain unchanged. Fresh development seeds9400137/9400151 and a separately isolated observed-farm-similarity sale gate are in progress.

## Corrected causal interpretation

The initial cash/shop/route explanation was only a hypothesis and was not supported by the route-only controls. Shop unlocks occur on fixed day boundaries, not cash thresholds. Policy changes can alter RNG consumption indirectly through empty tiles/weed draws, but that does not establish the cause here. The initial market overlay demonstrably appended/prepended sales and truncated the queue to ten, dropping planned hires. Kaito routes contain many ten-order daily hire openings. Keeping every parent slot fixes that implementation error; it does not prove generic immediate-sale superiority.

On seed9400109 Kaito self-play earns102348 each; the sale edit earns100306 versus98328. Against Igor, unchanged Kaito earns83279 versus70104, while the edit earns77306 versus67748. Own cash, opponent cash and winning margin are separately reported. Endogenous prices and later farm effects prevent attributing all final differences to one isolated unit price.

## Leader replay used as context

Read ../cloud-frontier-trace/OBSERVATIONS.md for episode106392861. Tomato diversification and realized sale prices are evidence to investigate, not copied inventory targets. This lane has not installed a copied one-game crop mix, replayed hidden future actions, or claimed a current leaderboard rating. Root owns submission.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
