# TITAN V5 lean-feed source-contract fix-forward

Operation: `TITAN-V5-LEAN-FEED-SOURCE-CONTRACT-FIXFORWARD-20260914`

Target: `woahwhattheheck/commons` issue #14337, post-merge repair of PR #14345 / merge `a590e578574e09995bea4bf8a5eaffa56cd72461`.

## Finding

The checked-in carrier authenticates a fixed `Corn/Pasture/Straw` purchase model and a `buy_feed` call as D2 authority. The retained official engine instead has `FEED` consume one `WHEAT`; `BUY_PRODUCT` supports `WHEAT` and `FERTILIZER` and executes unit-by-unit against changing inventory. Retained current-lineage source exposes a dynamic SELL-WHEAT reservation seam, not the checked-in fixed purchase vector. Exact D2 member bytes are not retained by the carrier, so a positive source/economics claim cannot be authenticated.

## Fix

The patch:

- adds an independent strict source contract with exact engine/mechanics/lineage identities;
- marks the legacy synthetic oracle `NON_AUTHORIZING_SYNTHETIC_ONLY`;
- emits `SOURCE_MODEL_BLOCKED` instead of `PROMOTE_RESEARCH_CANDIDATE` whenever the old synthetic model would promote;
- keeps conservative `NO_PROMOTION` results conservative;
- rejects duplicate keys, non-finite JSON, fictional feeds, fixed reserve vectors, forged lineage identities, and self-promoted D2 member claims;
- leaves gameplay, CURRENT, defaults, archives, Kaggle, providers, and accounts unchanged.

## Validation

- `python -m py_compile ...`: PASS
- focused authored-equivalent package: 16/16 normal PASS
- focused authored-equivalent package: 16/16 `python -O` PASS
- deterministic CLI output: `SOURCE_MODEL_BLOCKED`

The patch is based on exact current-main preimage blobs listed in `CURRENT_MAIN_PREIMAGE.json`. Current main was path-fenced after intervening merges; these target blobs were unchanged.

## Apply

From a clean current Commons checkout whose listed target blobs still match:

```bash
git apply --check titan-v5-lean-feed-source-contract-fix-forward.patch
git apply titan-v5-lean-feed-source-contract-fix-forward.patch
python -m py_compile revenue/kaggriculture/cloud-execution-lab/candidates/v5/lean-feed-carry-economics/*.py
python -m unittest -v \
  revenue/kaggriculture/cloud-execution-lab/candidates/v5/lean-feed-carry-economics/test_feed_carry_oracle.py \
  revenue/kaggriculture/cloud-execution-lab/candidates/v5/lean-feed-carry-economics/test_lean_feed_source_contract.py \
  revenue/kaggriculture/cloud-execution-lab/candidates/v5/lean-feed-carry-economics/test_cli_smoke.py
```
