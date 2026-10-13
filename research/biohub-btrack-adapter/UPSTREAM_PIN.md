# Upstream pin and audited seams

Audited target: `quantumjot/btrack` v0.7.0, exact tag commit `a3bd947915efe6837936f9db6db88417f0b51b45`, MIT.

Exact source identities used by this adapter review:

- `btrack/core.py` blob `85cc34824b54c25726e611f44f31d3bb7ef1d1a7`: `BayesianTracker` owns one native engine and accumulated object list; `append()` accepts localization collections; tracker volume is BTrack `(x,y,z)` geometry.
- `btrack/io/utils.py` blob `95f4ff8df06c34c3d0649c94b8b6c6de874671ac`: `localizations_to_objects()` overwrites localization `ID` with `np.arange(n_objects)` and preserves extra keys as `PyTrackObject.properties`.
- `btrack/btypes.py` blob `f4cdeeb27afdc56786ff1433e18dd1849e157334`: `Tracklet.refs` is the live list of contained object IDs; Tracklets expose parent/children and aligned `t/x/y/z/dummy` observation arrays; extra object properties are preserved.
- `btrack/io/hdf.py` blob `20cdd6ec7ecfef95a3775ff0b39af4ef99cba26f`: list-mode track writing renumbers supplied real/dummy objects in place before recomputing refs. Conversion therefore precedes any such serialization.
- `btrack/src/hypothesis.cc` blob `0fdb11586b7ec2e287d30a3330384382aa742f85`: hypothesis generation operates on the shared tracklet state and has no Commons dataset namespace, motivating one engine per dataset.

Additional routed runtime boundary: BTrack's optimiser imports `cvxopt.glpk.ilp`. A successful `import btrack` is not sufficient evidence that optimizer-backed division inference is runnable offline. The dependency owner must separately prove native BTrack construction and a tiny GLPK-reaching optimisation smoke in the target ABI.

This pin is source evidence only; it is not a claim that the target Kaggle runtime, native shared library, GLPK backend, competition entry, or scored submission has been verified.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

