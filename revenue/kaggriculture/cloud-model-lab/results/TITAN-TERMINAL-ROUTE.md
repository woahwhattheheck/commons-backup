# `terminal_route` on the canonical archive: a tie-breaker, not an improvement

Same immutable archive both arms: `titan-current.tar.gz`, 195,741 B, sha256
`70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb`. Source
unchanged, never edited, repacked or substituted. The only difference is
`Features(terminal_route=True)`, constructed in `cloud-model-lab/overlays/` and
recorded with the results rather than written back into the archive.

272 games, 104 paired cells, 0 failures, worst action 143.9 ms. Development seeds
**9902201–9902232**, censused clean against main `2fc1418f`; no overlap with
WIDEFIELD 9921, ECON 9922013–28 or T15 9943.

## Rating first

| opponent | control (default) | candidate (`terminal_route=true`) |
|---|---|---|
| **T08 frozen SELL** | 42/20/2 | **54/0/10** |
| Apex | 32/0/0 | 32/0/0 |
| COK | 8/0/0 | 8/0/0 |

The route **activates in 65 of 104 paired cells (62%)** — it changes terminal
cash there and is exactly inert elsewhere. Against Apex and COK it never changed
a single outcome, so those 40 cells carry no information about it.

## What it actually does: it resolves ties, at close to chance

Every one of the 20 ties against frozen SELL becomes decisive. **It never turned
a loss into a win, or a win into a loss** — the only transitions observed are
`T→W` and `T→L`.

| transition | seat-cells | independent seeds |
|---|---:|---:|
| `T→W` | 12 | **6** |
| `T→L` | 8 | **4** |

Both seats return identical cash throughout this panel, so the seat-cell counts
double-count: the honest tally is **6 favourable seeds against 4 adverse**.

Read as win-equivalents with a tie worth half a win — the reduction Kaggriculture's
Bradley-Terry standing and Kaggle's Gaussian simulation ladder both imply — ten
tie-resolving seeds are worth 5.0 before and 6.0 after: **net +1.0 over 10 seeds**.
One-sided binomial P(≥6 of 10) at even odds is **0.377**.

## Verdict

**No demonstrated gain. `terminal_route` stays opt-in and is not promoted, and no
held seeds were spent on it.**

It is a coin-flip on the only thing it touches. The first four seeds looked
promising — 4/4/0 → 8/0/0, all four ties favourable — and the next twelve
regressed to 6 W and 6 L on their ties, which is what a chance tie-breaker looks
like when the sample grows. Reporting the four-seed result alone would have been
a false positive.

Spending a held panel on this would not change the conclusion: ties are the only
outcome it moves, ties are rare, and at this rate a held set of the usual size
contains too few of them to separate +1.0 win-equivalents from zero. If anyone
wants to keep pursuing it, the useful axis is more development seeds against
frozen SELL specifically — every other opponent tested is inert — not a held
panel and not a new registry.

Own/rival cash on the flips is small in both directions: the favourable ones run
+42/−50 and +91/−106 own/rival, the adverse ones −8/−5. These are ties being
broken by tens of coins, not a production or liquidation gain.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
