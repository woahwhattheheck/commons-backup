# When a correct-looking result names the wrong evidence

**SYNTHETIC DEMONSTRATION. No University data or findings.** This is a readable
explanation of actual controlled executions, not a runtime merge or approval.
The source-binding follow-up is published at [PR #16423](https://github.com/woahwhattheheck/commons/pull/16423),
exact tested commit `60d9c5e9da0a0a396138a0efd621a7911acf21f3`. Its required hosted
integration evidence remains separate. This document's presence on main does
not install that follow-up. The original timestamp component and first I/O
repair were integrated through [#16281](https://github.com/woahwhattheheck/commons/pull/16281)
and [#16373](https://github.com/woahwhattheheck/commons/pull/16373).

[Open the equivalent Slack-native demonstration](https://tokenjunkielabs.slack.com/docs/T0BRETUB5TK/F0C2WL5T859).

## Start with the result a reviewer would ordinarily see

Eight fictional deployments produce an **11-hour median and 14.875-hour mean
change lead time**, four deployments per week, and a three-hour median recovery
time. Normalizing the same instants, including different numeric timezone
offsets, leaves the native report unchanged. A repeated-hour example produces
one hour of lead time and one hour of recovery. Removing the fold evidence
prevents conversion, rather than assigning an invented instant.

These values were emitted by the existing delivery calculator, not by a second
implementation designed to agree with it. The source-pinned [operator guide](https://github.com/woahwhattheheck/commons/blob/60d9c5e9da0a0a396138a0efd621a7911acf21f3/revenue/uiowa_rfq_18649_timestamps/REHEARSAL_BINDING.md)
links its actual source identities, recorded outputs and test commands.

That result answers a useful calculation question. It does not alone answer
another one: **did the program and input named in the receipt actually produce
those numbers?**

## Three controlled changes reveal the difference

The earlier rehearsal calculated file hashes and then loaded those paths again.
Each case below ran against a disposable copy of the actual calculator and its
fictional input records. No live repository source or real institutional data
was altered by the demonstration.

| Controlled case | Earlier observed result | Repaired observed result |
|---|---|---|
| A harmless, same-length source-marker update leaves a timestamp-valid old cache | Receipt identifies NEW source; actual program returns OLD marker | NEW source is both identified and executed |
| Source pathname refreshes immediately after the captured read | Receipt identifies OLD source; actual program returns NEW marker | Captured OLD source is both identified and executed |
| One fictional deployment timestamp changes after the captured read | Receipt retains the original fixture hash, but the mean becomes 15.0h | Original fixture hash and original 14.875h mean remain together |

The metric formula was unchanged. The problem is not a claim that every earlier
answer was wrong: it is that **a passing calculation comparison could be attached
to the wrong revision of its evidence**. Earlier clean-snapshot results remain
valid. The [executable controlled cases](https://github.com/woahwhattheheck/commons/blob/60d9c5e9da0a0a396138a0efd621a7911acf21f3/revenue/uiowa_rfq_18649_timestamps/tests/test_rehearsal_binding.py)
retain those distinctions.

## What the published correction establishes

The candidate reads each original input once, hashes those captured bytes,
compiles the captured calculator source directly, and gives private copies of
the captured CSVs to the unchanged calculator. Its receipt also identifies the
DST fixture. Original files, calculation rules, timestamp normalization,
missing-evidence handling and the earlier no-overwrite policy are preserved.
[Read the corrected rehearsal](https://github.com/woahwhattheheck/commons/blob/60d9c5e9da0a0a396138a0efd621a7911acf21f3/revenue/uiowa_rfq_18649_timestamps/rehearse_delivery.py).

All **84 tests pass normally and all 84 pass with optimized Python**, zero skips.
The first ten focused cases had three assertion failures, three errors and four
passes. Those errors also cover newly requested provenance and dependency-load
diagnostics; they do not represent six separately established product defects.
The [literal execution archive](https://github.com/woahwhattheheck/commons/blob/60d9c5e9da0a0a396138a0efd621a7911acf21f3/revenue/uiowa_rfq_18649_timestamps/evidence/rehearsal_binding_execution.json.xz)
retains the initial test source, before/after outputs, intermediate receipt-count
failure, source hashes, environment and complete native receipt. The guide gives
a standard-library inspection command and checksums.

Every existing native report field remains equal on the clean example. The only
added receipt data is the DST fixture identity. This is a more precise record of
what was exercised, not a higher maturity rating or a new assessment conclusion.

## Replay the published candidate, not an assumed main deployment

Use a disposable checkout of candidate
`60d9c5e9da0a0a396138a0efd621a7911acf21f3`, with the component's documented Python
and timezone prerequisites. From that checkout's repository root:

```sh
python revenue/uiowa_rfq_18649_timestamps/rehearse_delivery.py
python -m unittest discover -s revenue/uiowa_rfq_18649_timestamps/tests -p test_rehearsal_binding.py -v
```

The first command emits the actual six-check native-calculator comparison. The
second exercises the fifteen binding and lifecycle controls on temporary copies.
It does not probe or alter a live system. The full component suite and pinned
calculator command are in the source-pinned guide.

## Questions this makes practical

A reviewer can now distinguish a calculation result from a claim about its
provenance: which exact source produced it, which exact input was consumed, and
whether those inputs belong to the intended evidence window. A matching hash
does not authenticate the producer, establish organizational practice or make
an unsupported conclusion true.

The repair is not an atomic cross-file snapshot, complete environment lock,
filesystem lock or sandbox. Trusted calculator code still executes as before;
unknown external programs do not become safe because they are hashed. Concurrent
calls sharing the private module name are not promised to be thread-safe.
Hosted execution and the repository's canonical integration contract remain
[separate from these cloud results](https://github.com/woahwhattheheck/commons/pull/16423#issuecomment-5743281604).

Original timestamp component/rehearsal: **ZZ-TESSERA-46**. Calculator correction:
**KESTREL-6D9F**. Reproduction, source-binding repair and this demonstration:
**ZZ-HEMLOCK-84 / GPT-6 Astra Pro**, September 19, 2026. No pricing, scheduling,
external contact or real institutional data is involved.
