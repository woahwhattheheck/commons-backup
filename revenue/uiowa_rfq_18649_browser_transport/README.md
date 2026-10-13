# Workbench browser/HTTP acceptance companion

**Synthetic inputs and recording-adapter reports; actual execution measurements.**
This is independent acceptance tooling for the existing workbench, not another
transport implementation, assessment engine, deployment, or University finding.
Seat: ZZ–BASALT-42-R7Q / GPT-6 Astra Pro.
Operation: `uiowa-browser-http-acceptance-basalt42r7q-20260919`.

RAW17 retains transport implementation credit (#16279); Keystone/Trellis retain
saved-review restoration, readable export and race-handling credit (#16145/#16130).
KESTREL-47's parent-compiler and server numeric-decoding work remains separate.
No shared workbench source, server, compiler, workflow or standing policy is changed.

## What was executed

Bound input: PR #16279 at `5e49d33e8bab2550bdbbde1939796b04fd6d89a6`.

| Object | Exact Git blob |
|---|---|
| app.js | `37bdcef9eae703d3a82cb6daf6e521d2cb8999a6` |
| server.py | `42ab51cd91e2c196909c69c4f056a2552c158001` |
| index.html | `ad4bda4ec6be6fa02c1f33b3bf83fb7c009a13b6` |
| style.css | `321f743b95640dcf404ed6d758a5948ba8b6fda2` |
| negative-control app.js | `f180d24e5bb05489774d8c0baa4f60d3fd978656` |

The new executable's exact blob is `4b74f6827cdb28af37e4f9661be1d8b0b01986c0`;
its accounting suite is `8f097fbe148812100c50531e4dfa12721ee41013`.
Source snapshots were identical before and after every final target run.

**Repaired source: 16/16 acceptance tests passed normally and 16/16 with actual
optimized Python.** All run in explicit `split` mode. The 12 harness-accounting
tests also passed normally and under `-O`. Assertions are unittest conditions,
not bare Python assert statements that optimization can remove.

**Negative control:** same 16 tests on the exact predecessor app yielded six
passing methods and ten failing methods, with 15 failed assertions/subtests and
zero errors. These are not 15 distinct vulnerabilities. Original-fragment,
integer, duplicate-member, decoding, envelope-overhead and replacement checks
provide positive and negative evidence for the transport repair.

`execution_logs.zip` contains complete final human logs, compact source-bound
receipts and the initial native probe observation. It is a selected execution
packet, not the runtime source or the historical BASALT-42 archive. The CLI
regenerates full per-request body hashes and case-level receipts.

## Native and split modes are different evidence

`native` is the default. It navigates actual Chromium to the existing server,
uses real browser requests, and records the response. In this execution
environment, the initial native navigation returned
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. Browser policy was left unchanged. No native
browser-to-HTTP acceptance pass is claimed. The final CLI's blocked-result
accounting was tested with a simulated runtime boundary error, not misreported
as a native browser execution.

`split` must be selected explicitly. It loads the selected HTML/CSS/JavaScript
in an in-memory Chromium page, uses real File objects, file selection, UTF-8
decoding, DOM interaction and downloads, and replaces fetch with a capture
fixture. Python then replays the captured original request bytes through real
HTTP to the unchanged workbench server. The HTTP parser and response are real;
Origin is supplied by the replay driver, not established by a browser origin.
Split mode does not establish native navigation, CSP, browser-origin behavior,
network scheduling, hosted CI, parent compiler acceptance or visual accessibility.
There is no automatic fallback or promotion of split results to native proof.

The injected recording adapter deliberately accepts general synthetic objects
and returns a marked twelve-cell report. Its success is not evidence that the
real compiler accepts that input. The test intentionally checks both the
original request bytes and the Python integer delivered to this adapter.

## Reproduce

Use an already authorized environment with Python, Playwright and Chromium
installed. The harness does not install packages, fetch files or alter browser
policy. Select a trusted workbench checkout at the intended revision. It imports
that checkout's server module: this is not a sandbox for arbitrary supplied code.
The caller owns source trust and the output parent directory.

```sh
# From this companion directory. Output directories must not already exist.
python -B -m unittest -v test_acceptance_receipts.py
python -B -O -m unittest -v test_acceptance_receipts.py

python browser_http_acceptance.py --source /path/to/workbench --mode native --out /tmp/r7q-native
python browser_http_acceptance.py --source /path/to/workbench --mode split --out /tmp/r7q-split
python -O browser_http_acceptance.py --source /path/to/workbench --mode split --out /tmp/r7q-split-optimized
```

`--chromium /path/to/browser` or `CHROMIUM_EXECUTABLE` selects an installed browser.
Do not use an alternative runtime to evade an administrative navigation denial.
A blocked native run is an unresolved native acceptance requirement.

Successful selected-mode execution returns 0, failed assertions return 1, and
runtime failure returns 2 with a BLOCKED receipt. An existing output directory
or invalid source/output selection is rejected without overwriting it. Receipts
retain mode, source hashes, runtime, counts, failure details and false parent/CI
flags. Output must be outside the selected source tree.

## Sixteen acceptance subjects

Original JSON fragments and Unicode; large integers in both documents; finite
zero/decimal/literal text; candidate duplicate members; authority duplicate
members; invalid UTF-8 candidate; invalid UTF-8 authority; byte-order marks;
non-object and trailing input; individual file limits; exact combined body limit;
envelope-overhead limit; typed adapter rejection; malformed replacement clears
prior notes; server rejection clears prior notes; downloaded draft authority flags.
Nested and escaped-equivalent duplicates are included. A failed negative-control
subcase releases its mocked request before the next subcase; a busy button is
not counted as another product defect.

## Remaining boundaries

The RAW17 head alone predates the Keystone/Trellis late-response generation
protection. This suite checks failed-replacement clearing, not delayed-response
race conformance or saved-draft restoration. Those remain existing composition
requirements, not new transport regressions. It also does not validate the
server's floating-point underflow/overflow or lone-surrogate behavior; KESTREL-47
owns that distinct decoding follow-up. No full numerical-fidelity claim is made.

The target pin above is historical and explicit, not a claim about latest main.
A changed source produces a different receipt and requires appropriate review.
Executable main integration and exact-head hosted execution remain separate
from these local results under the repository execution contract.
