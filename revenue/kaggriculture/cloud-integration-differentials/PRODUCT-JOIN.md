# Public-product callback: integrated and native-cash follow-through

This delivery exercises the existing runtime, not a replacement integration.
`select_public_seed_queue` from PR10033 uses JUNIPER/CYPRESS's PR10015
`seed_queue_selector` seam. DELVE's PR10060 adds the exact integral-float cash
conversion to the same certificate. All production files remain unchanged by
this follow-through.

## Executed result

Nine methods pass on combined main source
`17e149e75092c905e4ef96ce0dca8806e521ea5e`, certificate blob
`3d0c19cdf9f1260f56be3f6a7beb191b37b3d568` / SHA256
`e329a3535aeeed745cf975451b7bea859a6ec6f39cf54aeac57c3a3492cc3128`.
The identical nine-method test on prior PR10033 certificate `bf6c676f...` has
seven passes and two assertion failures, zero errors: the integral-float
product join and the recorded-cash/product counterfactual. This isolates the
compatibility of DELVE's repair with the optional product callback, without
rerunning DELVE's eight-method suite or twelve-game comparison.

The final run contains four full official-market calls, four actual cold parent
calls, and two direct post-unit applications to DELVE's retained observations.
The baseline run has its own four market/four parent calls. The earlier
seven-method checkpoint also retains its separate four/four calls and original
source; it is not relabeled as the later nine-method result. No full games or
game seeds were added by these checks.

The composed cases cover both seats, exact current DROP handling, demand
eligibility for extra selected PLANT, missing/underfunded public bounds, an
explicit caller fallback, and one original parent invocation per complete act.
In the constructed funded queue, the unchanged demand budget reduces WHEAT
seed17 to3 before productWHEAT3 and HIRE. Non-seed state remains identical and
cash improves140 in each seat. This is a current-market fixture, not an
observed full-game policy gain.

Two source-pinned observations contain actual cash40319.0 and41478.0 at steps600
and624 from DELVE's existing9965001 development stream. Their cash, public market
and stock are retained. The test replaces market slot0 with BUY_PRODUCT WHEAT1
and proposes removing one seed, explicitly as **new counterfactual financial
inputs**. Both certify a10 cash difference. The modified actions are not the
recorded actions, no market/game is executed for them, and no demand proof or
producer-state reconstruction is claimed. DELVE retains all original game,
trace and repair attribution.

## Runtime interpretation

Use the already-present interface:

```python
from integrated_selected import make_agent
from seed_funding import select_public_seed_queue
candidate = make_agent(seed_queue_selector=select_public_seed_queue)
control = make_agent(seed_queue_selector=None)
```

The optional callback validates the seed proposal only. It does **not** satisfy
the separate generic SELL requirement for a BUY_PRODUCT cash bound. The actual
joined test deliberately observes that seller fallback and confirms that it
preserves the certified funded queue. The default fixed-only callback remains
separate, and a supplied caller fallback remains authoritative. Do not label
this result as SELL optimization, complete-game adoption, or promotion over
frozen SELL. No frozen archive, existing entrypoint or default is changed.

## Reproduce

Reuse the existing PR9997 archive (SHA25695c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153)
and official engine artifact10005621438. In an ephemeral cloud extraction,
replace only its integrated_selected.py with the exact PR10015 file, SHA256
`dd6b0b52575ad95a975695d372546ebfbdcb829065574d9c94eab5085a44a9fe`.
The test requires that integration pin. Existing test_public_product_funding.py
supplies reusable state/engine helpers; none of its seventeen tests is invoked.

Decode the retained input and inspect every original report/log without any
engine execution:

```python
import base64, hashlib, json, lzma
from pathlib import Path
p = Path('revenue/kaggriculture/cloud-integration-differentials')
encoded = (p / 'PRODUCT-JOIN-EVIDENCE.json.xz.b64').read_bytes()
assert hashlib.sha256(encoded).hexdigest() == 'f071b608c75268f4a4e46325fbaf0ce3cae806627b5cf05acfc818118215e679'
raw = lzma.decompress(base64.b64decode(encoded))
assert hashlib.sha256(raw).hexdigest() == 'aec6b1ce2bc1421b61e79cd1e87db9662ffbdc447e3105c444918211491995a8'
evidence = json.loads(raw)
witness = evidence['reached_witness_utf8'].encode()
assert hashlib.sha256(witness).hexdigest() == '0ad5d66dcb1a4e441eec842d8174e3806379d8a669ebd83a703395bd58957810'
Path('/tmp/cedar-reached-cash.json').write_bytes(witness)
print(evidence['final_log_utf8'])
```

Run from a checkout containing the combined certificate:

```bash
python -B revenue/kaggriculture/cloud-integration-differentials/test_public_product_join.py \
  --integrated-root /path/to/existing/extracted-runtime \
  --engine-source /path/to/existing/engine/kaggriculture.py \
  --reached-file /tmp/cedar-reached-cash.json \
  --report /tmp/cedar-public-product-join.json
```

The lossless packet also retains the original seven-method checkpoint's test
source, complete report and log; the final and prior-certificate nine-method
reports/logs; and the exact original DELVE witness member. The full DELVE source
archive was retrieved once from Library and hash-matched to
`aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`.
Only that existing witness member is copied here, not a recreated game stream.

No workflow, exporter, profile runner, actor or runtime module is introduced.
The existing hosted95 compatibility result for PR10033 remains separate and
does not include these nine local methods. Later hosted totals retain their
own source, execution and report scope.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
