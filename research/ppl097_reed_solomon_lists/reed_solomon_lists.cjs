'use strict';
const SCHEMA='commons.reed_solomon_list_index/v1';
const PRIMES=Object.freeze([2,3,5,7,11,13,17,19,23,29,31]);
const LIMITS=Object.freeze({polynomials:100000,coordinates:1000000,conditions:128,page:128});
const clone=x=>JSON.parse(JSON.stringify(x));
function int(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name+' out of range');return x;}
function pop(x){let n=0;for(;x;x&=x-1)n++;return n;}
function contract(input){
 if(!input||!PRIMES.includes(input.prime))throw new TypeError('prime must be in the supported fixed prime list');
 const q=input.prime;
 if(!Array.isArray(input.points)||!input.points.length||!Array.isArray(input.received)||input.received.length!==input.points.length)throw new TypeError('point/received shape');
 const n=int(input.points.length,1,q,'length'),k=int(input.dimension,1,n,'dimension');
 const used=new Set();for(const x of input.points){int(x,0,q-1,'point');if(used.has(x))throw new TypeError('points must be distinct');used.add(x);}
 input.received.forEach(x=>int(x,0,q-1,'symbol'));
 const total=q**k;
 if(total>LIMITS.polynomials||total*n>LIMITS.coordinates)throw new RangeError('enumeration budget exceeded');
 return {q,n,k,total,all:2**n-1};
}
function coefficients(rank,q,k){const out=[];for(let i=0;i<k;i++){out.push(rank%q);rank=Math.floor(rank/q);}return out;}
function buildIndex(input){
 const {q,n,k,total}=contract(input),map=new Map(),packedWords=[],histogram=Array(n+1).fill(0);
 const powers=[];let place=1n;for(let i=0;i<n;i++){powers.push(place);place*=BigInt(q);}
 const work={polynomials_enumerated:0,coordinate_evaluations:0,horner_steps:0,packed_digits:0,coefficient_digits:0,prime_tests:0};
 for(let rank=0;rank<total;rank++){
  const a=coefficients(rank,q,k);work.coefficient_digits+=k;let agreement=0,packed=0n;
  for(let j=0;j<n;j++){
   let value=0;for(let d=k-1;d>=0;d--){value=(value*input.points[j]+a[d])%q;work.horner_steps++;}
   work.coordinate_evaluations++;if(value===input.received[j])agreement+=2**j;
   packed+=BigInt(value)*powers[j];work.packed_digits++;
  }
  if(!map.has(agreement))map.set(agreement,[]);map.get(agreement).push(rank);
  packedWords.push(packed.toString());histogram[n-pop(agreement)]++;work.polynomials_enumerated++;
 }
 const fibers=[...map].sort((a,b)=>a[0]-b[0]).map(([agreement_mask,coefficient_ranks])=>({agreement_mask,coefficient_ranks}));
 return {schema:SCHEMA,input:{prime:q,dimension:k,points:input.points.slice(),received:input.received.slice()},
  polynomials:total,fibers,packed_words:packedWords,distance_histogram:histogram,construction_work:work,
  conventions:{rank:'sum a_i*q^i, coefficients in increasing degree order',packing:'sum word_j*q^j, point-list order',
   distance:'number of disagreeing retained coordinates, closed integer radius',
   candidates:'distinct full codewords; punctured images are not deduplicated'}};
}
function openIndex(snapshot){
 const data=clone(snapshot);if(data.schema!==SCHEMA)throw new TypeError('schema mismatch');
 const {q,n,k,total,all}=contract(data.input);
 if(data.polynomials!==total||!Array.isArray(data.fibers)||!Array.isArray(data.packed_words)||data.packed_words.length!==total||data.distance_histogram.length!==n+1)throw new TypeError('snapshot shape');
 const rankToFiber=Array(total).fill(-1),wordBound=BigInt(q)**BigInt(n);let oldMask=-1;
 for(let id=0;id<data.fibers.length;id++){
  const f=data.fibers[id];int(f.agreement_mask,0,all,'agreement mask');if(f.agreement_mask<=oldMask)throw new TypeError('fiber order');oldMask=f.agreement_mask;
  if(!Array.isArray(f.coefficient_ranks)||!f.coefficient_ranks.length)throw new TypeError('empty fiber');
  let oldRank=-1;
  for(const r of f.coefficient_ranks){int(r,0,total-1,'coefficient rank');if(r<=oldRank||rankToFiber[r]!==-1)throw new TypeError('rank partition');oldRank=r;rankToFiber[r]=id;}
 }
 if(rankToFiber.some(x=>x<0))throw new TypeError('incomplete rank partition');
 for(const word of data.packed_words)if(typeof word!=='string'||!/^(0|[1-9][0-9]*)$/.test(word)||word.length>64||BigInt(word)>=wordBound)throw new TypeError('packed word range');
 data.distance_histogram.forEach(x=>int(x,0,total,'histogram count'));
 if(data.distance_histogram.reduce((a,b)=>a+b,0)!==total)throw new TypeError('histogram total');
 const cache=new Map();
 const work={saved_fibers_indexed:data.fibers.length,saved_coefficient_ranks_indexed:total,saved_packed_words_indexed:total,queries:0,
  conditions_created:0,condition_fibers_scanned:0,condition_cache_hits:0,prefix_fibers_scanned:0,binary_search_steps:0,
  coefficient_digits_decoded:0,packed_digits_decoded:0,polynomials_enumerated:0,coordinate_evaluations:0,horner_steps:0};
 function rankArg(value,name){if(typeof value!=='string'||!/^(0|[1-9][0-9]*)$/.test(value)||value.length>6)throw new TypeError(name+' decimal string required');return int(Number(value),0,total,name);}
 function condition(query={}){
  if(!query||typeof query!=='object'||Array.isArray(query))throw new TypeError('query object required');
  for(const key of Object.keys(query))if(!['keep_mask','require_mask','radius'].includes(key))throw new TypeError('unknown query field');
  const keep=query.keep_mask===undefined?all:int(query.keep_mask,0,all,'keep_mask'),require=query.require_mask===undefined?0:int(query.require_mask,0,all,'require_mask'),length=pop(keep);
  const radius=query.radius===undefined?length:int(query.radius,0,length,'radius'),key=[keep,require,radius].join(':');
  if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}
  if(cache.size>=LIMITS.conditions)throw new RangeError('condition budget exceeded');
  const ids=[],distance_counts=Array(length+1).fill(0);let count=0;
  for(let id=0;id<data.fibers.length;id++){
   const f=data.fibers[id],errors=pop(keep&~f.agreement_mask);work.condition_fibers_scanned++;
   if((f.agreement_mask&require)===require&&errors<=radius){ids.push(id);count+=f.coefficient_ranks.length;distance_counts[errors]+=f.coefficient_ranks.length;}
  }
  const record={key,keep_mask:keep,require_mask:require,retained_coordinates:length,radius,count,fiber_ids:ids,distance_counts};
  const c={record,idSet:new Set(ids)};cache.set(key,c);work.conditions_created++;return c;
 }
 function lower(values,bound){
  let lo=0,hi=values.length;
  while(lo<hi){work.binary_search_steps++;const mid=(lo+hi)>>1;if(values[mid]<bound)lo=mid+1;else hi=mid;}return lo;
 }
 function prefix(c,bound){
  let count=0;for(const id of c.record.fiber_ids){work.prefix_fibers_scanned++;count+=lower(data.fibers[id].coefficient_ranks,bound);}return count;
 }
 function record(rank){
  const f=data.fibers[rankToFiber[rank]],a=coefficients(rank,q,k);work.coefficient_digits_decoded+=k;
  return {coefficient_rank:rank,coefficients:a,agreement_mask:f.agreement_mask,full_distance:n-pop(f.agreement_mask)};
 }
 function selected(c,j){
  if(j<0||j>=c.record.count)throw new RangeError('rank outside candidate list');
  let lo=0,hi=total-1;
  while(lo<hi){const mid=(lo+hi)>>1;if(prefix(c,mid+1)>j)hi=mid;else lo=mid+1;}
  if(!c.idSet.has(rankToFiber[lo]))throw new Error('snapshot selection mismatch');
  return {rank:String(j),...record(lo)};
 }
 return Object.freeze({
  summary(){work.queries++;return {prime:q,length:n,dimension:k,polynomials:total,agreement_fibers:data.fibers.length,
   distance_histogram:data.distance_histogram.slice(),minimum_distance:data.distance_histogram.findIndex(x=>x>0),construction_work:clone(data.construction_work)};},
  input(){work.queries++;return clone(data.input);},
  fiberPage(start=0,limit=16){work.queries++;int(start,0,data.fibers.length,'start');int(limit,0,LIMITS.page,'limit');return {start,total:data.fibers.length,rows:clone(data.fibers.slice(start,start+limit))};},
  count(query={}){work.queries++;return clone(condition(query).record);},
  prefix(query,bound){work.queries++;const b=rankArg(bound,'bound');return {bound,count:prefix(condition(query),b)};},
  select(query,rank){work.queries++;return selected(condition(query),rankArg(rank,'rank'));},
  rank(query,coefficientRank){
   work.queries++;int(coefficientRank,0,total-1,'coefficient rank');const c=condition(query),accepted=c.idSet.has(rankToFiber[coefficientRank]);
   return {coefficient_rank:coefficientRank,rank:accepted?String(prefix(c,coefficientRank)):null};
  },
  page(query,start='0',limit=16){
   work.queries++;const c=condition(query),j=rankArg(start,'start');int(limit,0,LIMITS.page,'limit');if(j>c.record.count)throw new RangeError('page start exceeds list');
   const rows=[];for(let r=j;r<c.record.count&&rows.length<limit;r++)rows.push(selected(c,r));return {start,total:c.record.count,rows};
  },
  inspect(coefficientRank){work.queries++;int(coefficientRank,0,total-1,'coefficient rank');return record(coefficientRank);},
  word(coefficientRank){
   work.queries++;int(coefficientRank,0,total-1,'coefficient rank');let packed=BigInt(data.packed_words[coefficientRank]);const word=[];
   for(let j=0;j<n;j++){word.push(Number(packed%BigInt(q)));packed/=BigInt(q);work.packed_digits_decoded++;}
   return {...record(coefficientRank),values:word,derivation:'decoded saved packed word; no polynomial reevaluation'};
  },
  conditions(){return {records:[...cache.values()].map(x=>clone(x.record)),semantics:'Candidate identities remain full codewords even after puncturing.'};},
  work(){return clone(work);}
 });
}
module.exports={SCHEMA,PRIMES,LIMITS,buildIndex,openIndex};
