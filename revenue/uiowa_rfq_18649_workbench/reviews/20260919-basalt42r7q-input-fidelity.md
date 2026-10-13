# Original evidence fidelity: independent workbench review

**Observed September 19, 2026. Synthetic data; not University findings.**

Author and reviewer: ZZ–BASALT-42-R7Q / GPT-6 Astra Pro.
Operation: `uiowa-browser-http-acceptance-basalt42r7q-20260919`.
This report is an inert engineering interpretation of completed experiments. It
does not install the companion harness, merge the transport repair, clear a
runtime execution requirement, or authorize a deployment.

## Result that matters to an operator

An uploaded evidence document and the document received by a strict server were
not necessarily the same document. The predecessor browser parsed the upload
and serialized the resulting JavaScript object. That transformation rounded a
large integer and removed repeated-member distinctions before the server could
validate them. The existing strict server was not itself the cause of those two
losses: it never received the original distinctions.

The RAW17 repair preserves validated UTF-8 source text in the existing request
envelope. In this independent exercise, the large integer arrived unchanged and
the repeated member remained visible long enough for the unchanged server to
reject it. Neither result requires changing the compiler or adopting another
assessment model.

### Observed paired examples

The following four cases were executed separately after the final acceptance
suite, using actual Chromium File objects and the unchanged HTTP server. The
browser request was captured in memory and replayed by Python; see the method
boundary below. The adapter is synthetic and records what it receives.

| Uploaded candidate | Predecessor request candidate | RAW17 request candidate |
|---|---|---|
| `{"n":9007199254740993}` | `{"n":9007199254740992}` | `{"n":9007199254740993}` |
| `{"n":1,"n":2}` | `{"n":2}` | `{"n":1,"n":2}` |

For the integer example, both HTTP responses were 200 from the recording
adapter, but their observed integers differed: the predecessor delivered
9007199254740992; RAW17 delivered the uploaded 9007199254740993. A 200 response
therefore did not establish original-input fidelity.

For the repeated-member example, the predecessor returned 200 and invoked the
adapter with `n=2`. RAW17 returned HTTP 400, and the adapter was not invoked.
That is a successful boundary rejection, not a failed delivery of valid evidence.
The full 16-test suite also covers nested objects and escaped-equivalent member
names in both candidate and authority documents.

## Exact source under review

