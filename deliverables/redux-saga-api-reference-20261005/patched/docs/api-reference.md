# API Reference

This page describes the public builders, matchers, and providers of
`redux-saga-test-plan`. The package has four named exports at its entry point:

```js
import { expectSaga, testSaga, matchers, providers } from 'redux-saga-test-plan';
```

`matchers` and `providers` are also available as standalone entry points:

```js
import * as matchers from 'redux-saga-test-plan/matchers';
import { dynamic, throwError, composeProviders } from 'redux-saga-test-plan/providers';
```

## Table of contents

* [Main exports](#main-exports)
* [expectSaga](#expectsaga)
  * [Configuration methods](#configuration-methods)
  * [Effect assertions](#effect-assertions)
  * [Sub-match helpers](#sub-match-helpers)
  * [The result](#the-result)
* [testSaga](#testsaga)
  * [Stepping through the saga](#stepping-through-the-saga)
  * [Effect assertions](#testsaga-effect-assertions)
* [matchers](#matchers)
* [providers](#providers)

## Main exports

| export | description |
| ------ | ----------- |
| `expectSaga(saga, ...sagaArgs)` | Integration-test a saga by actually running it. Chainable API; call `.run()` to start. |
| `testSaga(saga, ...sagaArgs)` | Unit-test a saga by stepping the generator directly. Chainable API; every `next()` advances one step. |
| `matchers` | Effect matchers used with `provide()`, e.g. `matchers.call.fn(fn)`. |
| `providers` | Helpers for `provide()`: `dynamic`, `throwError`, `composeProviders`. |

## expectSaga

`expectSaga(saga, ...sagaArgs)` returns a chainable API. Extra arguments are
passed to `saga` when it runs.

```js
expectSaga(userSaga, api, userId)
  .withState({ users: {} })
  .dispatch({ type: 'REQUEST_USER', payload: { id: 1 } })
  .put({ type: 'RECEIVE_USER', payload: fakeUser })
  .run()
  .then(result => { /* assertions on the result */ });
```

### Configuration methods

| method | description |
| ------ | ----------- |
| `withState(state)` | Set the current store state used by `select`. This does not replace a configured reducer or assert the final state. |
| `withReducer(reducer, initialState?)` | Run the saga against a real reducer, optionally with an initial state. |
| `provide(staticProviders)` | Provide matches for effects so they resolve to static values instead of running. Accepts an array of `[matcher, value]` tuples. |
| `provide(dynamicProviders)` | Provide an object of effect handlers, such as `{ call(effect, next) { ... } }`. Return a value to handle an effect, or return `next()` to delegate it. |
| `dispatch(action)` | Dispatch raw actions into the saga's store. Matches `take` effects by pattern. |
| `not` | A getter that flips the next effect assertion into a negation, e.g. `.not.call(fn)`. |
| `returns(value)` | Assert the saga's final return value. |
| `throws(errorOrConstructor)` | Assert the top-level saga throws an equal error object or an instance of the given error constructor. |
| `hasFinalState(expectedState)` | Assert the final state of the store equals `expectedState`. |
| `delay(ms)` | Delay the next `.dispatch(action)` by `ms`. This is dispatch configuration, not an assertion on a yielded delay effect. |
| `run(timeoutOrConfig?)` | Start the saga and return a `Promise` for the [result](#the-result). Accept a timeout in milliseconds, `false` to disable it, or `{ timeout, silenceTimeout }`. The default is `expectSaga.DEFAULT_TIMEOUT` (250ms). |
| `silentRun(timeout?)` | Like `run`, with timeout warnings suppressed. Assertion failures still reject the returned `Promise`. |

### Effect assertions

These methods register expectations checked when the run finishes or is
cancelled at its timeout. Each accepts the same arguments as its corresponding
effect creator.

`put`, `putResolve`, `call`, `apply`, `cps`, `fork`, `spawn`, `select`,
`take`, `takeMaybe`, `actionChannel`, `race`, `getContext`, `setContext`

Exact effect assertions use deep equality and do not require effects to occur
in the order of the assertions. Each positive assertion consumes one matching
effect from its effect store. Use partial matching to specify only selected
fields of an effect descriptor.

### Sub-match helpers

The following effect assertions expose helpers for partial matching:

| helper | matches by |
| ------ | ---------- |
| `call.like({ fn, args })` | a `call` to `fn` (and optionally `args`) |
| `call.fn(fn)` | a `call` to `fn`, any args |
| `apply.fn(fn)` | an `apply` with function `fn`, regardless of context or args |
| `cps.fn(fn)` | a `cps` call to `fn` |
| `fork.fn(fn)` | a `fork` of `fn` |
| `spawn.fn(fn)` | a `spawn` of `fn` |
| `put.like({ action })` / `put.actionType(type)` | a `put` of any action with `type` (`putResolve` too) |
| `select.like({ selector })` / `select.selector(fn)` | a `select` with the given selector |
| `actionChannel.like({ pattern })` / `actionChannel.pattern(pattern)` | an `actionChannel` for `pattern` |

### The result

`run()` resolves with a result object:

| key | description |
| --- | ----------- |
| `effects` | Remaining captured effects grouped by supported effect type, after effect assertions consume matches; empty groups are omitted. |
| `storeState` | The final state of the store (from the result object's `storeState` property). |
| `returnValue` | The saga's return value. |
| `allEffects` | Captured effects in encounter order, without removing asserted matches. Only effect types tracked by `expectSaga` are captured. |
| `toJSON()` | Return a JSON-friendly representation of the grouped `effects`. |

`run()` itself returns the `Promise`; the result object has no `toPromise()`,
`invokeError`, or `warnings` property. Effects that have no corresponding
assertion are allowed.

## testSaga

`testSaga(saga, ...sagaArgs)` returns a chainable API that drives the
generator directly, so effects are asserted strictly, in order.

```js
testSaga(userSaga, api, 1)
  .next()
  .call(api.get, 1)
  .next(fakeUser)
  .put({ type: 'RECEIVE_USER', payload: fakeUser })
  .next()
  .isDone();
```

### Stepping through the saga

| method | description |
| ------ | ----------- |
| `next(value?)` | Call `iterator.next(value)` once and expose assertions for the resulting value and completion state. |
| `finish(value?)` | Call `iterator.return(value)` once and expose assertions for that result. A `finally` block can still yield; use `isDone()` to assert completion. |
| `restart(...sagaArgs?)` | Restart the saga from the top, optionally with new arguments. |
| `throw(error)` | Throw `error` into the generator (as if a yielded promise rejected). |
| `back(n = 1)` | Remove `n` recorded steps, recreate the generator, and replay the remaining history. Use `restore(label)` for a named save point. |
| `save(label)` | Save the current position under `label`. |
| `restore(label)` | Restore to the position saved under `label`. |

### testSaga effect assertions

Available after `.next(...)`, `.throw(...)`, or `.finish(...)`, accepting the
same arguments as the effect creators and comparing effect descriptors by deep
equality:

`apply`, `call`, `cps`, `delay`, `fork`, `spawn`, `cancel`, `cancelled`,
`put`, `putResolve`, `race`, `select`, `take`, `takeMaybe`, `actionChannel`,
`all`, `flush`, `join`, `getContext`, `setContext`

Saga helpers are matched too: `takeEvery`, `takeLatest`, `takeLeading`,
`throttle`, `debounce`, `retry`.

General assertions:

| method | description |
| ------ | ----------- |
| `isDone()` | Assert the saga has finished (no more steps). |
| `is(value)` | Assert the current iterator result's value deeply equals `value`, without asserting completion. |
| `returns(value)` | Assert the current iterator result is done and its value deeply equals `value`. This does not advance the generator. |
| `inspect(fn)` | Call `fn` with the current iterator result's value for a custom assertion. |

## matchers

Calling a base matcher delegates to the corresponding Redux Saga effect
creator, producing an exact effect descriptor for `provide()`. The exported
base matchers are `actionChannel`, `apply`, `call`, `cancel`, `cancelled`, `cps`,
`flush`, `fork`, `getContext`, `join`, `put`, `putResolve`, `race`, `select`,
`setContext`, `spawn`, `take`, and `takeMaybe`.

Only the helpers listed below create partial matchers; there is no blanket
`.like(...)` helper on every base matcher.

```js
import { call, put, take } from 'redux-saga-test-plan/matchers';

expectSaga(saga)
  .provide([
    [call.fn(api.get), fakeUser],
    [call(api.get, 1), fakeUser],
  ])
  .run();
```

| matcher | matches |
| ------- | ------- |
| `call.fn(fn)` / `call.like({ fn, args })` | a `call` to `fn` (any args) / with given `fn` and optional `args` |
| `apply.fn(fn)` / `apply.like(...)` | an `apply` of `fn` |
| `cps.fn(fn)` / `cps.like(...)` | a `cps` callback call to `fn` |
| `fork.fn(fn)` / `fork.like(...)` | a `fork` of `fn` |
| `spawn.fn(fn)` / `spawn.like(...)` | a `spawn` of `fn` |
| `put.actionType(type)` / `put.like({ action })` | a `put` of an action with `type` |
| `putResolve.actionType(type)` / `putResolve.like({ action })` | a resolving `put` with the selected action fields |
| `select.selector(fn)` / `select.like({ selector })` | a `select` with selector `fn` |
| `actionChannel.pattern(pattern)` / `actionChannel.like({ pattern })` | an `actionChannel` for `pattern` |

Use the base `take(pattern)` and `takeMaybe(pattern)` matchers for exact take
effects. These two matchers do not have `.pattern(...)` or `.like(...)` helpers.

## providers

`providers` are helpers for the `provide()` method:

| helper | description |
| ------ | ----------- |
| `dynamic(fn)` | Wrap a static provider value so `fn(effect, next)` computes the value when its matcher matches. Return `next()` to delegate. |
| `throwError(error)` | Wrap a value that throws `error` when its static provider matches. |
| `composeProviders(...handlers)` | Return a handler that tries the supplied `(effect, next)` handlers in order and uses the first result that does not delegate with `next()`. It returns a function, not an array. |

```js
import { expectSaga } from 'redux-saga-test-plan';
import { throwError } from 'redux-saga-test-plan/providers';
import * as matchers from 'redux-saga-test-plan/matchers';

expectSaga(saga)
  .provide([
    [matchers.call.fn(api.get), throwError(new Error('boom'))],
  ])
  .run();
```
