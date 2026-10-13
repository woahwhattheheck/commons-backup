"use strict";

// Exact finite divisibility placement under the interval convention (m,m+W].
// Classical matching/Hall certificates and the Erdős-Pomerance period are credited in the guide.

const PLACEMENT_LIMITS = Object.freeze({
  n: 128, m_decimal_digits: 256, width: 4096, period_residues: 32768,
  divisor_checks: 16777216, alternating_edge_visits: 33554432, page_size: 256
});

function placeInt(x, name, low, high) {
  if (!Number.isSafeInteger(x) || x < low || x > high) {
    throw new RangeError(name + " must be a safe integer in [" + low + "," + high + "]");
  }
  return x;
}
function placeId(x) {
  if (typeof x !== "string" || !x.trim() || x.length > 512) throw new TypeError("source_id must be a nonempty string of at most 512 code units");
  return x;
}
function placePositive(x, name) {
  let v;
  if (typeof x === "bigint") v = x;
  else if (typeof x === "number" && Number.isSafeInteger(x)) v = BigInt(x);
  else if (typeof x === "string" && /^[1-9][0-9]*$/.test(x) && x.length <= PLACEMENT_LIMITS.m_decimal_digits) v = BigInt(x);
  else throw new TypeError(name + " must be a positive BigInt, safe integer or canonical decimal string");
  if (v <= 0n || v.toString().length > PLACEMENT_LIMITS.m_decimal_digits) throw new RangeError(name + " is outside the positive 256-digit input contract");
  return v;
}
function placeGcd(a,b) { while (b) { const t=a%b; a=b; b=t; } return a; }
function placeCopy(x) { return JSON.parse(JSON.stringify(x)); }
function placeMask(ids) { let m=0n; for (const id of ids) m |= 1n << BigInt(id-1); return m.toString(16); }
function placeMaskIds(hex, size) {
  const value=BigInt("0x"+hex), out=[];
  for (let id=1;id<=size;id++) if ((value&(1n<<BigInt(id-1)))!==0n) out.push(id);
  return out;
}
function placePeriod(n) {
  let period=1; const steps=[];
  for (let k=1;k<=n;k++) {
    const g=placeGcd(period,k), next=(period/g)*k;
    if (next>PLACEMENT_LIMITS.period_residues) {
      const e=new RangeError("the complete residue period exceeds "+PLACEMENT_LIMITS.period_residues);
      e.name="PlacementPeriodLimitError";
      e.details={n,first_exceeding_divisor:k,partial_period:period,next_period:next};
      throw e;
    }
    steps.push({divisor:k,previous_period:period,gcd:g,next_period:next});
    period=next;
  }
  return {period,steps};
}
function placeWork() {
  return {divisor_checks:0,incidence_edges_generated:0,alternating_edge_visits:0,
    successful_augmentations:0,hall_edge_visits:0,positions_processed:0,completed_instances:0};
}
function placeBudget(request) {
  const value=request===undefined?{}:request;
  if (!value || typeof value!=="object" || Array.isArray(value)) throw new TypeError("budget must be an object");
  const out={};
  for (const key of ["divisor_checks","alternating_edge_visits"]) {
    out[key]=placeInt(value[key]===undefined?PLACEMENT_LIMITS[key]:value[key],"budget."+key,1,PLACEMENT_LIMITS[key]);
  }
  for (const key of Object.keys(value)) if (!(key in out)) throw new TypeError("unknown budget field: "+key);
  return out;
}

