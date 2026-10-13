"use strict";
const clone=x=>JSON.parse(JSON.stringify(x));
const decimal=(s,name)=>{if(typeof s!=="string"||!/^(0|[1-9]\d*)$/.test(s))throw new TypeError(name+" must be a canonical nonnegative decimal string");return BigInt(s);};
const integer=(x,name,a,b)=>{if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(name);return x;};
function compile(input){
 const lim=input.limits,ps=input.primes;
 if(!lim||lim.max_primes!==16||lim.max_prime!==97||lim.max_decimal_exponent!==200||lim.max_intervals!==20000||lim.max_events!==40002)throw new Error("explicit limits required");
 if(!Array.isArray(ps)||ps.length<1||ps.length>16||new Set(ps).size!==ps.length||ps.some((p,i)=>!Number.isSafeInteger(p)||p<3||p>97||p%2===0||(i&&p<=ps[i-1])))throw new Error("ordered odd-prime premise");
 if(typeof input.upper!=="string"||input.upper.length>201)throw new Error("endpoint length");
 const upper=decimal(input.upper,"upper"),ceiling=BigInt("1"+"0".repeat(200));if(upper<1n||upper>ceiling)throw new RangeError("endpoint bound");
 const work={modular_inverses:0,euclidean_divisions:0,harmonic_residue_updates:0,power_multiplications:0,intervals:0,event_updates:0,event_sort_comparisons:0,event_positions:0,segments:0,group_prefix_additions:0,new_prime_sieve:0,new_standalone_primality_tests:0,enumerated_integers:0,full_harmonic_or_lcm_values:0};
 function inverse(k,p){let a=BigInt(k),b=BigInt(p),x=1n,y=0n;while(b){const q=a/b;[a,b]=[b,a-q*b];[x,y]=[y,x-q*y];work.euclidean_divisions++;}if(a!==1n)throw new Error("nonunit: input prime premise failed");work.modular_inverses++;return Number((x%BigInt(p)+BigInt(p))%BigInt(p));}
 const tables=[],intervals=[],events=new Map();
 function event(x){const key=String(x);if(!events.has(key)){if(events.size>=lim.max_events)throw new Error("event cap");events.set(key,{position:key,add:[],remove:[]});}return events.get(key);}
 event(1n);event(upper+1n);
 for(let pi=0;pi<ps.length;pi++){
  const p=ps[pi],rows=[],digits=[];let residue=0;
  for(let k=1;k<p;k++){const inv=inverse(k,p);residue=(residue+inv)%p;work.harmonic_residue_updates++;rows.push({k,inverse:inv,inverse_multiple:(k*inv-1)/p,residue});if(k>1&&residue===0)digits.push(k);}
  const powers=["1"];let power=1n,e=0;
  while(power<=upper){power*=BigInt(p);e++;work.power_multiplications++;powers.push(String(power));if(power>upper)break;
   for(const digit of digits){
    const lo=BigInt(digit)*power;if(lo>upper)continue;const naturalHi=BigInt(digit+1)*power-1n,hi=naturalHi<upper?naturalHi:upper;
    if(intervals.length>=lim.max_intervals)throw new Error("interval cap");
    const id=intervals.length;intervals.push({id,prime_index:pi,prime:p,exponent:e,digit,power:String(power),lo:String(lo),hi:String(hi),clipped:hi!==naturalHi});
    event(lo).add.push(id);event(hi+1n).remove.push(id);work.event_updates+=2;work.intervals++;
   }
  }
  tables.push({prime:p,index:pi,rows,zero_digits:digits,powers});
 }
 const eventRows=[...events.values()].sort((a,b)=>{work.event_sort_comparisons++;return BigInt(a.position)<BigInt(b.position)?-1:BigInt(a.position)>BigInt(b.position)?1:0;});
 const active=Array(ps.length).fill(null),segments=[],groupMap=new Map();let start=1n,mask=0;
 for(const ev of eventRows){const position=BigInt(ev.position);
  if(position>start){const hi=position-1n,length=position-start,id=segments.length,active_intervals=active.filter(x=>x!==null);
   segments.push({id,lo:String(start),hi:String(hi),length:String(length),mask,active_intervals});
   if(!groupMap.has(mask))groupMap.set(mask,{mask,segment_ids:[],prefix:["0"]});
   const g=groupMap.get(mask);g.segment_ids.push(id);g.prefix.push(String(BigInt(g.prefix.at(-1))+length));work.group_prefix_additions++;work.segments++;
  }
  for(const id of ev.remove){const t=intervals[id];if(active[t.prime_index]!==id)throw new Error("removal invariant");active[t.prime_index]=null;mask&=~(2**t.prime_index);}
  for(const id of ev.add){const t=intervals[id];if(active[t.prime_index]!==null)throw new Error("overlapping same-prime intervals");active[t.prime_index]=id;mask|=2**t.prime_index;}
  start=position;
 }
 if(start!==upper+1n||mask!==0||active.some(x=>x!==null))throw new Error("terminal partition");
 const groups=[...groupMap.values()].sort((a,b)=>a.mask-b.mask).map(g=>({...g,count:g.prefix.at(-1)}));
 work.event_positions=eventRows.length;
 return {schema:"harmonic-cancellation-intervals/v1",lower:"1",upper:input.upper,primes:ps.slice(),tables,intervals,events:eventRows,segments,groups,
  total:String(upper),screened:String(groups.filter(g=>g.mask!==0).reduce((a,g)=>a+BigInt(g.count),0n)),
  unresolved:groups.find(g=>g.mask===0)?.count??"0",provenance:clone(input.provenance),limits:clone(lim),work};
}
function openIndex(snapshot){
 const S=clone(snapshot),upper=decimal(S.upper,"saved upper"),ps=S.primes;
 if(S.schema!=="harmonic-cancellation-intervals/v1"||S.lower!=="1"||!Array.isArray(ps)||ps.length<1||ps.length>16||S.segments.length<1)throw new Error("saved shape");
 const segments=S.segments.map((s,i)=>{if(s.id!==i||!Number.isSafeInteger(s.mask)||s.mask<0||s.mask>=2**ps.length)throw new Error("segment shape");return {...s,lo:decimal(s.lo,"lo"),hi:decimal(s.hi,"hi"),length:decimal(s.length,"length")};});
 for(let i=0;i<segments.length;i++){const s=segments[i];if(s.lo>(s.hi)||s.hi-s.lo+1n!==s.length||s.lo!==(i?segments[i-1].hi+1n:1n))throw new Error("partition shape");}
 if(segments.at(-1).hi!==upper)throw new Error("saved endpoint");
 const work={queries:0,conditions:0,condition_cache_hits:0,segment_scans:0,conditional_prefix_additions:0,binary_search_steps:0,selected_offset_additions:0,rank_offset_additions:0,window_subtractions:0,witness_quotients:0,saved_interval_reads:0,new_modular_inverses:0,new_harmonic_residues:0,new_powers:0,new_intervals:0,new_events:0,new_partition:0};
 const cache=new Map(),pos=new Map(ps.map((p,i)=>[p,i]));
 function labels(values=[]){if(!Array.isArray(values)||new Set(values).size!==values.length||values.some(x=>!pos.has(x)))throw new Error("palette subset required");return values.slice().sort((a,b)=>a-b);}
 const maskOf=values=>values.reduce((a,p)=>a|2**pos.get(p),0);
 function condition(spec={}){
  const require=labels(spec.require),forbid=labels(spec.forbid),any=labels(spec.any);
  if(require.some(p=>forbid.includes(p)))throw new Error("contradictory condition");
  const key=JSON.stringify([require,forbid,any]);if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}
  if(cache.size>=32)throw new Error("condition cap");const a=maskOf(require),b=maskOf(forbid),c=maskOf(any),ids=[],prefix=[0n];
  for(const s of segments){work.segment_scans++;if((s.mask&a)===a&&(s.mask&b)===0&&(c===0||(s.mask&c)!==0)){ids.push(s.id);prefix.push(prefix.at(-1)+s.length);work.conditional_prefix_additions++;}}
  const out={spec:{require,forbid,any},ids,prefix,total:prefix.at(-1)};cache.set(key,out);work.conditions++;return out;
 }
 function boundedN(n){const x=decimal(n,"n");if(x<1n||x>upper)throw new RangeError("n outside saved domain");return x;}
 function locate(x,ids){let l=0,r=ids.length;while(l<r){work.binary_search_steps++;const m=Math.floor((l+r)/2);if(segments[ids[m]].lo<=x)l=m+1;else r=m;}return l-1;}
 const allIds=segments.map(s=>s.id);
 function selected(c,rank){let r=decimal(rank,"rank");if(r>=c.total)throw new RangeError("rank");let l=0,h=c.ids.length;while(l<h){work.binary_search_steps++;const m=Math.floor((l+h)/2);if(c.prefix[m+1]<=r)l=m+1;else h=m;}const s=segments[c.ids[l]],n=s.lo+r-c.prefix[l];work.selected_offset_additions++;return {rank,n:String(n),segment:s.id,mask:s.mask,primes:ps.filter((p,i)=>(s.mask&2**i)!==0)};}
 function ranked(c,value){const x=boundedN(value),i=locate(x,c.ids);if(i<0||x>segments[c.ids[i]].hi)return {n:value,member:false,rank:null};const s=segments[c.ids[i]];work.rank_offset_additions++;return {n:value,member:true,rank:String(c.prefix[i]+x-s.lo),segment:s.id,mask:s.mask};}
 function prefixCount(c,x){if(x<1n)return 0n;if(x>=upper)return c.total;const i=locate(x,c.ids);if(i<0)return 0n;const s=segments[c.ids[i]],end=x<s.hi?x:s.hi;return c.prefix[i]+end-s.lo+1n;}
 function family(c){return {condition:c.spec,count:String(c.total),segments:c.ids.length};}
 function query(q){
  work.queries++;let out;
  if(q.op==="summary")out={lower:S.lower,upper:S.upper,primes:ps,total:S.total,screened:S.screened,unresolved:S.unresolved,intervals:S.intervals.length,event_positions:S.events.length,segments:S.segments.length,mask_groups:S.groups.length,construction_work:S.work};
  else if(q.op==="prime"){if(!pos.has(q.prime))throw new Error("prime outside palette");out=S.tables[pos.get(q.prime)];}
  else if(q.op==="interval"){const id=integer(q.id,"interval id",0,S.intervals.length-1);work.saved_interval_reads++;out=S.intervals[id];}
  else if(q.op==="segment"){const id=integer(q.id,"segment id",0,S.segments.length-1);out=S.segments[id];}
  else if(q.op==="group"){const mask=integer(q.mask,"mask",0,2**ps.length-1);out=S.groups.find(g=>g.mask===mask)??{mask,segment_ids:[],prefix:["0"],count:"0"};}
  else if(q.op==="classify"||q.op==="witness"){
   const x=boundedN(q.n),i=locate(x,allIds),s=segments[i],primes=ps.filter((p,j)=>(s.mask&2**j)!==0);
   if(q.op==="classify")out={n:q.n,segment:i,mask:s.mask,primes,status:s.mask?"certified cancellation":"unresolved by selected palette"};
   else{
    if(q.prime!==undefined&&!pos.has(q.prime))throw new Error("prime outside palette");
    const candidates=s.active_intervals.map(id=>S.intervals[id]),v=q.prime===undefined?candidates[0]:candidates.find(v=>v.prime===q.prime);
    if(!v)out={n:q.n,prime:q.prime??null,certified:false,status:"no selected-prime cancellation witness"};
    else{const digit=x/BigInt(v.power);work.witness_quotients++;work.saved_interval_reads++;
     out={n:q.n,certified:true,prime:v.prime,interval:clone(v),leading_digit:String(digit),saved_modular_harmonic_residue:S.tables[v.prime_index].rows[v.digit-1].residue,statement:"This prime divides gcd(a_n,L_n); full gcd and denominator are not computed."};
    }
   }
  }
  else if(q.op==="conditions")out=[...cache.values()].map(family);
  else{
   const c=condition(q.condition);
   if(q.op==="family")out=family(c);
   else if(q.op==="select")out=selected(c,q.rank);
   else if(q.op==="rank")out=ranked(c,q.n);
   else if(q.op==="window"){const lo=boundedN(q.lo),hi=boundedN(q.hi);if(lo>hi)throw new RangeError("ordered window");work.window_subtractions++;out={condition:c.spec,lo:q.lo,hi:q.hi,count:String(prefixCount(c,hi)-prefixCount(c,lo-1n))};}
   else if(q.op==="page"){const offset=decimal(q.offset,"offset");if(offset>c.total)throw new RangeError("offset");const limit=integer(q.limit??20,"limit",0,128),rows=[];let r=offset;for(let j=0;j<limit&&r<c.total;j++,r++)rows.push(selected(c,String(r)));out={condition:c.spec,count:String(c.total),offset:q.offset,next:r<c.total?String(r):null,rows};}
   else throw new Error("unknown operation");
  }
  return clone(out);
 }
 return {query,work:()=>clone(work)};
}
module.exports={compile,openIndex};
