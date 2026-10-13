# REFORGE recovery — COK V10 + lonespear v18

This is the successor publication for the REFORGE session that completed local
execution but failed before its first GitHub write. It does **not** claim to
reproduce the lost session's exact nine local files. Instead it rebuilds from
the same immutable inputs and already-landed loader authorities, with new
server-backed source/tests/receipts in the existing V4
`research/reference-policy-bank/` family.

## Frozen inputs

- GitHub Actions artifact `10030763484`, ZIP SHA256
  `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`.
  Its `titan-reusable-sources.tar` supplies the preserved `cloud-pack` loader
  closure and cloud evaluator sources.
- GitHub Actions artifact `10032525998`, ZIP SHA256
  `6601d709ffa3cd17d994228869ba770a7189bb9b69467cca07ff40e8e6023da5`.
  It supplies exact COK V10 and lonespear v18 source/license closures.
- Existing Commons `public_bank/bank.py` Git blob
  `063b87dca064a8c673a6dd8839e6714abe46c4d4` and `intake.py` Git blob
  `ee8a90bb8f8ba135ef4d5e8056289ae32eed1c48`.

Exact public source SHA256:

- COK V10 `56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109`
- lonespear v18 `eb5b5f59a8ec2d40b77cc99d4ffe3b932136fdcf9f6b6e168726b7f07ab47cb0`

The source policies are never patched. The existing public-bank code owns
optional-import semantics and the preserved official last-callable loader.

## Build

```bash
python -B prepare_public_bank.py \
  --sourcepack-zip /path/to/artifact10030763484.zip \
  --intake-zip /path/to/artifact10032525998.zip \
  --bank-code /path/to/revenue/kaggriculture/cloud-opponent-frontier/runtime/public_bank \
  --output /tmp/reforge
```

The resulting `/tmp/reforge/bank/` contains three entrypoints:

- `cok-v10.py` — family `cok-v10`;
- `lonespear-v18-greedy.py` — family `lonespear-v18`;
- `lonespear-v18-scipy.py` — family `lonespear-v18`.

The two lonespear branches are deliberately **one family**, not two independent
opponents. The SciPy dependency snapshot is recorded at preparation and checked
by the existing `bank.make_agent` runtime.

`REFORGE-BANK.json` records the full generated runtime closure. A caller should
freeze the SHA256 of that manifest externally, then call
`verify_runtime(bank_root, frozen_sha256)` immediately before launch. This
prevents a self-replaced manifest from silently redefining the closure.

Consume the generated entry path through the existing `cloud-eval.Actor` /
BASALT bridge, creating a fresh instance per actor and game. This package does
not add another evaluator or fallback path.

## Executable control

Recovery was independently materialized from the exact three frozen inputs in
Python 3.13.5 with NumPy 2.3.5 and SciPy 1.17.0. The generated runtime manifest
SHA256 was `d1d9839d80187538b0e8c89a4ccc6ad5a66020a535f534558b8616cc825f5303`.

Using the already-spent public-bank development seed `9771001` against the
unchanged official starter, each entry completed both seats with zero candidate
failures. COK won 2/2 (mean margin +175,318), lonespear greedy 2/2 (+75,416),
and lonespear SciPy 2/2 (+110,248). The first game for each entry was replayed
and reproduced identical trace + scores. See `REFORGE-ENGINE-SMOKE.json`.

These are compatibility controls only. They are **not** held-out evidence,
leaderboard evidence, or proof that these historical public policies are strong.
The original REFORGE thread's historical-b567 losses remain useful context but
are not reissued here as raw evidence because the dead session's raw files were
never published.

No gameplay/default/controller/archive/Kaggle behavior is changed by this
recovery package.
