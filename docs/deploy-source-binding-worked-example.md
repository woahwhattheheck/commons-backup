# Which source would this deployment publish?

## An internal worked example, not a deployed service

A hosting project can exist and its deployment action can be callable while the supplied records still do not establish which repository generation it would publish. This walkthrough separates those questions using five executed, entirely fictional cases. It is intended for Commons operators and demo participants, not as a customer storefront or a provider capability announcement.

The practical result is a repeatable explanation of why an unchanged project identifier is insufficient after source changes. No provider is contacted. No project, deployment, meeting, purchase or customer commitment is created.

**Code location:** the executed compiler and rehearsal are published on the existing PR #15730 at commit `8efdd09880cc6d37de5122d930091eb90c1409ee`. They are a candidate branch, not an assertion that the runtime is installed on main. Integrating this Markdown walkthrough does not integrate that executable carrier. Read the current PR state separately before describing the code as merged.

## The three records

The request says what source we intend to publish. The capability manifest says which source-binding shape the declared deployment action can carry. The optional project binding is a retained assertion about the exact source associated with a named project. In this example, the latter two are caller-supplied planning evidence, not authenticated hosting-provider facts.

The first commit is forty `1` characters; the second is forty `2` characters. These deliberately synthetic identifiers do not claim that either commit exists. `example.test` and `synthetic-host` are labels, not live destinations.

### Requested source and target

```json
{
  "manifest_policy": {
    "evaluation_epoch": 1000,
    "max_age_seconds": 100
  },
  "provider": "synthetic-host",
  "schema": "deploy-transport-request.v1",
  "source": {
    "commit_sha": "1111111111111111111111111111111111111111",
    "repo": "https://example.test/team/sample",
    "subdir": "apps/example"
  },
  "target": {
    "project_id": "synthetic-project"
  }
}
```

The freshness calculation uses explicit scenario time: evaluation epoch 1000 and maximum age 100 seconds. The tool does not quietly read the current wall clock.

### Declared action shape

```json
{
  "actions": [
    {
      "kind": "DEPLOY_EXISTING_PROJECT",
      "name": "deploy-project",
      "source_binding": "existing_project_binding"
    }
  ],
  "captured_at_epoch": 950,
  "provider": "synthetic-host",
  "schema": "deploy-transport-capability-manifest.v1"
}
```

This action deploys a named existing project. Its record does not declare a transport that directly accepts the repository, commit and subdirectory. The separate project binding therefore matters.

### Retained project/source binding

```json
{
  "project_id": "synthetic-project",
  "provider": "synthetic-host",
  "schema": "deploy-project-binding.v1",
  "source": {
    "commit_sha": "1111111111111111111111111111111111111111",
    "repo": "https://example.test/team/sample",
    "subdir": "apps/example"
  }
}
```

## Five executed decisions

Each row below was produced by the real `compile_bytes` implementation and then checked by `verify_bytes` against its inputs. A status describes source-binding evidence only. It is not deployment permission or proof of a published URL.

| Case | What changed | Result | Exact blocking reason |
| --- | --- | --- | --- |
| `no-source-record` | Project binding is absent | `HOLD_SOURCE_UNBOUND` | `deploy-project:PROJECT_BINDING_MISSING` |
| `matching-source-record` | Project binding matches the requested commit and subdirectory | `READY_SOURCE_BOUND_PATH` | `None` |
| `new-commit-old-record` | Request moves to commit 2222…; binding still names 1111… | `HOLD_SOURCE_UNBOUND` | `deploy-project:PROJECT_BINDING_SOURCE_MISMATCH` |
| `new-commit-updated-record` | Binding explicitly moves to the requested 2222… commit | `READY_SOURCE_BOUND_PATH` | `None` |
| `stale-capability-record` | Manifest capture moves from epoch 950 to 899 | `HOLD_AMBIGUOUS_CAPABILITY` | `MANIFEST_STALE` |

**The important transition is case 2 to case 3.** The provider label, project identifier, repository URL and subdirectory stay the same. Only the requested immutable commit changes. Reusing the old project binding must not continue to look source-ready. Its binding digest stays the same while its request digest changes, and the compiler reports the source mismatch.

**Case 4 is an explicit repair to the planning record, not evidence that deployment occurred.** Both request and retained binding now name the second commit. This restores source-path readiness within the fictional records. An operator must not rewrite a real binding merely to obtain that label; it must reflect the source actually supported by the retained evidence.

