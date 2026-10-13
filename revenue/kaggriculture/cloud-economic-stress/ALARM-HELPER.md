# Direct cancellation helper composition

This follows the source-pinned PR10038 caller-timer repair documented in `CALLER-TIMER.md`. That original 20-method result remains unchanged. The current adapter additionally binds `_alarm(None, None)` to the active guard's cancellation object. This preserves the direct helper used by CANCEL's published `_commit`, transform and before-transform regressions without weakening the distinction between a guard timeout and a caller timeout.

A context-local active timer is installed/restored with the guard scope. When delivering an enclosing caller's handler, the adapter temporarily restores the caller's timer context. An enclosing `_alarm` therefore cannot acquire the inner guard's identity. Outside any guard, `_alarm` still raises `DeadlineExceeded(BaseException)`. Explicitly raised foreign exceptions remain foreign. The cancellation class/docstring, worker actions and liquidation fallbacks are unchanged; only the helper body and its context binding extend PR10038.

## Executed result

`test_alarm_helper.py` composes the unchanged `test_deadline_contract.py` suite with three new helper methods. **23 methods pass**, zero failures/errors, with six actual PR9997 actor/interpreter transitions and one real parent call in each. The 20 original methods remain byte-identical. `ALARM-HELPER-RESULTS.json` is the canonicalized executed report, including exact source hashes and all six actions/cash rows.

The three additions exercise direct helper cancellation at production/transform/before-transform boundaries, an enclosing caller registered with the same helper, and helper behavior outside a guard. Against exact PR10038 adapter33ce93fe the combined suite retains the original passing cases but reports five error records across the new helper methods/subtests. The corrected adapter resolves those errors without changing the tests. CANCEL retains its separate 18-method suite and prior evidence; its new-source execution is not included in this 23 count.

```sh
python3 -B revenue/kaggriculture/cloud-economic-stress/test_alarm_helper.py \
  --runtime /path/to/existing/integrated-selected-v1 \
  --engine-loader /path/to/existing/20260907-offline-agent/evaluate.py \
  --engine-cache /path/to/existing/engine \
  --report /tmp/deadline-helper-results.json
```

All options also support the existing repository layout defaults. The same frozen archive and engine inputs listed in `CALLER-TIMER.md` were reused, not regenerated. No games, new evaluation seeds, workflow changes or policy selection.

Adapter Git blob `1c777790cf74cd528461466765c2a48ef49cf191`, SHA256 `c3bef158763cb4f5f8b8436800f442b1acc94be2c407c5db1e740edd3a0d68f0`. Helper-test blob `815cc4afdecd7cbbdeea310c64093a936e72724f`, SHA256 `bd751468706d74ce9383cc4be9b9b84f5389cd6f17011e8ea185f05bdb89f624`. Original caller-test blob `38e226a67bf671b578e63d50cda6120970d1bde3` is retained.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
