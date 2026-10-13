# Fast-clone recovery: current-runtime port

Status: **landed in the single main V4 workspace; current-ABI component tested; not production-promoted**.

This extends the already-preserved #12431 package in this directory. It does not create a new feature key or successor V4 branch. The existing ORBIT helper and tests are retained byte-for-byte. The neighboring `port_fast_tape_clone.py` is the older generator-level donor; it must not be run against the current production ABI. `port_current_runtime.py` is the new, separate current-ABI adapter.

## What is ported

The reusable lossless-clone optimization is applied to the current `TitanAgent.act` selected-action checkpoint, not the old `Policy.act` tape-selection site. It appends `r04_fast_tape_clone: bool = False` after the existing Features fields, preserving existing positional arguments. A lazy import and clone branch run only when that field is enabled, inside the existing action deadline timer, immediately after the one production call. The disabled path retains `deepcopy(selected)` and does not import the helper. All unrelated runtime bytes, entrypoint behavior, deadline fallback copies, finalizers and checkpoint ordering remain unchanged.

The adapter requires an explicit full input Git blob, checks the actual AST scope and neighbors, rejects repeated application and changed/missing/duplicate anchors, compiles the result, and creates an output file exclusively. It does not execute a legacy generator, overwrite its input, install the result, change a config, or enable the flag.

## Exact identities

| Artifact | Git blob |
| --- | --- |
| Current runtime input, 33,885 bytes | `b952c9c228ecbde592bf3d2df01638677abb0d24` |
| Generated runtime result, 34,145 bytes | `2b2bd80e3fa76c61139bdbfeaa58dc8a8987339a` |
| Existing helper `r04_fast_tape_clone.py` | `b7c1fd2f7f786c5dc5f8a3b9a7116815ea40607a` |
| Existing helper suite `test_r04_fast_tape_clone.py` | `a292131f3a9b47c00d74585ca2691beb07fbb44a` |
| `port_current_runtime.py` | `4c7474062292feb25638ae0af5161e9d5382e6f5` |
| `test_current_runtime_port.py` | `475be4b8e31ceaab6179feb3eea626117edfe1e6` |
| `verify_current_runtime.py` | `045cebfb620a2fe20e3a2611c65f69032aa90bb5` |
| Frozen tape module | `a43289b9cc5e34a2481fddf652762a7d92f427ef` |

Generated runtime SHA-256: `5063e599f04a7f2ca35c9bc08a8718c6f4f3c1ed82e7e0713520d1e88fb2baaa`.

Current-runtime input was independently reconstructed from the retained Slack F0C18AXAL04 package by removing its V3-only additions. The resulting full Git blob matched the current GitHub source exactly; no approximate reconstruction was accepted. The tape bytes were independently recovered from that archive and authenticated. Current main also preserves those exact tape bytes at `candidates/v4/donor/overlay/r01_tapes.py`.

## Executed evidence

Local Python runs passed **20/20 helper tests plus 14/14 current-runtime tests**, separately in normal Python and `python -O`, with no corpus skip. Every one of the **9,347** frozen actions was compared through actual current `Features` and `TitanAgent` class code in three arms: unchanged baseline, port disabled, port enabled. Outputs and selected checkpoints matched, and mutable rows stayed detached.

The current-class harness substitutes the producer, clock, deadline timer and selected-consumer collaborators; it is not an engine/game benchmark. It exercises the actual class methods and exception paths. Tests cover default-OFF import isolation, preserved dataclass positional arguments, clone execution within the existing timer, internal alias preservation, cancellation during cloning without publishing a partial checkpoint, cancellation after a complete checkpoint, expired entry prelude, and propagation of a different timer's exception. Eight malformed/source-boundary mutations reject. A deliberate helper mutation returning its input instead of a copy makes the current-runtime suite fail in both normal and optimized modes.

**Not claimed:** full-engine games, packaged agent equivalence, economic improvement, whole-agent speedup, ON promotion, archive rebuild, or Kaggle submission. The input shape of this checkpoint is broader than a frozen tape row; the helper's deepcopy fallback is therefore retained for every unproved schema.

## Reproduce from cloud-execution-lab

```sh
P=candidates/v4/repairs/performance/fast-tape-clone
python "$P/verify_current_runtime.py" \
  --runtime titan_runtime.py \
  --tapes candidates/v4/donor/overlay/r01_tapes.py
```

The runner requires both authenticated inputs and executes normal and optimized suites in a temporary directory. Missing or changed inputs fail rather than skip. No fixture copies need to be added beside the preserved donor sources.

To materialize the reviewed source result for the current single-workspace integration gate, use a fresh output path:

```sh
python "$P/port_current_runtime.py" titan_runtime.py /tmp/titan-runtime-fast-clone.py \
  --expected-blob b952c9c228ecbde592bf3d2df01638677abb0d24
```

Any future materialized package must include the exact helper alongside its runtime and preserve the feature's false default. If current runtime changes, this receipt does not certify the new bytes: revalidate the adapter and combined package before promoting it. No broad legacy materializer execution is authorized by this component receipt.

## Main integration receipts

Adapter commit: `37d269892af5a68c9748333ec2477387ea3a88c3`.
Current-runtime suite commit: `964fbb690a7bf61807b2466a0dd713606b70a5a9`.
Mandatory-input runner commit: `0c2bf76f02662696fae6560a9f0282701fcb089e`.

Fresh main directory readback matched all three tested local Git blobs. Existing helper, donor suite, legacy recipe and its tests were not overwritten. Original deconfliction claim: #12431 comment `5642703480`; Slack main-channel claim `1789178114.731439`, execution handoff `1789178727.363809`.
