# KylinMemBench

A dependency-free, reproducible baseline for the **2026 Shanghai Open Source Application Innovation Competition / openKylin agent long-term-memory benchmark** task.

The sponsor asks for an automated benchmark on openKylin that can compare multiple agents using dialogue, memory records, action traces and files; cover long-term retention, recall, dynamic update, similar-item discrimination, boundary recognition and task reuse; provide explainable automated scoring, sample data/results, and a one-command CLI. KylinMemBench implements that offline scoring/evidence core without sending any evidence to hosted model APIs.

## What is in this milestone

- Six mandatory memory dimensions, enforced by dataset validation.
- Four evidence channels: `dialogue`, `memory`, `actions`, `files`.
- Explainable deterministic assertion types: `contains`, `not_contains`, `latest_equals`, `ordered_contains`.
- Strict schema validation: duplicate scenario records, unknown channels, malformed weights, unsupported dimensions/assertions fail closed.
- SHA-256 input provenance in reports.
- JSON + Markdown per-agent reports and a dependency-free SVG radar comparison.
- Two sample evidence bundles that make the score contrast visible without pretending they are real KylinBot/Hermes runs.
- Stdlib-only Python: no network access and no third-party package is required.

## Quick start

```bash
cd revenue/openkylin-memory-benchmark
python3 -B -m unittest discover -s tests -v
python3 -B kylin_memory_bench.py validate \
  --dataset sample/dataset.jsonl \
  --evidence sample/reference-agent.json \
  --evidence sample/forgetful-agent.json
python3 -B kylin_memory_bench.py compare \
  --dataset sample/dataset.jsonl \
  --evidence sample/reference-agent.json \
  --evidence sample/forgetful-agent.json \
  --out-dir build/demo
```

Expected comparison: `reference-agent` scores 100; the intentionally defective `forgetful-agent` scores below 50. `build/demo/radar.svg` is a portable radar chart suitable for report/video capture.

## Evidence adapter contract

An agent adapter emits one JSON bundle:

```json
{
  "agent": "agent-name",
  "records": [
    {
      "scenario_id": "retention.editor-preference",
      "channels": {
        "dialogue": ["..."],
        "memory": ["..."],
        "actions": ["..."],
        "files": ["..."]
      }
    }
  ]
}
```

This is deliberately framework-neutral. A KylinBot, kylin-agent, OpenClaw, Hermes Agent, or custom adapter only needs to map its native trace/export into these four channels. The benchmark scorer never needs the agent's credentials or network access.

## Dataset contract

The dataset is JSONL, one scenario per line. Every scenario chooses one of the six sponsor dimensions and declares weighted assertions. Example:

```json
{"id":"update.timezone","dimension":"dynamic_update","assertions":[
  {"type":"latest_equals","channel":"memory","value":"timezone=America/Kentucky/Louisville"},
  {"type":"not_contains","channel":"dialogue","value":"using timezone=America/New_York"}
]}
```

The baseline is intentionally deterministic. Future semantic judges can be added as a separate scorer while keeping this literal scorer as a reproducible anchor and audit trail.

## What is *not* claimed yet

This cloud seat is not an openKylin desktop and did not run KylinBot/kylin-agent/OpenClaw/Hermes. The two included bundles are synthetic fixtures for the scorer only. A submission-quality follow-up still needs a real openKylin x86 environment, at least two actual agent adapters/runs, a 3–5 minute desktop recording, and the organizer registration/submission steps. Those should be receipted separately rather than relabeled as completed here.

## Sponsor-aligned next milestones

1. Add two real openKylin agent adapters and capture immutable raw evidence bundles.
2. Expand the scenario bank with conflict updates, near-neighbor interference and sensitive-memory boundaries.
3. Package the stdlib CLI as a `.deb` for one-command installation.
4. Run repeat trials to quantify variance and add stability/confidence summaries.
5. Record the required openKylin desktop comparison video and assemble the submission document.
