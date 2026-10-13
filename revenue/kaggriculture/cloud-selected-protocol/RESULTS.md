# Selected-package replay results

**Passed: 2,876 sequential decisions, zero mismatches.** The selected standalone
archive, independently packaged frozen SELL, and original development action
labels matched on all four retained trajectories (719 decisions each). Eight
fresh actor processes made 5,752 policy calls. All 53 extracted runtime files
remained byte-identical after replay. No new game or held-observation evaluation
was performed. This is package/interface evidence, not additional W/T/L evidence.

## Measured execution

Python 3.12.3 on Linux 6.17.0-1022-azure, x86_64, glibc 2.39.
Function time and process/pipe overhead are separate. These are measured cloud
runner timings, not Kaggle timings or universal upper bounds.

| Existing development stream | Decisions | Differences | Max selected function (ms) | Max selected RPC (ms) | Startup + first selected RPC (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| candidate-apex-9600803-seat0.jsonl.gz | 719 | 0 | 24.859 | 26.162 | 75.460 |
| candidate-apex-9600803-seat1.jsonl.gz | 719 | 0 | 25.351 | 26.390 | 76.491 |
| candidate-arlene-9600803-seat0.jsonl.gz | 719 | 0 | 26.382 | 27.772 | 76.157 |
| candidate-arlene-9600803-seat1.jsonl.gz | 719 | 0 | 26.577 | 27.982 | 76.064 |

The complete run took 27.730 seconds. Fifteen local protocol regression tests
also passed; the same fifteen passed in the hosted job. The run did not install
packages, invoke the game engine, modify any policy, or upload to Kaggle. Python
import/socket canaries are dependency diagnostics, not an OS security sandbox.

## Durable evidence and exact provider receipt

[`RESULTS.json`](RESULTS.json) is the byte-for-byte original `REPORT.json` from
run 34156732280, attempt 1: 16,436 bytes, SHA-256
`c06e6b7f4e19b023316703c443c8631ecabe675c9f1aa2fe79d7c4a153859e97`.
It contains all four action digests, actor readiness/configuration, timings,
archive pins and the 53-file runtime manifest. It is not regenerated evidence.

- Source PR: [9909](https://github.com/woahwhattheheck/commons/pull/9909), merged as `14c76eae63f2033bbee6e7af2945dd65ea243e9b`.
- Actual run: [34156732280](https://github.com/woahwhattheheck/commons/actions/runs/34156732280), replay job `101850007324`, success.
- Verifier source head: `3eaa5ae74507cc4ce5fe36a2992750c9cfdc692b`; tested PR merge checkout: `9949e0d6dd9f3f1542f3c7e0a7d4baf286fa2ab3`.
- Verifier SHA-256: `21fc06d5dbd107475625e254dee50b0d07dc89e658c794c9b53ec25cc02ffc41`.
- Policy/source input pin: `c533e7ce210dbe77e078e566a71b15b175db0da9`; this does not move with main.

## Reuse without another export job

The completed artifact is `10031224878`, named
`titan-selected-protocol-34156732280-1`. ZIP size: 1,035,914 bytes.
GitHub and the downloaded local ZIP agree on SHA-256
`99867808e5f799f8fffe12f017eaca99705d0690af7ff3178d5c7c570c569a3f`.
The provider reports expiry on September 14, 2026; the source, report and pinned
preparation recipe remain in Git. The completed report was inspected locally
and all bundled input pins were checked; no duplicate local replay was run.

Connected cloud consumers can use:
```python
GitHub.download_workflow_artifact(
    repo_full_name="woahwhattheheck/commons",
    artifact_id=10031224878,
    file_name="titan-selected-protocol.zip",
)
```

After digest validation and safe extraction, `inputs/selected.tar.gz` is the
exact 181,166-byte selected archive, SHA-256
`5d3a2bf3878808679820ff7f5a5ca7533c41888366c5dcd358f15ff0213f1f10`.
Extract it into a fresh directory and use `main.py::agent(obs,configuration)`
with one actor per match. Keep the existing frozen control and notices intact.
No competition upload is authorized by this receipt.

The bundle also retains the 59,966-byte independent SELL source archive, four
development-only traces, pinned public configuration and `RUN.json`. The
verifier can consume `inputs/` offline; no repository checkout or installed
Kaggle package is needed for that replay. The published selected-package claim
is bounded to these traces and bytes, not a guarantee about all future states.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
