"use strict";

// Exact append-only navigation conditional on a supplied finite B3 premise.
// Repetitions are allowed in each triple; equality identifies multisets.
const LIMITS = Object.freeze({
  max_seed_size:24, max_integer_digits:1024, max_candidate_pairs:1000000,
  max_forbidden_rows:200000, max_snapshot_chars:12000000, max_page_size:64
});
const SCHEMA="erdos41.b3_append_index/v1";
function fail(s){throw new Error("b3_append_index: "+s);}
function integer(v,label){
  if(typeof v==="number"){if(!Number.isSafeInteger(v))fail(label+" must be an exact integer");v=String(v);}
  else if(typeof v==="bigint")v=String(v);
  if(typeof v!=="string"||!/^(0|[1-9][0-9]*)$/.test(v)||v.length>LIMITS.max_integer_digits)
    fail(label+" must be a canonical nonnegative integer within the digit limit");
  return BigInt(v);
}
function num(v,max,label){if(!Number.isSafeInteger(v)||v<0||v>max)fail(label+" out of range");return v;}
function copy(v){return JSON.parse(JSON.stringify(v));}
function seedInput(values){
  if(!Array.isArray(values)||values.length<1||values.length>LIMITS.max_seed_size)fail("nonempty seed size out of range");
  const b=values.map((x,i)=>integer(x,"seed["+i+"]"));
  for(let i=1;i<b.length;i++)if(b[i]<=b[i-1])fail("seed must be strictly increasing");
  return b;
}
function sourceId(v){if(typeof v!=="string"||!v.length||v.length>2048)fail("premise_id must identify the supplied B3 premise");return v;}
function compileAppendIndex(values,options={}){
  const b=seedInput(values), n=b.length, premise=sourceId(options.premise_id);
  if(String(3n*b[n-1]).length>LIMITS.max_integer_digits)fail("three-sum digit budget exceeded before construction");
  const pairCount=n*(n+1)/2, tripleCount=n*(n+1)*(n+2)/6;
  const candidateCount=tripleCount*(pairCount+n);
  if(candidateCount>LIMITS.max_candidate_pairs)fail("candidate budget exceeded before construction");
  const work={seed_values_read:n,pair_rows_constructed:0,triple_rows_constructed:0,
    one_new_candidates:0,two_new_candidates:0,one_new_above_max:0,
    two_new_odd_differences:0,two_new_integral_at_or_below_max:0,two_new_above_max:0,
    forbidden_rows_inserted:0,duplicate_candidate_hits:0,allowed_gaps_constructed:0,
    inherited_B3_checks:0,field_operations:0,source_decoder_calls:0};
  const pairs=[],triples=[],ps=[],ts=[];
  for(let i=0;i<n;i++)for(let j=i;j<n;j++){
    const s=b[i]+b[j];ps.push(s);pairs.push({indices:[i,j],sum:String(s)});work.pair_rows_constructed++;
  }
  for(let i=0;i<n;i++)for(let j=i;j<n;j++)for(let k=j;k<n;k++){
    const s=b[i]+b[j]+b[k];ts.push(s);triples.push({indices:[i,j,k],sum:String(s)});work.triple_rows_constructed++;
  }
  const M=b[n-1], min=b[0], ceiling=3n*M-2n*min, map=new Map();
  function hit(a,family,t,other){
    const key=String(a);let row=map.get(key);
    if(!row){
      if(map.size>=LIMITS.max_forbidden_rows)fail("forbidden-row budget exceeded");
      row={value:key,one_new_count:0,two_new_count:0,witness:{new_copies:family,triple_row:t,
        pair_row:family===1?other:null,seed_index:family===2?other:null}};
      map.set(key,row);work.forbidden_rows_inserted++;
    }else work.duplicate_candidate_hits++;
    if(family===1)row.one_new_count++;else row.two_new_count++;
  }
  for(let t=0;t<triples.length;t++){
    for(let p=0;p<pairs.length;p++){
      work.one_new_candidates++;const a=ts[t]-ps[p];
      if(a>M){work.one_new_above_max++;hit(a,1,t,p);}
    }
    for(let j=0;j<n;j++){
      work.two_new_candidates++;const d=ts[t]-b[j];
      if(d%2n!==0n){work.two_new_odd_differences++;continue;}
      const a=d/2n;
      if(a>M){work.two_new_above_max++;hit(a,2,t,j);}
      else work.two_new_integral_at_or_below_max++;
    }
  }
  const forbidden=Array.from(map.values()).sort((a,c)=>BigInt(a.value)<BigInt(c.value)?-1:1);
  const gaps=[];let cursor=M+1n,total=0n;
  for(const row of forbidden){
    const a=BigInt(row.value);
    if(cursor<a){const length=a-cursor;gaps.push({lo:String(cursor),hi:String(a-1n),
      rank_start:String(total),length:String(length)});total+=length;work.allowed_gaps_constructed++;}
    cursor=a+1n;
  }
  const snapshot={schema:SCHEMA,premise_id:premise,seed:b.map(String),
    pair_rows:pairs,triple_rows:triples,forbidden,allowed_gaps:gaps,
    finite_allowed_count:String(total),tail_start:String(cursor),
    universal_safe_above:String(ceiling),work,
    premise_boundary:"The seed B3 property is supplied, not checked. Sum rows are production data, not a uniqueness verification.",
    witness_order:"First encountered: triple rows lexicographic, then one-new pairs lexicographic before two-new single indices.",
    family_boundary:"Each allowed value is an independent one-element append to the same seed; allowed values are not mutually certified."};
  const text=JSON.stringify(snapshot);if(text.length>LIMITS.max_snapshot_chars)fail("snapshot size budget exceeded");
  return snapshot;
}
function openAppendIndex(input){
  let s;
  if(typeof input==="string"){if(input.length>LIMITS.max_snapshot_chars)fail("snapshot size exceeded");s=JSON.parse(input);}
  else {const t=JSON.stringify(input);if(t.length>LIMITS.max_snapshot_chars)fail("snapshot size exceeded");s=JSON.parse(t);}
  if(!s||s.schema!==SCHEMA)fail("snapshot schema mismatch");
  const b=seedInput(s.seed),n=b.length,M=b[n-1];sourceId(s.premise_id);
  const stats={structural_pair_rows:0,structural_triple_rows:0,structural_forbidden_rows:0,
    structural_gap_rows:0,binary_comparisons:0,queries:0,selected_values:0,witness_rows:0,
    pair_rows_constructed:0,triple_rows_constructed:0,candidate_pairs_replayed:0,
    inherited_B3_checks:0,field_operations:0};
  if(!Array.isArray(s.pair_rows)||s.pair_rows.length!==n*(n+1)/2||
     !Array.isArray(s.triple_rows)||s.triple_rows.length!==n*(n+1)*(n+2)/6)fail("sum-table dimensions");
  function rows(a,len){
    for(const r of a){
      if(!r||!Array.isArray(r.indices)||r.indices.length!==len)fail("sum-row structure");
      let old=-1;
      for(const x of r.indices){num(x,n-1,"sum index");if(x<old)fail("unordered sum indices");old=x;}
      integer(r.sum,"saved sum");
    }
  }
  rows(s.pair_rows,2);rows(s.triple_rows,3);
  stats.structural_pair_rows=s.pair_rows.length;stats.structural_triple_rows=s.triple_rows.length;
  if(!Array.isArray(s.forbidden)||s.forbidden.length>LIMITS.max_forbidden_rows)fail("forbidden dimensions");
  const f=[];let old=M;
  for(const r of s.forbidden){
    const a=integer(r.value,"forbidden value");if(a<=old)fail("forbidden ordering");old=a;f.push(a);
    num(r.one_new_count,LIMITS.max_candidate_pairs,"one-new count");
    num(r.two_new_count,LIMITS.max_candidate_pairs,"two-new count");
    if(r.one_new_count+r.two_new_count===0)fail("empty obstruction row");
    const w=r.witness;if(!w||(w.new_copies!==1&&w.new_copies!==2))fail("witness structure");
    num(w.triple_row,s.triple_rows.length-1,"triple reference");
    if(w.new_copies===1){num(w.pair_row,s.pair_rows.length-1,"pair reference");if(w.seed_index!==null)fail("unused seed reference");}
    else {num(w.seed_index,n-1,"seed reference");if(w.pair_row!==null)fail("unused pair reference");}
    stats.structural_forbidden_rows++;
  }
  const ceiling=integer(s.universal_safe_above,"safe ceiling");
  if(ceiling<M||old>ceiling)fail("safe ceiling range");
  const tail=integer(s.tail_start,"tail"),total=integer(s.finite_allowed_count,"finite count");
  if(tail!==old+1n)fail("tail endpoint");
  if(!Array.isArray(s.allowed_gaps)||s.allowed_gaps.length>f.length+1)fail("gap dimensions");
  const gaps=[];let priorHi=M,priorEnd=0n,covered=0n;
  for(const g of s.allowed_gaps){
    const lo=integer(g.lo,"gap lo"),hi=integer(g.hi,"gap hi"),start=integer(g.rank_start,"gap rank"),length=integer(g.length,"gap length");
    if(lo<=priorHi||hi<lo||hi>=tail||length!==hi-lo+1n||start!==priorEnd)fail("gap structural relation");
    gaps.push({lo,hi,start,length});priorHi=hi;priorEnd+=length;covered+=length;stats.structural_gap_rows++;
  }
  if(covered!==total||total+BigInt(f.length)!==tail-M-1n)fail("saved partition size");
  // This loader checks structure and saved dimensions, not arithmetic provenance,
  // sum-table completeness, obstruction completeness, or gap-set authentication.
  function lower(a,strict=false){
    let lo=0,hi=f.length;while(lo<hi){const mid=(lo+hi)>>1;stats.binary_comparisons++;
      if(f[mid]<a||(strict&&f[mid]===a))lo=mid+1;else hi=mid;}return lo;
  }
  function countRaw(a){if(a<=M)return 0n;return a-M-BigInt(lower(a,true));}
  function selectRaw(rank){
    if(rank>=total)return tail+(rank-total);
    let lo=0,hi=gaps.length;while(lo<hi){const mid=(lo+hi)>>1;stats.binary_comparisons++;
      if(gaps[mid].start+gaps[mid].length<=rank)lo=mid+1;else hi=mid;}
    if(lo===gaps.length)fail("saved rank gap missing");return gaps[lo].lo+rank-gaps[lo].start;
  }
  function witness(i){
    const r=s.forbidden[i],w=r.witness,t=s.triple_rows[w.triple_row],a=r.value;
    const lhs=w.new_copies===1?[a,...s.pair_rows[w.pair_row].indices.map(j=>s.seed[j])]:
      [a,a,s.seed[w.seed_index]];
    lhs.sort((x,y)=>BigInt(x)<BigInt(y)?-1:BigInt(x)>BigInt(y)?1:0);
    stats.witness_rows++;
    return {value:a,new_copies:w.new_copies,left:lhs,right:t.indices.map(j=>s.seed[j]),
      common_sum:t.sum,saved_reference:copy(w),one_new_count:r.one_new_count,two_new_count:r.two_new_count,
      arithmetic_rechecked:false};
  }
  function classifyRaw(a){
    if(a<=M)return {value:String(a),status:"OUTSIDE_APPEND_DOMAIN",minimum_append:String(M+1n)};
    const i=lower(a);if(i<f.length&&f[i]===a)return {value:String(a),status:"FORBIDDEN",obstruction_index:i,witness:witness(i)};
    return {value:String(a),status:"ALLOWED",rank:String(countRaw(a)-1n),
      certificate_basis:a>ceiling?"universal bound":"complete saved obstruction complement"};
  }
  const api={
    summary(){stats.queries++;return {schema:SCHEMA,premise_id:s.premise_id,seed:s.seed.slice(),
      size:n,maximum:String(M),pair_rows:s.pair_rows.length,triple_rows:s.triple_rows.length,
      forbidden_values:f.length,finite_allowed_count:String(total),finite_allowed_gaps:gaps.length,
      tail_start:String(tail),universal_safe_above:String(ceiling),first_allowed:String(selectRaw(0n)),
      conditional_on_seed_B3:true,independent_single_appends:true};},
    classify(value){stats.queries++;return classifyRaw(integer(value,"append"));},
    countThrough(value){stats.queries++;const a=integer(value,"bound");return {bound:String(a),allowed:String(countRaw(a)),domain_lower:String(M+1n)};},
    rank(value){stats.queries++;const a=integer(value,"append"),c=classifyRaw(a);
      return {value:String(a),member:c.status==="ALLOWED",rank:c.status==="ALLOWED"?c.rank:null,
        insertion_rank:String(a<=M?0n:countRaw(a-1n)),status:c.status};},
    select(rank){stats.queries++;const r=integer(rank,"rank"),a=selectRaw(r);stats.selected_values++;
      return {rank:String(r),value:String(a)};},
    page(start,count=32){stats.queries++;const r=integer(start,"page rank");num(count,LIMITS.max_page_size,"page count");
      const values=[];for(let i=0;i<count;i++){values.push(String(selectRaw(r+BigInt(i))));stats.selected_values++;}
      return {start_rank:String(r),values,next_rank:String(r+BigInt(count))};},
    forbiddenPage(start=0,count=32){stats.queries++;num(start,f.length,"forbidden start");num(count,LIMITS.max_page_size,"page count");
      const end=Math.min(start+count,f.length),rows=[];for(let i=start;i<end;i++)rows.push(witness(i));
      return {start,rows,next_index:end,end:end===f.length};},
    appendCertificate(value){stats.queries++;const a=integer(value,"append"),c=classifyRaw(a);
      if(c.status!=="ALLOWED")return {status:"NOT_APPENDED",classification:c};
      return {status:"CERTIFIED_CONDITIONAL_B3_APPEND",value:String(a),rank:c.rank,
        seed_premise_id:s.premise_id,enlarged_values:[...s.seed,String(a)],
        cardinality:n+1,unordered_triples_with_repetition:(n+1)*(n+2)*(n+3)/6,
        certificate_basis:c.certificate_basis,original_B3_rechecked:false,new_triples_enumerated:0,
        scope:"This one appended value only; no simultaneous extension by other allowed values."};},
    sourceRows(kind,start=0,count=32){stats.queries++;const a=kind==="pairs"?s.pair_rows:kind==="triples"?s.triple_rows:null;
      if(!a)fail("sourceRows kind must be pairs or triples");num(start,a.length,"source row start");num(count,LIMITS.max_page_size,"page count");
      const end=Math.min(start+count,a.length);return {kind,start,rows:copy(a.slice(start,end)),next_index:end,end:end===a.length};},
    stats(){return copy(stats);},
    snapshot(){return copy(s);}
  };
  return Object.freeze(api);
}
module.exports={LIMITS,compileAppendIndex,openAppendIndex};
