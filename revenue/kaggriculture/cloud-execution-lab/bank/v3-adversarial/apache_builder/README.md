# Apache Agent Builder clean-room whole-agent

This is a standalone, standard-library-only candidate inspired by the public prose and aggregate
farm trajectory in Version 19 of kaggriculture-agent-builder. It deliberately excludes the
notebook's public-replay action tape. The complete foundation is vendored in agent.py; inference
needs only agent(obs), no network, replay file, weight, environment variable, or credential.

The candidate is default-off and does not modify main.py or submission.tar.gz. Reproduce the
same-seed/both-seat screen and the opponent/episode/seed/seat/time-disjoint confirm with:

    python3 scripts/measure_apache_agent_builder.py

The measurement performs no Kaggle submission. A failed screen is a measured rejection and skips
confirm; an evidence or contract failure is inconclusive.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
