'use strict';
const SCHEMA='ppl145-hesse-uniform-support-v1';
const edgeBits=9,FULL=511;
function integer(x,a,b,name){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(name);return x;}
function abs(x){return x<0n?-x:x;}
function gcd(a,b){a=abs(a);b=abs(b);while(b){const r=a%b;a=b;b=r;}return a;}
function fraction(n,d){if(d<=0n)throw new RangeError('positive denominator');if(n===0n)return '0';const g=gcd(n,d);n/=g;d/=g;return d===1n?String(n):n+'/'+d;}
function rational(value){
 if(typeof value==='number'){if(!Number.isSafeInteger(value))throw new TypeError('integer number or rational string');value=String(value);}
 if(typeof value!=='string'||!/^\d+(?:\/\d+)?$/.test(value))throw new TypeError('nonnegative rational string');
 const s=value.split('/');let n=BigInt(s[0]),d=s[1]===undefined?1n:BigInt(s[1]);if(d===0n||n>d)throw new RangeError('visibility0..1');
 const g=gcd(n,d);n/=g;d/=g;return {n,d,key:fraction(n,d)};
}
function pop(x){let n=0;while(x){x&=x-1;n++;}return n;}
const add=(x,y)=>[x[0]+y[0],x[1]+y[1]];
const neg=x=>[-x[0],-x[1]];
const mul=(x,y)=>[x[0]*y[0]-x[1]*y[1],x[0]*y[1]+x[1]*y[0]-x[1]*y[1]];
const conj=x=>[x[0]-x[1],-x[1]];
const scale=(x,c)=>[x[0]*c,x[1]*c];
function trim(p){while(p.length>1&&p.at(-1)[0]===0n&&p.at(-1)[1]===0n)p.pop();return p;}
function padd(a,b){const c=Array.from({length:Math.max(a.length,b.length)},()=>[0n,0n]);for(let i=0;i<c.length;i++)c[i]=add(a[i]||[0n,0n],b[i]||[0n,0n]);return trim(c);}
function pneg(a){return a.map(neg);}
function pmul(a,b,work){const c=Array.from({length:a.length+b.length-1},()=>[0n,0n]);for(let i=0;i<a.length;i++)for(let j=0;j<b.length;j++){c[i+j]=add(c[i+j],mul(a[i],b[j]));work.polynomial_field_products++;}return trim(c);}
function determinant(matrix,work){
 if(matrix.length===1)return matrix[0][0];
 let out=[[0n,0n]];
 for(let j=0;j<matrix.length;j++){
 const sub=matrix.slice(1).map(row=>row.filter((_,k)=>k!==j));
 const term=pmul(matrix[0][j],determinant(sub,work),work);
 out=padd(out,j%2?pneg(term):term);
 }return out;
}
function compile(input){
 if(input.dimension!==3||!Array.isArray(input.coordinate_rows)||input.coordinate_rows.length!==3||
    input.coordinate_rows.some(r=>!Array.isArray(r)||r.length!==9))throw new TypeError('declared Hesse3x9 input');
 const tokens={'0':[0n,0n],'1':[1n,0n],'-1':[-1n,0n],'w':[0n,1n],'-w':[0n,-1n],'w2':[-1n,-1n],'-w2':[1n,1n]};
 const rows=input.coordinate_rows.map(r=>r.map(t=>{if(!Object.hasOwn(tokens,t))throw new TypeError('coordinate token');return tokens[t];}));
 const work={projector_outer_products:0,subset_matrix_additions:0,principal_polynomials:0,polynomial_field_products:0,
  at_one_coefficient_additions:0,old_SIC_Gram_checks:0,old_MUB_calls:0};
 // Each Q_i=2*Pi_i comes from the supplied normalized column v_i/sqrt(2).
 const Q=Array.from({length:9},(_,j)=>Array.from({length:3},(_,a)=>Array.from({length:3},(_,b)=>{work.projector_outer_products++;return mul(rows[a][j],conj(rows[b][j]));})));
 const sums=[Array.from({length:3},()=>Array.from({length:3},()=>[0n,0n]))],records=[null],profiles=new Map();
 const sets=[[0],[1],[2],[0,1],[0,2],[1,2],[0,1,2]];
 for(let mask=1;mask<=FULL;mask++){
   const bit=mask&-mask,ix=31-Math.clz32(bit),prior=mask^bit,k=pop(mask),K=BigInt(k);
   sums[mask]=sums[prior].map((r,a)=>r.map((x,b)=>{work.subset_matrix_additions++;return add(x,Q[ix][a][b]);}));
   const A=sums[mask].map((r,a)=>r.map((x,b)=>add(scale(x,4n),a===b?[-2n*K,0n]:[0n,0n])));
   // H(t)=3tA+2k(1-t)I; rho(t)=H(t)/(6k).
   const H=A.map((r,a)=>r.map((x,b)=>a===b?[[2n*K,0n],add(scale(x,3n),[-2n*K,0n])]:[[0n,0n],scale(x,3n)]));
   const minors=sets.map(vertices=>{
     const p=determinant(vertices.map(a=>vertices.map(b=>H[a][b])),work);work.principal_polynomials++;
     if(p.some(x=>x[1]!==0n))throw new Error('nonreal principal determinant');
     let value=0n;for(const x of p){value+=x[0];work.at_one_coefficient_additions++;}
     return {vertices,size:vertices.length,coefficients:p.map(x=>String(x[0])),at_one_numerator:String(value)};
   });
   const bad=minors.findIndex(x=>BigInt(x.at_one_numerator)<0n),psd=bad===-1;
   const rank=psd?Math.max(0,...minors.filter(x=>BigInt(x.at_one_numerator)>0n).map(x=>x.size)):null;
   const record={mask,size:k,A:A.map(r=>r.map(x=>x.map(String))),rho_denominator:String(2n*K),minors,
     at_one:{psd,rank,pure:rank===1,first_negative:bad===-1?null:bad},purity:fraction(12n-K,K)};
   records.push(record);
   const key=k+':'+(psd?'rank'+rank:'not-PSD');if(!profiles.has(key))profiles.set(key,[]);profiles.get(key).push(mask);
 }
 return {schema:SCHEMA,input,projectors_twice:Q.map(M=>M.map(r=>r.map(x=>x.map(String)))),
   records,profiles:Array.from(profiles,([key,masks])=>({key,masks})),work,
   summary:{dimension:3,outcomes:9,nonempty_supports:511,principal_polynomials:511*7,
     physical_uniform_supports:records.slice(1).filter(r=>r.at_one.psd).length,
     pure_uniform_supports:records.slice(1).filter(r=>r.at_one.pure).length,
     profile_counts:Array.from(profiles,([key,masks])=>({key,count:masks.length}))}};
}
function openIndex(data){
 if(!data||data.schema!==SCHEMA||!Array.isArray(data.records)||data.records.length!==512)throw new TypeError('saved index');
 const work={structural_rows_read:511,visibility_polynomial_evaluations:0,homogeneous_horner_steps:0,
   classification_cache_hits:0,condition_row_scans:0,rank_comparisons:0,selected_records:0,
   affine_matrix_entries:0,probability_entries:0,purity_evaluations:0,
   new_projector_outer_products:0,new_principal_polynomials:0};
 const evaluations=new Map(),conditions=new Map();
 function mask(x){return integer(x,1,FULL,'nonempty support mask');}
 function polynomial(coeff,n,d){
  let z=BigInt(coeff.at(-1)),power=d;
  for(let i=coeff.length-2;i>=0;i--){z=z*n+BigInt(coeff[i])*power;power*=d;work.homogeneous_horner_steps++;}
  return {n:z,d:d**BigInt(coeff.length-1)};
 }
 function classify(s,value='1'){
  s=mask(s);const t=rational(value),key=s+'@'+t.key;
  if(evaluations.has(key)){work.classification_cache_hits++;return JSON.parse(JSON.stringify(evaluations.get(key)));}
  const r=data.records[s],base=6n*BigInt(r.size);
  const minors=r.minors.map(m=>{
    const v=t.key==='1'?{n:BigInt(m.at_one_numerator),d:1n}:polynomial(m.coefficients,t.n,t.d);
    if(t.key!=='1')work.visibility_polynomial_evaluations++;
    return {vertices:m.vertices.slice(),size:m.size,numerator:String(v.n),denominator:String(v.d*(base**BigInt(m.size))),
      value:fraction(v.n,v.d*(base**BigInt(m.size)))};
  });
  const i=minors.findIndex(x=>BigInt(x.numerator)<0n),psd=i===-1;
  const rank=psd?Math.max(0,...minors.filter(x=>BigInt(x.numerator)>0n).map(x=>x.size)):null;
  const result={mask:s,size:r.size,visibility:t.key,psd,rank,pure:rank===1,
    negative_witness:i===-1?null:{principal_index:i,...minors[i]},principal_minors:minors};
  evaluations.set(key,result);return JSON.parse(JSON.stringify(result));
 }
 function state(s,value='1'){
  const c=classify(s,value),t=rational(value),r=data.records[mask(s)],k=BigInt(r.size),den=6n*k*t.d;
  const matrix=r.A.map((row,a)=>row.map((x,b)=>{
    work.affine_matrix_entries++;return {a:fraction(3n*t.n*BigInt(x[0])+(a===b?2n*k*(t.d-t.n):0n),den),
      b:fraction(3n*t.n*BigInt(x[1]),den)};}));
  const probabilities=Array.from({length:9},(_,j)=>{work.probability_entries++;return (s&(1<<j))?
    fraction(9n*t.n+(t.d-t.n)*k,9n*t.d*k):fraction(t.d-t.n,9n*t.d);});
  work.purity_evaluations++;
  const purity=fraction(t.d*t.d*k+t.n*t.n*(36n-4n*k),3n*t.d*t.d*k);
  return {mask:s,visibility:t.key,psd:c.psd,rank:c.rank,matrix,probabilities,purity,
    entry_notation:'a+b*w, w^2+w+1=0',negative_witness:c.negative_witness};
 }
 function condition(filter={}){
  const f={visibility:rational(filter.visibility===undefined?'1':filter.visibility).key,
    available:integer(filter.available===undefined?FULL:filter.available,0,FULL,'available'),
    include:integer(filter.include===undefined?0:filter.include,0,FULL,'include'),
    exclude:integer(filter.exclude===undefined?0:filter.exclude,0,FULL,'exclude'),
    size:filter.size===undefined||filter.size===null?null:integer(filter.size,1,9,'size'),
    psd:filter.psd===undefined?true:filter.psd,
    rank:filter.rank===undefined||filter.rank===null?null:integer(filter.rank,1,3,'rank')};
  if(f.psd!==true&&f.psd!==false&&f.psd!==null)throw new TypeError('psd true/false/null');
  if((f.include&f.available)!==f.include||(f.exclude&f.available)!==f.exclude||(f.include&f.exclude))throw new RangeError('support restrictions');
  const key=JSON.stringify(f);
  if(!conditions.has(key)){
    const masks=[],by_size=Array(10).fill(0);
    for(let s=1;s<=FULL;s++){work.condition_row_scans++;const r=data.records[s];
      if((s&f.available)!==s||(s&f.include)!==f.include||(s&f.exclude)||(f.size!==null&&r.size!==f.size))continue;
      const c=classify(s,f.visibility);if((f.psd!==null&&c.psd!==f.psd)||(f.rank!==null&&c.rank!==f.rank))continue;
      masks.push(s);by_size[r.size]++;}
    conditions.set(key,{key,filter:f,masks,by_size});}
  const c=conditions.get(key);return {key,filter:c.filter,count:c.masks.length,by_size:c.by_size.slice()};
 }
 function select(key,rank){const c=conditions.get(key);if(!c)throw new RangeError('unknown condition');
   integer(rank,0,c.masks.length-1,'rank');work.selected_records++;return {rank,...state(c.masks[rank],c.filter.visibility)};}
 function rank(key,s){mask(s);const c=conditions.get(key);if(!c)throw new RangeError('unknown condition');
  let lo=0,hi=c.masks.length;while(lo<hi){const mid=(lo+hi)>>1;work.rank_comparisons++;if(c.masks[mid]<s)lo=mid+1;else hi=mid;}
  return lo<c.masks.length&&c.masks[lo]===s?lo:null;}
 return {summary:()=>JSON.parse(JSON.stringify(data.summary)),classify,state,condition,select,rank,
   exportCaches:()=>({classifications:Array.from(evaluations.values()),conditions:Array.from(conditions.values())}),
   work:()=>({...work})};
}
module.exports={compile,openIndex};
