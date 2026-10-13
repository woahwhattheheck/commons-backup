# SAGE experiment plan — ARC-AGI-3 2026

## Objective

Maximize hidden-game completion with fewer real actions by turning interaction into reusable causal evidence rather than repeatedly prompting a model from raw screenshots.

## Hypotheses

### H1 — Full animation access materially improves state inference
Compare settled-frame-only versus all-frame observation on public games that return multiple frames. Hold policy/model constant. Primary outcome: game score/actions; secondary: incorrect effect-cluster rate.

### H2 — Information-gain probing beats uniform/random probing
For each public game, start from a clean scorecard and compare equal real-action budgets. SAGE selects untried/high-entropy state-changing actions; baseline samples valid actions uniformly. Record no-effect action rate and time to first progress.

### H3 — Generalized skill replay improves later levels
Learn only from prior levels in the same game. Replay is allowed only when `ScenePrecondition` matches and empirical support/confidence exceeds threshold. Compare against knowledge-reset between levels. Any public-game tuning must preserve a held-out game split.

### H4 — Coordinate candidate reduction improves ACTION6 efficiency
Compare all-grid/random clicks against object-centroid/bbox/corner candidates under the same click budget. Report candidate count and real clicks separately.

## Anti-overfit protocol

- Never hard-code public game IDs, board coordinates, action semantics or winning sequences into production policy.
- Store game IDs only in experiment manifests.
- Separate public development games from held-out public validation games.
- Require a code-reviewable reason for every game-specific adapter exception.
- Re-run with action semantics permuted in mocks.
- Preserve exact trace receipts so apparent improvements can be replayed/audited.

## Milestone 2 release gate

A candidate notebook is not called competition-ready until:

1. one-command clean offline run works with internet disabled;
2. exact source revision is public/open-source eligible;
3. official toolkit action-space changes and animation frames are retained;
4. runtime/memory fit inside Kaggle limits with margin;
5. benchmark manifest separates mock, public-development and public-validation evidence;
6. no credentials/secrets are embedded;
7. notebook does not contact external APIs;
8. no claimed score exceeds provider/Kaggle evidence actually observed.

The gate intentionally does not authorize Kaggle rule acceptance or submission.
