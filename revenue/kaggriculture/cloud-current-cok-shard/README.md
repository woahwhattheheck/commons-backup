# Current TITAN `87d7…` versus COK V10

This directory records a bounded, source-pinned development shard for the canonical
TITAN package that followed completed frozen-seller deadline recovery. It does not
change the agent, release pointer, evaluator, opponent, or provider state.

## Exact inputs

- Candidate: `revenue/kaggriculture/cloud-execution-lab/exports/titan-current.tar.gz`
  at PR10400 / merge `7b5fe42908e8ba936a32223b7145f7d8fe90dbfc`.
  Archive SHA-256 `87d7b8bf7c4e9467f4b6b46887abe2eb03735c42453cdbf4f2cac12c5962acc7`,
  292,007 bytes, 78 runtime files. Entrypoint `main.py::agent`.
- Candidate SOURCE manifest SHA-256
  `30f229d43bf4e6cbc8941fb91e5be4d521b5859c6c0f60bd626adda8009bba9f`.
- Opponent: exact public-bank `cok-v10.py::agent`, wrapper SHA-256
  `f2160afe24ee9a50ef3843d5d94b2f32c3af53620a43b6cbb25c0020c4cd903c`.
  Its retained upstream source is
  `COK-ZhangZiliang/Kaggriculture@7ef67eac458cd9ecd13786063e2e581fbe7403ec`,
  SHA-256 `56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109`.
  Existing public-bank licensing and third-party notices remain in their original
  owned path; no opponent source is copied here.
- Official engine: `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
- Evaluator SHA-256 `e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c`;
  loader SHA-256 `cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e`.
  Actor RPC deadline was 1 second, startup 10 seconds, game interval 120 seconds.

## Result

Development seeds `9969001` and `9969019` were checked against current repository
and Slack records before execution. Each ran both candidate seats with fresh
isolated actors.

| Seed | Candidate cash | COK cash | Margin | Seat relationship |
|---:|---:|---:|---:|---|
| 9969001 | 91,348 | 72,316 | +19,032 | exact mirror |
| 9969019 | 140,100 | 127,068 | +13,032 | exact mirror |

All four game rows completed 719 decisions: **4W / 0T / 0L**, zero candidate or
opponent failures. The rows comprise **two independent environment seeds**, not
four independent samples; each seed's two seat records are exact cash mirrors.
Mean candidate cash is 115,724, mean rival cash 99,692, and mean margin +16,032.
Across 2,876 candidate calls, maximum child call was 73.746 ms and maximum
parent-observed RPC was 75.514 ms. Maximum startup was 510.736 ms and maximum
candidate peak RSS was 104,152 KiB.

This is absolute current-package-versus-COK evidence. No ancestor package or
control was rerun, so it makes no paired improvement claim. It is not held
validation, a population win-rate estimate, a hosted Kaggle result, or a
leaderboard prediction. COK V10 is one public opponent family. Root retains the
separate authorized upload operation; this shard performs no Kaggle write.

## Reproduce the result record

The raw reports and concise evaluator logs are retained losslessly. From this
directory:

```sh
python verify_results.py
```

The verifier checks every input identity, score, trace digest, 719-call count,
mirrored-seat relation, aggregate, and retained file hash. It does not execute
new games or import the candidate/opponent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
