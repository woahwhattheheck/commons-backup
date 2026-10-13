"use strict";

/*
 * Exact fixed-left-support certificates for rho(4,-1/2).
 * C_(a,b),(c,d) = sum_j U_j[a,b] V_j[c,d], with ordinary transpose.
 * K_U represents 4 q(C), so the unnormalized state expectation is v* K_U v / 784.
 * Source conventions and the restricted-family boundary are in WERNER_FIXED_SUPPORT_API.md.
 * Pure CommonJS; no I/O, dependencies, native arithmetic or floating-point spectral calls.
 */

const WERNER_FIXED_SUPPORT_LIMITS = Object.freeze({
  local_dimension: 4, side_dimension: 16, max_left_columns: 2,
  max_support_absolute_value: 1000000,
  max_query_integer_digits: 80, max_internal_integer_digits: 4096,
  max_page_rows: 32, max_snapshot_characters: 4000000
});
const SCHEMA = "commons.werner_fixed_support/v1";
const N = 16;
const Z = Object.freeze([0n, 1n]);
const O = Object.freeze([1n, 1n]);

function fail(message) { throw new Error(message); }
function abs(x) { return x < 0n ? -x : x; }
function gcd(a,b) { a=abs(a);b=abs(b);while(b){const t=a%b;a=b;b=t;}return a; }
function bounded(x) {
  if (abs(x).toString().length > WERNER_FIXED_SUPPORT_LIMITS.max_internal_integer_digits)
    fail("Exact arithmetic exceeded the internal digit bound.");
  return x;
}
function rat(n,d=1n) {
  if(d===0n) fail("A rational denominator is zero.");
  if(d<0n){n=-n;d=-d;}
  if(n===0n) return Z;
  const g=gcd(n,d);
  return [bounded(n/g),bounded(d/g)];
}
function add(a,b) {
  const g=gcd(a[1],b[1]), ad=a[1]/g, bd=b[1]/g;
  return rat(bounded(a[0]*bd+b[0]*ad),bounded(ad*b[1]));
}
function neg(a){return a[0]===0n?Z:[-a[0],a[1]];}
function sub(a,b){return add(a,neg(b));}
function mul(a,b) {
  if(a[0]===0n||b[0]===0n)return Z;
  const g=gcd(a[0],b[1]),h=gcd(b[0],a[1]);
  return rat(bounded((a[0]/g)*(b[0]/h)),bounded((a[1]/h)*(b[1]/g)));
}
function div(a,b){if(b[0]===0n)fail("Division by zero.");return mul(a,rat(b[1],b[0]));}
function eq(a,b){return a[0]===b[0]&&a[1]===b[1];}
function fmt(a){return a[1]===1n?a[0].toString():a[0].toString()+"/"+a[1].toString();}
function integer(value,label,limit=80) {
  let s;
  if(typeof value==="bigint")s=value.toString();
  else if(typeof value==="number"&&Number.isSafeInteger(value))s=String(value);
  else if(typeof value==="string")s=value;
  else fail(label+" must be an exact integer.");
  if(!/^(0|-?[1-9][0-9]*)$/.test(s)||s.replace("-","").length>limit)
    fail(label+" is not a canonical bounded integer.");
  return BigInt(s);
}
function parseRat(value,label,limit=80,canonical=false) {
  if(typeof value!=="string")return rat(integer(value,label,limit));
  const parts=value.split("/");
  if(parts.length>2)fail(label+" is not a rational.");
  const a=integer(parts[0],label,limit);
  let b=1n;
  if(parts.length===2){b=integer(parts[1],label+" denominator",limit);if(b<=0n)fail(label+" needs a positive denominator.");}
  const v=rat(a,b);
  if(canonical&&fmt(v)!==value)fail(label+" is not in reduced canonical form.");
  return v;
}
function index(value,upper,label) {
  if(!Number.isSafeInteger(value)||value<0||value>=upper)fail(label+" is outside its integer range.");
  return value;
}
function dimensions(a,rows,columns,label) {
  if(!Array.isArray(a)||a.length!==rows)fail(label+" has the wrong row count.");
  for(const row of a)if(!Array.isArray(row)||row.length!==columns)fail(label+" has the wrong column count.");
}
function clone(x){return JSON.parse(JSON.stringify(x));}
function intMatrix(a,rows,cols,label,digits=4096) {
  dimensions(a,rows,cols,label);
  return a.map((row,i)=>row.map((v,j)=>integer(v,label+"["+i+"]["+j+"]",digits)));
}
function ratMatrix(a,rows,cols,label) {
  dimensions(a,rows,cols,label);
  return a.map((row,i)=>row.map((v,j)=>parseRat(v,label+"["+i+"]["+j+"]",4096,true)));
}
function encodeInts(a){return a.map(row=>row.map(x=>x.toString()));}
function encodeRats(a){return a.map(row=>row.map(fmt));}
function supportColumns(raw) {
  if(!Array.isArray(raw)||raw.length<1||raw.length>2)fail("left_columns must have one or two columns.");
  dimensions(raw,raw.length,N,"left_columns");
  return raw.map((col,j)=>col.map((v,i)=>{
    const z=integer(v,"left_columns["+j+"]["+i+"]");
    if(abs(z)>1000000n)fail("A support entry exceeds the absolute-value cap.");
    return z;
  }));
}
function gramDet(g) {return g.length===1?g[0][0]:g[0][0]*g[1][1]-g[0][1]*g[1][0];}
function emptyWork() {
  return {
    support_dot_products:0,support_dot_terms:0,trace_map_assignments:0,
    form_entries:0,trace_gram_products:0,full_trace_products:0,
    factor_pivots:0,factor_quotients:0,factor_schur_updates:0,
    load_integer_entries:0,load_rational_entries:0,
    evaluations:0,evaluation_gram_terms:0,evaluation_trace_map_terms:0,
    evaluation_sos_terms:0,evaluation_factor_terms:0,
    triangular_solve_terms:0,matrix_rows_returned:0,factor_rows_returned:0,
    coefficient_terms:0,form_constructions:0,eliminations:0
  };
}
function backDirection(L,z,completed,work) {
  const x=z.slice();
  for(let i=completed-1;i>=0;i--){
    let v=x[i];
    for(let j=i+1;j<x.length;j++){v=sub(v,mul(L[j][i],x[j]));work.triangular_solve_terms++;}
    x[i]=v;
  }
  return x;
}
function quadratic(K,x) {
  let q=Z;
  for(let i=0;i<x.length;i++)for(let j=0;j<x.length;j++)
    q=add(q,mul(rat(K[i][j]),mul(x[i],x[j])));
  return q;
}
function factorPSD(K,work) {
  const n=K.length,S=K.map(row=>row.map(v=>rat(v)));
  const L=Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>i===j?O:Z));
  const D=[];
  work.eliminations++;
  for(let k=0;k<n;k++){
    const p=S[k][k];work.factor_pivots++;
    let bad=-1;
    if(p[0]===0n)for(let i=k+1;i<n;i++)if(S[i][k][0]!==0n){bad=i;break;}
    if(p[0]<0n||bad>=0){
      const z=Array.from({length:n},()=>Z);
      let value,kind;
      if(p[0]<0n){z[k]=O;value=p;kind="negative_diagonal";}
      else{
        z[bad]=O;
        z[k]=neg(div(add(S[bad][bad],O),mul(rat(2n),S[bad][k])));
        value=rat(-1n);kind="zero_diagonal_nonzero_row";
      }
      const x=backDirection(L,z,k,work),direct=quadratic(K,x);
      if(!eq(direct,value)||direct[0]>=0n)fail("The computed negative direction failed its exact identity.");
      return {
        kind:"negative_direction",completed_pivots:k,stopping_index:k,reason:kind,
        L:encodeRats(L),D:D.map(fmt),
        residual:encodeRats(S.slice(k).map(row=>row.slice(k))),
        direction:x.map(fmt),form_value:fmt(value)
      };
    }
    D.push(p);
    if(p[0]===0n)continue;
    for(let i=k+1;i<n;i++){L[i][k]=div(S[i][k],p);work.factor_quotients++;}
    for(let i=k+1;i<n;i++)for(let j=i;j<n;j++){
      const next=sub(S[j][i],mul(L[i][k],S[j][k]));
      S[j][i]=next;S[i][j]=next;work.factor_schur_updates++;
    }
  }
  let determinant=O,rank=0;
  for(const d of D){determinant=mul(determinant,d);if(d[0]>0n)rank++;}
  return {
    kind:"ldlt_psd",L:encodeRats(L),D:D.map(fmt),rank,nullity:n-rank,
    positive_definite:rank===n,determinant:fmt(determinant)
  };
}
function compileWernerFixedSupport(input) {
  if(!input||typeof input!=="object")fail("A support input object is required.");
  const U=supportColumns(input.left_columns),r=U.length,n=N*r,w=emptyWork();
  const provenance=input.provenance===undefined?"caller_supplied_left_support":input.provenance;
  if(typeof provenance!=="string"||provenance.length>2048)fail("provenance must be a string of at most 2048 characters.");
  const G=Array.from({length:r},()=>Array(r).fill(0n));
  for(let a=0;a<r;a++)for(let b=a;b<r;b++){
    let s=0n;w.support_dot_products++;
    for(let i=0;i<N;i++){s+=U[a][i]*U[b][i];w.support_dot_terms++;}
    G[a][b]=s;G[b][a]=s;
  }
  const gd=gramDet(G);
  if(G[0][0]<=0n||gd<=0n)fail("The real left columns must be linearly independent.");
  const T1=Array.from({length:N},()=>Array(n).fill(0n));
  const T2=Array.from({length:N},()=>Array(n).fill(0n));
  const t=Array(n).fill(0n);
  for(let j=0;j<r;j++)for(let a=0;a<4;a++)for(let b=0;b<4;b++){
    t[j*N+4*a+b]=U[j][4*a+b];w.trace_map_assignments++;
    for(let d=0;d<4;d++){
      T1[4*b+d][j*N+4*a+d]+=U[j][4*a+b];
      T2[4*a+d][j*N+4*d+b]+=U[j][4*a+b];
      w.trace_map_assignments+=2;
    }
  }
  const K=Array.from({length:n},()=>Array(n).fill(0n));
  for(let i=0;i<n;i++)for(let j=i;j<n;j++){
    let s=(i%N===j%N)?4n*G[Math.floor(i/N)][Math.floor(j/N)]:0n;
    for(let row=0;row<N;row++){
      s-=2n*(T1[row][i]*T1[row][j]+T2[row][i]*T2[row][j]);
      w.trace_gram_products+=2;
    }
    s+=t[i]*t[j];w.full_trace_products++;w.form_entries++;
    K[i][j]=s;K[j][i]=s;
  }
  w.form_constructions++;
  const certificate=factorPSD(K,w);
  return {
    schema:SCHEMA,
    tensor:{local_dimension:4,side_dimension:N,left_columns:r,variables:n,
      variable_order:"left_column_then_row_major_right_pair",
      coefficient_convention:"C=U*V^T; no conjugation in this definition",
      form_scale:"4",state_expectation_denominator:"784"},
    provenance,left_columns:encodeInts(U),support_gram:encodeInts(G),
    support_gram_determinant:gd.toString(),
    trace_maps:{first:encodeInts(T1),second:encodeInts(T2),full:t.map(String)},
    integer_form:encodeInts(K),certificate,construction_work:w
  };
}
function complex(value,label) {
  if(Array.isArray(value)){
    if(value.length!==2)fail(label+" needs [real,imaginary].");
    return [parseRat(value[0],label+" real"),parseRat(value[1],label+" imaginary")];
  }
  return [parseRat(value,label),Z];
}
function cadd(a,b){return [add(a[0],b[0]),add(a[1],b[1])];}
function cscale(a,b){return [mul(a[0],b),mul(a[1],b)];}
function cnorm(a){return add(mul(a[0],a[0]),mul(a[1],a[1]));}
function cfmt(a){return [fmt(a[0]),fmt(a[1])];}
function openRetainedWernerFixedSupport(retained) {
  let snap;
  if(typeof retained==="string"){
    if(retained.length>WERNER_FIXED_SUPPORT_LIMITS.max_snapshot_characters)fail("Snapshot text is too large.");
    snap=JSON.parse(retained);
  }else{
    const encoded=JSON.stringify(retained);
    if(typeof encoded!=="string"||encoded.length>WERNER_FIXED_SUPPORT_LIMITS.max_snapshot_characters)fail("Snapshot object is absent or too large.");
    snap=JSON.parse(encoded);
  }
  if(!snap||snap.schema!==SCHEMA)fail("Unknown snapshot schema.");
  const U=supportColumns(snap.left_columns),r=U.length,n=r*N,w=emptyWork();
  const h=snap.tensor;
  if(!h||h.local_dimension!==4||h.side_dimension!==N||h.left_columns!==r||h.variables!==n||
    h.variable_order!=="left_column_then_row_major_right_pair"||
    h.coefficient_convention!=="C=U*V^T; no conjugation in this definition"||
    h.form_scale!=="4"||h.state_expectation_denominator!=="784")fail("Tensor convention mismatch.");
  if(typeof snap.provenance!=="string"||snap.provenance.length>2048)fail("Invalid provenance label.");
  const G=intMatrix(snap.support_gram,r,r,"support_gram"),K=intMatrix(snap.integer_form,n,n,"integer_form");
  if(G[0][0]<=0n||gramDet(G)<=0n||gramDet(G)!==integer(snap.support_gram_determinant,"support_gram_determinant",4096))
    fail("Invalid retained support Gram determinant.");
  for(let i=0;i<r;i++)for(let j=0;j<r;j++)if(G[i][j]!==G[j][i])fail("The retained Gram matrix is not symmetric.");
  for(let i=0;i<n;i++)for(let j=0;j<n;j++)if(K[i][j]!==K[j][i])fail("The retained form is not symmetric.");
  if(!snap.trace_maps)fail("Missing trace maps.");
  const T1=intMatrix(snap.trace_maps.first,N,n,"trace_maps.first");
  const T2=intMatrix(snap.trace_maps.second,N,n,"trace_maps.second");
  if(!Array.isArray(snap.trace_maps.full)||snap.trace_maps.full.length!==n)fail("Invalid full trace map.");
  const t=snap.trace_maps.full.map((x,i)=>integer(x,"trace_maps.full["+i+"]",4096));
  w.load_integer_entries=r*N+r*r+n*n+2*N*n+n+1;
  const c=snap.certificate;
  if(!c||!["ldlt_psd","negative_direction"].includes(c.kind))fail("Missing certificate.");
  const L=ratMatrix(c.L,n,n,"certificate.L");
  for(let i=0;i<n;i++)for(let j=i;j<n;j++)
    if(!eq(L[i][j],i===j?O:Z))fail("L must be unit lower triangular.");
  let D,negative=null;
  if(c.kind==="ldlt_psd"){
    if(!Array.isArray(c.D)||c.D.length!==n)fail("Wrong diagonal length.");
    D=c.D.map((x,i)=>parseRat(x,"D["+i+"]",4096,true));
    if(D.some(x=>x[0]<0n))fail("A PSD diagonal is negative.");
    const rank=D.filter(x=>x[0]>0n).length;
    if(c.rank!==rank||c.nullity!==n-rank||c.positive_definite!==(rank===n))fail("PSD summary mismatch.");
    parseRat(c.determinant,"determinant",4096,true);
  }else{
    index(c.completed_pivots,n,"completed_pivots");
    if(c.stopping_index!==c.completed_pivots)fail("Negative stopping index mismatch.");
    if(!Array.isArray(c.D)||c.D.length!==c.completed_pivots)fail("Wrong partial diagonal length.");
    D=c.D.map((x,i)=>parseRat(x,"D["+i+"]",4096,true));
    if(D.some(x=>x[0]<0n))fail("Completed pivots cannot be negative.");
    ratMatrix(c.residual,n-c.completed_pivots,n-c.completed_pivots,"residual");
    if(!Array.isArray(c.direction)||c.direction.length!==n)fail("Wrong negative direction length.");
    negative=c.direction.map((x,i)=>parseRat(x,"direction["+i+"]",4096,true));
    if(parseRat(c.form_value,"negative form_value",4096,true)[0]>=0n)fail("Negative witness value is not negative.");
  }
  w.load_rational_entries=n*n+D.length+(negative?n+(n-c.completed_pivots)**2+1:1);
  function vectors(columns,internal=false){
    dimensions(columns,r,N,"right_columns");
    const flat=[];
    for(let j=0;j<r;j++)for(let y=0;y<N;y++){
      const x=columns[j][y];
      if(internal)flat.push([parseRat(x,"internal right coordinate",4096,true),Z]);
      else flat.push(complex(x,"right_columns["+j+"]["+y+"]"));
    }
    return flat;
  }
  function evaluateFlat(v,includeCoefficients=false){
    w.evaluations++;
    let norm=Z;
    for(let a=0;a<r;a++)for(let b=0;b<r;b++)for(let y=0;y<N;y++){
      const z=add(mul(v[a*N+y][0],v[b*N+y][0]),mul(v[a*N+y][1],v[b*N+y][1]));
      norm=add(norm,mul(rat(G[a][b]),z));w.evaluation_gram_terms++;
    }
    const apply=rows=>rows.map(row=>{
      let s=[Z,Z];
      for(let j=0;j<n;j++){s=cadd(s,cscale(v[j],rat(row[j])));w.evaluation_trace_map_terms++;}
      return s;
    });
    const first=apply(T1),second=apply(T2),full=apply([t])[0];
    const normOf=a=>a.reduce((s,x)=>add(s,cnorm(x)),Z);
    const a=normOf(first),b=normOf(second),z=cnorm(full);
    const q4=add(sub(mul(rat(4n),norm),mul(rat(2n),add(a,b))),z);
    let sos=null,transformed=null,sosTerms=null;
    if(c.kind==="ldlt_psd"){
      transformed=[];sosTerms=[];sos=Z;
      for(let j=0;j<n;j++){
        let y=[Z,Z];
        for(let i=j;i<n;i++){y=cadd(y,cscale(v[i],L[i][j]));w.evaluation_factor_terms++;}
        const term=mul(D[j],cnorm(y));w.evaluation_sos_terms++;
        transformed.push(cfmt(y));sosTerms.push(fmt(term));sos=add(sos,term);
      }
      if(!eq(q4,sos))fail("The selected query disagrees with the retained sum-of-squares identity.");
    }else{
      let direct=Z;
      for(let i=0;i<n;i++)for(let j=0;j<n;j++){
        const z=add(mul(v[i][0],v[j][0]),mul(v[i][1],v[j][1]));
        direct=add(direct,mul(rat(K[i][j]),z));
      }
      if(!eq(q4,direct))fail("The selected query disagrees with the retained integer form.");
    }
    if(norm[0]<0n)fail("The selected norm is negative.");
    const output={
      right_columns:Array.from({length:r},(_,j)=>v.slice(j*N,(j+1)*N).map(cfmt)),
      norm_squared:fmt(norm),
      partial_trace_first:Array.from({length:4},(_,j)=>first.slice(4*j,4*j+4).map(cfmt)),
      partial_trace_second:Array.from({length:4},(_,j)=>second.slice(4*j,4*j+4).map(cfmt)),
      full_trace:cfmt(full),partial_trace_first_norm_squared:fmt(a),
      partial_trace_second_norm_squared:fmt(b),full_trace_norm_squared:fmt(z),
      form_value:fmt(q4),q_value:fmt(div(q4,rat(4n))),
      unnormalized_state_expectation:fmt(div(q4,rat(784n))),
      normalized_state_expectation:norm[0]===0n?null:fmt(div(q4,mul(rat(784n),norm))),
      transformed_coordinates:transformed,sum_of_squares_terms:sosTerms,
      sum_of_squares_value:sos===null?null:fmt(sos),
      query_identity_checked:true,
      retained_source_authentication:"external; loader does not reconstruct the form or factorization"
    };
    if(includeCoefficients){
      output.coefficient_matrix=Array.from({length:N},(_,x)=>Array.from({length:N},(_,y)=>{
        let vxy=[Z,Z];
        for(let j=0;j<r;j++){vxy=cadd(vxy,cscale(v[j*N+y],rat(U[j][x])));w.coefficient_terms++;}
        return cfmt(vxy);
      }));
    }
    return output;
  }
  function page(start,count,max,label){
    if(!Number.isSafeInteger(start)||start<0||start>max)fail(label+" start is out of range.");
    if(!Number.isSafeInteger(count)||count<0||count>32)fail(label+" count exceeds 32.");
    return Math.min(max,start+count);
  }
  const reader={
    summary(){
      return {schema:SCHEMA,local_dimension:4,left_columns:r,complex_variables:n,
        support_gram_determinant:snap.support_gram_determinant,
        status:c.kind,rank:c.kind==="ldlt_psd"?c.rank:null,
        nullity:c.kind==="ldlt_psd"?c.nullity:null,
        positive_definite:c.kind==="ldlt_psd"?c.positive_definite:false,
        determinant:c.kind==="ldlt_psd"?c.determinant:null,
        scope:"all complex right factors with this fixed real left support",
        loader_assurance:"structural checks and selected-query identities; no full certificate authentication",
        construction_work:clone(snap.construction_work)};
    },
    support(){return {left_columns:encodeInts(U),gram:encodeInts(G),provenance:snap.provenance};},
    formEntry(row,column){return K[index(row,n,"row")][index(column,n,"column")].toString();},
    formPage(start=0,count=32){
      const end=page(start,count,n,"formPage");w.matrix_rows_returned+=end-start;
      return {start,end,total:n,rows:encodeInts(K.slice(start,end)),next_start:end<n?end:null};
    },
    factorPage(start=0,count=32){
      if(c.kind!=="ldlt_psd")fail("Full factor rows require a PSD certificate.");
      const end=page(start,count,n,"factorPage");w.factor_rows_returned+=end-start;
      return {start,end,total:n,rows:L.slice(start,end).map((row,k)=>({
        index:start+k,diagonal:fmt(D[start+k]),lower_row:row.slice(0,start+k+1).map(fmt)
      })),next_start:end<n?end:null};
    },
    evaluate(right_columns,options={}){
      if(!options||typeof options!=="object"||(options.include_coefficients!==undefined&&typeof options.include_coefficients!=="boolean"))
        fail("include_coefficients must be Boolean.");
      return evaluateFlat(vectors(right_columns),options.include_coefficients===true);
    },
    factorDirection(column){
      if(c.kind!=="ldlt_psd")fail("Factor directions require a PSD certificate.");
      index(column,n,"factor column");
      const z=Array.from({length:n},(_,i)=>i===column?O:Z),x=backDirection(L,z,n,w);
      const columns=Array.from({length:r},(_,j)=>x.slice(j*N,(j+1)*N).map(fmt));
      const evaluation=evaluateFlat(vectors(columns,true));
      if(evaluation.form_value!==fmt(D[column]))fail("Factor direction does not isolate its retained diagonal.");
      return {factor_column:column,diagonal:fmt(D[column]),evaluation};
    },
    kernelColumns(){
      if(c.kind!=="ldlt_psd")fail("Kernel columns require a PSD certificate.");
      return D.flatMap((d,j)=>d[0]===0n?[j]:[]);
    },
    negativeDirection(){
      if(c.kind!=="negative_direction")return null;
      const columns=Array.from({length:r},(_,j)=>negative.slice(j*N,(j+1)*N).map(fmt));
      const evaluation=evaluateFlat(vectors(columns,true));
      if(evaluation.form_value!==c.form_value)fail("Negative witness value mismatch.");
      return {reason:c.reason,evaluation};
    },
    snapshot(){return clone(snap);},
    work(){return clone(w);}
  };
  return Object.freeze(reader);
}
module.exports = {
  compileWernerFixedSupport,openRetainedWernerFixedSupport,WERNER_FIXED_SUPPORT_LIMITS
};
