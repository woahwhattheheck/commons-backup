"use strict";
function integer(s,positive=false){if(typeof s!=="string"||s.length>4096||! /^(0|[1-9][0-9]*)$/.test(s))throw new TypeError("canonical unsigned integer string");const n=BigInt(s);if(positive&&n===0n)throw new RangeError("positive integer");return n;}
function gcd(a,b){while(b){const t=a%b;a=b;b=t;}return a;}
function ratio(a,b){const g=gcd(a,b);return{numerator:String(a/g),denominator:String(b/g)};}
function clone(x){return JSON.parse(JSON.stringify(x));}
function buildIndex(input){
 const big=integer(input.M,true);if(big>1000000n)throw new RangeError("M<=1000000");const M=Number(big);
 const work={factor_trial_steps:0,factor_divisions:0,divisor_products:0,candidate_trial_divisions:0,prime_power_options:0,dp_cells:0,dp_option_visits:0,valid_transitions:0};
 let rem=M;const factors=[],factor_trace=[];
 for(let d=2;d*d<=rem;d++){
  const before=rem,remainders=[],quotients=[];work.factor_trial_steps++;
  while(rem%d===0){remainders.push(0);rem/=d;quotients.push(rem);work.factor_divisions++;}
  remainders.push(rem%d);factor_trace.push({d,before,remainders,quotients,after:rem});
  if(quotients.length)factors.push({prime:d,exponent:quotients.length});
 }
 if(rem>1)factors.push({prime:rem,exponent:1});
 let divisors=[1];for(const f of factors){const old=divisors.slice();let power=1;for(let e=1;e<=f.exponent;e++){power*=f.prime;for(const d of old){divisors.push(d*power);work.divisor_products++;}}}
 divisors.sort((a,b)=>a-b);const position=new Map(divisors.map((d,i)=>[d,i]));
 const candidates=[],primes=[];
 for(const d of divisors){
  const p=d+1,trials=[];let divisor=null;
  for(let k=2;k*k<=p;k++){const r=p%k;trials.push({divisor:k,remainder:r});work.candidate_trial_divisions++;if(!r){divisor=k;break;}}
  const record={id:candidates.length,predecessor:d,value:p,is_prime:divisor===null,least_divisor:divisor,trials};candidates.push(record);
  if(divisor===null){
   const options=[{exponent:0,phi_block:"1",n_block:"1"}];let e=1,w=d,n=BigInt(p);
   while(M%w===0){options.push({exponent:e,phi_block:String(w),n_block:String(n)});work.prime_power_options++;if(w>M/p)break;w*=p;n*=BigInt(p);e++;}
   primes.push({index:primes.length,prime:p,candidate_id:record.id,options});
  }
 }
 const rows=Array(primes.length+1);
 rows[primes.length]=divisors.map(d=>({count:d===1?"1":"0",minimum:d===1?"1":null,maximum:d===1?"1":null,min_option:null,max_option:null}));
 work.dp_cells+=divisors.length;
 for(let i=primes.length-1;i>=0;i--){
  rows[i]=divisors.map(d=>{
   let count=0n,minimum=null,maximum=null,min_option=null,max_option=null;
   primes[i].options.forEach((o,j)=>{
    work.dp_option_visits++;const w=Number(o.phi_block);if(d%w)return;
    const child=rows[i+1][position.get(d/w)];work.valid_transitions++;
    count+=BigInt(child.count);if(child.minimum===null)return;
    const lo=BigInt(o.n_block)*BigInt(child.minimum),hi=BigInt(o.n_block)*BigInt(child.maximum);
    if(minimum===null||lo<minimum){minimum=lo;min_option=j;}
    if(maximum===null||hi>maximum){maximum=hi;max_option=j;}
   });
   work.dp_cells++;return{count:String(count),minimum:minimum===null?null:String(minimum),maximum:maximum===null?null:String(maximum),min_option,max_option};
  });
 }
 const targets=divisors.map((d,i)=>({target:String(d),...rows[0][i],least_ratio:rows[0][i].minimum===null?null:ratio(BigInt(rows[0][i].minimum),BigInt(d))}));
 const total=targets.reduce((a,r)=>a+BigInt(r.count),0n);
 return{format:"complete-totient-divisor-fibers-v1",input:clone(input),M:String(M),factorization:factors,factor_trace,divisors:divisors.map(String),candidates,primes,suffix:rows,targets,summary:{targets:divisors.length,attained_targets:targets.filter(r=>r.minimum!==null).length,candidate_values:candidates.length,primes:primes.length,options:primes.reduce((a,p)=>a+p.options.length,0),represented_integers:String(total)},work};
}
function openIndex(s){
 if(!s||s.format!=="complete-totient-divisor-fibers-v1"||s.suffix.length!==s.primes.length+1)throw new TypeError("snapshot");
 const divisors=s.divisors.map(BigInt),positions=new Map(s.divisors.map((d,i)=>[d,i]));
 const primes=s.primes.map(p=>({...p,options:p.options.map(o=>({...o,w:BigInt(o.phi_block),n:BigInt(o.n_block)}))}));
 const work={queries:0,cell_reads:0,option_visits:0,product_multiplications:0,factor_divisions:0};
 function target(t){integer(t,true);if(!positions.has(t))throw new RangeError("target must divide saved M");return BigInt(t);}
 function cell(i,t){work.cell_reads++;return s.suffix[i][positions.get(String(t))];}
 function assemble(t,exponents,trace,rank){let n=1n;for(let i=0;i<primes.length;i++){n*=primes[i].options[exponents[i]].n;work.product_multiplications++;}return{target:String(t),n:String(n),exponents,rank:rank===undefined?undefined:String(rank),ratio:ratio(n,t),trace};}
 function select(t,r){
  let remaining=t,rank=r;const first=cell(0,t);if(rank<0n||rank>=BigInt(first.count))throw new RangeError("rank");
  const exponents=[],trace=[];
  for(let i=0;i<primes.length;i++){
   const before=remaining;let chosen=null,skipped=0n;
   for(let j=0;j<primes[i].options.length;j++){work.option_visits++;const o=primes[i].options[j];if(remaining%o.w)continue;const c=BigInt(cell(i+1,remaining/o.w).count);if(rank>=c){rank-=c;skipped+=c;}else{chosen=j;remaining/=o.w;break;}}
   if(chosen===null)throw new Error("saved selection invariant");exponents.push(chosen);trace.push({stage:i,prime:primes[i].prime,remaining_before:String(before),exponent:chosen,skipped:String(skipped),residual_rank:String(rank),remaining_after:String(remaining)});
  }
  if(remaining!==1n||rank!==0n)throw new Error("terminal selection");return assemble(t,exponents,trace,r);
 }
 function ranking(t,exponents){
  if(!Array.isArray(exponents)||exponents.length!==primes.length)throw new TypeError("full exponent vector");
  let remaining=t,rank=0n;const trace=[];
  for(let i=0;i<primes.length;i++){
   const e=exponents[i];if(!Number.isInteger(e)||e<0||e>=primes[i].options.length)throw new RangeError("exponent");
   const before=remaining;let skipped=0n;
   for(let j=0;j<e;j++){work.option_visits++;const o=primes[i].options[j];if(remaining%o.w===0n)skipped+=BigInt(cell(i+1,remaining/o.w).count);}
   const o=primes[i].options[e];if(remaining%o.w!==0n)throw new RangeError("wrong target");remaining/=o.w;rank+=skipped;
   if(cell(i+1,remaining).count==="0")throw new RangeError("empty suffix");
   trace.push({stage:i,prime:primes[i].prime,remaining_before:String(before),exponent:e,skipped:String(skipped),remaining_after:String(remaining)});
  }
  if(remaining!==1n)throw new RangeError("wrong target");return assemble(t,exponents,trace,rank);
 }
 function extreme(t,which){
  if(!["minimum","maximum"].includes(which))throw new TypeError("extreme");
  const first=cell(0,t);if(first[which]===null)return{target:String(t),kind:which,n:null};
  let remaining=t;const exponents=[],trace=[];
  for(let i=0;i<primes.length;i++){const c=cell(i,remaining),j=c[which==="minimum"?"min_option":"max_option"],o=primes[i].options[j];trace.push({stage:i,prime:primes[i].prime,exponent:j,remaining_before:String(remaining),saved_extreme:c[which]});exponents.push(j);remaining/=o.w;}
  const result=assemble(t,exponents,trace);if(result.n!==first[which]||remaining!==1n)throw new Error("extreme trace");return{kind:which,...result};
 }
 function query(q){work.queries++;switch(q.op){
  case"summary":return clone(s.summary);
  case"targets":return clone(s.targets);
  case"factorization":return clone({factorization:s.factorization,trace:s.factor_trace,divisors:s.divisors});
  case"candidates":return clone(s.candidates);
  case"primes":return clone(s.primes);
  case"fiber":{const t=target(q.target);return clone(s.targets[positions.get(String(t))]);}
  case"state":{const t=target(q.target);if(!Number.isInteger(q.stage)||q.stage<0||q.stage>primes.length)throw new RangeError("stage");return clone(cell(q.stage,t));}
  case"select":return select(target(q.target),integer(q.rank));
  case"rank":return ranking(target(q.target),q.exponents);
  case"extreme":return extreme(target(q.target),q.kind);
  case"page":{const t=target(q.target),start=integer(q.start),count=BigInt(cell(0,t).count);if(start>count||!Number.isInteger(q.limit)||q.limit<0||q.limit>1000)throw new RangeError("page");const out=[];for(let r=start;r<count&&out.length<q.limit;r++)out.push(select(t,r));return{target:q.target,start:q.start,records:out};}
  case"classify":{
   const n=integer(q.n,true);let remaining=n;const exponents=[];
   for(const p of primes){let e=0;const b=BigInt(p.prime);while(remaining%b===0n){remaining/=b;e++;work.factor_divisions++;}exponents.push(e);}
   if(remaining!==1n||exponents.some((e,i)=>e>=primes[i].options.length))return{n:q.n,in_saved_family:false,remaining:String(remaining),exponents};
   let phi=1n;for(let i=0;i<primes.length;i++){phi*=primes[i].options[exponents[i]].w;work.product_multiplications++;}
   if(!positions.has(String(phi)))return{n:q.n,in_saved_family:false,remaining:"1",exponents,phi:String(phi)};
   return{in_saved_family:true,...ranking(phi,exponents)};
  }
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>clone(work)};
}
module.exports={buildIndex,openIndex};
