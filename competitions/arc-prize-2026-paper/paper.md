# Skills as a Compression Prior for Interactive Reasoning

_Submission candidate for ARC Prize 2026 Paper Track. Provider-linked Kaggle accuracy evidence is intentionally pending; local results below are mechanism checks only._

## Abstract

We study a simple claim for interactive reasoning: reusable state-action skills are a compression prior over hidden task dynamics. An agent should spend scarce actions learning what interventions do, promote successful traces into skills only when their preconditions and effects are stable, and reuse those skills when the same latent structure recurs. The repository’s landed ARC-AGI-3 SAGE carrier implements this design family with animation-aware observations, action-effect hypotheses, action-budget planning, generalized skill induction, deterministic receipts, and an official-toolkit adapter. This paper carrier adds a falsifiable theory, ablation protocol, provenance boundary, and reproducibility gate. A deterministic synthetic microdynamics test shows how skill reuse changes action cost under repeated structure; it is not represented as ARC/Kaggle accuracy. Final prize eligibility remains gated on a real public ARC-AGI-2 or ARC-AGI-3 notebook and submission ID.

## Motivation and Prior Work

ARC asks systems to adapt when task rules change rather than merely recognize familiar input patterns. Static ARC-AGI-2 emphasizes inferring transformations from examples; interactive ARC-AGI-3 adds the cost of discovering an environment through actions. In that setting, every exploratory move is both a decision and an experiment.

Our starting point is the already-landed SAGE research carrier in Commons, not a new claim of solver ownership. SAGE retains multi-frame observations, extracts deterministic change signatures, learns action-effect hypotheses, chooses exploration under action budgets, and compiles successful traces into reusable skills. Earlier Commons ARC-AGI-2 work provides a contrasting symbolic baseline built from explicit geometric and relational hypotheses. The paper contribution is to explain these mechanisms as one compression-and-intervention principle and to make that principle testable.

## Method

Let a skill be a tuple `(P, π, E)`: a precondition predicate `P`, a bounded action policy `π`, and an expected effect signature `E`. A trace is promotable only after observed transitions support both `P` and `E`; otherwise it remains evidence, not reusable authority. On a new state, exact skill reuse has priority only when its preconditions match. If no skill is admissible, the agent selects an intervention that reduces uncertainty over candidate action effects while respecting a finite action budget. The resulting transition updates the local world model. Successful traces may then refine or create skills.

This creates two distinct savings. **Within a task**, informative interventions eliminate incompatible action-effect hypotheses. **Across repeated latent structure**, a verified skill replaces renewed search with a short conditional execution. The method therefore predicts the largest gains when substructures recur, action budgets are tight, and transition effects are stable enough to identify.

## Why It Works

Assume a family of environments contains recurring latent subproblems and that an unknown subproblem would otherwise require search over `k` candidate interventions. Re-solving every occurrence pays that search cost repeatedly. A retained skill pays the identification cost once, then reduces later occurrences toward the length of `π`, provided `P` discriminates the relevant regime and `E` remains stable.

This is a compression view: the skill library is a shorter description of repeated successful transition structure than independent traces. It is also an experimental-design view: information-seeking actions are valuable because they reduce the version space before committing to longer policies. Neither view guarantees success. False perceptual equivalence can make `P` too broad; nonstationary dynamics can invalidate `E`; sparse feedback can prevent reliable promotion; and an overgrown skill library can create misleading transfer. The correct response is abstention or renewed exploration, not forced reuse.

## Results

The included deterministic microdynamics experiment is a mechanism sanity check, not an ARC benchmark. It generates repeated hidden transition families and compares four variants: the full reuse/update/probe loop; no skill reuse; no model update; and no information-gain ordering. The experiment records mean and p95 actions plus success rate across fixed seeds. Its generated JSON and SVG are content-addressable and explicitly labeled `LOCAL_SYNTHETIC_MECHANISM_ONLY`.

Across 64 fixed seeds and 15,360 episodes per variant, the full mechanism uses 1.705 actions per episode on average. Removing exact skill reuse increases the mean to 1.829; removing model update increases it to 2.166; replacing learned probe ordering with fixed open-loop order increases it to 2.173. Every variant still reaches its synthetic goal, so the comparison isolates action cost rather than success/failure. The benchmark deliberately contains a recurring dominant transition regime plus a recurring minority regime: coarse effect learning captures the common structure while exact skills preserve finer exceptions.

These measurements test the qualitative prediction that repeated latent structure can reward both retained skills and learned intervention structure. They do **not** establish Kaggle Accuracy. The submission-readiness compiler refuses a positive owner-review state until it is given an actual ARC track, concrete Kaggle submission ID, public notebook URL, provider-reconciled deadline, cover-media digest, and real leaderboard score. Final paper text should add provider-linked ARC results while retaining the local ablations as explanatory evidence.

## Limitations

The theory depends on recurrence. A fully novel environment offers little opportunity for reuse. Skill preconditions can alias states that look similar but behave differently. Transition effects may drift, and deterministic signatures may miss semantically important changes. The synthetic experiment intentionally isolates the mechanism and is not evidence of ARC private-evaluation performance. SAGE’s landed source and any future Kaggle execution must be reviewed as separate generations; this paper cannot self-mint their authority.

## Reproducibility

The carrier pins exact upstream Commons commits, generates its mechanism results and figures from standard-library Python, validates the paper’s conservative word count, and emits a deterministic readiness receipt. The upstream solver owners retain source credit. Prize-facing claims require a public notebook and real Kaggle submission. All local/mock evidence remains separately labeled so a reproducible toy result cannot be mistaken for leaderboard evidence.