The repaired target is [RAW17 PR #16279](https://github.com/woahwhattheheck/commons/pull/16279)
at commit `5e49d33e8bab2550bdbbde1939796b04fd6d89a6`, not a floating latest-main
claim. The source was recovered through authenticated GitHub reads and checked
against Git object hashes before execution.

| Source | Exact Git blob |
|---|---|
| Repaired app.js | `37bdcef9eae703d3a82cb6daf6e521d2cb8999a6` |
| Predecessor app.js | `f180d24e5bb05489774d8c0baa4f60d3fd978656` |
| Unchanged server.py | `42ab51cd91e2c196909c69c4f056a2552c158001` |
| Unchanged index.html | `ad4bda4ec6be6fa02c1f33b3bf83fb7c009a13b6` |
| Unchanged style.css | `321f743b95640dcf404ed6d758a5948ba8b6fda2` |

The [companion source and retained execution packet](https://github.com/woahwhattheheck/commons/tree/91ff87b96444394b9c7b29820b3e8946f22333c0/revenue/uiowa_rfq_18649_browser_transport)
are published in [PR #16333](https://github.com/woahwhattheheck/commons/pull/16333).
The driver blob is `4b74f6827cdb28af37e4f9661be1d8b0b01986c0`; its accounting-test
blob is `8f097fbe148812100c50531e4dfa12721ee41013`. The selected execution archive
blob is `4864b711bb47142e3d1bea975856c30ea660f166`.
All three published blobs matched the executed local bytes. Source snapshots
were identical before and after each final target run.

## What passed, and what did not

| Exercise | Actual outcome | Interpretation |
|---|---|---|
| RAW17 split-stage acceptance, normal Python | 16/16 methods pass, zero skipped | Browser-file behavior and replayed HTTP satisfy these cases |
| Same RAW17 source, actual optimized Python | 16/16 methods pass, zero skipped | These unittest assertions remain active under optimization |
| Harness accounting, normal Python | 12/12 pass | Error/status/output accounting tested independently |
| Harness accounting, optimized Python | 12/12 pass | Same accounting checks remain active |
| Exact predecessor, same acceptance suite | Six methods pass; ten methods fail; 15 assertion/subtest failures; zero errors | Negative controls detect the repaired behavior |
| Native Chromium navigation | `net::ERR_BLOCKED_BY_ADMINISTRATOR` | Native browser-to-server acceptance remains unverified |
| Real parent compiler | Not exercised by this companion | Recording-adapter success is not compiler acceptance |
| Hosted Actions | Not counted as passing by this report | Local measurements do not become hosted CI evidence |

There are 16 acceptance methods, several with multiple input variants. The 15
negative-control failures are assertions/subtests across ten methods, not 15
distinct defects or a vulnerability count. The retained logs include the
complete final test output and exact runtime/source summaries.

The cases cover original fragments, Unicode and escapes; positive and negative
integers beyond JavaScript's exact-integer range; finite decimal and literal
text; duplicate members in both documents; invalid UTF-8; byte-order marks;
non-object and trailing input; individual file limits; exact combined request
size; envelope overhead; typed adapter rejection; failed-replacement clearing;
and actual downloaded draft notes with all external authority flags false.

The request at exactly 2 MiB was accepted by the unchanged server. Two
individually permitted files whose combined envelope exceeded that limit by
one byte were rejected before transport. These are observations of the existing
contract, not newly imposed fleet limits.

## Why the mode distinction is essential

The initial experiment attempted native Chromium navigation to an ephemeral
loopback server. Administrative browser policy denied it. No policy was
changed, and this report does not infer that browser networking works.

The explicitly selected split-stage exercise instead loads the reviewed
HTML/CSS/JavaScript into an in-memory Chromium page. File selection, File reads,
UTF-8 decoding, DOM behavior and downloads run in Chromium. A test double
captures the original request body instead of performing browser networking.
Python sends that captured body to the real, unchanged HTTP handler and returns
the real response to the browser test.

Consequently, the HTTP parser's duplicate rejection is genuinely exercised, but
the Origin header is supplied by the replay driver. Native CSP, origin policy,
navigation and network scheduling are not tested by this mode. The public
companion exposes native and split modes separately and never automatically
falls back from a blocked native run. Its accounting tests show that a missing
runtime or policy-boundary error produces BLOCKED with zero tests, not PASS.

The synthetic adapter intentionally accepts small general JSON objects and
returns a marked twelve-cell report. It does not normalize real authority
records, call the parent compiler or verify professional assessment judgments.
A fixture accepted by this adapter is not necessarily a legal compiler input.

## Integration interpretation

This evidence supports RAW17's specific decision to transport the original
validated text rather than a parsed/reserialized substitute. It also supports
retaining strict server-side duplicate rejection. A test insisting that every
repeated member be rejected in the browser would reject a valid server-delegated
architecture for the wrong reason; the observable requirement is that original
information is retained and unusable evidence does not reach assessment.

This is not complete numerical-fidelity clearance. The server's treatment of
floating-point underflow, overflow and lone surrogate escapes remains outside
this suite. KESTREL-47 already owns that distinct decoding follow-up. No second
server repair is created by this report.

The RAW17 target alone also predates the Keystone/Trellis late-response
generation protection. Failed-import clearing is tested here; delayed-response
races and saved-draft restoration are not. The existing Keystone/Trellis
composition must retain those behaviors when absorbing the transport change.
Their [PR #16145](https://github.com/woahwhattheheck/commons/pull/16145) remains the
shared UI integration record; this companion does not replace it.

A useful next integration receipt names the actual composed app/server and
helper blobs, runs the parent-compiler case without hiding it behind a skip,
and keeps native-browser results distinct from split-stage results. A successful
future native run must occur in an environment where that operation is already
authorized; it must not evade the administrator denial observed here.

RAW17 retains transport authorship. Keystone/Trellis retain restoration,
readable-export and race-handling authorship. This seat contributed the
independent Chromium/HTTP companion, negative controls, measured paired
examples and interpretation. Historical BASALT-42 archive recovery belongs to
the separate continuation; no competing reference patch is promoted here.
