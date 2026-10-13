"use strict";

/**
 * Singer trace-zero difference sets from an identified retained prime-cubic
 * power cycle. This module performs no field reconstruction, primality test,
 * irreducibility test, generator search, or accepted B3 computation.
 *
 * The exact finite difference certificate is independent of those provenance
 * claims once its explicit residues and witness rows have been retained.
 * See SINGER_PLANE_API.md for attribution and the finite/global boundary.
 */

const SINGER_PLANE_LIMITS = Object.freeze({
  prime_min: 2,
  prime_max: 31,
  maximum_cycle_codes: 29790,
  maximum_trace_rows: 993,
  maximum_pair_rows: 2048,
  maximum_snapshot_chars: 2000000,
  maximum_page_rows: 256
});
const SNAPSHOT_SCHEMA = "commons.singer_plane_index/v1";
const COMPLETE = "EXACT_PLANAR_DIFFERENCE_INDEX";
const RECORD_SCHEMA = "erdos241.prime13_cubic_b3_run/v1";
const RESULT_SCHEMA = "erdos241.bose_chowla_b3/v1";

function fail(message) { throw new RangeError(message); }
function integer(value, name, low, high) {
  if (!Number.isSafeInteger(value) || value < low || value > high) {
    fail(name + " must be a safe integer in [" + low + "," + high + "]");
  }
  return value;
}
function object(value, name) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(name + " must be an object");
  return value;
}
function array(value, name, length) {
  if (!Array.isArray(value) || (length !== undefined && value.length !== length)) {
    fail(name + " must be an array" + (length === undefined ? "" : " of length " + length));
  }
  return value;
}
function bool(value, name) {
  if (typeof value !== "boolean") fail(name + " must be boolean");
  return value;
}
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function mod(value, modulus) { const r = value % modulus; return r < 0 ? r + modulus : r; }
function provenance(value) {
  object(value, "provenance");
  for (const key of ["repository", "path", "commit", "git_blob_sha"]) {
    if (typeof value[key] !== "string" || !value[key].length || /[\r\n]/.test(value[key])) {
      fail("provenance." + key + " must be a nonempty single-line string");
    }
  }
  if (!/^[^/\s]+\/[^/\s]+$/.test(value.repository)) fail("provenance.repository must be owner/name");
  for (const key of ["commit", "git_blob_sha"]) {
    if (!/^[0-9a-f]{40}$/.test(value[key])) fail("provenance." + key + " must be a lowercase 40-digit Git identity");
  }
  return { repository: value.repository, path: value.path, commit: value.commit, git_blob_sha: value.git_blob_sha };
}
function decode(code, q) {
  return [code % q, Math.floor(code / q) % q, Math.floor(code / (q * q))];
}
function parseDetached(value, name) {
  let serialized;
  if (typeof value === "string") serialized = value;
  else {
    object(value, name);
    serialized = JSON.stringify(value);
  }
  if (serialized.length > SINGER_PLANE_LIMITS.maximum_snapshot_chars) fail(name + " exceeds the character cap");
  return JSON.parse(serialized);
}
function zeroWork() {
  return {
    trace_rows_created: 0,
    retained_cycle_lookups: 0,
    field_codes_decoded: 0,
    coefficient_sums_mod_prime: 0,
    unordered_pairs_visited: 0,
    ordered_difference_rows_created: 0,
    sum_rows_created: 0,
    field_multiplications: 0,
    primality_tests: 0,
    irreducibility_tests: 0,
    primitive_cycle_reconstructions: 0,
    upstream_B3_triples_enumerated: 0,
    projective_point_pairs_enumerated: 0,
    projective_line_pairs_enumerated: 0
  };
}

/**
 * input.record is a completed result or the recognized retained run wrapper,
 * as an object or JSON text.
 * Its accepted field/cycle assertions are premises, not re-established here.
 * input.provenance identifies the independently retained exact source.
 *
 * A budget refusal occurs before any trace lookup. A mathematical failure
 * retains the newly completed finite rows but supplies no usable index.
 */
