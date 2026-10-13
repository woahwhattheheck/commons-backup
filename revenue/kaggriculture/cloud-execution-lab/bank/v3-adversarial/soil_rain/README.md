# Soil Remembers Rain V26-H independent whole agent

This directory vendors the Apache-2.0, standard-library-only V26-H policy as a
default-OFF independent candidate. The file is byte-identical to the resolved
Kaggle output. Production `main.py` neither imports nor embeds it, so the
current champion remains an independent hedge.

Reproduce the preregistered same-seed/both-seat screen and the opponent,
episode, seed, seat, and time-disjoint confirm with:

```bash
python3 scripts/measure_soil_remembers_rain.py
```

The confirm manifest is hashed before the screen. Confirm is opened only if
rank or mean margin improves without p20 regression. The script never submits
to Kaggle.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../../titanmcp.html). Cite Latch Pad KEEP.
