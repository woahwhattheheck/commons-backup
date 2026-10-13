"use strict";
const OUTCOMES=["normal","horizon","leaf_limit"];
function exact(x,name){if(typeof x==="bigint")return x;if(typeof x==="number"&&Number.isSafeInteger(x))return BigInt(x);if(typeof x==="string"&&/^(0|[1-9][0-9]*)$/.test(x))return BigInt(x);throw new TypeError(name+" must be a nonnegative exact integer");}
function compile(input){
  const {rootLeaves:N,horizon:H,leafCap:C}=input;
  if(!Number.isInteger(N)||N<1||N>9||!Number.isInteger(H)||H<0||H>10||!Number.isInteger(C)||C<N||C>20)throw new RangeError("compile bounds");
  const work={applicationRequests:0,syntaxNodesCreated:1,rootForms:0,redexOccurrenceVisits:0,
    redexMatches:0,contractions:0,ancestorRebuilds:0,stateBuilds:0,stateHits:0,
    coefficientAdditions:0,historyEnumeration:0};
  const terms=[{id:0,kind:"S",leaves:1}],apps=new Map();
  function app(left,right){
    work.applicationRequests++;const key=left+","+right;if(apps.has(key))return apps.get(key);
    const id=terms.length;terms.push({id,kind:"app",left,right,leaves:terms[left].leaves+terms[right].leaves});
    apps.set(key,id);work.syntaxNodesCreated++;return id;
  }
  const byLeaves=Array.from({length:N+1},()=>[]);byLeaves[1]=[0];
  for(let n=2;n<=N;n++)for(let a=1;a<n;a++)for(const l of byLeaves[a])for(const r of byLeaves[n-a])byLeaves[n].push(app(l,r));
  const roots=byLeaves[N].slice();work.rootForms=roots.length;
  const redexCache=new Map(),arcCache=new Map(),states=[],memo=new Map();
  function redexes(term){
    if(redexCache.has(term))return redexCache.get(term);
    const out=[];
    function walk(id,address){
      work.redexOccurrenceVisits++;const n=terms[id];if(n.kind!=="app")return;
      const a=terms[n.left],b=a.kind==="app"?terms[a.left]:null;
      if(b&&b.kind==="app"&&b.left===0){out.push(address);work.redexMatches++;}
      walk(n.left,address+"0");walk(n.right,address+"1");
    }
    walk(term,"");redexCache.set(term,out);return out;
  }
  function contract(term,address,at=0){
    const n=terms[term];
    if(at<address.length){work.ancestorRebuilds++;return address[at]==="0"?app(contract(n.left,address,at+1),n.right):app(n.left,contract(n.right,address,at+1));}
    const a=terms[n.left],b=terms[a.left],x=b.right,y=a.right,z=n.right;
    work.contractions++;return app(app(x,z),app(y,z));
  }
  function arcs(term){
    if(arcCache.has(term))return arcCache.get(term);
    const out=redexes(term).map(address=>({address,targetTerm:contract(term,address)}));
    arcCache.set(term,out);return out;
  }
  function visit(term,remaining){
    const key=term+"@"+remaining;if(memo.has(key)){work.stateHits++;return memo.get(key);}
    const id=states.length;memo.set(key,id);states.push(null);work.stateBuilds++;
    if(states.length>200000)throw new RangeError("state construction allowance exhausted");
    const counts=Object.fromEntries(OUTCOMES.map(o=>[o,Array(remaining+1).fill(0n)])),edges=[];
    let terminal=null;const rs=redexes(term);
    if(rs.length===0){terminal="normal";counts.normal[0]=1n;}
    else if(remaining===0){terminal="horizon";counts.horizon[0]=1n;}
    else for(const a of arcs(term)){
      if(terms[a.targetTerm].leaves>C){edges.push({...a,targetState:null,cutoff:"leaf_limit"});counts.leaf_limit[1]+=1n;}
      else{const child=visit(a.targetTerm,remaining-1);edges.push({...a,targetState:child,cutoff:null});
        for(const o of OUTCOMES)for(let k=0;k<states[child].counts[o].length;k++){
          work.coefficientAdditions++;counts[o][k+1]+=BigInt(states[child].counts[o][k]);
        }}
    }
    states[id]={id,term,remaining,terminal,edges,counts:Object.fromEntries(OUTCOMES.map(o=>[o,counts[o].map(String)]))};return id;
  }
  const rootRecords=roots.map((term,index)=>{const state=visit(term,H);return {index,term,state,counts:states[state].counts};});
  const totals=Object.fromEntries(OUTCOMES.map(o=>[o,Array(H+1).fill(0n)]));
  for(const root of rootRecords)for(const o of OUTCOMES)for(let k=0;k<=H;k++)totals[o][k]+=BigInt(root.counts[o][k]);
  const summary={roots:roots.length,syntaxNodes:terms.length,states:states.length,
    redexTerms:redexCache.size,contractedTerms:arcCache.size,
    stateEdges:states.reduce((s,x)=>s+x.edges.length,0),
    outcomeBySteps:Object.fromEntries(OUTCOMES.map(o=>[o,totals[o].map(String)]))};
  return {schema:"ppl004.pure-s-histories/v1",input,terms,states,roots:rootRecords,
    redexes:Array.from(redexCache,([term,addresses])=>({term,addresses})),
    arcs:Array.from(arcCache,([term,edges])=>({term,edges})),summary,constructionWork:work};
}
function createReader(saved){
  if(!saved||saved.schema!=="ppl004.pure-s-histories/v1")throw new TypeError("saved schema");
  const H=saved.input.horizon,conditions=new Map();
  const work={rootProfileReads:0,coefficientReads:0,conditionBuilds:0,conditionHits:0,
    prefixEdgeReads:0,selectEdgeReads:0,rankEdgeReads:0,termNodeReads:0,
    newContractions:0,newRedexSearches:0,newCoefficients:0};
  const copy=x=>JSON.parse(JSON.stringify(x));
  function root(index){if(!Number.isInteger(index)||index<0||index>=saved.roots.length)throw new RangeError("root index");return saved.roots[index];}
  function outcome(s){if(!OUTCOMES.includes(s))throw new RangeError("outcome");return s;}
  function steps(k){if(!Number.isInteger(k)||k<0||k>H)throw new RangeError("steps");return k;}
  function terminal(c){return c.cutoff||saved.states[c.state].terminal;}
  function coefficient(c,o,k){work.coefficientReads++;if(k<0)return 0n;
    if(c.cutoff)return o===c.cutoff&&k===0?1n:0n;
    return BigInt(saved.states[c.state].counts[o][k]||"0");
  }
  function next(c,e){return {state:e.targetState,term:e.targetTerm,cutoff:e.cutoff,
    addresses:c.addresses.concat(e.address),terms:c.terms.concat(e.targetTerm)};}
  function context(index,prefix=[]){
    const r=root(index);if(!Array.isArray(prefix)||prefix.some(a=>typeof a!=="string"||!/^[01]*$/.test(a)))throw new TypeError("address prefix");
    const key=index+":"+JSON.stringify(prefix);
    if(conditions.has(key)){work.conditionHits++;return conditions.get(key);}
    work.conditionBuilds++;
    let c={state:r.state,term:r.term,cutoff:null,addresses:[],terms:[r.term]};
    for(const address of prefix){
      if(terminal(c))throw new RangeError("prefix continues beyond a stopped history");
      let found=null;for(const e of saved.states[c.state].edges){work.prefixEdgeReads++;if(e.address===address){found=e;break;}}
      if(!found)throw new RangeError("prefix address is not a recorded redex");c=next(c,found);
    }
    conditions.set(key,c);return c;
  }
  function condition(index,prefix=[]){
    const c=context(index,prefix),shift=c.addresses.length;
    return {root:index,prefix:c.addresses.slice(),term:c.term,state:c.state,stopped:terminal(c),
      counts:Object.fromEntries(OUTCOMES.map(o=>[o,Array.from({length:H+1},(_,k)=>coefficient(c,o,k-shift).toString())]))};
  }
  function count(index,o,totalSteps,prefix=[]){
    outcome(o);steps(totalSteps);const c=context(index,prefix);
    return {root:index,outcome:o,steps:totalSteps,prefix:c.addresses.slice(),count:coefficient(c,o,totalSteps-c.addresses.length).toString()};
  }
  function select(index,o,totalSteps,rankValue,prefix=[]){
    outcome(o);steps(totalSteps);const rr=exact(rankValue,"rank");
    let c=context(index,prefix),k=totalSteps-c.addresses.length,r=rr;
    if(r<0n||r>=coefficient(c,o,k))throw new RangeError("rank outside selected history family");
    while(!terminal(c)){
      let found=null;for(const e of saved.states[c.state].edges){work.selectEdgeReads++;const child=next(c,e),n=coefficient(child,o,k-1);
        if(r<n){found=child;break;}r-=n;}
      if(!found)throw new Error("saved coefficient has no selecting branch");
      c=found;k--;
    }
    if(k!==0||terminal(c)!==o)throw new Error("selected terminal mismatch");
    return {root:index,outcome:o,steps:totalSteps,rank:rr.toString(),prefix:prefix.slice(),
      addresses:c.addresses.slice(),terms:c.terms.slice(),finalTerm:c.term};
  }
  function rank(index,o,totalSteps,path,prefix=[]){
    outcome(o);steps(totalSteps);if(!Array.isArray(path)||path.length!==totalSteps||prefix.some((a,i)=>path[i]!==a))throw new RangeError("history length or prefix");
    let c=context(index,prefix),k=totalSteps-c.addresses.length,r=0n;
    for(let i=prefix.length;i<path.length;i++){
      if(terminal(c))throw new RangeError("history continues beyond stop");
      let found=null;for(const e of saved.states[c.state].edges){work.rankEdgeReads++;const child=next(c,e);
        if(e.address===path[i]){found=child;break;}r+=coefficient(child,o,k-1);}
      if(!found)throw new RangeError("history address is not a recorded redex");c=found;k--;
    }
    if(k!==0||terminal(c)!==o)throw new RangeError("history does not end in requested outcome");
    return {root:index,outcome:o,steps:totalSteps,prefix:prefix.slice(),addresses:path.slice(),rank:r.toString(),finalTerm:c.term};
  }
  function term(id){
    if(!Number.isInteger(id)||id<0||id>=saved.terms.length)throw new RangeError("term id");
    function render(i){work.termNodeReads++;const n=saved.terms[i];return n.kind==="S"?"S":"("+render(n.left)+" "+render(n.right)+")";}
    return {id,leaves:saved.terms[id].leaves,text:render(id)};
  }
  return {summary:()=>copy({summary:saved.summary,constructionWork:saved.constructionWork}),
    rootProfiles:()=>{work.rootProfileReads+=saved.roots.length;return copy(saved.roots);},
    rootProfile:index=>{work.rootProfileReads++;return copy(root(index));},
    condition,count,select,rank,term,
    work:()=>copy(work),caches:()=>copy({conditions:Array.from(conditions.entries())})};
}
module.exports={compile,createReader};
