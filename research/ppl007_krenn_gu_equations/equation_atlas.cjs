"use strict";

const SCHEMA = "commons.krenn_gu_equation_atlas/v1";
const LIMITS = Object.freeze({
  vertices: 12, colors: 8, variables: 1024, equations: 8192,
  monomials: 40000, incidence_entries: 160000, page_rows: 64,
  query_terms: 256, sessions: 8, events_per_session: 48,
  source_id_chars: 512, json_values: 4000000,
  json_string_key_chars: 20000000, json_depth: 48, formatted_chars: 100000
});

class AtlasError extends Error {
  constructor(code, message) {
    super(message); this.name = "AtlasError"; this.code = code;
  }
}
function fail(code, message) { throw new AtlasError(code, message); }
function int(value, low, high, label) {
  if (!Number.isSafeInteger(value) || Object.is(value, -0) || value < low || value > high)
    fail("E_INTEGER", label + " must be an integer in [" + low + "," + high + "].");
  return value;
}
function plain(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null))
    fail("E_OBJECT", label + " must be a plain JSON object.");
}
function keys(value, required, optional, label) {
  plain(value, label);
  const allowed = new Set(required.concat(optional || []));
  for (const key of Object.keys(value)) if (!allowed.has(key))
    fail("E_FIELD", label + " has an unsupported field: " + key);
  for (const key of required) if (!Object.hasOwn(value, key))
    fail("E_FIELD", label + " requires " + key);
}
function array(value, length, label) {
  if (!Array.isArray(value) || (length !== null && value.length !== length))
    fail("E_ARRAY", label + " has an invalid array length.");
}
function sameArray(a, b) {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}
function lexCompare(a, b) {
  for (let i = 0; i < Math.min(a.length, b.length); i++)
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  return a.length === b.length ? 0 : a.length < b.length ? -1 : 1;
}
function copyJSON(input) {
  const usage = {values: 0, string_key_chars: 0, max_depth: 0};
  const stack = new Set();
  function visit(value, depth) {
    if (++usage.values > LIMITS.json_values || depth > LIMITS.json_depth)
      fail("E_JSON_BUDGET", "JSON value/depth budget exceeded.");
    usage.max_depth = Math.max(usage.max_depth, depth);
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isSafeInteger(value) || Object.is(value, -0))
        fail("E_JSON_NUMBER", "Only exact safe-integer JSON numbers are accepted.");
      return value;
    }
    if (typeof value === "string") {
      usage.string_key_chars += value.length;
      if (usage.string_key_chars > LIMITS.json_string_key_chars)
        fail("E_JSON_BUDGET", "JSON string/key budget exceeded.");
      return value;
    }
    if (!value || typeof value !== "object") fail("E_JSON_VALUE", "Unsupported JSON value.");
    if (stack.has(value)) fail("E_JSON_CYCLE", "Cyclic JSON is not accepted.");
    stack.add(value);
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const ownKeys = Reflect.ownKeys(value);
    let output;
    if (Array.isArray(value)) {
      if (ownKeys.length !== value.length + 1 ||
          ownKeys.some(k => typeof k !== "string" || (k !== "length" &&
            (!/^(0|[1-9][0-9]*)$/.test(k) || Number(k) >= value.length))))
        fail("E_JSON_ARRAY", "Arrays must be dense and have no extra properties.");
      output = [];
      for (let i = 0; i < value.length; i++) {
        const d = descriptors[String(i)];
        if (!d || !Object.hasOwn(d, "value") || !d.enumerable)
          fail("E_JSON_ARRAY", "Array accessors/holes are not accepted.");
        output.push(visit(d.value, depth + 1));
      }
    } else {
      plain(value, "JSON object"); output = {};
      for (const key of ownKeys) {
        const d = descriptors[key];
        if (typeof key !== "string" || !Object.hasOwn(d, "value") || !d.enumerable)
          fail("E_JSON_OBJECT", "Object symbols/accessors/non-enumerable fields are not accepted.");
        usage.string_key_chars += key.length;
        if (usage.string_key_chars > LIMITS.json_string_key_chars)
          fail("E_JSON_BUDGET", "JSON string/key budget exceeded.");
        Object.defineProperty(output, key, {value: visit(d.value, depth + 1),
          enumerable: true, writable: true, configurable: true});
      }
    }
    stack.delete(value); return output;
  }
  return {value: visit(input, 0), usage};
}
function addUsage(current, extra, depthOffset) {
  const next = {values: current.values + extra.values,
    string_key_chars: current.string_key_chars + extra.string_key_chars,
    max_depth: Math.max(current.max_depth, depthOffset + extra.max_depth)};
  if (next.values > LIMITS.json_values || next.string_key_chars > LIMITS.json_string_key_chars ||
      next.max_depth > LIMITS.json_depth)
    fail("E_JSON_BUDGET", "The recorded query would exceed the export budget.");
  return next;
}
function pairIndex(u, v, n) {
  return u * (2 * n - u - 1) / 2 + v - u - 1;
}
function modelFor(vertices, colors) {
  const n = int(vertices, 2, LIMITS.vertices, "vertices");
  if (n % 2) fail("E_ORDER", "The number of vertices must be even.");
  const d = int(colors, 2, LIMITS.colors, "colors");
  const degree = n / 2, pair_count = n * (n - 1) / 2;
  let pairing_count = 1;
  for (let q = n - 1; q >= 1; q -= 2) pairing_count *= q;
  const model = {vertices: n, colors: d, degree, pair_count,
    variable_count: pair_count * d * d, pairing_count,
    equation_count: d ** n, term_count: pairing_count * d ** n,
    incidence_entries: degree * pairing_count * d ** n};
  if (model.variable_count > LIMITS.variables || model.equation_count > LIMITS.equations ||
      model.term_count > LIMITS.monomials || model.incidence_entries > LIMITS.incidence_entries)
    fail("E_CONSTRUCTION_BUDGET", "This complete atlas exceeds a preflight construction budget.");
  return model;
}
function colorDigits(id, n, d) {
  const digits = Array(n);
  for (let v = n - 1; v >= 0; v--) { digits[v] = id % d; id = Math.floor(id / d); }
  return digits;
}
function encodeColors(colors, model) {
  array(colors, model.vertices, "coloring");
  let id = 0;
  for (const c of colors) id = id * model.colors + int(c, 0, model.colors - 1, "color");
  return id;
}
function isConstant(colors) { return colors.every(c => c === colors[0]); }
function sourceId(value) {
  if (typeof value !== "string" || !value.trim() || value.length > LIMITS.source_id_chars)
    fail("E_SOURCE_ID", "source_id must be a nonempty bounded string.");
  return value;
}
const BUILD_KEYS = Object.freeze([
  "pairs_written", "variables_written", "pairing_recursion_calls", "pairing_branch_choices",
  "pairings_written", "color_digits_written", "equations_written", "monomials_written",
  "variable_references_written", "incidence_entries_written", "numeric_weight_evaluations"
]);
const QUERY_KEYS = Object.freeze([
  "calls", "saved_rows_read", "saved_term_references_read", "variable_rows_read",
  "incidence_entries_read", "membership_comparisons", "color_digits_mapped",
  "permutation_variables_mapped", "returned_rows", "formatted_characters",
  "pairing_enumerations", "monomial_constructions", "incidence_constructions",
  "numeric_weight_evaluations"
]);
function zeroWork(names) { return Object.fromEntries(names.map(k => [k, 0])); }
function checkWork(value, names, label) {
  keys(value, names, [], label);
  for (const k of names) int(value[k], 0, Number.MAX_SAFE_INTEGER, label + "." + k);
}
function compileAtlas(input) {
  const args = copyJSON(input).value;
  keys(args, ["source_id", "vertices", "colors"], [], "compileAtlas input");
  sourceId(args.source_id);
  const model = modelFor(args.vertices, args.colors), n = model.vertices, d = model.colors;
  const work = zeroWork(BUILD_KEYS);
  const pairs = [], variables = [], pairings = [], equations = [], terms = [];
  for (let u = 0; u < n; u++) for (let v = u + 1; v < n; v++) {
    pairs.push([u, v]); work.pairs_written++;
    for (let a = 0; a < d; a++) for (let b = 0; b < d; b++) {
      variables.push([u, v, a, b]); work.variables_written++;
    }
  }
  function pairRemaining(remaining, prefix) {
    work.pairing_recursion_calls++;
    if (!remaining.length) {
      pairings.push(prefix.slice()); work.pairings_written++; return;
    }
    const u = remaining[0];
    for (let j = 1; j < remaining.length; j++) {
      work.pairing_branch_choices++;
      pairRemaining(remaining.slice(1, j).concat(remaining.slice(j + 1)),
        prefix.concat(pairIndex(u, remaining[j], n)));
    }
  }
  pairRemaining(Array.from({length: n}, (_, i) => i), []);
  const incidence = Array.from({length: model.variable_count}, () => []);
  for (let equation = 0; equation < model.equation_count; equation++) {
    const colors = colorDigits(equation, n, d);
    work.color_digits_written += n;
    equations.push(colors.concat(isConstant(colors) ? 1 : 0)); work.equations_written++;
    for (let pairing = 0; pairing < pairings.length; pairing++) {
      const monomial = pairings[pairing].map(pair => {
        const [u, v] = pairs[pair];
        work.variable_references_written++;
        return pair * d * d + colors[u] * d + colors[v];
      });
      const term = terms.length;
      terms.push(monomial); work.monomials_written++;
      for (const variable of monomial) {
        incidence[variable].push(term); work.incidence_entries_written++;
      }
    }
  }
  const record = {schema: SCHEMA, source_id: args.source_id, model,
    core: {pairs, variables, pairings, equations, terms, incidence},
    construction: {method: "compileAtlas", args, work},
    sessions: []};
  return copyJSON(record).value;
}

