# CHI-Bench reliability triplet report

A small offline analyzer for repeated CHI-Bench runs. It consumes **three prepared packet directories per group**, aligns tasks, and reports reliability metrics across repeated attempts.

- empirical pass@1 across the three attempts;
- `pass_3`: fraction of tasks that pass on all three attempts;
- mixed/flaky and never-pass task sets;
- mean agent cost and wall time from `result.json` when present;
- mean tool-call count when `trajectory.jsonl.zst` can be decompressed;
- baseline to candidate all-three-pass improvements and regressions.

It reads only the published packet contract (`trials/*/*/result.json`, `verifier/reward.json`, and optional compressed trajectory files). It does not alter a submission.

## Usage

```bash
python reliability_report.py \
  --group baseline=/runs/base-a,/runs/base-b,/runs/base-c \
  --group candidate=/runs/cand-a,/runs/cand-b,/runs/cand-c \
  --json-out reliability.json
```

Each packet must contain the same task identities. A mismatched task set is a hard error rather than silently comparing different workloads.

Tool-call counting is optional: the script uses Python `zstandard` when installed, otherwise `zstdcat`/`zstd -dc` if available. When neither is available, `mean_tool_calls` remains `null`.

## Focused check

```bash
python reliability_report.py --self-test
python -m py_compile reliability_report.py
```
