# TurnBench — submission narrative

**One-line:** TurnBench is CI for real-time voice agents: it turns a minimized AssemblyAI Voice Agent event trace into a deterministic, content-addressed acceptance receipt so turn-taking regressions can block a release before users hear them.

## Problem
Voice-agent regressions are subtle and expensive to review by ear. Endpointing can drift, barge-in can stop cancelling audio, a tool can fire from the wrong witness phrase, or a configuration change can silently alter turn behavior. A demo may still “sound fine” while those contracts have already broken.

## Solution
TurnBench evaluates a scenario contract against a minimized event trace and produces a reproducible PASS/HOLD receipt. The landed evaluator checks resolved session configuration, response latency, semantic interruption behavior, required tool calls and arguments, forbidden provider errors, clean session termination, and exact source bytes.

## Why AssemblyAI matters
The product is designed around AssemblyAI Voice Agent events and behaviors, including session configuration, transcripts, tool calls and semantic interruptions. A browser-facing live demo must use AssemblyAI’s server-minted temporary-token flow so the API key never enters client code.

## Evidence and privacy boundary
The repository already ships synthetic fixtures and a no-secret static judge demo. Synthetic fixtures prove evaluator behavior only; they do **not** prove a live AssemblyAI session. Live-provider execution, hackathon registration, deployment and final submission remain separate evidence gates. Capture normalization intentionally drops credentials, session/resume tokens and raw audio while retaining only the trace fields required for deterministic evaluation.

## Differentiation
Most voice-agent demos optimize for a happy path. TurnBench makes failure behavior testable and reviewable. It treats latency, interruption semantics, tool-call witnesses and provider errors as release contracts and binds the result to exact inputs with a canonical SHA-256 receipt.

## Commercial wedge
After the event, the same machinery can become a paid voice-agent regression audit/pilot: a team supplies a small set of production-safe scenarios and sanitized traces; the deliverable is reproducible release gates, failing traces, and concrete fix targets. This narrative does not claim a customer, accepted price, payment or revenue.

## External-truth ceiling
This source packet does not claim registration, live provider execution, public deployment, hackathon submission, judging, rank, prize, payment or revenue. The readiness compiler can emit only `EXTERNAL_GATES_PENDING` or `READY_FOR_OWNER_SUBMISSION_ACTION`; it never emits `SUBMITTED`.
