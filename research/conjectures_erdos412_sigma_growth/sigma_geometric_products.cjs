"use strict";

/**
 * Sigma of a product through cached exact component factorizations.
 * Supply sigmaFactorization from sigma_orbit_merge.cjs as the dependency.
 * Pure connected V8 / CommonJS; no imports, native execution, network or I/O.
 */
const limits = Object.freeze({
  component_factor_input_max: "1000000000000",
  max_input_components: 64,
  input_decimal_digits: 2048,
  max_factorizations: 1024,
  max_retained_catalog_entries: 1024,
  default_max_factorizations: 128,
  max_new_factorizations_per_call: 16,
  max_catalog_page: 128,
  component_prime_multiplicity_max: 39,
  combined_prime_multiplicity_max: 2496,
  remainder_tests_per_factorization_upper_bound: 500040,
  quotient_divisions_per_factorization_upper_bound: 39
});
const HARD_COMPONENT_MAX = BigInt(limits.component_factor_input_max);

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}

function natural(value, name) {
  let result;
  if (typeof value === "bigint") result = value;
  else if (typeof value === "number" && Number.isSafeInteger(value)) result = BigInt(value);
  else if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)
      && value.length <= limits.input_decimal_digits) result = BigInt(value);
  else fail("INVALID_INTEGER", name + " must be a nonnegative BigInt, safe integer, or canonical decimal string");
  if (result < 0n || result.toString().length > limits.input_decimal_digits)
    fail("INTEGER_OUT_OF_RANGE", name + " exceeds the supported natural-number range");
  return result;
}

function bound(value, name, minimum, maximum) {
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum)
    fail("INVALID_BOUND", name + " must be an integer from " + minimum + " through " + maximum);
  return value;
}

function copy(value) {
  return JSON.parse(JSON.stringify(value));
}

