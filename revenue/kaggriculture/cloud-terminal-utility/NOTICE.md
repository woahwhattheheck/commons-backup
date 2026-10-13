# Source and licensing

The new adapter, CLI, and fixture/test scripts in this directory are released
under Apache-2.0, as marked in each Python file.

Tests consume, without republishing or modifying:

* Kaggle's Apache-2.0 official interpreter at
  `Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`;
  source path `kaggle_environments/envs/kaggriculture/kaggriculture.py`,
  SHA-256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.
* Commons' Apache-2.0 T15 solver at
  `woahwhattheheck/commons@46332a6b2ed2e3b329cca62faf85d2482c23000f`,
  `revenue/kaggriculture/cloud-market-game-theory/solver.py`,
  Git blob `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3`,
  SHA-256 `65b394dcfb3de6177f7b5b27b1960dd92db1d8d33dcc04a5c673ce848c8dc404`.
* The existing Commons evaluator from retained artifact10005621438,
  `peer/evaluate.py`, SHA-256
  `cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e`.
  The evaluator compiles the unchanged upstream seed helper from the supplied
  cached utils.py. It is not replaced with an invented initializer.

The engine artifact was already published and was downloaded through the
existing artifact connector. No new engine export workflow was started. The T15
solver was read at its pinned GitHub revision. SciPy is used only as an optional
independent linear-programming test oracle; production imports only Python's
standard library. Full engine and dependency license notices remain in their
existing source locations.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
