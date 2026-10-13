"use strict";

/**
 * Smooth pair-sum graphs and retained exact maximum-clique searches.
 * Source least factors and primality are accepted premises. Opening a saved
 * index validates bounded structure and references, not its mathematical proof.
 * No filesystem, network, clock, random source, native dependency, or test suite.
 */
const SCHEMA = "smooth-sum-clique-index/v1";
const LIMITS = Object.freeze({
  vertices: 128, basis_limit: 65536, allowed_primes: 32, graph_views: 8,
  nodes_per_call: 10000, nodes_per_search: 50000, sessions: 64,
  events_per_session: 256, source_id_chars: 512, copy_items: 6000000,
  copy_text_chars: 64000000, copy_depth: 32, page_size: 256
});
const WORK_KEYS = Object.freeze([
  "distinct_sums_factored", "least_factor_reads", "exact_factor_divisions",
  "pair_rows_built", "graph_views_built", "pair_support_checks",
  "adjacency_edges_added", "searches_started", "search_nodes_processed",
  "color_classes_built", "color_vertices_assigned", "search_branches",
  "search_prunes", "search_leaves", "incumbent_improvements",
  "maximum_results_built", "maximum_pair_rows_selected",
  "maximum_factor_rows_selected"
]);
function fail(code, message) {
  const error = new Error(message); error.code = code; throw error;
}
function requireThat(value, code, message) {
  if (!value) fail(code, message);
}
function object(value, name) {
  requireThat(value !== null && typeof value === "object" &&
    !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype ||
      Object.getPrototypeOf(value) === null), "INVALID_OBJECT", name + " must be a plain object");
  return value;
}
function integer(value, min, max, name) {
  requireThat(Number.isSafeInteger(value) && value >= min && value <= max,
    "INVALID_INTEGER", name + " is outside its exact integer range");
  return value;
}
function identity(value, name) {
  requireThat(typeof value === "string" && value.length > 0 &&
    value.length <= LIMITS.source_id_chars, "INVALID_SOURCE_ID", name + " must be a bounded nonempty string");
  return value;
}
function array(value, max, name) {
  requireThat(Array.isArray(value) && value.length <= max,
    "INVALID_ARRAY", name + " must be a bounded array");
  return value;
}
function exactKeys(value, keys, name) {
  object(value, name);
  const actual = Object.keys(value).sort();
  const expected = keys.slice().sort();
  requireThat(actual.length === expected.length &&
    actual.every((key, i) => key === expected[i]), "INVALID_FIELDS", name + " has unexpected or missing fields");
}
function copy(value) {
  let items = 0, chars = 0;
  function visit(x, depth) {
    requireThat(++items <= LIMITS.copy_items && depth <= LIMITS.copy_depth,
      "COPY_LIMIT", "The retained object exceeds the bounded copy limit");
    if (x === null || typeof x === "boolean") return x;
    if (typeof x === "number") {
      requireThat(Number.isSafeInteger(x), "INVALID_NUMBER", "Only safe integer JSON numbers are supported");
      return x;
    }
    if (typeof x === "string") {
      chars += x.length;
      requireThat(chars <= LIMITS.copy_text_chars, "COPY_LIMIT", "The retained text exceeds the bounded copy limit");
      return x;
    }
    if (Array.isArray(x)) return x.map(y => visit(y, depth + 1));
    object(x, "retained value");
    const out = {};
    for (const key of Object.keys(x)) {
      requireThat(key !== "__proto__" && key !== "constructor" && key !== "prototype",
        "INVALID_FIELD", "Reserved object field");
      out[key] = visit(x[key], depth + 1);
    }
    return out;
  }
  return visit(value, 0);
}
function zeroWork() { return Object.fromEntries(WORK_KEYS.map(key => [key, 0])); }
function validateWork(work, name) {
  exactKeys(work, WORK_KEYS, name);
  for (const key of WORK_KEYS) integer(work[key], 0, Number.MAX_SAFE_INTEGER, name + "." + key);
}
function hex(mask) { return mask.toString(16); }
function readHex(value, universe, name) {
  requireThat(typeof value === "string" && /^(?:0|[1-9a-f][0-9a-f]*)$/.test(value) &&
    value.length <= 16384, "INVALID_MASK", name + " must be canonical nonnegative hexadecimal");
  const mask = BigInt("0x" + value);
  requireThat((mask & ~universe) === 0n, "INVALID_MASK", name + " has out-of-universe bits");
  return mask;
}
function sortedIntegers(values, min, max, cap, name) {
  array(values, cap, name);
  let prior = min - 1;
  for (const value of values) {
    integer(value, min, max, name + " entry");
    requireThat(value > prior, "INVALID_ORDER", name + " must be strictly increasing");
    prior = value;
  }
  return values;
}
function requireOptions(options, keys, name) {
  object(options, name);
  requireThat(Object.keys(options).every(key => keys.includes(key)),
    "INVALID_OPTIONS", name + " contains an unsupported option");
}
function compileSmoothSumIndex(options) {
  requireOptions(options, ["source_id", "basis_id", "candidates", "basis"], "compile options");
  const sourceId = identity(options.source_id, "source_id");
  const basisId = identity(options.basis_id, "basis_id");
  const candidates = copy(options.candidates);
  sortedIntegers(candidates, 0, LIMITS.basis_limit, LIMITS.vertices, "candidates");
  requireThat(candidates.length >= 1, "EMPTY_DOMAIN", "At least one candidate is required");
  const basis = copy(options.basis);
  exactKeys(basis, ["limit", "primes", "least_factor_by_integer"], "basis");
  const bound = integer(basis.limit, 2, LIMITS.basis_limit, "basis.limit");
  sortedIntegers(basis.primes, 2, bound, bound, "basis.primes");
  const lpf = array(basis.least_factor_by_integer, bound + 1, "least_factor_by_integer");
  requireThat(lpf.length === bound + 1 && lpf[0] === 0 && lpf[1] === 1,
    "INVALID_BASIS", "Least-factor entries must cover 0 through the declared limit, with entries 0 and 1");
  const primeIndex = new Map(basis.primes.map((p, i) => [p, i]));
  for (let value = 2; value <= bound; value++) {
    integer(lpf[value], 2, value, "least-factor entry");
    requireThat(primeIndex.has(lpf[value]), "INVALID_BASIS", "A least-factor entry is absent from the accepted prime list");
    requireThat((lpf[value] === value) === primeIndex.has(value),
      "INVALID_BASIS", "Prime-list membership and diagonal least-factor entries disagree");
  }
  if (candidates.length > 1)
    requireThat(candidates[candidates.length - 1] + candidates[candidates.length - 2] <= bound,
      "BASIS_COVERAGE", "Every distinct-endpoint sum must lie in the accepted least-factor table");
  const sumSet = new Set();
  for (let i = 0; i < candidates.length; i++)
    for (let j = i + 1; j < candidates.length; j++) sumSet.add(candidates[i] + candidates[j]);
  const sums = Array.from(sumSet).sort((a, b) => a - b);
  const work = zeroWork(), rows = [], sumIndex = new Map();
  for (const sum of sums) {
    requireThat(sum > 0 && sum <= bound, "BASIS_COVERAGE", "Distinct natural endpoints must have a covered positive sum");
    const chain = [], powers = new Map();
    let value = sum, support = 0n;
    while (value > 1) {
      const p = lpf[value];
      work.least_factor_reads++;
      requireThat(Number.isSafeInteger(p) && p >= 2 && p <= value && primeIndex.has(p) &&
        value % p === 0, "INVALID_FACTORIZATION", "The accepted entry does not give an exact covered factor division");
      const quotient = value / p;
      requireThat(Number.isSafeInteger(quotient) && quotient >= 1 && quotient < value,
        "INVALID_FACTORIZATION", "Factorization failed to descend by exact division");
      chain.push({value, prime: p, quotient});
      powers.set(p, (powers.get(p) || 0) + 1);
      support |= 1n << BigInt(primeIndex.get(p));
      value = quotient; work.exact_factor_divisions++;
    }
    const factors = Array.from(powers, ([prime, exponent]) =>
      ({prime, exponent, prime_index: primeIndex.get(prime)})).sort((a, b) => a.prime - b.prime);
    const row = {id: rows.length, sum, divisions: chain, factors, support_mask_hex: hex(support)};
    sumIndex.set(sum, row.id); rows.push(row); work.distinct_sums_factored++;
  }
  const pairs = [];
  for (let i = 0; i < candidates.length; i++)
    for (let j = i + 1; j < candidates.length; j++)
      pairs.push([i, j, sumIndex.get(candidates[i] + candidates[j])]);
  work.pair_rows_built = pairs.length;
  const state = {
    schema: SCHEMA, source_id: sourceId,
    basis: {source_id: basisId, limit: bound, primes: basis.primes,
      source_least_factor_entries: lpf.length, premise: "accepted-prime-and-least-factor-source"},
    candidates, sum_rows: rows, pair_rows: pairs, graph_views: [], searches: [],
    work, activity: []
  };
  return makeIndex(state, sourceId, "compile", copy(work), null);
}

