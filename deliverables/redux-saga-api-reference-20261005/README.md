# Redux Saga Test Plan API-reference correction

The API-reference document proposed in [upstream PR395](https://github.com/jfairbank/redux-saga-test-plan/pull/395) directs readers to nonexistent imports and helper methods, and gives several public methods the wrong behavior. This packet corrects that document against the unchanged library implementation. It is a continuation patch for the existing contribution by popsous, with original source, corrected source, and an applicable unified patch.

Current upstream master is `9199c6cf7b1359a19168eba6b41a56bc4633df18`, also PR395's base. PR395 remains open at `7748deb994e8ecee46362f447f1446ec7c0db58f`; its original document blob is `2ae123fb6e2a979c461ed3e63180376fdd6dabbd`. [Issue93](https://github.com/jfairbank/redux-saga-test-plan/issues/93) asks for a compact API reference. The independent open [PR393](https://github.com/jfairbank/redux-saga-test-plan/pull/393) by dicnunz also proposes a reference; both contributors and their existing submissions are preserved.

The correction covers these user-facing contracts:

- Import the four actual root exports. Import `throwError` from the providers entry point; there are no root `provide` or `throwError` exports.
- Describe dynamic providers as effect-handler objects receiving `(effect, next)`. `dynamic` wraps a static provider value, and `composeProviders` returns a handler function.
- Describe `withState` as setting state, `delay` as configuring the next dispatch, and `silentRun` as suppressing timeout warnings. Explain supported timeout forms.
- Describe effect matching as deep equality without positional ordering in `expectSaga`. Remove nonexistent `take` partial helpers and the claim that every matcher has `.like`.
- List the actual run result fields and explain that matching assertions consume entries from grouped effect stores while `allEffects` retains captured entries.
- Describe `testSaga.finish`, numeric history rewind, `is`, `returns`, and `inspect` according to the iterator operations and public signatures. Remove the broken time-travel table-of-contents entry.

All edits are confined to `docs/api-reference.md`. The existing executable examples, library implementation, dependencies, and workflow configuration are not part of the patch.

## Apply to the existing candidate

At PR395 head `7748deb994e8ecee46362f447f1446ec7c0db58f`, from the repository root:

```sh
git apply /path/to/api-reference.patch
```

The patch is tied to that document preimage. Reconcile subsequent contributor edits before applying it to a newer head. The full corrected document is also available at `patched/docs/api-reference.md`; `original/docs/api-reference.md` is the exact retained preimage.

## Source and acceptance limits

`SOURCE.json` pins the complete source evidence used for the correction: root exports; both public builders; provider dispatch, composition, and wrappers; matcher exports; expectation consumption; and equality/history handling. These are production library files. No test or example was executed or added. The executor was offline; package installation, documentation rendering, build, and runtime acceptance remain unperformed. This is a source patch, not upstream acceptance, issue closure, or a bounty-payment claim.

The repository root and README contain no contribution-guide link or root CONTRIBUTING file in the inspected current listing. No upstream branch, PR, issue comment, or external account was changed. The upstream MIT license and Jeremy Fairbank attribution are retained in `LICENSE`.
