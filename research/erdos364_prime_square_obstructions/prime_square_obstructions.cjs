"use strict";
const SCHEMA="consecutive-powerful-palette/v1";
function small(x,name,min,max){if(!Number.isSafeInteger(x)||x<min||x>max)throw new RangeError(name);return x;}
function integer(x,name,positive=false){if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x))throw new TypeError(name+" must be decimal");const n=BigInt(x);if(positive&&n===0n)throw new RangeError(name+" must be positive");return n;}
function construct(input){
 const primes=input.primes;
 if(!Array.isArray(primes)||primes.length<1||primes.length>12)throw new RangeError("one through twelve supplied prime premises");
 primes.forEach((p,i)=>{small(p,"prime premise",2,97);if(i&&p<=primes[i-1])throw new RangeError("strictly increasing prime premises");});
 const maxRows=small(input.max_local_rows===undefined?10000:input.max_local_rows,"max_local_rows",1,100000);
 const work={modulus_products:0,period_products:0,local_rows:0,prime_remainders:0,square_remainders:0,histogram_increments:0,
 crt_cofactor_divisions:0,euclidean_divisions:0,crt_weight_products:0,suffix_cells:0,weighted_suffix_products:0,suffix_additions:0,
 primality_tests:0,phase_enumerations:0,integer_factorizations:0};
 const moduli=primes.map(p=>{++work.modulus_products;return p*p;});
 if(moduli.reduce((a,b)=>a+b,0)>maxRows)throw new RangeError("local row cap");
 let period=1n;
 for(const m of moduli){period*=BigInt(m);++work.period_products;}
 function inverse(a,m){
  let r0=a,r1=m,s0=1n,s1=0n;
  while(r1){const q=r0/r1;++work.euclidean_divisions;[r0,r1]=[r1,r0-q*r1];[s0,s1]=[s1,s0-q*s1];}
  if(r0!==1n)throw new RangeError("moduli not pairwise coprime");
  return (s0%m+m)%m;
 }
 const crt=moduli.map(m=>{
  const cofactor=period/BigInt(m);++work.crt_cofactor_divisions;
  const inv=inverse(cofactor,BigInt(m)),weight=cofactor*inv;++work.crt_weight_products;
  return {modulus:m,cofactor:cofactor.toString(),inverse:inv.toString(),weight:weight.toString()};
 });
 const local=primes.map((p,index)=>{
  const modulus=moduli[index],masks=[],histogram=Array(8).fill(0);
  for(let r=0;r<modulus;r++){
   ++work.local_rows;let mask=0;
   for(let offset=0;offset<3;offset++){
    ++work.prime_remainders;
    if((r+offset)%p===0){++work.square_remainders;if((r+offset)%modulus!==0)mask|=1<<offset;}
   }
   masks.push(mask);++histogram[mask];++work.histogram_increments;
  }
  return {prime:p,modulus,masks,histogram};
 });
 const suffix=Array(primes.length+1);
 suffix[primes.length]=["1","0","0","0","0","0","0","0"];work.suffix_cells+=8;
 for(let i=primes.length-1;i>=0;i--){
  const row=Array(8).fill(0n);
  for(let a=0;a<8;a++)if(local[i].histogram[a])
   for(let b=0;b<8;b++)if(suffix[i+1][b]!=="0"){
    row[a|b]+=BigInt(local[i].histogram[a])*BigInt(suffix[i+1][b]);
    ++work.weighted_suffix_products;++work.suffix_additions;
   }
  suffix[i]=row.map(String);work.suffix_cells+=8;
 }
 return {schema:SCHEMA,primes:primes.slice(),offsets:[0,1,2],moduli,period:period.toString(),crt,local,suffix,
  exact_mask_counts:suffix[0],order:"lexicographic residue coordinates modulo p^2 in ascending supplied-prime order",
  domain:"positive starts n; bit i certifies n+i is not powerful for offset i=0,1,2",
  survivor_meaning:"no exponent-one obstruction from this finite prime palette; unresolved powerfulness",
  prime_contract:"Supplied values are distinct primes by the identified input premise; no primality test is performed.",
  limits:{max_primes:12,max_prime:97,max_local_rows:maxRows},provenance:input.provenance||{},work};
}
function open(snapshot){
 if(!snapshot||snapshot.schema!==SCHEMA||!Array.isArray(snapshot.primes)||snapshot.primes.length<1)throw new TypeError("snapshot");
 const k=snapshot.primes.length,period=integer(snapshot.period,"period",true);
 if(snapshot.local.length!==k||snapshot.crt.length!==k||snapshot.suffix.length!==k+1)throw new TypeError("array shape");
 for(let i=0;i<k;i++){
  if(snapshot.local[i].masks.length!==snapshot.moduli[i]||snapshot.local[i].histogram.length!==8||snapshot.suffix[i].length!==8)throw new TypeError("local shape");
 }
 if(snapshot.suffix[k].length!==8)throw new TypeError("terminal shape");
 const work={queries:0,local_row_reads:0,saved_coefficient_reads:0,coefficient_sums:0,selection_branches:0,rank_branches:0,
 rank_additions:0,rank_subtractions:0,crt_products:0,crt_additions:0,crt_reductions:0,translation_products:0,translation_additions:0,
 input_residue_reductions:0,witness_value_additions:0,witness_prime_quotients:0,witness_square_quotients:0,witness_square_remainders:0,
 construction_calls:0,new_local_predicates:0,new_suffix_coefficients:0,primality_tests:0,integer_factorizations:0};
 function condition(options={}){
  const mustFail=small(options.must_fail===undefined?0:options.must_fail,"must_fail",0,7);
  const mustSurvive=small(options.must_survive===undefined?0:options.must_survive,"must_survive",0,7);
  if(mustFail&mustSurvive)throw new RangeError("contradictory mask condition");
  const prefix=options.prefix_residues===undefined?[]:options.prefix_residues;
  if(!Array.isArray(prefix)||prefix.length>k)throw new RangeError("prefix_residues");
  let mask=0;
  prefix.forEach((r,i)=>{small(r,"prefix residue",0,snapshot.moduli[i]-1);mask|=snapshot.local[i].masks[r];++work.local_row_reads;});
  return {must_fail:mustFail,must_survive:mustSurvive,prefix_residues:prefix.slice(),prefix_mask:mask};
 }
 function allowed(mask,c){return (mask&c.must_fail)===c.must_fail&&(mask&c.must_survive)===0;}
 function completions(i,mask,c){
  let count=0n;
  for(let tail=0;tail<8;tail++){
   ++work.saved_coefficient_reads;
   if(allowed(mask|tail,c)){count+=BigInt(snapshot.suffix[i][tail]);++work.coefficient_sums;}
  }
  return count;
 }
 function phase(coordinates){
  let value=0n;
  for(let i=0;i<k;i++){value+=BigInt(coordinates[i])*BigInt(snapshot.crt[i].weight);++work.crt_products;++work.crt_additions;}
  ++work.crt_reductions;return value%period;
 }
 function materialize(coordinates,mask,cycles){
  const residue=phase(coordinates),base=residue===0n?period:residue;
  ++work.translation_products;++work.translation_additions;
  return {coordinates,mask,phase:residue.toString(),least_positive_start:base.toString(),cycles:cycles.toString(),n:(base+period*cycles).toString()};
 }
 function selectCore(rank,c,cycles){
  const count=completions(c.prefix_residues.length,c.prefix_mask,c);
  if(rank>=count)throw new RangeError("rank outside conditioned family");
  const coordinates=c.prefix_residues.slice();let mask=c.prefix_mask,r=rank;
  for(let i=coordinates.length;i<k;i++){
   let chosen=false;
   for(let residue=0;residue<snapshot.moduli[i];residue++){
    ++work.selection_branches;++work.local_row_reads;
    const nextMask=mask|snapshot.local[i].masks[residue],w=completions(i+1,nextMask,c);
    if(r<w){coordinates.push(residue);mask=nextMask;chosen=true;break;}
    r-=w;++work.rank_subtractions;
   }
   if(!chosen)throw new Error("saved counts do not select");
  }
  return Object.assign({rank:rank.toString(),count:count.toString(),condition:c},materialize(coordinates,mask,cycles));
 }
 function coordinatesOf(n){return snapshot.moduli.map(m=>{++work.input_residue_reductions;return Number(n%BigInt(m));});}
 function rankCore(n,c){
  const coordinates=coordinatesOf(n);
  if(c.prefix_residues.some((r,i)=>coordinates[i]!==r))return {member:false,rank:null,coordinates,reason:"prefix mismatch"};
  let mask=c.prefix_mask,rank=0n;
  for(let i=c.prefix_residues.length;i<k;i++){
   for(let r=0;r<coordinates[i];r++){
    ++work.rank_branches;++work.local_row_reads;
    rank+=completions(i+1,mask|snapshot.local[i].masks[r],c);++work.rank_additions;
   }
   mask|=snapshot.local[i].masks[coordinates[i]];++work.local_row_reads;
  }
  if(!allowed(mask,c))return {member:false,rank:null,coordinates,mask,reason:"mask condition"};
  return {member:true,rank:rank.toString(),coordinates,mask,count:completions(c.prefix_residues.length,c.prefix_mask,c).toString(),condition:c};
 }
 const api={
  summary(){++work.queries;return {primes:snapshot.primes,offsets:snapshot.offsets,period:snapshot.period,
   exact_mask_counts:snapshot.exact_mask_counts,order:snapshot.order,survivor_meaning:snapshot.survivor_meaning,construction_work:snapshot.work};},
  family(options){++work.queries;const c=condition(options);return {condition:c,count:completions(c.prefix_residues.length,c.prefix_mask,c).toString()};},
  select(rank,options,cycles="0"){++work.queries;return selectCore(integer(rank,"rank"),condition(options),integer(cycles,"cycles"));},
  rank(n,options){++work.queries;return rankCore(integer(n,"n",true),condition(options));},
  page(start,limit,options,cycles="0"){
   ++work.queries;const c=condition(options),r=integer(start,"start"),q=integer(cycles,"cycles"),count=completions(c.prefix_residues.length,c.prefix_mask,c);
   small(limit,"limit",0,100);if(r>count)throw new RangeError("page start");
   const rows=[];for(let j=0;j<limit&&r+BigInt(j)<count;j++)rows.push(selectCore(r+BigInt(j),c,q));
   return {condition:c,count:count.toString(),start:r.toString(),rows,next_rank:(r+BigInt(rows.length)).toString(),complete:r+BigInt(rows.length)===count};
  },
  local(index){++work.queries;small(index,"index",0,k-1);return snapshot.local[index];},
  witness(n){
   ++work.queries;const value=integer(n,"n",true),coordinates=coordinatesOf(value),records=[];let mask=0;
   for(let i=0;i<k;i++){
    const localMask=snapshot.local[i].masks[coordinates[i]],p=BigInt(snapshot.primes[i]),square=BigInt(snapshot.moduli[i]);
    ++work.local_row_reads;mask|=localMask;
    for(let offset=0;offset<3;offset++)if(localMask&(1<<offset)){
     const shifted=value+BigInt(offset);++work.witness_value_additions;
     const q=shifted/p,squareQ=shifted/square,remainder=shifted%square;
     ++work.witness_prime_quotients;++work.witness_square_quotients;++work.witness_square_remainders;
     records.push({offset,prime:snapshot.primes[i],value:shifted.toString(),prime_quotient:q.toString(),square_quotient:squareQ.toString(),square_remainder:remainder.toString()});
    }
   }
   return {n,coordinates,mask,records,surviving_offsets:[0,1,2].filter(i=>(mask&(1<<i))===0),
    survivor_meaning:snapshot.survivor_meaning};
  },
  work(){return Object.assign({},work);}
 };
 return api;
}
module.exports={SCHEMA,construct,open};
