# Local density-rank candidate for Mapping Equity

This original generator produces one regional candidate CSV plus its density audit from locally supplied challenge files. It is an uncalibrated baseline, not a reconstruction of organizer references or a measured coverage/equity result. No data has been downloaded or processed for this publication. Python, DuckDB and the SQL have not been executed or syntax-checked by a runtime.

## Current source contract

As read on 2026-10-06, the official challenge permits supplied inputs for scored predictions and prohibits removed reference layers or equivalent copies. The sample defines scored membership and GEOID must remain text. Extra datasets belong only to the separate discovery writeup. This package performs no account, team, terms-acceptance or submission action. [Official rules and scope](https://zindi.world/competitions/bias-bounty-mapping-equity-challenge).

The organizer README names the regional files below, pins Overture 2026-08-19.0 and documents OGC:CRS84 coordinates. Its September 25 notice removes TIGER road, Microsoft building, HIFLD and CBP references. [Organizer data documentation](https://source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge).

The code consumes the existing [Lane A contract](../README.md) without changing its [validator](../validate_contract.py). Its source was read at Commons merge 4aeaf2e44e45e98cfe1475c17c0a1abaeb3c0ba0, README f8f661ca1408edd35322897baf31b6be1a962ba1 and validator b6f3542a4b046798e31f80a6b7ca6c53d5170e18. Existing validation outcomes were not rerun.

**Do not use the older reference-reconstruction pipeline as this generator's dependency.** The separate directory competitions/zindi-mapping-equity documents TIGER/Microsoft/HIFLD/CBP ratios in its README 1d23b774dcc8d6f0caebb3fcbc37c46902da62a8 at that same merge. Those inputs conflict with the current scored-data rule. No code, tests or results from that older implementation were acquired, altered or replayed here.

## Exactly five local inputs per region

The accepted region values are eastern-ok (1,192 sample rows), maricopa-az (1,593), northern-ca (591) and south-central-tx (6,003). The dated row counts are deliberate drift checks; a changed official sample requires an explicit source update. There is no eastern-wa mode.

| Role | Path below data root | Columns consumed |
|---|---|---|
| Membership | reference/REGION/REGION-sample-submission.csv | GEOID only |
| Tracts | strata/REGION/REGION-census-tracts.parquet | GEOID, geometry |
| Buildings | reference/REGION/REGION-overture-buildings.parquet | geometry |
| Roads | reference/REGION/REGION-overture-roads.parquet | geometry |
| POIs | reference/REGION/REGION-overture-pois.parquet | geometry |

The geometry column must be read as DuckDB GEOMETRY. Tract GEOID must already be VARCHAR; the program never repairs numeric IDs by guessing zero padding. Building shapes must be polygon/multipolygon, roads line/multiline, and POIs point. Missing columns or incompatible types stop the run. These are documentation-bound expected schemas, not a claim that this publication inspected the actual data rows.

The CSV reader uses only GEOID. Sample score/component cells are ignored and never become features. ACS, demographics, confidence values, vulnerability labels and organizer reference scores are not inputs to this implementation. Thus absent confidence or strata values are not converted to zero.

## Provenance manifest

Before a future authorized local run, the caller supplies a UTF-8 JSON object with these fields:

- region: one accepted slug.
- overture_release: exactly 2026-08-19.0.
- crs: exactly OGC:CRS84.
- files: an object keyed by exactly the five relative paths above. Each value has sha256 (64 lowercase hex digits), source_url (the exact corresponding https://data.source.coop/humane-intelligence/bias-bounty-mapping-equity-challenge/ URL), and retrieved_at (the actual nonempty retrieval date/time).

There are no example hashes or invented data rows in this package. Populate the manifest from an actual acquisition receipt. The generator hashes the local files and compares them with the supplied pins before doing spatial work. It checks them again before emitting outputs and also checks that the manifest bytes did not change.

These checks detect ordinary byte drift. A caller-written URL, date, CRS or release label is not independent organizer authentication and cannot prove a file's origin, completeness or release. Use an immutable local input snapshot; the before/after hashes do not make concurrent writes safe. Paths resolve inside the data root and cannot contain Parquet glob metacharacters. No arbitrary feature-source or remote URL argument is exposed.

## Algorithm and boundary conventions

1. Load the official sample IDs in their original order. Reject non-ASCII/non-11-digit IDs, duplicates, malformed CSV rows or a changed row count. Only these IDs participate in ranking.
2. Match every scored ID to exactly one supplied tract row. Any missing or duplicate scored geometry stops the run; an absent polygon never becomes a zero-density tract. Additional unscored tract rows are excluded and counted in the run receipt.
3. Reject null, empty, invalid or wrong-type geometry and nonfinite envelopes. Before projection, check longitude/latitude envelope bounds. Convert from the declared OGC:CRS84 to EPSG:5070 with always_xy=true. Reject nonfinite transformed envelopes and nonpositive tract area.
4. Represent a building row by a point on its projected surface. Use the POI point directly. If multiple scored polygons cover that point, assign the input row once to the smallest lexical GEOID. Because all IDs are fixed-width digits, that tie rule is explicit and stable. Count ties and unassigned input rows in the receipt. Each input row is an observation; this method does not merge potentially duplicated source entities.
5. Intersect each projected road row with each intersected scored tract and sum projected lengths in ascending numeric length order, with one DuckDB thread. This sum order does not depend on the temporary input-row identifiers. A road exactly along a shared boundary contributes to both tracts. This is a per-tract intersection-density convention, not a conserved regional road inventory. Zero-length touches contribute zero. Nonfinite, null or negative lengths stop the run.
6. Divide the three observed quantities by projected square kilometres. For a valid tract, no assigned feature rows is a measured zero under this attribution rule. It is not the fallback for a missing polygon, failed input read, invalid feature, or empty layer. An entirely empty input feature layer stops the run.
7. Within the selected region, rank each density family from low to high. For n tracts, if a value has l strictly lower values and k equal values, its rank deficit is 1 - (l + (k-1)/2)/(n-1). Average the three deficits with equal weights.

The formula stays in [0,1] because its midrank lies between 0 and n-1. Tied values receive identical deficits. A constant family, including an entirely zero aggregate family, contributes 0.5 to every tract; it does not imply universal missing coverage. These are algebraic properties of the chosen formula, not executed results.

The shape checks do not certify a geographic partition or detect every plausible CRS misdeclaration. Building/POI overlap ties are reported; road overlaps and shared boundaries follow the stated convention. Bounds alone cannot prove CRS correctness. The method uses projected lengths rather than geodesic road lengths and total polygon area rather than dry-land/populated area.

## Running later on real, authorized inputs

The supplied requirements.txt pins DuckDB 1.5.4. Python 3.10+ and the matching spatial extension must already be available. The script disables automatic extension installation/loading and then explicitly loads the preinstalled spatial extension. It contains no package installation, remote data query, download, network extension load, target training or submission command.

From this directory, after preparing the local inputs and manifest:

    python density_baseline.py --region northern-ca \
      --data-root /absolute/local/challenge-data \
      --manifest /absolute/local/northern-ca-inputs.json \
      --out-dir /absolute/local/northern-ca-density-v1

Run each region separately. The output directory must not exist. The process returns nonzero on errors, and it never overwrites an earlier result. A failure during output writing can leave a partial new directory; only a completed run-receipt.json identifies a completed generation, and that receipt still makes no accuracy claim. Source execution and realistic cost measurements remain future work, not delivered validation.

Outputs:

- candidate.csv: GEOID, coverage_gap_score only, in official sample order. There are no optional component-gap columns that could be mistaken for organizer components.
- density-audit.csv: area, input-row counts, road-intersection metres, all three densities and rank deficits, plus the candidate score.
- run-receipt.json: method, input pins/byte counts, caller retrieval provenance, source/manifest/output SHA-256 values, DuckDB version, membership counts, unassigned point rows, tie counts and road allocation convention.

After a successful real run, the unchanged Lane A validator can consume candidate.csv:

    python ../validate_contract.py submission --region northern-ca \
      --sample /absolute/local/challenge-data/reference/northern-ca/northern-ca-sample-submission.csv \
      --candidate /absolute/local/northern-ca-density-v1/candidate.csv

This command is a future integration step, not a report that the validator or generator ran here. Do not combine regions or upload until an authorized participant checks the current platform/sample packaging.

## Interpretation, cost and validation limits

This method assumes only that lower observed mapping density may be worth investigating. It has no reference denominator and no target labels, so it cannot estimate absolute completeness by construction. Within-region ranks also discard absolute density differences between regions and impose an arbitrary relative distribution. They are not calibrated probabilities.

Natural rural sparsity, water-heavy tracts, mixed land use, large polygons, source entity duplicates, boundary allocation, projection effects and missing/outdated source coverage can all move the score. A perfectly mapped sparse tract may rank as a large deficit. A dense tract can still be badly mapped. Do not present these scores as evidence of discrimination, causal effects, disaster risk, measured inequity or a discovery prize finding. In particular, do not promote the separate Lane D cohort hypotheses using these unvalidated proxies.

The code requires complete provided feature files and a complete scored polygon match. It can read substantial data twice for hashing and materialize projected layers and spatial joins. A 2GB DuckDB memory limit is a database setting, not a guarantee of total process memory, disk footprint or completion. No timing, storage, geometry-repair success, score, leaderboard, reproducibility-across-platforms or clinical/public-safety claim has been measured. Invalid geometry is rejected instead of being silently repaired.

Publication checks were limited to complete source reading, primary API documentation, exact text construction and Git blob identity. No interpreter, SQL engine, compiler, package installer, synthetic data, tests or workflow was run. A real-data execution failure must be corrected before this candidate is represented as operational.

## Sources and rights

SOURCE_MAP.json distinguishes official documentation, inherited Lane A inputs and the preserved older implementation. No dataset, sample rows, borrowed implementation or full third-party document is redistributed in this directory.

This original source is contributed under the Commons root Apache-2.0 license. That source license does not relicense organizer data, Overture layers or any future derived data product. The organizer's data-sharing terms and per-layer notices remain separate. This internal source packet is not a competition entry or authorization to share work outside a properly formed competition team.