const OPEN_KEYS = Object.freeze([
  "copied_json_values", "copied_string_key_chars", "copied_max_depth",
  "pair_rows_checked", "variable_rows_checked", "pairing_rows_checked",
  "equation_rows_checked", "monomial_rows_checked", "term_variable_references_checked",
  "incidence_entries_checked", "history_sessions_checked", "history_events_checked",
  "pairing_enumerations", "monomial_constructions", "incidence_constructions"
]);
const METHODS = Object.freeze([
  "pageVariables", "pagePairings", "pageEquations", "lookupColoring", "pageTerms",
  "term", "locateMonomial", "differentiate", "variableIncidence", "jointIncidence",
  "restrictionProfile", "linearExpansion", "permuteEquation", "formatEquation"
]);
function checkOpening(opening) {
  keys(opening, OPEN_KEYS.concat(["finite_atlas_complete", "source_origin_authenticated"]), [],
    "opening work");
  for (const k of OPEN_KEYS) int(opening[k], 0, Number.MAX_SAFE_INTEGER, "opening." + k);
  if (opening.finite_atlas_complete !== true || opening.source_origin_authenticated !== false)
    fail("E_HISTORY", "Invalid recorded opening disposition.");
}
function validateRecord(record, copyUsage) {
  keys(record, ["schema", "source_id", "model", "core", "construction", "sessions"], [], "record");
  if (record.schema !== SCHEMA) fail("E_SCHEMA", "Unsupported atlas schema.");
  sourceId(record.source_id);
  const model = modelFor(record.model?.vertices, record.model?.colors);
  keys(record.model, Object.keys(model), [], "model");
  for (const k of Object.keys(model)) if (record.model[k] !== model[k])
    fail("E_MODEL", "The model's exact count is inconsistent: " + k);
  const n = model.vertices, d = model.colors, core = record.core;
  keys(core, ["pairs", "variables", "pairings", "equations", "terms", "incidence"], [], "core");
  const work = zeroWork(OPEN_KEYS);
  work.copied_json_values = copyUsage.values;
  work.copied_string_key_chars = copyUsage.string_key_chars;
  work.copied_max_depth = copyUsage.max_depth;
  array(core.pairs, model.pair_count, "pairs");
  array(core.variables, model.variable_count, "variables");
  array(core.pairings, model.pairing_count, "pairings");
  array(core.equations, model.equation_count, "equations");
  array(core.terms, model.term_count, "terms");
  array(core.incidence, model.variable_count, "incidence");
  for (let pair = 0; pair < core.pairs.length; pair++) {
    const row = core.pairs[pair]; array(row, 2, "pair row");
    const u = int(row[0], 0, n - 2, "pair u"), v = int(row[1], u + 1, n - 1, "pair v");
    if (pairIndex(u, v, n) !== pair) fail("E_PAIR", "Pair table must use canonical lexicographic order.");
    work.pair_rows_checked++;
  }
  for (let variable = 0; variable < core.variables.length; variable++) {
    const row = core.variables[variable]; array(row, 4, "variable row");
    const pair = Math.floor(variable / (d * d)), rem = variable % (d * d);
    if (row[0] !== core.pairs[pair][0] || row[1] !== core.pairs[pair][1] ||
        row[2] !== Math.floor(rem / d) || row[3] !== rem % d)
      fail("E_VARIABLE", "Variable table does not match its canonical endpoint/color channel.");
    work.variable_rows_checked++;
  }
  for (let pairing = 0; pairing < core.pairings.length; pairing++) {
    const row = core.pairings[pairing]; array(row, model.degree, "pairing row");
    let vertices = 0, previous = -1;
    for (const p of row) {
      int(p, 0, model.pair_count - 1, "pairing pair");
      if (p <= previous) fail("E_PAIRING", "Pairing pairs must be strictly increasing.");
      previous = p;
      const [u, v] = core.pairs[p], bits = (1 << u) | (1 << v);
      if (vertices & bits) fail("E_PAIRING", "A pairing repeats a vertex.");
      vertices |= bits;
    }
    if (vertices !== (1 << n) - 1 ||
        (pairing && lexCompare(core.pairings[pairing - 1], row) >= 0))
      fail("E_PAIRING", "Pairings must be distinct, complete and lexicographically ordered.");
    work.pairing_rows_checked++;
  }
  for (let equation = 0; equation < core.equations.length; equation++) {
    const row = core.equations[equation]; array(row, n + 1, "equation row");
    let id = 0, constant = true;
    for (let v = 0; v < n; v++) {
      id = id * d + int(row[v], 0, d - 1, "equation color");
      if (row[v] !== row[0]) constant = false;
    }
    if (id !== equation || row[n] !== (constant ? 1 : 0))
      fail("E_EQUATION", "The equation's coloring/right-hand side is inconsistent.");
    work.equation_rows_checked++;
  }
  for (let term = 0; term < core.terms.length; term++) {
    const row = core.terms[term]; array(row, model.degree, "monomial row");
    const equation = Math.floor(term / model.pairing_count), pairing = term % model.pairing_count;
    const colors = core.equations[equation];
    for (let j = 0; j < row.length; j++) {
      const variable = int(row[j], 0, model.variable_count - 1, "monomial variable");
      const channel = core.variables[variable], pair = Math.floor(variable / (d * d));
      if (pair !== core.pairings[pairing][j] ||
          channel[2] !== colors[channel[0]] || channel[3] !== colors[channel[1]])
        fail("E_MONOMIAL", "A saved monomial does not have its declared pairing/coloring.");
      work.term_variable_references_checked++;
    }
    work.monomial_rows_checked++;
  }
  const perVariable = model.pairing_count / (n - 1) * d ** (n - 2);
  for (let variable = 0; variable < core.incidence.length; variable++) {
    const row = core.incidence[variable]; array(row, perVariable, "variable incidence row");
    let previous = -1;
    for (const term of row) {
      int(term, 0, model.term_count - 1, "incidence term");
      if (term <= previous || !core.terms[term].includes(variable))
        fail("E_INCIDENCE", "Incidence must be a distinct ordered list of containing monomials.");
      previous = term; work.incidence_entries_checked++;
    }
  }
  keys(record.construction, ["method", "args", "work"], [], "construction receipt");
  if (record.construction.method !== "compileAtlas") fail("E_CONSTRUCTION", "Invalid construction method.");
  keys(record.construction.args, ["source_id", "vertices", "colors"], [], "construction args");
  if (record.construction.args.source_id !== record.source_id ||
      record.construction.args.vertices !== n || record.construction.args.colors !== d)
    fail("E_CONSTRUCTION", "Construction arguments differ from the atlas.");
  checkWork(record.construction.work, BUILD_KEYS, "construction work");
  const expectedWrites = {pairs_written: model.pair_count, variables_written: model.variable_count,
    pairings_written: model.pairing_count, color_digits_written: n * model.equation_count,
    equations_written: model.equation_count, monomials_written: model.term_count,
    variable_references_written: model.incidence_entries,
    incidence_entries_written: model.incidence_entries, numeric_weight_evaluations: 0};
  for (const k of Object.keys(expectedWrites)) if (record.construction.work[k] !== expectedWrites[k])
    fail("E_CONSTRUCTION", "Construction count differs from the saved complete table: " + k);
  array(record.sessions, null, "sessions");
  if (record.sessions.length > LIMITS.sessions) fail("E_HISTORY", "Too many recorded sessions.");
  for (let sid = 0; sid < record.sessions.length; sid++) {
    const session = record.sessions[sid];
    keys(session, ["session_id", "opening", "events", "query_work"], [], "session");
    if (session.session_id !== sid) fail("E_HISTORY", "Session identities are not consecutive.");
    checkOpening(session.opening); checkWork(session.query_work, QUERY_KEYS, "session work");
    array(session.events, null, "session events");
    if (session.events.length > LIMITS.events_per_session) fail("E_HISTORY", "Too many recorded events.");
    const totals = zeroWork(QUERY_KEYS);
    for (let eid = 0; eid < session.events.length; eid++) {
      const event = session.events[eid];
      keys(event, ["reference", "method", "args", "result", "work"], [], "event");
      keys(event.reference, ["session", "event"], [], "event reference");
      if (event.reference.session !== sid || event.reference.event !== eid ||
          !METHODS.includes(event.method)) fail("E_HISTORY", "Invalid event reference/method.");
      plain(event.args, "event args"); plain(event.result, "event result");
      checkWork(event.work, QUERY_KEYS, "event work");
      if (event.work.calls !== 1 || event.work.pairing_enumerations !== 0 ||
          event.work.monomial_constructions !== 0 || event.work.incidence_constructions !== 0 ||
          event.work.numeric_weight_evaluations !== 0)
        fail("E_HISTORY", "Invalid saved-reader construction/evaluation work.");
      for (const k of QUERY_KEYS) totals[k] += event.work[k];
      work.history_events_checked++;
    }
    for (const k of QUERY_KEYS) if (totals[k] !== session.query_work[k])
      fail("E_HISTORY", "Session query totals differ from the retained events.");
    work.history_sessions_checked++;
  }
  work.finite_atlas_complete = true;
  work.source_origin_authenticated = false;
  return work;
}

