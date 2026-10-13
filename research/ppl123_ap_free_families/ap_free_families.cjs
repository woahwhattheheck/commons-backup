'use strict';

/*
 * Exact persistent families of k-AP-free subsets of [1,N].
 * Element order decreases; LO precedes HI. No filesystem, network or clocks.
 * Ordinary reads use retained nodes and cardinality polynomials.
 */
const SCHEMA = 'commons.ap_free_family/v1';
const LIMITS = Object.freeze({
  max_n: 48, min_k: 3, max_k: 8, max_nodes: 16000,
  max_polynomial_coefficients: 50000, max_points_per_advance: 48,
  max_filter_calls_per_point: 1000000,
  max_page: 64, max_sessions: 16, max_events_per_session: 32,
  max_source_id_chars: 512, max_decimal_digits: 128,
  max_export_values: 4000000, max_export_string_units: 20000000,
  max_export_depth: 48
});
const MAX_COUNT = 2 ** LIMITS.max_n;
const CORE_KEYS = Object.freeze([
  'completed_points', 'constraints_applied', 'filter_calls', 'filter_memo_hits',
  'node_requests', 'node_reuses', 'nodes_created', 'zero_suppressions',
  'polynomial_requests', 'polynomial_reuses', 'polynomials_created',
  'coefficient_additions', 'polynomial_coefficients_created',
  'summary_coefficient_reads', 'sets_enumerated'
]);
const QUERY_KEYS = Object.freeze([
  'calls', 'node_steps', 'coefficient_reads', 'total_reads', 'saved_rows_read',
  'returned_sets', 'returned_rows', 'integer_maps',
  'saved_constraints_scanned', 'family_constructions',
  'constraint_filter_replays', 'polynomial_recurrence_replays'
]);
const QUERY_METHODS = Object.freeze([
  'histogram', 'pageIntervals', 'pageNodes', 'pagePolynomials',
  'pageConstraints', 'selectSet', 'selectMaximum', 'pageSets',
  'rankSet', 'reflectSet', 'affineImage', 'findProgression'
]);
class APFamilyError extends Error {
  constructor(code, message) { super(message); this.name = 'APFamilyError'; this.code = code; }
}
class PointBudget extends Error {
  constructor(code, detail) { super(code); this.code = code; this.detail = detail; }
}
function fail(code, message) { throw new APFamilyError(code, message); }
function integer(v, name, lo, hi) {
  if (!Number.isSafeInteger(v) || v < lo || v > hi)
    fail('E_INTEGER', name + ' must be an integer in [' + lo + ',' + hi + ']');
  return v;
}
function plain(v, name) {
  if (!v || typeof v !== 'object' || Array.isArray(v) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(v)))
    fail('E_OBJECT', name + ' must be a plain object');
  return v;
}
function fields(v, required, optional, name) {
  plain(v, name);
  const keys = Reflect.ownKeys(v);
  for (const key of keys) {
    if (typeof key !== 'string' || !required.concat(optional).includes(key))
      fail('E_FIELD', 'Unexpected ' + name + ' field');
    const d = Object.getOwnPropertyDescriptor(v, key);
    if (!d.enumerable || !Object.hasOwn(d, 'value'))
      fail('E_FIELD', name + ' cannot contain accessors or hidden fields');
  }
  for (const key of required) if (!Object.hasOwn(v, key))
    fail('E_FIELD', 'Missing ' + name + '.' + key);
  return v;
}
function dense(v, name, max) {
  if (!Array.isArray(v) || v.length > max) fail('E_ARRAY', name + ' must be a bounded array');
  const keys = Reflect.ownKeys(v);
  if (keys.length !== v.length + 1) fail('E_ARRAY', name + ' must be dense with no extra fields');
  for (let i = 0; i < v.length; i++) {
    const d = Object.getOwnPropertyDescriptor(v, String(i));
    if (!d || !d.enumerable || !Object.hasOwn(d, 'value'))
      fail('E_ARRAY', name + ' must have plain elements');
  }
  return v;
}
function blank(keys) { return Object.fromEntries(keys.map(k => [k, 0])); }
function addWork(a, b, keys) { for (const k of keys) a[k] += b[k]; return a; }
function diffWork(a, b, keys) { return Object.fromEntries(keys.map(k => [k, a[k] - b[k]])); }
function validateWork(v, keys, name) {
  fields(v, keys, [], name);
  for (const key of keys) integer(v[key], name + '.' + key, 0, Number.MAX_SAFE_INTEGER);
}
function copyJSON(value) {
  const stats = {values: 0, string_units: 0, depth: 0};
  const stack = new Set();
  function walk(v, depth) {
    stats.values++; stats.depth = Math.max(stats.depth, depth);
    if (stats.values > LIMITS.max_export_values || depth > LIMITS.max_export_depth)
      fail('E_EXPORT_LIMIT', 'JSON value/depth limit exceeded');
    if (v === null || typeof v === 'boolean') return v;
    if (typeof v === 'number') {
      if (!Number.isSafeInteger(v)) fail('E_JSON_NUMBER', 'Only safe integer JSON numbers are accepted');
      return v;
    }
    if (typeof v === 'string') {
      stats.string_units += v.length;
      if (stats.string_units > LIMITS.max_export_string_units)
        fail('E_EXPORT_LIMIT', 'JSON string/key limit exceeded');
      return v;
    }
    if (!v || typeof v !== 'object') fail('E_JSON_VALUE', 'Unsupported JSON value');
    if (stack.has(v)) fail('E_JSON_CYCLE', 'JSON cycles are not accepted');
    stack.add(v);
    let out;
    if (Array.isArray(v)) {
      dense(v, 'JSON array', LIMITS.max_export_values);
      out = v.map(x => walk(x, depth + 1));
    } else {
      plain(v, 'JSON object'); out = Object.create(null);
      for (const key of Reflect.ownKeys(v)) {
        if (typeof key !== 'string') fail('E_JSON_KEY', 'JSON symbol keys are not accepted');
        const d = Object.getOwnPropertyDescriptor(v, key);
        if (!d.enumerable || !Object.hasOwn(d, 'value'))
          fail('E_JSON_FIELD', 'JSON accessors and hidden fields are not accepted');
        stats.string_units += key.length;
        if (stats.string_units > LIMITS.max_export_string_units)
          fail('E_EXPORT_LIMIT', 'JSON string/key limit exceeded');
        out[key] = walk(d.value, depth + 1);
      }
    }
    stack.delete(v); return out;
  }
  return {value: walk(value, 0), stats};
}
function sumCoefficients(p, work) {
  let total = 0;
  for (const x of p) { total += x; if (work) work.summary_coefficient_reads++; }
  return integer(total, 'family count', 0, MAX_COUNT);
}
function polyOf(core, id) { return core.polynomials[core.nodes[id][3]]; }
function coefficient(core, id, size, work) {
  const p = polyOf(core, id);
  if (size === null) {
    if (work) work.total_reads++;
    return core.polynomial_totals[core.nodes[id][3]];
  }
  if (work) work.coefficient_reads++;
  return size < 0 || size >= p.length ? 0 : p[size];
}
function intervalRow(core, n) { return core.intervals[n]; }
function intervalSummary(core, n) {
  const r = intervalRow(core, n);
  return {
    n, root: r.root, polynomial_id: core.nodes[r.root][3],
    family_count: r.family_count, maximum_size: r.maximum_size,
    maximum_count: r.maximum_count, constraints: r.constraint_end,
    nodes_at_completion: r.node_end, polynomial_rows_at_completion: r.polynomial_end
  };
}
function initialCore() {
  return {
    n: 0,
    nodes: [[0, 0, 0, 0], [0, 0, 0, 1]],
    polynomials: [[0], [1]], polynomial_totals: [0, 1], polynomial_coefficients: 2,
    constraints: [],
    intervals: [{
      n: 0, root: 1, previous_root: null, include_root: null,
      constraint_start: 0, constraint_end: 0, node_end: 2,
      polynomial_end: 2, polynomial_coefficients: 2,
      family_count: 1, maximum_size: 0, maximum_count: 1
    }],
    work: blank(CORE_KEYS)
  };
}
function nodeKey(v, lo, hi) { return v + ':' + lo + ':' + hi; }
function polynomialKey(p) { return p.join(','); }
function makeMaps(core) {
  const nodes = new Map(), polynomials = new Map();
  for (let id = 2; id < core.nodes.length; id++) {
    const r = core.nodes[id]; nodes.set(nodeKey(r[0], r[1], r[2]), id);
  }
  for (let id = 0; id < core.polynomials.length; id++)
    polynomials.set(polynomialKey(core.polynomials[id]), id);
  return {nodes, polynomials};
}


