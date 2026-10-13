# Current Readiness Authority Guard

A preventive AST-only gate for new or changed revenue Python. It targets repeated stop-merge defects where current readiness could be minted from caller-owned clocks, caller-authored evidence, or a verifier replaying retained time.

The scanner does not import or execute target modules. Within one module it follows public functions and public class methods through private methods, nested helpers, and simple callable aliases. It tracks branch-specific reaching definitions, constructor/dictionary readiness fields, string/enum states, and boolean readiness/authority outputs. Arbitrary caller-derived values remain untrusted when they reach deadline/currentness decisions.

## Rules

- `CRG000` — source cannot be parsed or read safely.
- `CRG001` — caller-derived data reaches a deadline/expiry comparison, including through private, nested, aliased, or method helpers.
- `CRG002` — a public current-positive surface accepts a caller-selectable time/clock override.
- `CRG003` — a current-positive path is not controlled by an actually consumed independent authority parameter. Merely naming an unused parameter `authority`, `root`, `receipt`, or `evidence` does not suppress the rule.
- `CRG004` — a verifier replays retained caller/report time without a process-owned clock projection that is unavoidable on every accepting return path. Decoy samples, overwritten fresh projections, `retained OR fresh`, caller-owned clock objects, and shadowed clock imports do not count.

Trusted clocks are derived from exact standard-library `datetime`/`time` imports plus the explicit host primitive `_process_now`; parameter/local/module shadowing removes trust. The guard does not treat arbitrary method suffixes such as `.current_utc()` as process authority.

The analysis is intentionally conservative. It does not prove that an authority parameter is externally authentic; it proves only that a distinct authority value is mechanically consumed as a control on every detected positive path. Provider/source authenticity remains a separate runtime obligation.

## Changed-source custody

Changed `revenue/**/*.py` paths include regular-file type changes (`ACMRT`). Reads use component-wise dirfd traversal, `O_DIRECTORY|O_NOFOLLOW` for intermediate components, `O_NOFOLLOW|O_NONBLOCK` for the leaf, a 2 MiB ceiling, regular-file checks, and exact descriptor/visible-generation binding over device, inode, mode, link count, size, mtime, and ctime. Symlinks, FIFOs, path escapes, type changes, and generation drift become `CRG000`; they are never silently skipped.

## Usage

```bash
python -m tools.current_readiness_guard.cli scan revenue/path/to/gate.py
python -m tools.current_readiness_guard.cli --json scan revenue/path/to/gate.py
python -m tools.current_readiness_guard.cli changed --base <base-sha> --head <head-sha>
python -m tools.current_readiness_guard.cli all
```

Exit codes: `0` no unexempted findings, `1` findings, `2` policy/tooling failure.

## Central exemptions only

Inline suppression is unsupported. `policy.json` is the only exception surface; each entry binds exact path + rule and includes rationale, owner, issue, and a non-expired date. An exemption is reviewable debt, not evidence that code is safe.

## Scope ceiling

The current interprocedural model is same-module; it does not authenticate or execute imports. This guard cannot establish buyer facts, source completeness, corporate evidence, pricing, staffing, legal/submission authority, award, payment, or revenue. It only blocks known unsafe source shapes. Direct-to-main pushes can bypass a pull-request-only changed-file workflow unless repository policy prevents them.
