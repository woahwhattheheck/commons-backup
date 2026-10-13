"use strict";
const clone=x=>JSON.parse(JSON.stringify(x));
function exact(x,name){
 if(typeof x==="bigint")return x;
 if(typeof x==="number"&&Number.isSafeInteger(x))return BigInt(x);
 if(typeof x==="string"&&/^-?(0|[1-9][0-9]*)$/.test(x))return BigInt(x);
 throw new TypeError(name+" must be an exact integer");
}
function compile(input){
 const primes=input.primes;
 if(!Array.isArray(primes)||primes.length<1||primes.length>12||primes.some((p,i)=>!Number.isSafeInteger(p)||p<3||p>10000||p%2!==1||(i&&p<=primes[i-1])))throw new RangeError("declared ascending odd prime palette");
 const offsets=primes.map(p=>p+1),spread=BigInt(offsets[offsets.length-1]-offsets[0]);
 const cs=[1n],steps=[],work={catalanSteps:0,prefixContributions:0,fiberInsertions:0,primalityWork:0,fibonacciRecurrence:0};
 let J;
 for(let j=0;j<10000;j++){
  const numerator=2n*BigInt(2*j+1)*cs[j],denominator=BigInt(j+2);
  if(numerator%denominator!==0n)throw new Error("nonintegral Catalan recurrence");
  const next=numerator/denominator;cs.push(next);steps.push({from:j,numerator:String(numerator),denominator:String(denominator),value:String(next)});work.catalanSteps++;
  if(j>=1&&next-cs[j]>spread){J=j;break;}
 }
 if(J===undefined)throw new RangeError("prefix allowance");
 const fibers=new Map(),canonical=[0];for(let j=2;j<=J;j++)canonical.push(j);
 for(let p=0;p<primes.length;p++)for(const j of canonical){
  work.prefixContributions++;const n=cs[j]+BigInt(offsets[p]),k=String(n);
  if(!fibers.has(k)){fibers.set(k,[]);work.fiberInsertions++;}
  fibers.get(k).push([p,j]);
 }
 const prefix=Array.from(fibers,([n,pairs])=>[n,pairs.sort((a,b)=>a[0]-b[0]||a[1]-b[1])]).sort((a,b)=>BigInt(a[0])<BigInt(b[0])?-1:1);
 const indexCount=pairs=>pairs.reduce((s,a)=>s+(a[1]===0?4:2),0);
 return {schema:"ppl013.catalan-union/v1",input,offsets,spread:String(spread),J,tailStart:J+1,catalans:cs.map(String),steps,canonicalPrefixIndices:canonical,prefix,
  summary:{prefixDistinct:prefix.length,prefixValueRepresentations:work.prefixContributions,prefixIndexRepresentations:prefix.reduce((s,a)=>s+indexCount(a[1]),0),
   prefixCollisionTargets:prefix.filter(a=>a[1].length>1).length,maxPrefixValueMultiplicity:Math.max(...prefix.map(a=>a[1].length)),
   prefixMax:prefix[prefix.length-1][0],firstTailMinimum:String(cs[J+1]+BigInt(offsets[0])),tailWidth:offsets.length},
  constructionWork:work};
}
function createReader(saved,options={}){
 if(!saved||saved.schema!=="ppl013.catalan-union/v1")throw new TypeError("saved schema");
 const maxIndex=options.maxEvaluatedIndex===undefined?2048:options.maxEvaluatedIndex;
 if(!Number.isSafeInteger(maxIndex)||maxIndex<saved.tailStart||maxIndex>10000)throw new RangeError("maxEvaluatedIndex");
 const primes=saved.input.primes,offsets=saved.offsets,K=saved.tailStart,J=saved.J,cs=saved.catalans.map(BigInt),extensions=[],conditions=new Map();
 const work={conditionBuilds:0,conditionHits:0,prefixFiberReads:0,prefixContributionReads:0,
  prefixComparisons:0,tailComparisons:0,offsetComparisons:0,symbolicSelections:0,symbolicRanks:0,
  newCatalanSteps:0,catalanCacheReads:0,materializations:0,newPrefixContributions:0,fibonacciRecurrence:0,primalityWork:0};
 function maskValue(mask){if(!Number.isSafeInteger(mask)||mask<0||mask>=(1<<primes.length))throw new RangeError("prime mask");return mask;}
 function context(mask){
  maskValue(mask);if(conditions.has(mask)){work.conditionHits++;return conditions.get(mask);}
  work.conditionBuilds++;const selected=[];for(let i=0;i<primes.length;i++)if(mask&(1<<i))selected.push(i);
  const prefix=[];
  for(const [n,pairs]of saved.prefix){work.prefixFiberReads++;const kept=[];
   for(const a of pairs){work.prefixContributionReads++;if(mask&(1<<a[0]))kept.push(a.slice());}
   if(kept.length)prefix.push([n,kept]);}
  const c={mask,selected,prefix,prefixCount:prefix.length,prefixIndexRepresentations:prefix.reduce((s,a)=>s+a[1].reduce((z,b)=>z+(b[1]===0?4:2),0),0)};
  conditions.set(mask,c);return c;
 }
 function extend(index){
  if(index>maxIndex)throw new RangeError("materialized Catalan index exceeds configured budget");
  while(cs.length<=index){
   const j=cs.length-1,numerator=2n*BigInt(2*j+1)*cs[j],denominator=BigInt(j+2);
   if(numerator%denominator!==0n)throw new Error("nonintegral Catalan extension");
   const value=numerator/denominator;cs.push(value);extensions.push({index:j+1,value:String(value)});work.newCatalanSteps++;
  }
  work.catalanCacheReads++;return cs[index];
 }
 function prefixLower(c,n,upper){
  let lo=0,hi=c.prefix.length;while(lo<hi){const m=Math.floor((lo+hi)/2),v=BigInt(c.prefix[m][0]);work.prefixComparisons++;
   if(v<n||(upper&&v===n))lo=m+1;else hi=m;}return lo;
 }
 function prefixTarget(row){
  return {kind:"integer",value:row[0],canonical:{primeIndex:row[1][0][0],catalanIndex:String(row[1][0][1])},
   valueRepresentations:row[1].length,indexRepresentations:row[1].reduce((s,a)=>s+(a[1]===0?4:2),0),
   contributions:row[1].map(([p,j])=>({primeIndex:p,prime:primes[p],fibonacciValue:"1",fibonacciIndices:[1,2],catalanValue:saved.catalans[j],catalanIndices:j===0?[0,1]:[j]}))};
 }
 function tailTarget(p,j){
  return {kind:"catalan-plus-offset",value:null,catalanIndex:String(j),offset:offsets[p],canonical:{primeIndex:p,catalanIndex:String(j)},
   valueRepresentations:1,indexRepresentations:2,prime:primes[p],fibonacciValue:"1",fibonacciIndices:[1,2],catalanIndices:[String(j)]};
 }
 function select(mask,rank){
  const c=context(mask),r=exact(rank,"rank");if(r<0n||!c.selected.length)throw new RangeError("rank outside family");work.symbolicSelections++;
  if(r<BigInt(c.prefixCount))return {mask,rank:String(r),target:prefixTarget(c.prefix[Number(r)])};
  const k=r-BigInt(c.prefixCount),m=BigInt(c.selected.length),j=BigInt(K)+k/m,p=c.selected[Number(k%m)];
  return {mask,rank:String(r),target:tailTarget(p,j)};
 }
 function symbolic(mask,p,jValue){
  const c=context(mask),j=exact(jValue,"Catalan index");if(j<0n||!Number.isSafeInteger(p)||!c.selected.includes(p))throw new RangeError("symbolic contribution outside palette");
  work.symbolicRanks++;
  if(j<=BigInt(J)){
   const canonical=j===1n?0:Number(j),n=BigInt(saved.catalans[canonical])+BigInt(offsets[p]),i=prefixLower(c,n,false);
   if(i===c.prefix.length||BigInt(c.prefix[i][0])!==n)throw new Error("prefix contribution absent");
   return {mask,rank:String(i),target:prefixTarget(c.prefix[i])};
  }
  const position=c.selected.indexOf(p),r=BigInt(c.prefixCount)+(j-BigInt(K))*BigInt(c.selected.length)+BigInt(position);
  return {mask,rank:String(r),target:tailTarget(p,j)};
 }
 function lastTail(c,n){
  if(!c.selected.length)return K-1;
  const minimum=BigInt(offsets[c.selected[0]]);
  while(cs[cs.length-1]+minimum<=n)extend(cs.length);
  let lo=K,hi=cs.length;while(lo<hi){const m=Math.floor((lo+hi)/2);work.tailComparisons++;
   if(cs[m]+minimum<=n)lo=m+1;else hi=m;}return lo-1;
 }
 function countLeq(mask,value){
  const c=context(mask),n=exact(value,"threshold");if(!c.selected.length)return {mask,threshold:String(n),count:"0"};
  const prefix=prefixLower(c,n,true),j=lastTail(c,n);let count=BigInt(prefix);
  if(j>=K){count+=BigInt(j-K)*BigInt(c.selected.length);for(const p of c.selected){work.offsetComparisons++;if(cs[j]+BigInt(offsets[p])<=n)count++;}}
  return {mask,threshold:String(n),count:String(count)};
 }
 function fiberValue(mask,value){
  const c=context(mask),n=exact(value,"target"),i=prefixLower(c,n,false);
  if(i<c.prefixCount&&BigInt(c.prefix[i][0])===n)return {mask,target:prefixTarget(c.prefix[i]),rank:String(i)};
  if(!c.selected.length)return {mask,value:String(n),target:null,rank:null};
  const j=lastTail(c,n);if(j>=K)for(const p of c.selected){work.offsetComparisons++;if(cs[j]+BigInt(offsets[p])===n){const out=symbolic(mask,p,j);return {...out,target:{...out.target,value:String(n)}};}}
  return {mask,value:String(n),target:null,rank:null};
 }
 function materialize(mask,rank){
  const out=select(mask,rank);work.materializations++;if(out.target.kind==="integer")return out;
  const j=BigInt(out.target.catalanIndex);if(j>BigInt(maxIndex))throw new RangeError("symbolic result exceeds materialization budget");
  const value=extend(Number(j))+BigInt(out.target.offset);return {...out,target:{...out.target,value:String(value)}};
 }
 return {summary:()=>clone({summary:saved.summary,constructionWork:saved.constructionWork,J,K,spread:saved.spread,maxEvaluatedIndex:maxIndex}),
  condition:mask=>{const c=context(mask);return clone({mask:c.mask,selected:c.selected,primes:c.selected.map(p=>primes[p]),offsets:c.selected.map(p=>offsets[p]),prefixCount:c.prefixCount,prefixIndexRepresentations:c.prefixIndexRepresentations,tailStart:K,tailWidth:c.selected.length,infinite:c.selected.length>0});},
  prefix:mask=>clone(context(mask).prefix.map(prefixTarget)),select,rankSymbolic:symbolic,materialize,countLeq,fiberValue,
  countWindow:(mask,lo,hi)=>{const l=exact(lo,"lo"),h=exact(hi,"hi");return {mask,lo:String(l),hi:String(h),count:l>h?"0":String(BigInt(countLeq(mask,h).count)-BigInt(countLeq(mask,l-1n).count))};},
  catalan:index=>{if(!Number.isSafeInteger(index)||index<0)throw new RangeError("index");return {index,value:String(extend(index))};},
  work:()=>clone(work),caches:()=>clone({conditions:Array.from(conditions.values()),catalans:cs.map(String),extensions,maxEvaluatedIndex:maxIndex})};
}
module.exports={compile,createReader};
