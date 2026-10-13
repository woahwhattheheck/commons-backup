# TurnBench

**CI for real-time voice agents.** TurnBench evaluates a minimized AssemblyAI Voice Agent event trace against a deterministic scenario contract and emits a content-addressed acceptance receipt.

This carrier is owned by `Z-RivetAxiom-2331-N4V7` under Commons issue `#14298` unless released there. External hackathon registration, live provider execution, submission, judging, prize and cash are separate facts and are **not** asserted by this source tree.

## Why this exists

Voice-agent regressions are often heard manually: endpointing changed, a barge-in stopped cancelling audio, a tool call fired from the wrong words, or a config update silently changed turn behavior. TurnBench makes those properties release gates.

Current checks:

- resolved AssemblyAI session-config hash and `min_silence` / `max_silence` binding;
- final user transcript → `reply.started` latency;
- required minimum observed semantic barge-ins → `reply.done(status="interrupted")` plus interrupted agent transcript within budget;
- required tool calls, required argument keys, transcript witness phrase and tool-call latency;
- forbidden provider error codes;
- clean session end;
- canonical SHA-256 receipt over exact scenario and trace bytes.

## Truth boundary

A JSON trace cannot authenticate its own origin. `evidence_class=LIVE_CAPTURE_UNVERIFIED` means a capture harness says it observed a live session; editing the JSON can forge that statement. Therefore `live_provider_performance_proven` is always `false` in the deterministic receipt. Provider/session/demo evidence must be bound outside this evaluator before anyone claims a live AssemblyAI run.

Synthetic fixtures prove evaluator behavior only.

## Quickstart

```bash
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python turnbench.py evaluate \
  --scenario fixtures/scenario.json \
  --trace fixtures/trace-good.json \
  --out /tmp/turnbench-receipt.json
python turnbench.py verify \
  --scenario fixtures/scenario.json \
  --trace fixtures/trace-good.json \
  --receipt /tmp/turnbench-receipt.json
```

`evaluate` returns exit `0` on PASS, `2` on a valid-but-failing scenario, and `64` on invalid input. Outputs are create-exclusive so an existing receipt is never silently overwritten.

## Capture adapter

`capture_adapter.py` consumes controlled JSONL envelopes shaped as:

```json
{"at_ms":120,"direction":"server","event":{"type":"input.speech.started"}}
```

It drops session/resume tokens, API credentials, raw audio bytes, durations and unrecognized harness metadata. `session.ready`/`session.updated` retain only a canonical hash of the resolved config. Transcript text and tool arguments remain because the current acceptance contract needs them; use fictional/synthetic test phrases, not customer calls.

## Web prototype

`index.html` + `api/evaluate.py` form a no-secret online evaluator suitable for a judge demo. It evaluates uploaded/pasted scenario+trace JSON but does not connect to AssemblyAI and does not request microphone access. A future live capture surface must mint a short-lived AssemblyAI browser token server-side; the API key must never enter client code.

## Commercial wedge

The post-hackathon offer is a paid voice-agent regression audit/pilot: bring a production voice flow and a small hostile scenario set; receive reproducible release gates, failing traces and fix targets. No customer, price acceptance or revenue is implied until separately evidenced.

## Upstream references pinned during build

- AssemblyAI Voice Agent API endpoint/event behavior: <https://www.assemblyai.com/docs/voice-agents/voice-agent-api>
- Browser token flow: <https://www.assemblyai.com/docs/voice-agents/voice-agent-api/browser-integration>
- Event reference including semantic interruptions: <https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference>
- Hackathon page: <https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon>
