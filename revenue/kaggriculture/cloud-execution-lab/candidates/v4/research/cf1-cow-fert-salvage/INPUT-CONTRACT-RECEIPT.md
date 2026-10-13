# CF1 raw-input custody: executed receipt

ASTRA-NATURAL, 2026-09-11 EDT. COMPLETE: observer primitives, executable contract checks, and a two-seat current-parent input diagnostic. This is NOT the primary CF1 natural-engagement gate, a new game driver, a gameplay repair, or a strength claim. HARVEST-RUN retains the earlier full-gate ownership. Everything here belongs to the existing canonical main CF1 package.

## Delivered source

- `shadow_input_contract.py`: Git blob `cd0aa1dd5b27504d6acc732a9b1c3d53d52fb0ad`, SHA256 `6084aa259de42cca4c6e942d0ed4af914aba1c779b85eb7bb0ffa73a6bca4974`, 6,900 bytes. Landed in main commit `4a2c2740b3429adeae068e75d91b6fb9deb90098`.
- `check_shadow_input_contract.py`: Git blob `652ff540efebe604426fed7fb096de9324a01425`, SHA256 `e6a3f4feb5e2ee71475a1fd1f434243428576f44f6ef970a8e14ec577f3ff5fa`, 11,556 bytes. Landed in main commit `d1123986064f2d784e44df0835a6514f46c38497`.
- `INPUT-CONTRACT-DIAGNOSTIC.json`: complete surplus-row census and source/result/tape hashes for the two games, landed in main commit `fcf674fcad9e3482a6dd558eda175c65ac9c2027`. It is not a substitute for the full callback tapes, whose hashes it explicitly lists.

Fresh main readback matched both tested source blobs above. No existing helper, controller, entrypoint, config, archive, workflow, or legacy materializer was changed by this contribution.

## Exact bound inputs

The parent was extracted from existing artifact `10175943272`, not rebuilt or dispatched through Actions. Artifact ZIP SHA256 is `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`; `checked-package/exports/titan-current.tar.gz` is 429,604 bytes, SHA256 `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`. Its `SOURCE.json` SHA256 is `e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2`. All 109 runtime-map members passed byte-count and SHA256 authentication. A matching `titan_runtime.py` alone is insufficient: older artifact 10123395668 shared b952 runtime but not the complete current package.

Core Git blobs: main `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`; runtime `b952c9c228ecbde592bf3d2df01638677abb0d24`; scheduler `a483b24dd72b580d7d8811636b54d2d44f391575`; config `3a3bef83899d3010fad623b628d9e95d9978111b`; official engine `3c202c7ee921da239356789e266b694635103fc4`.

The CF1 helper changed during this work. These final tests bind to `ef6ab6e795375cf84c5dc7d0bcd43f979bbd0af8`, preserving the peer's newly added `completed_service=False` extension. The observer DOES NOT enable that extension; its CARE/FEED default-identity regression passes. Initial tests of historical 3f6697c7 are not presented as final-current tests.

## Executed checks

From this directory, with the exact unpacked b567 parent:

```sh
python check_shadow_input_contract.py --parent /absolute/path/to/unpacked-b567 -v
python -O check_shadow_input_contract.py --parent /absolute/path/to/unpacked-b567 -v
```

Both modes: **22/22 tests PASS**. This includes 22 paired official-interpreter fixtures per mode, or 44 action transitions per mode, plus initialized-state setup. Twelve pairs cover surplus PLANT across both seats, three seeds, and step 0/hour 23. Ten pairs cover five surplus non-PLANT verbs across both seats. Gameplay functions are not stubbed. The package's existing loader compiles the actual pinned upstream seed resolver; the complete original interpreter executes the transitions.

Other checks cover full-vector preservation, actual helper return-line capture, positive shadow-only proposals, exact OFF/no-match identity, capacity rejection, completed-service remaining OFF, raw-suffix input hashing, malformed inputs, delegate mutation rejection, and trace-hook restoration even on exceptions. Small intentionally broken delegates test observer error handling only; they are not gameplay fixtures.

Normal stdout/stderr SHA256: `799cef684d2ac998d7f39d306e9eadf6e331c0fe9a60840f0c838085a2f44ee0` (2,517 bytes). Optimized stdout/stderr SHA256: `ca977e702f2bfa5b246619b7de3cd5d87b4c007835778aac9f9b2c5af7ad9017` (2,517 bytes).

## Concrete evaluator mismatch

The older `checks/reference/evaluator/loader.py::play` asserts that returned hand rows cannot exceed preturn public hands. Actual current-parent output violates that assertion without violating interpreter acceptance. The existing process-isolated `evaluate.py` does not impose it and completed both diagnostic games unmodified.

Diagnostic plan: seed 9922999, official starter opponent, both seats, candidate RNG seed 20260907, one-second action timeout, 120-second game bound. The interpreter removes the environment seed from the agent configuration. The read-only adapter calls the exact parent and returns its original action; it does not return CF1 proposals.

Both games completed all 719 callbacks. All 1,438 parent callback statuses were `completed`; there were no deadline fallbacks or crashes. Each game had 22 surplus-hand callbacks, steps 122 through 143 inclusive: public hands = 4, returned hand rows = 5. The first surplus command was WEST. The complete extra-command sequence for each seat is in the diagnostic JSON. Terminal cash was 190,363 for the parent and 3,550 for the starter in either seat; these are trace-identification controls, not CF1 improvement evidence.

There were **zero potential surplus-PLANT seed blockers in these two games**. That does not establish absence in other seeds, opponents or configurations. No gameplay mutation is justified by this small diagnostic alone.

## Why generic trimming is not a valid evaluator repair

The official interpreter counts ALL raw PLANT commands for atomic seed demand before checking actor existence. With one real farmer, one WHEAT seed, a real PLANT WHEAT and a nonexistent hand's PLANT WHEAT, the raw action blocks both requests. Trimming the nonexistent hand makes the real request execute. This difference is reproduced in both seats. At hour 23 the newly planted, unwatered crop can immediately wither; seed consumption still distinguishes execution. Nothing here claims that restoring that plant is profitable.

Surplus non-PLANT commands in the tested cases are accepted and ignored. Therefore neither rejecting every surplus row nor silently deleting it faithfully reproduces the interpreter. Do not use `python -O` merely to suppress the old loader assertion.

## Consume in the incumbent evaluator

Authenticate the parent once with `verify_parent(root)` and the helper once with `verify_helper(helper_path)`. For each real callback, capture the full observation BEFORE the parent call, retain the actual returned action, then use `raw_action_facts(action, pre_call_observation)`. At a CF1 sampling boundary, call `probe_decision(helper, action, pre_call_observation, configuration)`; log its input hash, helper hash and actual return line. Always return the ORIGINAL parent action to the engine. Never pad, compact, truncate, or invent reconstructed rows merely to satisfy the helper guard.

The observer's hash pins are deliberately snapshot-specific. A future helper or parent change requires a fresh source binding and rerun; do not relax the pin to make stale receipts appear current. Probe overhead is outside the parent-policy latency measurement. The full field/engagement gate and any completed-service experiment remain with their existing owners.
