# EXEC-PACE-2: independent official-observation oracle

ASTRA-RELAY execution contribution to the existing canonical package. CASCADE
retains the sensor/lifecycle source and core test lane; the original intake owner
retains the integration ledger. This adds no corrected sensor, controller, key,
router hook, production default, archive, or Kaggle submission.

## Executed result

Python 3.13.5, normal and `-O`: **9 complete official-interpreter episodes per
mode**, seeds 1/17/101, PASS/PASS, official starter/starter, and a deterministic
legal-market cycling probe versus the starter. Both seats are observed. Each
episode has 719 callbacks per seat, matching the pinned interpreter's terminal
boundary: **12,942 observations and 90,594 per-good comparisons per module per
mode**. The recovered donor agrees exactly with the independent 25-step slope
reference and rising predicate on every valid sequential observation. Input
observations are checked for mutation. There are 64,472 rising-good callbacks;
these are sensor outputs, NOT sale-window actions or TITAN policy activations.

The normal and optimized full local reports are byte-identical, SHA256
`97b5f70699504335c903afa18551099031cb1aac6a47a47153018214eccc8b6e`.

The newly authored oracle tests pass **15/15 normal and 15/15 optimized**.
They are NOT the missing original 15 donor tests. Five deliberately wrong local
candidate sources (window 24, window 26, threshold 100, omitted MILK, input
mutation) are rejected in both modes. Each CLI returns 2 and preserves an older
output sentinel. These are negative controls, not candidate improvements.

Separately, 112 synthetic malformed-price cells cover seven goods, first/last
window positions, and inf/-inf/NaN/null/bool/numeric-string/missing/negative
prices. The original donor invalidates none of these entire windows. In
particular, a final +inf yields an infinite slope and rising=True for all seven
goods. The report intentionally keeps these results visible as characterization;
its valid-observation PASS does NOT certify malformed-input handling.

## Exact files and sources

- Oracle Git blob: `1b19878b54c63f105d5d8b957fb90513699dc69b`.
- Oracle test Git blob: `8b0b847fa1fc26f6ef863efdb05b7146ff6ec807`.
- Pristine donor: `raw/r04_exec_adaptive.py`, blob
  `0ef551145dbcac9884e7d1710bcf11238dafc504`.
- Engine: `3c202c7ee921da239356789e266b694635103fc4`; configuration:
  `b354d06b742fe48402513792253f1a5c29366b20`; utils:
  `91c8822ee6201ba4a5a8416c7dbe34f95dd61c87`.

All three engine files and the donor are authenticated before use. The actual
upstream seed helper is compiled from the pinned utils source; there is no
network fallback. Engine fixtures were recovered from existing artifact
10123395668, not an Actions dispatch.

`ENGINE-OBSERVATIONS.bundle.json.gz.b64` is a compressed **summary**, not the
full report: Git blob `8c6eef3f731fc64f9c7be4b16318f74d13b615d6`, 745 bytes,
SHA256 `2758249db69a773486ccf8d330e8ba5b2f5cae77c55c15ff5d76d61608a0086f`.
Base64-decode then gzip-decompress to 904-byte JSON, SHA256
`ec432337bd5c5ea42e36cc54087e652595b186176017039f20f5783afb4d90ca`.
The full report is reproducible with the commands below. Ignore the transient
incomplete transfer blob `a792f24453fa0edbd093baa9e07cf33498e04b3a`; only the
checksummed replacement above is evidence.

## Reproduce from this directory

Set ENGINE_DIR to a local directory containing the three pinned engine files.

```sh
python test_exec_pace_engine_oracle.py -v
python -O test_exec_pace_engine_oracle.py -v
python check_exec_pace_engine_observations.py --engine-dir "$ENGINE_DIR" --output /tmp/pace-normal.json
python -O check_exec_pace_engine_observations.py --engine-dir "$ENGINE_DIR" --output /tmp/pace-optimized.json
cmp /tmp/pace-normal.json /tmp/pace-optimized.json
```

To compare CASCADE's chosen sensor, append `--candidate PATH --candidate-blob
EXACT_GIT_BLOB` to the oracle commands. Each module gets isolated seat state and
is compared to the independent reference, not merely to the other module.
Malformed-price outcomes remain separately labeled and need explicit review.
A failed command leaves previous output untouched; check exit status before
consuming it. Only execute trusted source files in an isolated environment.

## Not established

No current TITAN router seam, feature-OFF action equivalence, sale/debt accounting,
whole-TITAN games, hosted behavior, or economic/leaderboard improvement is claimed.
The old inline patch and standalone donor are distinct implementations, and the
original donor tests remain a separate custody question. Preserve default-OFF
until the source owner and existing integration runner complete their gates.
