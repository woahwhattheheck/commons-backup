"use strict";

/* Finite stopped fair odd(3n +/- 1) process. No infinite convergence claim. */
const ABSORPTION_LIMITS=Object.freeze({
  max_states:128,max_matrix_cells:65536,max_elimination_updates:8000000,
  max_fraction_digits:1024,max_snapshot_chars:4000000,
  max_provenance_chars:16384,max_page_rows:32
});
const SCHEMA="commons.finite_fair_collatz_absorption/v1";
function fail(s){throw new RangeError(s);}
function small(v,name,lo,hi){
  if(typeof v!=="number"||!Number.isSafeInteger(v)||v<lo||v>hi)fail(name+" outside bounds");
  return v;
}
function copy(v){return JSON.parse(JSON.stringify(v));}
function gcd(a,b,work){
  a=a<0n?-a:a;b=b<0n?-b:b;
  while(b){const r=a%b;a=b;b=r;if(work)work.gcd_divisions++;}
  return a;
}
function rat(a,b=1n,work){
  if(!b)fail("zero denominator");
  if(b<0n){a=-a;b=-b;}
  if(!a)return[0n,1n];
  const g=gcd(a,b,work);return[a/g,b/g];
}
function add(a,b,w){return rat(a[0]*b[1]+b[0]*a[1],a[1]*b[1],w);}
function scale(a,b,w){return rat(a[0]*b,a[1],w);}
function divide(a,b,w){return rat(a[0],a[1]*b,w);}
function serial(a){
  if(a[0].toString().length>ABSORPTION_LIMITS.max_fraction_digits||
     a[1].toString().length>ABSORPTION_LIMITS.max_fraction_digits)fail("fraction digit cap");
  return{numerator:a[0].toString(),denominator:a[1].toString()};
}
function parseFraction(v){
  if(!v||typeof v.numerator!=="string"||typeof v.denominator!=="string"||
     v.numerator.length>ABSORPTION_LIMITS.max_fraction_digits||
     v.denominator.length>ABSORPTION_LIMITS.max_fraction_digits||
     !/^(0|[1-9][0-9]*)$/.test(v.numerator)||
     !/^[1-9][0-9]*$/.test(v.denominator))fail("invalid saved nonnegative fraction");
  return[BigInt(v.numerator),BigInt(v.denominator)];
}
function provenance(v){
  if(v===undefined)return null;
  const t=JSON.stringify(v);
  if(typeof t!=="string"||t.length>ABSORPTION_LIMITS.max_provenance_chars)fail("provenance cap");
  return JSON.parse(t);
}
function compileFiniteAbsorption(options){
  if(!options||typeof options!=="object")fail("options required");
  const max=small(options.max_odd,"max_odd",1,2*ABSORPTION_LIMITS.max_states-1);
  if(max%2!==1)fail("max_odd must be odd");
  const count=(max+1)/2;
  const work={compiler_calls:1,transitions:0,halvings:0,scc_edge_visits:0,
    reachability_edge_visits:0,elimination_updates:0,exact_divisions:0,
    row_swaps:0,back_substitution_terms:0,gcd_divisions:0,
    residual_equations:0,residual_terms:0,probability_partition_checks:0};
  const nodes=[];
  for(let n=1;n<=max;n+=2){
    const edges=[];
    for(const sign of [-1,1]){
      const raw=3*n+sign;let target=raw,halvings=0;
      while(target%2===0){target/=2;halvings++;work.halvings++;}
      edges.push({sign,raw,halvings,target});work.transitions++;
    }
    nodes.push({state:n,edges});
  }
  const ix=n=>(n-1)/2;
  // Tarjan on the internal transition graph, retaining all source edges separately.
  const discovery=Array(count).fill(-1),low=Array(count).fill(0),
    onStack=Array(count).fill(false),stack=[],parts=[];
  let next=0;
  function visit(v){
    discovery[v]=low[v]=next++;stack.push(v);onStack[v]=true;
    for(const e of nodes[v].edges){
      work.scc_edge_visits++;
      if(e.target>max)continue;
      const z=ix(e.target);
      if(discovery[z]<0){visit(z);low[v]=Math.min(low[v],low[z]);}
      else if(onStack[z])low[v]=Math.min(low[v],discovery[z]);
    }
    if(low[v]===discovery[v]){
      const part=[];let z;
      do{z=stack.pop();onStack[z]=false;part.push(nodes[z].state);}while(z!==v);
      part.sort((a,b)=>a-b);parts.push(part);
    }
  }
  for(let v=0;v<count;v++)if(discovery[v]<0)visit(v);
  parts.sort((a,b)=>a[0]-b[0]);
  const component=Array(count),components=[];
  parts.forEach((states,id)=>states.forEach(n=>component[ix(n)]=id));
  parts.forEach((states,id)=>{
    const closed=states.every(n=>nodes[ix(n)].edges.every(e=>
      e.target<=max&&component[ix(e.target)]===id));
    components.push({id,states,closed,contains_one:states.includes(1)});
  });
  const exits=Array.from(new Set(nodes.flatMap(n=>n.edges.filter(e=>e.target>max)
    .map(e=>e.target)))).sort((a,b)=>a-b);
  const outcomes=[{kind:"hit_one",key:"one",states:[1]},
    ...exits.map(n=>({kind:"first_exit",key:"exit:"+n,states:[n]})),
    ...components.filter(c=>c.closed&&!c.contains_one).map(c=>
      ({kind:"closed_class",key:"class:"+c.id,states:c.states,component:c.id}))];
  const outMap=new Map(outcomes.map((o,i)=>[o.key,i]));
  const terminal=Array(count).fill(-1);
  terminal[0]=0;
  for(let i=0;i<outcomes.length;i++)if(outcomes[i].kind==="closed_class")
    for(const n of outcomes[i].states)terminal[ix(n)]=i;
  function destination(e){
    return e.target>max?{outcome:outMap.get("exit:"+e.target)}:
      terminal[ix(e.target)]>=0?{outcome:terminal[ix(e.target)]}:{state:e.target};
  }
  // Reverse shortest paths certify that every nonterminal node can terminate.
  const reverse=Array.from({length:count},()=>[]),distance=Array(count).fill(null),
    toward=Array(count).fill(null),queue=[];
  for(let i=0;i<count;i++)if(terminal[i]>=0){distance[i]=0;queue.push(i);}
  for(let i=0;i<count;i++)for(const e of nodes[i].edges){
    if(e.target<=max)reverse[ix(e.target)].push({from:i,sign:e.sign});
    else if(distance[i]===null){distance[i]=1;toward[i]={sign:e.sign,target:e.target};queue.push(i);}
  }
  for(let p=0;p<queue.length;p++){
    const v=queue[p];
    for(const r of reverse[v]){
      work.reachability_edge_visits++;
      if(distance[r.from]===null){
        distance[r.from]=distance[v]+1;
        toward[r.from]={sign:r.sign,target:nodes[v].state};queue.push(r.from);
      }
    }
  }
  if(distance.some(x=>x===null))fail("unclassified closed graph component");
  const transient=nodes.filter((_,i)=>terminal[i]<0).map(x=>x.state),
    transMap=new Map(transient.map((n,i)=>[n,i])),t=transient.length,b=outcomes.length+1;
  if(t*(t+b)>ABSORPTION_LIMITS.max_matrix_cells)fail("matrix cell cap");
  let planned=0;for(let k=0;k<t-1;k++)planned+=(t-k-1)*(t+b-k-1);
  if(planned>ABSORPTION_LIMITS.max_elimination_updates)fail("elimination budget");
  const matrix=transient.map((n,i)=>{
    const row=Array(t+b).fill(0n);row[i]=2n;
    for(const e of nodes[ix(n)].edges){
      const d=destination(e);
      if(d.state!==undefined)row[transMap.get(d.state)]-=1n;
      else row[t+d.outcome]+=1n;
    }
    row[t+b-1]=2n;return row;
  });
  const original=matrix.map(row=>row.slice()),pivots=[];
  let previous=1n;
  for(let k=0;k<t-1;k++){
    let selected=k;while(selected<t&&matrix[selected][k]===0n)selected++;
    if(selected===t)fail("singular finite absorption system");
    if(selected!==k){[matrix[k],matrix[selected]]=[matrix[selected],matrix[k]];work.row_swaps++;}
    const pivot=matrix[k][k];
    pivots.push({column:k,selected_row:selected,pivot:pivot.toString(),
      previous_divisor:previous.toString()});
    for(let i=k+1;i<t;i++){
      const lower=matrix[i][k];
      for(let j=k+1;j<t+b;j++){
        const numerator=matrix[i][j]*pivot-lower*matrix[k][j];
        if(numerator%previous!==0n)fail("nonexact fraction-free division");
        matrix[i][j]=numerator/previous;work.elimination_updates++;work.exact_divisions++;
      }
      matrix[i][k]=0n;
    }
    previous=pivot;
  }
  if(t&&matrix[t-1][t-1]===0n)fail("singular final pivot");
  const solved=Array.from({length:t},()=>Array(b));
  for(let i=t-1;i>=0;i--)for(let c=0;c<b;c++){
    let value=[matrix[i][t+c],1n];
    for(let j=i+1;j<t;j++){
      value=add(value,scale(solved[j][c],-matrix[i][j],work),work);
      work.back_substitution_terms++;
    }
    solved[i][c]=divide(value,matrix[i][i],work);
    if(solved[i][c][0]<0n)fail("negative solved value");
  }
  const residuals=[];
  for(let i=0;i<t;i++){
    const row=[];
    for(let c=0;c<b;c++){
      let residual=[-original[i][t+c],1n];
      for(let j=0;j<t;j++)if(original[i][j]!==0n){
        residual=add(residual,scale(solved[j][c],original[i][j],work),work);
        work.residual_terms++;
      }
      if(residual[0]!==0n)fail("nonzero equation residual");
      row.push("0");work.residual_equations++;
    }
    residuals.push({state:transient[i],residuals:row});
  }
  const solutions=nodes.map((node,i)=>{
    let values;
    if(terminal[i]>=0){
      values=Array.from({length:b},(_,j)=>[j===terminal[i]?1n:0n,1n]);
    }else values=solved[transMap.get(node.state)];
    let sum=[0n,1n],exit=[0n,1n],closed=[0n,1n];
    for(let j=0;j<outcomes.length;j++){
      const v=values[j];
      if(v[0]>v[1])fail("probability above one");
      sum=add(sum,v,work);
      if(outcomes[j].kind==="first_exit")exit=add(exit,v,work);
      if(outcomes[j].kind==="closed_class")closed=add(closed,v,work);
    }
    if(sum[0]!==sum[1])fail("absorption mass not one");
    work.probability_partition_checks++;
    return{state:node.state,component:component[i],terminal_outcome:terminal[i]>=0?terminal[i]:null,
      distance_to_terminal:distance[i],toward_terminal:toward[i],
      probabilities:values.slice(0,-1).map(serial),expected_stopped_steps:serial(values[b-1]),
      eventual_hit_one_enclosure:{lower:serial(values[0]),upper:serial(add(values[0],exit,work))},
      exit_probability:serial(exit),closed_class_probability:serial(closed)};
  });
  const pathLength=Math.max(...distance);
  const snapshot={schema:SCHEMA,max_odd:max,model:{coin:"independent fair signs",
    transitions:"odd(3n-1),odd(3n+1)",one_absorbing:true,
    stopping:"first hit one, first domain exit, or first entry to another closed class"},
    nodes,components,outcomes,transient_states:transient,solutions,
    finite_termination:{maximum_witness_length:pathLength,
      success_probability_lower_bound:serial([1n,1n<<BigInt(pathLength)]),
      statement:"Conditional on not stopped, a terminal event occurs within L moves with probability at least 2^-L."},
    linear_system:{form:"A=2I-internal multiplicity; outcome RHS=terminal edge multiplicity; time RHS=2",
      outcome_columns:outcomes.map(o=>o.key),last_column:"expected_stopped_steps",
      original:original.map(row=>row.map(String)),fraction_free_upper:matrix.map(row=>row.map(String)),
      pivots,final_pivot:t?matrix[t-1][t-1].toString():null,residuals},
    provenance:provenance(options.provenance)};
  const text=JSON.stringify(snapshot);
  if(text.length>ABSORPTION_LIMITS.max_snapshot_chars)fail("snapshot character cap");
  return{status:"EXACT_STOPPED_CHAIN",snapshot,work,snapshot_chars:text.length};
}
function openRetainedAbsorption(input){
  const text=typeof input==="string"?input:JSON.stringify(input);
  if(typeof text!=="string"||text.length>ABSORPTION_LIMITS.max_snapshot_chars)fail("snapshot cap");
  const s=JSON.parse(text);
  if(!s||s.schema!==SCHEMA)fail("schema");
  const max=small(s.max_odd,"max_odd",1,2*ABSORPTION_LIMITS.max_states-1);
  if(max%2!==1)fail("odd domain");
  const n=(max+1)/2;
  if(!s.model||s.model.coin!=="independent fair signs"||s.model.one_absorbing!==true||
     s.model.transitions!=="odd(3n-1),odd(3n+1)")fail("model");
  if(!Array.isArray(s.nodes)||s.nodes.length!==n||!Array.isArray(s.solutions)||
     s.solutions.length!==n||!Array.isArray(s.outcomes)||!s.outcomes.length||
     s.outcomes.length>2*n+1||!Array.isArray(s.components)||!s.components.length||s.components.length>n||
     !Array.isArray(s.transient_states)||s.transient_states.length>n||!s.finite_termination)fail("snapshot tables");
  const stats={queries:0,saved_state_rows:0,saved_fraction_fields:0,
    page_rows_returned:0,mixture_terms:0,boundary_terms:0,gcd_divisions:0,
    compiler_calls:0,transition_recomputations:0,scc_recomputations:0,
    elimination_updates:0,equation_residual_recomputations:0};
  function frac(v){stats.saved_fraction_fields++;return parseFraction(v);}
  small(s.finite_termination.maximum_witness_length,"witness length",0,n);
  const bound=frac(s.finite_termination.success_probability_lower_bound);
  if(bound[0]===0n||bound[0]>bound[1])fail("termination bound");
  let prior=0;
  for(const v of s.transient_states){small(v,"transient state",1,max);if(v%2!==1||v<=prior)fail("transient ordering");prior=v;}
  if(s.outcomes[0].kind!=="hit_one"||s.outcomes[0].key!=="one"||JSON.stringify(s.outcomes[0].states)!=="[1]")fail("first outcome");
  for(const o of s.outcomes){
    if(!["hit_one","first_exit","closed_class"].includes(o.kind)||typeof o.key!=="string"||
       !Array.isArray(o.states)||!o.states.length||o.states.length>n)fail("outcome shape");
    for(const v of o.states){small(v,"outcome state",1,3*max+1);if(v%2!==1)fail("odd outcome");}
  }
  for(let i=0;i<n;i++){
    const node=s.nodes[i],row=s.solutions[i];
    if(node.state!==2*i+1||row.state!==node.state||!Array.isArray(node.edges)||
       node.edges.length!==2||!Array.isArray(row.probabilities)||
       row.probabilities.length!==s.outcomes.length)fail("state row");
    small(row.component,"component",0,s.components.length-1);
    small(row.distance_to_terminal,"distance",0,n);
    if(row.terminal_outcome!==null)small(row.terminal_outcome,"terminal outcome",0,s.outcomes.length-1);
    for(let j=0;j<2;j++){
      const e=node.edges[j];
      if(e.sign!==(j===0?-1:1))fail("sign ordering");
      small(e.raw,"raw",2,3*max+1);small(e.target,"target",1,3*max+1);
      if(e.target%2!==1)fail("odd target");
      small(e.halvings,"halvings",1,16);
    }
    for(const p of row.probabilities){const v=frac(p);if(v[0]>v[1])fail("probability");}
    frac(row.expected_stopped_steps);
    const lo=frac(row.eventual_hit_one_enclosure.lower),
      hi=frac(row.eventual_hit_one_enclosure.upper);
    if(lo[0]*hi[1]>hi[0]*lo[1]||hi[0]>hi[1])fail("enclosure");
    frac(row.exit_probability);frac(row.closed_class_probability);
    stats.saved_state_rows++;
  }
  provenance(s.provenance);
  // Structural loading does not establish transition, SCC, equation or probability correctness.
  function index(v){
    small(v,"state",1,max);if(v%2!==1)fail("state must be odd");return(v-1)/2;
  }
  function pageRows(rows,start,limit){
    small(start,"start",0,rows.length);small(limit,"limit",0,ABSORPTION_LIMITS.max_page_rows);
    const result=rows.slice(start,start+limit);stats.page_rows_returned+=result.length;
    const next=start+result.length;return{start,total:rows.length,records:copy(result),
      next_start:next<rows.length?next:null};
  }
  return Object.freeze({
    summary(){
      stats.queries++;
      return{schema:SCHEMA,max_odd:max,state_count:n,transient_states:s.transient_states.length,
        components:s.components.length,outcomes:s.outcomes.length,
        exit_outcomes:s.outcomes.filter(o=>o.kind==="first_exit").length,
        other_closed_classes:s.outcomes.filter(o=>o.kind==="closed_class").length,
        finite_termination:copy(s.finite_termination),reader_validation:"structural only"};
    },
    source(){stats.queries++;return copy(s.provenance);},
    state(v){stats.queries++;const i=index(v);return{node:copy(s.nodes[i]),solution:copy(s.solutions[i])};},
    page(options={}){
      stats.queries++;return pageRows(s.solutions,options.start===undefined?0:options.start,
        options.limit===undefined?16:options.limit);
    },
    outcomes(options={}){
      stats.queries++;return pageRows(s.outcomes,options.start===undefined?0:options.start,
        options.limit===undefined?16:options.limit);
    },
    mixture(entries){
      stats.queries++;
      if(!Array.isArray(entries)||!entries.length||entries.length>n)fail("mixture size");
      let total=[0n,1n],lo=[0n,1n],hi=[0n,1n],time=[0n,1n];
      const seen=new Set();
      for(const e of entries){
        const i=index(e.state);if(seen.has(i))fail("duplicate mixture state");seen.add(i);
        const w=parseFraction(e.weight);if(w[0]>w[1])fail("weight");
        total=add(total,w,stats);
        const row=s.solutions[i];
        function weighted(v){const f=parseFraction(v);return rat(f[0]*w[0],f[1]*w[1],stats);}
        lo=add(lo,weighted(row.eventual_hit_one_enclosure.lower),stats);
        hi=add(hi,weighted(row.eventual_hit_one_enclosure.upper),stats);
        time=add(time,weighted(row.expected_stopped_steps),stats);stats.mixture_terms++;
      }
      if(total[0]!==total[1])fail("mixture weights must sum to one");
      return{eventual_hit_one_enclosure:{lower:serial(lo),upper:serial(hi)},
        expected_stopped_steps:serial(time),states:entries.length};
    },
    boundary(state,values){
      stats.queries++;const row=s.solutions[index(state)];
      if(!Array.isArray(values))fail("boundary values");
      const exits=s.outcomes.map((o,i)=>({o,i})).filter(r=>r.o.kind==="first_exit");
      if(values.length!==exits.length)fail("supply one value for every exit");
      const map=new Map();
      for(const v of values){
        small(v.state,"exit state",max+1,3*max+1);
        if(map.has(v.state))fail("duplicate exit");
        const f=parseFraction(v.value);if(f[0]>f[1])fail("boundary value");map.set(v.state,f);
      }
      let value=parseFraction(row.probabilities[0]);
      for(const r of exits){
        const f=map.get(r.o.states[0]);if(!f)fail("missing exit");
        const p=parseFraction(row.probabilities[r.i]);
        value=add(value,rat(p[0]*f[0],p[1]*f[1],stats),stats);stats.boundary_terms++;
      }
      return{state,value:serial(value),scope:"Dirichlet evaluation. Equals original eventual-hit probability only if supplied exit values equal those unknown probabilities; other closed classes contribute zero."};
    },
    snapshot(){stats.queries++;return copy(s);},
    statistics(){return copy(stats);}
  });
}
module.exports={ABSORPTION_LIMITS,compileFiniteAbsorption,openRetainedAbsorption};
