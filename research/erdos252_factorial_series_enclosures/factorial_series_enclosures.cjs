"use strict";
// Exact positive-index divisor-power factorial series, no floating-point certificate.
const SCHEMA = "divisor-factorial-enclosures/v1";
const MAX_K = 12, MAX_N = 512, MAX_PLACES = 512;
function integer(x, lo, hi, name) {
  if (!Number.isSafeInteger(x) || x < lo || x > hi) throw new RangeError(name);
  return x;
}
function natural(x, name) {
  if (typeof x !== "string" || !/^(0|[1-9][0-9]*)$/.test(x) || x.length > 10000)
    throw new TypeError(name + " must be a bounded decimal string");
  return BigInt(x);
}
function signed(x, name) {
  if (typeof x !== "string" || !/^(0|-?[1-9][0-9]*)$/.test(x) || x.length > 10000)
    throw new TypeError(name + " must be a bounded signed decimal string");
  return BigInt(x);
}
function gcd(a,b) { while (b) { const t=a%b; a=b;b=t; } return a; }
function rational(a,b) {
  if (b <= 0n) throw new RangeError("positive denominator required");
  const g=gcd(a<0n?-a:a,b);
  return {numerator:(a/g).toString(),denominator:(b/g).toString()};
}
function pair(r) {
  const a=natural(r.numerator,"numerator"),b=natural(r.denominator,"denominator");
  if (!b) throw new RangeError("zero denominator");
  return [a,b];
}
function add(a,b) { const [p,q]=pair(a),[r,s]=pair(b); return rational(p*s+r*q,q*s); }
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function buildIndex(input) {
  if (!input || typeof input !== "object") throw new TypeError("input");
  const k=integer(input.k,1,MAX_K,"k"),N=integer(input.N,1,MAX_N,"N");
  const work={power_evaluations:0,divisor_visits:0,sigma_additions:0,
    factorial_multiplications:0,partial_recurrence_steps:0,tail_rows:0,unavailable_tail_rows:0};
  const powers=[null];
  for(let d=1;d<=N+2;d++){powers.push((BigInt(d)**BigInt(k)).toString());work.power_evaluations++;}
  const divisors=Array.from({length:N+1},()=>[]);
  const sigma=Array(N+1).fill(0n);
  for(let d=1;d<=N;d++)for(let n=d;n<=N;n+=d){
    divisors[n].push(d);sigma[n]+=BigInt(powers[d]);work.divisor_visits++;work.sigma_additions++;
  }
  const factorials=["1"]; let f=1n;
  for(let n=1;n<=N+1;n++){f*=BigInt(n);factorials.push(f.toString());work.factorial_multiplications++;}
  const rows=[null];let A=0n;
  for(let n=1;n<=N;n++){
    A=BigInt(n)*A+sigma[n];work.partial_recurrence_steps++;
    const lower=rational(A,BigInt(factorials[n]));
    const B=BigInt(n+1)*BigInt(powers[n+1]),C=BigInt(powers[n+2]);
    const rho=rational(C,B);
    let tail=null,upper=null,unavailable_reason=null;
    if(C<B){
      tail=rational(B*B,BigInt(factorials[n+1])*(B-C));
      upper=add(lower,tail);work.tail_rows++;
    }else{unavailable_reason="geometric_ratio_not_below_one";work.unavailable_tail_rows++;}
    rows.push({n,divisors:divisors[n],sigma:sigma[n].toString(),factorial:factorials[n],
      partial_numerator:A.toString(),lower,rho,tail,upper,unavailable_reason});
  }
  return {schema:SCHEMA,k,N,indexing:"n>=1",divisor_convention:"ordinary positive divisors, once each",
    powers,factorials,rows,provenance:copy(input.provenance||{}),
    limits:{max_k:MAX_K,max_N:MAX_N,max_places:MAX_PLACES},work};
}
function openIndex(saved) {
  // Shape validation only. Algebraic and divisor completeness certificates are not replayed.
  const data=copy(saved);
  if(data.schema!==SCHEMA||data.indexing!=="n>=1")throw new TypeError("schema/indexing");
  const k=integer(data.k,1,MAX_K,"k"),N=integer(data.N,1,MAX_N,"N");
  if(!Array.isArray(data.rows)||data.rows.length!==N+1||data.rows[0]!==null||
     !Array.isArray(data.powers)||data.powers.length!==N+3||
     !Array.isArray(data.factorials)||data.factorials.length!==N+2)throw new TypeError("shape");
  for(let n=1;n<=N;n++){
    const r=data.rows[n];if(!r||r.n!==n||!Array.isArray(r.divisors))throw new TypeError("row");
    let prev=0;for(const d of r.divisors){integer(d,1,n,"divisor label");if(d<=prev)throw new TypeError("divisor order");prev=d;}
    natural(r.sigma,"sigma");natural(r.factorial,"factorial");natural(r.partial_numerator,"partial_numerator");
    pair(r.lower);pair(r.rho);
    if(r.tail===null){if(r.upper!==null||r.unavailable_reason!=="geometric_ratio_not_below_one")throw new TypeError("unavailable tail");}
    else{pair(r.tail);pair(r.upper);if(r.unavailable_reason!==null)throw new TypeError("available tail");}
  }
  for(let d=1;d<data.powers.length;d++)natural(data.powers[d],"power");
  for(const f of data.factorials)natural(f,"factorial");
  const work={queries:0,saved_row_reads:0,power_evaluations:0,power_cache_hits:0,
    floor_divisions:0,cross_products:0,precision_probes:0,constructor_steps:0};
  const scales=new Map();
  const alphabet="0123456789abcdefghijklmnopqrstuvwxyz";
  function row(n){integer(n,1,N,"n");work.saved_row_reads++;return data.rows[n];}
  function scale(base,places){
    const key=base+":"+places;
    if(scales.has(key)){work.power_cache_hits++;return scales.get(key);}
    const value=BigInt(base)**BigInt(places);work.power_evaluations++;scales.set(key,value);return value;
  }
  function radix(z,base){
    if(z===0n)return "0";let s="";const b=BigInt(base);
    while(z){s=alphabet[Number(z%b)]+s;z/=b;}return s;
  }
  function digitResult(r,base,places){
    if(r.upper===null)return {status:"unavailable",reason:r.unavailable_reason,n:r.n,base,places};
    const sc=scale(base,places),[a,b]=pair(r.lower),[c,d]=pair(r.upper);
    const lo=a*sc/b,hi=c*sc/d;work.floor_divisions+=2;
    const result={status:lo===hi?"certified":"undecided",n:r.n,base,places,scale:sc.toString(),
      lower_scaled_floor:lo.toString(),upper_scaled_floor:hi.toString(),lower:r.lower,upper:r.upper};
    if(lo===hi){
      let s=radix(lo,base);
      if(places){s=s.padStart(places+1,"0");s=s.slice(0,-places)+"."+s.slice(-places);}
      result.radix_prefix=s;
      result.meaning="floor(series * base^places), certified by the saved closed interval";
    }
    return result;
  }
  function query(q){
    if(!q||typeof q!=="object")throw new TypeError("query");
    work.queries++;
    switch(q.op){
    case "summary":return copy({schema:SCHEMA,k,N,indexing:data.indexing,
      available_tail_rows:data.work.tail_rows,unavailable_tail_rows:data.work.unavailable_tail_rows,
      final_interval:{lower:data.rows[N].lower,upper:data.rows[N].upper},construction_work:data.work});
    case "term":{
      const r=row(q.n);
      return copy({...r,divisor_powers:r.divisors.map(d=>({divisor:d,power:data.powers[d]})),
        term:{numerator:r.sigma,denominator:r.factorial}});
    }
    case "interval":{
      const r=row(q.n===undefined?N:q.n);
      return copy({n:r.n,lower:r.lower,upper:r.upper,tail:r.tail,rho:r.rho,
        status:r.upper?"available":"unavailable",reason:r.unavailable_reason});
    }
    case "page":{
      const from=integer(q.from,1,N,"from"),limit=integer(q.limit,0,64,"limit");
      const end=Math.min(N+1,from+limit);const out=[];
      for(let n=from;n<end;n++)out.push(copy(row(n)));
      return {from,count:out.length,next:end<=N?end:null,rows:out};
    }
    case "digits":{
      const base=integer(q.base,2,36,"base"),places=integer(q.places,0,MAX_PLACES,"places");
      return copy(digitResult(row(q.n===undefined?N:q.n),base,places));
    }
    case "precision":{
      const base=integer(q.base,2,36,"base"),cap=integer(q.cap,0,MAX_PLACES,"cap"),r=row(q.n===undefined?N:q.n);
      const probes=[];
      function probe(d){const a=digitResult(r,base,d);work.precision_probes++;probes.push(a);return a.status==="certified";}
      if(!probe(0))return copy({status:r.upper?"undecided":"unavailable",n:r.n,base,cap,
        largest_certified_places:null,probes});
      let low=0,high=cap+1;
      while(high-low>1){const mid=Math.floor((low+high)/2);if(probe(mid))low=mid;else high=mid;}
      const winning=probes.find(p=>p.places===low);
      return copy({status:"certified",n:r.n,base,cap,largest_certified_places:low,
        cap_reached:low===cap,radix_prefix:winning.radix_prefix,probes});
    }
    case "compare":{
      const r=row(q.n===undefined?N:q.n),a=signed(q.numerator,"threshold numerator"),
        b=natural(q.denominator,"threshold denominator");
      if(!b)throw new RangeError("zero threshold denominator");
      if(!r.upper)return {status:"unavailable",reason:r.unavailable_reason,n:r.n};
      const [l,ld]=pair(r.lower),[u,ud]=pair(r.upper);
      const lower_difference=l*b-a*ld,upper_difference=u*b-a*ud;work.cross_products+=4;
      return copy({status:lower_difference>0n?"above":upper_difference<0n?"below":"undecided",
        n:r.n,threshold:rational(a,b),lower:r.lower,upper:r.upper,
        lower_cross_difference:lower_difference.toString(),upper_cross_difference:upper_difference.toString()});
    }
    default:throw new RangeError("unknown operation");
    }
  }
  return {query,work:()=>copy(work)};
}
module.exports={buildIndex,openIndex,SCHEMA};
