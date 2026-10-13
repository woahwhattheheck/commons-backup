"use strict";

/* Exact zero-class covering wheel and CRT phase navigation; no primality claims. */
const COVERING_LIMITS=Object.freeze({
  max_moduli:16,max_modulus_product:1000000,max_gap:1024,
  max_snapshot_chars:8000000,max_slice_intervals:500000,
  max_integer_digits:1000,max_page_rows:32,max_provenance_chars:16384
});
const WHEEL="commons.residue_covering_wheel/v1",SLICE="commons.residue_covering_slice/v1";
function fail(s){throw new RangeError(s);}
function small(v,name,lo,hi){
  if(typeof v!=="number"||!Number.isSafeInteger(v)||v<lo||v>hi)fail(name+" outside integer bounds");
  return v;
}
function integer(v,name,nonnegative=false){
  if(typeof v==="number"){
    if(!Number.isSafeInteger(v))fail(name+" must be exact");v=String(v);
  }else if(typeof v==="bigint")v=v.toString();
  if(typeof v!=="string"||v.replace("-","").length>COVERING_LIMITS.max_integer_digits||
     !/^(0|-?[1-9][0-9]*)$/.test(v))fail(name+" must be a canonical bounded integer");
  const b=BigInt(v);if(nonnegative&&b<0n)fail(name+" must be nonnegative");return b;
}
function clone(x){return JSON.parse(JSON.stringify(x));}
function provenance(v){
  if(v===undefined)return null;
  const t=JSON.stringify(v);
  if(typeof t!=="string"||t.length>COVERING_LIMITS.max_provenance_chars)fail("provenance cap");
  return JSON.parse(t);
}
function gcd(a,b,w){while(b){const r=a%b;a=b;b=r;if(w)w.gcd_divisions++;}return a;}
function inverse(a,m,w){
  let r0=m,r1=a,s0=0,s1=1;
  while(r1){const q=Math.floor(r0/r1);[r0,r1]=[r1,r0-q*r1];[s0,s1]=[s1,s0-q*s1];w.inverse_divisions++;}
  if(r0!==1)fail("inverse not defined");return((s0%m)+m)%m;
}
function checkModuli(values){
  if(!Array.isArray(values)||!values.length||values.length>COVERING_LIMITS.max_moduli)fail("moduli count");
  let product=1,previous=1;
  const moduli=values.map(m=>{
    small(m,"modulus",2,COVERING_LIMITS.max_modulus_product);
    if(m<=previous)fail("moduli must be strictly increasing");previous=m;
    product*=m;if(product>COVERING_LIMITS.max_modulus_product)fail("period cap");return m;
  });
  return{moduli,product};
}
function compileResidueCoverings(options){
  if(!options||typeof options!=="object")fail("options required");
  const{moduli,product:P}=checkModuli(options.moduli);
  const work={compiler_calls:1,gcd_divisions:0,inverse_divisions:0,
    marking_visits:0,newly_marked_residues:0,residue_positions_scanned:0,
    gap_rows:0,profile_rows:0,assignment_vectors_enumerated:0,prime_tests:0};
  for(let i=0;i<moduli.length;i++)for(let j=0;j<i;j++)
    if(gcd(moduli[i],moduli[j],work)!==1)fail("moduli must be pairwise coprime");
  const crt=moduli.map(m=>{
    const cofactor=P/m,inv=inverse(cofactor%m,m,work);
    return{modulus:m,cofactor,inverse:inv,coefficient:cofactor*inv};
  });
  const blocked=new Uint8Array(P);
  for(const m of moduli)for(let r=0;r<P;r+=m){
    work.marking_visits++;
    if(!blocked[r]){blocked[r]=1;work.newly_marked_residues++;}
  }
  const survivors=[];
  for(let r=0;r<P;r++){work.residue_positions_scanned++;if(!blocked[r])survivors.push(r);}
  if(survivors[0]!==1||survivors[survivors.length-1]!==P-1)fail("unexpected zero-free endpoints");
  const gaps=survivors.map((r,i)=>{work.gap_rows++;return(i+1<survivors.length?survivors[i+1]:P+survivors[0])-r;});
  let maximum=0;for(const g of gaps)if(g>maximum)maximum=g;
  if(maximum>COVERING_LIMITS.max_gap)fail("gap cap");
  const histogram=Array(maximum+1).fill(0);
  for(const g of gaps)histogram[g]++;
  const counts=Array(maximum+1).fill(0);
  let active=0,sum=0;
  for(let y=maximum;y>=0;y--){
    if(y+1<=maximum){active+=histogram[y+1];sum+=(y+1)*histogram[y+1];}
    counts[y]=sum-y*active;work.profile_rows++;
  }
  if(counts[0]!==P)fail("phase partition");
  const snapshot={schema:WHEEL,moduli,period:P,crt,survivors,gap_lengths:gaps,
    gap_histogram:histogram,cover_counts:counts,maximum_gap:maximum,
    maximum_coverage:maximum-1,ordering:"increasing CRT phase t in [0,P)",
    assignment:"a_m = -t mod m",provenance:provenance(options.provenance)};
  const text=JSON.stringify(snapshot);
  if(text.length>COVERING_LIMITS.max_snapshot_chars)fail("snapshot cap");
  return{status:"EXACT_COVERING_WHEEL",snapshot,work,snapshot_chars:text.length};
}
function parseSnapshot(value,schema){
  const text=typeof value==="string"?value:JSON.stringify(value);
  if(typeof text!=="string"||text.length>COVERING_LIMITS.max_snapshot_chars)fail("snapshot cap");
  const s=JSON.parse(text);if(!s||s.schema!==schema)fail("schema");return s;
}
function structuralCrt(s){
  const{moduli,product}=checkModuli(s.moduli);
  if(s.period!==product||!Array.isArray(s.crt)||s.crt.length!==moduli.length)fail("CRT shape");
  s.crt.forEach((row,i)=>{
    if(row.modulus!==moduli[i]||row.cofactor!==product/moduli[i])fail("CRT row");
    small(row.inverse,"saved inverse",0,row.modulus-1);
    if(row.coefficient!==row.cofactor*row.inverse)fail("CRT coefficient");
  });
  return product;
}
function phaseResidues(t,moduli){return moduli.map(m=>(m-(t%m))%m);}
function encode(residues,s,stats){
  if(!Array.isArray(residues)||residues.length!==s.moduli.length)fail("residue vector length");
  let total=0n;
  residues.forEach((a,i)=>{
    small(a,"residue",0,s.moduli[i]-1);
    total-=BigInt(a)*BigInt(s.crt[i].coefficient);stats.crt_terms++;
  });
  const p=BigInt(s.period);return Number((total%p+p)%p);
}
function openRetainedCoveringWheel(value){
  const s=parseSnapshot(value,WHEEL),P=structuralCrt(s);
  if(s.ordering!=="increasing CRT phase t in [0,P)"||s.assignment!=="a_m = -t mod m")fail("wheel conventions");
  if(!Array.isArray(s.survivors)||!s.survivors.length||s.survivors.length>P||
     !Array.isArray(s.gap_lengths)||s.gap_lengths.length!==s.survivors.length)fail("gap table");
  const max=small(s.maximum_gap,"maximum gap",1,COVERING_LIMITS.max_gap);
  if(s.maximum_coverage!==max-1||!Array.isArray(s.cover_counts)||s.cover_counts.length!==max+1||
     !Array.isArray(s.gap_histogram)||s.gap_histogram.length!==max+1)fail("profile shape");
  const stats={queries:0,saved_gap_relations_checked:0,saved_profile_fields:0,
    gap_rows_scanned_for_slices:0,slice_intervals_created:0,
    binary_comparisons:0,witness_modulus_tests:0,witness_rows_created:0,
    crt_terms:0,compiler_calls:0,marking_visits:0,prime_tests:0};
  let prior=0,sum=0;
  for(let i=0;i<s.survivors.length;i++){
    const r=small(s.survivors[i],"survivor",1,P-1);
    if(r<=prior)fail("survivor ordering");prior=r;
    const next=i+1<s.survivors.length?s.survivors[i+1]:P+s.survivors[0];
    const g=small(s.gap_lengths[i],"gap",1,max);
    if(next-r!==g)fail("saved gap relation");
    sum+=g;stats.saved_gap_relations_checked++;
  }
  if(s.survivors[0]!==1||prior!==P-1||sum!==P)fail("gap endpoints");
  for(let y=0;y<=max;y++){
    small(s.cover_counts[y],"cover count",0,P);
    small(s.gap_histogram[y],"histogram count",0,P);stats.saved_profile_fields+=2;
  }
  if(s.cover_counts[0]!==P||s.cover_counts[max]!==0)fail("profile endpoints");
  provenance(s.provenance);
  function classify(shift){
    const t=integer(shift,"shift"),p=BigInt(P),phase=Number((t%p+p)%p);
    let lo=0,hi=s.survivors.length;
    while(lo<hi){const mid=(lo+hi)>>1;stats.binary_comparisons++;
      if(s.survivors[mid]<=phase)lo=mid+1;else hi=mid;}
    const next=lo<s.survivors.length?s.survivors[lo]:P+s.survivors[0],
      first=next-phase,witnesses=[];
    for(let offset=1;offset<first;offset++){
      const v=t+BigInt(offset);let selected=null;
      for(const modulus of s.moduli){
        stats.witness_modulus_tests++;
        if(v%BigInt(modulus)===0n){selected=modulus;break;}
      }
      if(selected===null)fail("saved coverage contradicts moduli");
      witnesses.push({offset,modulus:selected,integer:v.toString(),
        quotient:(v/BigInt(selected)).toString()});stats.witness_rows_created++;
    }
    const v=t+BigInt(first),remainders=s.moduli.map(modulus=>{
      const m=BigInt(modulus),remainder=Number((v%m+m)%m);
      stats.witness_modulus_tests++;if(remainder===0)fail("saved first survivor contradicts moduli");
      return{modulus,remainder};
    });
    return{shift:t.toString(),phase,residues:phaseResidues(phase,s.moduli),
      covered_length:first-1,covered:witnesses,
      first_uncovered:{offset:first,integer:v.toString(),remainders}};
  }
  return Object.freeze({
    summary(){stats.queries++;return{schema:WHEEL,moduli:s.moduli.slice(),period:P,
      survivors:s.survivors.length,maximum_gap:max,maximum_coverage:max-1,
      complete_residue_assignments:P,ordering:s.ordering,
      validation:"saved structure/gap relations only; sieve completeness and CRT inverses are premises"};},
    source(){stats.queries++;return clone(s.provenance);},
    profile(){stats.queries++;return s.cover_counts.map((count,y)=>({covered_prefix:y,count,gaps_of_length_y:s.gap_histogram[y]}));},
    crt(){stats.queries++;return clone(s.crt);},
    count(y){stats.queries++;const b=integer(y,"covered prefix",true);return{covered_prefix:b.toString(),count:b>=BigInt(max)?0:s.cover_counts[Number(b)]};},
    classifyShift(t){stats.queries++;return classify(t);},
    classifyResidues(a){stats.queries++;return classify(encode(a,s,stats));},
    slice(y){
      stats.queries++;const b=integer(y,"covered prefix",true),intervals=[];
      let total=0;
      if(b===0n){intervals.push([0,P-1,0]);total=P;stats.slice_intervals_created++;}
      else if(b<BigInt(max)){
        const threshold=Number(b);
        for(let i=0;i<s.survivors.length;i++){
          stats.gap_rows_scanned_for_slices++;
          const length=s.gap_lengths[i]-threshold;
          if(length>0){intervals.push([s.survivors[i],s.survivors[i]+length-1,total]);
            total+=length;stats.slice_intervals_created++;}
        }
      }
      if(intervals.length>COVERING_LIMITS.max_slice_intervals)fail("slice interval cap");
      return{schema:SLICE,moduli:s.moduli.slice(),period:P,crt:clone(s.crt),
        covered_prefix:b.toString(),total,intervals,ordering:s.ordering,
        provenance:{wheel_schema:WHEEL,wheel_provenance:clone(s.provenance),
          completeness:"Derived from all saved gap rows; original sieve completeness remains a premise."}};
    },
    snapshot(){stats.queries++;return clone(s);},
    statistics(){return clone(stats);}
  });
}
function openRetainedCoverageSlice(value){
  const s=parseSnapshot(value,SLICE),P=structuralCrt(s);
  if(s.ordering!=="increasing CRT phase t in [0,P)")fail("slice ordering");
  integer(s.covered_prefix,"covered prefix",true);
  small(s.total,"total",0,P);
  if(!Array.isArray(s.intervals)||s.intervals.length>COVERING_LIMITS.max_slice_intervals)fail("interval table");
  const stats={queries:0,saved_interval_rows:0,binary_comparisons:0,crt_terms:0,
    selected_assignments:0,page_rows_returned:0,wheel_gap_scans:0,marking_visits:0};
  let count=0,last=-1;
  for(const row of s.intervals){
    if(!Array.isArray(row)||row.length!==3)fail("interval row");
    const start=small(row[0],"start",0,P-1),end=small(row[1],"end",start,P-1);
    if(start<=last||row[2]!==count)fail("interval order/cumulative count");
    count+=end-start+1;last=end;stats.saved_interval_rows++;
  }
  if(count!==s.total)fail("slice count");
  function selection(input){
    const b=integer(input,"rank",true);
    if(b>=BigInt(s.total))fail("rank out of range");
    const rank=Number(b);let lo=0,hi=s.intervals.length;
    while(lo<hi){const mid=(lo+hi)>>1;stats.binary_comparisons++;
      if(s.intervals[mid][2]<=rank)lo=mid+1;else hi=mid;}
    const row=s.intervals[lo-1],phase=row[0]+rank-row[2];
    stats.selected_assignments++;
    return{rank,phase,residues:phaseResidues(phase,s.moduli)};
  }
  function phaseRank(phase){
    small(phase,"phase",0,P-1);let lo=0,hi=s.intervals.length;
    while(lo<hi){const mid=(lo+hi)>>1;stats.binary_comparisons++;
      if(s.intervals[mid][0]<=phase)lo=mid+1;else hi=mid;}
    if(lo===0)return{phase,covered:false,rank:null,insertion_rank:0};
    const row=s.intervals[lo-1],inside=phase<=row[1],
      before=row[2]+Math.min(phase-row[0],row[1]-row[0]+1);
    return{phase,covered:inside,rank:inside?before:null,insertion_rank:before};
  }
  return Object.freeze({
    summary(){stats.queries++;return{schema:SLICE,period:P,covered_prefix:s.covered_prefix,
      total:s.total,intervals:s.intervals.length,ordering:s.ordering,
      validation:"interval structure only; wheel-derived completeness is a premise"};},
    source(){stats.queries++;return clone(s.provenance);},
    select(rank){stats.queries++;return selection(rank);},
    rankPhase(phase){stats.queries++;return phaseRank(phase);},
    rankResidues(residues){stats.queries++;return phaseRank(encode(residues,s,stats));},
    page(options={}){
      stats.queries++;const b=integer(options.start===undefined?0:options.start,"start",true);
      if(b>BigInt(s.total))fail("page start beyond total");
      const limit=small(options.limit===undefined?16:options.limit,"limit",0,COVERING_LIMITS.max_page_rows),
        start=Number(b),records=[];
      for(let rank=start;rank<s.total&&records.length<limit;rank++)records.push(selection(rank));
      stats.page_rows_returned+=records.length;
      const next=start+records.length;
      return{start,total:s.total,records,next_start:next<s.total?next:null};
    },
    snapshot(){stats.queries++;return clone(s);},
    statistics(){return clone(stats);}
  });
}
module.exports={COVERING_LIMITS,compileResidueCoverings,
  openRetainedCoveringWheel,openRetainedCoverageSlice};
