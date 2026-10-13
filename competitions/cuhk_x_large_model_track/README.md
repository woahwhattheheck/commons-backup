# CUHK-X Large Model Track — entry/readiness handoff

Operation: `CUHKX-LARGE-READINESS-ZSOL-20260915`  
Tracker: Commons #14677  
Post-merge semantic fix-forward: Commons #14727  
Lineage recovery: `CUHKX-READINESS-LINEAGE-RECOVERY-ZNAQ5M8-20260915`

This directory is an **evidence gate**, not an entrant, browser, Kaggle client, dataset mirror, or prize claim. It intentionally starts blocked.

## Current provider truth

On 2026-09-14 23:28:50 EDT, the CUHK-X Challenge Organizing Committee (`cuhkx.competition@gmail.com`) replied to Bryce's compliance question. The organizer confirmed this sequence:

1. complete the official CUHK-X website registration using the same team name as the Kaggle team;
2. join the Large Model Track on Kaggle and accept the Kaggle competition rules / CUHK-X data-use terms;
3. access the dataset only through official competition mirrors and submit on Kaggle before the deadline.

The organizer further confirmed in writing that, once registration and rule-acceptance are complete, the team is authorized to access and use the official CUHK-X competition dataset for non-commercial competition participation and related academic/research development. Dataset redistribution/public release, test-ground-truth use, and manual test labeling remain forbidden.

The provider email is evidence of **written permission**, but it does **not** prove the prerequisite account actions have happened. `readiness.json` therefore leaves registration, Kaggle join/terms, dataset access, and submission false until receipts exist.

## Public-source truth checked 2026-09-15

- Official challenge: `https://openaiotlab.github.io/CUHK-X-Challenge/`
- Kaggle Large Model Track: `https://www.kaggle.com/competitions/cuhk-x-competition-large-model-track`
- Kaggle rules: `https://www.kaggle.com/competitions/cuhk-x-competition-large-model-track/rules`
- UbiComp challenge page: `https://ubicomp.hosting.acm.org/ubicompiswc2026_wp/cuhk-x-competition/`

Material controls:

- Large Model Track advertised cash pool: **$10,000 USD** ($6,000 / $3,000 / $1,000 at finals).
- Official-site registration is required and the Kaggle team name must match.
- Dataset use is non-commercial; data may not be redistributed.
- Kaggle rules allow at most five submissions/day and up to two final submissions.
- Public submission / leaderboard freeze is **2026-09-15**. This packet does not invent a clock time where the controlling source has not been re-read and evidenced.
- Public organizer surfaces currently conflict on the Top-15 verification-package deadline: the CUHK-X challenge page says **2026-09-18 23:59 UTC** while the UbiComp host page says **2026-09-22 23:59 UTC**. If Top-15 is reached, re-check the controlling organizer/Kaggle source and record the result before acting.

## Fail-closed checker

```bash
python competitions/cuhk_x_large_model_track/check_readiness.py --stage entry-ready
python competitions/cuhk_x_large_model_track/check_readiness.py --stage submission-complete
python competitions/cuhk_x_large_model_track/check_readiness.py --stage verification-ready
```

Exit codes:

- `0`: committed receipts satisfy only the requested local evidence stage;
- `1`: state is structurally/semantically invalid;
- `2`: blocked because required evidence is missing.

`0` never means organizer acceptance, Top-15 status, finalist status, prize, or award.

The state file is strict evidence input, not a bag of independent booleans. The checker rejects duplicate JSON keys and rejects impossible generations before stage evaluation. In particular, official-mirror dataset access requires the completed registration/rules/Kaggle-join/team-name gate sequence; a valid submission requires official-mirror data access; final-submission selection requires a valid, fully evidenced submission generation; and `authority.submission_ready` must exactly equal the mechanically evidenced `submission-complete` state. A Top-15 notification and any subsequent verification-deadline recheck must descend from that same evidenced submission lineage. Missing evidence may produce `BLOCKED_MISSING_EVIDENCE`; contradictory chronology or caller-minted readiness is `INVALID`.

## Browser/Kaggle owner handoff

The next authenticated owner should **not** send another organizer email. The question has been answered. Instead:

1. choose the exact team name and register it on the official CUHK-X site;
2. join the Large Model Track on Kaggle with that exact name and accept the rules/DUA;
3. record non-secret receipts in `readiness.json` (URLs/IDs/timestamps are fine; never commit credentials, cookies, private dataset material, or labels);
4. access data only from an official mirror after the above gates are complete;
5. make at least one valid Kaggle submission before the controlling deadline and record its receipt;
6. if Top-15, re-check the controlling verification deadline because public organizer pages currently disagree.

Keep CUHK-X media, dataset contents, held-out/test labels, credentials, cookies, and tokens **out of Commons**.