// New right vertices arrive in order. Each successful alternating path raises a
// maximum matching by one; a failure leaves the previous maximum unchanged.
function placeCore(n, residues, maxWidth, work, budget) {
  const leftMatch=Array(n+1).fill(0), rightMatch=[0];
  const leftEdges=Array.from({length:n+1},()=>[]), rightEdges=[[]];
  const next=Array(n+1).fill(0);
  for (let k=1;k<=n;k++) next[k]=k-residues[k];
  let matched=0, completeWidth=0;
  function stopped(kind, width, extra) {
    return {status:"RESOURCE_LIMIT",resource_stop:{kind,generated_width:width,complete_width:completeWidth,...extra},
      maximum_matching_size_at_complete_width:matched,
      partial_graph:{left_match:leftMatch.slice(1),right_match:rightMatch.slice(1),
        neighbors_by_offset:rightEdges.slice(1)},max_width:maxWidth};
  }
  for (let width=1;width<=maxWidth;width++) {
    if (work.divisor_checks+n>budget.divisor_checks) return stopped("divisor_checks",width-1,{limit:budget.divisor_checks});
    const adjacent=[];
    for (let k=n;k>=1;k--) {
      work.divisor_checks++;
      if (next[k]===width) {
        adjacent.push(k); leftEdges[k].push(width); next[k]+=k; work.incidence_edges_generated++;
      }
    }
    rightEdges.push(adjacent); rightMatch.push(0);
    const seenLeft=Array(n+1).fill(false), seenRight=Array(width+1).fill(false);
    const parentLeft=Array(n+1).fill(0), queue=[width];
    seenRight[width]=true;
    let free=0;
    for (let head=0;head<queue.length && free===0;head++) {
      const right=queue[head];
      for (const k of rightEdges[right]) {
        if (work.alternating_edge_visits>=budget.alternating_edge_visits) {
          return stopped("alternating_edge_visits",width,{limit:budget.alternating_edge_visits});
        }
        work.alternating_edge_visits++;
        if (seenLeft[k]) continue;
        seenLeft[k]=true; parentLeft[k]=right;
        if (leftMatch[k]===0) { free=k; break; }
        const mate=leftMatch[k];
        if (!seenRight[mate]) { seenRight[mate]=true; queue.push(mate); }
      }
    }
    if (free!==0) {
      const beforeLeft=matched===n-1?leftMatch.slice():null;
      const beforeRight=matched===n-1?rightMatch.slice():null;
      let k=free;
      while (k!==0) {
        const right=parentLeft[k], previous=rightMatch[right];
        leftMatch[k]=right; rightMatch[right]=k; k=previous;
      }
      matched++; work.successful_augmentations++;
      if (matched===n) {
        // Alternating reachability from every unmatched left vertex in width-1
        // gives a Hall set. The just-arrived right vertex is excluded.
        const hallLeft=Array(n+1).fill(false), hallRight=Array(width).fill(false), q=[];
        for (let i=1;i<=n;i++) if (beforeLeft[i]===0) {hallLeft[i]=true;q.push(i);}
        for (let head=0;head<q.length;head++) {
          for (const right of leftEdges[q[head]]) {
            if (right>=width) continue;
            work.hall_edge_visits++;
            if (hallRight[right]) continue;
            hallRight[right]=true;
            const mate=beforeRight[right];
            if (mate===0) throw new Error("internal maximum-matching invariant failed while extracting Hall obstruction");
            if (!hallLeft[mate]) {hallLeft[mate]=true;q.push(mate);}
          }
        }
        const divisors=[], neighbors=[];
        for (let i=1;i<=n;i++) if (hallLeft[i]) divisors.push(i);
        for (let j=1;j<width;j++) if (hallRight[j]) neighbors.push(j);
        if (divisors.length-neighbors.length!==1) throw new Error("internal Hall-deficiency invariant failed");
        work.positions_processed++; work.completed_instances++;
        return {status:"EXACT_MINIMUM_WIDTH",width,assignment_offsets:leftMatch.slice(1),
          hall_divisors:divisors,hall_neighbor_offsets:neighbors,
          previous_maximum_matching_size:n-1,
          compact_record:[width,leftMatch.slice(1),placeMask(divisors),placeMask(neighbors)]};
      }
    }
    completeWidth=width; work.positions_processed++;
  }
  return stopped("width",maxWidth,{limit:maxWidth});
}

function expandPlacementRecord(n,m,row,provenance) {
  const width=row[0], offsets=row[1], divisors=placeMaskIds(row[2],n), neighbors=placeMaskIds(row[3],width-1);
  const assignment=offsets.map((offset,i)=> {
    const divisor=i+1,value=m+BigInt(offset);
    return {divisor,offset,value:value.toString(),quotient:(value/BigInt(divisor)).toString()};
  });
  return {schema:"divisibility_placement.point/v1",status:"EXACT_MINIMUM_WIDTH",n,m:m.toString(),width,
    interval:{left_excluded:m.toString(),right_included:(m+BigInt(width)).toString()},
    open_right_integer_width:width+1,assignment,
    hall_obstruction:{failed_width:width-1,divisors,neighbor_offsets:neighbors,
      neighbor_values:neighbors.map(offset=>(m+BigInt(offset)).toString()),
      deficiency:divisors.length-neighbors.length,
      complete_neighbor_progressions:divisors.map(divisor=>{
        const first=divisor-Number(m%BigInt(divisor)), end=width-1;
        return {divisor,first_positive_offset:first,step:divisor,
          hits_through_failed_width:first>end?0:Math.floor((end-first)/divisor)+1};
      })},
    provenance,finite_n_only:true,general_asymptotic_claim:false};
}

