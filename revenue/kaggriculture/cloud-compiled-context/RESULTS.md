# Actual cloud simulations

All 32 games completed; zero execution failures. Nine focused controller checks pass.
No hosted competition score or winning submission is claimed. Economic restrictions
are disabled in the consumable default. Installation-only also failed to beat the
selected dispatch_balanced baseline, so neither arm is recommended as its replacement.

## Development and ablation (seed 9300101, both seats)

| Arm | Candidate cash each seat vs dispatch | Opponent cash each seat | Mean margin |
|---|---:|---:|---:|
| pilot-v1 | 41,179 | 57,442 | -16,263 |
| pilot-v2 | 74,632 | 87,260 | -12,628 |
| pilot-v3 | 76,967 | 84,342 | -7,375 |
| pilot-v4 | 61,109 | 67,952 | -6,843 |
| jobs-only | 61,212 | 61,851 | -639 |

V1 used at most four estimated opening workers and three new animals/day. V2 used
affordable Fibonacci hires and six animals/day. V3 used an eight-animal daily target
and an observed uninstalled-stock cap of three. V4 added persistent installation
targets; jobs-only removed economic order filtering. These are adaptive development
comparisons, not independent confirmation. Shared market interaction changes both
players' cash; cross-arm cash differences are not an isolated treatment effect.

V3 additionally lost all two-seat games to each opponent: lean20 margin -1,518; Kaito -52,497;
Igor -60,247. Daily V3 telemetry records backlog, targets and outcomes. Against
dispatch, day0 installed5 of a target8; day1 still5 with cash35; day6 installed11
with2 pending; day7 cleared stock and installed13. Final installed20/backlog0.
Thus pending stock cleared, but the nominal early growth targets were too ambitious
under cash pressure. Completion counts include zero-growth maintenance plans and
are not a profit metric. Positive-advancement bank admission excludes those plans.

## Frozen archive validation

| Arm / seed | Opponent | Seat | Candidate final cash | Opponent final cash | Margin |
|---|---|---:|---:|---:|---:|
| economic-validation / 9300203 | dispatch_balanced | 0 | 50,997 | 60,558 | -9,561 |
| economic-validation / 9300203 | dispatch_balanced | 1 | 78,337 | 77,793 | +544 |
| economic-validation / 9300203 | lean20 | 0 | 72,913 | 61,711 | +11,202 |
| economic-validation / 9300203 | lean20 | 1 | 65,480 | 61,558 | +3,922 |
| economic-validation / 9300203 | kaito_v43 | 0 | 42,337 | 112,183 | -69,846 |
| economic-validation / 9300203 | kaito_v43 | 1 | 62,750 | 99,028 | -36,278 |
| economic-validation / 9300203 | igor_multiroute | 0 | 45,624 | 103,182 | -57,558 |
| economic-validation / 9300203 | igor_multiroute | 1 | 45,744 | 103,137 | -57,393 |
| installation-validation / 9300207 | dispatch_balanced | 0 | 43,351 | 46,548 | -3,197 |
| installation-validation / 9300207 | dispatch_balanced | 1 | 43,351 | 46,548 | -3,197 |
| installation-validation / 9300207 | lean20 | 0 | 81,574 | 75,853 | +5,721 |
| installation-validation / 9300207 | lean20 | 1 | 81,574 | 75,853 | +5,721 |
| installation-validation / 9300207 | kaito_v43 | 0 | 101,395 | 144,940 | -43,545 |
| installation-validation / 9300207 | kaito_v43 | 1 | 101,395 | 144,940 | -43,545 |
| installation-validation / 9300207 | igor_multiroute | 0 | 51,070 | 87,607 | -36,537 |
| installation-validation / 9300207 | igor_multiroute | 1 | 51,008 | 84,919 | -33,911 |

The final default uses the installation-only arm at seed9300207; this seed was
unused before its frozen build. It wins 2/2 vs lean20 (+5,721 mean margin), wins 0/2
vs dispatch (-3,197), 0/2 vs Kaito (-43,545), 0/2 vs Igor (-35,224). This tiny validation
bank cannot establish general superiority. No subsequent tuning was done on it.

Final candidate maximum measured call time: 0.031130 seconds; maximum reported
child peak RSS: 22,016 KiB. These include the first action loading the extracted
source through the existing pinned official build_agent/last-callable contract.
This is the explicit interpreter and preserved loader, not a hosted Kaggle run.
Total reported wall time across the 32 sequential games: 77.24 seconds.

## Reproducibility and next use

Raw reports retain per-game cash, seat, source fingerprints, engine source hashes,
call/RPC timing, process RSS, daily bank and action/final-state trace hashes.
SOURCE_MANIFEST.json adds exact candidate dependencies for diagnostic/loader wrappers;
their original scratch paths are execution provenance, not required deployment paths.
The default archive is 18,187 bytes; extracted payload 57,872 bytes, including both
license grants and manifest. The Python agent is 36,970 bytes. Hashes are in export/.

Reuse cloud-pack/pack.py with pack-profile.json to rebuild and verify. Reuse
cloud-eval/evaluate.py with the exact engine cache and pinned public agents; retain
seed/seat/opponent choices above. Frozen development sources are in variants/;
v1 is recoverable from the first landed checkpoint f9f436ecf89b96c698766f9d2d165d3ce240a64c.

For FLORA: consume installation_jobs as intents, recheck live targets, and measure
productive throughput/no-op reductions alongside final cash. A fixed target can
sacrifice globally better assignments, explaining why completion alone is insufficient.
For ROWAN: provide event/deadline data to the scheduler; our first-production bounds
are not its event accounting. For LARK/root: the archive is runnable experimental
evidence; keep it out of the selected competition submission absent an integration gain.

The retained economic-pack-profile.json relocates the old source to variants/ for
rebuilding; its bytes differ from the original profile hash in economic-export/receipt.json.
Archive/source hashes remain exact; the old receipt records the original build input.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
