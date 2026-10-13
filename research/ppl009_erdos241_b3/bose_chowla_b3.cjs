"use strict";

// Classical Bose-Chowla construction, specialized to prime fields and order 3.
// Source attribution and exact certificate contracts: BOSE_CHOWLA_B3_API.md.
const BOSE_CHOWLA_B3_LIMITS = Object.freeze({
  min_prime: 2,
  max_prime: 43,
  max_field_elements: 79507,
  max_primitive_candidates: 4096,
  max_field_multiplications: 2000000
});

function constructBoseChowlaB3(options) {
  if (!options || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const p = options.prime;
  if (!Number.isSafeInteger(p) || p < BOSE_CHOWLA_B3_LIMITS.min_prime ||
      p > BOSE_CHOWLA_B3_LIMITS.max_prime) {
    throw new RangeError("prime must be an integer from 2 through 43");
  }
  const primeTests = [];
  for (let divisor = 2; divisor * divisor <= p; divisor++) {
    const remainder = p % divisor;
    primeTests.push({ divisor, remainder });
    if (remainder === 0) throw new RangeError("prime is composite");
  }
  if (!Array.isArray(options.cubic_coefficients) ||
      options.cubic_coefficients.length !== 3) {
    throw new TypeError("cubic_coefficients must be [constant, linear, quadratic]");
  }
  const polynomial = Array.from(options.cubic_coefficients, value => {
    if (!Number.isSafeInteger(value) || value < 0 || value >= p) {
      throw new RangeError("cubic coefficients must be canonical residues modulo prime");
    }
    return value === 0 ? 0 : value;
  });
  const mod = value => ((value % p) + p) % p;
  const work = {
    prime_trial_divisors: primeTests.length,
    polynomial_root_evaluations: 0,
    primitive_candidates_tested: 0,
    field_power_calls: 0,
    power_result_multiplications: 0,
    power_squarings: 0,
    field_multiplications: 0,
    degree_certificate_products: 0,
    cycle_steps: 0,
    discrete_log_lookups: 0,
    cyclic_gaps_examined: 0,
    triple_sums_enumerated: 0,
    subsets_enumerated: 0
  };
  const rootValues = [];
  for (let value = 0; value < p; value++) {
    const result = mod(mod(mod(value + polynomial[2]) * value + polynomial[1]) *
      value + polynomial[0]);
    work.polynomial_root_evaluations++;
    rootValues.push({ argument: value, value: result });
    if (result === 0) {
      const error = new Error("the monic cubic has a base-field root");
      error.name = "ReduciblePolynomialError";
      error.root_witness = { prime: p, cubic_coefficients: polynomial.slice(), root: value };
      throw error;
    }
  }

  const fieldSize = p * p * p, order = fieldSize - 1, p2 = p * p;
  if (fieldSize > BOSE_CHOWLA_B3_LIMITS.max_field_elements) {
    throw new RangeError("field exceeds the complete-table limit");
  }
  const decode = code => [code % p, Math.floor(code / p) % p, Math.floor(code / p2)];
  const encode = values => values[0] + p * values[1] + p2 * values[2];
  function multiply(left, right) {
    if (work.field_multiplications >= BOSE_CHOWLA_B3_LIMITS.max_field_multiplications) {
      const error = new RangeError("field multiplication budget exhausted");
      error.work = { ...work };
      throw error;
    }
    work.field_multiplications++;
    const a = decode(left), b = decode(right), coefficients = Array(5).fill(0);
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) coefficients[i + j] += a[i] * b[j];
    }
    for (let i = 0; i < 5; i++) coefficients[i] = mod(coefficients[i]);
    for (let degree = 4; degree >= 3; degree--) {
      const leading = coefficients[degree];
      coefficients[degree] = 0;
      for (let i = 0; i < 3; i++) {
        coefficients[degree - 3 + i] =
          mod(coefficients[degree - 3 + i] - leading * polynomial[i]);
      }
    }
    return encode(coefficients);
  }
  function power(base, exponent) {
    work.field_power_calls++;
    let result = 1, factor = base, remaining = exponent;
    while (remaining > 0) {
      if (remaining % 2 === 1) {
        result = multiply(result, factor);
        work.power_result_multiplications++;
      }
      remaining = Math.floor(remaining / 2);
      if (remaining > 0) {
        factor = multiply(factor, factor);
        work.power_squarings++;
      }
    }
    return result;
  }

  const orderFactorization = [];
  let remainingOrder = order;
  for (let prime = 2; prime * prime <= remainingOrder; prime++) {
    if (remainingOrder % prime !== 0) continue;
    let exponent = 0;
    while (remainingOrder % prime === 0) {
      remainingOrder /= prime;
      exponent++;
    }
    orderFactorization.push({ prime, exponent });
  }
  if (remainingOrder > 1) orderFactorization.push({ prime: remainingOrder, exponent: 1 });
  const candidateRecords = [];
  function assessGenerator(candidate) {
    work.primitive_candidates_tested++;
    const record = {
      candidate_code: candidate,
      candidate_coefficients: decode(candidate),
      prime_factor_tests: [],
      full_order_power_code: null,
      primitive: false
    };
    for (const factor of orderFactorization) {
      const exponent = order / factor.prime;
      const value = power(candidate, exponent);
      record.prime_factor_tests.push({
        order_prime_factor: factor.prime,
        exponent,
        power_code: value,
        power_coefficients: decode(value)
      });
      if (value === 1) {
        candidateRecords.push(record);
        return null;
      }
    }
    record.full_order_power_code = power(candidate, order);
    if (record.full_order_power_code !== 1) {
      throw new Error("finite-field multiplicative-order invariant failed");
    }
    record.primitive = true;
    candidateRecords.push(record);
    return record;
  }

  let selected = null;
  const automatic = options.generator_code === undefined;
  if (!automatic) {
    const candidate = options.generator_code;
    if (!Number.isSafeInteger(candidate) || candidate < 1 || candidate >= fieldSize) {
      throw new RangeError("generator_code must be a nonzero encoded field element");
    }
    selected = assessGenerator(candidate);
    if (selected === null) {
      const error = new Error("the supplied field element is not primitive");
      error.name = "NonPrimitiveElementError";
      error.order_witness = candidateRecords[0];
      throw error;
    }
  } else {
    for (let candidate = p; candidate < fieldSize && selected === null; candidate++) {
      if (work.primitive_candidates_tested >= BOSE_CHOWLA_B3_LIMITS.max_primitive_candidates) {
        const error = new RangeError("primitive-element candidate limit exhausted");
        error.candidate_records = candidateRecords;
        error.work = { ...work };
        throw error;
      }
      selected = assessGenerator(candidate);
    }
    if (selected === null) throw new Error("no primitive element found in the complete field");
  }
  const theta = selected.candidate_code, thetaCoordinates = decode(theta);
  const thetaSquared = multiply(theta, theta);
  work.degree_certificate_products++;
  const squareCoordinates = decode(thetaSquared);
  const determinant = mod(thetaCoordinates[1] * squareCoordinates[2] -
    thetaCoordinates[2] * squareCoordinates[1]);
  if (determinant === 0) throw new Error("degree-three basis certificate failed");

  const logs = new Int32Array(fieldSize);
  logs.fill(-1);
  const powers = [];
  let current = 1;
  for (let exponent = 0; exponent < order; exponent++) {
    if (current <= 0 || current >= fieldSize || logs[current] !== -1) {
      throw new Error("complete primitive power cycle invariant failed");
    }
    logs[current] = exponent;
    powers.push(current);
    current = multiply(current, theta);
    work.cycle_steps++;
  }
  if (current !== 1) throw new Error("primitive power cycle did not close at its order");

  const offsets = [];
  for (let offset = 0; offset < p; offset++) {
    const coordinates = thetaCoordinates.slice();
    coordinates[0] = mod(coordinates[0] + offset);
    const code = encode(coordinates), exponent = logs[code];
    work.discrete_log_lookups++;
    if (exponent < 1 || exponent >= order) {
      throw new Error("Bose-Chowla affine-line exponent invariant failed");
    }
    offsets.push({
      offset,
      target_code: code,
      target_coefficients: coordinates,
      canonical_exponent: exponent
    });
  }
  const residues = offsets.map(row => row.canonical_exponent).sort((a, b) => a - b);
  if (new Set(residues).size !== p) throw new Error("affine offsets did not produce distinct exponents");

  const gaps = [];
  let largestGap = null;
  for (let index = 0; index < residues.length; index++) {
    const from = residues[index], to = residues[(index + 1) % residues.length];
    const distance = index + 1 < residues.length ? to - from : order + to - from;
    const record = { from, to, distance, wraps_zero: index + 1 === residues.length };
    gaps.push(record);
    work.cyclic_gaps_examined++;
    if (largestGap === null || distance > largestGap.distance ||
        (distance === largestGap.distance && to < largestGap.to)) {
      largestGap = record;
    }
  }
  const start = largestGap.to;
  const residueMod = value => ((value % order) + order) % order;
  const mapped = offsets.map(row => ({
    offset: row.offset,
    canonical_exponent: row.canonical_exponent,
    positive_integer: residueMod(row.canonical_exponent - start) + 1
  })).sort((a, b) => a.positive_integer - b.positive_integer);
  const values = mapped.map(row => row.positive_integer);
  const bound = order - largestGap.distance + 1;
  if (values[0] !== 1 || values[values.length - 1] !== bound) {
    throw new Error("largest-gap positive interval invariant failed");
  }

  return {
    schema: "erdos241.bose_chowla_b3/v1",
    status: "EXACT_CONSTRUCTED_B3_SET",
    prime: p,
    order_of_sums: 3,
    cubic_coefficients: polynomial,
    field_size: fieldSize,
    cyclic_modulus: order,
    prime_certificate: {
      trial_divisor_limit: Math.floor(Math.sqrt(p)),
      trial_remainders: primeTests
    },
    irreducibility_certificate: {
      degree: 3,
      monic: true,
      base_field_root_values: rootValues,
      reason: "a reducible cubic over a field has a linear factor"
    },
    field_encoding: {
      basis: ["1", "alpha", "alpha^2"],
      code: "c0 + prime*c1 + prime^2*c2",
      coefficient_order: "constant, linear, quadratic",
      reduction: "alpha^3 = -f0 - f1*alpha - f2*alpha^2 modulo prime"
    },
    multiplicative_order_factorization: orderFactorization,
    generator_search: {
      mode: automatic ? "increasing_codes_outside_base_field" : "supplied_code",
      automatic_first_code: automatic ? p : null,
      candidate_records: candidateRecords,
      selected_code: theta,
      selected_coefficients: thetaCoordinates
    },
    degree_three_certificate: {
      basis_columns: [[1, 0, 0], thetaCoordinates, squareCoordinates],
      theta_squared_code: thetaSquared,
      determinant_mod_prime: determinant,
      determinant_nonzero: true
    },
    power_cycle: {
      exponent_start: 0,
      exponent_end_inclusive: order - 1,
      codes: powers,
      unique_nonzero_codes: powers.length,
      next_code_after_cycle: current,
      interpretation: "codes[e] is theta^e; the complete table is invertible to discrete logs"
    },
    affine_offset_exponents: offsets,
    canonical_residues: residues,
    interval_lift: {
      largest_gap: largestGap,
      all_cyclic_gaps: gaps,
      tied_largest_gaps: gaps.filter(gap => gap.distance === largestGap.distance),
      start_residue: start,
      residue_translation: residueMod(1 - start),
      mapping: "b(a) = ((a - start_residue) mod cyclic_modulus) + 1",
      values,
      mapped_elements: mapped,
      minimum: 1,
      maximum: bound,
      optimal_among_cyclic_cuts_of_this_set: true,
      optimized_over_field_choices_or_unit_multipliers: false
    },
    theorem_consequences: {
      cardinality: p,
      repetitions_in_triples_allowed: true,
      equal_sums_identify_multisets: true,
      modular_B3: true,
      positive_integer_B3: true,
      unordered_triples_with_repetition: p * (p + 1) * (p + 2) / 6,
      distinct_triple_sum_residues: p * (p + 1) * (p + 2) / 6,
      triple_sums_enumerated: false,
      finite_lower_bound: { notation: "f(N)", N: bound, at_least: p },
      extremal_equality_claimed: false,
      asymptotic_improvement_claimed: false,
      external_frontier_claimed: false
    },
    limits: { ...BOSE_CHOWLA_B3_LIMITS },
    work
  };
}


