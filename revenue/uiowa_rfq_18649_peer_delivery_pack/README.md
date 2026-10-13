# UIOWA-015 — software delivery peer evidence, with its conditions intact

Start with [the complete 13-card peer pack](15-development-peer-pack.md). It is an interview reference, not a scorecard, a University of Iowa finding, or a statement that a published control is operating.

Original research and generator: **OP5-KELVIN (Claude Opus 5)**, [88ce48dd9042e0cc11c01bde463c227607b2cee8](https://github.com/woahwhattheheck/commons/commit/88ce48dd9042e0cc11c01bde463c227607b2cee8). Source-context review, UC recovery, validation repair and integration: **ZZ-TRACEFORGE (GPT-6 Astra Pro)**, 2026-09-19. All ten original card identifiers remain; three UC cards extend the existing pack.

## Use it in an interview

Choose one recent change and keep its actual identifier throughout. Start with the applicable local policy, data classification and any approved exception. A peer's classification is not a mapping to Iowa's classification.

Then follow that same change through requirements, recorded review, tests and acceptance, production approval, deployed revision and maintenance documentation. PC-004/005/006 ask for evidence of review and requirements coverage; PC-002/003 ask where release decisions are recorded; PC-011/012/013 add security-review, defect-history and exact-revision questions. PC-001 is useful when a second qualified reviewer was unavailable. Treat PC-009/010 as draft-source prompts until the official source can be re-opened.

Record what was actually shown: artifact locator, relevant date or revision, decision and decision-maker's role, applicability basis and unresolved question. Do not store credentials, personal data or production extracts in this repository. A permission-limited redacted example is enough for the rehearsal.

**Worked interpretation, explicitly fictional:** an interviewee shows approval ticket C-17 and says a pipeline ran. The ticket references version V-9, but the presented test output references V-8. That supports two narrow observations: an approval record was supplied, and the presented test record does not yet establish testing of V-9. It does not establish that testing was absent, that a deployment was unsafe, or that the organization failed a peer's policy. Ask for the V-9 test locator and any documented equivalence or exception; leave the connection unresolved until evidence is supplied. This is an analyst exercise, not a peer implementation result.

Finish by reading the observations back and separating records seen from assertions and items not collected. Do not infer maturity, contractual compliance, funding commitments or tool purchases from these cards.

## Why the source conditions matter

Kansas's global subtask rule changes the force of the isolated testing sentences when Level 1 data is involved. Minnesota's High/Medium/Low columns change individual rows; its optional design-review entry is retained as optional text, not a missing requirement. Dakota State permits lifecycle tailoring and has separate issue and adoption dates. These distinctions are linked to the exact clauses in the [pack](15-development-peer-pack.md).

UC's previously unread PDF now supplies three scoped cards. Its recorded approval date is not its earlier running-footer date; the pack does not establish supersession. Northeastern's two rechecks returned HTTP 502, so the original author's draft observation is preserved rather than presented as a fresh verification. Rutgers remains a landing-page collection limit; its linked report and project records were not inspected. None of these observations establishes consistent implementation.

## Run the retained source package

The full source and test carrier is [zz/traceforge-uiowa015-source-context-20260919](https://github.com/woahwhattheheck/commons/tree/zz/traceforge-uiowa015-source-context-20260919/revenue/uiowa_rfq_18649_peer_delivery_pack). Documentation can be integrated separately; its presence on main does **not** mean the executable/data carrier has merged or hosted tests have passed. Read the PR receipts for that state.

Use Python 3 with its standard library, from the package directory:

```sh
python peerpack.py --check
python peerpack.py --render
python -m unittest -v test_peerpack test_source_context
python -O -m unittest -v test_peerpack test_source_context
python -W error::ResourceWarning -m unittest -v test_peerpack test_source_context
```

The generator reads local JSON only. Invalid semantic data exits 1 without printing or replacing the deliverable; malformed input exits 2. The checker enforces the recorded schema and scope cases, not the truth of arbitrary new source claims. Fresh source inspection remains a separate research task. [Verification and exact tested objects](VERIFICATION.md).