function makeNode(ctx, v, lo, hi) {
  const c = ctx.core, w = c.work;
  w.node_requests++;
  if (hi === 0) { w.zero_suppressions++; return lo; }
  const key = nodeKey(v, lo, hi), existing = ctx.maps.nodes.get(key);
  if (existing !== undefined) { w.node_reuses++; return existing; }
  if (c.nodes.length >= LIMITS.max_nodes)
    throw new PointBudget('node_limit', {limit: LIMITS.max_nodes});
  if (c.nodes.length - ctx.start_nodes >= ctx.allowed_nodes)
    throw new PointBudget('new_node_budget', {limit: ctx.allowed_nodes});
  if (lo >= c.nodes.length || hi >= c.nodes.length ||
      c.nodes[lo][0] >= v || c.nodes[hi][0] >= v)
    fail('E_INTERNAL_ORDER', 'A new node must have earlier children with smaller elements');
  const a = polyOf(c, lo), b = polyOf(c, hi);
  const p = new Array(Math.max(a.length, b.length + 1)).fill(0);
  for (let i = 0; i < p.length; i++) {
    p[i] = (a[i] || 0) + (i ? (b[i - 1] || 0) : 0);
    integer(p[i], 'new polynomial coefficient', 0, MAX_COUNT);
    w.coefficient_additions++;
  }
  while (p.length > 1 && p[p.length - 1] === 0) p.pop();
  w.polynomial_requests++;
  const pkey = polynomialKey(p);
  let pid = ctx.maps.polynomials.get(pkey);
  if (pid === undefined) {
    if (c.polynomial_coefficients + p.length > LIMITS.max_polynomial_coefficients)
      throw new PointBudget('polynomial_coefficient_limit',
        {limit: LIMITS.max_polynomial_coefficients, needed: p.length});
    if (c.polynomial_coefficients - ctx.start_coefficients + p.length > ctx.allowed_coefficients)
      throw new PointBudget('new_polynomial_coefficient_budget',
        {limit: ctx.allowed_coefficients, needed: p.length});
    const total = sumCoefficients(p, w);
    pid = c.polynomials.length;
    c.polynomials.push(p); c.polynomial_totals.push(total);
    c.polynomial_coefficients += p.length;
    ctx.maps.polynomials.set(pkey, pid); ctx.polynomial_keys.push(pkey);
    w.polynomials_created++; w.polynomial_coefficients_created += p.length;
  } else w.polynomial_reuses++;
  const id = c.nodes.length;
  c.nodes.push([v, lo, hi, pid]);
  ctx.maps.nodes.set(key, id); ctx.node_keys.push(key);
  w.nodes_created++;
  return id;
}
/*
 * Return exactly the members of root that do not contain required.
 * required is strictly decreasing. A missing skipped required element
 * makes the whole remaining family safe; omitting a present required
 * element also makes the corresponding LO branch safe.
 */