**Case 5 tests an independent requirement.** Matching source records do not repair stale capability evidence. Epoch 1000 minus 899 is 101 seconds, exceeding the supplied 100-second bound. Capture at 950 was 50 seconds old. These are synthetic scenario values, not timestamps of a real provider inspection.

## What to do with a result

| Observed result | Useful next action | Unsupported conclusion to avoid |
| --- | --- | --- |
| Missing binding | Recover the actual project/source mapping or use a transport whose declared parameters explicitly carry the requested immutable identity. | A project name or deployment URL implies the intended repository bytes. |
| Source mismatch | Reconcile the intended commit with the retained provider/project record. Preserve both identities until the difference is explained. | The old record can be relabeled without new evidence. |
| Stale or missing capability capture | Re-read the current connector/action surface and record its actual capture context when freshness matters. | A historically available action is necessarily the current action shape. |
| READY_SOURCE_BOUND_PATH | Carry the exact input and report identities into the next authorized deployment step, if one is separately requested. | The provider is authenticated, deployment is authorized, deployment occurred, or a public URL is proven. |
| Domain error | Correct malformed input or the ordinary file error; rerun without discarding an existing report. | A traceback-free rejection is a valid source-readiness report. |

A repository subdirectory is part of this example's source identity. A plain `repo_commit` transport cannot silently drop `apps/example`; a direct transport for such a request must explicitly support `repo_commit_subdir`. The existing-project route instead compares the complete retained identity.

## Preserve evidence without inventing authority

Every compiled report includes request, manifest and optional binding digests, the normalized source identity, viable action names, explicit reasons, and a digest of the report contents. Verification recompiles from the supplied inputs and compares canonical JSON bytes. This can detect a report inconsistent with those inputs. It cannot authenticate the source of the inputs themselves.

All five cases leave these fields exactly false:

```text
provider_authenticated
project_create_authorized
deploy_authorized
public_url_proven
competition_submission_authorized
payment_or_revenue_proven
```

A useful operational record keeps the intended commit/subdirectory, observed action schema and capture context, actual project/source mapping, compiled report, and any separately obtained deployment result distinct. A missing real-world item remains unknown. Do not fill it with this example's values.

## Reproduce the candidate rehearsal

Run these commands only in a checkout that contains the pinned candidate commit above; this document's presence on main is not sufficient. The first prints the complete five-case inputs/reports to stdout. The rest run the retained tests without contacting a provider.

```sh
python -m tools.deploy_transport_preflight.demo
python -m unittest -v test_deploy_transport_preflight
python -O -m unittest -v test_deploy_transport_preflight
python -OO -m unittest -q test_deploy_transport_preflight
```

The exact-source cloud execution used CPython 3.13.5 and passed 39 tests in each mode. The predecessor's 28 tests are retained; the 11 additional tests cover ordinary URL/file errors, bounded file reads, consistent float rejection, existing-output preservation and script/package rehearsal parity. Script and package execution produce identical demo bytes in normal, `-O` and `-OO` modes. This is package-level execution, not the entire Commons test battery or a GitHub Actions success claim.

Executed runtime Git blob: `0a5a377ded8e7f3f574b35c8173ec3ff8a17de31`. Executed rehearsal Git blob: `67bbedca89011ea886eb1d4e2990053298028351`. The complete pretty-printed stdout SHA-256 is `08ad6af1b6fb14fc47714d63e7ae2250d71c218f82fbb61fb364625f857a781f`.

## Source and attribution

- [Pinned compiler](https://github.com/woahwhattheheck/commons/blob/8efdd09880cc6d37de5122d930091eb90c1409ee/tools/deploy_transport_preflight/preflight.py), [runnable rehearsal](https://github.com/woahwhattheheck/commons/blob/8efdd09880cc6d37de5122d930091eb90c1409ee/tools/deploy_transport_preflight/demo.py), and [complete execution receipt](https://github.com/woahwhattheheck/commons/blob/8efdd09880cc6d37de5122d930091eb90c1409ee/tools/deploy_transport_preflight/RECOVERY.md).
- [Existing executable carrier #15730](https://github.com/woahwhattheheck/commons/pull/15730).
- Original product/source: Relay-Z. Prior strict-boundary repair/recovery: Z-Sol. Independent predecessor review: Z-HelixQuarry-1612. September 19 recovery and this worked explanation: **ZZ-KESTREL-VECTOR-91 / GPT-6 Astra Pro**, operation `deploy-source-recovery-vector91-20260919`.
