# Portable execution of the existing B7 oracle

ASTRA-B7-RUN, 2026-09-11. Additive tooling in the single canonical `main/candidates/v4/repairs/gameplay/b7-shed-overflow` package. The existing oracle, helper, CURRENT_ORACLE.json, production runtime and defaults are untouched. This is not another B7 implementation.

## Executed result

Python 3.13.5, standard library only. `test_portable_oracle.py`: **20/20 normal and 20/20 optimized**, no skips. The tests include real pinned-engine execution, six individual source-corruption controls, two-archive dependency staging, wrong-local-source rejection despite a correct archive, missing source/dependencies, symlinks, unsafe ZIP member names, oversized members, archive member-count limits, duplicate byte-identical members, timeouts, malformed child output, input nonmutation and caller import-namespace isolation.

The default portable command executes isolated normal and optimized children. EACH child runs the unchanged existing oracle: **128 cases, 80 transformed and 48 exact-identity cases, 5 ordered boundaries**, 40 transformations per seat and per actor index. The two child results are identical. Executing the parent itself under normal Python and `python -O` produced byte-identical full JSON. A separate run using only the two canonical source files plus the two actual archived ZIPs produced the same JSON, leaving that minimal checkout at two files.

Exact source and evidence identities:

- `run_portable_oracle.py`: Git `3e7a2c581f7c70c572691f3188c51583bffbdfe6`, 10040 bytes, SHA256 `965a4ca246a30f66a59d5b35f43e9893ecacb2c10268944ef7f1f7f86ab28e06`.
- `test_portable_oracle.py`: Git `8db6e2f6eb8b04c5900dfb66947daa7fecf1a783`, 10298 bytes, SHA256 `645dd9040a0ed65561c6bc1a0ed5af23345a4ea360d1a51cecdd67f7bb3f2578`.
- `PORTABLE-STDOUT.json`: exact stdout, Git `a7232b20c8cd77183d08e07f48b8e8b6bd023583`, 3804 bytes, SHA256 `f08a43b8fc961a2ff9398feacc1e4b082766b2e02eb52b49c2cfdf7c015cfd21`.

## Reproduce

From the repository root:

```sh
B7=revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay/b7-shed-overflow
python "$B7/run_portable_oracle.py" --root .
python -O "$B7/run_portable_oracle.py" --root .
python "$B7/test_portable_oracle.py"
python -O "$B7/test_portable_oracle.py"
```

If engine/spec/utils/runtime files are absent, supply already downloaded GitHub artifact ZIPs with repeated `--artifact /absolute/file.zip`. The canonical oracle and helper must exist locally. Existing files with incorrect pins FAIL; archives never override a wrong local source. All recovered files are written only into an automatically removed temporary directory outside the repository. No `extractall`, package installation, network request, workflow dispatch or repository write occurs.

For tests in a minimal checkout, set `B7_PORTABLE_TEST_ARTIFACTS` to the artifact paths joined by the platform path separator (colon on Linux). The test suite requires all exact dependencies; it does not skip a missing fixture.

## Dependency transport discovered and independently verified

Existing artifact **10123395668** from run **34400824037**, head `4be7772ab850e50f42d0eb0fe715fecadb19ee10`, contains the exact current runtime in both `final-pressure-runtime/titan_runtime.py` and `seed-retry-runtime/titan_runtime.py`: Git `b952c9c228ecbde592bf3d2df01638677abb0d24`, 33885 bytes, SHA256 `da391af2dbdec0f6e4a25749ed539cdd39578ace8861c0e225b5fbfef90d75a8`. ZIP SHA256 `d11b9ca245dc8205dabd26523c2e431055feaa22afa3bc10866e4e3bae3db4ed`.

Artifact **10285621024** supplied exact engine `3c202c7e`, spec `b354d06b`, utils `91c8822e`, but its runtime is OLD `a10ad66f`; do not claim current runtime validation from that file. ZIP SHA256 `5ff92183fedce1ff8071b35e8e97dc23dc1ea7762ee47260c7ff2be2d0d2bc94`. The portable runner accepts only full pinned identities, never these abbreviated names.

## Import adaptation and claim boundary

The original direct oracle command fails here with `ModuleNotFoundError: kaggle_environments`; that direct invocation is NOT represented as passing. The portable runner creates an isolated `-I -B` subprocess and supplies the unchanged AST-extracted `resolve_episode_seed` function from hash-pinned official utils as the engine's sole external import. The full official engine and original oracle execute unchanged. Resolver calls are counted and required to equal zero for these unit-action tests. No production runtime is imported: its hash and hook text are checked by the original oracle.

This receipt proves component behavior on constructed cases, not actual packaged B7 reachability, full episodes, paired economic gain, Python 3.11 hosting or Kaggle performance. B7 remains unwired/default-OFF; the original oracle owner retains CURRENT_ORACLE.json. No stale V3/V4 materializer is executed.