function solveDivisibilityPlacement(request) {
  if (!request || typeof request!=="object" || Array.isArray(request)) throw new TypeError("request must be an object");
  const sourceId=placeId(request.source_id),n=placeInt(request.n,"n",1,PLACEMENT_LIMITS.n);
  const m=placePositive(request.m,"m"), budget=placeBudget(request.budget);
  const maxWidth=placeInt(request.max_width===undefined?Math.min(n*n,PLACEMENT_LIMITS.width):request.max_width,
    "max_width",1,PLACEMENT_LIMITS.width);
  const residues=Array(n+1).fill(0);
  for (let k=1;k<=n;k++) residues[k]=Number(m%BigInt(k));
  const work=placeWork(), result=placeCore(n,residues,maxWidth,work,budget);
  if (result.status!=="EXACT_MINIMUM_WIDTH") return {...result,n,m:m.toString(),source_id:sourceId,work,budget};
  return {...expandPlacementRecord(n,m,result.compact_record,{kind:"computed_in_this_call",source_id:sourceId}),
    compact_record:result.compact_record,work,budget};
}

function compileDivisibilityPlacementPeriod(request) {
  if (!request || typeof request!=="object" || Array.isArray(request)) throw new TypeError("request must be an object");
  const sourceId=placeId(request.source_id), n=placeInt(request.n,"n",1,PLACEMENT_LIMITS.n);
  const {period,steps}=placePeriod(n),budget=placeBudget(request.budget),work=placeWork();
  const records=[], histogram=new Map(); let sum=0,min=Infinity,max=-Infinity; const maxResidues=[];
  const base={schema:"divisibility_placement.period/v1",source_id:sourceId,n,period,
    representative_rule:"row r uses positive m=period+r; it applies to all positive m congruent to r modulo period",
    interval_convention:"(m,m+width]",lcm_steps:steps,
    record_columns:["width","assignment_offsets_by_divisor_1_through_n","hall_divisor_mask_hex","hall_neighbor_offset_mask_hex"],
    mask_convention:"bit i-1 denotes positive divisor or positive offset i; lowercase hex without prefix",
    limits:PLACEMENT_LIMITS,budget};
  for (let residue=0;residue<period;residue++) {
    const residues=Array(n+1).fill(0);
    for (let k=1;k<=n;k++) residues[k]=residue%k;
    const result=placeCore(n,residues,Math.min(n*n,PLACEMENT_LIMITS.width),work,budget);
    if (result.status!=="EXACT_MINIMUM_WIDTH") {
      return {...base,status:"PARTIAL_PERIOD",records,completed_residues:records.length,next_residue:residue,
        partial_point:{m:String(period+residue),...result},work,
        exact_period_maximum_claimed:false};
    }
    records.push(result.compact_record);const width=result.width;
    histogram.set(width,(histogram.get(width)||0)+1);sum+=width;min=Math.min(min,width);
    if (width>max) {max=width;maxResidues.length=0;maxResidues.push(residue);}
    else if (width===max) maxResidues.push(residue);
  }
  const g=placeGcd(sum,period),diagonal=records[n%period][0];
  return {...base,status:"EXACT_PERIODIC_TABLE",records,completed_residues:period,next_residue:null,
    summary:{minimum_width:min,maximum_width:max,width_histogram:Array.from(histogram).sort((a,b)=>a[0]-b[0]),
      sum_widths:sum,mean_width:{numerator:sum/g,denominator:period/g},
      diagonal_width:diagonal,diagonal_endpoint:n+diagonal,max_minus_diagonal_width:max-diagonal,
      maximizing_residue_count:maxResidues.length},
    maximizing_residues:maxResidues,work,exact_period_maximum_claimed:true,
    general_asymptotic_claim:false,source_identity_authenticated:false};
}