function avoidContaining(ctx, root, required) {
  const c = ctx.core, memo = new Map();
  function visit(id, at) {
    c.work.filter_calls++; ctx.point_filter_calls++;
    if (ctx.point_filter_calls > LIMITS.max_filter_calls_per_point)
      throw new PointBudget('filter_call_limit', {limit: LIMITS.max_filter_calls_per_point});
    if (at === required.length) return 0;
    if (id < 2) return id;
    const node = c.nodes[id], needed = required[at];
    if (node[0] < needed) return id;
    const key = id + ':' + at;
    if (memo.has(key)) { c.work.filter_memo_hits++; return memo.get(key); }
    let out;
    if (node[0] === needed)
      out = makeNode(ctx, node[0], node[1], visit(node[2], at + 1));
    else
      out = makeNode(ctx, node[0], visit(node[1], at), visit(node[2], at));
    memo.set(key, out); return out;
  }
  return visit(root, 0);
}
function shallowCore(core) {
  return {
    n: core.n, nodes: core.nodes.slice(), polynomials: core.polynomials.slice(),
    polynomial_totals: core.polynomial_totals.slice(),
    polynomial_coefficients: core.polynomial_coefficients,
    constraints: core.constraints.slice(), intervals: core.intervals.slice(),
    work: {...core.work}
  };
}
function compileAdvance(core, maps, k, args) {
  const c = shallowCore(core);
  const ctx = {
    core: c, maps: {nodes: new Map(maps.nodes), polynomials: new Map(maps.polynomials)},
    node_keys: [], polynomial_keys: [], start_nodes: c.nodes.length,
    start_coefficients: c.polynomial_coefficients,
    allowed_nodes: args.max_new_nodes,
    allowed_coefficients: args.max_new_polynomial_coefficients,
    point_filter_calls: 0
  };
  const preparation = {
    copied_array_slots: c.nodes.length + c.polynomials.length + c.polynomial_totals.length +
      c.constraints.length + c.intervals.length,
    copied_node_map_entries: maps.nodes.size,
    copied_polynomial_map_entries: maps.polynomials.size,
    old_constraint_filters_replayed: 0
  };
  const startN = c.n, oldWork = {...c.work};
  let status = 'requested_points_complete', stopped = null;
  for (let count = 0; count < args.points; count++) {
    if (c.n === LIMITS.max_n) { status = 'domain_limit'; break; }
    const m = c.n + 1;
    const before = {
      nodes: c.nodes.length, polynomials: c.polynomials.length,
      coefficients: c.polynomial_coefficients, constraints: c.constraints.length,
      node_keys: ctx.node_keys.length, polynomial_keys: ctx.polynomial_keys.length,
      work: {...c.work}
    };
    ctx.point_filter_calls = 0;
    try {
      const previous = c.intervals[c.n].root;
      let include = previous;
      for (let d = 1; d <= Math.floor((m - 1) / (k - 1)); d++) {
        const required = [];
        for (let j = 1; j < k; j++) required.push(m - j * d);
        const input = include;
        include = avoidContaining(ctx, include, required);
        c.constraints.push([m, d, input, include]);
        c.work.constraints_applied++;
      }
      const root = makeNode(ctx, m, previous, include);
      const p = polyOf(c, root), pid = c.nodes[root][3];
      c.intervals.push({
        n: m, root, previous_root: previous, include_root: include,
        constraint_start: before.constraints, constraint_end: c.constraints.length,
        node_end: c.nodes.length, polynomial_end: c.polynomials.length,
        polynomial_coefficients: c.polynomial_coefficients,
        family_count: c.polynomial_totals[pid], maximum_size: p.length - 1,
        maximum_count: p[p.length - 1]
      });
      c.n = m; c.work.completed_points++;
    } catch (error) {
      if (!(error instanceof PointBudget)) throw error;
      status = error.code;
      stopped = {
        point: m, reason: error.code, detail: error.detail,
        discarded_new_nodes: c.nodes.length - before.nodes,
        discarded_new_polynomial_rows: c.polynomials.length - before.polynomials,
        discarded_new_polynomial_coefficients: c.polynomial_coefficients - before.coefficients,
        discarded_completed_filters: c.constraints.length - before.constraints,
        work: diffWork(c.work, before.work, CORE_KEYS)
      };
      for (let j = before.node_keys; j < ctx.node_keys.length; j++)
        ctx.maps.nodes.delete(ctx.node_keys[j]);
      for (let j = before.polynomial_keys; j < ctx.polynomial_keys.length; j++)
        ctx.maps.polynomials.delete(ctx.polynomial_keys[j]);
      ctx.node_keys.length = before.node_keys; ctx.polynomial_keys.length = before.polynomial_keys;
      c.nodes.length = before.nodes; c.polynomials.length = before.polynomials;
      c.polynomial_totals.length = before.polynomials;
      c.polynomial_coefficients = before.coefficients;
      c.constraints.length = before.constraints; c.work = before.work;
      break;
    }
  }
  return {
    core: c, maps: ctx.maps,
    result: {
      status, start_n: startN, end_n: c.n, completed_points: c.n - startN,
      requested_points: args.points, frontier: intervalSummary(c, c.n),
      new_nodes: c.nodes.length - core.nodes.length,
      new_polynomial_rows: c.polynomials.length - core.polynomials.length,
      new_polynomial_coefficients: c.polynomial_coefficients - core.polynomial_coefficients,
      stopped_point: stopped
    },
    work: {
      completed: diffWork(c.work, oldWork, CORE_KEYS),
      discarded_point: stopped ? stopped.work : blank(CORE_KEYS), preparation
    }
  };
}


