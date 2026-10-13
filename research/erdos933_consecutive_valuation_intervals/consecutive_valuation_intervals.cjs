'use strict';
function integer(x,name) {
  if(typeof x==='number'&&!Number.isSafeInteger(x))throw new TypeError(name+' must be exact');
  if(typeof x!=='number'&&typeof x!=='bigint'&&!(typeof x==='string'&&/^-?\d+$/.test(x)))throw new TypeError(name+' must be an integer');
  return BigInt(x);
}
function mod(a,m){const r=a%m;return r<0n?r+m:r;}
function floor(a,b){let q=a/b;if(a<0n&&a%b!==0n)q--;return q;}
function inverse(a,m,work){let r0=m,r1=mod(a,m),x0=0n,x1=1n;while(r1){const q=r0/r1;[r0,r1]=[r1,r0-q*r1];[x0,x1]=[x1,x0-q*x1];work.euclidean_steps++;}if(r0!==1n)throw new Error('Noncoprime CRT moduli');return mod(x0,m);}
function compile(input) {
  const A=input.cap2,B=input.cap3;
  if(!Number.isSafeInteger(A)||!Number.isSafeInteger(B)||A<1||B<1||A>32||B>24)throw new RangeError('Valuation caps');
  const work={power_products:0,euclidean_steps:0,inverses:0,inverse_cache_hits:0,crt_pairs:0,cell_accounting_terms:0,integer_enumeration:0,factorization:0,logarithms:0};
  const p2=[1n],p3=[1n];for(let i=1;i<=A+1;i++){p2.push(p2[i-1]*2n);work.power_products++;}
  for(let i=1;i<=B+1;i++){p3.push(p3[i-1]*3n);work.power_products++;}
  const axis2=[],axis3=[{label:0,lower:0,exact:true,modulus:'3',residues:['1']}];
  for(let a=1;a<=A;a++)axis2.push({label:a,lower:a,exact:true,modulus:String(p2[a+1]),residues:[p2[a]-1n,p2[a]].map(String)});
  axis2.push({label:'overflow',lower:A+1,exact:false,modulus:String(p2[A+1]),residues:['0',String(p2[A+1]-1n)]});
  for(let b=1;b<=B;b++)axis3.push({label:b,lower:b,exact:true,modulus:String(p3[b+1]),residues:[p3[b]-1n,p3[b],2n*p3[b]-1n,2n*p3[b]].map(String)});
  axis3.push({label:'overflow',lower:B+1,exact:false,modulus:String(p3[B+1]),residues:['0',String(p3[B+1]-1n)]});
  const period=p2[A+1]*p3[B+1],inverseMap=new Map(),cells=[];let accounting=0n,progressions=0;
  for(let i=0;i<axis2.length;i++)for(let j=0;j<axis3.length;j++){
    const a=axis2[i],b=axis3[j],m2=BigInt(a.modulus),m3=BigInt(b.modulus),M=m2*m3,key=m2+','+m3;
    let inv=inverseMap.get(key);if(inv===undefined){inv=inverse(m2,m3,work);inverseMap.set(key,inv);work.inverses++;}else work.inverse_cache_hits++;
    const residues=[];
    for(const x of a.residues)for(const y of b.residues){
      const r=mod(BigInt(x)+m2*mod((BigInt(y)-BigInt(x))*inv,m3),M);
      residues.push(String(r));work.crt_pairs++;
    }
    residues.sort((x,y)=>BigInt(x)<BigInt(y)?-1:BigInt(x)>BigInt(y)?1:0);
    const classes=BigInt(residues.length)*(period/M);accounting+=classes;work.cell_accounting_terms++;progressions+=residues.length;
    const smooth=p2[a.lower]*p3[b.lower];
    cells.push({id:cells.length,axis2:i,axis3:j,a:a.label,b:b.label,lower2:a.lower,lower3:b.lower,exact2:a.exact,exact3:b.exact,modulus:String(M),inverse2mod3:String(inv),residues,classes_per_period:String(classes),smooth_lower_bound:String(smooth),smooth_exact:a.exact&&b.exact});
  }
  if(accounting!==period)throw new Error('Valuation partition accounting mismatch');
  return{schema:'consecutive-valuation-intervals-v1',input,cap2:A,cap3:B,powers2:p2.map(String),powers3:p3.map(String),axis2,axis3,period:String(period),cells,
    summary:{cells:cells.length,progressions,period:String(period),exact_cells:A*(B+1),overflow_cells:cells.length-A*(B+1),classes_per_period:String(accounting),positive_domain:true},work};
}
function openIndex(saved,retainedCaches) {
  if(saved.schema!=='consecutive-valuation-intervals-v1')throw new TypeError('Snapshot schema');
  const cache=new Map(retainedCaches?.entries||[]),work={condition_normalizations:0,cell_filter_reads:0,range_cache_hits:0,range_cache_misses:0,progression_counts:0,floor_divisions:0,binary_steps:0,axis_modulo_tests:0,axis_residue_reads:0,quotient_certificates:0,product_evaluations:0,new_powers:0,new_crt:0,new_factorization:0};
  function condition(o={}) {
    const parse=(x,axis,name)=>{
      if(x===undefined)return axis.map(a=>a.label);
      if(!Array.isArray(x)||new Set(x.map(String)).size!==x.length||x.some(v=>!axis.some(a=>a.label===v)))throw new TypeError(name+' categories');
      return axis.filter(a=>x.includes(a.label)).map(a=>a.label);
    };
    const a=parse(o.a,saved.axis2,'a'),b=parse(o.b,saved.axis3,'b');work.condition_normalizations++;
    return{a,b};
  }
  function ids(c){const rows=[];for(const row of saved.cells){work.cell_filter_reads++;if(c.a.includes(row.a)&&c.b.includes(row.b))rows.push(row.id);}return rows;}
  function interval(lo,hi){lo=integer(lo,'lo');hi=integer(hi,'hi');if(lo<1n||hi<lo)throw new RangeError('Positive closed interval');return[lo,hi];}
  function cellMass(row,lo,hi){if(hi<lo)return 0n;const M=BigInt(row.modulus);let sum=0n;for(const str of row.residues){const r=BigInt(str);sum+=floor(hi-r,M)-floor(lo-1n-r,M);work.progression_counts++;work.floor_divisions+=2;}return sum;}
  function mass(lo,hi,chosen){if(hi<lo)return 0n;const key=JSON.stringify([String(lo),String(hi),chosen]);if(cache.has(key)){work.range_cache_hits++;return BigInt(cache.get(key));}work.range_cache_misses++;let n=0n;for(const id of chosen)n+=cellMass(saved.cells[id],lo,hi);cache.set(key,String(n));return n;}
  function counts(lo,hi,o={}){[lo,hi]=interval(lo,hi);const c=condition(o),chosen=ids(c),rows=[];let total=0n;for(const id of chosen){const n=cellMass(saved.cells[id],lo,hi);rows.push({id,a:saved.cells[id].a,b:saved.cells[id].b,count:String(n)});total+=n;}return{lo:String(lo),hi:String(hi),condition:c,count:String(total),cells:rows};}
  function count(lo,hi,o={}){[lo,hi]=interval(lo,hi);const c=condition(o);return{lo:String(lo),hi:String(hi),condition:c,count:String(mass(lo,hi,ids(c)))};}
  function axisMatch(axis,n) {
    for(let i=0;i<axis.length;i++){const row=axis[i],M=BigInt(row.modulus),r=mod(n,M);work.axis_modulo_tests++;
      for(const str of row.residues){work.axis_residue_reads++;if(r===BigInt(str))return{index:i,label:row.label,lower:row.lower,exact:row.exact,modulus:row.modulus,residue:String(r),quotient:String((n-r)/M)};}
    }throw new Error('Saved valuation category missing');
  }
  function classify(n){
    n=integer(n,'n');if(n<1n)throw new RangeError('Positive n required');
    const a=axisMatch(saved.axis2,n),b=axisMatch(saved.axis3,n),row=saved.cells[a.index*saved.axis3.length+b.index];work.quotient_certificates+=2;
    const lower=BigInt(row.smooth_lower_bound);let reduced=null;
    if(row.smooth_exact){work.product_evaluations++;reduced=String(n*(n+1n)/lower);}
    return{n:String(n),cell:row.id,a,b,smooth_lower_bound:String(lower),smooth_exact:row.smooth_exact,smooth_part:row.smooth_exact?String(lower):null,remaining_coprime_to_6:row.smooth_exact?reduced:null,overflow_unresolved:!row.smooth_exact};
  }
  function select(lo,hi,rank,o={}){
    [lo,hi]=interval(lo,hi);let r=integer(rank,'rank');if(r<0n)throw new RangeError('Negative rank');
    const c=condition(o),chosen=ids(c),total=mass(lo,hi,chosen);if(r>=total)throw new RangeError('Rank outside interval family');
    let left=lo,right=hi;const trace=[];
    while(left<right){const middle=(left+right)/2n,n=mass(lo,middle,chosen);work.binary_steps++;trace.push({left:String(left),right:String(right),middle:String(middle),prefix_count:String(n)});if(n>r)right=middle;else left=middle+1n;}
    return{lo:String(lo),hi:String(hi),condition:c,rank:String(r),family_count:String(total),record:classify(left),trace};
  }
  function rank(lo,hi,n,o={}){
    [lo,hi]=interval(lo,hi);n=integer(n,'n');if(n<lo||n>hi)throw new RangeError('n outside interval');
    const c=condition(o),chosen=ids(c),record=classify(n),included=chosen.includes(record.cell);
    return{lo:String(lo),hi:String(hi),condition:c,record,rank:included?String(mass(lo,n-1n,chosen)):null};
  }
  function page(lo,hi,start,limit,o={}){
    const r=integer(start,'start');if(r<0n||!Number.isSafeInteger(limit)||limit<0||limit>50)throw new RangeError('Page bounds');
    const total=BigInt(count(lo,hi,o).count);if(r>total)throw new RangeError('Page start');
    const records=[];let at=r;for(;at<total&&records.length<limit;at++)records.push(select(lo,hi,String(at),o));
    return{start:String(r),count:String(total),records,next:at<total?String(at):null};
  }
  return{summary:()=>saved.summary,cells:()=>saved.cells,axes:()=>({axis2:saved.axis2,axis3:saved.axis3}),count,counts,classify,select,rank,page,caches:()=>({schema:'consecutive-valuation-interval-caches-v1',entries:[...cache.entries()]}),work:()=>({...work})};
}
module.exports={compile,openIndex};
