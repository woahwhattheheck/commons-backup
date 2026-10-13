"use strict";
const SCHEMA="common-factor-difference-index/v1";
function small(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name);return x;}
function dec(s,name){if(typeof s!=="string"||!/^(0|[1-9][0-9]*)$/.test(s))throw new TypeError(name+" decimal string");return BigInt(s);}
function construct(input){
 const limits=Object.assign({max_hosts:16,max_factor_pairs:100000,max_divisor_nodes:1000000,max_zeta_additions:1000000},input.limits||{});
 Object.entries(limits).forEach(([k,v])=>small(v,k,1,Number.MAX_SAFE_INTEGER));
 if(!Array.isArray(input.hosts)||!input.hosts.length||input.hosts.length>limits.max_hosts||input.hosts.length>16)throw new RangeError("host count");
 const work={host_integer_multiplies:0,known_host_values_reused:0,duplicate_host_rows:0,sqrt_divisions:0,sqrt_additions:0,divisor_nodes:0,divisor_bound_divisions:0,divisor_products:0,factor_partner_divisions:0,difference_subtractions:0,factor_pairs:0,support_or_updates:0,support_count_additions:0,zeta_additions:0,subset_size_additions:0,profile_count_additions:0,primality_tests:0,generic_factorizations:0,binomial_valuation_cells:0};
 function sqrt(n){let x=1n<<BigInt(Math.ceil(n.toString(2).length/2));for(;;){const y=(x+n/x)>>1n;++work.sqrt_divisions;++work.sqrt_additions;if(y>=x)return x;x=y;}}
 const map=new Map();
 for(let i=0;i<input.hosts.length;i++){
  const h=input.hosts[i];if(!Array.isArray(h.factors)||!h.factors.length)throw new TypeError("nonempty prime factors");
  h.factors.forEach(([p,e],j)=>{small(p,"prime premise",2,Number.MAX_SAFE_INTEGER);small(e,"positive exponent",1,1000);if(j&&p<=h.factors[j-1][0])throw new RangeError("ordered factors");});
  let N;if(h.known_value!==undefined){N=dec(h.known_value,"known value");if(N<2n)throw new RangeError("host value");++work.known_host_values_reused;}
  else {N=1n;for(const [p,e]of h.factors)for(let j=0;j<e;j++){N*=BigInt(p);++work.host_integer_multiplies;}}
  const key=N.toString(),lineage={input_index:i,source_row_id:h.source_row_id,binomial_n:h.binomial_n,binomial_k:h.binomial_k,known_value_reader_query:h.known_value_reader_query};
  if(map.has(key)){const old=map.get(key);if(JSON.stringify(old.factors)!==JSON.stringify(h.factors))throw new Error("duplicate value with inconsistent factor premises");old.lineage.push(lineage);++work.duplicate_host_rows;}
  else map.set(key,{value:key,factors:h.factors.map(x=>x.slice()),lineage:[lineage],known_value_reused:h.known_value!==undefined});
 }
 const hosts=[...map.values()].sort((a,b)=>BigInt(a.value)<BigInt(b.value)?-1:1),H=hosts.length,M=2**H;
 if(H*M/2>limits.max_zeta_additions)throw new RangeError("zeta cap");
 const differences=new Map();
 for(let hi=0;hi<H;hi++){
  const h=hosts[hi],N=BigInt(h.value),bound=sqrt(N),pairs=[];
  function walk(i,d){
   if(work.divisor_nodes>=limits.max_divisor_nodes)throw new RangeError("divisor node cap");++work.divisor_nodes;
   if(i===h.factors.length){
    if(work.factor_pairs>=limits.max_factor_pairs)throw new RangeError("factor pair cap");
    const b=N/d,difference=b-d;++work.factor_partner_divisions;++work.difference_subtractions;++work.factor_pairs;
    pairs.push({a:d.toString(),b:b.toString(),difference:difference.toString()});return;
   }
   const [p,e]=h.factors[i],prime=BigInt(p);let v=d;
   for(let j=0;j<=e;j++){walk(i+1,v);if(j<e){const allowed=bound/prime;++work.divisor_bound_divisions;if(v>allowed)break;v*=prime;++work.divisor_products;}}
  }
  walk(0,1n);pairs.sort((a,b)=>BigInt(a.a)<BigInt(b.a)?-1:1);h.index=hi;h.sqrt_floor=bound.toString();h.pairs=pairs;h.pair_count=pairs.length;
  for(let pi=0;pi<pairs.length;pi++){
   const d=pairs[pi].difference;if(!differences.has(d))differences.set(d,{difference:d,support_mask:0,occurrences:[]});
   const row=differences.get(d);if(row.support_mask&(1<<hi))throw new Error("duplicate difference in one host");
   row.support_mask|=1<<hi;++work.support_or_updates;row.occurrences.push({host_index:hi,pair_index:pi});
  }
 }
 const diffRows=[...differences.values()].sort((a,b)=>BigInt(a.difference)<BigInt(b.difference)?-1:1),freq=Array(M).fill(0);
 for(let id=0;id<diffRows.length;id++){const r=diffRows[id];r.id=id;++freq[r.support_mask];++work.support_count_additions;for(const o of r.occurrences)hosts[o.host_index].pairs[o.pair_index].difference_id=id;}
 const common=freq.slice();
 for(let bit=0;bit<H;bit++)for(let mask=0;mask<M;mask++)if(!(mask&(1<<bit))){common[mask]+=common[mask|(1<<bit)];++work.zeta_additions;}
 const unionCount=common[0];common[0]=null;
 const sizes=Array(M).fill(0),profiles=new Map(),maxBySize=Array(H+1).fill(null),qualifying=Array(H+1).fill(0);
 for(let mask=1;mask<M;mask++){
  const size=sizes[mask>>1]+(mask&1);sizes[mask]=size;++work.subset_size_additions;
  const c=common[mask],key=size+":"+c;profiles.set(key,(profiles.get(key)||0)+1);++work.profile_count_additions;
  if(maxBySize[size]===null||c>maxBySize[size])maxBySize[size]=c;if(c>=size)++qualifying[size];
 }
 return{schema:SCHEMA,hosts,host_count:H,nonempty_subsets:M-1,subset_order:"increasing numeric host-bit mask; host bits use increasing numerical N",empty_subset:"excluded: the unrestricted empty intersection is infinite",factor_contract:"Complete supplied prime factorizations and any known host value are premises; no primality, factorization or known-value product is rechecked.",
  differences:diffRows,union_difference_count:unionCount,exact_support_counts:freq,common_counts:common,subset_sizes:sizes,
  profiles:[...profiles].map(([key,count])=>{const [size,common_count]=key.split(":").map(Number);return{size,common_count,count};}).sort((a,b)=>a.size-b.size||a.common_count-b.common_count),
  maximum_common_by_size:maxBySize,qualifying_counts_by_size:qualifying,limits,provenance:input.provenance||{},work};
}
function open(s){
 if(!s||s.schema!==SCHEMA||!Array.isArray(s.hosts)||!Array.isArray(s.differences)||!Array.isArray(s.common_counts))throw new TypeError("snapshot");
 const H=s.host_count,F=2**H-1;if(s.hosts.length!==H||s.common_counts.length!==F+1||s.subset_sizes.length!==F+1||s.common_counts[0]!==null)throw new TypeError("snapshot shape");
 const work={queries:0,family_conditions:0,family_cache_hits:0,saved_subset_scans:0,conditional_masks:0,rank_binary_probes:0,subset_host_bit_checks:0,shared_conditions:0,shared_cache_hits:0,support_row_scans:0,shared_ids:0,difference_binary_probes:0,witness_occurrence_checks:0,saved_pair_lookups:0,constructor_calls:0,new_divisors:0,new_differences:0,new_supports:0,new_zeta_cells:0,prime_tests:0,factorizations:0};
 const familyCache=new Map(),sharedCache=new Map();
 function maskValue(mask){return small(mask,"nonempty subset mask",1,F);}
 function subsetCore(mask){maskValue(mask);const hosts=[];for(let i=0;i<H;i++){++work.subset_host_bit_checks;if(mask&(1<<i))hosts.push({index:i,value:s.hosts[i].value});}return{mask,size:s.subset_sizes[mask],common_count:s.common_counts[mask],qualifies:s.common_counts[mask]>=s.subset_sizes[mask],hosts};}
 function normalize(o={}){
  const c={min_size:o.min_size===undefined?1:small(o.min_size,"min_size",1,H),max_size:o.max_size===undefined?H:small(o.max_size,"max_size",1,H),
   min_common:o.min_common===undefined?0:small(o.min_common,"min_common",0,s.union_difference_count),max_common:o.max_common===undefined?s.union_difference_count:small(o.max_common,"max_common",0,s.union_difference_count),
   required_mask:o.required_mask===undefined?0:small(o.required_mask,"required_mask",0,F),forbidden_mask:o.forbidden_mask===undefined?0:small(o.forbidden_mask,"forbidden_mask",0,F),
   qualifies:o.qualifies===undefined?null:o.qualifies};
  if(c.min_size>c.max_size||c.min_common>c.max_common||(c.required_mask&c.forbidden_mask))throw new RangeError("contradictory condition");
  if(c.qualifies!==null&&typeof c.qualifies!=="boolean")throw new TypeError("qualifies Boolean");return c;
 }
 function family(options){
  const c=normalize(options),key=JSON.stringify(c);if(familyCache.has(key)){++work.family_cache_hits;return familyCache.get(key);}
  ++work.family_conditions;const masks=[];
  for(let mask=1;mask<=F;mask++){++work.saved_subset_scans;const k=s.subset_sizes[mask],d=s.common_counts[mask];
   if(k<c.min_size||k>c.max_size||d<c.min_common||d>c.max_common||(mask&c.required_mask)!==c.required_mask||(mask&c.forbidden_mask)||(c.qualifies!==null&&(d>=k)!==c.qualifies))continue;
   masks.push(mask);++work.conditional_masks;
  }
  const out={key,condition:c,count:String(masks.length),masks};familyCache.set(key,out);return out;
 }
 function shared(mask){maskValue(mask);if(sharedCache.has(mask)){++work.shared_cache_hits;return sharedCache.get(mask);}
  ++work.shared_conditions;const ids=[];for(const r of s.differences){++work.support_row_scans;if((r.support_mask&mask)===mask){ids.push(r.id);++work.shared_ids;}}
  if(ids.length!==s.common_counts[mask])throw new Error("saved count and shared query mismatch");
  const out={mask,count:String(ids.length),difference_ids:ids};sharedCache.set(mask,out);return out;
 }
 function witnessRow(row,mask){
  const witnesses=[];for(const o of row.occurrences){++work.witness_occurrence_checks;if(mask&(1<<o.host_index)){++work.saved_pair_lookups;const p=s.hosts[o.host_index].pairs[o.pair_index];witnesses.push({host_index:o.host_index,N:s.hosts[o.host_index].value,pair_index:o.pair_index,a:p.a,b:p.b});}}
  return{id:row.id,difference:row.difference,support_mask:row.support_mask,witnesses};
 }
 function findDifference(d){const value=dec(d,"difference");let lo=0,hi=s.differences.length;while(lo<hi){const m=Math.floor((lo+hi)/2);++work.difference_binary_probes;if(BigInt(s.differences[m].difference)<value)lo=m+1;else hi=m;}return lo<s.differences.length&&s.differences[lo].difference===d?s.differences[lo]:null;}
 return{
  summary(){++work.queries;return{host_count:H,nonempty_subsets:F,union_differences:s.union_difference_count,factor_pairs:s.work.factor_pairs,maximum_common_by_size:s.maximum_common_by_size,qualifying_counts_by_size:s.qualifying_counts_by_size,profiles:s.profiles,order:s.subset_order,construction_work:s.work};},
  hosts(){++work.queries;return s.hosts.map(({pairs,...x})=>x);},
  hostPage(index,start,limit){++work.queries;small(index,"host index",0,H-1);const h=s.hosts[index];small(start,"start",0,h.pairs.length);small(limit,"limit",0,200);const end=Math.min(h.pairs.length,start+limit);work.saved_pair_lookups+=end-start;return{host_index:index,value:h.value,count:h.pairs.length,start,pairs:h.pairs.slice(start,end),next:end,complete:end===h.pairs.length};},
  subset(mask){++work.queries;return subsetCore(mask);},
  family(options){++work.queries;const c=family(options);return{condition:c.condition,count:c.count};},
  select(rank,options){++work.queries;const c=family(options),r=dec(rank,"rank");if(r>=BigInt(c.masks.length))throw new RangeError("rank");return{condition:c.condition,count:c.count,rank,subset:subsetCore(c.masks[Number(r)])};},
  rank(mask,options){++work.queries;maskValue(mask);const c=family(options);let lo=0,hi=c.masks.length;while(lo<hi){const m=Math.floor((lo+hi)/2);++work.rank_binary_probes;if(c.masks[m]<mask)lo=m+1;else hi=m;}const member=c.masks[lo]===mask;return{condition:c.condition,count:c.count,member,rank:member?String(lo):null,subset:subsetCore(mask)};},
  page(start,limit,options){++work.queries;const c=family(options),r=dec(start,"start");small(limit,"limit",0,200);if(r>BigInt(c.masks.length))throw new RangeError("page");const end=Math.min(c.masks.length,Number(r)+limit);return{condition:c.condition,count:c.count,start,subsets:c.masks.slice(Number(r),end).map((mask,j)=>({rank:String(Number(r)+j),subset:subsetCore(mask)})),next_rank:String(end),complete:end===c.masks.length};},
  sharedPage(mask,start,limit){++work.queries;const c=shared(mask);small(start,"start",0,c.difference_ids.length);small(limit,"limit",0,200);const end=Math.min(c.difference_ids.length,start+limit);return{mask,count:c.count,start,rows:c.difference_ids.slice(start,end).map(id=>witnessRow(s.differences[id],mask)),next:end,complete:end===c.difference_ids.length};},
  difference(d){++work.queries;const row=findDifference(d);return row?witnessRow(row,row.support_mask):{difference:d,present:false};},
  witness(mask,d){++work.queries;maskValue(mask);const row=findDifference(d);if(!row||(row.support_mask&mask)!==mask)return{mask,difference:d,member:false,missing_host_mask:row?mask&~row.support_mask:mask};return{mask,member:true,...witnessRow(row,mask)};},
  caches(){return{families:[...familyCache.values()],shared:[...sharedCache.values()]};},
  work(){return Object.assign({},work);}
 };
}
module.exports={SCHEMA,construct,open};