function compileSingerPlaneFromBoseChowla(input) {
  object(input, "input");
  const src = provenance(input.provenance);
  const record = parseDetached(input.record, "record");
  const result = record.schema === RESULT_SCHEMA ? record :
    record.schema === RECORD_SCHEMA ? object(record.result, "record.result") :
    fail("unsupported retained construction schema");
  if (result.schema !== RESULT_SCHEMA || result.status !== "EXACT_CONSTRUCTED_B3_SET") {
    fail("an identified completed Bose-Chowla construction record is required");
  }
  const q = integer(result.prime, "result.prime", SINGER_PLANE_LIMITS.prime_min, SINGER_PLANE_LIMITS.prime_max);
  const fieldSize = q * q * q, cycleOrder = fieldSize - 1, v = q * q + q + 1, k = q + 1;
  if (result.field_size !== fieldSize || result.cyclic_modulus !== cycleOrder || result.order_of_sums !== 3) {
    fail("inconsistent prime-cubic source dimensions");
  }
  const f = array(result.cubic_coefficients, "cubic_coefficients", 3).map((x,i) => integer(x, "cubic coefficient " + i, 0, q - 1));
  const encoding = object(result.field_encoding, "field_encoding");
  if (encoding.code !== "c0 + prime*c1 + prime^2*c2" ||
      encoding.coefficient_order !== "constant, linear, quadratic") fail("unsupported field code convention");
  const cycle = object(result.power_cycle, "power_cycle");
  if (cycle.exponent_start !== 0 || cycle.exponent_end_inclusive !== cycleOrder - 1) fail("unsupported cycle exponent interval");
  const codes = array(cycle.codes, "power_cycle.codes", cycleOrder);
  if (codes.length > SINGER_PLANE_LIMITS.maximum_cycle_codes) fail("cycle length exceeds the cap");
  const selectedCode = integer(object(result.generator_search, "generator_search").selected_code, "selected generator code", 1, fieldSize - 1);
  const maxTrace = input.max_trace_rows === undefined ? SINGER_PLANE_LIMITS.maximum_trace_rows :
    integer(input.max_trace_rows, "max_trace_rows", 0, SINGER_PLANE_LIMITS.maximum_trace_rows);
  const maxPairs = input.max_pair_rows === undefined ? SINGER_PLANE_LIMITS.maximum_pair_rows :
    integer(input.max_pair_rows, "max_pair_rows", 0, SINGER_PLANE_LIMITS.maximum_pair_rows);
  const requiredPairs = k * (k - 1) + k * (k + 1) / 2;
  const work = zeroWork();
  if (v > maxTrace || requiredPairs > maxPairs) {
    return {
      schema: SNAPSHOT_SCHEMA, status: "INCOMPLETE_BUDGET",
      stop: { stage: "preflight", required_trace_rows: v, allowed_trace_rows: maxTrace,
        required_pair_rows: requiredPairs, allowed_pair_rows: maxPairs },
      provenance: src, work, snapshot: null
    };
  }

  const traceRecords = [], residues = [], diagnostics = [];
  for (let e = 0; e < v; e++) {
    const exponents = [e, (e * q) % cycleOrder, (e * q * q) % cycleOrder];
    const accessed = exponents.map((a,j) => {
      work.retained_cycle_lookups++;
      return integer(codes[a], "accessed power code at exponent " + a, 1, fieldSize - 1);
    });
    const coefficients = accessed.map(c => { work.field_codes_decoded++; return decode(c, q); });
    const tr = [0,1,2].map(j => {
      work.coefficient_sums_mod_prime++;
      return (coefficients[0][j] + coefficients[1][j] + coefficients[2][j]) % q;
    });
    const trCode = tr[0] + q * tr[1] + q * q * tr[2];
    const isZero = trCode === 0;
    traceRecords.push({ residue: e, cycle_exponents: exponents, field_codes: accessed,
      trace_coefficients: tr, trace_code: trCode, is_zero: isZero });
    work.trace_rows_created++;
    if (tr[1] !== 0 || tr[2] !== 0) diagnostics.push({ kind: "trace_not_in_base_field", residue: e, trace_coefficients: tr });
    if (isZero) residues.push(e);
  }
  if (residues.length !== k) diagnostics.push({ kind: "unexpected_trace_zero_count", expected: k, actual: residues.length });
  if (diagnostics.length) {
    return { schema: SNAPSHOT_SCHEMA, status: "INVALID_PREMISE_OR_TRACE_RESULT", provenance: src,
      prime: q, modulus: v, trace_records: traceRecords, difference_set: residues, diagnostics, work, snapshot: null };
  }

  const differences = new Array(v).fill(null), sums = [], sumRanks = new Array(v).fill(null);
  function addDifference(fromIndex, toIndex) {
    const a = residues[fromIndex], b = residues[toIndex], r = mod(b - a, v);
    const row = { difference: r, from_index: fromIndex, to_index: toIndex, from: a, to: b };
    work.ordered_difference_rows_created++;
    if (r === 0 || differences[r] !== null) diagnostics.push({ kind: "difference_collision", previous: differences[r], candidate: row });
    else differences[r] = row;
  }
  for (let i = 0; i < k; i++) {
    for (let j = i; j < k; j++) {
      work.unordered_pairs_visited++;
      const row = { rank: sums.length, left_index: i, right_index: j,
        left: residues[i], right: residues[j], sum: (residues[i] + residues[j]) % v };
      if (sumRanks[row.sum] !== null) diagnostics.push({ kind: "sum_collision", previous_rank: sumRanks[row.sum], candidate: row });
      else sumRanks[row.sum] = row.rank;
      sums.push(row); work.sum_rows_created++;
      if (i !== j) { addDifference(i,j); addDifference(j,i); }
    }
  }
  for (let r = 1; r < v; r++) if (differences[r] === null) diagnostics.push({ kind: "missing_nonzero_difference", difference: r });
  if (diagnostics.length) {
    return { schema: SNAPSHOT_SCHEMA, status: "NOT_A_PLANAR_DIFFERENCE_INDEX", provenance: src,
      prime: q, modulus: v, trace_records: traceRecords, difference_set: residues,
      ordered_differences: differences.slice(1), unordered_sums: sums, diagnostics, work, snapshot: null };
  }
  const shift = 1 - residues[0], positive = residues.map(a => a + shift);
  const snapshot = {
    schema: SNAPSHOT_SCHEMA, status: COMPLETE,
    construction: {
      kind: "trace_zero_from_identified_prime_cubic_cycle",
      prime: q, extension_degree: 3, field_size: fieldSize, cycle_order: cycleOrder,
      scalar_subgroup_order: q - 1, modulus: v, generator_code: selectedCode,
      cubic_coefficients: f, field_code: encoding.code, coefficient_order: encoding.coefficient_order,
      source_wrapper_schema: record.schema, source_result_schema: result.schema,
      source: src,
      field_and_primitive_cycle_are_identified_premises: true,
      field_and_primitive_cycle_reconstructed: false
    },
    difference_set: residues,
    trace_records: traceRecords,
    ordered_differences: differences.slice(1),
    unordered_sums: sums,
    sum_rank_by_residue: sumRanks,
    positive_lift: {
      translation: shift, values: positive, cardinality: k, endpoint: positive[positive.length - 1],
      convention: "subtract the least canonical residue and add one; no cyclic-gap or affine optimization"
    },
    summary: {
      modulus: v, field_prime: q, difference_set_size: k,
      nonzero_difference_count: v - 1, unordered_pair_count: k * (k + 1) / 2,
      repeated_summand_pairs: k, represented_sum_residues: sums.length,
      missing_sum_residues: v - sums.length,
      point_count: v, line_count: v, points_per_line: k, lines_per_point: k,
      total_incidences: v * k,
      cyclic_sidon_maximum_size: k,
      cyclic_sidon_optimality_scope: "subsets of this cyclic group; the difference count gives the upper bound",
      incidence_storage: "implicit translates of the retained difference set; all line/point pairs are not enumerated"
    },
    work,
    limits: clone(SINGER_PLANE_LIMITS)
  };
  const length = JSON.stringify(snapshot).length;
  if (length > SINGER_PLANE_LIMITS.maximum_snapshot_chars) {
    return { schema: SNAPSHOT_SCHEMA, status: "INCOMPLETE_BUDGET", stop: {
      stage: "snapshot", actual_chars: length, allowed_chars: SINGER_PLANE_LIMITS.maximum_snapshot_chars
    }, provenance: src, work, snapshot: null };
  }
  return { schema: SNAPSHOT_SCHEMA, status: COMPLETE, summary: clone(snapshot.summary),
    snapshot, work: clone(work), snapshot_chars: length };
}

