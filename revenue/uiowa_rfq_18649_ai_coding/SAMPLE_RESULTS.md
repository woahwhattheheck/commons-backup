# Executed synthetic rehearsal — UIOWA-076

ZZ-COPPERFIN-73 / GPT-6 Astra Pro, 2026-09-19. These are computations over authored fictional histories, not measured University or live-model results. Source and complete sample generation: `rehearse.py`. The source registry contains 77 exact line locators, all bound to the generated UTF-8 history file.

Executed in the ephemeral cloud Python environment:

```text
python -m unittest discover -s . -p 'test_ai_coding.py' -v
Ran 36 tests in 2.341s
OK

python -O -m unittest discover -s . -p 'test_ai_coding.py'
Ran 36 tests in 2.377s
OK

python rehearse.py --out <new-empty-directory>
OK changes=6 pairs=3 comparable=2 sources=77
```

The timing lines describe those local test runs only, not a throughput benchmark or hosted CI result. Byte-level publication verification and merge state are recorded separately in the GitHub PR and Slack receipt.

| Fictional change | Authoring person-min | Delivery person-min | 30-day lifecycle person-min | Complete-window faults |
|---|---:|---:|---:|---:|
| ESS-A assisted | 8 | 75 | 80 | 0 |
| ESS-M manual | 75 | 145 | 150 | 0 |
| RIS-A assisted | 5 | 170 | 260 | 3 |
| RIS-M manual | 50 | 140 | 170 | 1 |
| IAM-A assisted | 4 | UNKNOWN | UNKNOWN | UNKNOWN |
| IAM-M manual | 55 | 115 | 130 | 0 |

Assisted-minus-manual contrasts: ESS authoring -67 minutes, delivery -70, lifecycle -70, faults 0. RIS authoring -45 minutes, delivery +30, lifecycle +90, faults +2. IAM is not comparable: task fingerprint and complexity differ, assisted acceptance is unsupported, and lifecycle effort and follow-up outcomes are incomplete. Its known recorded effort is 34 minutes; that is not a complete total. Accepted examples each have 90 elapsed minutes before acceptance, a quantity distinct from aggregate person-effort.

## Three-minute operator route

Generate the new rehearsal directory and open `reports/report.md`. Start with the full-workflow results, then compare ESS with RIS: the first-draft speed story alone cannot distinguish them. Follow the RIS practice and repair anchors into the exact retained excerpts. Finish with IAM: the program keeps useful recorded facts while refusing a misleading contrast. Open the input JSON and change one declared follow-up endpoint from August 31 to September 5; run the analyzer into a new output directory. The longer unsliced window becomes incomplete for the requested 30-day comparison rather than silently accumulating extra faults and effort.

This route requires no server, account login, model call, appointment or real institutional data. The complete human histories and editable JSON are outputs of the committed generator, so another operator can reproduce them without this chat or Slack history. See `RUBRIC.md` for follow-up questions and interpretation limits.
