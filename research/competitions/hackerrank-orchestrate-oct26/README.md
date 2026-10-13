# HackerRank Orchestrate October 2026 — submission edge

This directory contains challenge-agnostic helpers for the October 24, 2026 HackerRank Orchestrate event. It deliberately does not guess the challenge, dataset, or output schema before HackerRank releases them.

Official event page: https://www.hackerrank.com/hackerrank-orchestrate-october26

The event requires code, agent output, and an AI chat transcript, followed by a 30-minute AI-judge interview. The helpers here reduce avoidable submission failures without prescribing the agent architecture.

## submission_edge.py

Four small commands are provided:

- sanitize-transcript: removes records explicitly tagged visibility=private|internal|secret, redacts common credential fields and recognizable bearer/GitHub/OpenAI-style tokens, and emits stable JSONL. This is a safety assist, not a substitute for manual review of the final transcript.
- validate-output: validates CSV or JSONL row structure, required fields, duplicate/missing IDs, optional expected-ID coverage, and normalized deterministic equality against a second run.
- receipt: hashes exact deliverables and records explicit commit/model/wall-time metadata without dumping the ambient environment.
- defense: renders a one-page technical-defense note from the same receipt, plus explicit tradeoffs and known failure modes.

Example flow:

~~~bash
python submission_edge.py sanitize-transcript chat.jsonl chat.public.jsonl

python submission_edge.py validate-output output.csv \
  --id-field ticket_id --required action --required justification \
  --expected-ids expected_ids.txt --compare repeat_output.csv

python submission_edge.py receipt \
  --artifact output.csv --artifact agent.zip \
  --commit "$GIT_SHA" --model "$MODEL" --wall-seconds 812.4 \
  --metadata challenge=orchestrate-october26 \
  --output run-receipt.json

python submission_edge.py defense run-receipt.json \
  --architecture "Deterministic policy gates around model decisions." \
  --tradeoff "Prefer escalation on unresolved high-risk ambiguity." \
  --failure-mode "Retrieval can miss paraphrased evidence." \
  --output defense.md
~~~

## Focused check

From this directory:

~~~bash
python -m unittest -v test_submission_edge.py
~~~

The challenge-day output schema remains authoritative. Update invocation arguments, not this tool's semantics, once HackerRank releases the actual task.
