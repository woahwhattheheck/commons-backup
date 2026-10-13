"use strict";

// A finite-to-limit consumer of the saved N=96 dilated-triple family.
// It never calls compile(), reconstructs constraints, or rebuilds base polynomials.
function encloseFromSavedPrefix(openIndex, snapshot, input, record = () => {}) {
  const fail = message => { throw new Error(message); };
  if (typeof openIndex !== "function" || typeof record !== "function") fail("reader and record functions required");
  if (!input || input.schema !== "dilated-triple-density-input/v1") fail("input schema");
  if (!snapshot || snapshot.schema !== "dilated-triple-family/v1" || snapshot.N !== 96 || input.N !== 96) fail("this consumer requires the saved N=96 family");
  const smooth = input.smooth_prefix;
  const coreOne = snapshot.components.find(c => c.core === 1);
  if (!coreOne || !Array.isArray(smooth) || JSON.stringify(smooth) !== JSON.stringify(coreOne.vertices)) fail("core-one prefix mismatch");
  if (smooth.length !== 20 || smooth[0] !== 1 || smooth.at(-1) !== 96) fail("expected twenty-term smooth prefix");
  if (!Number.isSafeInteger(input.decimal_places) || input.decimal_places < 0 || input.decimal_places > 100) fail("decimal precision");
  const degree = id => {
    const node = snapshot.nodes[id];
    const p = node && node.coefficients;
    if (!Array.isArray(p) || p.length === 0 || !/^[1-9][0-9]*$/.test(p.at(-1))) fail("nonempty trimmed saved polynomial required");
    return p.length - 1;
  };
  const reused = new Map();
  for (const component of snapshot.components) {
    const j = component.vertices.length;
    if (reused.has(j)) continue;
    if (j > smooth.length || component.vertices.some((v,i) => v !== component.core * smooth[i])) fail("component is not a scaled smooth prefix");
    const rootDegree = degree(component.root), tailDegree = degree(component.tail_root);
    reused.set(j, {
      maximum_size: rootDegree - tailDegree,
      evidence: {method:"saved_component_degree_difference", component_id:component.id,
        core:component.core, root:component.root, tail_root:component.tail_root,
        root_degree:rootDegree, tail_degree:tailDegree}
    });
  }
  const missing = smooth.map((_,i) => i+1).filter(j => !reused.has(j));
  if (JSON.stringify(missing) !== JSON.stringify(input.new_condition_prefix_sizes)) fail("declared new conditions mismatch");
  if (missing.length > 16) fail("saved-reader condition cap");
  const reader = openIndex(snapshot), prefixRows = [], newQueries = [], reusedRows = [];
  let previous = 0;
  for (let j=1; j<=smooth.length; j++) {
    let maximum, evidence;
    if (reused.has(j)) {
      const saved = reused.get(j);
      maximum = saved.maximum_size;
      evidence = saved.evidence;
      reusedRows.push({prefix_size:j, maximum_size:maximum, ...evidence});
    } else {
      const keep = new Set(smooth.slice(0,j));
      const forbidden = Array.from({length:snapshot.N}, (_,i) => i+1).filter(v => !keep.has(v));
      const query = {op:"family", condition:{required:[], forbidden}};
      const output = reader.query(query);
      const item = {index:newQueries.length, prefix_size:j, query, output, work_after:reader.work()};
      newQueries.push(item);
      record("prefix_query_"+j, item);
      maximum = output.maximum_size;
      evidence = {method:"new_condition_on_saved_diagram", query_index:item.index};
    }
    if (!Number.isSafeInteger(maximum) || maximum < 0 || maximum > j) fail("prefix maximum");
    const increment = maximum - previous;
    if (increment !== 0 && increment !== 1) fail("prefix rank increment");
    prefixRows.push({prefix_size:j, smooth_value:smooth[j-1], maximum_size:maximum, increment, evidence});
    previous = maximum;
  }
  function gcd(a,b) { while (b) { const r=a%b; a=b; b=r; } return a; }
  function rational(n,d=1n) {
    if (d<=0n) fail("positive rational denominator required");
    const g=gcd(n<0n?-n:n,d);
    return {n:n/g,d:d/g};
  }
  function add(a,b) { return rational(a.n*b.d+b.n*a.d,a.d*b.d); }
  function subtract(a,b) { return rational(a.n*b.d-b.n*a.d,a.d*b.d); }
  const pack = a => ({numerator:String(a.n),denominator:String(a.d)});
  let reciprocalSum=rational(0n), weightedIncrementSum=rational(0n);
  for (const row of prefixRows) {
    const reciprocal=rational(1n,BigInt(row.smooth_value));
    reciprocalSum=add(reciprocalSum,reciprocal);
    if (row.increment === 1) weightedIncrementSum=add(weightedIncrementSum,reciprocal);
  }
  const tailReciprocal=subtract(rational(3n),reciprocalSum);
  if (tailReciprocal.n < 0n) fail("negative smooth reciprocal tail");
  const lower=rational(weightedIncrementSum.n,3n*weightedIncrementSum.d);
  const tailAllowance=rational(tailReciprocal.n,3n*tailReciprocal.d);
  const upper=add(lower,tailAllowance);
  const scale=10n**BigInt(input.decimal_places);
  const scaledLower=lower.n*scale/lower.d;
  const scaledUpper=(upper.n*scale+upper.d-1n)/upper.d;
  function decimal(scaled) {
    if (input.decimal_places===0) return String(scaled);
    const s=String(scaled).padStart(input.decimal_places+1,"0");
    return s.slice(0,-input.decimal_places)+"."+s.slice(-input.decimal_places);
  }
  const work=reader.work();
  if (work.queries!==missing.length || work.conditions!==missing.length ||
      work.new_constructor_states!==0 || work.new_factor_divisions!==0 ||
      work.new_constraints!==0 || work.new_base_coefficients!==0) fail("unexpected saved-reader work");
  const result={
    schema:"dilated-triple-density-enclosure/v1",
    input,
    interpretation:"lambda is the limiting maximum density of positive-integer subsets excluding each simultaneous n,2n,3n triple",
    formula:"lambda = (1/3) * sum_{j>=1} (g_j-g_(j-1))/s_j, where s_j enumerates 2^a*3^b",
    prefix_rows:prefixRows,
    reused_prefixes:reusedRows,
    new_prefix_queries:newQueries,
    exact:{
      smooth_reciprocal_prefix:pack(reciprocalSum),
      smooth_reciprocal_tail:pack(tailReciprocal),
      weighted_increment_prefix:pack(weightedIncrementSum),
      lower:pack(lower),
      upper:pack(upper),
      width:pack(tailAllowance)
    },
    decimal:{places:input.decimal_places,lower_floor:decimal(scaledLower),
      upper_ceiling:decimal(scaledUpper),rounding:"outward; inclusive enclosure"},
    work:{reused_prefix_count:reusedRows.length,new_prefix_query_count:newQueries.length,
      rational_prefix_terms:prefixRows.length,decimal_scale_powers:1,saved_reader:work},
    scope:{
      base_family_reconstructed:false,
      previous_queries_replayed:false,
      historical_paper_read:false,
      new_limit_existence_claim:false,
      best_known_bound_claim:false,
      irrationality_claim:false
    }
  };
  record("density_enclosure",result);
  return result;
}

module.exports={encloseFromSavedPrefix};

if (typeof require==="function" && require.main===module) {
  const fs=require("fs"), path=require("path");
  const {openIndex}=require("./dilated_triple_families.cjs");
  const read=name=>JSON.parse(fs.readFileSync(path.join(__dirname,name),"utf8"));
  const result=encloseFromSavedPrefix(openIndex,read("interval96_family_index.json"),read("density_enclosure_input.json"));
  process.stdout.write(JSON.stringify(result,null,2)+"\n");
}
