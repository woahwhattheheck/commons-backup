#!/usr/bin/env python3
"""#12620 donor only: AST proof for Policy.act / E184 native-advance reachability."""
from __future__ import annotations
import ast, re

PARENT = re.compile(r"^_(?:V[0-9A-Z]+|SALE)_PARENT$")
class Reject(ValueError): pass

def req(x,m):
    if not x: raise Reject(m)

def truth(n):
    try: return bool(ast.literal_eval(n))
    except (ValueError, TypeError): return None

def terminates(body):
    for s in body:
        if isinstance(s,(ast.Return,ast.Raise)): return True
        if isinstance(s,ast.If):
            t=truth(s.test)
            if t is True and terminates(s.body): return True
            if t is False and terminates(s.orelse): return True
            if t is None and s.orelse and terminates(s.body) and terminates(s.orelse): return True
    return False

def live(body):
    for s in body:
        yield s
        if isinstance(s,ast.If):
            t=truth(s.test)
            if t is True:
                yield from live(s.body)
                if terminates(s.body): return
            elif t is False:
                yield from live(s.orelse)
                if terminates(s.orelse): return
            else:
                yield from live(s.body); yield from live(s.orelse)
                if s.orelse and terminates(s.body) and terminates(s.orelse): return
        elif isinstance(s,(ast.Return,ast.Raise)):
            return

def calls(fn,name):
    out=[]
    for n in live(fn.body):
        for x in ast.walk(n):
            if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and x is not n: continue
            if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id==name: out.append(x)
    return out

def policy_return(fn):
    for n in live(fn.body):
        if isinstance(n,ast.Return) and isinstance(n.value,ast.Call):
            c=n.value
            if (isinstance(c.func,ast.Attribute) and c.func.attr=='act' and
                isinstance(c.func.value,ast.Name) and c.func.value.id=='_POLICY' and
                len(c.args)==1 and not c.keywords and isinstance(c.args[0],ast.Name) and
                c.args[0].id=='observation'):
                return True
    return False

def class_method(cls,name):
    found=[]
    for s in cls.body:
        if isinstance(s,(ast.FunctionDef,ast.AsyncFunctionDef)) and s.name==name: found.append(s)
        elif isinstance(s,(ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Delete)):
            for x in ast.walk(s):
                if isinstance(x,ast.Name) and isinstance(x.ctx,(ast.Store,ast.Del)) and x.id==name:
                    raise Reject(f'Policy.{name} rebound')
    req(len(found)==1 and not found[0].decorator_list,f'bad Policy.{name}')
    return found[0]

