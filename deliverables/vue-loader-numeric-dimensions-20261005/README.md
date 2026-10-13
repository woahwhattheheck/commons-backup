# Vue Content Loader: preserve numeric SVG dimensions

This patch repairs numeric parsing inside **EHFCEngineering07**'s responsive-width proposal [egoist/vue-content-loader PR #433](https://github.com/egoist/vue-content-loader/pull/433). The broader responsiveness implementation remains that contributor's work.

The candidate uses a restricted decimal matcher for its default drawing dimensions. Valid SVG attribute numbers such as a leading-decimal fraction, an explicit plus sign or an exponent therefore fall back to the default coordinate. The original upstream implementation interpolates those numeric strings into `viewBox`, where they are valid SVG numbers.

The replacement matcher recognizes SVG numeric notation, with an optional pixel suffix, before conversion. Finite nonnegative string dimensions retain their intended coordinate; relative CSS units continue to use the candidate's existing axis fallback. Conversion is checked for finiteness so a decimal string outside JavaScript's finite numeric range does not insert `Infinity` into the default viewBox.

The governing [SVG 1.1 number grammar](https://www.w3.org/TR/SVG11/types.html#DataTypeNumber) permits an optional sign, decimal fractions and optional exponents in attributes. Its [length grammar](https://www.w3.org/TR/SVG11/types.html#DataTypeLength) permits a numeric magnitude with a unit suffix. This patch only converts unitless and pixel strings; it does not attempt to resolve percentages, viewport units or other relative lengths.

## Source and integration

- Contributor: `EHFCEngineering07`.
- Source repository: `EHFCEngineering07/vue-content-loader`.
- PR head: `48507d4f3872b8d5607a8cef2c3e902fe5f18477`.
- Source path: `src/ContentLoader.tsx`.
- Original Git blob: `69910b452f66cf3a278a7c24b0979334f1971ce8`.

The packet retains the complete source before and after the change, `numeric-dimensions.patch`, source metadata and the upstream MIT terms. The upstream README credits EGOIST under MIT, and package metadata also identifies MIT; those source pins are recorded in `SOURCE.json`.

Apply the patch from the root of the pinned PR checkout with `git apply /path/to/numeric-dimensions.patch`, or use `patched/src/ContentLoader.tsx` as the postimage. Reconcile later changes to the existing helper before integration.

The width and height attributes still receive the original prop values. The numeric-prop branch, explicit viewBox selection, fallback dimensions, preserveAspectRatio, slots, gradients, animation, presets and dependencies are unchanged. The existing string fallback for negative magnitudes remains; the numeric-prop branch's prior behavior is outside this patch.

## Acceptance limits

Validation is static comparison with actual source and the published SVG grammar, followed by exact Git readback. No parser inputs were executed, no SVG or Vue rendering was run, and no build, tests, fixtures, workflow or substitute runtime was created or executed.

The existing responsive proposals, including #428, #429, #432 and #433, remain external submissions. This packet does not choose an upstream winner, mutate a contributor's branch or add another full responsive implementation. Upstream build/browser acceptance and the broader [issue #18](https://github.com/egoist/vue-content-loader/issues/18) remain pending. No bounty eligibility, award approval or payment is claimed.