function openAtlas(inputRecord) {
  const copied = copyJSON(inputRecord), record = copied.value;
  const opening = validateRecord(record, copied.usage);
  if (record.sessions.length >= LIMITS.sessions) fail("E_SESSION_BUDGET", "No reader session remains.");
  const model = record.model, core = record.core, n = model.vertices, d = model.colors;
  const sid = record.sessions.length;
  const sessionCopy = copyJSON({session_id: sid, opening, events: [], query_work: zeroWork(QUERY_KEYS)});
  let usage = addUsage(copied.usage, sessionCopy.usage, 2);
  const session = sessionCopy.value; record.sessions.push(session);

  function run(method, input, perform) {
    if (session.events.length >= LIMITS.events_per_session)
      fail("E_EVENT_BUDGET", "This reader session has no remaining event slots.");
    const args = copyJSON(input === undefined ? {} : input).value;
    plain(args, method + " arguments");
    const work = zeroWork(QUERY_KEYS); work.calls = 1;
    const result = perform(args, work);
    plain(result, "query result");
    const entry = copyJSON({reference: {session: sid, event: session.events.length},
      method, args, result, work});
    const nextUsage = addUsage(usage, entry.usage, 4);
    const totals = {};
    for (const k of QUERY_KEYS)
      totals[k] = int(session.query_work[k] + work[k], 0, Number.MAX_SAFE_INTEGER, "query total");
    const response = copyJSON(entry.value).value;
    session.events.push(entry.value); session.query_work = totals; usage = nextUsage;
    return response;
  }
  function equationId(value) { return int(value, 0, model.equation_count - 1, "equation_id"); }
  function variableId(value) { return int(value, 0, model.variable_count - 1, "variable_id"); }
  function termId(value) { return int(value, 0, model.term_count - 1, "term_id"); }
  function page(args, total) {
    const offset = int(args.offset === undefined ? 0 : args.offset, 0, total, "offset");
    const limit = int(args.limit === undefined ? LIMITS.page_rows : args.limit, 0, LIMITS.page_rows, "limit");
    const end = Math.min(total, offset + limit);
    return {offset, limit, total, end, next_offset: end < total ? end : null};
  }
  function pageResult(p, rows) {
    return {offset: p.offset, limit: p.limit, total: p.total,
      next_offset: p.next_offset, rows};
  }
  function variableList(value, maxLength, allowRepeats, label) {
    array(value, null, label);
    if (value.length > maxLength) fail("E_LIST_BUDGET", label + " is too long.");
    const found = new Set();
    for (const id of value) {
      variableId(id);
      if (!allowRepeats && found.has(id)) fail("E_DUPLICATE", label + " must not repeat a variable.");
      found.add(id);
    }
    return value.slice();
  }
  function variableRow(id, work) {
    const [u, v, color_u, color_v] = core.variables[id];
    work.variable_rows_read++; work.returned_rows++;
    return {variable_id: id, symbol: "x" + id, u, v, color_u, color_v};
  }
  function pairingRow(id, work) {
    const row = core.pairings[id];
    work.saved_rows_read += 1 + row.length; work.returned_rows++;
    return {pairing_id: id, pair_ids: row.slice(),
      pairs: row.map(pair => core.pairs[pair].slice())};
  }
  function equationRow(id, work) {
    const row = core.equations[id];
    work.saved_rows_read++; work.returned_rows++;
    return {equation_id: id, colors: row.slice(0, n),
      kind: row[n] ? "monochromatic" : "mixed", rhs: row[n],
      degree: model.degree, term_start: id * model.pairing_count,
      term_count: model.pairing_count};
  }
  function termRow(id, work) {
    const row = core.terms[id];
    work.saved_rows_read++; work.saved_term_references_read += row.length; work.returned_rows++;
    return {term_id: id, equation_id: Math.floor(id / model.pairing_count),
      pairing_id: id % model.pairing_count, coefficient: 1, variables: row.slice()};
  }
  function equationIDs(kind, work) {
    if (!["all", "monochromatic", "mixed"].includes(kind))
      fail("E_KIND", "kind must be all, monochromatic or mixed.");
    const ids = [];
    for (let id = 0; id < model.equation_count; id++) {
      if (kind === "all") ids.push(id);
      else {
        work.saved_rows_read++;
        if ((core.equations[id][n] === 1) === (kind === "monochromatic")) ids.push(id);
      }
    }
    return ids;
  }
  function binaryIncidence(row, target, work) {
    let lo = 0, hi = row.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      work.incidence_entries_read++; work.membership_comparisons++;
      if (row[mid] < target) lo = mid + 1; else hi = mid;
    }
    if (lo >= row.length) return false;
    work.incidence_entries_read++; work.membership_comparisons++;
    return row[lo] === target;
  }
  function locatePairing(pairs, work) {
    let lo = 0, hi = core.pairings.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      work.saved_rows_read++; work.membership_comparisons++;
      if (lexCompare(core.pairings[mid], pairs) < 0) lo = mid + 1; else hi = mid;
    }
    if (lo < core.pairings.length) {
      work.saved_rows_read++; work.membership_comparisons++;
      if (sameArray(core.pairings[lo], pairs)) return lo;
    }
    return -1;
  }
  function monomialLocation(ids, work) {
    if (ids.length !== model.degree) return {member: false, reason: "wrong_degree"};
    const sorted = ids.slice().sort((a, b) => a - b), colors = Array(n).fill(-1), pairs = [];
    let covered = 0;
    for (const id of sorted) {
      const [u, v, a, b] = core.variables[id];
      work.variable_rows_read++;
      const bits = (1 << u) | (1 << v);
      if (covered & bits) return {member: false, reason: "overlapping_vertices"};
      covered |= bits; colors[u] = a; colors[v] = b;
      pairs.push(Math.floor(id / (d * d)));
    }
    if (covered !== (1 << n) - 1) return {member: false, reason: "incomplete_vertex_cover"};
    const pairing = locatePairing(pairs, work);
    if (pairing < 0) fail("E_INTERNAL_INDEX", "A valid pairing is missing from the saved atlas.");
    const equation = encodeColors(colors, model); work.color_digits_mapped += n;
    const term = equation * model.pairing_count + pairing;
    work.saved_rows_read++; work.saved_term_references_read += model.degree;
    work.membership_comparisons++;
    if (!sameArray(core.terms[term], sorted))
      fail("E_INTERNAL_INDEX", "The saved monomial lookup is inconsistent.");
    return {member: true, term_id: term, equation_id: equation, pairing_id: pairing, colors};
  }

  const api = {
    summary() {
      return {schema: SCHEMA, source_id: record.source_id, ...model,
        session_id: sid, recorded_events: session.events.length,
        construction_work: {...record.construction.work},
        query_work: {...session.query_work}, export_usage: {...usage},
        finite_atlas_complete: true, source_origin_authenticated: false};
    },
    openingWork() { return {...opening}; },
    snapshot() { return copyJSON(record).value; },
    pageVariables(input) {
      return run("pageVariables", input, (a, w) => {
        keys(a, [], ["offset", "limit"], "pageVariables");
        const p = page(a, model.variable_count), rows = [];
        for (let id = p.offset; id < p.end; id++) rows.push(variableRow(id, w));
        return pageResult(p, rows);
      });
    },
    pagePairings(input) {
      return run("pagePairings", input, (a, w) => {
        keys(a, [], ["offset", "limit"], "pagePairings");
        const p = page(a, model.pairing_count), rows = [];
        for (let id = p.offset; id < p.end; id++) rows.push(pairingRow(id, w));
        return pageResult(p, rows);
      });
    },
    pageEquations(input) {
      return run("pageEquations", input, (a, w) => {
        keys(a, [], ["kind", "offset", "limit"], "pageEquations");
        const ids = equationIDs(a.kind === undefined ? "all" : a.kind, w);
        const p = page(a, ids.length), rows = [];
        for (let i = p.offset; i < p.end; i++) rows.push(equationRow(ids[i], w));
        return pageResult(p, rows);
      });
    },
    lookupColoring(input) {
      return run("lookupColoring", input, (a, w) => {
        keys(a, ["colors"], [], "lookupColoring");
        const id = encodeColors(a.colors, model); w.color_digits_mapped += n;
        return {equation: equationRow(id, w)};
      });
    },
    pageTerms(input) {
      return run("pageTerms", input, (a, w) => {
        keys(a, ["equation_id"], ["offset", "limit"], "pageTerms");
        const id = equationId(a.equation_id), p = page(a, model.pairing_count), rows = [];
        for (let i = p.offset; i < p.end; i++) rows.push(termRow(id * model.pairing_count + i, w));
        return {equation_id: id, ...pageResult(p, rows)};
      });
    },
    term(input) {
      return run("term", input, (a, w) => {
        keys(a, ["term_id"], [], "term");
        const id = termId(a.term_id), row = termRow(id, w);
        return {term: row, equation: equationRow(row.equation_id, w),
          channels: core.terms[id].map(variable => variableRow(variable, w))};
      });
    },
    locateMonomial(input) {
      return run("locateMonomial", input, (a, w) => {
        keys(a, ["variables"], [], "locateMonomial");
        const ids = variableList(a.variables, LIMITS.vertices, true, "variables");
        return monomialLocation(ids, w);
      });
    },

    differentiate(input) {
      return run("differentiate", input, (a, w) => {
        keys(a, ["equation_id", "variables"], [], "differentiate");
        const equation = equationId(a.equation_id);
        const ids = variableList(a.variables, LIMITS.vertices, true, "variables");
        const selected = new Set(ids), rows = [];
        w.saved_rows_read++;
        const rhs = ids.length ? 0 : core.equations[equation][n];
        if (selected.size !== ids.length || ids.length > model.degree)
          return {equation_id: equation, variables: ids, degree_bound: Math.max(0, model.degree - ids.length),
            rhs, repeated_variable: selected.size !== ids.length, zero_polynomial: true, terms: []};
        for (let p = 0; p < model.pairing_count; p++) {
          const term = equation * model.pairing_count + p, row = core.terms[term];
          w.saved_rows_read++; w.saved_term_references_read += row.length;
          let includes = true;
          for (const variable of ids) {
            w.membership_comparisons++;
            if (!row.includes(variable)) { includes = false; break; }
          }
          if (includes) {
            if (rows.length >= LIMITS.query_terms) fail("E_QUERY_BUDGET", "Derivative output term limit exceeded.");
            rows.push({source_term_id: term, coefficient: 1,
              variables: row.filter(variable => !selected.has(variable))});
            w.returned_rows++;
          }
        }
        return {equation_id: equation, variables: ids, degree_bound: model.degree - ids.length,
          rhs, repeated_variable: false, zero_polynomial: rows.length === 0 && rhs === 0, terms: rows};
      });
    },
    variableIncidence(input) {
      return run("variableIncidence", input, (a, w) => {
        keys(a, ["variable_id"], ["offset", "limit"], "variableIncidence");
        const variable = variableId(a.variable_id), ids = core.incidence[variable];
        const p = page(a, ids.length), rows = [];
        for (let i = p.offset; i < p.end; i++) {
          w.incidence_entries_read++;
          rows.push(termRow(ids[i], w));
        }
        return {variable_id: variable, ...pageResult(p, rows)};
      });
    },
    jointIncidence(input) {
      return run("jointIncidence", input, (a, w) => {
        keys(a, ["variables"], ["offset", "limit"], "jointIncidence");
        const variables = variableList(a.variables, LIMITS.vertices, false, "variables");
        let selected;
        if (!variables.length) selected = Array.from({length: model.term_count}, (_, id) => id);
        else {
          const ordered = variables.slice().sort((a, b) => core.incidence[a].length - core.incidence[b].length || a - b);
          selected = [];
          for (const term of core.incidence[ordered[0]]) {
            w.incidence_entries_read++;
            let found = true;
            for (let i = 1; i < ordered.length; i++)
              if (!binaryIncidence(core.incidence[ordered[i]], term, w)) { found = false; break; }
            if (found) selected.push(term);
          }
        }
        const p = page(a, selected.length), rows = [];
        for (let i = p.offset; i < p.end; i++) rows.push(termRow(selected[i], w));
        return {variables, ...pageResult(p, rows)};
      });
    },
    restrictionProfile(input) {
      return run("restrictionProfile", input, (a, w) => {
        keys(a, ["zero_variables"], [], "restrictionProfile");
        const ids = variableList(a.zero_variables, model.variable_count, false, "zero_variables");
        const removed = new Set(ids), counts = [], histogram = new Map(), impossible = [];
        let surviving = 0, mixed = 0, monochromatic = 0, singletonMixed = 0;
        for (let equation = 0; equation < model.equation_count; equation++) {
          let count = 0;
          for (let p = 0; p < model.pairing_count; p++) {
            const term = equation * model.pairing_count + p, row = core.terms[term];
            w.saved_rows_read++;
            let retained = true;
            for (const variable of row) {
              w.saved_term_references_read++; w.membership_comparisons++;
              if (removed.has(variable)) { retained = false; break; }
            }
            if (retained) count++;
          }
          w.saved_rows_read++;
          const mono = core.equations[equation][n] === 1;
          counts.push(count); surviving += count;
          if (mono) { monochromatic += count; if (!count) impossible.push(equation); }
          else { mixed += count; if (count === 1) singletonMixed++; }
          if (!histogram.has(count)) histogram.set(count,
            {surviving_terms: count, equations: 0, monochromatic: 0, mixed: 0});
          const bucket = histogram.get(count);
          bucket.equations++; bucket[mono ? "monochromatic" : "mixed"]++;
        }
        const buckets = [...histogram.values()].sort((a, b) => a.surviving_terms - b.surviving_terms);
        w.returned_rows += counts.length + buckets.length;
        return {zero_variables: ids, equations: model.equation_count,
          surviving_terms: surviving, monochromatic_terms: monochromatic, mixed_terms: mixed,
          mixed_singleton_equations: singletonMixed, surviving_terms_by_equation: counts,
          histogram: buckets, impossible_unit_equations: impossible,
          interpretation: "Symbolic zero-channel restriction; remaining weights are unevaluated."};
      });
    },

    linearExpansion(input) {
      return run("linearExpansion", input, (a, w) => {
        keys(a, ["equation_id", "vertex"], [], "linearExpansion");
        const equation = equationId(a.equation_id), vertex = int(a.vertex, 0, n - 1, "vertex");
        if (model.pairing_count > LIMITS.query_terms)
          fail("E_QUERY_BUDGET", "Expansion output term limit exceeded.");
        const groups = new Map();
        for (let p = 0; p < model.pairing_count; p++) {
          const term = equation * model.pairing_count + p, row = core.terms[term];
          w.saved_rows_read++; w.saved_term_references_read += row.length;
          let selected = -1;
          for (const variable of row) {
            const channel = core.variables[variable]; w.variable_rows_read++;
            if (channel[0] === vertex || channel[1] === vertex) { selected = variable; break; }
          }
          if (selected < 0) fail("E_INTERNAL_INDEX", "The saved matching does not cover the selected vertex.");
          if (!groups.has(selected)) groups.set(selected, {variable_id: selected, coefficient_terms: []});
          groups.get(selected).coefficient_terms.push({source_term_id: term, coefficient: 1,
            variables: row.filter(variable => variable !== selected)});
          w.returned_rows++;
        }
        const rows = [...groups.values()].sort((a, b) => a.variable_id - b.variable_id);
        w.saved_rows_read++; w.returned_rows += rows.length;
        return {equation_id: equation, vertex, rhs: core.equations[equation][n],
          coefficient_degree: model.degree - 1, groups: rows};
      });
    },
    permuteEquation(input) {
      return run("permuteEquation", input, (a, w) => {
        keys(a, ["equation_id", "vertex_images", "color_images"], [], "permuteEquation");
        const equation = equationId(a.equation_id);
        function permutation(value, size, label) {
          array(value, size, label);
          for (const item of value) int(item, 0, size - 1, label + " entry");
          if (new Set(value).size !== size) fail("E_PERMUTATION", label + " must be a permutation.");
          return value;
        }
        const vertexImages = permutation(a.vertex_images, n, "vertex_images");
        const colorImages = permutation(a.color_images, d, "color_images");
        if (model.pairing_count > LIMITS.query_terms)
          fail("E_QUERY_BUDGET", "Permutation output term limit exceeded.");
        const sourceColors = core.equations[equation], targetColors = Array(n);
        w.saved_rows_read++;
        for (let v = 0; v < n; v++) {
          targetColors[vertexImages[v]] = colorImages[sourceColors[v]];
          w.color_digits_mapped++;
        }
        const targetEquation = encodeColors(targetColors, model); w.color_digits_mapped += n;
        const maps = [];
        for (let p = 0; p < model.pairing_count; p++) {
          const sourceTerm = equation * model.pairing_count + p, row = core.terms[sourceTerm];
          w.saved_rows_read++; w.saved_term_references_read += row.length;
          const mapped = row.map(variable => {
            const [u, v, ca, cb] = core.variables[variable];
            w.variable_rows_read++; w.permutation_variables_mapped++;
            const x = vertexImages[u], y = vertexImages[v];
            const a = colorImages[ca], b = colorImages[cb];
            return x < y ? pairIndex(x, y, n) * d * d + a * d + b
              : pairIndex(y, x, n) * d * d + b * d + a;
          }).sort((a, b) => a - b);
          const location = monomialLocation(mapped, w);
          if (!location.member || location.equation_id !== targetEquation)
            fail("E_INTERNAL_INDEX", "Permutation does not map to the saved target polynomial.");
          maps.push({source_term_id: sourceTerm, target_term_id: location.term_id,
            target_variables: mapped}); w.returned_rows++;
        }
        return {source_equation_id: equation, vertex_images: vertexImages.slice(),
          color_images: colorImages.slice(), target_equation: equationRow(targetEquation, w),
          term_map: maps};
      });
    },
    formatEquation(input) {
      return run("formatEquation", input, (a, w) => {
        keys(a, ["equation_id"], ["form", "variable_prefix"], "formatEquation");
        const equation = equationId(a.equation_id), form = a.form === undefined ? "equation" : a.form;
        const prefix = a.variable_prefix === undefined ? "x" : a.variable_prefix;
        if (!["equation", "residual"].includes(form)) fail("E_FORMAT", "form must be equation or residual.");
        if (typeof prefix !== "string" || !/^[A-Za-z_][A-Za-z0-9_]{0,31}$/.test(prefix))
          fail("E_FORMAT", "variable_prefix must be a bounded identifier.");
        const pieces = [];
        for (let p = 0; p < model.pairing_count; p++) {
          const row = core.terms[equation * model.pairing_count + p];
          w.saved_rows_read++; w.saved_term_references_read += row.length;
          pieces.push(row.map(variable => prefix + variable).join("*"));
        }
        w.saved_rows_read++;
        const rhs = core.equations[equation][n];
        let text = pieces.join(" + ");
        if (form === "equation") text += " = " + rhs;
        else if (rhs) text += " - 1";
        if (text.length > LIMITS.formatted_chars) fail("E_FORMAT_BUDGET", "Formatted equation is too long.");
        w.formatted_characters += text.length;
        return {equation_id: equation, form, variable_prefix: prefix,
          amplitude_terms: model.pairing_count, residual_constant: rhs ? -1 : 0, rhs, text};
      });
    }
  };
  return Object.freeze(api);
}

module.exports = Object.freeze({SCHEMA, LIMITS, AtlasError, compileAtlas, openAtlas});
