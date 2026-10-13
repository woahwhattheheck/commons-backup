"use strict";
const SCHEMA="selected-prime-binary-minima/v1";
function small(x,name,min,max){if(!Number.isSafeInteger(x)||x<min||x>max)throw new RangeError(name);return x;}
function decimal(x,name){if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x))throw new TypeError(name+" must be nonnegative decimal");return BigInt(x);}
function construct(input){
 const B=small(input.bit_length,"bit_length",4,160),L=small(input.low_bits,"low_bits",2,8),base=2**L,K=B-L;
 if(K<2)throw new RangeError("at least two high bits");
 const primes=input.primes;
 if(!Array.isArray(primes)||primes.length<1||primes.length>16)throw new RangeError("prime count");
 primes.forEach((p,i)=>{small(p,"prime premise",2,base-1);if(i&&p<=primes[i-1])throw new RangeError("ordered prime premises");});
 const limits=Object.assign({max_blocks:10000,max_pascal_cells:20000,max_histogram_additions:1000000},input.limits||{});
 Object.keys(limits).forEach(k=>small(limits[k],k,1,Number.MAX_SAFE_INTEGER));
 const F=K-2;
 if(base*K>limits.max_blocks)throw new RangeError("block cap");
 if((F+1)*(F+3)>limits.max_pascal_cells)throw new RangeError("Pascal/cumulative cap");
 const work={low_popcount_cells:0,low_popcount_additions:0,low_prime_records:0,low_subtractions:0,low_wrap_additions:0,
  pascal_cells:0,pascal_additions:0,cumulative_cells:0,cumulative_additions:0,blocks:0,borrow_cost_add_subtract_steps:0,
  histogram_additions:0,mask_histogram_additions:0,total_additions:0,primality_tests:0,integer_enumerations:0};
 const pc=[0];++work.low_popcount_cells;
 for(let x=1;x<base;x++){pc[x]=pc[Math.floor(x/2)]+(x%2);++work.low_popcount_cells;++work.low_popcount_additions;}
 const pascal=[],cumulative=[];
 for(let f=0;f<=F;f++){
  const row=[];
  for(let j=0;j<=f;j++){
   row[j]=j===0||j===f?1n:BigInt(pascal[f-1][j-1])+BigInt(pascal[f-1][j]);
   if(j>0&&j<f)++work.pascal_additions;
   ++work.pascal_cells;
  }
  pascal.push(row.map(String));
  const pref=[0n];++work.cumulative_cells;
  for(const v of row){pref.push(pref[pref.length-1]+v);++work.cumulative_cells;++work.cumulative_additions;}
  cumulative.push(pref.map(String));
 }
 const lows=[];
 for(let r=0;r<base;r++){
  const records=[],best=[null,null],masks=[0,0];
  for(let j=0;j<primes.length;j++){
   const p=primes[j],borrow=r<p?1:0;let low=r-p;++work.low_subtractions;
   if(borrow){low+=base;++work.low_wrap_additions;}
   const cost=pc[low];records.push({prime_index:j,prime:p,borrow,low_remainder:low,low_popcount:cost});++work.low_prime_records;
   if(best[borrow]===null||cost<best[borrow]){best[borrow]=cost;masks[borrow]=1<<j;}
   else if(cost===best[borrow])masks[borrow]|=1<<j;
  }
  lows.push({residue:r,records,best_no_borrow:best[0],best_borrow:best[1],no_borrow_prime_mask:masks[0],borrow_prime_mask:masks[1]});
 }
 const blocks=[],costCounts=Array(B+1).fill(0n),joint=new Map(),maskCounts=new Map();let total=0n;
 for(let r=0;r<base;r++)for(let t=0;t<K;t++){
  const low=lows[r];let delta=low.best_no_borrow,mask=low.no_borrow_prime_mask;
  if(low.best_borrow!==null){
   const c=low.best_borrow+t-1;work.borrow_cost_add_subtract_steps+=2;
   if(delta===null||c<delta){delta=c;mask=low.borrow_prime_mask;}
   else if(c===delta)mask|=low.borrow_prime_mask;
  }
  const free=t===K-1?0:K-t-2,fixed=t===K-1?1:2;
  const high=t===K-1?"1"+"0".repeat(K-1):"1"+"?".repeat(free)+"1"+"0".repeat(t);
  const template=high+r.toString(2).padStart(L,"0"),count=cumulative[free][free+1];
  const b={id:blocks.length,low_residue:r,trailing_zeros:t,free_bits:free,fixed_high_ones:fixed,delta,
   optimal_prime_mask:mask,template,count};
  blocks.push(b);++work.blocks;total+=BigInt(count);++work.total_additions;
  maskCounts.set(mask,(maskCounts.get(mask)||0n)+BigInt(count));++work.mask_histogram_additions;
  for(let ones=0;ones<=free;ones++){
   if(work.histogram_additions+2>limits.max_histogram_additions)throw new RangeError("histogram cap");
   const cost=fixed+ones+delta;
   if(cost<0||cost>B)throw new Error("cost outside bit-length range");
   const weight=BigInt(pascal[free][ones]),key=cost+":"+mask;
   costCounts[cost]+=weight;joint.set(key,(joint.get(key)||0n)+weight);work.histogram_additions+=2;
  }
 }
 const lower=1n<<BigInt(B-1),upper=(lower<<1n)-1n;
 if(total!==lower)throw new Error("block weights do not cover bit-length domain");
 const nonzero=costCounts.map((v,i)=>v?i:-1).filter(i=>i>=0);
 return {schema:SCHEMA,bit_length:B,low_bits:L,high_bits:K,low_base:base,primes:primes.slice(),
  domain:{lower:lower.toString(),upper:upper.toString(),count:total.toString()},limits,
  prime_contract:"Supplied prime values are identified premises; no primality testing.",
  order:"increasing low residue, then high-part trailing-zero count, then lexicographic free bitstring; not numerical integer order",
  low_popcounts:pc,low_records:lows,pascal,cumulative,blocks,cost_counts:costCounts.map(String),
  minimum_cost:nonzero[0],maximum_cost:nonzero[nonzero.length-1],
  exact_prime_mask_counts:[...maskCounts].sort((a,b)=>a[0]-b[0]).map(([mask,count])=>({mask,count:count.toString()})),
  joint_cost_mask_counts:[...joint].map(([key,count])=>{const [cost,mask]=key.split(":").map(Number);return{cost,mask,count:count.toString()};}).sort((a,b)=>a.cost-b.cost||a.mask-b.mask),
  provenance:input.provenance||{},work};
}
function open(s){
 if(!s||s.schema!==SCHEMA||!Array.isArray(s.blocks)||!Array.isArray(s.pascal)||!Array.isArray(s.cumulative))throw new TypeError("snapshot");
 const B=s.bit_length,L=s.low_bits,K=s.high_bits,maskLimit=(1<<s.primes.length)-1;
 if(s.blocks.length!==s.low_base*K||s.pascal.length!==K-1||s.cumulative.length!==K-1)throw new TypeError("snapshot lengths");
 const lower=decimal(s.domain.lower,"lower"),upper=decimal(s.domain.upper,"upper");
 const work={queries:0,conditions_compiled:0,condition_cache_hits:0,condition_block_scans:0,prefix_character_checks:0,
  conditional_entries:0,conditional_prefix_additions:0,pascal_prefix_reads:0,pascal_range_subtractions:0,
  cache_binary_probes:0,selection_bit_decisions:0,rank_bit_decisions:0,rank_additions:0,rank_subtractions:0,
  template_character_reads:0,input_bit_scans:0,profile_cost_additions:0,representation_subtractions:0,
  representation_bit_scans:0,low_record_reads:0,block_reads:0,
  constructor_calls:0,new_low_costs:0,new_pascal_cells:0,new_base_histogram_cells:0,primality_tests:0,integer_enumerations:0};
 const caches=new Map();
 function range(f,lo,hi){
  lo=Math.max(0,lo);hi=Math.min(f,hi);
  if(lo>hi)return 0n;
  work.pascal_prefix_reads+=2;++work.pascal_range_subtractions;
  return BigInt(s.cumulative[f][hi+1])-BigInt(s.cumulative[f][lo]);
 }
 function normalize(options={}){
  const c={min_powers:options.min_powers===undefined?0:small(options.min_powers,"min_powers",0,B),
   max_powers:options.max_powers===undefined?B:small(options.max_powers,"max_powers",0,B),
   required_prime_mask:options.required_prime_mask===undefined?0:small(options.required_prime_mask,"required_prime_mask",0,maskLimit),
   forbidden_prime_mask:options.forbidden_prime_mask===undefined?0:small(options.forbidden_prime_mask,"forbidden_prime_mask",0,maskLimit),
   low_residue:options.low_residue===undefined?null:small(options.low_residue,"low_residue",0,s.low_base-1),
   binary_prefix:options.binary_prefix===undefined?"":options.binary_prefix};
  if(c.min_powers>c.max_powers||(c.required_prime_mask&c.forbidden_prime_mask))throw new RangeError("contradictory condition");
  if(typeof c.binary_prefix!=="string"||!/^[01]*$/.test(c.binary_prefix)||c.binary_prefix.length>B)throw new TypeError("binary_prefix");
  return c;
 }
 function compile(options){
  const c=normalize(options),key=JSON.stringify(c);
  if(caches.has(key)){++work.condition_cache_hits;return caches.get(key);}
  ++work.conditions_compiled;const entries=[];let total=0n;
  for(const b of s.blocks){
   ++work.condition_block_scans;
   if(c.low_residue!==null&&b.low_residue!==c.low_residue)continue;
   if((b.optimal_prime_mask&c.required_prime_mask)!==c.required_prime_mask||(b.optimal_prime_mask&c.forbidden_prime_mask))continue;
   let freePrefix="",knownOnes=0,conflict=false;
   for(let j=0;j<c.binary_prefix.length;j++){
    ++work.prefix_character_checks;const bit=c.binary_prefix[j],at=b.template[j];
    if(at==="?"){freePrefix+=bit;if(bit==="1")++knownOnes;}
    else if(at!==bit){conflict=true;break;}
   }
   if(conflict)continue;
   const remaining=b.free_bits-freePrefix.length;
   const lo=Math.max(0,c.min_powers-b.fixed_high_ones-b.delta-knownOnes);
   const hi=Math.min(remaining,c.max_powers-b.fixed_high_ones-b.delta-knownOnes);
   const count=range(remaining,lo,hi);if(count===0n)continue;
   const start=total;total+=count;++work.conditional_prefix_additions;++work.conditional_entries;
   entries.push({block:b.id,free_prefix:freePrefix,remaining,lo,hi,count:count.toString(),start:start.toString(),end:total.toString()});
  }
  const cache={key,condition:c,count:total.toString(),entries};caches.set(key,cache);return cache;
 }
 function primeList(mask){return s.primes.filter((p,i)=>mask&(1<<i));}
 function entryByRank(cache,rank){
  let lo=0,hi=cache.entries.length;
  while(lo<hi){const mid=Math.floor((lo+hi)/2);++work.cache_binary_probes;if(rank<BigInt(cache.entries[mid].end))hi=mid;else lo=mid+1;}
  return cache.entries[lo];
 }
 function entryByBlock(cache,id){
  let lo=0,hi=cache.entries.length;
  while(lo<hi){const mid=Math.floor((lo+hi)/2);++work.cache_binary_probes;if(cache.entries[mid].block<id)lo=mid+1;else hi=mid;}
  return cache.entries[lo]?.block===id?cache.entries[lo]:null;
 }
 function profileCore(n){
  const value=decimal(n,"n");if(value<lower||value>upper)throw new RangeError("outside fixed bit-length domain");
  const binary=value.toString(2),high=binary.slice(0,K),r=parseInt(binary.slice(K),2);let t=0,ones=0;
  for(let i=high.length-1;i>=0;i--){++work.input_bit_scans;if(high[i]!=="0")break;++t;}
  for(const bit of high){++work.input_bit_scans;if(bit==="1")++ones;}
  const block=s.blocks[r*K+t];++work.block_reads;++work.profile_cost_additions;
  return {n,binary,block:block.id,low_residue:r,trailing_zeros:t,high_popcount:ones,
   minimum_powers:ones+block.delta,optimal_prime_mask:block.optimal_prime_mask,optimal_primes:primeList(block.optimal_prime_mask)};
 }
 function selectCore(rank,cache){
  if(rank>=BigInt(cache.count))throw new RangeError("rank outside family");
  const e=entryByRank(cache,rank),b=s.blocks[e.block];let local=rank-BigInt(e.start),lo=e.lo,hi=e.hi,tail="";
  ++work.rank_subtractions;
  for(let left=e.remaining;left>0;left--){
   ++work.selection_bit_decisions;const zero=range(left-1,lo,hi);
   if(local<zero)tail+="0";else{local-=zero;++work.rank_subtractions;tail+="1";--lo;--hi;}
  }
  const free=e.free_prefix+tail;let at=0,binary="",ones=0;
  for(const ch of b.template){++work.template_character_reads;if(ch==="?"){const bit=free[at++];binary+=bit;if(bit==="1")++ones;}else binary+=ch;}
  return {rank:rank.toString(),n:BigInt("0b"+binary).toString(),binary,block:b.id,free_bits:free,
   minimum_powers:b.fixed_high_ones+ones+b.delta,optimal_prime_mask:b.optimal_prime_mask,optimal_primes:primeList(b.optimal_prime_mask)};
 }
 function rankCore(n,cache){
  const p=profileCore(n),c=cache.condition;
  if(p.minimum_powers<c.min_powers||p.minimum_powers>c.max_powers||
    (p.optimal_prime_mask&c.required_prime_mask)!==c.required_prime_mask||(p.optimal_prime_mask&c.forbidden_prime_mask)||
    (c.low_residue!==null&&p.low_residue!==c.low_residue)||!p.binary.startsWith(c.binary_prefix))return{member:false,rank:null,profile:p};
  const e=entryByBlock(cache,p.block);if(!e)throw new Error("condition cache missing member block");
  const b=s.blocks[p.block];let free="";
  for(let i=0;i<B;i++){++work.template_character_reads;if(b.template[i]==="?")free+=p.binary[i];}
  const tail=free.slice(e.free_prefix.length);let local=0n,lo=e.lo,hi=e.hi;
  for(let i=0;i<tail.length;i++){
   ++work.rank_bit_decisions;
   if(tail[i]==="1"){local+=range(tail.length-i-1,lo,hi);++work.rank_additions;--lo;--hi;}
  }
  ++work.rank_additions;
  return {member:true,rank:(BigInt(e.start)+local).toString(),profile:p};
 }
 const api={
  summary(){++work.queries;return{bit_length:B,primes:s.primes,domain:s.domain,minimum_cost:s.minimum_cost,maximum_cost:s.maximum_cost,
   cost_counts:s.cost_counts,exact_prime_mask_counts:s.exact_prime_mask_counts,blocks:s.blocks.length,order:s.order,construction_work:s.work};},
  family(options){++work.queries;const c=compile(options);return{condition:c.condition,count:c.count,nonempty_blocks:c.entries.length};},
  select(rank,options){++work.queries;const c=compile(options);return Object.assign({condition:c.condition,count:c.count},selectCore(decimal(rank,"rank"),c));},
  rank(n,options){++work.queries;const c=compile(options);return Object.assign({condition:c.condition,count:c.count},rankCore(n,c));},
  page(start,limit,options){++work.queries;const c=compile(options),r=decimal(start,"start");small(limit,"limit",0,100);
   if(r>BigInt(c.count))throw new RangeError("page start");const rows=[];
   for(let i=0;i<limit&&r+BigInt(i)<BigInt(c.count);i++)rows.push(selectCore(r+BigInt(i),c));
   return{condition:c.condition,count:c.count,start:r.toString(),rows,next_rank:(r+BigInt(rows.length)).toString(),complete:r+BigInt(rows.length)===BigInt(c.count)};},
  profile(n){++work.queries;return profileCore(n);},
  representation(n,primeIndex){
   ++work.queries;const p=profileCore(n);
   let j=primeIndex;if(j===undefined){j=0;while(!(p.optimal_prime_mask&(1<<j)))++j;}else small(j,"primeIndex",0,s.primes.length-1);
   if(!(p.optimal_prime_mask&(1<<j)))throw new RangeError("requested prime is not optimal");
   const remainder=BigInt(n)-BigInt(s.primes[j]);++work.representation_subtractions;const bits=remainder.toString(2),exponents=[];
   for(let i=bits.length-1;i>=0;i--){++work.representation_bit_scans;if(bits[i]==="1")exponents.push(bits.length-1-i);}
   if(exponents.length!==p.minimum_powers)throw new Error("saved minimum and canonical representation differ");
   return{profile:p,prime_index:j,prime:s.primes[j],remainder:remainder.toString(),exponents,term_count:exponents.length,
    convention:"canonical distinct binary powers attain the minimum even though the source permits repeated exponents"};},
  low(residue){++work.queries;small(residue,"residue",0,s.low_base-1);++work.low_record_reads;return s.low_records[residue];},
  block(id){++work.queries;small(id,"block",0,s.blocks.length-1);++work.block_reads;return s.blocks[id];},
  caches(){return [...caches.values()];},
  work(){return Object.assign({},work);}
 };
 return api;
}
module.exports={SCHEMA,construct,open};
