# SPDX-License-Identifier: Apache-2.0
"""Pure copy semantics: no game, actor or engine dependencies."""
from __future__ import annotations

from collections import OrderedDict, defaultdict
import copy
import math
import unittest

from state_copy import deepcopy_state


class Hook:
    calls = 0
    def __init__(self, linked=None):
        self.linked = linked
    def __deepcopy__(self, memo):
        type(self).calls += 1
        out = type(self)()
        memo[id(self)] = out
        out.linked = copy.deepcopy(self.linked, memo)
        return out


class StateCopyTests(unittest.TestCase):
    def test_nested_plain_values_and_order(self):
        value = {'a':[1,True,None,'str',b'bytes',1.2,3j],2:{'b':[]}}
        result = deepcopy_state(value)
        self.assertEqual(result,copy.deepcopy(value))
        self.assertEqual(list(result),list(value))
        self.assertIsNot(result,value)
        self.assertIsNot(result['a'],value['a'])

    def test_repeated_mutable_references_stay_shared_only_inside_copy(self):
        shared=[{'x':1}];value={'a':shared,'b':shared}
        result=deepcopy_state(value)
        self.assertIs(result['a'],result['b'])
        self.assertIsNot(result['a'],shared)
        result['a'][0]['x']=2
        self.assertEqual(value['a'][0]['x'],1)

    def test_list_cycle(self):
        value=[];value.append(value)
        result=deepcopy_state(value)
        self.assertIs(result[0],result)
        self.assertIsNot(result,value)

    def test_dict_cycle(self):
        value={};value['self']=value
        result=deepcopy_state(value)
        self.assertIs(result['self'],result)

    def test_mixed_cycle(self):
        value={'items':[]};value['items'].append(value)
        result=deepcopy_state(value)
        self.assertIs(result['items'][0],result)

    def test_scalar_identity_is_preserved(self):
        for value in (None,True,12345,1.2,3j,'large text',b'bytes'):
            with self.subTest(value=value):
                self.assertIs(deepcopy_state(value),value)

    def test_nonfinite_values_are_not_normalized(self):
        nan=float('nan');values=[nan,float('inf'),float('-inf')]
        result=deepcopy_state(values)
        self.assertIs(result[0],nan)
        self.assertTrue(math.isinf(result[1]))
        self.assertEqual(result[2],float('-inf'))

    def test_explicit_memo_has_standard_atomic_override_semantics(self):
        value=12345;replacement=object()
        self.assertIs(deepcopy_state(value,{id(value):replacement}),replacement)

    def test_explicit_memo_mutable_override(self):
        value=[];other=['memo']
        self.assertIs(deepcopy_state(value,{id(value):other}),other)

    def test_tuple_cycle_falls_back_without_losing_alias(self):
        inner=[];value=(inner,);inner.append(value)
        result=deepcopy_state(value)
        self.assertIs(result[0][0],result)
        self.assertIsNot(result,value)

    def test_sets_and_frozensets_match_stdlib(self):
        value={'set':{1,2},'frozen':frozenset((3,4))}
        result=deepcopy_state(value)
        self.assertEqual(result,copy.deepcopy(value))
        self.assertIs(type(result['set']),set)

    def test_container_subclasses_remain_subclasses(self):
        class List(list): pass
        class Dict(dict): pass
        value={'list':List([1]),'dict':Dict(x=2)}
        result=deepcopy_state(value)
        self.assertIs(type(result['list']),List)
        self.assertIs(type(result['dict']),Dict)

    def test_defaultdict_and_ordereddict_preserve_behavior(self):
        value=[defaultdict(list,x=[1]),OrderedDict((('b',2),('a',1)))]
        result=deepcopy_state(value)
        self.assertEqual(result[0]['new'],[])
        self.assertEqual(list(result[1]),['b','a'])

    def test_custom_hook_runs_once_after_plain_detection(self):
        shared=[];hook=Hook(shared)
        value={'before':shared,'hook':hook,'again':hook}
        Hook.calls=0
        result=deepcopy_state(value)
        self.assertEqual(Hook.calls,1)
        self.assertIs(result['hook'],result['again'])
        self.assertIs(result['hook'].linked,result['before'])

    def test_custom_hook_reference_back_to_root(self):
        value={};value['hook']=Hook(value)
        Hook.calls=0
        result=deepcopy_state(value)
        self.assertIs(result['hook'].linked,result)
        self.assertEqual(Hook.calls,1)

    def test_custom_key_falls_back_as_a_whole_graph(self):
        key=Hook();value={key:key}
        Hook.calls=0
        result=deepcopy_state(value)
        copied_key=next(iter(result))
        self.assertIs(result[copied_key],copied_key)
        self.assertEqual(Hook.calls,1)

    def test_custom_copy_exception_propagates(self):
        class Broken:
            def __deepcopy__(self,memo): raise RuntimeError('retained exception')
        with self.assertRaisesRegex(RuntimeError,'retained exception'):
            deepcopy_state({'x':Broken()})

    def test_noncopyable_generator_keeps_normal_error(self):
        value=(x for x in range(3))
        with self.assertRaises(TypeError):deepcopy_state(value)

    def test_key_and_value_scalars_match_original_identity(self):
        key='unusual'+str(id(self));value={key:[key]}
        result=deepcopy_state(value)
        self.assertIs(next(iter(result)),key)
        self.assertIs(result[key][0],key)

    def test_no_stdlib_global_patch(self):
        before=copy.deepcopy
        deepcopy_state({'x':[1,2,3]})
        self.assertIs(copy.deepcopy,before)


if __name__=='__main__':unittest.main(verbosity=2)
