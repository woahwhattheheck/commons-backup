# pass-js Issue #694 upstream contribution

Submitted upstream as [tinovyatkin/pass-js PR #700](https://github.com/tinovyatkin/pass-js/pull/700), open for maintainer review. Contribution head: `558a17dc5182705ff7bc7ea74a555ed162690958` on `woahwhattheheck/pass-js:feat/poster-generic-694`.

Adds the iOS 27 `posterGeneric` style, `footerFields`, and the documented `PKBarcodeFormatCode39` value. Poster fields hydrate and serialize; `additionalInfoFields` works for poster passes. A supplied `generic` fallback survives constructor hydration, cloning, folder loading, and ZIP loading.

Build and lint passed. Full upstream suite: 138 passed, 3 environment-dependent skips. Physical Wallet rendering remains untested. Hosted workflows currently require maintainer approval to run.

PR #699 covers separate featured actions and is not the #694 delivery. The original preserved patch is historical candidate material: its malformed hunks and undocumented `PKBarcodeFormat39` spelling were corrected in the upstream contribution. Other fallback-style combinations retain the library's existing behavior. Submission is distinct from merge, award approval, and payment.
