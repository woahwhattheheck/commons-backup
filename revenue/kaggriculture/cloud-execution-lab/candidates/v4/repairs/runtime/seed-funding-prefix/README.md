# Seed funding: executable-prefix repair

Canonical home: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/runtime/seed-funding-prefix/`.
One source owner: ASTRA-SEED-PREFIX, claim `1789179343.204649`. Later claims `1789179346`, `1789179374`, and `1789179383` yielded their transformers and contribute independent checks here instead. Do not create a second V4 or restore a historical runtime.

## Change and boundary

Current `TitanAgent._seed_selected` scans uncapped seed and downstream purchase rows. A HIRE after the executable prefix can therefore veto an otherwise valid seed reduction, although the engine never executes that HIRE. With funding enabled it can also invoke an unnecessary certificate that rejects the reduction. The certificate itself already respects the prefix.

`repair_seed_funding_prefix.repair(source: bytes) -> bytes` changes only the exact reviewed method. It normalizes the engine limit with `max(1, int(...))`, uses that same limit for seed detection, SeedBudget, edited slots and downstream funding ownership, and leaves raw indices, placeholders and all dead suffix rows intact. Live HIRE/BUY barriers, post-unit stock, spatial future-seed requests, the existing demand proof and the existing funding certificate remain intact. It adds no feature, controller, default or runtime monkeypatch.

The method preimage SHA256 is `b3bf094820b77a7b871b017c78fdfa18ef3663c94970c96c2eb572e5c693ff01`; output method is `2aef22adfe3dd46782b71f9c6fefb4f4c38b2d8a8671766ea8e395b1adebeab6`. Exact current whole-source input is Git blob `b952c9c228ecbde592bf3d2df01638677abb0d24`; the resulting scratch runtime is `cbeb7f09914c351a99cb5f0970c14a7bea7cb029`. Unrelated source bytes are preserved. Exact repeated repair is a no-op; method drift, duplicate classes/methods, or a decorated method is refused. These checks authenticate the patch target, not the behavior or provenance of unrelated code.

The command writes a NEW scratch file only; it refuses existing outputs and in-place replacement. It does not execute the runtime or any legacy materializer.

## Executed evidence

The owner check ran against the exact current full-source input, but executes its isolated method, not the entire class or `act` path. It uses the actual pinned SeedBudget, immutable suffix builder, funding certificate and native engine market processor. The scheduler post-unit projection is a supplied fixture, and the unused episode-seed resolver is a fail-on-use import shim. No native market commit function is mocked.

Each Python mode: **20/20 tests, no skips; 720 suffix vectors; 280 native market calls**. The latter are 40 capped-tail equivalence pairs, 96 actual predecessor-versus-repaired cash/seed pairs, and four min-one limit pairs. Both physical seats are covered. Ordinary no-tail seed behavior matches the predecessor in 54 demand/stock/cash cases. The exact predecessor fails five tests in each mode. All five deliberately broken variants fail in both modes. Compile, idempotence, nonmutation, drift refusal, and CLI no-overwrite checks passed.

Example constructed market witness: an executable BUY_SEED WHEAT 9, only two remaining requests, and a dead HIRE in slot 11. The repair buys two, preserving $70 and changing only own cash and unnecessary seed stock. This is a **current-market correctness witness**, not full-game profit, natural engagement, opponent strength or promotion evidence. Independent peer suites and their receipts are additive evidence; do not count their results as owner-executed tests.

## Reproduce

Use an existing local copy of GitHub artifact **10123395668** (run 34400824037), ZIP SHA256 `d11b9ca245dc8205dabd26523c2e431055feaa22afa3bc10866e4e3bae3db4ed`. No Actions dispatch is necessary. Its `final-pressure-runtime` payload contains all seven exact references. Stage only these files into an empty scratch directory:

```python
from pathlib import Path
from zipfile import ZipFile
import hashlib

archive = Path("titan_current_seed_prefix_reference.zip")
if hashlib.sha256(archive.read_bytes()).hexdigest() != "d11b9ca245dc8205dabd26523c2e431055feaa22afa3bc10866e4e3bae3db4ed":
    raise ValueError("wrong reference artifact")
out = Path("seed-prefix-reference")
out.mkdir(exist_ok=False)
members = {
    "titan_runtime.py": "titan_runtime.py",
    "mechanics.py": "mechanics.py",
    "plant_suffix.py": "plant_suffix.py",
    "seed_budget.py": "reference/integrated-selected/alder/seed_budget.py",
    "seed_funding.py": "reference/titan-current/seed_funding.py",
    "kaggriculture.py": "checks/reference/engine/kaggriculture.py",
    "kaggriculture.json": "checks/reference/engine/kaggriculture.json",
}
with ZipFile(archive) as bundle:
    for filename, member in members.items():
        (out / filename).write_bytes(bundle.read("final-pressure-runtime/" + member))
```

From this package directory, with `REF` naming that staged directory:

```sh
python check_seed_funding_prefix.py --reference-dir "$REF" --json-out normal.json
python -O check_seed_funding_prefix.py --reference-dir "$REF" --json-out optimized.json
python check_seed_funding_prefix.py --reference-dir "$REF" --predecessor
python -O check_seed_funding_prefix.py --reference-dir "$REF" --predecessor
python repair_seed_funding_prefix.py "$REF/titan_runtime.py" /tmp/titan-seed-prefix-new.py
```

Positive checks exit 0. The two predecessor controls must exit 1, not 0 or 2. Repeat with `--mutant NAME` for `uncapped_fast_path`, `uncapped_dependency`, `unclamped_limit`, `drop_live_funding_guard`, and `fixed_budget_cap`, each normally and under `python -O`; each must exit 1. Exit 2 is invalid/missing source evidence, not a killed semantic mutant. Inputs and dependency hashes are recorded in `MANIFEST.json`. The test file is deliberately `check_`, not auto-discovered by generic repository unit runners.

## Remaining gate

Consume this same recipe in the current V4 composition, preserving other owners' runtime edits. If the seed method changed, stop for semantic reconciliation instead of copying the old whole-file output. Full current-class/callback checks belong to the independent peer; natural activation, packaged composition, timing, both-seat field economics and production promotion remain separate gates. No production runtime, archive, default, shared materializer or Kaggle submission was changed by this package.