// Structural premise loader: no matching, incidence union, or period search is replayed.
function openRetainedPlacementPeriod(request) {
  if (!request || typeof request!=="object" || Array.isArray(request)) throw new TypeError("request must be an object");
  const sourceId=placeId(request.source_id),raw=request.snapshot;
  if (!raw || raw.schema!=="divisibility_placement.period/v1" || raw.status!=="EXACT_PERIODIC_TABLE") {
    throw new TypeError("a complete retained periodic table is required");
  }
  const n=placeInt(raw.n,"retained n",1,PLACEMENT_LIMITS.n);
  const period=placeInt(raw.period,"retained period",1,PLACEMENT_LIMITS.period_residues);
  if (!Array.isArray(raw.records) || raw.records.length!==period) throw new TypeError("retained period rows are incomplete");
  for (const row of raw.records) {
    if (!Array.isArray(row) || row.length!==4) throw new TypeError("invalid compact record shape");
    const width=placeInt(row[0],"retained width",n,PLACEMENT_LIMITS.width);
    if (!Array.isArray(row[1]) || row[1].length!==n || new Set(row[1]).size!==n) throw new TypeError("retained assignment offsets must be distinct");
    for (const offset of row[1]) placeInt(offset,"assignment offset",1,width);
    for (const [value,size] of [[row[2],n],[row[3],width-1]]) {
      if (typeof value!=="string" || value.length>Math.max(1,Math.ceil(size/4)) ||
          !/^(0|[1-9a-f][0-9a-f]*)$/.test(value) || BigInt("0x"+value)>=(1n<<BigInt(size))) {
        throw new TypeError("invalid retained Hall mask");
      }
    }
  }
  if (!Array.isArray(raw.maximizing_residues) || !raw.summary) throw new TypeError("retained maximum summary is missing");
  let previous=-1;
  for (const residue of raw.maximizing_residues) {
    placeInt(residue,"maximizing residue",0,period-1);
    if (residue<=previous) throw new TypeError("maximizing residues must be strictly increasing");
    previous=residue;
  }
  const snapshot=placeCopy(raw);
  const provenance={kind:"retained_period_premise",source_id:sourceId,structural_checks:true,
    source_identity_authenticated:false,lcm_recomputed:false,matching_search_replayed:false,
    hall_neighbor_unions_recomputed:false,summary_recomputed:false};
  function lookup(value) {
    const m=placePositive(value,"m"),residue=Number(m%BigInt(period));
    return {...expandPlacementRecord(n,m,snapshot.records[residue],provenance),
      residue,period,source_row:residue};
  }
  function maximizingResiduePage(request={}) {
    const start=placeInt(request.start_index===undefined?0:request.start_index,"start_index",0,snapshot.maximizing_residues.length);
    const limit=placeInt(request.limit===undefined?64:request.limit,"limit",0,PLACEMENT_LIMITS.page_size);
    const residues=snapshot.maximizing_residues.slice(start,start+limit),next=start+residues.length;
    return {start_index:start,total:snapshot.maximizing_residues.length,residues,
      next_index:next<snapshot.maximizing_residues.length?next:null};
  }
  return Object.freeze({lookup,maximizingResiduePage,
    describe:()=>({schema:"divisibility_placement.period_summary/v1",n,period,status:snapshot.status,
      source_id:snapshot.source_id,summary:placeCopy(snapshot.summary),provenance:placeCopy(provenance)}),
    snapshot:()=>placeCopy(snapshot)});
}


// Compose explicitly identified row shards in their declared residue order.
// Identifiers are equality labels, not content hashes or authentication.
function assembleRetainedPlacementPeriod(request) {
  if (!request || typeof request!=="object" || Array.isArray(request)) throw new TypeError("request must be an object");
  const manifest=request.manifest,shards=request.shards;
  if (!manifest || manifest.schema!=="divisibility_placement.period_manifest/v1" ||
      !manifest.header || manifest.header.schema!=="divisibility_placement.period/v1" ||
      manifest.header.status!=="EXACT_PERIODIC_TABLE") throw new TypeError("a complete period manifest is required");
  const n=placeInt(manifest.header.n,"manifest n",1,PLACEMENT_LIMITS.n);
  const period=placeInt(manifest.header.period,"manifest period",1,PLACEMENT_LIMITS.period_residues);
  if (!Array.isArray(manifest.row_shards) || !manifest.row_shards.length || manifest.row_shards.length>32 ||
      !Array.isArray(shards) || shards.length!==manifest.row_shards.length) throw new TypeError("all declared row shards are required");
  const supplied=new Map();
  for (const shard of shards) {
    if (!shard || shard.schema!=="divisibility_placement.period_rows/v1") throw new TypeError("invalid shard schema");
    placeId(shard.source_id);
    if (supplied.has(shard.source_id)) throw new TypeError("duplicate supplied shard identifier");
    supplied.set(shard.source_id,shard);
  }
  const records=[],sources=[];let cursor=0;
  for (const item of manifest.row_shards) {
    placeId(item.source_id);
    if (item.start_residue!==cursor) throw new TypeError("declared shards must be contiguous and ordered from residue zero");
    const count=placeInt(item.row_count,"shard row_count",1,period);
    const shard=supplied.get(item.source_id);
    if (!shard || shard.n!==n || shard.period!==period || shard.start_residue!==cursor ||
        shard.row_count!==count || !Array.isArray(shard.records) || shard.records.length!==count) {
      throw new TypeError("missing or inconsistent row-shard premise");
    }
    if (cursor+count>period) throw new RangeError("row shards exceed the declared period");
    records.push(...shard.records);sources.push(item.source_id);
    supplied.delete(item.source_id);cursor+=count;
  }
  if (cursor!==period || supplied.size) throw new TypeError("row shards do not cover exactly the full period");
  return {snapshot:placeCopy({...manifest.header,records}),
    assembly:{row_count:cursor,shard_source_ids:sources,source_identifiers_authenticated:false,
      matching_search_replayed:false,hall_neighbor_unions_recomputed:false}};
}

module.exports={solveDivisibilityPlacement,compileDivisibilityPlacementPeriod,
  openRetainedPlacementPeriod,assembleRetainedPlacementPeriod,PLACEMENT_LIMITS};
