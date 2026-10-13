# Incident-learning review explorer

A read-only, single-file browser companion to the **existing UIOWA-067 incident-learning kit**. It makes incident histories, corrective work, replacement decisions and source excerpts inspectable without installing a web service. It is not a second assessment engine, a maturity model, or a new command board.

View implementation: **ZZ-LANTERN-47R / GPT-6 Astra Pro**, operation `uiowa067-review-explorer-lantern47r-20260919`. Preserve **ZZ-Sol** and **ZZ-HELIODORE-67** attribution for the canonical assessment, contract and fictional cases. Their `analyze.py`, `contract.py`, `fixture.py` and existing reporting commands remain unchanged. Related original integration: #16223; original work record: #16149.

## Source availability and review status

The executable presentation is published in [PR #16366](https://github.com/woahwhattheheck/commons/pull/16366), original tested source commit `9925a8acd9aad2dabc19a5cec63294ba5f5daaa2`, on `swarm/zz-lantern-47r-incident-review-20260919`. The commands below require that source; the guide's presence on `main` alone does **not** establish that the executable files have been integrated. Verify the PR's current state separately. The scoped runs reported here do not replace the repository's exact-head provider execution authority.

A [readable walkthrough is also available in the internal demo Slack canvas](https://tokenjunkielabs.slack.com/docs/T0BRETUB5TK/F0C36DJKXM2). It walks through the actual fictional case without requiring a reader to run code.

## Generate a working page

From the repository root, using Python 3.10+ and only the standard library:

```sh
python revenue/uiowa_rfq_18649_incident_learning/review_view.py --demo --out /tmp/incident-review.html
```

Open the generated HTML in a JavaScript-enabled browser. The file contains the complete report, source excerpts, original packet bytes, style and program; it needs no server, CDN, account, upload or network connection. Keep the component's four `review_view.py/.html/.js/.css` source files together when generating it. Do **not** open the unpopulated `review_view.html` template as the demonstration.

For an existing canonical **raw packet**:

```sh
python revenue/uiowa_rfq_18649_incident_learning/review_view.py --input /path/to/packet.json --out /path/to/new-review.html
```

The input is the `uiowa-incident-learning/v1` packet accepted by `analyze.py`, not the already-analyzed `report.py --format json` result and not the older reference-only `examples.json` format. The viewer calls the canonical analyzer rather than trusting a caller-supplied verdict. The existing legacy and report commands remain available.

`--out` must name a new file in an existing directory. Existing files, input aliases and existing symlink/hardlink destinations are not overwritten. Files are created with owner read/write permissions where the operating system supports those mode bits. The caller manages parent directories; this is not a filesystem sandbox or protection against a hostile process controlling the parent directory. Input is read once, at most 4 MiB. Duplicate JSON keys, non-finite numbers, malformed Unicode and excessive structure are rejected before presentation; the canonical contract still checks record relationships. Failed input creates no page.

## A useful five-minute walkthrough

1. Start with all groups. The supplied fictional packet contains **3 incidents, 6 unique actions, 3 overdue unresolved actions and 10 source records**. The header explicitly labels it **FICTIONAL REHEARSAL — NOT UNIVERSITY FINDINGS**. These counts describe the complete packet and do not change when a panel is filtered.
2. Select **RIS** and **Overdue unresolved**. The corrective-work panel shows **ACT-02** and **ACT-03**. ACT-02 is shared with ESS but appears only once. ACT-03's reported closure is not evidence-linked implementation and verification; it remains `closure_unverified`.
3. Inspect RIS's history. Restoration-to-verification remains **UNKNOWN** because the supporting milestone is absent. In IAM, unsupported impact-start evidence leaves impact-to-restoration **UNKNOWN**. The view does not replace missing measurements with zero or elapsed time from unsupported endpoints.
4. Select **Replacement documented** and follow **ACT-04 → ACT-05**. The link resets filters when needed to reveal the target. ACT-04 has a documented decision; ACT-05 is still open and overdue at the packet's explicit as-of time. Replacing an action does not complete its successor.
5. Follow an evidence link, such as **EV-ESS**. Its exact supplied source record opens in the source appendix. The locator is plain text, never fetched. Inspect the excerpt and its limitations rather than treating the source's existence as authentication.
6. Export the current selection. The JSON contains **selected IDs plus the entire unchanged canonical report and original packet bytes**, so cross-references still resolve. The plain-text summary contains only visible incident/action records and explicitly says it is a filtered view. Neither export records a decision, acceptance, or resolution.

Group and search affect both incident and action panels. Action-state filtering affects only corrective work. Search includes the record and its directly cited source excerpts. The complete source and contributing-condition appendices remain available even with no visible matches. Anchor navigation may reset filters to expose a linked record; the status line announces this.

## Interpretation and data handling

Milestones are ordered by their supplied timestamp instants, including UTC offsets. Their raw timestamp strings and original event order remain in the exported canonical report. A missing milestone is not an assertion that the activity never happened. Comparisons retain counts, exposure, units, cohorts, windows and the canonical non-causal interpretation.

The visible state names are the canonical analyzer's results. The viewer does not grade employees, rank groups, mint verification, propose a product purchase, or infer a University baseline. SHA-256 values identify the exact supplied input bytes and canonical report serialization; they are **not** signatures, source authentication, or analyst approval. Reformatting input JSON changes its input hash but not the canonical report hash when the record content is unchanged.

An `engagement` packet retains that classification; it is not relabeled synthetic. The generated page and every JSON selection export contain the **entire input**, including sources outside the visible filter. Handle them at the same sensitivity as the original packet. Do not publish confidential engagement data or put it in this repository. The example uses only the canonical fictional fixture. There is no browser storage, upload, automatic source fetch, background polling or schedule.

The generated page uses content-hashed inline scripts/styles, text-only DOM rendering for supplied records and a Content Security Policy that disallows network connections and external resources. Source locators are deliberately not external links. The generated HTML itself remains an editable file, not a tamper-proof evidence container.

Printing preserves the selected incident/action panels and expands details so source excerpts and supporting records are not silently omitted. The source and condition appendices remain complete. The print action does not transmit or schedule anything. Without JavaScript, use the existing `report.py` Markdown/CSV commands; the HTML explicitly states that it has not displayed an assessment.

## Reproducible checks

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_incident_learning -p test_review_view.py -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_incident_learning -p test_review_view.py -v
python -W error::ResourceWarning -m unittest discover -s revenue/uiowa_rfq_18649_incident_learning -p test_review_view.py -q
python -m py_compile revenue/uiowa_rfq_18649_incident_learning/review_view.py revenue/uiowa_rfq_18649_incident_learning/test_review_view.py revenue/uiowa_rfq_18649_incident_learning/review_view_browser_test.py
node --check revenue/uiowa_rfq_18649_incident_learning/review_view.js
```

Optional real-browser checks require Playwright and an **already installed Chromium**. They are separate from the dependency-free unit suite and fail explicitly when prerequisites are missing; no browser install, provider purchase or new workflow is triggered.

```sh
python revenue/uiowa_rfq_18649_incident_learning/review_view_browser_test.py --browser /usr/bin/chromium
```

Authored-source execution on the ephemeral cloud container: **29/29 unit tests normal, 29/29 optimized, 29/29 ResourceWarning-strict; 14/14 real-Chromium tests; no skips**. Browser: Chromium **144.0.7559.96**, Python **3.13.5**. Browser checks exercised filtering, source/replacement links, all anchor targets, byte-exact original downloads, full-report selection exports, plain-text summaries, unknowns, untrusted text, keyboard controls, 390-pixel layout, print expansion and empty/engagement packets. No viewer network requests or JavaScript errors were observed in the passing suite.

The managed test browser blocks `file://` navigation. Browser tests therefore use `set_content` on the exact generated HTML bytes; **they do not establish a successful file-URL navigation**. The page has no external resource dependency. Actual browser/desktop policy still controls whether a recipient may open HTML files or download exports. These are scoped tests, not repository-wide or hosted GitHub Actions results.

The unchanged canonical dependency blobs used in this execution were read back and matched exactly:

| Existing source | Git blob |
|---|---|
| `analyze.py` | `e6d148527f3da5608bb0e4095d1b5862532068d9` |
| `contract.py` | `7967d574d3cdc344c53967ece6315b6803420b09` |
| `fixture.py` | `fdf1ddb14a99eb37f4638bf10f047462dd316003` |

The new tests are discovered by the existing package command documented in the main README. No new Actions workflow or claim of hosted CI coverage is added here.
