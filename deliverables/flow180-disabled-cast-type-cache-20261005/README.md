# Omit unused standalone cast caches with checks disabled

The existing fix for issue180 avoids a runtime type cache for annotated variable declarations when both assertions and warnings are disabled. The standalone TypeCastExpression path still converts the type and generates an unused cache before removing the cast. Inside a generic function, that conversion can reference a type parameter which the disabled Function visitor never creates in the runtime body. The original issue documents the same failure mechanism for an annotated variable declaration.

This follow-up preserves the underlying expression and returns before creating or updating that unused cache. It uses the existing shouldCheck flag, which is shouldAssert OR shouldWarn. Assertion and warning modes continue through the existing conversion/check path.

## Integration

Integrate this patch into [gajus/flow-runtime PR285](https://github.com/gajus/flow-runtime/pull/285) after reconciling its current head. The exact preparation head is `a838eb5a3d7ac0f3ad009fd5c2a75a144eafd2fb`; original transformVisitors.js blob `d0e31b0c01f76caea56ba3492014ef215f1a8f9e`. Complete before/after sources, exact patch and the unchanged MIT license are included.

This packet retains dicnunz's existing variable-declaration fix. PR292 by selimeneserd independently fixes that original path; PR296 by ncthuc2004 is closed and unmerged and shares PR285's production blob. Their authorship and reward custody are unchanged. There is no new upstream submission or change to another contributor's branch.

## Why this branch is necessary

- transformVisitors defines shouldCheck from assertions or warnings.
- Function returns before adding runtime type-parameter definitions when shouldCheck is false.
- GenericTypeAnnotation conversion directly references a known type parameter; that conversion is unnecessary for an unchecked ordinary statement cast.
- The old TypeCastExpression statement path creates/updates valueUid through convert before its final shouldCheck conditional. Its false branch merely unwraps the expression, leaving the earlier cache.
- AssignmentExpression also returns when checks are disabled, so that generated statement-cast cache is not used by later assignment checks.
- The new branch is after the existing special typed-catch and explicit reify handling, and after the non-statement-cast branch. Those behaviors and enabled checks remain exact.
- The underlying expression is retained; this is not deletion of its evaluation. No type-cache allocation/conversion occurs on this ordinary disabled-check branch.

This is a source-bound correction, not an executed reproduction. The packet does not claim that all generic, reify, typed-catch, annotation-only or async-return issues are resolved. It changes only the ordinary standalone cast branch. Concurrent compiler work in Function or convert is separate and must be composed by hunk after current-head reconciliation.

## Validation state

Static inspection of the actual visitor, generic converter and annotation visitor; exact source/patch comparison only. No target execution, compiler, runtime, installation, tests, fixtures, workflow or hosted check was performed. Existing authors' reported checks remain their own observations. Upstream build/runtime acceptance and IssueHunt award/payment remain pending.

Source background: [issue180](https://github.com/gajus/flow-runtime/issues/180), [PR285](https://github.com/gajus/flow-runtime/pull/285), [PR292](https://github.com/gajus/flow-runtime/pull/292), [PR296](https://github.com/gajus/flow-runtime/pull/296).
