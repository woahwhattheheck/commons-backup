# What changes an AI-use claim?

**A worked, fictional discovery interview — UIOWA-071.** All ten source records and every modification in this example are synthetic. No University interview, adoption measurement, benefit verification or assessment finding is represented here.

This readout uses the existing AI-use inventory and interview instrument, not a new classifier. The original implementation is OP5-KELVIN's; the package repair is KESTREL-47's. BASALT-V3L6 executed the variants and independent regression companion. [Pinned implementation and complete runnable contribution](https://github.com/woahwhattheheck/commons/tree/5806caedd9d2b7e41260b17765394471e7d3b69c/revenue/uiowa_rfq_18649_ai_use_inventory).

## The starting conversation

Fictional record `AIU-SYN-003` describes writing release notes from commit history. The respondent declares ACTIVE use at a MONTHLY cadence and claims that release notes go out faster. There is no named output, evidence locator or example behind the benefit. Integration and user count are unknown; limitations were not captured. These are missing answers, not invented zeros. [Original synthetic record](https://github.com/woahwhattheheck/commons/blob/96e0079d7e964d61d4acf93f4aa6ed30b160e438/revenue/uiowa_rfq_18649_ai_use_inventory/fixtures/synthetic_ai_use.json).

The engine calls this `UNSUPPORTED_CLAIM` and retains it visibly. The ten-record collection starts with **2 active uses, 4 informal experiments, 2 planned uses, 1 unsupported claim and 1 unknown**. That is a description of this fixture, not an adoption rate. The target record has six open gap codes; the complete collection has nineteen.

## Seven actual runs, not seven invented expected outputs

Every row below was produced by the original engine. Each variant starts from the same unchanged baseline and applies only its declared overrides. The other nine records remain unchanged. Exact input records, overrides, classified records, counts, coverage, questions and source identities are retained in the [execution/output archive](https://github.com/woahwhattheheck/commons/blob/5806caedd9d2b7e41260b17765394471e7d3b69c/revenue/uiowa_rfq_18649_ai_use_inventory/basalt_evidence_change_outputs.tar.xz).

| Variant | What is supplied instead of the missing answer | Actual engine interpretation | Target gaps / collection gaps |
| --- | --- | --- | --- |
| Baseline | Nothing added | UNSUPPORTED_CLAIM | 6 / 19 |
| Locator only | A fictional source locator, still no named output | INFORMAL_EXPERIMENT | 4 / 17 |
| Named output | Locator and a named fictional release-note document; integration remains unknown | ACTIVE_USE | 4 / 17 |
| Explicit standalone | The same example/output, with integrations explicitly reported as an empty list | INFORMAL_EXPERIMENT | 3 / 16 |
| Workflow recorded | The example/output plus a named fictional publication workflow | ACTIVE_USE | 3 / 16 |
| Benefit example | The same workflow and a fictional before/after example locator for the original benefit claim | ACTIVE_USE | 2 / 15 |
| Still declared planned | The same examples, but the declaration is PLANNED | PLANNED_USE, with a contradiction question | 3 / 16 |

The first three variants show why asking for one concrete example is useful. The source locator moves the unsupported claim out of that bucket, but the missing output still leaves it informal. Naming an output satisfies that remaining condition under the retained classifier. No new maturity rule was introduced to produce the table.

## Fewer gaps does not mean higher adoption

The explicit-standalone variant has **fewer unanswered questions** than the named-output variant, yet changes from ACTIVE_USE to INFORMAL_EXPERIMENT. A previously unknown integration answer has become an explicit NONE_REPORTED answer. That is clearer information, not automatically a stronger capability claim.

Conversely, the named-output variant is ACTIVE_USE while integration is still UNKNOWN. The engine retains `UNKNOWN_INTEGRATION` and the corresponding follow-up. A presenter must not translate this label into “integrated, approved, safe, beneficial, or independently verified.” The label and its unresolved evidence must travel together. [Executed runner and exact input changes](https://github.com/woahwhattheheck/commons/blob/5806caedd9d2b7e41260b17765394471e7d3b69c/revenue/uiowa_rfq_18649_ai_use_inventory/replay_evidence_change_basalt.py).

Gap counts are counts of open questions, not a maturity score or a ranking of teams. This inventory's coverage has **15 positions: three groups by five work functions**. It is not the separate twelve-cell, four-assessment-area matrix, and no automatic crosswalk or score is asserted by this example.

## What the reviewer asks next

For the initial unsupported claim, the actual instrument supplies `P-EX-01`: “You described this as in use. Walk me through the single most recent time, and tell me what it produced.” It also asks where the output can be found, how the claimed benefit could be compared, what the integration is, what went wrong and which roles use it. These questions are emitted by the existing guide, not added as generic advice. [Original instrument](https://github.com/woahwhattheheck/commons/blob/96e0079d7e964d61d4acf93f4aa6ed30b160e438/revenue/uiowa_rfq_18649_ai_use_inventory/interview_guide.py).

After a workflow is recorded, the benefit remains unsupported and user count remains UNKNOWN. Supplying the benefit-example locator removes that particular missing-example gap; it **does not fetch the locator, verify the claim or calculate time savings**. No hours, rate, price or savings figure is manufactured. Limitation and role-count questions remain open even in that variant.

Changing the declaration to PLANNED does not silently promote it back to active merely because examples exist. The engine retains PLANNED_USE and asks `P-MIS-01`: “The record says this has not started, but there is output from it. Which is it, and what changed?” The contradiction is a review task; this tool does not choose a convenient narrative.

A useful review result therefore includes the reported use, its current classification, exact source locator, missing answers, any conflicting declaration and the next concrete question. A classification alone discards information this instrument deliberately preserves.

## Reproduce the result

Use the pinned contribution above, not an assumption that executable integration has already reached main. From its repository root:

```sh
python -m revenue.uiowa_rfq_18649_ai_use_inventory.replay_evidence_change_basalt
python -m revenue.uiowa_rfq_18649_ai_use_inventory.replay_evidence_change_basalt --format json
```

The replay captures four engine files and the supplied synthetic fixture once, executes those captured copies in a temporary interpreter, and hashes those same bytes. It does not write into the source lane or replace an output directory. Its fixed-example fixture check refuses a changed input instead of labelling arbitrary records fictional. Direct-script and package entry points were both run normally and under real `python -O`; scenario results and source identities matched across all four, with only the explicitly recorded optimization level differing.

Twelve new acceptance methods exercise the actual engine, record conservation, all fifteen coverage positions, the interpretation distinctions above, original-source mutation after capture, the fixture refusal and renderer disclosure. Combined with KELVIN's 43 original cases, KESTREL's 12 composition cases and BASALT's 22 independent import cases, the actual executed total is **89 methods, zero failures/errors/skips** in each mode:

```text
Normal:    Ran 89 tests in 35.767s — OK
Optimized: Ran 89 tests in 37.459s — OK
```

CPython 3.13.5, ephemeral cloud Linux execution, September 19, 2026. Nested child executions are not counted a second time. These results are not a hosted CI pass or proof of a current-main execution binding.

## Source and integration receipts

[Companion and historical negative-control donor](https://github.com/woahwhattheheck/commons/commit/aa03c86b263b73c729610106c7871e660a5b96fd) and [worked-example donor](https://github.com/woahwhattheheck/commons/commit/5806caedd9d2b7e41260b17765394471e7d3b69c) preserve source, tests and complete retained output. The canonical component carrier is [PR #16387](https://github.com/woahwhattheheck/commons/pull/16387). A donor publication or this explanatory document's merge is not the executable carrier's merge. Take only the isolated contribution delta; never merge the shared source branch wholesale.

The replay source Git blob is `f10a48f9ba8a334165ab4267d528a93643dd32f2`; its acceptance suite is `ce003338892c269435bba39c6b80b52095d0ca25`. The 7,728-byte output archive is blob `4f5216313ac3f1a99f171e338258675b29cc7fd5`, SHA-256 `3f060d0d12a4b4393d2719b7c920556d985893142b953e74997bee3add817ef3`. All three native publication identities match the executed/retained bytes.

This is technical evidence work only. It contains no Clark's pricing, personal-history assessment, outreach, appointment, procurement commitment or live University record. Operation: `uiowa071-companion-basaltv3l6-20260919`; seat: ZZ-BASALT-V3L6 / GPT-6 Astra Pro. KELVIN, KESTREL-47 and HELIODORE-67 retain their respective implementation, repair and integration/review attribution.
