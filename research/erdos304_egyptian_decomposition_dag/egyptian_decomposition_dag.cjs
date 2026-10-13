"use strict";
const clone=x=>JSON.parse(JSON.stringify(x));
function decimal(s,name){if(typeof s!=="string"||!/^(0|[1-9]\d*)$/.test(s))throw new TypeError(name+" canonical decimal string");return BigInt(s);}
function integer(x,name,a,b){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(name);return x;}
function compile(input){
 const L=input.limits;
 if(!L||L.max_input_denominator!==1000||L.max_terms!==5||L.max_nodes!==20000||L.max_prefix_candidates!==100000||L.max_trial_divisions!==500000||L.max_divisor_cells!==1000000||L.max_two_term_candidates!==200000)throw new Error("explicit limits required");
 if(typeof input.numerator!=="string"||typeof input.denominator!=="string"||input.numerator.length>4||input.denominator.length>4)throw new Error("input integer length");
 let a=decimal(input.numerator,"a"),b=decimal(input.denominator,"b");
 if(a<1n||a>=b||b>1000n||input.min_denominator!=="2")throw new RangeError("positive proper input and denominator>1 required");
 const K=integer(input.max_terms,"max terms",1,5);
 const work={states:0,memo_hits:0,gcd_divisions:0,prefix_candidates:0,one_term_decisions:0,two_term_candidates:0,two_term_accepts:0,factorizations:0,factor_cache_hits:0,factor_trial_divisions:0,factor_exact_divisions:0,divisor_cells:0,divisor_power_products:0,branch_prefix_additions:0,old_input_calculations_replayed:0};
 function gcd(x,y){while(y){[x,y]=[y,x%y];work.gcd_divisions++;}return x;}
 const initialG=gcd(a,b);a/=initialG;b/=initialG;
 const factorizations=[],factorCache=new Map(),nodes=[],memo=new Map();
 function divisorTable(d){
  const key=String(d);if(factorCache.has(key)){work.factor_cache_hits++;return factorizations[factorCache.get(key)];}
  let n=d;const factors=[];
  for(let p=2n;p*p<=n;p=p===2n?3n:p+2n){let e=0;for(;;){if(++work.factor_trial_divisions>L.max_trial_divisions)throw new Error("trial division cap");if(n%p!==0n)break;n/=p;e++;work.factor_exact_divisions++;}if(e)factors.push({prime:String(p),exponent:e});}
  if(n>1n)factors.push({prime:String(n),exponent:1});
  let divisors=[1n];if(++work.divisor_cells>L.max_divisor_cells)throw new Error("divisor cell cap");
  for(const f of factors){const old=divisors.slice(),p=BigInt(f.prime);let power=1n;for(let e=1;e<=2*f.exponent;e++){power*=p;work.divisor_power_products++;for(const d0 of old){if(++work.divisor_cells>L.max_divisor_cells)throw new Error("divisor cell cap");divisors.push(d0*power);}}}
  divisors.sort((x,y)=>x<y?-1:x>y?1:0);
  const id=factorizations.length,out={id,denominator:key,factors,square_divisors:divisors.map(String)};
  factorizations.push(out);factorCache.set(key,id);work.factorizations++;return out;
 }
 function solve(a,b,min,r){
  const key=[a,b,min,r].join(",");if(memo.has(key)){work.memo_hits++;return memo.get(key);}
  if(++work.states>L.max_nodes)throw new Error("node cap");
  const out={id:null,a:String(a),b:String(b),min_denominator:String(min),terms:r,kind:r===1?"one":r===2?"two":"prefix",bounds:null,reason:null,factorization_id:null,candidates:[],branches:[],prefix:["0"],count:"0"};
  if(r===1){work.one_term_decisions++;if(b%a!==0n)out.reason="nonintegral final denominator";else{const d=b/a;if(d<min)out.reason="final denominator below minimum";else out.branches.push({denominators:[String(d)],child:null,count:"1"});}}
  else{
   const first=b/a+1n,lo=min>first?min:first,hi=BigInt(r)*b/a;
   out.bounds={lo:String(lo),hi:String(hi)};
   if(lo>hi)out.reason="empty necessary first-denominator range";
   else if(r===2){
    const table=divisorTable(b);out.factorization_id=table.id;const square=b*b;
    for(const text of table.square_divisors){const t=BigInt(text);if(t>=b)break;
     if(++work.two_term_candidates>L.max_two_term_candidates)throw new Error("two-term candidate cap");
     const s=square/t,nx=b+t,ny=b+s,rx=nx%a,ry=ny%a;
     const c={factor:text,cofactor:String(s),first_remainder:String(rx),second_remainder:String(ry),denominators:null,accepted:false,reason:null};
     if(rx!==0n||ry!==0n)c.reason="nonintegral denominator";
     else{const x=nx/a,y=ny/a;c.denominators=[String(x),String(y)];
      if(x<min)c.reason="first denominator below minimum";
      else if(x>=y)c.reason="denominators not strictly increasing";
      else{c.accepted=true;work.two_term_accepts++;out.branches.push({denominators:c.denominators,child:null,count:"1"});}
     }out.candidates.push(c);
    }
   }else{
    for(let x=lo;x<=hi;x++){
     if(++work.prefix_candidates>L.max_prefix_candidates)throw new Error("prefix candidate cap");
     let na=a*x-b,nb=b*x;const g=gcd(na,nb);na/=g;nb/=g;
     const child=solve(na,nb,x+1n,r-1),count=nodes[child].count;
     out.candidates.push({denominator:String(x),residual_a:String(na),residual_b:String(nb),child,count});
     if(count!=="0")out.branches.push({denominators:[String(x)],child,count});
    }
   }
  }
  let sum=0n;for(const branch of out.branches){sum+=BigInt(branch.count);out.prefix.push(String(sum));work.branch_prefix_additions++;}
  out.count=String(sum);out.id=nodes.length;nodes.push(out);memo.set(key,out.id);return out.id;
 }
 const roots=[];for(let k=1;k<=K;k++){const id=solve(a,b,2n,k);roots.push({terms:k,node:id,count:nodes[id].count});}
 return {schema:"egyptian-decomposition-dag/v1",input:clone(input),reduced:{numerator:String(a),denominator:String(b)},roots,nodes,factorizations,minimum_terms:roots.find(r=>r.count!=="0")?.terms??null,total:String(roots.reduce((sum,r)=>sum+BigInt(r.count),0n)),order:"exact term count; lexicographically increasing numeric denominator tuple",work};
}
function openIndex(snapshot){
 const S=clone(snapshot),K=integer(S.input.max_terms,"saved terms",1,5);
 if(S.schema!=="egyptian-decomposition-dag/v1"||!Array.isArray(S.nodes)||S.nodes.length>20000||S.roots.length!==K)throw new Error("saved shape");
 const prefix=S.nodes.map((n,i)=>{
  if(n.id!==i||n.prefix.length!==n.branches.length+1||n.prefix[0]!=="0"||n.prefix.at(-1)!==n.count)throw new Error("saved node shape");
  integer(n.terms,"saved node terms",1,K);decimal(n.a,"saved a");decimal(n.b,"saved b");decimal(n.min_denominator,"saved minimum");
  for(const branch of n.branches){if(branch.child!==null&&(!Number.isSafeInteger(branch.child)||branch.child<0||branch.child>=i||S.nodes[branch.child].terms!==n.terms-1))throw new Error("saved child");
   if(branch.denominators.length!==(branch.child===null?n.terms:1)||branch.denominators.some(d=>decimal(d,"saved denominator")<=1n))throw new Error("saved denominator list");decimal(branch.count,"branch count");}
  const p=n.prefix.map(x=>decimal(x,"prefix"));if(p.some((x,j)=>j>0&&x<p[j-1]))throw new Error("saved prefix order");return p;
 });
 const work={queries:0,branch_comparisons:0,selection_steps:0,rank_steps:0,prefix_steps:0,saved_node_reads:0,saved_factorization_reads:0,rank_additions:0,new_residual_arithmetic:0,new_gcd:0,new_factorization:0,new_divisors:0,new_constructor_nodes:0};
 function root(k){integer(k,"terms",1,K);return S.roots[k-1];}
 function values(xs,k,partial=false){if(!Array.isArray(xs)||xs.length>(k)||(!partial&&xs.length!==k))throw new Error("denominator length");let prev=1n;return xs.map(s=>{const d=decimal(s,"denominator");if(d<=prev)throw new Error("strict denominator order");prev=d;return s;});}
 function findBranch(n,target){let l=0,r=n.branches.length;const t=BigInt(target);while(l<r){work.branch_comparisons++;const m=Math.floor((l+r)/2),v=BigInt(n.branches[m].denominators[0]);if(v<t)l=m+1;else r=m;}return l<n.branches.length&&n.branches[l].denominators[0]===target?l:-1;}
 function select(k,rank){
  const rt=root(k);let r=decimal(rank,"rank");if(r>=BigInt(rt.count))throw new RangeError("rank");
  let id=rt.node;const denominators=[],path=[];
  for(;;){const n=S.nodes[id],p=prefix[id];work.selection_steps++;let l=0,h=n.branches.length;
   while(l<h){work.branch_comparisons++;const m=Math.floor((l+h)/2);if(p[m+1]<=r)l=m+1;else h=m;}
   const branch=n.branches[l];r-=p[l];path.push({node:id,branch:l});denominators.push(...branch.denominators);
   if(branch.child===null){if(r!==0n)throw new Error("terminal rank");break;}id=branch.child;
  }return {terms:k,rank,denominators,path};
 }
 function rank(k,xs){
  const list=values(xs,k),rt=root(k);let id=rt.node,at=0,r=0n;const path=[];
  for(;;){const n=S.nodes[id];work.rank_steps++;const j=findBranch(n,list[at]);if(j<0)return {terms:k,denominators:list,member:false,rank:null};
   const branch=n.branches[j];if(branch.denominators.some((x,i)=>x!==list[at+i]))return {terms:k,denominators:list,member:false,rank:null};
   r+=prefix[id][j];work.rank_additions++;at+=branch.denominators.length;path.push({node:id,branch:j});
   if(branch.child===null)return {terms:k,denominators:list,member:at===list.length,rank:at===list.length?String(r):null,path};
   id=branch.child;
  }
 }
 function prefixQuery(k,xs){
  const list=values(xs,k,true);let id=root(k).node,at=0,start=0n;const path=[];
  for(;;){const n=S.nodes[id];work.prefix_steps++;
   if(at===list.length)return {terms:k,prefix:list,count:n.count,first_rank:n.count==="0"?null:String(start),node:id,path,forced_suffix:[]};
   const j=findBranch(n,list[at]);if(j<0)return {terms:k,prefix:list,count:"0",first_rank:null,path};
   const branch=n.branches[j],take=Math.min(list.length-at,branch.denominators.length);
   if(branch.denominators.slice(0,take).some((x,i)=>x!==list[at+i]))return {terms:k,prefix:list,count:"0",first_rank:null,path};
   start+=prefix[id][j];work.rank_additions++;path.push({node:id,branch:j});at+=take;
   if(at===list.length)return {terms:k,prefix:list,count:branch.count,first_rank:String(start),node:branch.child,path,forced_suffix:branch.denominators.slice(take)};
   if(branch.child===null)return {terms:k,prefix:list,count:"0",first_rank:null,path};
   id=branch.child;
  }
 }
 function query(q){work.queries++;let out;
  if(q.op==="summary")out={input:S.input,reduced:S.reduced,roots:S.roots,minimum_terms:S.minimum_terms,total:S.total,nodes:S.nodes.length,factorizations:S.factorizations.length,construction_work:S.work};
  else if(q.op==="family")out=root(q.terms);
  else if(q.op==="select")out=select(q.terms,q.rank);
  else if(q.op==="rank")out=rank(q.terms,q.denominators);
  else if(q.op==="prefix")out=prefixQuery(q.terms,q.denominators);
  else if(q.op==="page"){const rt=root(q.terms),offset=decimal(q.offset,"offset"),total=BigInt(rt.count);if(offset>total)throw new RangeError("offset");const limit=integer(q.limit??20,"limit",0,128),rows=[];let r=offset;for(let i=0;i<limit&&r<total;i++,r++)rows.push(select(q.terms,String(r)));out={terms:q.terms,count:rt.count,offset:q.offset,next:r<total?String(r):null,rows};}
  else if(q.op==="node"){work.saved_node_reads++;out=S.nodes[integer(q.id,"node id",0,S.nodes.length-1)];}
  else if(q.op==="factorization"){work.saved_factorization_reads++;out=S.factorizations[integer(q.id,"factorization id",0,S.factorizations.length-1)];}
  else throw new Error("unknown operation");
  return clone(out);
 }
 return {query,work:()=>clone(work)};
}
module.exports={compile,openIndex};