function validateSavedState(state) {
  exactKeys(state, ["schema", "source_id", "basis", "candidates", "sum_rows", "pair_rows",
    "graph_views", "searches", "work", "activity"], "snapshot");
  requireThat(state.schema === SCHEMA, "INVALID_SCHEMA", "Unsupported saved-index schema");
  identity(state.source_id, "snapshot.source_id");
  exactKeys(state.basis, ["source_id", "limit", "primes", "source_least_factor_entries", "premise"], "saved basis");
  identity(state.basis.source_id, "saved basis source");
  const bound = integer(state.basis.limit, 2, LIMITS.basis_limit, "saved basis limit");
  sortedIntegers(state.basis.primes, 2, bound, bound, "saved primes");
  requireThat(state.basis.source_least_factor_entries === bound + 1 &&
    state.basis.premise === "accepted-prime-and-least-factor-source", "INVALID_BASIS", "Saved basis custody fields disagree");
  sortedIntegers(state.candidates, 0, LIMITS.basis_limit, LIMITS.vertices, "saved candidates");
  const n = state.candidates.length;
  requireThat(n > 0, "EMPTY_DOMAIN", "Saved domain must be nonempty");
  const universe = (1n << BigInt(n)) - 1n;
  const primeUniverse = (1n << BigInt(state.basis.primes.length)) - 1n;
  const indices = (values, name) => {
    array(values, n, name); const seen = new Set();
    for (const value of values) {
      integer(value, 0, n - 1, name + " index");
      requireThat(!seen.has(value), "DUPLICATE_INDEX", name + " repeats an index"); seen.add(value);
    }
  };
  array(state.sum_rows, n * (n - 1) / 2, "sum rows");
  let lastSum = 0;
  state.sum_rows.forEach((row, id) => {
    exactKeys(row, ["id", "sum", "divisions", "factors", "support_mask_hex"], "sum row");
    requireThat(row.id === id, "INVALID_REFERENCE", "Sum rows must use contiguous ids");
    integer(row.sum, lastSum + 1, bound, "sum value"); lastSum = row.sum;
    array(row.divisions, 16, "factor divisions");
    for (const step of row.divisions) {
      exactKeys(step, ["value", "prime", "quotient"], "factor division");
      integer(step.value, 2, bound, "division value");
      integer(step.prime, 2, bound, "division prime");
      integer(step.quotient, 1, bound, "division quotient");
    }
    array(row.factors, 16, "factor powers");
    let priorPrime = 1;
    for (const factor of row.factors) {
      exactKeys(factor, ["prime", "exponent", "prime_index"], "factor power");
      integer(factor.prime, priorPrime + 1, bound, "factor prime"); priorPrime = factor.prime;
      integer(factor.exponent, 1, 16, "factor exponent");
      integer(factor.prime_index, 0, state.basis.primes.length - 1, "factor prime index");
      requireThat(state.basis.primes[factor.prime_index] === factor.prime,
        "INVALID_REFERENCE", "Factor prime index does not address its retained prime");
    }
    readHex(row.support_mask_hex, primeUniverse, "prime support mask");
  });
  array(state.pair_rows, n * (n - 1) / 2, "pair rows");
  requireThat(state.pair_rows.length === n * (n - 1) / 2, "INVALID_PAIR_DOMAIN", "Pair table must cover the declared unordered-pair count");
  const pairKeys = new Set();
  for (const row of state.pair_rows) {
    requireThat(Array.isArray(row) && row.length === 3, "INVALID_PAIR_ROW", "Each pair row must have three entries");
    integer(row[0], 0, n - 1, "left index"); integer(row[1], row[0] + 1, n - 1, "right index");
    integer(row[2], 0, state.sum_rows.length - 1, "sum row reference");
    const key = row[0] + "," + row[1];
    requireThat(!pairKeys.has(key), "DUPLICATE_PAIR", "Pair addresses must be unique"); pairKeys.add(key);
  }
  array(state.graph_views, LIMITS.graph_views, "graph views");
  const graphKeys = new Set();
  for (const graph of state.graph_views) {
    exactKeys(graph, ["key", "allowed_primes", "allowed_mask_hex", "adjacency_masks_hex", "edge_count"], "graph view");
    sortedIntegers(graph.allowed_primes, 2, bound, LIMITS.allowed_primes, "allowed primes");
    requireThat(graph.allowed_primes.every(p => state.basis.primes.includes(p)),
      "INVALID_REFERENCE", "An allowed prime is absent from the accepted source");
    requireThat(graph.key === graph.allowed_primes.join(",") && !graphKeys.has(graph.key),
      "INVALID_GRAPH_KEY", "Graph keys must identify unique allowed-prime sets");
    graphKeys.add(graph.key);
    readHex(graph.allowed_mask_hex, primeUniverse, "allowed-prime mask");
    array(graph.adjacency_masks_hex, n, "adjacency masks");
    requireThat(graph.adjacency_masks_hex.length === n, "INVALID_GRAPH", "One adjacency mask is required for every candidate");
    graph.adjacency_masks_hex.forEach(value => readHex(value, universe, "adjacency mask"));
    integer(graph.edge_count, 0, state.pair_rows.length, "edge count");
  }
  array(state.searches, LIMITS.graph_views, "searches");
  const searchKeys = new Set();
  for (const search of state.searches) {
    exactKeys(search, ["key", "status", "stop_reason", "next_node_id", "processed_nodes", "pending",
      "incumbent_indices", "incumbent_history", "maximum"], "search");
    requireThat(graphKeys.has(search.key) && !searchKeys.has(search.key),
      "INVALID_REFERENCE", "Search must reference one unique retained graph");
    searchKeys.add(search.key);
    requireThat(search.status === "complete" || search.status === "incomplete", "INVALID_STATUS", "Unknown search status");
    requireThat(["not_started", "node_budget", "node_capacity", "exhausted"].includes(search.stop_reason),
      "INVALID_STATUS", "Unknown search stop reason");
    integer(search.next_node_id, 1, LIMITS.nodes_per_search, "next node id");
    array(search.processed_nodes, LIMITS.nodes_per_search, "processed nodes");
    array(search.pending, LIMITS.nodes_per_search, "pending nodes");
    indices(search.incumbent_indices, "incumbent");
    array(search.incumbent_history, n + 1, "incumbent history");
    requireThat(search.incumbent_history.length > 0, "INVALID_HISTORY", "Initial empty incumbent must be retained");
    search.incumbent_history.forEach((entry, index) => {
      exactKeys(entry, ["node_id", "clique_indices"], "incumbent history entry");
      if (entry.node_id !== null) integer(entry.node_id, 0, search.next_node_id - 1, "incumbent node id");
      else requireThat(index === 0 && entry.clique_indices.length === 0,
        "INVALID_HISTORY", "Only the initial empty incumbent has no node");
      indices(entry.clique_indices, "historical incumbent");
    });
    const states = new Map(), parents = [];
    function nodeAddress(node, pending) {
      integer(node.id, 0, search.next_node_id - 1, "node id");
      requireThat(!states.has(node.id), "DUPLICATE_NODE", "Each allocated node must occur exactly once");
      if (node.id === 0) requireThat(node.parent_id === null && node.branch === "root", "INVALID_ROOT", "Root address must be explicit");
      else {
        integer(node.parent_id, 0, search.next_node_id - 1, "parent node id");
        requireThat(node.branch === "include" || node.branch === "exclude", "INVALID_BRANCH", "Unknown child branch");
      }
      indices(node.clique_indices, "node clique");
      readHex(node.candidate_mask_hex, universe, "node candidates");
      states.set(node.id, {node, pending});
    }
    for (const node of search.processed_nodes) {
      exactKeys(node, ["id", "parent_id", "branch", "clique_indices", "candidate_mask_hex",
        "incumbent_size_before", "incumbent_size_after", "incumbent_history_index", "color_classes",
        "bound", "decision", "selected_vertex_index", "children"], "processed node");
      nodeAddress(node, false);
      integer(node.incumbent_size_before, 0, n, "prior incumbent size");
      integer(node.incumbent_size_after, node.incumbent_size_before, n, "resulting incumbent size");
      integer(node.incumbent_history_index, 0, search.incumbent_history.length - 1, "incumbent history reference");
      array(node.color_classes, n, "color classes");
      node.color_classes.forEach(values => {
        indices(values, "color class");
        requireThat(values.length > 0, "INVALID_COLOR_CLASS", "A retained color class must be nonempty");
      });
      integer(node.bound, 0, n, "node upper bound");
      requireThat(["branch", "leaf", "prune"].includes(node.decision), "INVALID_DECISION", "Unknown node decision");
      if (node.decision === "branch") {
        integer(node.selected_vertex_index, 0, n - 1, "selected vertex");
        exactKeys(node.children, ["include_id", "exclude_id"], "children");
        integer(node.children.include_id, 0, search.next_node_id - 1, "include child");
        integer(node.children.exclude_id, 0, search.next_node_id - 1, "exclude child");
        requireThat(node.children.include_id !== node.children.exclude_id && node.children.include_id > node.id && node.children.exclude_id > node.id,
          "INVALID_CHILDREN", "Branches must have distinct forward-allocated addresses");
        parents.push(node);
      } else requireThat(node.selected_vertex_index === null && node.children === null,
        "INVALID_TERMINAL", "A terminal record must not allocate children");
    }
    for (const node of search.pending) {
      exactKeys(node, ["id", "parent_id", "branch", "clique_indices", "candidate_mask_hex"], "pending node");
      nodeAddress(node, true);
    }
    requireThat(states.size === search.next_node_id && states.has(0),
      "INVALID_COVERAGE", "Every allocated node must be processed or pending");
    for (const parent of parents) {
      for (const branch of ["include", "exclude"]) {
        const child = states.get(parent.children[branch + "_id"]);
        requireThat(child && child.node.parent_id === parent.id && child.node.branch === branch,
          "INVALID_REFERENCE", "A branch must address the matching retained child");
      }
    }
    for (const [id, entry] of states) if (id !== 0) {
      const parent = states.get(entry.node.parent_id);
      requireThat(parent && !parent.pending && parent.node.decision === "branch" &&
        parent.node.children[entry.node.branch + "_id"] === id,
        "INVALID_REFERENCE", "Every non-root state must belong to its processed branch parent");
    }
    for (const entry of search.incumbent_history) if (entry.node_id !== null)
      requireThat(states.has(entry.node_id) && !states.get(entry.node_id).pending,
        "INVALID_REFERENCE", "An incumbent witness must reference a processed node");
    if (search.status === "complete") {
      requireThat(search.pending.length === 0 && search.stop_reason === "exhausted" && search.maximum !== null,
        "INVALID_COMPLETION", "A completed search requires no pending states and a saved maximum");
      const maximum = search.maximum;
      exactKeys(maximum, ["status", "graph_key", "size", "candidate_indices", "values", "pair_witnesses",
        "actual_prime_union", "actual_prime_count", "finite_universe_size", "search_node_count",
        "incumbent_history_index"], "maximum result");
      requireThat(maximum.status === "maximum_in_declared_graph" && maximum.graph_key === search.key &&
        maximum.finite_universe_size === n && maximum.search_node_count === search.processed_nodes.length,
        "INVALID_RESULT", "Saved maximum custody fields disagree");
      indices(maximum.candidate_indices, "maximum indices");
      array(maximum.values, n, "maximum values");
      integer(maximum.size, 0, n, "maximum size");
      requireThat(maximum.size === maximum.candidate_indices.length && maximum.size === maximum.values.length,
        "INVALID_RESULT", "Saved maximum size fields disagree");
      maximum.values.forEach((value, index) => requireThat(value === state.candidates[maximum.candidate_indices[index]],
        "INVALID_REFERENCE", "Maximum value does not address its retained candidate"));
      sortedIntegers(maximum.actual_prime_union, 2, bound, state.basis.primes.length, "actual prime union");
      requireThat(maximum.actual_prime_count === maximum.actual_prime_union.length,
        "INVALID_RESULT", "Actual-prime count disagrees with its retained list");
      integer(maximum.incumbent_history_index, 0, search.incumbent_history.length - 1, "maximum incumbent reference");
      array(maximum.pair_witnesses, n * (n - 1) / 2, "maximum pair witnesses");
      for (const witness of maximum.pair_witnesses) {
        exactKeys(witness, ["pair_row_id", "sum_row_id"], "pair witness");
        integer(witness.pair_row_id, 0, state.pair_rows.length - 1, "pair row reference");
        integer(witness.sum_row_id, 0, state.sum_rows.length - 1, "sum row reference");
        requireThat(state.pair_rows[witness.pair_row_id][2] === witness.sum_row_id,
          "INVALID_REFERENCE", "Pair and factor witness references disagree");
      }
    } else requireThat(search.pending.length > 0 && search.maximum === null && search.stop_reason !== "exhausted",
      "INVALID_COMPLETION", "Incomplete search must retain pending states and no maximum claim");
  }
  validateWork(state.work, "cumulative work");
  array(state.activity, LIMITS.sessions - 1, "prior activity");
  for (const session of state.activity) {
    exactKeys(session, ["id", "source_id", "opened_by", "loading", "new_work", "events"], "session");
    integer(session.id, 0, LIMITS.sessions - 1, "session id"); identity(session.source_id, "session source");
    requireThat(session.opened_by === "compile" || session.opened_by === "saved_open", "INVALID_SESSION", "Unknown session origin");
    if (session.loading !== null) {
      exactKeys(session.loading, ["sum_rows_indexed", "pair_rows_indexed", "graph_views_loaded",
        "search_nodes_loaded", "pending_nodes_loaded", "mathematical_proof_replayed"], "loading");
      requireThat(session.loading.mathematical_proof_replayed === false, "INVALID_SESSION", "Saved loading must not claim proof replay");
      for (const key of Object.keys(session.loading)) if (key !== "mathematical_proof_replayed")
        integer(session.loading[key], 0, LIMITS.copy_items, "loading count");
    }
    validateWork(session.new_work, "session work");
    array(session.events, LIMITS.events_per_session, "session events");
    for (const event of session.events) object(event, "event");
  }
}
function openSmoothSumIndex(snapshot, options) {
  requireOptions(options, ["source_id"], "open options");
  const sourceId = identity(options.source_id, "reader source_id");
  const state = copy(snapshot);
  validateSavedState(state);
  const loading = {
    sum_rows_indexed: state.sum_rows.length, pair_rows_indexed: state.pair_rows.length,
    graph_views_loaded: state.graph_views.length,
    search_nodes_loaded: state.searches.reduce((sum, search) => sum + search.processed_nodes.length, 0),
    pending_nodes_loaded: state.searches.reduce((sum, search) => sum + search.pending.length, 0),
    mathematical_proof_replayed: false
  };
  return makeIndex(state, sourceId, "saved_open", zeroWork(), loading);
}

