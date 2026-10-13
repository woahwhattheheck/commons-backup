# minikit — SYNTHETIC FIXTURE. FICTION. NOT UNIVERSITY OF IOWA MATERIAL.

These four tiny lane directories exist only so `test_verify_kit.py` can prove the
verifier's classifier against known ground truth without touching the real lane tree.

| fixture lane | built to be | expected verdict |
|---|---|---|
| `uiowa_rfq_18649_alpha` | code with a check that passes | WORKING |
| `uiowa_rfq_18649_bravo` | code with a check that genuinely fails | DRAFT |
| `uiowa_rfq_18649_charlie` | documents only, no executable code | DRAFT (document) |
| `uiowa_rfq_18649_echo` | present on disk, absent from the manifest | UNMAPPED |
| `uiowa_rfq_18649_delta` | named by the manifest, never created | MISSING |

`bravo` fails on purpose. It is the strength/gap pair the fixture is required to
demonstrate: alpha shows the verifier can certify a passing component, bravo shows
it refuses to certify a broken one even though bravo's own README claims it works.
