# openKylin competition milestone receipt

## Task fit

KylinMemBench targets the openKylin challenge's six stated long-term-memory capabilities and its requirement to organize dialogue, memory, action and file evidence into an automated, explainable, reproducible benchmark.

## Current evidence

- Source is dependency-free Python 3 and requires no provider credentials.
- `python3 -B -m unittest discover -s tests -v` is the acceptance command.
- The bundled dataset covers every required dimension exactly once for a compact smoke benchmark.
- The reference fixture scores 100/100; the intentionally forgetful fixture scores below 50 and produces explicit failed-assertion reasons.
- `compare` emits per-agent JSON/Markdown plus a radar SVG.

## Submission boundary

This repository milestone is code/test/sample evidence only. It is **not** a claim of registration, organizer submission, openKylin desktop execution, two real-agent execution, finalist status, award, or payment. Those require separate external/environment actions and receipts.
