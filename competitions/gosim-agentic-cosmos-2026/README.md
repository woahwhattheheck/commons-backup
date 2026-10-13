# GOSIM Agentic Cosmos 2026 — causal observer foundation

This is a **pre-registration / pre-organizer-schema foundation**, not an official competition submission. The live GOSIM index describes Agentic Cosmos as a digital observer that weighs scientific and operational trade-offs and chooses a next observation every 900 seconds. The organizer's eventual simulator/data/API contract must replace the generic adapter fields here rather than being guessed.

## What is implemented

`observer.py` defines a strict causal snapshot and deterministic horizon planner. Every decision tick is exactly 900 seconds. Candidate data is split into **NOW** values and explicitly labelled **FORECAST** rows. There is no field for future realized weather or future realized science yield; unknown keys fail closed. The planner uses current availability, expected science, visibility, weather-success forecast, observation/switch budget, revisit age, target/tag diversity, and a bounded deterministic beam search.

Each decision receipt binds the exact snapshot, candidate set, policy and selected schedule by SHA-256 and states that it is not an official score or submission. `verify_decision()` recompiles the decision from the same inputs.

`replay.py` deliberately separates what the agent may see from realized outcomes. Realized success/yield is provided to the evaluator only **after** the action is selected. This prevents a replay harness from silently leaking future truth into the policy. The report is labelled `foundation_evaluation_only` and never claims organizer scoring.

## Organizer integration gate

When GOSIM releases the actual environment, add one adapter that maps organizer observations into this causal snapshot. Before trusting it:

1. prove organizer time steps map to the documented 900-second tick or revise this contract with source evidence;
2. classify every field as current observation, explicit forecast, durable past result, or prohibited future realized outcome;
3. map exact cost/resource units instead of assuming the generic integer budget units here;
4. map real target/visibility/weather/science features without inventing astronomy or telescope physics;
5. add organizer-fixture regression tests and compare baseline policies in the official sandbox;
6. only then tune weights/horizon and create a submission package.

No registration, terms acceptance, private data/simulator access, external submission, final attendance/travel, compute purchase/spend, official score/rank, prize/award/payment, or revenue is represented by this source.
