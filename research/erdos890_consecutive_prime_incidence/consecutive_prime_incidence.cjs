'use strict';

// The input's distinct-prime property is an explicit inherited premise.
function integer(x,name) {
  if (typeof x==='number' && (!Number.isSafeInteger(x))) throw new TypeError(name+' must be exact');
  if (typeof x!=='number' && typeof x!=='bigint' && !(typeof x==='string' && /^-?\d+$/.test(x))) throw new TypeError(name+' must be an integer');
  return BigInt(x);
}
function mod(x,m) {const r=x%m;return r<0n?r+m:r;}
function inverse(a,m,work) {
  let r0=m,r1=mod(a,m),s0=0n,s1=1n;
  while(r1) {const q=r0/r1;[r0,r1]=[r1,r0-q*r1];[s0,s1]=[s1,s0-q*s1];work.euclidean_steps++;}
  if(r0!==1n) throw new Error('Input moduli are not pairwise coprime');
  return mod(s0,m);
}
function compile(input) {
  const k=input.window,primes=input.primes;
  if(!Number.isSafeInteger(k)||k<1||k>8||!Array.isArray(primes)||primes.length<1||primes.length>16) throw new RangeError('Input dimensions');
  if(primes.some((p,i)=>!Number.isSafeInteger(p)||p<=k||(i>0&&p<=primes[i-1]))) throw new RangeError('Increasing prime premise');
  const m=primes.length,work={period_products:0,euclidean_steps:0,crt_weights:0,groups:0,coefficient_updates:0,coefficient_cells:1,profile_aggregations:0,primality_tests:0,old_sieve:0,old_factorization:0,exponent_enumeration:0};
  let period=1n;
  for(const p of primes){period*=BigInt(p);work.period_products++;}
  const coordinates=primes.map((p,i)=>{
    const groups=[{lo:0,hi:0,offset:0},{lo:1,hi:p-k,offset:null}];
    for(let r=p-k+1;r<p;r++)groups.push({lo:r,hi:r,offset:p-r});
    const cofactor=period/BigInt(p),inv=inverse(cofactor,BigInt(p),work),weight=cofactor*inv;
    work.groups+=groups.length;work.crt_weights++;
    return{id:i,prime:p,groups,cofactor:String(cofactor),inverse:String(inv),weight:String(weight)};
  });
  const zero=Array(k).fill(0),layers=Array(m+1);
  layers[m]=[{counts:zero,ways:'1'}];
  for(let i=m-1;i>=0;i--){
    const table=new Map();
    for(const row of layers[i+1])for(const g of coordinates[i].groups){
      const counts=row.counts.slice();if(g.offset!==null)counts[g.offset]++;
      const key=counts.join(','),old=table.get(key),delta=BigInt(row.ways)*BigInt(g.hi-g.lo+1);
      table.set(key,{counts,ways:(old?old.ways:0n)+delta});work.coefficient_updates++;
    }
    layers[i]=[...table.values()].sort((a,b)=>{for(let j=0;j<k;j++)if(a.counts[j]!==b.counts[j])return a.counts[j]-b.counts[j];return 0;}).map(r=>({counts:r.counts,ways:String(r.ways)}));
    work.coefficient_cells+=layers[i].length;
    if(work.coefficient_cells>100000)throw new RangeError('Coefficient budget');
  }
  const totals=Array(m+1).fill(0n);let accounting=0n;
  for(const row of layers[0]){totals[row.counts.reduce((a,b)=>a+b,0)]+=BigInt(row.ways);accounting+=BigInt(row.ways);work.profile_aggregations++;}
  if(accounting!==period)throw new Error('CRT family accounting mismatch');
  const atMost=totals.slice(0,k+1).reduce((a,b)=>a+b,0n),excluded=period-atMost;
  return{schema:'consecutive-prime-incidence-v1',input,window:k,primes,period:String(period),coordinates,layers,
    summary:{coordinates:m,offset_profiles:layers[0].length,suffix_cells:work.coefficient_cells,residue_classes:String(period),total_histogram:totals.map(String),at_most_window:String(atMost),strictly_more_than_window:String(excluded),scope:'Palette incidences are lower bounds on the full distinct-prime sum.'},work};
}
function openIndex(saved,retainedCaches) {
  if(saved.schema!=='consecutive-prime-incidence-v1')throw new TypeError('Snapshot schema');
  const k=saved.window,m=saved.primes.length,P=BigInt(saved.period),cache=new Map(retainedCaches?.entries||[]);
  const work={condition_compilations:0,saved_profile_scans:0,coefficient_additions:0,mass_cache_hits:0,mass_cache_misses:0,coordinate_group_reads:0,rank_blocks:0,select_blocks:0,crt_multiply_adds:0,crt_reductions:0,residue_reductions:0,quotient_witnesses:0,selected_records:0,new_coefficients:0,new_inverse:0,new_primality:0};
  function condition(o={}) {
    function bounds(v,def,label){if(v===undefined)return Array(k).fill(def);if(!Array.isArray(v)||v.length!==k||v.some(x=>!Number.isSafeInteger(x)||x<0))throw new TypeError(label);return v.slice();}
    const min=bounds(o.min,0,'min'),max=bounds(o.max,m,'max'),minTotal=o.min_total??0,maxTotal=o.max_total??m;
    if(!Number.isSafeInteger(minTotal)||!Number.isSafeInteger(maxTotal)||minTotal<0||maxTotal<0)throw new TypeError('Total bounds');
    work.condition_compilations++;
    return{min,max,min_total:minTotal,max_total:maxTotal};
  }
  function accepts(counts,c) {
    const total=counts.reduce((a,b)=>a+b,0);
    return total>=c.min_total&&total<=c.max_total&&counts.every((v,j)=>v>=c.min[j]&&v<=c.max[j]);
  }
  function mass(i,prefix,c) {
    const key=JSON.stringify([c,i,prefix]);
    if(cache.has(key)){work.mass_cache_hits++;return BigInt(cache.get(key));}
    work.mass_cache_misses++;let sum=0n;
    for(const row of saved.layers[i]){
      work.saved_profile_scans++;
      const counts=row.counts.map((v,j)=>v+prefix[j]);
      if(accepts(counts,c)){sum+=BigInt(row.ways);work.coefficient_additions++;}
    }
    cache.set(key,String(sum));return sum;
  }
  function validateResidues(values) {
    if(!Array.isArray(values)||values.length!==m||values.some((r,i)=>!Number.isSafeInteger(r)||r<0||r>=saved.primes[i]))throw new TypeError('Residue coordinates');
  }
  function coordinateGroup(i,r) {
    for(const g of saved.coordinates[i].groups){work.coordinate_group_reads++;if(r>=g.lo&&r<=g.hi)return g;}
    throw new Error('Saved coordinate group missing');
  }
  function materialize(residues,cycle=0n) {
    validateResidues(residues);if(cycle<0n)throw new RangeError('Negative cycle');
    let residue=0n;const counts=Array(k).fill(0),support=Array.from({length:k},()=>[]);
    for(let i=0;i<m;i++){
      residue+=BigInt(residues[i])*BigInt(saved.coordinates[i].weight);work.crt_multiply_adds++;
      const g=coordinateGroup(i,residues[i]);if(g.offset!==null){counts[g.offset]++;support[g.offset].push(saved.primes[i]);}
    }
    residue=mod(residue,P);work.crt_reductions++;const positive=residue===0n?P:residue,n=positive+cycle*P;
    const witnesses=support.map((ps,i)=>ps.map(p=>{work.quotient_witnesses++;return{prime:p,value:String(n+BigInt(i)),quotient:String((n+BigInt(i))/BigInt(p))};}));
    work.selected_records++;
    return{residues:residues.slice(),residue:String(residue),positive_representative:String(positive),cycle:String(cycle),n:String(n),counts,total:counts.reduce((a,b)=>a+b,0),support,witnesses,full_factor_count:'not established'};
  }
  function count(o={}){const c=condition(o);return{condition:c,count:String(mass(0,Array(k).fill(0),c))};}
  function select(rank,o={},cycle='0'){
    let r=integer(rank,'rank');if(r<0n)throw new RangeError('Negative rank');
    const c=condition(o),original=r,total=mass(0,Array(k).fill(0),c);
    if(r>=total)throw new RangeError('Rank outside family');
    let prefix=Array(k).fill(0);const residues=[],trace=[];
    for(let i=0;i<m;i++){
      let found=false;
      for(const g of saved.coordinates[i].groups){
        work.select_blocks++;const next=prefix.slice();if(g.offset!==null)next[g.offset]++;
        const per=mass(i+1,next,c),block=per*BigInt(g.hi-g.lo+1);
        if(r>=block){r-=block;continue;}
        const coordinateOffset=r/per,residue=g.lo+Number(coordinateOffset);r%=per;
        trace.push({coordinate:i,prime:saved.primes[i],lo:g.lo,hi:g.hi,offset:g.offset,per_residue:String(per),residue,remaining_rank:String(r)});
        residues.push(residue);prefix=next;found=true;break;
      }
      if(!found)throw new Error('Saved selection path missing');
    }
    return{condition:c,rank:String(original),family_count:String(total),record:materialize(residues,integer(cycle,'cycle')),trace};
  }
  function rank(residues,o={}){
    validateResidues(residues);const c=condition(o);let prefix=Array(k).fill(0),r=0n;
    const trace=[];
    for(let i=0;i<m;i++){
      for(const g of saved.coordinates[i].groups){
        work.rank_blocks++;const next=prefix.slice();if(g.offset!==null)next[g.offset]++;
        const per=mass(i+1,next,c);
        if(residues[i]>g.hi){r+=per*BigInt(g.hi-g.lo+1);continue;}
        if(residues[i]<g.lo)throw new Error('Saved group gap');
        r+=per*BigInt(residues[i]-g.lo);prefix=next;
        trace.push({coordinate:i,residue:residues[i],prefix_rank:String(r)});break;
      }
    }
    return{condition:c,rank:accepts(prefix,c)?String(r):null,counts:prefix,trace};
  }
  function window(n) {
    n=integer(n,'n');if(n<1n)throw new RangeError('Positive n required');
    const residues=saved.primes.map(p=>{work.residue_reductions++;return Number(n%BigInt(p));});
    const base=mod(n,P),positive=base===0n?P:base,cycle=(n-positive)/P;
    return materialize(residues,cycle);
  }
  function profiles(o={}){const c=condition(o),rows=[];for(const row of saved.layers[0]){work.saved_profile_scans++;if(accepts(row.counts,c))rows.push(row);}return{condition:c,profiles:rows};}
  function page(start,limit,o={},cycle='0'){
    const a=integer(start,'start');if(a<0n||!Number.isSafeInteger(limit)||limit<0||limit>100)throw new RangeError('Page bounds');
    const total=BigInt(count(o).count);if(a>total)throw new RangeError('Page start');
    const records=[];let j=a;
    for(;j<total&&records.length<limit;j++)records.push(select(j,o,cycle));
    return{start:String(a),count:String(total),records,next:j<total?String(j):null};
  }
  return{summary:()=>saved.summary,coordinates:()=>saved.coordinates,profiles,count,select,rank,window,page,caches:()=>({schema:'consecutive-prime-incidence-caches-v1',entries:[...cache.entries()]}),work:()=>({...work})};
}
module.exports={compile,openIndex};
