# Fictional release evidence — packet 057

**Entirely synthetic training material.** These records are invented for an offline assessment rehearsal. The repository, identities, revisions and input digests are illustrative. No institutional release, person, approval, or deployed service is represented.

## Approval

Record `ev-approval`; custodian role: Service change coordinator. A fictional change record identifies source `https://example.invalid/fictional-ess-service`, full revision `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, as the revision approved at 2026-01-12 09:00:00 UTC. This is a source-revision approval record, not proof of acceptance testing, commercial approval, or the authority of a real signatory. Export captured at 10:00:00 UTC the same day.

Interview challenge: ask the custodian to demonstrate how an approval refers to the exact source revision, how emergency changes are recorded, and what happens when the source changes after approval. No answer is pre-filled for any real team.

## Build

Record `ev-build`; custodian role: Build-platform maintainer. Fictional attempt `b1` began at 09:01:00 UTC and ended at 09:02:00 UTC on 2026-01-12. It records the same repository and revision as source `s1`. Builder label is `synthetic/build-platform`. Recipe identifier is `synthetic-records.md#build`; recipe-digest input is the literal UTF-8 string `fictional-recipe-057`. This is not an executable recipe.

The claimed complete resolved-input inventory contains `synthetic:toolchain` at a 64-character lowercase `b` digest and `synthetic:dependency-lock` at a 64-character lowercase `c` digest. These input hashes are invented examples, not verified toolchain files. Completeness is only declared. The input list illustrates metadata to request, not an assessment of dependencies. Export captured at 10:00:00 UTC.

## Artifact

Record `ev-artifact`; custodian role: Release custodian. Artifact `a1` is the non-executable `demo-artifact.txt`, labeled `fictional-1.0`, associated with build `b1`. Its genuine SHA-256 is computed by `make_fixtures.py` over the included demonstration bytes and placed into `fixtures.json`. A reviewer can independently hash those supplied bytes with the inspector's optional artifact root. This establishes a match to the demonstration file only, not that a real build created it. Export captured at 10:00:00 UTC.

## Deployment

Record `ev-deployment`; custodian role: Service operations owner. Fictional observation `d1` at 09:03:00 UTC records artifact `a1` in the **ESS-rehearsal** environment with label `fictional-1.0` and the same digest. No live environment was queried. Export captured at 10:00:00 UTC.

## Deliberately incomplete export

The `missing-build` packet removes build record `b1` while retaining the source, artifact and deployment records. The artifact still refers to `b1`. A supportable conclusion is: the supplied packet cannot currently link artifact `a1` to a producing build attempt. It is not supportable to conclude that no build record ever existed, the team lacks a build process, or the release was compromised. Request the attempt record and its locator.

## Deliberately contradictory export

The `digest-mismatch` packet changes only the deployment's recorded digest to a 64-character lowercase `d` value. The inspector identifies the artifact/deployment disagreement while retaining all other links. Plausible questions include whether the wrong deployment was selected, the artifact was repackaged, a mutable label was reused, or an export copied the wrong field. These are competing explanations to examine, not established causes. Preserve both original records until reconciliation is documented.