function openRetainedSingerPlane(value) {
  const s = parseDetached(value, "snapshot");
  if (s.schema !== SNAPSHOT_SCHEMA || s.status !== COMPLETE) fail("a complete retained Singer index is required");
  const c = object(s.construction, "construction");
  const q = integer(c.prime, "prime", SINGER_PLANE_LIMITS.prime_min, SINGER_PLANE_LIMITS.prime_max);
  const v = q*q+q+1, k = q+1, fieldSize = q*q*q, cycleOrder = fieldSize-1;
  if (c.modulus !== v || c.field_size !== fieldSize || c.cycle_order !== cycleOrder ||
      c.scalar_subgroup_order !== q-1 || c.extension_degree !== 3 ||
      c.kind !== "trace_zero_from_identified_prime_cubic_cycle" ||
      c.field_and_primitive_cycle_are_identified_premises !== true ||
      c.field_and_primitive_cycle_reconstructed !== false) fail("inconsistent construction header");
  provenance(c.source);
  const D = array(s.difference_set, "difference_set", k);
  for (let i=0;i<k;i++) {
    integer(D[i],"difference set residue",0,v-1);
    if (i && D[i] <= D[i-1]) fail("difference set must be strictly increasing");
  }
  const indexOf = new Map(D.map((a,i)=>[a,i]));
  const stats = {
    loaded_trace_records: 0, loaded_difference_witnesses: 0, loaded_sum_rows: 0,
    saved_difference_arithmetic_checks: 0, saved_sum_arithmetic_checks: 0,
    queries: 0, summary_queries: 0, trace_queries: 0, difference_queries: 0,
    incidence_queries: 0, join_queries: 0, meet_queries: 0, pair_queries: 0,
    page_queries: 0, rank_queries: 0, select_queries: 0, positive_lift_queries: 0,
    page_rows_returned: 0, translated_incidence_labels: 0,
    field_multiplications: 0, trace_recomputations: 0,
    cycle_reconstructions: 0, difference_pair_enumerations: 0, unordered_pair_enumerations: 0,
    projective_point_pairs_enumerated: 0, projective_line_pairs_enumerated: 0
  };
  array(s.trace_records,"trace_records",v);
  for (let e=0;e<v;e++) {
    const r=object(s.trace_records[e],"trace row");
    if(r.residue!==e) fail("trace rows must use residue order");
    array(r.cycle_exponents,"cycle_exponents",3).forEach(x=>integer(x,"saved exponent",0,cycleOrder-1));
    array(r.field_codes,"field_codes",3).forEach(x=>integer(x,"saved field code",1,fieldSize-1));
    array(r.trace_coefficients,"trace_coefficients",3).forEach(x=>integer(x,"saved trace coefficient",0,q-1));
    integer(r.trace_code,"saved trace code",0,fieldSize-1);
    bool(r.is_zero,"saved zero flag");
    if(r.is_zero!==indexOf.has(e)) fail("zero flags and retained difference set disagree");
    stats.loaded_trace_records++;
  }
  const diff = new Array(v).fill(null);
  array(s.ordered_differences,"ordered_differences",v-1);
  for(let r=1;r<v;r++){
    const a=object(s.ordered_differences[r-1],"difference row");
    if(a.difference!==r) fail("difference rows must cover nonzero residues in order");
    const i=integer(a.from_index,"from_index",0,k-1),j=integer(a.to_index,"to_index",0,k-1);
    if(i===j || a.from!==D[i] || a.to!==D[j] || mod(a.to-a.from,v)!==r) fail("invalid saved ordered-difference witness");
    diff[r]=a; stats.loaded_difference_witnesses++; stats.saved_difference_arithmetic_checks++;
  }
  const pairCount=k*(k+1)/2;
  array(s.unordered_sums,"unordered_sums",pairCount);
  array(s.sum_rank_by_residue,"sum_rank_by_residue",v);
  const sumLookup=new Array(v).fill(null);
  let expectedI=0,expectedJ=0;
  for(let rank=0;rank<pairCount;rank++){
    const a=object(s.unordered_sums[rank],"sum row");
    if(a.rank!==rank || a.left_index!==expectedI || a.right_index!==expectedJ ||
       a.left!==D[expectedI] || a.right!==D[expectedJ]) fail("sum rows must cover all unordered pairs in lexicographic order");
    integer(a.sum,"sum residue",0,v-1);
    if(a.sum!==(a.left+a.right)%v || sumLookup[a.sum]!==null) fail("invalid or repeated sum residue");
    sumLookup[a.sum]=rank; stats.loaded_sum_rows++; stats.saved_sum_arithmetic_checks++;
    expectedJ++;
    if(expectedJ===k){expectedI++;expectedJ=expectedI;}
  }
  for(let r=0;r<v;r++) if(s.sum_rank_by_residue[r]!==sumLookup[r]) fail("sum index disagrees with saved rows");
  const lift=object(s.positive_lift,"positive_lift"),shift=1-D[0];
  if(lift.translation!==shift || lift.cardinality!==k || lift.endpoint!==D[k-1]+shift) fail("invalid positive lift header");
  array(lift.values,"positive_lift.values",k).forEach((a,i)=>{if(a!==D[i]+shift)fail("invalid positive lift value");});
  const expectedSummary={
    modulus:v,field_prime:q,difference_set_size:k,nonzero_difference_count:v-1,
    unordered_pair_count:pairCount,repeated_summand_pairs:k,represented_sum_residues:pairCount,
    missing_sum_residues:v-pairCount,point_count:v,line_count:v,points_per_line:k,
    lines_per_point:k,total_incidences:v*k,cyclic_sidon_maximum_size:k
  };
  object(s.summary,"summary");
  for(const [key,want] of Object.entries(expectedSummary)) if(s.summary[key]!==want) fail("summary mismatch: "+key);

  function label(x,name){return integer(x,name,0,v-1);}
  function query(kind){stats.queries++;stats[kind]++;}
  function pageBounds(options,size){
    if(options===undefined)options={};
    object(options,"page options");
    const start=options.start===undefined?0:integer(options.start,"page start",0,size);
    const limit=options.limit===undefined?SINGER_PLANE_LIMITS.maximum_page_rows:
      integer(options.limit,"page limit",1,SINGER_PLANE_LIMITS.maximum_page_rows);
    return {start,end:Math.min(size,start+limit),total:size};
  }
  function pageOf(rows,options){
    const b=pageBounds(options,rows.length),records=rows.slice(b.start,b.end);
    stats.page_queries++;stats.page_rows_returned+=records.length;
    return {start:b.start,count:records.length,total:b.total,next_start:b.end<b.total?b.end:null,records:clone(records)};
  }
  function lineRows(line){
    line=label(line,"line");
    const rows=D.map((d,i)=>({point:mod(line+d,v),line,difference_set_index:i,difference_set_value:d}));
    stats.translated_incidence_labels+=k;
    rows.sort((a,b)=>a.point-b.point);
    return rows.map((a,rank)=>({rank,...a}));
  }
  function pencilRows(point){
    point=label(point,"point");
    const rows=D.map((d,i)=>({line:mod(point-d,v),point,difference_set_index:i,difference_set_value:d}));
    stats.translated_incidence_labels+=k;
    rows.sort((a,b)=>a.line-b.line);
    return rows.map((a,rank)=>({rank,...a}));
  }
  function pairAt(rank){
    return s.unordered_sums[integer(rank,"pair rank",0,pairCount-1)];
  }
  function selectIncidence(rows,rank){
    stats.select_queries++;
    return clone(rows[integer(rank,"incidence rank",0,k-1)]);
  }
  function rankIncidence(rows,value,key){
    stats.rank_queries++;
    return rows.findIndex(r=>r[key]===value);
  }
  const api={
    summary(){query("summary_queries");return clone(s.summary);},
    source(){query("summary_queries");return clone(c);},
    differenceSet(){query("summary_queries");return D.slice();},
    traceRow(residue){query("trace_queries");return clone(s.trace_records[label(residue,"residue")]);},
    tracePage(options){query("trace_queries");return pageOf(s.trace_records,options);},
    differenceWitness(residue){
      query("difference_queries");integer(residue,"nonzero difference",1,v-1);return clone(diff[residue]);
    },
    differencePage(options){query("difference_queries");return pageOf(s.ordered_differences,options);},
    incidence(point,line){
      query("incidence_queries");point=label(point,"point");line=label(line,"line");
      const d=mod(point-line,v),i=indexOf.get(d);
      return {point,line,incident:i!==undefined,difference_set_value:d,difference_set_index:i===undefined?null:i};
    },
    join(point1,point2){
      query("join_queries");point1=label(point1,"point1");point2=label(point2,"point2");
      if(point1===point2)fail("join requires distinct points; use pencilPage for all lines through one point");
      const r=mod(point2-point1,v),w=diff[r],line=mod(point1-w.from,v);
      return {points:[point1,point2],line,difference:r,witness:clone(w),
        offsets:[w.from,w.to],unique:true};
    },
    meet(line1,line2){
      query("meet_queries");line1=label(line1,"line1");line2=label(line2,"line2");
      if(line1===line2)fail("meet requires distinct lines; use linePage for all points on one line");
      const r=mod(line2-line1,v),w=diff[r],point=mod(line1+w.to,v);
      return {lines:[line1,line2],point,difference:r,witness:clone(w),
        offsets:[w.to,w.from],unique:true};
    },
    linePage(line,options){query("incidence_queries");return {line:label(line,"line"),...pageOf(lineRows(line),options)};},
    pencilPage(point,options){query("incidence_queries");return {point:label(point,"point"),...pageOf(pencilRows(point),options)};},
    selectPointOnLine(line,rank){query("incidence_queries");return selectIncidence(lineRows(line),rank);},
    rankPointOnLine(line,point){
      query("incidence_queries");point=label(point,"point");const rank=rankIncidence(lineRows(line),point,"point");return rank<0?null:rank;
    },
    selectLineThroughPoint(point,rank){query("incidence_queries");return selectIncidence(pencilRows(point),rank);},
    rankLineThroughPoint(point,line){
      query("incidence_queries");line=label(line,"line");const rank=rankIncidence(pencilRows(point),line,"line");return rank<0?null:rank;
    },
    pairForSum(residue){
      query("pair_queries");residue=label(residue,"sum residue");const rank=sumLookup[residue];
      return {sum:residue,count:rank===null?0:1,representation:rank===null?null:clone(s.unordered_sums[rank])};
    },
    pairPage(options){query("pair_queries");return pageOf(s.unordered_sums,options);},
    selectPair(rank){query("pair_queries");stats.select_queries++;return clone(pairAt(rank));},
    rankPair(pair){
      query("pair_queries");stats.rank_queries++;array(pair,"pair",2);
      const a=label(pair[0],"first summand"),b=label(pair[1],"second summand");
      let i=indexOf.get(a),j=indexOf.get(b);
      if(i===undefined || j===undefined)return null;
      if(i>j){const t=i;i=j;j=t;}
      return i*k-i*(i-1)/2+(j-i);
    },
    positiveLift(){query("positive_lift_queries");return clone(s.positive_lift);},
    snapshot(){return clone(s);},
    statistics(){return clone(stats);}
  };
  return Object.freeze(api);
}

module.exports={
  SINGER_PLANE_LIMITS,
  compileSingerPlaneFromBoseChowla,
  openRetainedSingerPlane
};
