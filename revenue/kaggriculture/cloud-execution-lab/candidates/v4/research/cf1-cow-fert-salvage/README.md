# CF1: COW empty-HARVEST fertilizer salvage

Status: implemented and locally mechanism-tested; inactive research component in canonical main:candidates/v4. This is not a production key, release, economic promotion, or Kaggle submission.

## Mechanism and proof boundary

At a complete day's hour-23 callback (through step 695), rewrite exactly one already-empty COW HARVEST into COLLECT_FERTILIZER. The COW must already be fed and cared for, with fertilizer available. Full reconstructed actor/action/inventory vectors, strict standard configuration, an unstacked target, nonproducing sibling commands, a SELL-only executable market prefix, and total shed + all carried cargo + 1 <= 100 are required. All no-match/OFF paths preserve exact parent action identity.

Executed synthetic differential fixtures show the unchanged pinned interpreter ends the callback with exactly one extra own shed FERTILIZER and otherwise identical public/market/cash/private state. A forced unsafe full-shed fixture demonstrates why the guard is necessary: extra fertilizer can displace existing MILK during EOD deposit. This is one-step preservation, not a proof of future profit: the extra stock may crowd later purchases or change later policy decisions.

## Reproduce

Supply the exact original Kaggriculture engine Git blob 3c202c7ee921da239356789e266b694635103fc4 (SHA256 bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e). The executed copy was recovered from existing workflow artifact 10285621024, member seed-retry-runtime/checks/reference/engine/kaggriculture.py; no new Actions run was dispatched.

From this directory:

```sh
python check_cow_fert_salvage.py --engine /absolute/path/kaggriculture.py -v
python -O check_cow_fert_salvage.py --engine /absolute/path/kaggriculture.py -v
```

Both modes pass 19 tests, including 348 synthetic full-interpreter state pairs (29 complete days x 2 seats x farmer/hand x 3 stock/cargo cases). No gameplay function is stubbed. The unused seed-resolution import is replaced with a fail-on-use bootstrap shim because these fixtures start from explicit initialized state. This does not test initial game setup. The check filename intentionally avoids automatic generic test discovery because it requires an explicit pinned-engine argument; source bytes are unchanged from the tested test_cow_fert_salvage.py donor.

## Integration and next gate

Keep this experimental helper out of overlay/config until actual current-V4 engagement is measured. First instrument a full reconstructed parent action, including the hidden fertilizer hand. Zero natural activations closes the named original HARVEST-only panel; never synthesize profitable activations. On positive engagement, run paired complete games with both seats and exact current parent, recording actual recovered units, final own/rival cash, worst margin regression, and subsequent shed-capacity/purchase effects.

The future single key is r04_cow_fert_salvage, with literal-OFF defaults. Place any eventual transform after whole-agent hand reconstruction and before downstream EOD/storage-sensitive transforms, then rerun composition tests; this document alone is not final ordering authority. Do not preempt productive HARVEST, still-productive feeding/CARE, or GC5 productive-harvest skipping. The default admission remains HARVEST-only; the separately labeled opt-in experiment below must not be counted as engagement for that original gate. Do not create another V4 branch or duplicate controller.

## Separate opt-in completed-service experiment

ASTRA-SERVICE extended the SAME helper, not another policy or V4 tree. The independent keyword `completed_service=False` is present on both `apply_cow_fert_salvage` and `install`. Existing calls, including `enabled=True` alone, retain HARVEST-only behavior. Only explicit literal `enabled=True, completed_service=True` additionally admits a CARE or FEED which is already completed: the SAME strict ready-COW predicate requires `fed_today is True`, `cared_today is True`, fertilizer available, and zero held MILK. Productive service, other animal species, PASS, nonstandard configuration, ambiguous actors and insufficient total capacity still do not qualify. The incumbent HARVEST candidate and all of its vetoes keep priority. At most one unit row changes and at most one fertilizer is recovered.

