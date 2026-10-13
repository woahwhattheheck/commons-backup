# Recovered BIRCH shared-capacity handoff

This directory makes BIRCH's previously local-only tested patch durable without
claiming that the production bridge or canonical TITAN default has adopted it.
The original package explicitly reported no Slack/GitHub publication.

BRIDGE recovery check (2026-09-08): `test_joint_capacity_patch.py` extracts the
exact `tighten_joint_sales` function from `upstream.patch` and executes 11
standard-library methods. All 11 pass. The suite covers validation, singleton and
partial tightening, operating-product exclusion, no-change identity, and exhaustive
two-product integer marginals for capacities 1..6. It does not run the native
engine, policy actors, games, or reproduce BIRCH's larger 21-method/native packet.

Current main was checked before recovery and still had the exact original target
blob `59d85cefb4cb793f8d7a3fc79d8e5675449956fb`; GitHub code search returned no
`tighten_joint_sales`. Apply/adopt through the history owner after current-source
revalidation. Do not infer terminal-history strength or enable it by default from
this recovery alone.

---

# TITAN: shared-capacity refinement of prior sale history

**Status: implemented and tested locally; not posted to Slack, pushed, or merged.**
The original session exposed read-only Slack/GitHub connector actions. The two
patch files were an integration handoff, not an assertion of repository delivery.
No selected default, canonical archive, provider submission, or live process was changed.

## The concrete change

The existing `SelectedActionHistory` bridge intersects prior non-buyable-product
sale intervals with their shared pre-market shed capacity. In the pinned native
engine, worker actions finish before market processing; CARROT, TOMATO, STRAWBERRY,
MELON, EGG, MILK, and WOOL cannot be purchased to replenish that shed during market
processing. Their total sold quantity therefore cannot exceed its starting capacity.
WHEAT and FERTILIZER are deliberately excluded because market buy/sell cycles are possible.

For old marginal bounds `lower[i] <= quantity[i] <= upper[i]` and shared capacity `C`,
the added helper computes:

```python
new_upper[i] = min(upper[i], C - sum(lower[j] for j in other_products))
```

This preserves every previously feasible original joint vector and yields the exact
marginal bounds of that capacity relaxation. It does not make interval endpoints
independent. A missing product record stays missing; impossible joint lower bounds
produce the existing unknown-history outcome before any record is appended.

For example, 100 proven MILK sales from a capacity-100 shed force a formerly
floor-censored WOOL `[0,100]` interval to `[0,0]`. Eighty proven MILK sales tighten it
to `[0,20]`, still uncertain. A request to sell 100 MILK is not proof of 100 sales:
a native price-floor negative control proves only 76 admissions and keeps WOOL
`[0,24]`. Quiet floor-censored history stays unknown rather than becoming a guessed zero.

When a sale interval is genuinely singleton, the bridge marks its quantity identified
for the unchanged `FlowHistory`. Original censoring reason and old/new sale/admission
bounds remain in `joint_sale_bounds`. Exact sold quantity is not exact market admission,
revenue, current hidden stock, an observed rival order, or a future probability.

The production change is limited to an added `tighten_joint_sales` helper and its
call from the existing `SelectedActionHistory.observe`. Every other existing method
is AST-identical. There is no new controller, solver, scenario sampler, or wrapper.

## Executed validation inherited from BIRCH

| Check | Result and scope |
| --- | --- |
| New regression suite | **21 methods pass**, zero failures/errors. |
| Exhaustive integer relaxation | 14,745 interval/capacity inputs: 9,109 feasible and 5,636 rejected as inconsistent. All 56,604 feasible integer portfolios are retained, and marginal bounds match enumeration. |
| Native prior-market cases | 19 targeted historical/control transitions plus a separate 336-transition portfolio sweep across both positions and capacity/price regimes. All 2,352 truth-containment checks pass. Rival truth is used only by the test, never by the bridge. |
| Existing downstream consumer | Constructed same-phase history reaches three joint lags, where the original reaches none. The unchanged terminal producer's eight conditional market cells match eight full native-interpreter terminal transitions on both cash rewards. |
| Original-source discriminator | Nine new native-consumer requirements against the exact original produce seven expected failures and zero execution errors. The other two controls pass. This is not a passing original test suite. |
| Retained-data check | All 55 prior transitions / 385 non-buyable intervals remain unchanged: exact intervals **334 -> 334**, ready joint families **1 -> 1**. |

**The retained data show no natural coverage gain.** They are the prior PR10134
phase-study receipts, not RULE's later 128-game bank. This patch does not resolve
quiet or generally censored histories, establish game strength, or justify enabling
terminal history in the selected policy. Its positive evidence is a source-grounded
conditional inference that can be consumed when those constraints really arise.

The native tests use actual inference, history, bridge, joint-family and terminal
producer code, with a pinned official interpreter. They use the bridge's documented
shared-ledger interface with an already-reconciled empty own queue fixture. They do
not execute the actual `ObservedFillLedger`, a policy actor, or a full game. The
retained-data checker performs only new arithmetic over saved intervals; it reruns no
prior actor, inference, market transition or game. No game seeds are consumed.

## Exact source and integration destination

Original bridge Git blob: `59d85cefb4cb793f8d7a3fc79d8e5675449956fb`.
Candidate bridge Git blob: `7967fb43c64bc3154fe7da609497873163c773eb`.
Candidate SHA-256: `f83bf0804eadee97b91250ec0f93c44332cc2269d38b66aa25568873c46694d4`.

`upstream.patch` targets:
`revenue/kaggriculture/cloud-market-response/selected_action_history.py`.

The original package also contained a canonical-reference patch carrying the same
implementation into the existing TITAN dependency mirror. That canonical adoption
remains builder-owned and is deliberately not represented as completed by this
recovery directory. An old archive does not acquire this change automatically.

Pinned official engine reference in BIRCH's evidence:
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.

## Provenance and limits

Source was read through the connected repository and recovered from Library receipts.
BIRCH retains implementation and native-test attribution. BRIDGE adds only durable
publication of the exact patch plus the 11-method patch-level acceptance check.
No credentials are bundled and no provider/account action occurred.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