function validateRecord(record) {
  fields(record, ['schema', 'source_id', 'k', 'core', 'sessions'], [], 'record');
  if (record.schema !== SCHEMA) fail('E_SCHEMA', 'Unsupported record schema');
  if (typeof record.source_id !== 'string' || !record.source_id.length ||
      record.source_id.length > LIMITS.max_source_id_chars)
    fail('E_SOURCE_ID', 'A bounded nonempty source_id is required');
  integer(record.k, 'k', LIMITS.min_k, LIMITS.max_k);
  const c = record.core;
  fields(c, ['n', 'nodes', 'polynomials', 'polynomial_totals', 'polynomial_coefficients',
    'constraints', 'intervals', 'work'], [], 'core');
  integer(c.n, 'core.n', 0, LIMITS.max_n);
  dense(c.nodes, 'nodes', LIMITS.max_nodes);
  dense(c.polynomials, 'polynomials', LIMITS.max_polynomial_coefficients);
  dense(c.polynomial_totals, 'polynomial_totals', LIMITS.max_polynomial_coefficients);
  dense(c.constraints, 'constraints', LIMITS.max_n * LIMITS.max_n);
  dense(c.intervals, 'intervals', LIMITS.max_n + 1);
  if (c.nodes.length < 2 || c.polynomials.length < 2 ||
      c.polynomial_totals.length !== c.polynomials.length || c.intervals.length !== c.n + 1)
    fail('E_RECORD_SHAPE', 'Incomplete core tables');
  const maps = {nodes: new Map(), polynomials: new Map()};
  const opening = {
    node_rows: 0, polynomial_rows: 0, polynomial_coefficients: 0,
    constraint_rows: 0, interval_rows: 0, historical_sessions: 0,
    historical_events: 0, historical_query_work_fields: 0,
    node_identity_entries: 0, polynomial_identity_entries: 0,
    family_enumerations: 0, constraint_filter_replays: 0,
    polynomial_recurrence_replays: 0
  };
  const coefficientPrefix = [0];
  for (let pid = 0; pid < c.polynomials.length; pid++) {
    const p = dense(c.polynomials[pid], 'polynomial', LIMITS.max_n + 1);
    if (!p.length || (p.length > 1 && p[p.length - 1] === 0))
      fail('E_POLYNOMIAL', 'Polynomials require canonical nonempty coefficient arrays');
    let sum = 0;
    for (const x of p) { integer(x, 'coefficient', 0, MAX_COUNT); sum += x; }
    integer(sum, 'polynomial total', 0, MAX_COUNT);
    if (c.polynomial_totals[pid] !== sum)
      fail('E_POLYNOMIAL_TOTAL', 'Saved polynomial total disagrees with its coefficients');
    if ((pid === 0 && (p.length !== 1 || p[0] !== 0)) ||
        (pid === 1 && (p.length !== 1 || p[0] !== 1)))
      fail('E_TERMINALS', 'Terminal polynomials must be zero and one');
    const key = polynomialKey(p);
    if (maps.polynomials.has(key)) fail('E_DUPLICATE_POLYNOMIAL', 'Duplicate polynomial row');
    maps.polynomials.set(key, pid);
    opening.polynomial_rows++; opening.polynomial_coefficients += p.length;
    coefficientPrefix.push(opening.polynomial_coefficients);
  }
  if (c.polynomial_coefficients !== opening.polynomial_coefficients ||
      c.polynomial_coefficients > LIMITS.max_polynomial_coefficients)
    fail('E_POLYNOMIAL_BUDGET', 'Invalid polynomial coefficient total');
  for (let id = 0; id < c.nodes.length; id++) {
    const r = dense(c.nodes[id], 'node', 4);
    if (r.length !== 4) fail('E_NODE', 'Node rows require four fields');
    opening.node_rows++;
    if (id < 2) {
      if (r[0] !== 0 || r[1] !== 0 || r[2] !== 0 || r[3] !== id)
        fail('E_TERMINALS', 'Invalid terminal node');
      continue;
    }
    integer(r[0], 'node element', 1, c.n);
    integer(r[1], 'LO child', 0, id - 1);
    integer(r[2], 'HI child', 1, id - 1);
    integer(r[3], 'polynomial id', 1, c.polynomials.length - 1);
    if (c.nodes[r[1]][0] >= r[0] || c.nodes[r[2]][0] >= r[0] ||
        c.polynomials[r[3]].length > r[0] + 1 ||
        c.polynomial_totals[r[3]] < 1 || c.polynomial_totals[r[3]] > 2 ** r[0])
      fail('E_NODE_ORDER', 'Invalid decreasing element order or bounded node polynomial');
    const key = nodeKey(r[0], r[1], r[2]);
    if (maps.nodes.has(key)) fail('E_DUPLICATE_NODE', 'Duplicate node identity');
    maps.nodes.set(key, id);
  }
  const rowFields = ['n', 'root', 'previous_root', 'include_root', 'constraint_start',
    'constraint_end', 'node_end', 'polynomial_end', 'polynomial_coefficients',
    'family_count', 'maximum_size', 'maximum_count'];
  let constraintAt = 0, priorNodeEnd = 2, priorPolynomialEnd = 2;
  for (let n = 0; n <= c.n; n++) {
    const row = fields(c.intervals[n], rowFields, [], 'interval');
    if (row.n !== n || row.constraint_start !== constraintAt)
      fail('E_INTERVAL', 'Noncontiguous interval history');
    integer(row.node_end, 'interval node end', priorNodeEnd, c.nodes.length);
    integer(row.polynomial_end, 'interval polynomial end', priorPolynomialEnd, c.polynomials.length);
    integer(row.root, 'interval root', 1, row.node_end - 1);
    if (row.polynomial_coefficients !== coefficientPrefix[row.polynomial_end])
      fail('E_INTERVAL', 'Interval polynomial frontier mismatch');
    const p = polyOf(c, row.root), pid = c.nodes[row.root][3];
    if (pid >= row.polynomial_end || row.family_count !== c.polynomial_totals[pid] ||
        row.maximum_size !== p.length - 1 || row.maximum_count !== p[p.length - 1])
      fail('E_INTERVAL', 'Interval count summary differs from saved polynomial');
    if (n === 0) {
      if (row.root !== 1 || row.previous_root !== null || row.include_root !== null ||
          row.node_end !== 2 || row.polynomial_end !== 2 || row.constraint_end !== 0)
        fail('E_INTERVAL_ZERO', 'Invalid empty-domain interval');
    } else {
      const previous = c.intervals[n - 1].root;
      if (row.previous_root !== previous || row.root !== row.node_end - 1 ||
          c.nodes[row.root][0] !== n || c.nodes[row.root][1] !== previous ||
          c.nodes[row.root][2] !== row.include_root)
        fail('E_INTERVAL_SPINE', 'The old root must be the literal LO child of the new root');
      let include = previous;
      for (let d = 1; d <= Math.floor((n - 1) / (record.k - 1)); d++) {
        const q = dense(c.constraints[constraintAt], 'constraint', 4);
        if (q.length !== 4 || q[0] !== n || q[1] !== d || q[2] !== include)
          fail('E_CONSTRAINT_CHAIN', 'Incomplete or out-of-order new-maximum constraints');
        integer(q[3], 'filtered root', 0, row.node_end - 1);
        include = q[3]; constraintAt++; opening.constraint_rows++;
      }
      if (row.include_root !== include || row.constraint_end !== constraintAt)
        fail('E_CONSTRAINT_CHAIN', 'New interval inclusion branch differs from the saved chain');
    }
    priorNodeEnd = row.node_end; priorPolynomialEnd = row.polynomial_end;
    opening.interval_rows++;
  }
  if (constraintAt !== c.constraints.length || priorNodeEnd !== c.nodes.length ||
      priorPolynomialEnd !== c.polynomials.length)
    fail('E_CORE_FRONTIER', 'Unbound tail after the last complete interval');
  validateWork(c.work, CORE_KEYS, 'core work');
  if (c.work.completed_points !== c.n || c.work.constraints_applied !== c.constraints.length ||
      c.work.nodes_created !== c.nodes.length - 2 ||
      c.work.polynomials_created !== c.polynomials.length - 2 ||
      c.work.polynomial_coefficients_created !== c.polynomial_coefficients - 2 ||
      c.work.sets_enumerated !== 0)
    fail('E_CORE_WORK', 'Core work totals disagree with retained append-only tables');


  dense(record.sessions, 'sessions', LIMITS.max_sessions);
  if (!record.sessions.length) fail('E_SESSIONS', 'At least one historical session is required');
  for (let sid = 0; sid < record.sessions.length; sid++) {
    const s = fields(record.sessions[sid],
      ['session_id', 'opened_at_n', 'opening', 'events', 'query_work'], [], 'session');
    if (s.session_id !== sid) fail('E_SESSION_REFERENCE', 'Sessions must have consecutive identities');
    integer(s.opened_at_n, 'opened_at_n', 0, c.n);
    plain(s.opening, 'opening work');
    dense(s.events, 'session events', LIMITS.max_events_per_session);
    validateWork(s.query_work, QUERY_KEYS, 'session query work');
    const observed = blank(QUERY_KEYS);
    for (let eid = 0; eid < s.events.length; eid++) {
      const e = fields(s.events[eid], ['reference', 'method', 'args', 'result', 'work'], [], 'event');
      fields(e.reference, ['session_id', 'event_id'], [], 'event reference');
      if (e.reference.session_id !== sid || e.reference.event_id !== eid)
        fail('E_EVENT_REFERENCE', 'Event identity differs from its retained position');
      plain(e.args, 'event args'); plain(e.result, 'event result');
      if (e.method === 'advance') {
        fields(e.work, ['completed', 'discarded_point', 'preparation'], [], 'advance work');
        validateWork(e.work.completed, CORE_KEYS, 'completed advance work');
        validateWork(e.work.discarded_point, CORE_KEYS, 'discarded advance work');
        fields(e.work.preparation, ['copied_array_slots', 'copied_node_map_entries',
          'copied_polynomial_map_entries', 'old_constraint_filters_replayed'], [], 'preparation work');
        for (const value of Object.values(e.work.preparation))
          integer(value, 'preparation work value', 0, Number.MAX_SAFE_INTEGER);
      } else if (QUERY_METHODS.includes(e.method)) {
        validateWork(e.work, QUERY_KEYS, 'query event work');
        if (e.work.calls !== 1 || e.work.family_constructions !== 0 ||
            e.work.constraint_filter_replays !== 0 || e.work.polynomial_recurrence_replays !== 0)
          fail('E_QUERY_WORK', 'Saved-query work cannot claim family construction');
        addWork(observed, e.work, QUERY_KEYS);
        opening.historical_query_work_fields += QUERY_KEYS.length;
      } else fail('E_EVENT_METHOD', 'Unrecognized historical method');
      opening.historical_events++;
    }
    for (const key of QUERY_KEYS) if (observed[key] !== s.query_work[key])
      fail('E_SESSION_WORK', 'Session query total differs from its event receipts');
    opening.historical_sessions++;
  }
  opening.node_identity_entries = maps.nodes.size;
  opening.polynomial_identity_entries = maps.polynomials.size;
  return {maps, opening};
}
function requestedN(core, args) {
  return Object.hasOwn(args, 'n') ? integer(args.n, 'n', 0, core.n) : core.n;
}
function requestedSize(args, n) {
  return !Object.hasOwn(args, 'size') || args.size === null
    ? null : integer(args.size, 'size', 0, n);
}
function pageRange(args, total) {
  return {
    offset: Object.hasOwn(args, 'offset') ? integer(args.offset, 'offset', 0, total) : 0,
    limit: Object.hasOwn(args, 'limit') ? integer(args.limit, 'limit', 0, LIMITS.max_page) : LIMITS.max_page
  };
}
function valuesArgument(args, n) {
  const a = dense(args.values, 'values', LIMITS.max_n);
  let previous = 0;
  for (const value of a) {
    integer(value, 'set element', 1, n);
    if (value <= previous) fail('E_SET_ORDER', 'Set elements must be strictly increasing');
    previous = value;
  }
  return a;
}
function decimal(v, name) {
  if (typeof v !== 'string' || !/^(?:0|-?[1-9][0-9]*)$/.test(v) ||
      v.replace('-', '').length > LIMITS.max_decimal_digits)
    fail('E_DECIMAL', name + ' must be a bounded canonical signed decimal string');
  return BigInt(v);
}