function createSigmaGeometricProducts(exactFactorSigma, options = {}) {
  if (typeof exactFactorSigma !== "function")
    fail("MISSING_FACTORIZATION_DEPENDENCY", "supply sigmaFactorization from sigma_orbit_merge.cjs");
  if (!options || typeof options !== "object" || Array.isArray(options))
    fail("INVALID_OPTIONS", "options must be an object");
  const componentLimit = options.component_limit === undefined
    ? HARD_COMPONENT_MAX : natural(options.component_limit, "component_limit");
  if (componentLimit < 1n || componentLimit > HARD_COMPONENT_MAX)
    fail("INVALID_COMPONENT_LIMIT", "component_limit must be from 1 through " + limits.component_factor_input_max);
  const maxFactorizations = options.max_factorizations === undefined
    ? limits.default_max_factorizations
    : bound(options.max_factorizations, "max_factorizations", 0, limits.max_factorizations);
  const cache = new Map();
  const catalog = [];
  let importedCatalogEntries = 0;
  let importedPrimePowerReconstructions = 0;
  let completedSteps = 0;
  let stepCalls = 0;
  let componentLookups = 0;
  let cachedComponentLookups = 0;
  let unitComponents = 0;
  let remainderTests = 0;
  let quotientDivisions = 0;
  let trialCandidates = 0;
  let geometricPowerMultiplications = 0;
  let componentPrimePowerReconstructions = 0;

  function describe() {
    return {
      schema: "erdos412.sigma_geometric_products_index/v1",
      component_limit: componentLimit.toString(),
      max_factorizations: maxFactorizations,
      factorizations: catalog.length,
      remaining_factorization_capacity: maxFactorizations - (catalog.length - importedCatalogEntries),
      ...(importedCatalogEntries > 0 ? {
        imported_catalog_entries: importedCatalogEntries,
        fresh_factorizations: catalog.length - importedCatalogEntries
      } : {}),
      retained_catalog_entries: catalog.length,
      completed_steps: completedSteps,
      work: {
        step_calls: stepCalls,
        component_lookups: componentLookups,
        cached_component_lookups: cachedComponentLookups,
        unit_components: unitComponents,
        remainder_tests: remainderTests,
        exact_quotient_divisions: quotientDivisions,
        trial_candidates: trialCandidates,
        geometric_power_multiplications: geometricPowerMultiplications,
        component_prime_power_reconstructions: componentPrimePowerReconstructions,
        ...(importedCatalogEntries > 0 ? {
          imported_component_prime_power_reconstructions: importedPrimePowerReconstructions
        } : {}),
        total_remainder_tests_upper_bound:
          maxFactorizations * limits.remainder_tests_per_factorization_upper_bound
      },
      dependency_contract: "the supplied function is the exact deterministic sigmaFactorization API; reconstruction is checked here, primality comes from that dependency",
      catalog_retained_in_full: true
    };
  }

  function validateFactorization(raw, value) {
    if (!raw || raw.schema !== "erdos412.sigma_factorization/v1"
        || raw.input !== value || raw.factor_product !== value
        || !Array.isArray(raw.prime_powers))
      fail("INVALID_FACTORIZATION_RESULT", "the exact dependency returned an incompatible factorization");
    let product = 1n;
    let multiplicity = 0;
    const seen = new Set();
    for (const factor of raw.prime_powers) {
      const prime = natural(factor.prime, "factor prime");
      const exponent = bound(factor.exponent, "factor exponent", 1, limits.component_prime_multiplicity_max);
      if (prime < 2n || prime > componentLimit || seen.has(prime.toString()))
        fail("INVALID_FACTORIZATION_RESULT", "component prime factors must be distinct and within the input bound");
      seen.add(prime.toString());
      const power = prime ** BigInt(exponent);
      if (power.toString() !== factor.prime_power)
        fail("INVALID_FACTORIZATION_RESULT", "a prime power does not match its base and exponent");
      product *= power;
      multiplicity += exponent;
    }
    if (product.toString() !== value || multiplicity > limits.component_prime_multiplicity_max)
      fail("INVALID_FACTORIZATION_RESULT", "component prime powers do not reconstruct the bounded input");
    if (!raw.work || !Number.isSafeInteger(raw.work.trial_candidates) || raw.work.trial_candidates < 0
        || raw.work.trial_candidates > limits.remainder_tests_per_factorization_upper_bound)
      fail("INVALID_FACTORIZATION_RESULT", "the dependency omitted exact trial-work accounting");
    bound(raw.work.remainder_tests, "factor remainder tests", 0, limits.remainder_tests_per_factorization_upper_bound);
    bound(raw.work.exact_quotient_divisions, "factor quotient divisions", 0, limits.quotient_divisions_per_factorization_upper_bound);
    return copy(raw);
  }

  // Retained records are trusted outputs of the stated exact dependency.
  // This validates their product binding, without calling the factorizer again.
  if (options.retained_catalog !== undefined) {
    if (!Array.isArray(options.retained_catalog)
        || options.retained_catalog.length > limits.max_retained_catalog_entries)
      fail("INVALID_RETAINED_CATALOG", "retained_catalog must contain at most " + limits.max_retained_catalog_entries + " complete entries");
    for (let retainedIndex = 0; retainedIndex < options.retained_catalog.length; retainedIndex += 1) {
      const entry = options.retained_catalog[retainedIndex];
      if (!entry || entry.catalog_index !== retainedIndex)
        fail("INVALID_RETAINED_CATALOG", "retained catalog indices must be consecutive from zero");
      const value = natural(entry.component, "retained component");
      if (value < 2n || value > componentLimit || cache.has(value.toString()))
        fail("INVALID_RETAINED_CATALOG", "retained components must be distinct supported nonunit values");
      const factorization = validateFactorization(entry.factorization, value.toString());
      catalog.push({ catalog_index: retainedIndex, component: value.toString(), factorization });
      cache.set(value.toString(), retainedIndex);
      importedCatalogEntries += 1;
      importedPrimePowerReconstructions += factorization.prime_powers.length;
      componentPrimePowerReconstructions += factorization.prime_powers.length;
    }
  }

  function step(request, newFactorizationBudget = limits.max_new_factorizations_per_call) {
    bound(newFactorizationBudget, "newFactorizationBudget", 1, limits.max_new_factorizations_per_call);
    if (!request || typeof request !== "object" || Array.isArray(request) || !Array.isArray(request.components))
      fail("INVALID_REQUEST", "request.components must be an array");
    if (request.components.length > limits.max_input_components)
      fail("COMPONENT_COUNT_OUT_OF_RANGE", "at most " + limits.max_input_components + " input components are supported");
    const components = request.components.map((value, index) => {
      const parsed = natural(value, "component " + index);
      if (parsed < 1n) fail("NONPOSITIVE_COMPONENT", "components must be positive");
      return parsed;
    });
    const expectedInput = request.expected_input === undefined
      ? null : natural(request.expected_input, "expected_input");
    stepCalls += 1;
    const blocked = components.flatMap((value, index) =>
      value > componentLimit ? [{ component_index: index, value: value.toString() }] : []);
    if (blocked.length) {
      return {
        schema: "erdos412.sigma_geometric_product_step/v1",
        status: "COMPONENT_LIMIT",
        expected_input: expectedInput === null ? null : expectedInput.toString(),
        input_binding: "not_checked_because_a_component_exceeds_the_factor_limit",
        input_components: components.map(String),
        blocked_components: blocked,
        component_limit: componentLimit.toString(),
        new_factorizations_this_call: 0,
        index: describe()
      };
    }

    let input = 1n;
    for (const value of components) input *= value;
    if (expectedInput !== null && input !== expectedInput)
      fail("INPUT_PRODUCT_MISMATCH", "input components do not multiply to expected_input");
    let newFactorizations = 0;
    let cachedLookupsThisCall = 0;
    const refs = [];

    function pending(status, componentIndex) {
      return {
        schema: "erdos412.sigma_geometric_product_step/v1",
        status,
        input: input.toString(),
        input_binding: "component_product_checked",
        input_components: components.map(String),
        completed_component_refs: refs.slice(),
        next_component_index: componentIndex,
        next_component_value: components[componentIndex].toString(),
        new_factorizations_this_call: newFactorizations,
        cached_component_lookups_this_call: cachedLookupsThisCall,
        continuation: {
          request: { components: components.map(String), expected_input: input.toString() },
          semantics: "repeat this unfinished request on this index; completed component factorizations are reused from the catalog"
        },
        index: describe()
      };
    }

    for (let componentIndex = 0; componentIndex < components.length; componentIndex += 1) {
      const value = components[componentIndex].toString();
      componentLookups += 1;
      if (value === "1") {
        unitComponents += 1;
        refs.push(null);
        continue;
      }
      let catalogIndex = cache.get(value);
      if (catalogIndex !== undefined) {
        cachedComponentLookups += 1;
        cachedLookupsThisCall += 1;
      } else {
        if (catalog.length - importedCatalogEntries >= maxFactorizations)
          return pending("FACTORIZATION_LIMIT", componentIndex);
        if (newFactorizations >= newFactorizationBudget)
          return pending("NEEDS_MORE_FACTORIZATIONS", componentIndex);
        const factorization = validateFactorization(exactFactorSigma(value), value);
        catalogIndex = catalog.length;
        catalog.push({ catalog_index: catalogIndex, component: value, factorization });
        cache.set(value, catalogIndex);
        newFactorizations += 1;
        componentPrimePowerReconstructions += factorization.prime_powers.length;
        remainderTests += factorization.work.remainder_tests;
        quotientDivisions += factorization.work.exact_quotient_divisions;
        trialCandidates += factorization.work.trial_candidates;
      }
      refs.push(catalogIndex);
    }

    const exponents = new Map();
    for (const catalogIndex of refs) {
      if (catalogIndex === null) continue;
      for (const factor of catalog[catalogIndex].factorization.prime_powers) {
        const prime = factor.prime;
        exponents.set(prime, (exponents.get(prime) || 0) + factor.exponent);
      }
    }
    const sorted = [...exponents].sort((a, b) => {
      const left = BigInt(a[0]);
      const right = BigInt(b[0]);
      return left < right ? -1 : left > right ? 1 : 0;
    });
    let reconstructedInput = 1n;
    let sigma = 1n;
    let multiplicity = 0;
    const primePowers = [];
    for (const [primeText, exponent] of sorted) {
      const prime = BigInt(primeText);
      let primePower = 1n;
      let geometricSum = 1n;
      for (let powerIndex = 0; powerIndex < exponent; powerIndex += 1) {
        primePower *= prime;
        geometricSum += primePower;
      }
      geometricPowerMultiplications += exponent;
      multiplicity += exponent;
      reconstructedInput *= primePower;
      sigma *= geometricSum;
      primePowers.push({
        prime: primeText, exponent,
        prime_power: primePower.toString(),
        geometric_sum: geometricSum.toString()
      });
    }
    if (reconstructedInput !== input || multiplicity > limits.combined_prime_multiplicity_max)
      fail("INTERNAL_PRODUCT_COMPOSITION_ERROR", "combined prime exponents did not reconstruct the product within the declared bound");
    const completedStepIndex = completedSteps;
    completedSteps += 1;
    const outputComponents = primePowers.map(factor => factor.geometric_sum);
    return {
      schema: "erdos412.sigma_geometric_product_step/v1",
      status: "COMPLETE",
      completed_step_index: completedStepIndex,
      input: input.toString(),
      input_binding: "component_product_and_combined_prime_powers_checked",
      input_components: components.map(String),
      component_catalog_refs: refs,
      prime_powers: primePowers,
      factor_product: reconstructedInput.toString(),
      sigma: sigma.toString(),
      output_components: outputComponents,
      next_component_count_within_bound: outputComponents.length <= limits.max_input_components,
      next_components_within_factor_limit: outputComponents.every(value => BigInt(value) <= componentLimit),
      new_factorizations_this_call: newFactorizations,
      cached_component_lookups_this_call: cachedLookupsThisCall,
      geometric_power_multiplications: multiplicity,
      index: describe()
    };
  }

  function records(page = {}) {
    if (!page || typeof page !== "object" || Array.isArray(page))
      fail("INVALID_PAGE", "page must be an object");
    const start = page.start_index === undefined ? 0
      : bound(page.start_index, "start_index", 0, catalog.length);
    const pageLimit = page.limit === undefined ? limits.max_catalog_page
      : bound(page.limit, "limit", 1, limits.max_catalog_page);
    const end = Math.min(catalog.length, start + pageLimit);
    return {
      schema: "erdos412.sigma_component_catalog_page/v1",
      start_index: start,
      returned_records: end - start,
      current_catalog_count: catalog.length,
      next_start_index: end < catalog.length ? end : null,
      records: copy(catalog.slice(start, end))
    };
  }

  return Object.freeze({ describe, step, records });
}

module.exports = { createSigmaGeometricProducts, limits };