function makeIndex(state, sourceId, openedBy, initialWork, loading) {
  requireThat(state.activity.length < LIMITS.sessions, "SESSION_LIMIT", "The saved index has reached its session limit");
  const session = {id: state.activity.length, source_id: sourceId, opened_by: openedBy,
    loading, new_work: initialWork, events: []};
  state.activity.push(session);
  const n = state.candidates.length, universe = (1n << BigInt(n)) - 1n;
  const bits = Array.from({length: n}, (_, i) => 1n << BigInt(i));
  const bitIndex = new Map(bits.map((bit, index) => [bit, index]));
  const valueIndex = new Map(state.candidates.map((value, index) => [value, index]));
  const primeIndex = new Map(state.basis.primes.map((prime, index) => [prime, index]));
  const pairIndex = new Map(state.pair_rows.map((row, id) => [row[0] * n + row[1], id]));
  const graphIndex = new Map(state.graph_views.map(graph => [graph.key, graph]));
  const searchIndex = new Map(state.searches.map(search => [search.key, search]));
  const runtimeGraphs = new Map();
  function increment(key, count = 1) {
    requireThat(WORK_KEYS.includes(key) && Number.isSafeInteger(count) && count >= 0,
      "INTERNAL_COUNTER", "Unknown or invalid work counter");
    requireThat(Number.isSafeInteger(state.work[key] + count) &&
      Number.isSafeInteger(session.new_work[key] + count), "COUNTER_LIMIT", "Work counter overflow");
    state.work[key] += count; session.new_work[key] += count;
  }
  function beginEvent() {
    requireThat(session.events.length < LIMITS.events_per_session,
      "EVENT_LIMIT", "Open a saved snapshot in a fresh session before making more queries");
  }
  function event(value) { session.events.push(value); }
  function primeRequest(values) {
    const allowed = copy(values);
    array(allowed, LIMITS.allowed_primes, "allowed_primes");
    allowed.sort((a, b) => a - b);
    sortedIntegers(allowed, 2, state.basis.limit, LIMITS.allowed_primes, "allowed_primes");
    requireThat(allowed.every(p => primeIndex.has(p)), "UNKNOWN_PRIME", "Allowed primes must belong to the accepted source");
    return {allowed, key: allowed.join(",")};
  }
  function runtimeGraph(graph) {
    if (!runtimeGraphs.has(graph.key))
      runtimeGraphs.set(graph.key, graph.adjacency_masks_hex.map(value => BigInt("0x" + value)));
    return runtimeGraphs.get(graph.key);
  }
  function graphFor(request) {
    if (graphIndex.has(request.key)) return graphIndex.get(request.key);
    requireThat(state.graph_views.length < LIMITS.graph_views, "GRAPH_LIMIT", "The retained graph-view limit has been reached");
    let allowedMask = 0n;
    for (const prime of request.allowed) allowedMask |= 1n << BigInt(primeIndex.get(prime));
    const adjacency = Array.from({length: n}, () => 0n);
    const supports = state.sum_rows.map(row => BigInt("0x" + row.support_mask_hex));
    let edges = 0;
    for (const pair of state.pair_rows) {
      increment("pair_support_checks");
      if ((supports[pair[2]] & ~allowedMask) === 0n) {
        adjacency[pair[0]] |= bits[pair[1]];
        adjacency[pair[1]] |= bits[pair[0]];
        edges++; increment("adjacency_edges_added");
      }
    }
    const graph = {key: request.key, allowed_primes: request.allowed, allowed_mask_hex: hex(allowedMask),
      adjacency_masks_hex: adjacency.map(hex), edge_count: edges};
    state.graph_views.push(graph); graphIndex.set(graph.key, graph); runtimeGraphs.set(graph.key, adjacency);
    increment("graph_views_built"); return graph;
  }
  function colorCandidates(candidateMask, adjacency) {
    let remaining = candidateMask;
    const classes = [];
    while (remaining !== 0n) {
      let available = remaining;
      const colorClass = [];
      while (available !== 0n) {
        const bit = available & -available, vertex = bitIndex.get(bit);
        colorClass.push(vertex); remaining &= ~bit; available &= ~bit;
        available &= ~adjacency[vertex];
        increment("color_vertices_assigned");
      }
      classes.push(colorClass); increment("color_classes_built");
    }
    return classes;
  }
  function saveMaximum(search) {
    const selected = search.incumbent_indices.slice().sort((a, b) => a - b);
    const witnesses = [], factorRows = new Set(), primes = new Set();
    for (let a = 0; a < selected.length; a++) for (let b = a + 1; b < selected.length; b++) {
      const pairId = pairIndex.get(selected[a] * n + selected[b]);
      const sumId = state.pair_rows[pairId][2];
      witnesses.push({pair_row_id: pairId, sum_row_id: sumId}); factorRows.add(sumId);
      increment("maximum_pair_rows_selected");
    }
    for (const id of factorRows) {
      for (const factor of state.sum_rows[id].factors) primes.add(factor.prime);
      increment("maximum_factor_rows_selected");
    }
    const actualPrimes = Array.from(primes).sort((a, b) => a - b);
    search.maximum = {
      status: "maximum_in_declared_graph", graph_key: search.key, size: selected.length,
      candidate_indices: selected, values: selected.map(index => state.candidates[index]),
      pair_witnesses: witnesses, actual_prime_union: actualPrimes,
      actual_prime_count: actualPrimes.length, finite_universe_size: n,
      search_node_count: search.processed_nodes.length,
      incumbent_history_index: search.incumbent_history.length - 1
    };
    increment("maximum_results_built");
  }
  function searchMaximumClique(options) {
    requireOptions(options, ["allowed_primes", "node_budget"], "search options");
    const request = primeRequest(options.allowed_primes);
    const budget = options.node_budget === undefined ? 256 :
      integer(options.node_budget, 1, LIMITS.nodes_per_call, "node_budget");
    beginEvent();
    const before = copy(session.new_work), graph = graphFor(request);
    let search = searchIndex.get(request.key), started = false;
    if (!search) {
      search = {key: request.key, status: "incomplete", stop_reason: "not_started", next_node_id: 1,
        processed_nodes: [], pending: [{id: 0, parent_id: null, branch: "root",
          clique_indices: [], candidate_mask_hex: hex(universe)}],
        incumbent_indices: [], incumbent_history: [{node_id: null, clique_indices: []}], maximum: null};
      state.searches.push(search); searchIndex.set(request.key, search); started = true;
      increment("searches_started");
    }
    const wasComplete = search.status === "complete", adjacency = runtimeGraph(graph);
    let processed = 0;
    while (search.pending.length > 0 && processed < budget) {
      // Reserve room for both children before touching the next state. At the
      // hard capacity this conservatively preserves it, without partial work.
      if (search.next_node_id + 2 > LIMITS.nodes_per_search) {
        search.stop_reason = "node_capacity"; break;
      }
      const current = search.pending.pop(), candidateMask = BigInt("0x" + current.candidate_mask_hex);
      const priorSize = search.incumbent_indices.length;
      if (current.clique_indices.length > priorSize) {
        search.incumbent_indices = current.clique_indices.slice().sort((a, b) => a - b);
        search.incumbent_history.push({node_id: current.id, clique_indices: search.incumbent_indices.slice()});
        increment("incumbent_improvements");
      }
      let classes = [], bound = current.clique_indices.length;
      let decision, vertex = null, children = null;
      if (candidateMask === 0n) {
        decision = "leaf"; increment("search_leaves");
      } else {
        classes = colorCandidates(candidateMask, adjacency);
        bound += classes.length;
        if (bound <= search.incumbent_indices.length) {
          decision = "prune"; increment("search_prunes");
        } else {
          decision = "branch";
          const finalClass = classes[classes.length - 1];
          vertex = finalClass[finalClass.length - 1];
          const includeId = search.next_node_id++, excludeId = search.next_node_id++;
          children = {include_id: includeId, exclude_id: excludeId};
          const include = {id: includeId, parent_id: current.id, branch: "include",
            clique_indices: current.clique_indices.concat(vertex),
            candidate_mask_hex: hex(candidateMask & adjacency[vertex])};
          const exclude = {id: excludeId, parent_id: current.id, branch: "exclude",
            clique_indices: current.clique_indices.slice(),
            candidate_mask_hex: hex(candidateMask & ~bits[vertex])};
          search.pending.push(exclude, include);
          increment("search_branches");
        }
      }
      search.processed_nodes.push({
        ...current, incumbent_size_before: priorSize, incumbent_size_after: search.incumbent_indices.length,
        incumbent_history_index: search.incumbent_history.length - 1, color_classes: classes,
        bound, decision, selected_vertex_index: vertex, children
      });
      processed++; increment("search_nodes_processed");
    }
    if (search.pending.length === 0) {
      search.status = "complete"; search.stop_reason = "exhausted";
      if (search.maximum === null) saveMaximum(search);
    } else {
      search.status = "incomplete";
      if (search.stop_reason !== "node_capacity") search.stop_reason = "node_budget";
    }
    const newWork = Object.fromEntries(WORK_KEYS.map(key => [key, session.new_work[key] - before[key]]));
    event({operation: "searchMaximumClique", graph_key: graph.key, node_budget: budget,
      search_started: started, completed_result_reused: wasComplete, processed_this_call: processed,
      processed_node_count: search.processed_nodes.length, pending_count: search.pending.length,
      status: search.status, stop_reason: search.stop_reason});
    return copy({
      status: search.status, stop_reason: search.stop_reason, graph_key: graph.key,
      allowed_primes: graph.allowed_primes, edge_count: graph.edge_count,
      processed_this_call: processed, processed_node_count: search.processed_nodes.length,
      pending_count: search.pending.length,
      incumbent: {size: search.incumbent_indices.length, candidate_indices: search.incumbent_indices,
        values: search.incumbent_indices.map(index => state.candidates[index])},
      maximum: search.maximum, new_work: newWork
    });
  }
  function getMaximum(options) {
    requireOptions(options, ["allowed_primes"], "maximum options");
    const request = primeRequest(options.allowed_primes); beginEvent();
    const search = searchIndex.get(request.key);
    const result = search && search.status === "complete" ?
      {status: "complete", maximum: search.maximum} :
      {status: search ? "incomplete" : "not_searched", graph_key: request.key,
        processed_node_count: search ? search.processed_nodes.length : 0,
        pending_count: search ? search.pending.length : 0};
    event({operation: "getMaximum", graph_key: request.key, status: result.status,
      retained_result_only: true});
    return copy(result);
  }
  function getPair(options) {
    requireOptions(options, ["left", "right"], "pair options");
    integer(options.left, 0, LIMITS.basis_limit, "left");
    integer(options.right, 0, LIMITS.basis_limit, "right");
    requireThat(valueIndex.has(options.left) && valueIndex.has(options.right),
      "UNKNOWN_CANDIDATE", "Both endpoints must belong to the retained candidate universe");
    requireThat(options.left !== options.right, "DIAGONAL_PAIR", "Self-sums are outside the off-diagonal problem");
    beginEvent();
    const a = valueIndex.get(options.left), b = valueIndex.get(options.right);
    const left = Math.min(a, b), right = Math.max(a, b), pairId = pairIndex.get(left * n + right);
    const row = state.pair_rows[pairId], factorRow = state.sum_rows[row[2]];
    event({operation: "getPair", left: options.left, right: options.right,
      pair_row_id: pairId, sum_row_id: row[2], retained_result_only: true});
    return copy({status: "retained_pair", canonical_values: [state.candidates[left], state.candidates[right]],
      candidate_indices: [left, right], pair_row_id: pairId, sum_row_id: row[2], factorization: factorRow});
  }
  function pageSums(options) {
    requireOptions(options, ["offset", "limit"], "sum-page options");
    const offset = options.offset === undefined ? 0 : integer(options.offset, 0, state.sum_rows.length, "offset");
    const limit = options.limit === undefined ? 64 : integer(options.limit, 1, LIMITS.page_size, "limit");
    beginEvent();
    const rows = state.sum_rows.slice(offset, offset + limit), end = offset + rows.length;
    event({operation: "pageSums", offset, limit, returned: rows.length, retained_result_only: true});
    return copy({status: "retained_sum_page", offset, total: state.sum_rows.length,
      next_offset: end < state.sum_rows.length ? end : null, rows});
  }
  function summary() {
    return copy({schema: SCHEMA, source_id: state.source_id, active_session_id: session.id,
      active_session_source_id: session.source_id, vertex_count: n, sum_row_count: state.sum_rows.length,
      pair_row_count: state.pair_rows.length,
      graph_views: state.graph_views.map(graph => ({key: graph.key, allowed_primes: graph.allowed_primes, edge_count: graph.edge_count})),
      searches: state.searches.map(search => ({key: search.key, status: search.status, stop_reason: search.stop_reason,
        processed_node_count: search.processed_nodes.length, pending_count: search.pending.length,
        incumbent_size: search.incumbent_indices.length, maximum_size: search.maximum ? search.maximum.size : null})),
      work: state.work, session: {id: session.id, source_id: session.source_id, opened_by: session.opened_by,
        loading: session.loading, new_work: session.new_work, event_count: session.events.length}});
  }
  function snapshot() { return copy(state); }
  return Object.freeze({searchMaximumClique, getMaximum, getPair, pageSums, summary, snapshot});
}
module.exports = Object.freeze({SCHEMA, LIMITS, compileSmoothSumIndex, openSmoothSumIndex});
