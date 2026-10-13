# UIOWA-107: research-deadline preparation walkthrough

**Fictional rehearsal, not a University of Iowa finding or an approved plan.**
No calendar entry, change deferral, staffing commitment, account operation or contact is made.

Original scenario, interval model, analyzer, renderers and 42-test suite: **OP5-KELVIN**, retained from commit `4af4e7cdabfc96692f4ab87f95ed2925397a13ff`. Finite-quantity repair, independent execution, six-case rehearsal and this walkthrough: **ZZ-ASTRA-RIVET / GPT-6 Astra Pro**, operation `uiowa107-followthrough-astra-rivet-20260919`.

The existing fictional RIS reporting path depends on shared IAM identity and an application change near a reporting window. The useful preparation question is not “which option wins?” It is: **what can be said under the stated capacity, what remains unresolved, and which evidence would change the interpretation?**

## Read this first

This document is independently usable as a worked review. Its publication on main does **not** establish that the separate executable package is integrated or has passed GitHub-hosted execution. The exact executed source objects and commands are recorded below; the accompanying source PR carries its current integration state.

The executable follow-through uses Kelvin's actual `Analysis`, CSV writers and Markdown renderer, not a replacement calculator. Six separate copies of the exact retained fixture change only named assumption records. The original fixture and all four original sample-output files stay byte-identical. Every new numeric what-if is labelled `ASSUMED`, not `MEASURED`; removing a quantity produces `UNKNOWN` with null bounds. Original deadline, dependencies, option descriptions and exclusions remain intact.

## The native baseline

All quantities below are fictional hours in the existing model. The shared identity wait `ASM-002` is unknown. Usable analyst capacity `ASM-003` is 32–40 in the retained fictional observation; possible extra capacity `ASM-006` is only assumed at 0–16.

| Option | In-window exposure | Available capacity | Native verdict |
| --- | --- | --- | --- |
| A: proceed | 20–unbounded | 32–40 | NOT_DETERMINED |
| B: defer the change | 2–2 | 32–40 | FITS |
| C: proceed with rehearsed rollback | 16–unbounded | 32–40 | NOT_DETERMINED |
| D: proceed with temporary capacity | 20–unbounded | 32–56 | NOT_DETERMINED |

B has lower modelled in-window exposure than the three proceed options. That is **not** approval to defer: the cost of remaining on the old version and downstream dependencies are explicitly outside its calculation. A and D have the same exposure; adding people changes capacity, not the modeled amount of work and wait.

## Six actually executed cases

`NOT_DETERMINED` is abbreviated ND in this table only; the emitted data retains the complete state. These are separate hypothetical scenarios, not successive evidence collection or an evolving real schedule.

| Case | Explicit edits from the original | A | B | C | D |
| --- | --- | --- | --- | --- | --- |
| baseline | None | ND | FITS | ND | ND |
| wait-bounded | Assume IAM wait 0–2 | ND | FITS | FITS | ND |
| capacity-added | Assume IAM wait 0–2 and 16 usable temporary hours | ND | FITS | FITS | FITS |
| peak-window | Assume IAM wait 0–2 and only 8–12 usable analyst hours | AT_RISK | FITS | AT_RISK | ND |
| capacity-unknown | Remove the analyst-capacity observation; IAM wait remains unknown | ND | ND | ND | ND |
| long-wait-peak | Assume IAM wait 20–24 and usable analyst capacity 8–12 | AT_RISK | FITS | AT_RISK | AT_RISK |

**Bounding one input does not finish the decision.** In wait-bounded, A and D have exposure 20–46, still overlapping the original 32–40 capacity; C is 16–28 and fits. In capacity-added, D's 48–56 capacity exceeds its 20–46 exposure, but A and D still cannot be separated on exposure alone. These arithmetic statements do not confirm temporary funding or rollback feasibility.

**Lower exposure is not sufficient capacity.** Removing the capacity observation makes even B NOT_DETERMINED. B remains lower-exposure than the proceed options. Converting that comparison into a capacity guarantee would be a mistake.

**The peak-window case makes the staffing question concrete.** A's minimum exposure is 20 and C's is 16, both above the assumed capacity maximum of 12. D's assumed 8–28 capacity still overlaps 20–46 exposure, so it cannot be presented as a guaranteed rescue. In long-wait-peak, A/D exposure becomes 40–68 and C becomes 36–50; all three exceed even their best available capacity in this scenario.

## Preparation choices and the evidence needed

The following is an internal review worksheet. The role names are responsibility categories in the fictional scenario, not identified University contacts or assignments to real people.

| Preparation question | Relevant scenario link | Evidence to obtain in an authorized assessment | What the evidence would and would not establish |
| --- | --- | --- | --- |
| Can the IAM wait be bounded in the reporting window? | DEP-IDENTITY, IAM, ASM-002 | A stated freeze/change window, escalation path and interval basis from the service owner | Permits a bounded what-if. Does not establish that RIS may change or bypass IAM. |
| Who can defer the application change? | DEP-APPCHANGE, RIS, option B | Change authority, notice requirements and downstream-impact review | Establishes the decision route; B's two-hour exposure alone cannot approve deferral. |
| How many usable analyst hours remain during the peak? | ASM-003, A/B/C/D | Window-specific roster, concurrent obligations, availability and skill coverage | Supports a usable-capacity interval rather than a headcount proxy. Does not guarantee execution. |
| Is the rehearsed rollback operationally possible? | ASM-004, option C | A verified rollback procedure and recovery evidence covering the reporting state | Tests C's central feasibility exclusion. The six-case arithmetic does not execute a rollback. |
| Is temporary capacity funded, available and usable? | ASM-006, option D | Funding decision, availability, permissions, training and ramp-up assumptions | Supports a capacity claim; it does not reduce exposure or create an appointment. |
| Are the quantities comparable? | All summed exposure and capacity terms | Definitions separating elapsed wait, labor effort and available service time | Determines whether the present additive model is appropriate before using it for a real deadline. |

