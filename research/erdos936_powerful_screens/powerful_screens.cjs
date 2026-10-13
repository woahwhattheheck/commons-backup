"use strict";
const SCHEMA="commons.powerful-local-screen.v1";
const LIMITS={primes:8,prime:97,base_period:4096,local_cells:2000000,suffix_cells:1000000,page:64,digits:2048};
function fail(s){throw Error(s);}
function int(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside bounds");return x;}
function cp(x){return JSON.parse(JSON.stringify(x));}
function gcd(a,b){while(b){const t=a%b;a=b;b=t;}return a;}
function natural(s,name){if(typeof s!=="string"||!/^(0|[1-9][0-9]*)$/.test(s)||s.length>LIMITS.digits)fail(name+" requires canonical nonnegative decimal");return BigInt(s);}
function inverse(a,m){let r=m,n=a,t=0n,u=1n;while(n){const q=r/n;[r,n]=[n,r-q*n];[t,u]=[u,t-q*u];}if(r!==1n)fail("coprime CRT factors required");return(t%m+m)%m;}
function buildIndex(input){
 const base=int(input.base,"base",2,1000000),B=int(input.base_period,"base period",1,LIMITS.base_period);
 if(!Array.isArray(input.primes)||input.primes.length<1||input.primes.length>LIMITS.primes||!input.provenance)fail("identified prime list required");
 const primes=input.primes.map((p,i)=>int(p,"odd prime premise",i?input.primes[i-1]+1:3,LIMITS.prime));
 if(primes.some(p=>!(p&1)||gcd(base,p)!==1))fail("odd bases coprime to exponential base required");
 const cycles=[],fixed=[],outer=[],work={prime_tests:0,cycle_entries:0,modular_multiplications:0,cycle_closures:0,base_phase_lookups:0,coordinate_flag_cells:0,suffix_cells:0,suffix_additions:0,crt_inverses:0,enumerated_global_exponents:0};
 for(let k=0;k<primes.length;k++){const p=primes[k],mod=p*p,period=p*(p-1);let x=1;const entries=[];
  for(let n=0;n<period;n++){const plus=(x+1)%mod,minus=(x+mod-1)%mod,mask=(plus!==0&&plus%p===0?1:0)|(minus!==0&&minus%p===0?2:0);entries.push([x,plus,minus,mask]);work.cycle_entries++;x=(x*base)%mod;work.modular_multiplications++;}
  if(x!==1)fail("supplied Euler-period closure failed");work.cycle_closures++;cycles.push({prime:p,modulus:mod,period,entries,terminal_power:x});
  if(B%period===0)fixed.push(k);else if(B%(p-1)===0&&gcd(B,p)===1)outer.push(k);else fail("base period does not separate this prime");
 }
 const coordinatePrimes=outer.map(i=>primes[i]);
 for(let i=0;i<coordinatePrimes.length;i++)for(let j=0;j<i;j++)if(gcd(coordinatePrimes[i],coordinatePrimes[j])!==1)fail("CRT coordinate overlap");
 const T=coordinatePrimes.reduce((a,p)=>a*BigInt(p),1n),P=BigInt(B)*T;
 const crt=coordinatePrimes.map(p=>{const factor=T/BigInt(p),inv=inverse(factor%BigInt(p),BigInt(p));work.crt_inverses++;return{prime:p,factor:factor.toString(),inverse:inv.toString(),coefficient:(factor*inv).toString()};});
 const rows=[],totals=Array(4).fill(0n),prefix=[];
 for(let b=0;b<B;b++){
  const fixedFlags=fixed.map(i=>{work.base_phase_lookups++;return cycles[i].entries[b%cycles[i].period][3];}),baseMask=fixedFlags.reduce((x,y)=>x|y,0);
  const flags=outer.map(i=>Array.from({length:primes[i]},(_,r)=>{if(++work.coordinate_flag_cells>LIMITS.local_cells)fail("local cell budget");return cycles[i].entries[(b+B*r)%cycles[i].period][3];}));
  const d=outer.length,suffix=Array.from({length:d+1},()=>Array.from({length:4},()=>Array(4).fill(0n)));
  for(let incoming=0;incoming<4;incoming++)for(let target=0;target<4;target++){suffix[d][incoming][target]=incoming===target?1n:0n;work.suffix_cells++;}
  for(let pos=d-1;pos>=0;pos--)for(let incoming=0;incoming<4;incoming++)for(let target=0;target<4;target++){
   let sum=0n;for(const flag of flags[pos]){sum+=suffix[pos+1][incoming|flag][target];work.suffix_additions++;}suffix[pos][incoming][target]=sum;work.suffix_cells++;
  }
  if(work.suffix_cells>LIMITS.suffix_cells)fail("suffix cell budget");
  const counts=suffix[0][baseMask];for(let c=0;c<4;c++)totals[c]+=counts[c];prefix.push(totals.map(String));
  rows.push({base_phase:b,fixed_flags:fixedFlags,base_mask:baseMask,flags,suffix:suffix.map(a=>a.map(v=>v.map(String))),counts:counts.map(String)});
 }
 if(totals.reduce((a,b)=>a+b,0n)!==P)fail("phase partition cardinality");
 return{schema:SCHEMA,base,primes,base_period:B,coordinate_period:T.toString(),period:P.toString(),fixed_prime_indices:fixed,outer_prime_indices:outer,coordinate_primes:coordinatePrimes,crt,cycles,rows,prefix,totals:totals.map(String),summary:{period:P.toString(),class_counts:totals.map(String),plus_excluded:(totals[1]+totals[3]).toString(),minus_excluded:(totals[2]+totals[3]).toString(),both_pass_local_screen:totals[0].toString(),base_phases:B,coordinate_primes:coordinatePrimes},ordering:{exponents:"positive only",block:"(block*P,(block+1)*P]",within_block:"base phase b, then lexicographic t mod coordinate primes",not_numeric_order:true,class_bits:{plus_excluded:1,minus_excluded:2},zero_phase:"represents the right endpoint of its positive period block"},provenance:cp(input.provenance),construction:work};
}
function openIndex(saved){
 const index=cp(saved);if(index.schema!==SCHEMA)fail("schema");const B=int(index.base_period,"base period",1,LIMITS.base_period),P=natural(index.period,"period"),T=natural(index.coordinate_period,"coordinate period"),d=index.outer_prime_indices.length;
 if(P!==BigInt(B)*T||index.rows.length!==B||index.prefix.length!==B||index.crt.length!==d||index.coordinate_primes.length!==d||index.totals.length!==4)fail("shape");
 index.totals.forEach(x=>natural(x,"count"));
 index.cycles.forEach(c=>{if(c.period!==c.prime*(c.prime-1)||c.modulus!==c.prime*c.prime||c.entries.length!==c.period||c.terminal_power!==1)fail("cycle shape");c.entries.forEach(e=>{if(e.length!==4)fail("entry shape");for(let i=0;i<3;i++)int(e[i],"residue",0,c.modulus-1);int(e[3],"flag",0,3);});});
 index.rows.forEach((r,b)=>{if(r.base_phase!==b||r.flags.length!==d||r.suffix.length!==d+1||r.counts.length!==4)fail("row shape");int(r.base_mask,"base mask",0,3);r.flags.forEach((a,j)=>{if(a.length!==index.coordinate_primes[j])fail("coordinate shape");a.forEach(x=>int(x,"flag",0,3));});r.suffix.forEach(a=>{if(a.length!==4)fail("suffix input shape");a.forEach(v=>{if(v.length!==4)fail("suffix target shape");v.forEach(x=>natural(x,"suffix count"));});});});
 const work={base_rows_indexed:B,queries:0,cycle_lookups:0,coordinate_lookups:0,suffix_lookups:0,base_prefix_steps:0,crt_terms:0,new_modular_power_steps:0,new_suffix_cells:0,new_global_exponents_enumerated:0};
 function decompose(n){const value=natural(n,"positive exponent");if(value===0n)fail("positive exponent required");const phase=value%P,block=(value-1n)/P,b=Number(phase%BigInt(B)),t=(phase-BigInt(b))/BigInt(B),coords=index.coordinate_primes.map(p=>Number(t%BigInt(p))),row=index.rows[b];let mask=row.base_mask;coords.forEach((r,j)=>{mask|=row.flags[j][r];work.coordinate_lookups++;});return{value,phase,block,b,t,coords,mask};}
 function point(n){const x=decompose(n),witnesses=[];
  index.cycles.forEach(c=>{const phase=Number(x.value%BigInt(c.period)),e=c.entries[phase];work.cycle_lookups++;if(e[3]&1)witnesses.push({sign:"plus",prime:c.prime,prime_square:c.modulus,exponent_phase:phase,power_residue:e[0],shifted_residue:e[1]});if(e[3]&2)witnesses.push({sign:"minus",prime:c.prime,prime_square:c.modulus,exponent_phase:phase,power_residue:e[0],shifted_residue:e[2]});});
  return{exponent:n,period:index.period,period_block:x.block.toString(),phase:x.phase.toString(),base_phase:x.b,coordinate_residues:x.coords,class_mask:x.mask,plus_excluded:!!(x.mask&1),minus_excluded:!!(x.mask&2),witnesses,survival_means:"No selected prime supplies valuation-one obstruction; powerfulness unclassified."};
 }
 function select(mask,rank){
  int(mask,"class",0,3);const r=natural(rank,"rank"),total=BigInt(index.totals[mask]);if(total===0n)fail("empty class");const block=r/total,within=r%total;let lo=0,hi=B-1;
  while(lo<hi){work.base_prefix_steps++;const mid=(lo+hi)>>1;if(BigInt(index.prefix[mid][mask])>within)hi=mid;else lo=mid+1;}
  const b=lo,row=index.rows[b];let remaining=within-(b?BigInt(index.prefix[b-1][mask]):0n),incoming=row.base_mask;const coords=[];
  for(let j=0;j<d;j++){let found=false;for(let v=0;v<index.coordinate_primes[j];v++){const next=incoming|row.flags[j][v];work.coordinate_lookups++;const ways=BigInt(row.suffix[j+1][next][mask]);work.suffix_lookups++;if(remaining<ways){coords.push(v);incoming=next;found=true;break;}remaining-=ways;}if(!found)fail("saved selection counts inconsistent");}
  if(incoming!==mask||remaining!==0n)fail("saved terminal count inconsistent");let t=0n;for(let j=0;j<d;j++){t+=BigInt(coords[j])*BigInt(index.crt[j].coefficient);work.crt_terms++;}t%=T;const phase=BigInt(b)+BigInt(B)*t,n=block*P+(phase===0n?P:phase);
  if(n.toString().length>LIMITS.digits)fail("selected exponent exceeds decimal budget");
  return{class_mask:mask,rank,period_block:block.toString(),within_block_rank:within.toString(),base_phase:b,coordinate_residues:coords,phase:phase.toString(),exponent:n.toString(),order:index.ordering.within_block};
 }
 function rank(n){const x=decompose(n),row=index.rows[x.b];let r=x.b?BigInt(index.prefix[x.b-1][x.mask]):0n,incoming=row.base_mask;
  for(let j=0;j<d;j++){for(let v=0;v<x.coords[j];v++){const next=incoming|row.flags[j][v];work.coordinate_lookups++;r+=BigInt(row.suffix[j+1][next][x.mask]);work.suffix_lookups++;}incoming|=row.flags[j][x.coords[j]];work.coordinate_lookups++;}
  return{exponent:n,class_mask:x.mask,period_block:x.block.toString(),within_block_rank:r.toString(),rank:(x.block*BigInt(index.totals[x.mask])+r).toString(),order:index.ordering.within_block};
 }
 return{
  summary(){work.queries++;return cp({summary:index.summary,construction:index.construction,ordering:index.ordering});},
  cycle(prime){work.queries++;const c=index.cycles.find(c=>c.prime===prime);if(!c)fail("prime not indexed");return cp(c);},
  phase(b){work.queries++;return cp(index.rows[int(b,"phase",0,B-1)]);},
  point(n){work.queries++;return point(n);},
  select(mask,r){work.queries++;return select(mask,r);},
  rank(n){work.queries++;return rank(n);},
  page(mask,start,count){work.queries++;int(mask,"class",0,3);natural(start,"rank");int(count,"page",0,LIMITS.page);const r=BigInt(start),a=[];for(let j=0;j<count;j++)a.push(select(mask,(r+BigInt(j)).toString()));return a;},
  work(){return cp(work);}
 };
}
module.exports={SCHEMA,LIMITS,buildIndex,openIndex};
