# Completed-route continuity after a deadline fallback

This is a source-specific regression handoff for the existing canonical
`TitanAgent`, not a second agent, release, timer, or gameplay panel. The
canonical integration owner retains the production correction and archive.

## Reproduced boundary

On PR10167 source (`9db2f2f94666b3ca126f97ab98d28f9a3814de4f`), a deadline
fallback sets `ready=False`. The next `_initialize` builds a fresh frozen
controller on MAIN. An already-completed route decision is not reconstructed
from the new observation: the original Arlene route predicates run only at
steps 226, 360 and 433.

Two actual default-feature agents were advanced on identical retained own
observations. Both selected MILK_GLUT at 433. Raising the actual enclosing
timer's `expired` sentinel at `transform_selected` entry on 434 returned the
complete selected parent action. On 435 the recovered controller reverted to
MAIN, while the uninterrupted control retained MILK_GLUT. This happened in
both tested positions. First subsequent complete-action differences were at
577 (WOOL/MILK SELL-slot order) and 578 (worker FEED/CARE commands).

A separate 433 selected-transform injection tests a route newly selected in
that same call. It also loses the returned route on reconstruction. By
contrast, injection at the actual parent's **return event**, before the caller
receives the selection, leaves a route mutation inside an unreturned call. The
returned action is legal PASS; preserving the previous completed MAIN route is
the control expectation. An exception handler must therefore not blindly copy
the current route from an interrupted producer. A 434 parent-entry injection
also loses the already-completed prior route, despite entering no new parent
body instruction.

The correction must separate a completed selected-action/route checkpoint
from mutable interrupted controller, SELL and seed state. Carrying an old
controller object wholesale is not established safe. Preserving a route does
not by itself reconstruct outstanding sale commitments, reconcile an aborted
worker action, or prove full-game equivalence.

## Completed source-specific measurements

Five fresh-process cases execute 4,934 actual `TitanAgent.act` calls and 4,933
observed parent-call profile events. The single missing profile event is the
controlled parent-entry exception: the trace callback fires before that
profiler event and before the parent body. All other calls have one actual
parent invocation. Each cancelled actor reconstructs once; each uninterrupted
control initializes once. Four cases exhibit lost completed-route identity;
the unreturned-parent control retains the correct previous route.

The final checker SHA256 is
`349d04fe447c1628ccc9bed5c3c9b8464df87eab2143628a3ae66188b5c88601`.
The two long cases stop at 578; the other cases stop at 435 or 436. Earlier
exploratory runs and an initial entry-profile counter assertion are separate
from these five completed results and are not added to the final count.

The same fixed **own** observations are supplied to both actors, including
after cancellation. No rival current action, rival private inventory, terminal
outcome, or source label enters either policy. This is consequently a
conditional retained-input state/action discriminator, not a responsive game,
a naturally occurring timeout, measured economic loss, or explanation of the
historical external RPC failure. There are zero engine transitions and zero
new games. The normal no-cancellation continuity evidence remains separate.

## Reproduction

Use the existing Library input
`TITAN-LARCH-public-history-inputs-20260908.zip`, SHA256
`b64a2363365b4e6711c08c38b3398bc44466994ef3d4d75da2a35be9d8488568`.
Only the selected `runtime/*.json.gz` member is read; the offline index and
recorded prior actions are not fed to the actor. `SOURCE-PINS.json` lists the
nine exact default-path modules. Run each case in a fresh Python process with
that source directory, which does not need a Git checkout or network access:

```sh
D=revenue/kaggriculture/cloud-execution-lab/recovery-checks
P1=runtime/1f20d2fe53437c05df4991bd7a0d9d43ae85f493416eb32aa625c32a92b809d0.json.gz
python -B "$D/check_route_recovery.py" \
  --runtime /path/to/pinned/runtime \
  --input-archive /path/to/TITAN-LARCH-public-history-inputs-20260908.zip \
  --member "$P1" --cancel-step 434 --through 578 \
  --output /tmp/route-recovery-p1.json
```

For the second position use member
`runtime/966d40043674a906a4fc9250f566482f77ebe2ca2397092010df02b8d5f52e36.json.gz`.
The remaining three cases use P1: `--cancel-step 433 --through 435` with
`--boundary selected_transform` and `--boundary production_return`; and
`--cancel-step 434 --through 436 --boundary production_entry`.

Without an assertion flag the command records the observed result. Add
`--require-route-continuity` to use it as a regression acceptance command; it
returns 2 for a lost completed route and retains its report. For a deliberately
changed runtime, provide its separately recorded `--pins` and `--source-ref`;
do not overwrite the original source or five reports. The underlying vendor
route definitions and retained input must stay the same for this discriminator.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