function selectInternal(core, n, size, rank, work, trace) {
  const root = core.intervals[n].root, total = coefficient(core, root, size, work);
  if (!total) fail('E_EMPTY_SIZE', 'No represented set has the requested cardinality');
  integer(rank, 'rank', 0, total - 1);
  const originalRank = rank, values = [], path = [];
  let id = root, remaining = size;
  while (id >= 2) {
    const nodeId = id, node = core.nodes[id], loCount = coefficient(core, node[1], remaining, work);
    work.node_steps++;
    let branch;
    if (rank < loCount) { id = node[1]; branch = 'lo'; }
    else {
      rank -= loCount; values.push(node[0]); id = node[2]; branch = 'hi';
      if (remaining !== null) remaining--;
    }
    if (trace) path.push({
      node: nodeId,
      element: node[0], branch, skipped_count: branch === 'hi' ? loCount : 0,
      rank_after: rank, remaining_size: remaining
    });
  }
  if (id !== 1 || rank !== 0 || (remaining !== null && remaining !== 0))
    fail('E_SAVED_COUNTS', 'Saved counts do not lead to a terminal member');
  values.reverse(); work.returned_sets++;
  const result = {n, size, rank: originalRank, total, values};
  if (trace) result.path = path;
  return result;
}
function rankInternal(core, n, size, values, work, trace) {
  let id = core.intervals[n].root, at = values.length - 1, rank = 0, remaining = size;
  const path = [];
  while (id >= 2) {
    const nodeId = id, node = core.nodes[id];
    work.node_steps++;
    if (at >= 0 && values[at] > node[0]) {
      const result = {n, size, member: false, rank: null, values: values.slice(),
        reason: 'required_element_skipped', missing_element: values[at]};
      if (trace) result.path = path;
      return result;
    }
    let branch, skipped = 0;
    if (at >= 0 && values[at] === node[0]) {
      skipped = coefficient(core, node[1], remaining, work);
      rank += skipped; id = node[2]; at--; branch = 'hi';
      if (remaining !== null) remaining--;
    } else { id = node[1]; branch = 'lo'; }
    if (trace) path.push({
      node: nodeId, element: node[0], branch, skipped_count: skipped,
      accumulated_rank: rank, remaining_size: remaining
    });
  }
  const member = id === 1 && at < 0 && (remaining === null || remaining === 0);
  const result = {n, size, member, rank: member ? rank : null, values: values.slice(),
    reason: member ? 'represented' : 'terminal_rejection'};
  if (trace) result.path = path;
  return result;
}


