"use strict";

/**
 * Exact recurrent subsequences of floor(n * (u + sign*sqrt(D))/v).
 * A supplied positive norm-one Pell unit is checked once by the compiler.
 * Retained navigation trusts the saved mathematical power/seed premises.
 * Dependency-free CommonJS; no I/O or floating-point approximations.
 */
const QUADRATIC_BEATTY_LIMITS = Object.freeze({
  input_digits: 32, output_digits: 16384,
  max_index: 256, power_rows: 9, page_size: 32
});
function label(x) {
  if (typeof x !== "string" || x.length === 0 || x.length > 512)
    throw new TypeError("source_id must be a nonempty string of at most 512 code units");
  return x;
}
function object(x, name) {
  if (!x || typeof x !== "object" || Array.isArray(x))
    throw new TypeError(name + " must be an object");
  return x;
}
function whole(x, name, low, high) {
  if (!Number.isSafeInteger(x) || x < low || x > high)
    throw new RangeError(name + " must be a safe integer in [" + low + "," + high + "]");
  return x;
}
function dec(x, name, digits, minimum) {
  if (typeof x === "number") {
    if (!Number.isSafeInteger(x)) throw new TypeError(name + " number must be a safe integer");
    x = String(x);
  } else if (typeof x === "bigint") x = x.toString();
  if (typeof x !== "string" || !/^(?:0|-?[1-9][0-9]*)$/.test(x))
    throw new TypeError(name + " must be a canonical decimal integer");
  const n = x[0] === "-" ? x.length - 1 : x.length;
  if (n > digits) throw new RangeError(name + " exceeds the decimal digit cap");
  const b = BigInt(x);
  if (minimum !== undefined && b < minimum) throw new RangeError(name + " is below its minimum");
  return b;
}
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function bounded(x) {
  const t = x < 0n ? -x : x;
  if (t.toString().length > QUADRATIC_BEATTY_LIMITS.output_digits)
    throw new RangeError("A computed integer exceeds the output digit cap");
  return x;
}
function mul(a, b) {
  if (a === 0n || b === 0n) return 0n;
  const da = (a < 0n ? -a : a).toString().length;
  const db = (b < 0n ? -b : b).toString().length;
  if (da + db - 1 > QUADRATIC_BEATTY_LIMITS.output_digits)
    throw new RangeError("A product exceeds the output digit cap");
  return bounded(a * b);
}
function add(a, b) { return bounded(a + b); }
function sqrtFloor(D) {
  let lo = 0n, hi = 1n << BigInt(Math.ceil(D.toString(2).length / 2));
  let iterations = 0;
  while (hi - lo > 1n) {
    const mid = (lo + hi) / 2n;
    if (mid * mid <= D) lo = mid; else hi = mid;
    iterations++;
  }
  return {value: lo, iterations};
}
function applyPower(state, power) {
  const x = add(mul(power.p, state.x), mul(power.dq, state.z));
  const z = add(mul(power.q, state.x), mul(power.p, state.z));
  return {x, z};
}
function stateRow(index, state, u, v, sign) {
  const n = mul(v, state.z);
  const a = add(mul(u, state.z), sign === 1 ? state.x : -state.x);
  if (n <= 0n || a <= 0n) throw new RangeError("The constructed index and value must be positive");
  return [index, state.x.toString(), state.z.toString(), n.toString(), a.toString()];
}