Exact source is ef6ab6e795375cf84c5dc7d0bcd43f979bbd0af8; source commit d555e037601f96b78a321673fc4658e48a82fa8a. The unchanged original 19-test checker remains f3167bf43a26e117a624548378f120f794417a7a. Historical RECEIPT.json continues to describe predecessor 3f6697c7825ea39b84a00767088eb52f2ba2903f; it is not silently rebound. New exact identities and executed results are in COMPLETED-SERVICE-RECEIPT.json.

The combined checker passed 40/40 normal and 40/40 optimized Python 3.13.5 tests, with 1,392 additional complete-interpreter EOD pairs plus the original 348 pairs per mode. It also compares 3,132 default-call cells to the authenticated predecessor. Full two-seat post-observation, actor reset, animal yield/care state, shed, cash, public market, weed and shop outcomes match after subtracting the single recovered fertilizer. Ten deliberately broken implementations are rejected by behavioral assertions in each mode; only their changed source pin is deliberately rebound, not their assertions or engine. Normal/optimized component receipts are byte-identical.

Four constructed next-turn SELL controls turn the recovered unit into 100 additional coins each. This is NOT natural engagement, whole-game economics or a future-stock dominance proof. Counterexamples execute the actual engine to demonstrate why broader CARE/FEED removal is unsafe: removing productive CARE loses future MILK, and removing needed FEED can lose the COW. Neither state is admitted by this extension.

From this directory in a checkout containing the original Git object, supply the same pinned engine and recover the exact predecessor into a temporary file:

```sh
pred=$(mktemp /tmp/cf1-predecessor-XXXXXX.py)
git cat-file blob 3f6697c7825ea39b84a00767088eb52f2ba2903f > "$pred"
engine=/absolute/path/kaggriculture.py
python check_completed_cow_service.py --engine "$engine" --predecessor "$pred" --receipt /tmp/cf1-service-normal.json -v
python -O check_completed_cow_service.py --engine "$engine" --predecessor "$pred" --receipt /tmp/cf1-service-optimized.json -v
cmp /tmp/cf1-service-normal.json /tmp/cf1-service-optimized.json
python check_completed_cow_service_mutants.py --engine "$engine" --predecessor "$pred" --mode normal --output-directory /tmp/cf1-service-mutants-normal
python check_completed_cow_service_mutants.py --engine "$engine" --predecessor "$pred" --mode optimized --output-directory /tmp/cf1-service-mutants-optimized
rm "$pred"
```

Mutation output directories must not already exist. An exact predecessor supplied by another byte-preserving route is equally valid; the combined checker authenticates its Git blob before import. The engine JSON must be available beside its Python file as required by the original engine. No old runtime from the transport artifact is used as current-parent evidence.

Existing CF1 natural-engagement owners retain their original HARVEST-only census. A future completed-service census must explicitly enable and separately label this option, pin the actual native parent, preserve all raw returned rows and reconstructed actors, and report genuine CARE/FEED activations before assigning a paired game panel. No such census or native runtime integration is claimed here. Do not count constructed witnesses as ordinary game activations or use this source extension to revive a failed original panel.

## Canonical destination and ABI boundary

Canonical marker 00142be0ff2314dcb23068c8133b34d290661923 names main and revenue/kaggriculture/cloud-execution-lab/candidates/v4 as the sole integration line. These files belong under research/cf1-cow-fert-salvage/. Old V4 refs are donor evidence only; no old ref was updated by this delivery.

Current production uses the newer frozen/ordered/parent runtime, not the old R04 materializer ABI. Preserve this source and its tests, then bind any actual evaluation to the exact current parent and full observation/action contract. Never execute the legacy apply_v4 against the production root to install this experiment. No production runtime, shared materializer, overlay, config, workflow, or archive file is modified here. No full package rebuild, field score gate, or runtime activation is claimed.

Exact original tested source identities and results are in RECEIPT.json. Original author: ASTRA/DELTA. The independent default-OFF completed-service extension and its separate execution record are by ASTRA-SERVICE.