function answerQuery(core, k, method, args) {
  const w = blank(QUERY_KEYS); w.calls = 1;
  let result;
  if (method === 'histogram') {
    fields(args, [], ['n'], method);
    const n = requestedN(core, args), row = core.intervals[n], p = polyOf(core, row.root);
    w.saved_rows_read++; w.coefficient_reads += p.length;
    result = {...intervalSummary(core, n), size_counts: p.slice(), minimum_size: 0};
  } else if (method === 'pageIntervals') {
    fields(args, [], ['offset', 'limit'], method);
    const total = core.intervals.length, {offset, limit} = pageRange(args, total);
    const rows = core.intervals.slice(offset, offset + limit).map(r => ({...r,
      polynomial_id: core.nodes[r.root][3]}));
    w.saved_rows_read += rows.length; w.returned_rows += rows.length;
    result = {offset, total, rows, next_offset: offset + rows.length < total ? offset + rows.length : null};
  } else if (method === 'pageNodes') {
    fields(args, [], ['offset', 'limit'], method);
    const total = core.nodes.length, {offset, limit} = pageRange(args, total);
    const rows = core.nodes.slice(offset, offset + limit).map((r, i) => ({
      id: offset + i, element: r[0], lo: r[1], hi: r[2], polynomial_id: r[3],
      family_count: core.polynomial_totals[r[3]]
    }));
    w.saved_rows_read += rows.length; w.returned_rows += rows.length; w.total_reads += rows.length;
    result = {offset, total, rows, next_offset: offset + rows.length < total ? offset + rows.length : null};
  } else if (method === 'pagePolynomials') {
    fields(args, [], ['offset', 'limit'], method);
    const total = core.polynomials.length, {offset, limit} = pageRange(args, total);
    const rows = core.polynomials.slice(offset, offset + limit).map((p, i) => {
      w.coefficient_reads += p.length; w.total_reads++;
      return {id: offset + i, coefficients: p.slice(), total: core.polynomial_totals[offset + i]};
    });
    w.saved_rows_read += rows.length; w.returned_rows += rows.length;
    result = {offset, total, rows, next_offset: offset + rows.length < total ? offset + rows.length : null};
  } else if (method === 'pageConstraints') {
    fields(args, [], ['n', 'offset', 'limit'], method);
    const n = Object.hasOwn(args, 'n') ? requestedN(core, args) : null;
    const start = n === null ? 0 : core.intervals[n].constraint_start;
    const end = n === null ? core.constraints.length : core.intervals[n].constraint_end;
    const total = end - start, {offset, limit} = pageRange(args, total), rows = [];
    for (let i = start + offset; i < Math.min(end, start + offset + limit); i++) {
      const q = core.constraints[i], progression = [];
      for (let j = k - 1; j >= 0; j--) progression.push(q[0] - j * q[1]);
      w.integer_maps += k;
      rows.push({index: i, maximum: q[0], difference: q[1], input_root: q[2],
        output_root: q[3], progression, required_without_maximum: progression.slice(0, -1)});
    }
    w.saved_rows_read += rows.length; w.returned_rows += rows.length;
    result = {n, offset, total, rows,
      next_offset: offset + rows.length < total ? offset + rows.length : null};
  } else if (method === 'selectSet' || method === 'selectMaximum') {
    fields(args, ['rank'], method === 'selectSet' ? ['n', 'size'] : ['n'], method);
    const n = requestedN(core, args);
    const size = method === 'selectMaximum' ? core.intervals[n].maximum_size : requestedSize(args, n);
    result = selectInternal(core, n, size, args.rank, w, true);
  } else if (method === 'pageSets') {
    fields(args, [], ['n', 'size', 'offset', 'limit'], method);
    const n = requestedN(core, args), size = requestedSize(args, n);
    const total = coefficient(core, core.intervals[n].root, size, w);
    const {offset, limit} = pageRange(args, total), rows = [];
    for (let rank = offset; rank < Math.min(total, offset + limit); rank++) {
      const selected = selectInternal(core, n, size, rank, w, false);
      rows.push({rank, values: selected.values});
    }
    w.returned_rows += rows.length;
    result = {n, size, offset, total, rows,
      next_offset: offset + rows.length < total ? offset + rows.length : null};
  } else if (method === 'rankSet') {
    fields(args, ['values'], ['n', 'size'], method);
    const n = requestedN(core, args), size = requestedSize(args, n), values = valuesArgument(args, n);
    if (size !== null && size !== values.length)
      fail('E_SIZE', 'A cardinality-filtered rank requires exactly that many elements');
    result = rankInternal(core, n, size, values, w, true);


  } else if (method === 'reflectSet') {
    fields(args, ['rank'], ['n', 'size'], method);
    const n = requestedN(core, args), size = requestedSize(args, n);
    const selected = selectInternal(core, n, size, args.rank, w, false);
    const reflected = selected.values.map(value => n + 1 - value).reverse();
    w.integer_maps += reflected.length;
    const address = rankInternal(core, n, size, reflected, w, false);
    result = {n, size, source: selected, reflected_values: reflected,
      reflected_member: address.member, reflected_rank: address.rank};
  } else if (method === 'affineImage') {
    fields(args, ['rank', 'scale', 'offset'], ['n', 'size'], method);
    const n = requestedN(core, args), size = requestedSize(args, n);
    const scale = decimal(args.scale, 'scale'), offset = decimal(args.offset, 'offset');
    if (scale === 0n) fail('E_SCALE', 'An affine image requires a nonzero scale');
    const selected = selectInternal(core, n, size, args.rank, w, false);
    const pairs = selected.values.map(value => [value, (offset + scale * BigInt(value)).toString()]);
    w.integer_maps += pairs.length;
    const ordered = pairs.map(pair => pair[1]);
    if (scale < 0n) ordered.reverse();
    result = {n, size, source: selected, scale: args.scale, offset: args.offset,
      pairs, ordered_image: ordered,
      interpretation: 'An injective affine image on the integers; the image domain need not be [1,n].'};
  } else if (method === 'findProgression') {
    fields(args, ['values'], ['n'], method);
    const n = requestedN(core, args), values = valuesArgument(args, n), present = new Set(values);
    let witness = null;
    if (values.length >= k) {
      const end = core.intervals[n].constraint_end;
      for (let index = 0; index < end; index++) {
        const q = core.constraints[index], progression = [];
        for (let j = k - 1; j >= 0; j--) progression.push(q[0] - j * q[1]);
        w.saved_constraints_scanned++; w.integer_maps += k;
        if (progression.every(value => present.has(value))) {
          witness = {constraint_index: index, maximum: q[0], difference: q[1], progression};
          break;
        }
      }
    }
    result = {n, k, values: values.slice(), contains_progression: witness !== null, witness};
  } else fail('E_METHOD', 'Unknown saved-family query');
  return {result, work: w};
}
function newSession(session_id, n, opening) {
  return {session_id, opened_at_n: n, opening, events: [], query_work: blank(QUERY_KEYS)};
}


