# Results

Verdict: **PASS for the bounded source repair; no gameplay claim.**

- Authenticated packet: `F0C0JPCAAQP`, 27,500 bytes, SHA-256 `f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728`.
- Upstream integrator: SHA-256 `8e1093429a1bb463e2b82490963b43d9c9a4fcbd16f9d1b8d02fd75434f84436`.
- Historical predecessor archive: `F0C06QB6CFR`, 408,621 bytes, SHA-256 `6ac897241cb54baa205e4132fab1f83e7a21e4ae957e19e16c6c48a7ecbd8bc1`; deliberately treated only as a mismatched-base witness.
- Legacy result: raises on the late frozen anchor after changing exactly `titan_runtime.py` and `scheduler.py`.
- Repaired result on the same failure class: all five target bytes remain exact.
- Adversarial suite: 13/13 pass under `ResourceWarning`-as-error.
- Compile gate: pass for upstream copy, repaired source, and test source.

No exact `a055fd56…` build or game was claimed because the first Slack file named `titan-current.tar.gz` was the historical `6ac897…` archive, and provenance was not weakened to make it pass.