function compileQuadraticBeattyIndex(request) {
  object(request, "request");
  const source_id = label(request.source_id), cap = QUADRATIC_BEATTY_LIMITS.input_digits;
  const D = dec(request.D, "D", cap, 1n), u = dec(request.u, "u", cap);
  const v = dec(request.v, "v", cap, 1n), p = dec(request.p, "p", cap, 1n);
  const q = dec(request.q, "q", cap, 1n);
  if (request.sign !== 1 && request.sign !== -1) throw new RangeError("sign must be 1 or -1");
  const sign = request.sign, root = sqrtFloor(D), s = root.value;
  if (s * s === D) throw new RangeError("D must be nonsquare");
  if (p * p - D * q * q !== 1n) throw new RangeError("The supplied p,q must satisfy p^2-D*q^2=1");
  const t = u - v;
  const slopeAboveOne = sign === 1 ? (t >= 0n || D > t * t) : (t > 0n && t * t > D);
  if (!slopeAboveOne) throw new RangeError("(u+sign*sqrt(D))/v must be greater than one");
  const seed = {x: sign === 1 ? s : s + 1n, z: 1n};
  const seedNorm = seed.x * seed.x - D;
  const powers = [];
  let power = {p, q, dq: D * q};
  for (let j = 0; j < QUADRATIC_BEATTY_LIMITS.power_rows; j++) {
    powers.push([2 ** j, power.p.toString(), power.q.toString(), power.dq.toString()]);
    if (j + 1 < QUADRATIC_BEATTY_LIMITS.power_rows) {
      power = {
        p: add(mul(power.p, power.p), mul(power.q, power.dq)),
        q: mul(2n, mul(power.p, power.q)),
        dq: mul(2n, mul(power.p, power.dq))
      };
    }
  }
  const next = applyPower(seed, {p, q, dq: D * q});
  const initial = [stateRow(0, seed, u, v, sign), stateRow(1, next, u, v, sign)];
  const parameters = {D: D.toString(), u: u.toString(), v: v.toString(), sign,
    p: p.toString(), q: q.toString()};
  const snapshot = {
    schema: "kimberling.quadratic_beatty_pell_index/v1", source_id,
    max_index: QUADRATIC_BEATTY_LIMITS.max_index, parameters,
    sqrt_floor: s.toString(), seed_norm: seedNorm.toString(),
    recurrence_coefficient: (2n * p).toString(),
    initial_state_columns: ["index", "x", "z", "beatty_index", "value"],
    initial_states: initial,
    power_columns: ["exponent", "p_component", "q_component", "D_times_q_component"],
    power_basis: powers
  };
  return {
    schema: "kimberling.quadratic_beatty_compilation/v1",
    status: "CERTIFIED_QUADRATIC_BEATTY_INPUT", source_id, parameters,
    certificate: {
      positive_nonsquare_D: true, sqrt_floor: s.toString(),
      sqrt_lower_squared_gap: (D - s * s).toString(),
      sqrt_upper_squared_gap: ((s + 1n) * (s + 1n) - D).toString(),
      pell_norm: "1", positive_p_and_q: true, fundamental_unit_checked: false,
      slope_greater_than_one: true, seed_side: sign === 1 ? "floor" : "ceiling",
      seed_norm: seedNorm.toString(),
      conjugate_multiplier: "p-q*sqrt(D)=1/(p+q*sqrt(D)), strictly between zero and one",
      recurrence: {lag_one: (2n * p).toString(), lag_two: "-1", homogeneous: true},
      indices_and_values_strictly_increasing: true,
      mathematical_construction_for_every_integer_index_ge_zero: true
    },
    initial_states: copy(initial), snapshot,
    work: {integer_sqrt_iterations: root.iterations, pell_norm_checks: 1,
      power_squarings: QUADRATIC_BEATTY_LIMITS.power_rows - 1,
      initial_state_matrix_applications: 1, fundamental_unit_search_steps: 0,
      irrational_sqrt_or_floor_evaluations: 0},
    scope: "An explicit sufficient quadratic family. No full characterization, minimal recurrence order, or novelty claim."
  };
}

