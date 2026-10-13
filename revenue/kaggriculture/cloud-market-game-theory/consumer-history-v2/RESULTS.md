# One TITAN: history development ablation

The exact PR10152 archive75740d43 completed128/128 games on
DEVELOPMENT9943201-9943216. History ON and OFF each finish62W/0T/2L.
All64 paired engine traces, own cash and rival cash are identical. The history
mechanism executes but changes no terminal action in this panel. This is consumer
evidence for the single integrated TITAN, not a separate release or submission.

| Opponent | OFF | ON | Paired cash changes | Outcome flips |
|---|---:|---:|---:|---:|
| Exact frozen SELL | 30W/0T/2L | 30W/0T/2L | 0 | 0 |
| Retained public COK10 | 32W/0T/0L | 32W/0T/0L | 0 | 0 |

Both seats are retained; mirrored cells are not independent evidence. The two
negative-margin cells in each arm are SELL9943203 seat0,59067 own/59407 rival,
and SELL9943211 seat0,61291 own/63515 rival. Their history families do not reach
the minimum joint support. No incomplete game, external RPC deadline exit or
internal deadline fallback occurred in these128 attempts. Earlier T15 and peer
runtime exposures remain unchanged historical evidence.

## What actually ran

Each ON game uses the archived TITAN-HISTORY-CONFIG.json; OFF changes only
terminal_history=false. Both call the same archived TitanAgent and frozen+funded
seed production path. The candidate calls one parent per turn:46016 calls per
arm. ON records45952 observed-fill reconciliation turns across64 games.
All71 archived runtime entries, source/engine/opponent bindings and the source
freeze were verified unchanged. No isolated method or constructed case is counted
as a game. Original six boundary cases were not rerun.

First4 seeds completed32games in149.32s. The same-source next12 completed96games
in470.25s; jobs2 throughout. No decision, hypothesis or timing parameter changed
between chunks. No held seed or hosted submission was used.

| Timing, candidate arm | History OFF | History ON |
|---|---:|---:|
| Largest returned call, seconds | 0.468688204 | 0.249908962 |
| Largest external RPC, seconds | 0.726592720 | 0.284547245 |
| Largest episode wall, seconds | 12.041499314 | 12.891133319 |

These are observed maxima, not a general latency guarantee or causal speedup.
Existing evaluator limits are1s per action RPC,120s episode,zero overage. Cold
package construction and diagnostic extraction are inside the returned call;
serialization and transport count toward RPC. Per-game actor CPU/wall and all
input/action traces are retained. No new timing framework was introduced.

## Why history changed no action

Forty of64 terminal families are ready and reach complete native receipt tables.
Twenty-four have fewer than three common eligible lags across all seven identified
products. Their actual retained intervals include floor-censored WOOL in21games,
STRAWBERRY in9 and MILK in2; these counts overlap. Missing common-lag evidence
remains unknown. WHEAT/FERTILIZER stock is supplied only by the explicit quiet
operating-stock hypothesis, not inferred from rival cash or hidden inventory.

Of40 ready families,34 contain only quiet queues and6 include nonzero prior
historical lots. Every complete table gives the baseline the maximum conditional
absolute win score1, so the configured baseline tie rule preserves its action.
Scanning those exact native receipts yields zero pure cash-Pareto alternatives;
changing only the existing cash_pareto tie setting would not create an economic
choice on these tables. No additional configuration arm was justified or run.

The actual final rival queue is absent from36of40 ready finite families. This is
an evaluation-only coverage comparison, not a demand for exact action prediction.
The concrete mismatch is terminal liquidation versus ordinary same-hour history:
SELL9943201 really liquidates MILK5/WOOL2/CARROT47/EGG2/FERTILIZER9, whereas its
ready family contains only an empty queue. Historical zero sales at hour22 do not
establish zero terminal inventory. Slot order and quiet operating stock remain
finite hypotheses; scenario probabilities remain null.

The original integration owner receives these reached states, causal intervals,
native receipts and actual queues as inputs for improving the single TITAN's
terminal-family construction. A broader legal terminal inventory family must use
public constraints and explicit hypotheses; these evaluation-only rival actions
must not be fed into policy. This result does not warrant a history-on default.

## Source and delivery

PR10157 merged the runnable consumer and first32 receipts at
a8bb9032a79035894e8d7fae9222703ec2db00de, all73 paths exact readback.
The final successor adds96 original receipts/traces, RESULTS.json, this report,
and ACTIVATION-DIAGNOSIS.json with its offline reader. FIRST4.json and the original
SOURCE-FREEZE.json stay unchanged. All results live only under the owned consumer
scope; the integration owner retains main.py, the current archive and its pointer.

At checkpoint main c9fb7ee2f, the existing current pointer and downloaded current
archive still both identify70554dc0. The integration owner is consolidating that
pointer with newer source. No replacement archive was chosen or produced here;
this completed experiment remains explicitly bound to75740d43. Next executable
intake uses the integration owner's single current artifact after consolidation.

No old adaptive panel, successful peer cell, source-bank export, upload, notebook
write, owner-PC execution, new VM or paid service was used. Lower-level negative
arms remain available. Full receipts and trace hashes support every aggregate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
