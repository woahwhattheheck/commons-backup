# Validation record

The development runs below are synthetic examples on the existing Commons Gemini Code Assist route through actual Strands agents. They are not customer incidents, buyer deliveries, executed fixes, a reliability benchmark, or evidence of time saved or revenue. Token usage is unavailable from the existing relay. Raw local receipts are retained unchanged in `runs/`; `RUN_HISTORY.json` records their exact hashes, source versions, request outcomes and timings without credential values.

| Run ID | Source prefix | Calls | Recorded outcome and substantive interpretation |
|---|---|---:|---|
| `4591332e-fe19-4f80-a8ad-e56a13af0974` | `b39339c3` | 1 | Ordinary case failed closed after an actual provider timeout of 680.253301 seconds. No model output was recovered. This was a timeout, not an operator-aborted request. |
| `57dac963-b455-4bbe-9a2f-a1a0a1a130bc` | `b39339c3` | 2 | Insufficient case requested clarification with no diagnosis. This result belongs to the earlier implementation. |
| `b83eb7df-6465-4c1f-ad2b-a4d6028f930a` | `b39339c3` | 2 | Structurally accepted but **semantically failed** independent inspection: unseen file reversion was labeled observed, confidence was inflated, and the reviewer failed to resolve its own competing account. This is withheld from positive demonstrations and retained as a regression fixture. |
| `34efe41d-4de9-4e76-b3c5-585902e928c3` | `d489dadb` | 2 | Ordinary case failed closed parsing a single enclosing JSON fence in the reviewer output. The draft had improved uncertainty, but no accepted result was released. The old receipt did not persist the exact assembled draft report, so its full reviewer hash cannot be independently reconstructed from this receipt alone. |
| `f566ee09-1682-4f7f-a98c-d0f52f6d01bb` | `d489dadb` | 2 | Insufficient case correctly proposed no diagnosis, but failed closed at the same fenced-output parser boundary. |
| `d816c9e4-f82b-49f8-b5f1-7e22e0c6cd7a` | `b9a03b81` | 2 | Ordinary case was correctly rejected by the reviewer: HIGH confidence contradicted the still-plausible alternative that the unseen test reads source configuration directly. The draft report is retained and withheld. |
| `3492780d-082f-400c-b114-09198837ee42` | `b9a03b81` | 2 | Insufficient case contained no diagnosis and the reviewer accepted it, but an application rule incorrectly required cause counterexamples even though no causes existed. The actual result remains failed closed; its output is a controlled regression for the corrected rule. |
| `a587751f-18d8-4de3-97ad-63a5fb90877f` | `c43450c9` | 1 | Ordinary case failed closed with an actual provider TimeoutError after 663.079792 seconds. No output was recovered and no operator abort occurred. |
| `76834cee-c9e0-4675-9062-193f39679910` | `c43450c9` | 2 | Insufficient case requested relevant missing execution evidence with analysis null; reviewer accepted and author-agent inspection found no invented diagnosis. This is a successful clarification on the revised source. |
| `8a51560b-7f21-4e56-b252-3150e4ef7547` | `c43450c9` | 2 | Structurally accepted but **semantically failed** author inspection. The primary hypothesis is appropriately MEDIUM, but a contributing hidden-cognition claim is HIGH. The reviewer incorrectly treats a short outward remark as direct access to internal reasoning and incorrectly rules out its alternative. This report is withheld from a positive demonstration. |
| `5137cd90-1cd8-4db0-9f39-8fd14a585295` | `52c316ef` | 2 | Accepted qualified ordinary draft: MEDIUM mechanism with unseen-file/test uncertainty, LOW unverified cognition hypothesis with plausible alternatives. Its paired clarification failed an applicability rule, so the later same-version pair is used for the demo. |
| `ccba1238-9917-4644-801a-ae1ad3ff168e` | `52c316ef` | 2 | Correct no-diagnosis clarification failed closed because the reviewer honestly marked causal challenge false when no causes existed. That applicability rule was repaired; the original failed receipt remains unchanged. |
| `72bfcf46-6b2e-4e31-83c8-ab4a0828e0de` | `5446a970` | 2 | **Approved for the recorded demo as a qualified probabilistic draft.** Primary MEDIUM inference retains the possible alternate test read path; contributing LOW hypothesis retains unknown agent-context alternatives. All proposed work remains unexecuted. |
| `983555b7-e6de-4f82-aa5b-a88b4949958e` | `5446a970` | 2 | **Approved for the recorded demo as a no-diagnosis clarification.** It requests missing command/output/error/change evidence, has analysis null, and honestly retains a false causal-challenge flag because there are no causes. |

There have been twenty-six actual requests in these fourteen retained runs. Final source version is `5446a970b4b737e08dbaa76dda49000366844e2088f165b25279ba5a3ab23005`. The final ordinary phases took 43.752307 and 31.485665 seconds; clarification phases took 10.247462 and 19.349761 seconds. Each used two real requests and no revision. The revision path is controlled-test verified, but was not exercised by a successful live run. These are elapsed observations, not a baseline comparison or a time-saving claim. Subsequent outcomes must be appended with their actual version and receipt hashes; a successful retry must not replace this history.

All exact raw synthetic receipts are published under `validation_receipts/<run_id>.json`, including failures. The final ordinary receipt SHA-256 is `bf528fe661841846cc7769ccd65b635bf7277a30d6aa43ce2fd3ae74551a5eee`; final clarification is `ef615b436ba2a6b7367ecdadd7305db023c7e1811e742abb0436d39c2f53fe40`. Approval is author AI-agent source inspection for a recorded demonstration, not human review or proof that every causal judgment is true.

The current controlled suite has 46 tests using the real Strands loop and explicitly labeled model doubles. It checks evidence, confidence, review coverage, strict parsing, isolated contexts, provider completion and request accounting, plus a bounded internal revision that retains both versions and obtains a fresh independent review. The new conservative transcript-only profile rejects the actual hidden-cognition HIGH false acceptance and preserves MEDIUM/LOW capability. These tests establish gate behavior, not model accuracy. The one-revision design is a response to actual reviewer rejection, not permission to silently lower confidence or automatically accept a report.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