const CYCLIC_ORBIT_LIMITS = Object.freeze({
  max_modulus: 65536,
  max_raw_residues: 1024,
  max_distinct_residues: 256,
  max_symmetries: 64,
  max_classes: 8192,
  max_representative_residue_evaluations: 2000000,
  max_optimal_unit_cuts: 65536,
  max_source_id_characters: 512
});

// Optimizes an identified finite cyclic set. It does not certify a B3 premise.
function minimizeCyclicUnitOrbit(options) {
  if (!options || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError("options must be an object");
  }
  const modulus = options.modulus;
  if (!Number.isSafeInteger(modulus) || modulus < 2 ||
      modulus > CYCLIC_ORBIT_LIMITS.max_modulus) {
    throw new RangeError("modulus must be an integer from 2 through 65536");
  }
  if (typeof options.source_id !== "string" || !options.source_id.trim() ||
      options.source_id.length > CYCLIC_ORBIT_LIMITS.max_source_id_characters) {
    throw new TypeError("source_id must be a nonempty string of at most 512 characters");
  }
  if (!Array.isArray(options.residues) || options.residues.length < 1 ||
      options.residues.length > CYCLIC_ORBIT_LIMITS.max_raw_residues) {
    throw new RangeError("residues must contain from 1 through 1024 raw entries");
  }
  function residue(value, label) {
    if (!Number.isSafeInteger(value) || value < 0 || value >= modulus) {
      throw new RangeError(label + " must be a canonical residue");
    }
    return value === 0 ? 0 : value;
  }
  const values = [...new Set(Array.from(options.residues, value =>
    residue(value, "input residue")))].sort((a, b) => a - b);
  if (values.length > CYCLIC_ORBIT_LIMITS.max_distinct_residues) {
    throw new RangeError("too many distinct residues");
  }
  const mod = value => ((value % modulus) + modulus) % modulus;
  const work = {
    gcd_calls: 0,
    euclidean_steps: 0,
    symmetry_residue_evaluations: 0,
    symmetry_group_products: 0,
    unit_candidates_examined: 0,
    coset_member_products: 0,
    representative_residue_evaluations: 0,
    gap_records: 0,
    optimal_cut_records: 0,
    best_lift_residue_evaluations: 0,
    source_field_multiplications: 0,
    source_field_powers_recomputed: 0,
    triple_sums_enumerated: 0
  };
  function gcd(a, b) {
    work.gcd_calls++;
    while (b !== 0) {
      const next = a % b;
      a = b;
      b = next;
      work.euclidean_steps++;
    }
    return a;
  }
  const inputSymmetries = options.symmetries === undefined ?
    (modulus === 2 ? [{ multiplier: 1, sign: 1, translation: 0 }] : [
      { multiplier: 1, sign: 1, translation: 0 },
      { multiplier: modulus - 1, sign: -1, translation: 0 }
    ]) : options.symmetries;
  if (!Array.isArray(inputSymmetries) || inputSymmetries.length < 1 ||
      inputSymmetries.length > CYCLIC_ORBIT_LIMITS.max_symmetries) {
    throw new RangeError("symmetries must contain from 1 through 64 records");
  }
  const multiplierSet = new Set();
  const symmetries = Array.from(inputSymmetries, (row, index) => {
    if (!row || typeof row !== "object" || Array.isArray(row) ||
        (row.sign !== 1 && row.sign !== -1)) {
      throw new TypeError("each symmetry needs multiplier, sign 1 or -1, and translation");
    }
    const multiplier = residue(row.multiplier, "symmetry multiplier");
    const translation = residue(row.translation, "symmetry translation");
    if (multiplier === 0 || gcd(multiplier, modulus) !== 1) {
      throw new RangeError("a symmetry multiplier must be a unit");
    }
    if (multiplierSet.has(multiplier)) throw new TypeError("duplicate symmetry multiplier");
    multiplierSet.add(multiplier);
    const image = values.map(value => {
      work.symmetry_residue_evaluations++;
      return mod(multiplier * value);
    }).sort((a, b) => a - b);
    const expected = values.map(value => mod(row.sign * value + translation))
      .sort((a, b) => a - b);
    if (image.some((value, i) => value !== expected[i])) {
      const error = new Error("supplied symmetry does not preserve the source set as stated");
      error.name = "InvalidSymmetryError";
      error.symmetry_index = index;
      error.observed_image = image;
      error.expected_image = expected;
      throw error;
    }
    return {
      multiplier,
      sign: row.sign,
      translation,
      image_residues: image,
      set_relation_checked: true
    };
  }).sort((a, b) => a.multiplier - b.multiplier);
  if (!multiplierSet.has(1)) throw new TypeError("the symmetry multipliers must include identity");
  for (const left of symmetries) {
    for (const right of symmetries) {
      const product = mod(left.multiplier * right.multiplier);
      work.symmetry_group_products++;
      if (!multiplierSet.has(product)) {
        const error = new Error("symmetry multipliers are not a closed subgroup");
        error.name = "InvalidSymmetryGroupError";
        error.closure_witness = { left: left.multiplier, right: right.multiplier, product };
        throw error;
      }
    }
  }

  const units = [];
  for (let value = 1; value < modulus; value++) {
    work.unit_candidates_examined++;
    if (gcd(value, modulus) === 1) units.push(value);
  }
  const classCount = units.length / symmetries.length;
  if (!Number.isSafeInteger(classCount)) throw new Error("subgroup order does not divide unit count");
  if (classCount > CYCLIC_ORBIT_LIMITS.max_classes) throw new RangeError("too many quotient classes");
  if (classCount * values.length > CYCLIC_ORBIT_LIMITS.max_representative_residue_evaluations) {
    throw new RangeError("representative residue budget exceeded");
  }
  const assigned = new Set(), classes = [];
  for (const representative of units) {
    if (assigned.has(representative)) continue;
    const members = symmetries.map(symmetry => {
      work.coset_member_products++;
      return mod(representative * symmetry.multiplier);
    }).sort((a, b) => a - b);
    for (const member of members) {
      if (assigned.has(member)) throw new Error("unit cosets overlap");
      assigned.add(member);
    }
    classes.push({ representative, unit_members: members });
  }
  if (assigned.size !== units.length || classes.length !== classCount) {
    throw new Error("unit quotient coverage is incomplete");
  }

  let bestGap = 0;
  for (const orbitClass of classes) {
    const image = values.map(value => {
      work.representative_residue_evaluations++;
      return mod(orbitClass.representative * value);
    }).sort((a, b) => a - b);
    const gaps = [];
    let largest = 0;
    for (let index = 0; index < image.length; index++) {
      const from = image[index], to = image[(index + 1) % image.length];
      const distance = index + 1 < image.length ? to - from : modulus + to - from;
      gaps.push({ from, to, distance, wraps_zero: index + 1 === image.length });
      largest = Math.max(largest, distance);
      work.gap_records++;
    }
    orbitClass.transformed_residues = image;
    orbitClass.cyclic_gaps = gaps;
    orbitClass.largest_gap_distance = largest;
    orbitClass.largest_gaps = gaps.filter(gap => gap.distance === largest);
    orbitClass.minimum_interval_length = modulus - largest + 1;
    bestGap = Math.max(bestGap, largest);
  }
  const bestClasses = classes.filter(orbitClass => orbitClass.largest_gap_distance === bestGap);
  const attainmentCount = bestClasses.reduce((sum, orbitClass) =>
    sum + orbitClass.largest_gaps.length * symmetries.length, 0);
  if (attainmentCount > CYCLIC_ORBIT_LIMITS.max_optimal_unit_cuts) {
    throw new RangeError("too many complete optimal unit/cut records");
  }
  const optimalCuts = [];
  for (const orbitClass of bestClasses) {
    const representative = orbitClass.representative;
    for (const symmetry of symmetries) {
      const unit = mod(representative * symmetry.multiplier);
      const shift = mod(representative * symmetry.translation);
      const transform = value => mod(symmetry.sign * value + shift);
      for (const gap of orbitClass.largest_gaps) {
        const from = symmetry.sign === 1 ? transform(gap.from) : transform(gap.to);
        const to = symmetry.sign === 1 ? transform(gap.to) : transform(gap.from);
        optimalCuts.push({
          unit,
          representative,
          symmetry_multiplier: symmetry.multiplier,
          sign: symmetry.sign,
          shift,
          gap_from: from,
          gap_to: to,
          gap_distance: bestGap,
          start_residue: to,
          residue_translation: mod(1 - to),
          interval_length: modulus - bestGap + 1
        });
        work.optimal_cut_records++;
      }
    }
  }
  optimalCuts.sort((a, b) => a.unit - b.unit || a.start_residue - b.start_residue);
  const best = optimalCuts[0];
  const mapped = values.map(value => {
    work.best_lift_residue_evaluations++;
    const transformed = mod(best.unit * value);
    return {
      source_residue: value,
      multiplied_residue: transformed,
      positive_integer: mod(transformed - best.start_residue) + 1
    };
  }).sort((a, b) => a.positive_integer - b.positive_integer);
  const positive = mapped.map(row => row.positive_integer);
  if (positive[0] !== 1 || positive[positive.length - 1] !== best.interval_length) {
    throw new Error("optimal interval endpoint invariant failed");
  }
  return {
    schema: "cyclic.unit_orbit_interval/v1",
    status: "EXACT_AFFINE_ORBIT_MINIMUM",
    source_id: options.source_id,
    modulus,
    source_residues: values,
    raw_residue_entries: options.residues.length,
    duplicate_residues_removed: options.residues.length - values.length,
    symmetries,
    coverage: {
      unit_count: units.length,
      symmetry_group_order: symmetries.length,
      quotient_class_count: classes.length,
      class_sizes: symmetries.length,
      covered_units: assigned.size,
      complete_disjoint_unit_cosets: true,
      subgroup_closure_checked: true
    },
    classes,
    maximum_empty_gap_distance: bestGap,
    minimum_positive_interval_length: modulus - bestGap + 1,
    optimal_representatives: bestClasses.map(row => row.representative),
    optimal_unit_cuts: optimalCuts,
    best: {
      ...best,
      mapped_elements: mapped,
      positive_values: positive
    },
    validity_boundary: {
      source_id_authenticated: false,
      source_B3_property_checked: false,
      supplied_symmetry_relations_checked: true,
      optimum_scope: "unit multiplications and translations of this finite cyclic source set",
      global_extremal_optimum_claimed: false
    },
    limits: { ...CYCLIC_ORBIT_LIMITS },
    work
  };
}

module.exports = {
  constructBoseChowlaB3,
  BOSE_CHOWLA_B3_LIMITS,
  minimizeCyclicUnitOrbit,
  CYCLIC_ORBIT_LIMITS
};
