# Autopsy Agent

Autopsy Agent turns one failed agent-run transcript into an evidence-linked diagnostic draft, or a concrete clarification request when the record cannot support a diagnosis. Each round uses **two actual Strands Agents**: an intake/drafter and an independent reviewer with fresh context. A rejected draft can receive one internal revision and a new independent review. Observed events are projected directly from verified source-line quotations; model-written causal claims stay in inference fields. Deterministic checks validate the evidence bytes, citations, and report contract before releasing the result.

This candidate is for the Professional Agents track of [AWS Agents for Humans](https://agentsforhumans.devpost.com/rules). The engineering and Strands integration are new work. It incorporates the attributed Commons Autopsy foundation described below. No contest entry, prize, sale, buyer delivery, or revenue is established by this repository.

## Run on Windows

The tested platform is Windows x64 with Python 3.12. Use a fresh environment and the completed source/dependency audits:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe scripts/install_audited.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/verify_vendor.py
```

`install_audited.py` checks the official SDK source inventory and the completed metadata audit, installs exact hash-locked wheels with no dependency expansion, and disables pip's download cache. It pins **Strands 1.0.1**, whose package source has no llama.cpp provider module or native runtime. No optional model-provider extras are installed. Do not upgrade the SDK without a new source inventory and dependency audit. The dependency lock is specific to Windows CPython 3.12.

### Portable service route for judges: Amazon Bedrock

Configure your own authorized AWS credentials through the normal AWS credential chain and select an available Bedrock model identifier. Then run:

```powershell
.\.venv\Scripts\python.exe -m autopsy_agent --provider bedrock --model-id YOUR_BEDROCK_MODEL_ID --out runs/bedrock
```

This uses the standard Strands `BedrockModel` included in the base SDK. There is no dependency on the author's Commons environment for this route. **No existing AWS model route has been verified in this task; Bedrock was not invoked.** The wrapper and its request allowance have controlled tests. Credentials remain in the AWS credential facility; never put them in a case or receipt. Selecting this route uses your existing AWS service resources.

### Existing Commons service route used for development validation

```powershell
.\.venv\Scripts\python.exe -m autopsy_agent --provider commons-relay --model-id gemini-pro-agent --relay-path PATH_TO_EXISTING_COMMONS_PEER_RELAY_PY --out runs/commons
```

This optional custom Strands `Model` adapter uses the owner's existing Gemini Code Assist OAuth client. It is **not** standard Gemini SDK access, an OpenAI-compatible endpoint, or Bedrock. The local relay is supplied by the existing Commons installation and is not vendored here. Only its `stream_generate` library function is used; its peer launcher and public read/post tools are never invoked. A private imported client copy exposes no tools. Each agent receives a new request session.

Commons direct credential retrieval remains available through its shared secure credential facility (`gemini/profile`, `gemini/access`, `gemini/refresh`), independently of this optional client convenience. This candidate neither distributes credentials nor creates peer access gates. The relay reads its existing secure profile and may refresh its token using the existing route. It returns completion reasons but does not expose token usage, so usage is recorded as unavailable rather than estimated as a provider measurement.

The CLI runs both supplied cases by default. `--case examples/ordinary/case.json` selects one. `--max-model-requests` permits at most six attempts across the invocation, including failed attempts. After a valid rejection with concrete required changes, `--max-revisions 1` (the default) permits one internal rewrite and a fresh independent review; `--max-revisions 0` withholds the first rejected draft immediately. Each round and its exact hashes remain in the receipt. Revision never changes evidence or executes proposed fixes, and a second rejection stays withheld. A new CLI invocation starts a new allowance, so preserve the run receipts when coordinating a shared validation limit.

## What the result means

Each run writes a JSON receipt containing the actual model outputs, every draft/review round, separate reviewer decision, application-generated agent/request IDs, evidence hashes, implementation version, wall-clock measurements, and final status. `draft_report` is retained for inspection even when withheld; only `report` is a released result. The existing relay does not expose a provider-issued response ID:

| Status | Result |
|---|---|
| `VALIDATED_SYNTHETIC_DRAFT` | Both model stages completed; the accepted draft passed the upstream schema, semantic contract, and on-disk evidence validation. |
| `CLARIFICATION_REQUESTED` | One specific evidence request, no diagnostic report, no invented causes or fixes. |
| `REVIEW_REJECTED` | Reviewer rejected the candidate; the diagnostic report is withheld. |
| `FAILED_CLOSED` | Invalid evidence, malformed output, stale source, service failure, or exhausted allowance; no report is released. |

The upstream contract intentionally requires synthetic reports to remain `PEER_DRAFT` with unmeasured buyer-review fields. The separate run receipt records the **actual model review** without converting a synthetic example into a buyer incident or human review. The inherited `DIAGNOSIS_DELIVERED` enum inside a synthetic report is a contract label; it is not evidence of delivery to a buyer. Proposed fixes and replay checks remain `PROPOSED_NOT_RUN`.

This candidate has an explicit conservative `CURATED_SYNTHETIC_TRANSCRIPT_ONLY` evidence profile. It accepts one transcript and cannot ingest an independent mechanism-verification artifact, so its causal findings are limited to **MEDIUM or LOW**. Code rejects HIGH from either primary or contributing causes before review and never silently changes the model's confidence. The original upstream HIGH definition and vendored schema remain unchanged. This narrower rule is new candidate design, not a claim that all transcript evidence universally precludes HIGH confidence. Prompts distinguish outward behavior from hidden cognition; a cognition or context explanation must be an explicitly unverified hypothesis. Model assessment of those explanations remains probabilistic.

## Evidence and tests

`examples/ordinary` contains the attributed synthetic generated-settings transcript. It records two output-file edits, generator messages, and repeated test failure. A correct new analysis must distinguish those observations from an inference about unseen source configuration or generated-file contents. Untested alternatives reduce confidence.

`examples/insufficient` contains only an assertion that a run failed, with no command sequence or error evidence. It must yield a clarification request and **no diagnosis**.

The automated tests use the actual Strands agent loop with explicitly labeled **controlled test doubles**. They check orchestration and failure gates, not diagnostic model accuracy. Negative controls cover invented citations, free-form observations, HIGH confidence with unresolved alternatives, incomplete reviewer cause coverage, malformed/duplicate JSON, false replay execution, stale evidence in either outcome, stale source versions, invalid case IDs, non-independent model instances, reviewer rejection, empty/truncated provider completion, and request limits. An actual earlier live result that both models incorrectly accepted is retained in `tests/fixtures/accepted-but-unfaithful.json` and now fails the same intake/draft gate. The copied upstream report is a structural test fixture; its wording is not a measured positive example of the new model's reasoning.

A second actual false acceptance, `tests/fixtures/accepted-hidden-cognition-high.json`, inferred HIGH confidence about hidden cognition from an outward remark. It now fails the conservative evidence-profile gate while retaining its original HIGH output unchanged. Positive controls preserve MEDIUM and LOW capability and verify that the upstream schema still includes its original HIGH definition.

Actual service receipts, when present in `runs/`, are separate from controlled tests. [VALIDATION.md](VALIDATION.md) retains the development outcomes, including the first provider timeout, an earlier structurally accepted but semantically unfaithful result, parser failures, reviewer rejection, and the no-causes clarification overconstraint. Successful repairs must not erase those failures. No synthetic test establishes production reliability, customer acceptance, time saved, or revenue. See [ARCHITECTURE.md](ARCHITECTURE.md) and [SOURCE_FIDELITY.md](SOURCE_FIDELITY.md) for the mechanism and limits.

## Current scope

The CLI accepts one pre-redacted, explicitly synthetic UTF-8 text artifact with stable line anchors. It supports up to 100 anchors and 2,000,000 raw bytes, within the larger upstream intake contract. It executes no transcript commands and has no repository, production, email, payment, or public-post tools.

This candidate does not yet implement real-buyer intake, automatic redaction or injection detection/quarantine, multiple-file intake, PDF/OCR extraction, clarification-response ingestion, refund fulfillment, or production deployment. It expects curated synthetic evidence. The upstream quarantine and refund procedures remain requirements for a future real-buyer workflow, not claims of implemented protection here. Agent review is probabilistic; structural validation proves citation existence and contract consistency, not the truth of every causal inference.

## Attribution and contest requirements

The unmodified `vendor/autopsy` sources come from [Commons PR #8811](https://github.com/woahwhattheheck/commons/pull/8811), pinned to commit `c8e40bcda9c14305236c3e0ccd814a944d11ee74`. They include the intake/report schemas, validator, synthetic examples, runbook, and report template. `SOURCE_MANIFEST.json` records each exact Git blob; `scripts/verify_vendor.py` verifies them. The Commons contributors' work is used under Apache-2.0. The new orchestration, adapter, case handling, tests, and documentation use the same license; see [LICENSE](LICENSE) and [NOTICE](NOTICE).

The [official rules](https://agentsforhumans.devpost.com/rules) require a new Strands project, disclosure of incorporated work, a public runnable MIT/Apache repository, README, architecture diagram, and a public working demo video no longer than five minutes. Submission closes September 14, 2026 at 5 p.m. Pacific. An AWS account and Builder ID are required; AgentCore is optional. Registration, account eligibility, public repository, demo publication, and actual submission remain separate from this local engineering candidate.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