function makeFacade(record, initialMaps) {
  let maps = initialMaps;
  const sid = record.sessions.length - 1;
  function reserveEvent() {
    if (record.sessions[sid].events.length >= LIMITS.max_events_per_session)
      fail('E_EVENT_LIMIT', 'Open a new session before adding more event receipts');
  }
  function commit(method, args, result, work, candidate) {
    const session = record.sessions[sid];
    const reference = {session_id: sid, event_id: session.events.length};
    const saved = copyJSON({reference, method, args, result, work}).value;
    const outward = copyJSON({...result, reference, work}).value;
    const nextWork = method === 'advance'
      ? session.query_work : addWork({...session.query_work}, work, QUERY_KEYS);
    if (candidate) { record.core = candidate.core; maps = candidate.maps; }
    session.events.push(saved); session.query_work = nextWork;
    return outward;
  }
  const facade = {
    summary() {
      const core = record.core, session = record.sessions[sid];
      return copyJSON({
        schema: record.schema, source_id: record.source_id, k: record.k,
        frontier: intervalSummary(core, core.n), node_count: core.nodes.length,
        polynomial_count: core.polynomials.length,
        polynomial_coefficients: core.polynomial_coefficients,
        sessions: record.sessions.length, session_id: sid, events: session.events.length,
        core_work: core.work, query_work: session.query_work
      }).value;
    },
    openingWork() { return copyJSON(record.sessions[sid].opening).value; },
    snapshot() { return copyJSON(record).value; },
    advance(args) {
      fields(args, ['points'], ['max_new_nodes', 'max_new_polynomial_coefficients'], 'advance');
      const effective = {
        points: integer(args.points, 'points', 0, LIMITS.max_points_per_advance),
        max_new_nodes: Object.hasOwn(args, 'max_new_nodes')
          ? integer(args.max_new_nodes, 'max_new_nodes', 0, LIMITS.max_nodes)
          : LIMITS.max_nodes - record.core.nodes.length,
        max_new_polynomial_coefficients: Object.hasOwn(args, 'max_new_polynomial_coefficients')
          ? integer(args.max_new_polynomial_coefficients, 'max_new_polynomial_coefficients',
              0, LIMITS.max_polynomial_coefficients)
          : LIMITS.max_polynomial_coefficients - record.core.polynomial_coefficients
      };
      reserveEvent();
      const candidate = compileAdvance(record.core, maps, record.k, effective);
      const result = {...candidate.result, effective_request: effective};
      return commit('advance', args, result, candidate.work, candidate);
    }
  };
  for (const method of QUERY_METHODS) {
    facade[method] = function(args = {}) {
      reserveEvent();
      const answer = answerQuery(record.core, record.k, method, args);
      return commit(method, args, answer.result, answer.work, null);
    };
  }
  return Object.freeze(facade);
}
function createAPFamily(args) {
  fields(args, ['source_id', 'k'], [], 'createAPFamily');
  if (typeof args.source_id !== 'string' || !args.source_id.length ||
      args.source_id.length > LIMITS.max_source_id_chars)
    fail('E_SOURCE_ID', 'A bounded nonempty source_id is required');
  integer(args.k, 'k', LIMITS.min_k, LIMITS.max_k);
  const core = initialCore();
  const opening = {
    kind: 'constructor', seed_family: 'unit_family_on_empty_domain',
    node_identity_entries: 0, polynomial_identity_entries: 2,
    family_enumerations: 0, constraint_filter_replays: 0,
    polynomial_recurrence_replays: 0
  };
  const record = {schema: SCHEMA, source_id: args.source_id, k: args.k, core,
    sessions: [newSession(0, 0, opening)]};
  return makeFacade(record, makeMaps(core));
}
function openAPFamily(input) {
  const copied = copyJSON(input), record = copied.value;
  const checked = validateRecord(record);
  if (record.sessions.length >= LIMITS.max_sessions)
    fail('E_SESSION_LIMIT', 'The retained record has reached its session limit');
  const opening = {
    kind: 'saved_record', ...checked.opening,
    copied_json_values: copied.stats.values,
    copied_string_key_units: copied.stats.string_units,
    copied_maximum_depth: copied.stats.depth,
    imported_completeness_authenticated: false
  };
  record.sessions.push(newSession(record.sessions.length, record.core.n, opening));
  return makeFacade(record, checked.maps);
}
if (typeof module !== 'undefined' && module.exports)
  module.exports = Object.freeze({SCHEMA, LIMITS, createAPFamily, openAPFamily});