def module_state(tree):
    cur={}; caps={}; adv_defs=[]; native=None; capline=-1
    custody={'POLICY_AGENT','_SALE_NATIVE_ADVANCE','advance_sales','Policy'}
    for s in tree.body:
        if isinstance(s,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            cur[s.name]=s
            if isinstance(s,(ast.FunctionDef,ast.AsyncFunctionDef)) and s.name=='advance_sales': adv_defs.append(s)
            continue
        if isinstance(s,ast.Assign) and all(isinstance(t,ast.Name) for t in s.targets):
            val=cur.get(s.value.id) if isinstance(s.value,ast.Name) else None
            for t in s.targets:
                name=t.id
                if name=='POLICY_AGENT' or PARENT.fullmatch(name):
                    req(isinstance(s.value,ast.Name) and isinstance(val,(ast.FunctionDef,ast.AsyncFunctionDef)),f'bad capture {name}')
                    req(name not in caps,f'duplicate capture {name}'); caps[name]=val
                if name=='_SALE_NATIVE_ADVANCE':
                    req(isinstance(s.value,ast.Name) and s.value.id=='advance_sales','bad native capture syntax')
                    req(len(adv_defs)==1 and val is adv_defs[0],'native must capture unique pre-E184 advance_sales')
                    req(native is None,'duplicate native capture'); native=val; capline=s.lineno
                cur[name]=val if isinstance(s.value,ast.Name) else s.value
            continue
        for x in ast.walk(s):
            if isinstance(x,ast.Name) and isinstance(x.ctx,(ast.Store,ast.Del)) and (x.id in custody or PARENT.fullmatch(x.id)):
                raise Reject(f'ambiguous top-level binding {x.id}')
    req(native is not None,'missing native capture')
    return cur,caps,native,capline

def resolve_agent(fn,caps):
    seen=set()
    while True:
        req(id(fn) not in seen,'parent cycle'); seen.add(id(fn))
        if policy_return(fn): return fn
        names={c.func.id for n in live(fn.body) for c in ast.walk(n)
               if isinstance(c,ast.Call) and isinstance(c.func,ast.Name) and c.func.id in caps}
        req(len(names)==1,f'{fn.name}: expected one parent edge')
        fn=caps[next(iter(names))]

def exact_delegate(fn):
    b=list(fn.body)
    if b and isinstance(b[0],ast.Expr) and isinstance(b[0].value,ast.Constant) and isinstance(b[0].value.value,str): b=b[1:]
    if not b or not isinstance(b[0],ast.If) or len(b[0].body)!=1: return False
    r=b[0].body[0]
    if not isinstance(r,ast.Return) or not isinstance(r.value,ast.Call): return False
    c=r.value
    if not isinstance(c.func,ast.Name) or c.func.id!='_SALE_NATIVE_ADVANCE' or c.keywords: return False
    return [a.id if isinstance(a,ast.Name) else None for a in c.args]==['action','view','state','tape','step']

def policy_e184_roots(tree):
    """Return (Policy.act, captured native advance_sales); fail closed otherwise."""
    cur,caps,native,capline=module_state(tree)
    va,vc,vs=cur.get('v3_agent'),cur.get('_v3_core'),cur.get('_v3_stack')
    pc,fa,pa=cur.get('Policy'),cur.get('advance_sales'),caps.get('POLICY_AGENT')
    req(isinstance(va,(ast.FunctionDef,ast.AsyncFunctionDef)),'no v3_agent')
    req(isinstance(vc,(ast.FunctionDef,ast.AsyncFunctionDef)),'no _v3_core')
    req(isinstance(vs,(ast.FunctionDef,ast.AsyncFunctionDef)),'no _v3_stack')
    req(isinstance(pc,ast.ClassDef),'no Policy')
    req(isinstance(fa,(ast.FunctionDef,ast.AsyncFunctionDef)),'no final advance_sales')
    req(pa is not None,'no POLICY_AGENT')
    req(calls(va,'_v3_core'),'v3_agent !> _v3_core')
    req(calls(vc,'_v3_stack'),'_v3_core !> _v3_stack')
    req(calls(vs,'POLICY_AGENT'),'_v3_stack !> POLICY_AGENT')
    resolve_agent(pa,caps)
    act=class_method(pc,'act')
    req(calls(act,'advance_sales'),'Policy.act !> advance_sales')
    req(native is not fa and fa.lineno>capline,'native capture/redefinition order broken')
    req(exact_delegate(fa),'final advance_sales lacks exact E184 native delegation')
    return act,native

FIX='''\
def advance_sales(action,view,state,tape,step):\n    if ADV:\n        import r04_advance\n        return r04_advance.apply(action)\n    return None\nclass Policy:\n    def act(self,observation):\n        if DEAD:\n            import r04_dead\n            return r04_dead.apply(observation)\n        advance_sales(action,view,state,tape,step)\n        return action\n_POLICY=None\ndef agent(observation,configuration=None):\n    return _POLICY.act(observation)\n_V216_PARENT=agent\ndef agent(observation,configuration=None):\n    return _V216_PARENT(observation,configuration)\nPOLICY_AGENT=agent\n_SALE_NATIVE_ADVANCE=advance_sales\ndef advance_sales(action,view,state,tape,step):\n    if step < ADVANCE_START:\n        return _SALE_NATIVE_ADVANCE(action,view,state,tape,step)\n    return None\ndef _v3_stack(observation,configuration=None):\n    return POLICY_AGENT(observation,configuration)\ndef _v3_core(observation,configuration=None):\n    return _v3_stack(observation,configuration)\ndef v3_agent(observation,configuration=None):\n    if not OUTER:\n        return _v3_core(observation,configuration)\n    return observation\n'''
def bad(src):
    try: policy_e184_roots(ast.parse(src))
    except Reject: return
    raise RuntimeError('poison passed')
def selftest():
    a,n=policy_e184_roots(ast.parse(FIX)); req(a.name=='act' and n.name=='advance_sales','positive failed')
    bad(FIX.replace('POLICY_AGENT=agent','def bogus(observation): return observation\nPOLICY_AGENT=bogus'))
    bad(FIX.replace('_SALE_NATIVE_ADVANCE=advance_sales','_SALE_NATIVE_ADVANCE=agent'))
    bad(FIX.replace('return _SALE_NATIVE_ADVANCE(action,view,state,tape,step)','return None'))
    bad(FIX.replace('advance_sales(action,view,state,tape,step)\n        return action','return action\n        advance_sales(action,view,state,tape,step)'))
    bad(FIX.replace('return POLICY_AGENT(observation,configuration)','return observation\n    POLICY_AGENT(observation,configuration)'))
    bad(FIX.replace('return _V216_PARENT(observation,configuration)','return observation\n    _V216_PARENT(observation,configuration)'))
    bad(FIX.replace('POLICY_AGENT=agent\n_SALE_NATIVE_ADVANCE=advance_sales','POLICY_AGENT=agent\ndef advance_sales(action,view,state,tape,step): return None\n_SALE_NATIVE_ADVANCE=advance_sales'))
if __name__=='__main__': selftest(); print('POLICY/E184 REACHABILITY DONOR OK')