function openRetainedQuadraticBeattyIndex(request) {
  object(request, "request");
  const source_id = label(request.source_id), saved = object(request.snapshot, "snapshot");
  if (saved.schema !== "kimberling.quadratic_beatty_pell_index/v1")
    throw new TypeError("A quadratic Beatty Pell snapshot is required");
  label(saved.source_id);
  if (saved.max_index !== QUADRATIC_BEATTY_LIMITS.max_index)
    throw new RangeError("The snapshot index cap must match the public contract");
  const par = object(saved.parameters, "parameters"), small = QUADRATIC_BEATTY_LIMITS.input_digits;
  const D = dec(par.D, "D", small, 1n), u = dec(par.u, "u", small);
  const v = dec(par.v, "v", small, 1n), p = dec(par.p, "p", small, 1n);
  const q = dec(par.q, "q", small, 1n);
  if (par.sign !== 1 && par.sign !== -1) throw new RangeError("sign must be 1 or -1");
  const sign = par.sign, big = QUADRATIC_BEATTY_LIMITS.output_digits;
  const s = dec(saved.sqrt_floor, "sqrt_floor", small, 1n);
  const norm = dec(saved.seed_norm, "seed_norm", big);
  const coefficient = dec(saved.recurrence_coefficient, "recurrence_coefficient", big, 1n);
  if (!Array.isArray(saved.power_basis) || saved.power_basis.length !== QUADRATIC_BEATTY_LIMITS.power_rows)
    throw new RangeError("Exactly nine indexed power rows are required");
  const powers = saved.power_basis.map((row, j) => {
    if (!Array.isArray(row) || row.length !== 4 || row[0] !== 2 ** j)
      throw new TypeError("Invalid indexed power row");
    return {p: dec(row[1], "power p", big, 1n), q: dec(row[2], "power q", big, 1n),
      dq: dec(row[3], "power Dq", big, 1n)};
  });
  if (!Array.isArray(saved.initial_states) || saved.initial_states.length !== 2)
    throw new RangeError("Exactly two initial state rows are required");
  const initial = saved.initial_states.map((row, index) => {
    if (!Array.isArray(row) || row.length !== 5 || row[0] !== index)
      throw new TypeError("Invalid initial state row");
    return {index, x: dec(row[1], "initial x", big, 1n), z: dec(row[2], "initial z", big, 1n),
      n: dec(row[3], "initial Beatty index", big, 1n), a: dec(row[4], "initial value", big, 1n)};
  });
  const snapshot = {
    schema: saved.schema, source_id: saved.source_id, max_index: saved.max_index,
    parameters: {D: D.toString(), u: u.toString(), v: v.toString(), sign,
      p: p.toString(), q: q.toString()},
    sqrt_floor: s.toString(), seed_norm: norm.toString(), recurrence_coefficient: coefficient.toString(),
    initial_state_columns: ["index", "x", "z", "beatty_index", "value"],
    initial_states: initial.map(t => [t.index, t.x.toString(), t.z.toString(), t.n.toString(), t.a.toString()]),
    power_columns: ["exponent", "p_component", "q_component", "D_times_q_component"],
    power_basis: powers.map((t, j) => [2 ** j, t.p.toString(), t.q.toString(), t.dq.toString()])
  };
  const boundary = {
    source_id, snapshot_source_id: saved.source_id, source_authenticated: false,
    pell_norm_rechecked: false, nonsquare_and_slope_rechecked: false,
    seed_floor_rechecked: false, power_basis_recomputed: false,
    power_and_initial_state_relations_reverified: false,
    recurrence_coefficient_reverified: false,
    validation: "Bounded schema, indexed row coverage, canonical integers and positive numeric ranges only. Unit, seed, power, recurrence and monotonicity identities are trusted mathematical source premises."
  };
  const cache = new Map();
  const work = {term_requests: 0, cache_hits: 0, new_term_states: 0,
    quadratic_matrix_applications: 0, binary_search_comparisons: 0,
    pell_norm_checks: 0, power_squarings: 0, irrational_sqrt_or_floor_evaluations: 0};
  function record(index, state, from, exponents) {
    const x = state.x, z = state.z;
    const n = state.n === undefined ? mul(v, z) : state.n;
    const a = state.a === undefined ? add(mul(u, z), sign === 1 ? x : -x) : state.a;
    if (n <= 0n || a <= 0n) throw new RangeError("Retained construction produced a nonpositive term");
    const low = sign === 1 ? x : x - 1n;
    const high = sign === 1 ? x + 1n : x;
    const lowGap = sign === 1 ? -norm : add(2n * x - 1n, -norm);
    const highGap = sign === 1 ? add(2n * x + 1n, norm) : norm;
    if (low < 0n || lowGap <= 0n || highGap <= 0n)
      throw new RangeError("Retained premises do not yield positive strict floor-certificate gaps");
    return {
      status: "EXACT_CONSTRUCTED_TERM", source_id, index,
      x: x.toString(), z: z.toString(), beatty_index: n.toString(), value: a.toString(),
      floor_witness: {
        sqrt_interval_lower: low.toString(), sqrt_interval_upper: high.toString(),
        lower_squared_gap: lowGap.toString(), upper_squared_gap: highGap.toString(),
        preserved_norm: norm.toString(),
        identities: ["D*z^2-lower^2=lower_squared_gap", "upper^2-D*z^2=upper_squared_gap"],
        consequence: "value < beatty_index*(u+sign*sqrt(D))/v < value+1",
        derivation: "The supplied Pell power and seed premises preserve x^2-D*z^2. No new integer square root or direct square check was performed for this term."
      },
      construction: {from, power_exponents_used: exponents}
    };
  }
  for (const t of initial) cache.set(t.index, record(t.index, t, "retained_initial_state", []));
  function term(index) {
    whole(index, "index", 0, QUADRATIC_BEATTY_LIMITS.max_index); work.term_requests++;
    if (cache.has(index)) { work.cache_hits++; return copy(cache.get(index)); }
    let state = {x: initial[0].x, z: initial[0].z}, bits = index, j = 0;
    const exponents = [];
    while (bits > 0) {
      if (bits % 2 === 1) {
        state = applyPower(state, powers[j]); work.quadratic_matrix_applications++;
        exponents.push(2 ** j);
      }
      bits = Math.floor(bits / 2); j++;
    }
    const result = record(index, state, "retained_power_basis", exponents);
    cache.set(index, result); work.new_term_states++;
    return copy(result);
  }
  function lowerBoundValue(input) {
    object(input, "lowerBoundValue request");
    const value = dec(input.value, "value", big, 0n), trace = [];
    const last = term(QUADRATIC_BEATTY_LIMITS.max_index);
    work.binary_search_comparisons++;
    trace.push({index: last.index, value: last.value, at_least_target: BigInt(last.value) >= value});
    if (BigInt(last.value) < value) return {
      status: "ABOVE_INDEX_CAP", source_id, target: value.toString(),
      max_index: QUADRATIC_BEATTY_LIMITS.max_index, greatest_indexed_term: last, trace,
      interpretation: "The infinite mathematical sequence may reach this target later; the bounded index did not search later terms."
    };
    let lo = 0, hi = QUADRATIC_BEATTY_LIMITS.max_index;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2), t = term(mid), atLeast = BigInt(t.value) >= value;
      work.binary_search_comparisons++;
      trace.push({index: mid, value: t.value, at_least_target: atLeast});
      if (atLeast) hi = mid; else lo = mid + 1;
    }
    const found = term(lo), previous = lo > 0 ? term(lo - 1) : null;
    return {status: "FOUND_IN_INDEX_RANGE", source_id, target: value.toString(),
      index: lo, term: found, previous, trace,
      interpretation: "First constructed subsequence value at least the target; this does not search every value in the full Beatty sequence."};
  }
  return Object.freeze({
    describe() { return {status: "OPEN_RETAINED_QUADRATIC_BEATTY_INDEX", source_id,
      parameters: copy(snapshot.parameters), recurrence_coefficient: snapshot.recurrence_coefficient,
      max_index: QUADRATIC_BEATTY_LIMITS.max_index, indexed_terms: QUADRATIC_BEATTY_LIMITS.max_index + 1,
      mathematical_sequence_infinite: true, boundary: copy(boundary)}; },
    term,
    pageTerms(input) {
      object(input, "pageTerms request");
      const at = whole(input.start_index === undefined ? 0 : input.start_index, "start_index",
        0, QUADRATIC_BEATTY_LIMITS.max_index + 1);
      const limit = whole(input.limit === undefined ? 8 : input.limit, "limit", 1, QUADRATIC_BEATTY_LIMITS.page_size);
      const end = Math.min(at + limit, QUADRATIC_BEATTY_LIMITS.max_index + 1), rows = [];
      for (let index = at; index < end; index++) rows.push(term(index));
      return {status: "INDEX_PAGE", source_id, start_index: at, records: rows,
        next_index: end <= QUADRATIC_BEATTY_LIMITS.max_index ? end : null,
        max_index: QUADRATIC_BEATTY_LIMITS.max_index, mathematical_sequence_infinite: true};
    },
    lowerBoundValue,
    rankValue(input) {
      object(input, "rankValue request");
      const found = lowerBoundValue({value: input.value});
      if (found.status === "ABOVE_INDEX_CAP") return found;
      const matches = found.term.value === found.target;
      return {status: matches ? "MEMBER_OF_CONSTRUCTED_SUBSEQUENCE" : "NOT_IN_CONSTRUCTED_SUBSEQUENCE",
        source_id, value: found.target, rank: matches ? found.index : null, lower_bound: found,
        scope: "Membership and zero-based rank in this constructed subsequence, not in the entire Beatty sequence."};
    },
    queriedTerms() { return Array.from(cache.values()).sort((a, b) => a.index - b.index).map(copy); },
    work() { return copy(work); },
    snapshot() { return copy(snapshot); }
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {compileQuadraticBeattyIndex, openRetainedQuadraticBeattyIndex, QUADRATIC_BEATTY_LIMITS};
}
