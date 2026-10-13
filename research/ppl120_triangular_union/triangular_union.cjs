"use strict";
// Exact finite-offset unions of shifted triangular sequences.
// All serialized integer values and ranks are decimal strings.
function integer(x, name) {
  if (typeof x === "bigint") return x;
  if (typeof x === "number" && Number.isSafeInteger(x)) return BigInt(x);
  if (typeof x === "string" && /^-?(0|[1-9][0-9]*)$/.test(x)) return BigInt(x);
  throw new TypeError(name + " must be an exact integer");
}
function tri(k) { return k * (k + 1n) / 2n; }
function compile(input) {
  const work = { offsetPairs: 0, factorTrials: 0, divisors: 0,
    retainedPairIntersections: 0, fiberInsertions: 0,
    targetIntervalScans: 0, primalityTests: 0, sieveWork: 0 };
  const modes = {};
  for (const spec of input.modes) {
    if (!/^[a-z][a-z0-9_]*$/.test(spec.id) || modes[spec.id]) throw new TypeError("mode id");
    if (![1,2].includes(spec.c) || ![0,1].includes(spec.kMin)) throw new TypeError("mode shape");
    const ps = spec.offsets;
    if (!Array.isArray(ps) || ps.length < 1 || ps.length > 20 ||
        ps.some((p,i)=>!Number.isSafeInteger(p)||p<0||(i&&p<=ps[i-1]))) throw new TypeError("offsets");
    const fibers = new Map(), pairs = [];
    for (let i=0; i<ps.length; i++) for (let j=i+1; j<ps.length; j++) {
      work.offsetPairs++;
      const twiceDelta=2n*(BigInt(ps[j])-BigInt(ps[i])), c=BigInt(spec.c);
      const rec={left:i,right:j,factorProduct:null,solutions:[]};
      if (twiceDelta%c!==0n) { pairs.push(rec); continue; }
      const h=twiceDelta/c; rec.factorProduct=h.toString();
      for (let u=1n; u*u<h; u++) {
        work.factorTrials++;
        if (h%u!==0n) continue;
        work.divisors++;
        const v=h/u;
        if ((u+v)%2n!==1n) continue;
        const a=(u+v-1n)/2n, b=(v-u-1n)/2n;
        if (a<BigInt(spec.kMin)||b<BigInt(spec.kMin)) continue;
        const value=BigInt(ps[i])+c*tri(a);
        rec.solutions.push({u:u.toString(),v:v.toString(),leftIndex:a.toString(),
          rightIndex:b.toString(),value:value.toString()});
        work.retainedPairIntersections++;
        const key=value.toString();
        if (!fibers.has(key)) fibers.set(key,new Map());
        const f=fibers.get(key);
        for (const [branch,k] of [[i,a],[j,b]]) {
          if (!f.has(branch)) work.fiberInsertions++;
          f.set(branch,{branch,offset:ps[branch],index:k.toString()});
        }
      }
      pairs.push(rec);
    }
    const collisions=Array.from(fibers,([value,f])=>{
      const representations=Array.from(f.values()).sort((a,b)=>a.branch-b.branch);
      return {value,mask:representations.reduce((m,r)=>m+2**r.branch,0),representations};
    }).sort((a,b)=>BigInt(a.value)<BigInt(b.value)?-1:1);
    const correction=collisions.reduce((s,f)=>s+f.representations.length-1,0);
    modes[spec.id]={id:spec.id,c:spec.c,kMin:spec.kMin,offsets:ps.slice(),
      fullMask:2**ps.length-1,pairs,collisions,summary:{
        branches:ps.length,pairIntersections:pairs.reduce((s,p)=>s+p.solutions.length,0),
        collisionValues:collisions.length,excessRepresentations:correction,
        maximumMultiplicity:Math.max(1,...collisions.map(f=>f.representations.length)),
        lastCollision:collisions.length?collisions[collisions.length-1].value:null}};
  }
  return {schema:"ppl120.triangular-union/v1",input,modes,constructionWork:work};
}
function createReader(saved) {
  if (!saved || saved.schema!=="ppl120.triangular-union/v1") throw new TypeError("saved schema");
  const conditions=new Map(), counts=new Map();
  const work={conditionBuilds:0,conditionHits:0,savedFiberScans:0,savedRepresentationScans:0,
    countBuilds:0,countHits:0,branchCountEvaluations:0,collisionCountScans:0,
    squareRootCalls:0,squareRootIterations:0,representationBranchChecks:0,
    numericSelectIterations:0,newPairIntersections:0,constructorCalls:0};
  function mode(id) { const m=saved.modes[id]; if(!m) throw new RangeError("mode"); return m; }
  function context(id,mask) {
    const m=mode(id), s=mask===undefined?m.fullMask:mask;
    if (!Number.isSafeInteger(s)||s<0||s>m.fullMask) throw new RangeError("palette mask");
    const key=id+":"+s;
    if(conditions.has(key)){work.conditionHits++;return conditions.get(key);}
    work.conditionBuilds++;
    const branches=m.offsets.map((p,i)=>({branch:i,offset:p})).filter(r=>(s&2**r.branch)!==0);
    const collisions=[];
    for(const f of m.collisions){
      work.savedFiberScans++;
      const reps=f.representations.filter(r=>{work.savedRepresentationScans++;return (s&2**r.branch)!==0;});
      if(reps.length>=2) collisions.push({value:f.value,representations:reps,excess:reps.length-1});
    }
    const out={mode:id,mask:s,branches,collisions};
    conditions.set(key,out);return out;
  }
  function sqrt(n) {
    if(n<0n) throw new RangeError("negative square root");
    work.squareRootCalls++;
    if(n<2n)return n;
    let x=1n<<BigInt(Math.ceil(n.toString(2).length/2));
    while(true){work.squareRootIterations++;const y=(x+n/x)/2n;if(y>=x)return x;x=y;}
  }
  function branchCount(m,p,x) {
    work.branchCountEvaluations++;
    if(x<BigInt(p))return 0n;
    const z=(x-BigInt(p))/BigInt(m.c), k=(sqrt(1n+8n*z)-1n)/2n;
    return k<BigInt(m.kMin)?0n:k-BigInt(m.kMin)+1n;
  }
  function count(id,bound,mask) {
    const x=integer(bound,"bound"), m=mode(id), c=context(id,mask), key=id+":"+c.mask+":"+x;
    if(counts.has(key)){work.countHits++;return counts.get(key);}
    work.countBuilds++;
    let sum=0n,excess=0n;
    if(x>=0n){
      for(const b of c.branches)sum+=branchCount(m,b.offset,x);
      for(const f of c.collisions){work.collisionCountScans++;if(BigInt(f.value)<=x)excess+=BigInt(f.excess);}
    }
    const out={mode:id,mask:c.mask,bound:x.toString(),representations:sum.toString(),
      excess:excess.toString(),distinct:(sum-excess).toString()};
    counts.set(key,out);return out;
  }
  function representations(id,value,mask) {
    const x=integer(value,"value"),m=mode(id),c=context(id,mask),reps=[];
    for(const b of c.branches){
      work.representationBranchChecks++;
      const d=x-BigInt(b.offset);
      if(d<0n||d%BigInt(m.c)!==0n)continue;
      const z=d/BigInt(m.c),root=sqrt(1n+8n*z);
      if(root*root!==1n+8n*z)continue;
      const k=(root-1n)/2n;
      if(k>=BigInt(m.kMin))reps.push({branch:b.branch,offset:b.offset,index:k.toString()});
    }
    return {mode:id,mask:c.mask,value:x.toString(),representations:reps};
  }
  function rank(id,value,mask) {
    const r=representations(id,value,mask);
    return {...r,rank:r.representations.length?count(id,integer(value,"value")-1n,r.mask).distinct:null};
  }
  function select(id,rankValue,mask) {
    const r=integer(rankValue,"rank"),m=mode(id),c=context(id,mask);
    if(r<0n)throw new RangeError("negative rank");
    if(!c.branches.length)throw new RangeError("empty palette has no selected value");
    let lo=0n,hi=BigInt(c.branches[0].offset)+BigInt(m.c)*tri(r+BigInt(m.kMin));
    while(lo<hi){work.numericSelectIterations++;const mid=(lo+hi)/2n;
      if(BigInt(count(id,mid,c.mask).distinct)>r)hi=mid;else lo=mid+1n;}
    return {...representations(id,lo,c.mask),rank:r.toString()};
  }
  function window(id,lower,upper,mask) {
    const l=integer(lower,"lower"),u=integer(upper,"upper");
    if(l<0n||u<l)throw new RangeError("window must have 0 <= lower <= upper");
    const a=count(id,l-1n,mask),b=count(id,u,mask);
    return {mode:id,mask:b.mask,lower:l.toString(),upper:u.toString(),
      distinct:(BigInt(b.distinct)-BigInt(a.distinct)).toString(),
      representations:(BigInt(b.representations)-BigInt(a.representations)).toString()};
  }
  function profile(id,bound,mask) {
    const x=integer(bound,"bound"),c=context(id,mask),total=count(id,x,c.mask),hist={};
    let collisionValues=0n;
    for(const f of c.collisions){work.collisionCountScans++;if(BigInt(f.value)<=x){
      const k=f.representations.length;hist[k]=(BigInt(hist[k]||"0")+1n).toString();collisionValues++;}}
    hist[1]=(BigInt(total.distinct)-collisionValues).toString();
    return {...total,positiveMultiplicityCounts:hist};
  }
  const copy=x=>JSON.parse(JSON.stringify(x));
  return {
    summary:()=>copy({modes:Object.fromEntries(Object.entries(saved.modes).map(([id,m])=>[id,m.summary])),
      constructionWork:saved.constructionWork}),
    condition:(id,mask)=>copy(context(id,mask)),
    collisions:(id,mask)=>copy(context(id,mask).collisions),
    count,window,representations,rank,select,profile,
    work:()=>copy(work),
    caches:()=>copy({conditions:Array.from(conditions.entries()),counts:Array.from(counts.entries())})
  };
}
module.exports={compile,createReader};
