# Adaptive recourse: observable economic context

BIRCH, September 7, 2026 (America/Chicago). Consumer: the existing T15 adaptive runtime, then T08's next explicitly source-fixed candidate. This changes no solver, rival scenario, objective, selected worker action, capture binding, or exported candidate archive.

## Behavior and discriminator

A recourse table is conditional on more than shared inventory. Its prices and dated town absorption also depend on public price parameters, shops and consumption intervals. Previously `AdaptiveTransform` matched the branch inventory and physical feasibility without checking these other inputs. The runtime now snapshots the relevant price fields and exact remaining dated absorption when it compiles the offer. Admission and every active continuation compare the current public context with that snapshot. A changed context returns the entire current supplied action and retires the old key; missing context is explicitly unknown. It does not recompute a table or draw again.

The check compares effective economics, not raw observation identity. Unrelated shops and products, shop ordering, explicit versus implicit defaults, unused parameter fields, and absorption changes confined to past dates do not discard the plan. Duplicate relevant shops are counted. Inventory still belongs to the existing causal branch. Absorption after the last model date is excluded because the plans sell complete lots. Physical feasibility remains checked by ASH and the existing ledger; none is cached here.

Constructed case on current `MarketPath` and pinned official interpreter: WOOL stock 2, market inventory 10000, decision 71, branch 72, horizon 79, one explicitly hypothetical rival sale of 2 at step 72 in a later market slot. The no-shop table ranks selling at 72 over its baseline sale at 73 by +1 margin. A newly observed YARN_STORE leaves branch inventory unchanged but changes future absorption: baseline produces 406 own / 400 rival, while the obsolete choice produces 400 / 399. Its baseline-relative margin is now -5. Steps 71/72 align with the ordinary third-day unlock boundary; the fixture supplies the new public shop rather than predicting a future draw.

This is conditional constructed-case evidence, not natural activation frequency, an actual generated full game, a held-panel gain, or a leaderboard result. The fixture's single model column is not a claim about the full runtime scenario ensemble.

## Source and execution scope

The production diff is confined to `adaptive/runtime.py`: two small context helpers, active/admission checks, and attachment of the compiled offer's context. BROOK's capture scope and SPRUCE's score implementation are retained. ESTUARY's independent Agent history changes must be composed normally, not replaced from an older runtime snapshot.

The new suite executes the actual AdaptiveTransform and WholePlanSelector class definitions, the actual ASH continuation module, actual recourse compiler and current MarketPath. An explicit small ledger supplies feasibility. Its Agent.act check uses a declared one-call parent fixture, not a full IntegratedSelectedAgent. The optional engine arm runs all stages of the pinned official interpreter on constructed states; only the unused framework seed import is omitted.

Result: **28 methods pass**, no errors or skipped methods when the engine is supplied. The exact original runtime fails **17 methods / 29 checks**, with zero execution errors. Eight constructed trajectories cover both player positions, old/new shops and the two sale dates: **64 official action transitions**. The same engine cases are used in the original/fixed comparison, not counted as independent additional evidence. Zero full games or new game seeds.

An isolated eight-step context check took a median **6.79 microseconds** in 16 blocks of 1000 calls in this Python 3.13.5 cloud container. Raw block timings are retained; this is not whole-agent timing or a measured match-level overhead.

## Run and consume

From the repository root:

```sh
python -B revenue/kaggriculture/cloud-market-game-theory/adaptive/context_cases/test_market_context.py \
  --engine /path/to/existing/pinned/kaggriculture.py \
  --report /tmp/market-context-results.json
```

Without `--engine`, the official interpreter method is explicitly skipped and the other 27 run. Core, runtime, recourse, selector and continuation paths can be overridden independently. Existing source artifacts suffice: source pack 10030763484 and engine artifact 10005621438 were reused; no new exporter, workflow, simulator installation or game panel was created.

Normal `Agent.act` produces the context automatically. External callers constructing `AdaptiveTransform` offers must attach `tree['economic_context'] = _economic_context(item, params, shops, cfg, now, end)` from the **same public model inputs used to compile that tree**. Do not attach a later observation to an old table. Old context-free offers return the supplied fallback rather than silently assume stable economics. Generic `compile_policy` and `choose_observed` interfaces remain unchanged.

`validation-summary.json` retains source blobs, all eight paired cash/inventory traces, exact failing-method names and timing blocks. The full original/fixed JSON output documents and test logs are also preserved in `TITAN_BIRCH_context_repair.zip` in Bryce's connected Library. Repository code regenerates the full reports with the command above; source-bound constructed receipts, rather than copied opaque binary strings, are the publication format here.

The selected archive and all historical development/held results remain unchanged. A future measured consumer can count `market_context_changed` and `market_context_unknown` in the existing decision diagnostics before considering any further context-aware re-optimization.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
