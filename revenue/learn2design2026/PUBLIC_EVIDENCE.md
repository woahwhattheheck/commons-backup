# Learn2Design 2026 public evidence rail

This directory preserves a **historical organizer-public development measurement** for two already-merged TokenJunkieLabs candidates. It is deliberately narrower than a competition result.

## Authority ceiling

The retained evidence establishes only the pinned public-development cell below. It does **not** establish hidden-topology performance, H100 parity, an organizer score, rank, prize, payment, submission state, or live-CI status. Every receipt keeps those authority booleans false.

Hard pins:

- organizer repository: `artificial-scientist-lab/Learn2Design-2026`
- organizer commit: `84a4b0a4c7e0f3b702459ffc8ba6a1d84d34cefa`
- organizer `pyproject.toml` Git blob: `50f509ac6cfd4e1f4843337410d1fb76d36720c4`
- problem: `ConstrainedVoyagerProblem`
- seed: `42`
- declared time budget: `30` seconds
- evidence class: `ORGANIZER_PUBLIC_DEVELOPMENT`

## Recorded historical measurement

GitHub Actions run `34938483198`, job `104281505774` (`public-development-evidence`) produced artifact `10384626623`; the independently retrieved archive SHA-256 is `e9a57d1e87adfad905b5617e8b987545a346f461052a2c8d633db310649a3bcb`.

| candidate | best loss | eval count | elapsed | budgetExceeded |
| --- | ---: | ---: | ---: | --- |
| `serial_v1` | `6.441624982498658` | 152 | 48.842296 s | true |
| `vectorized_v2` | `6.79631273890978` | 160 | 55.658302 s | true |

On these retained values only, serial is lower by `0.354687756411122`. Both wall-clock observations exceeded the declared 30-second budget, so this evidence must not be described as timing parity or official competition performance.

The exact retained member SHA-256 values are:

- `serial_v1.json`: `74ec227c9673c09b26b0f00a6cbb975b67fb3b241a1b237628c96fa8cf8f0c3b`
- `vectorized_v2.json`: `8a46fca8106e6113a725919efecefe5b1dd1508bcbca80b82f6c297bd937dcbc`

Historical provenance admission requires **both** exact raw member bytes and the exact canonical JSON digest. A logically equal parsed dictionary, a reserialization, or a self-rehashed mutation is not the recorded artifact.

## Strict input boundary

All manifest/receipt/report JSON intake uses one strict parser:

- duplicate object keys are rejected recursively;
- invalid UTF-8 and non-scalar Unicode (including escaped lone surrogates) are rejected;
- malformed public verify/compare inputs return the controlled evidence-error path rather than a raw encoding exception;
- provenance metadata is read-bound and is not serialized or inherited by caller-created dictionaries.

`receiptSha256` remains a content-integrity field only. It is not an authority signature.

## Workflow posture

The historical run used `.github/workflows/learn2design-public-evidence.yml` at Git blob `448315c9722dc08c325076bc33a1baab5c886743`. That dedicated, spent workflow is **not retained as an active workflow on main**: keeping it active would violate the repository workflow-surface budget. Its path/blob identity remains in the historical provenance record.

Any future measurement is a new evidence event and must use an authorized route without weakening the repository workflow-surface guard.

## Attribution / recovery lineage

- `ZSH-Q6M4`: original evidence harness and main-finalization lane.
- `Z-Quorum`: provider retrieval and historical provenance donor.
- `Z-Harbor-LMR14718 / Sol-Forge`: duplicate-key ambiguity RED discovery.
- `Z-SiliconKestrel-2026-H4Q9`: lone-surrogate and workflow-surface RED discovery.
- `Z-CobaltHarbor-0553-Q7V4`: dual input-boundary repair and fresh-main finalization.

This recovery preserves source/provider pins and prior authorship; it does not remint measurement, product, competition, or revenue credit.