The original model adds identity waiting time and labor effort. Both are labelled hours, but that does **not** prove they are interchangeable resources. C is described as rehearsing before the window while its rehearsal effort is included in the additive exposure. This rehearsal preserves that existing model; it does not silently reinterpret the time window or validate those modeling choices. A real timeline or staffing conclusion needs those distinctions resolved first.

## Run the reproducible package

In an isolated cloud checkout containing the exact source generation:

```sh
cd revenue/uiowa_rfq_18649_deadline_continuity
python -m unittest -v test_continuity test_quantities test_rehearse
PYTHONOPTIMIZE=1 python -O -m unittest -v test_continuity test_quantities test_rehearse
python rehearse.py --outdir /tmp/uiowa107-new-rehearsal
```

The destination must not exist. Select another new path for another run. The command has no network dependency and makes no calendar/provider calls.

Read `START_HERE.md`, then each named case's `input.json` and `continuity_report.md`. Each case also contains `continuity_analysis.json`, `continuity_options.csv` and `evidence_requests.csv`. Across six cases there are 30 case files, plus `summary.json`, `START_HERE.md` and `manifest.json`: **33 files**. The manifest binds the exact input fixture, three source files and the other 32 outputs using byte counts, SHA-256 and Git blob IDs. It deliberately does not hash itself.

The wrapper refuses existing directories, files and final-path symlinks. A later I/O failure retains its new partial directory with `.incomplete`; such output is not successful completion. The output directory must remain operator-controlled. This is not an atomic multi-file transaction, crash-durability guarantee or defense against hostile concurrent directory replacement. The original `continuity.py --outdir` writer is unchanged and can overwrite prior files; use it only with a fresh scratch destination. The create-new protection belongs to `rehearse.py`, not to an asserted repair of that legacy CLI.

## Finite-quantity repair and measured validation

Actual predecessor execution accepted Boolean capacity and turned `true` into one hour. It accepted NaN and infinity; infinite measured capacity made B FITS. A numeric string raised TypeError rather than the controlled quantity error.

The existing `intervals.py` now requires exact built-in, finite, non-Boolean integers or floats for bounds and multipliers. The admitted numeric domain must be float-representable because the retained human-readable renderer uses `%g`; oversized integers are refused rather than allowed to fail during rendering. Accepted values are not coerced. Arithmetic overflow is rejected at result construction. Every non-UNKNOWN assumption is checked, even when unused by an option. A null upper bound remains the distinct unbounded state. UNKNOWN records still may not carry numbers.

This is a quantitative-contract repair, **not a general-purpose hostile-input or model-correctness certification**. The original comparison formula and strict interval boundary remain unchanged: touching ranges are NOT_DETERMINED. The original conservative zero-multiplier/unbounded behavior and exposure-only pair comparison are not redesigned here. Mixed units, arbitrary input structures, dependency authenticity and correlated-uncertainty optimization need their own contract; none is asserted solved by finite-number checks.

Executed on CPython 3.13.5 / Linux x86_64, standard library only:

```text
Original source: 42 tests normal — OK; 42 optimized — OK.
New quantity suite against original source: 16 tests;
FAILED (failures=23, errors=11), including subtests.

python -m unittest -v test_continuity test_quantities test_rehearse
Ran 76 tests in 8.651s
OK

PYTHONOPTIMIZE=1 python -O -m unittest -v test_continuity test_quantities test_rehearse
Ran 76 tests in 8.600s
OK
```

No skips in the 76-test runs. Counts are 42 unchanged original methods, 16 quantity methods and 18 rehearsal methods, not 152 distinct tests. Optimized execution propagates to real CLI children. The six native CLI replays agree with wrapper outputs; all 33 complete-bundle files are byte-identical between separately executed normal and optimized runs. An independent endpoint calculation checks both intervals for all 24 option/case combinations. A separate 100-pair finite grid checks the unchanged verdict arithmetic. All six source/test modules pass `py_compile`.

Exact executed Git blob identities:

| Object | Git blob |
| --- | --- |
| Unchanged continuity.py | efdaacc9c7ca9f1428a7e224cd0ad74de6177f42 |
| Repaired intervals.py | b6ea95923e1436082c881570649d9faf3f35ab7c |
| rehearse.py | 24157dd723808aa828134318ac5382195deac6d1 |
| Unchanged test_continuity.py | 78867f8e9be6f9e8a5211d07f28a9b3229f000d4 |
| test_quantities.py | eaa604d0d25d8be917f8b6f7a3a29e2ff18e758f |
| test_rehearse.py | cf3c201f9eac9c77b4d55fc3553f63c8d2f9add2 |
| Original fictional fixture | 889aaff4f90658091902db0249161bff66a935a4 |

The original generated Markdown, JSON and two CSVs were regenerated and independently matched to their retained provider blob IDs before the original stale-sample tests ran. These are actual exact-component executions, not a full-repository checkout or GitHub Actions success.

## Remaining integration seam

The six-case runner exercises the existing UIOWA-107 analyzer and renderers. It does **not** claim execution of the separate seasonal-capacity, ownership or continuity specialist engines mentioned by the broader work order. The worksheet above identifies their required inputs; a subsequent integration must read their actual schemas, preserve the native service/assumption identities and execute their real entrypoints. Merely sharing join-key vocabulary is not an executed integration.

Source and current-main/provider execution remain separate authorities. This document records a completed finite-number repair and reproducible case analysis without claiming the entire broader order, a University assessment, hosted CI or a production deployment is complete.
