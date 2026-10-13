# Gemini MERIDIAN convergence — hidden-state bounds and adaptive recourse

Status: **research-only historical convergence; no runtime/default/policy authority**.

This file brings two authenticated custom-Gemini MERIDIAN proposals into the single V4 convergence surface without reimplementing the older T15 planner.

## 1. Hidden rival inventory / physically feasible stream pruning

Custom Gemini MERIDIAN proposed an optional upstream filter for T15: use public cash plus mass-balance constraints to exclude rival market streams that are physically impossible before maximin, while preserving ambiguity over hidden spending, purchases, deposits and carried inventory. The proposal explicitly required a **joint** shed-capacity constraint rather than independent per-product clipping, kept carry separate from shed, warned that net cash is not gross receipts unless costs are identified, and required ordered own+rival market semantics. The relaxation was required to retain a superset of feasible hidden states and prune only contradictions.

That proposal was not safe to promote literally from prose, but later T15 work built the useful core in stronger forms:

- `revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/joint-capacity/` (PR #10377) applied shared shed-capacity tightening to the retained 64 terminal-history families. It tightened **604** still-floor-censored intervals and removed **4,772 units** of upper-bound slack, but changed **0** lower bounds, **0** readiness decisions, **0** scenarios and **0** family projections. No interval became exact.
- `revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/interval-family/` (PR #10395) then enumerated the **complete same-lag integer sale-vector set** under shared shed capacity and explicit slot/operating-stock hypotheses when the whole set fit a bounded family. Marginal endpoints were never composed independently. A >32-vector/scenario family returned a named limit/fallback rather than a partial family. On the saved 64-record bank, 28 bounded families were representable but all were already exact-ready; 36 exceeded the bound; **newly ready = 0** and terminal selector executions = 0.

### V4 disposition

**CORRECTED_DESCENDANT / RESEARCH_ONLY.** The valuable theorem is uncertainty reduction by joint physically feasible hidden-state families, not a private-stock oracle and not a blanket stream predictor. Preserve the complete-family/superset guarantee and explicit fallback when enumeration is incomplete. Current evidence shows real bound tightening but no activation improvement, so no V4 action consumer is warranted from this result alone.

Promotion requires a current-native consumer whose robust decision actually changes because a complete public-only feasible-family set removes a contradicted stream, plus both-seat official-engine economics. Private rival stock/current orders and evaluation-only realized rival actions remain forbidden policy inputs.

## 2. Adaptive recourse after an identical committed prefix

Custom Gemini MERIDIAN separately proposed adaptive recourse among plans that share an **identical committed prefix**: commit only the common prefix, then choose a continuation after a newly visible public observation partitions the remaining scenarios. It explicitly required preserving every stream compatible with the entire public observation and forbade branching on unobservable world labels.

This was subsequently implemented in the existing T15 adaptive authority rather than a second wrapper:

- PR #10008 landed `revenue/kaggriculture/cloud-market-game-theory/adaptive/recourse.py` and the tree/selector tests.
- The retained package demonstrates a strict constructed-state positive where adaptive recourse improves over a one-shot mixed plan.
- Held sets did **not** improve wins: retained README results report held A baseline 20-20 vs adaptive 20-20, held B baseline 17-20 vs adaptive 17-20. Therefore the implementation is a real source component but not a measured strength promotion.
- Later continuation work tightened the identical-prefix contract further: PR #10225 preserves exact emitted product/slot/quantity prefix before accepting a different suffix, while keeping legitimate identical-prefix suffix recourse.

### V4 disposition

**CORRECTED_DESCENDANT / RESEARCH_ONLY.** Preserve the existing recourse theorem and its exact-prefix/public-observation contract. Do not activate it merely because constructed states improve. A V4 consumer must first show natural current-native recurrence, correct public observation partitioning, no hidden-world leakage, and positive both-seat economics relative to the incumbent complete-plan decision.

## Why this is a bridge, not another planner

The source implementations and receipts remain in their existing historical T15/continuation authorities. This V4 file only records their durable Gemini provenance, corrected theorem, negative activation evidence and promotion boundary so those ideas are neither lost nor rebuilt as parallel controllers.
