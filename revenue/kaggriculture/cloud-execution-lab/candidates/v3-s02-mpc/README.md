# TITAN V3 S02 receding-horizon planner

Wraps the unchanged canonical TITAN agent (`canonical_main.py`, same bytes as archive `main.py`).
Planner lives in `planner_mpc.py`. Disable with `TITAN_MPC=0`. Horizon `TITAN_MPC_H` (6/12/24). Budget `TITAN_MPC_BUDGET` default 0.6s.

Unpack `exports/titan-current.tar.gz` (SHA256 f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c) beside these files so `titan_runtime.py` and siblings resolve. Do not replace the archive here; Bryce promotes it.

Gauntlet: `tools/v25_sims/gauntlet.py --candidate <this>/main.py`.
