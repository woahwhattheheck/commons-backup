# SPDX-License-Identifier: Apache-2.0
"""Standalone JSON-value clone regressions; no private game input required."""
import copy
from decimal import Decimal
import json
import math
import random
import unittest
from observed_clone import detached_json_value

class WrappedDict(dict):
    """A JSON mapping wrapper without extra JSON fields."""

def wrap(value):
    if isinstance(value,dict):return WrappedDict({k:wrap(v) for k,v in value.items()})
    if isinstance(value,list):return [wrap(v) for v in value]
    return value

def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

class JsonValueTests(unittest.TestCase):
    def test_scalars_exact(self):
        for value in [None,False,True,0,-1,2**80,0.0,-0.0,1.25,'','a\x00b','\u2603']:
            self.assertEqual(encoded(detached_json_value(value)),encoded(value))
            self.assertIs(type(detached_json_value(value)),type(value))
        self.assertEqual(math.copysign(1,detached_json_value(-0.0)),-1)

    def test_plain_nested_value(self):
        value={'a':[None,{},[],{'x':3}], 'b':{'same':False}}
        self.assertEqual(detached_json_value(value),copy.deepcopy(value))

    def test_struct_normalizes_only_json_value(self):
        value=wrap({'a':[{'x':3}], 'b':None})
        result=detached_json_value(value)
        self.assertIs(type(result),dict);self.assertIs(type(result['a'][0]),dict)
        self.assertEqual(encoded(result),encoded(value))

    def test_every_container_detached(self):
        value=wrap({'a':[{'x':[1]}],'b':{'c':[]}})
        result=detached_json_value(value)
        def walk(a,b):
            if isinstance(a,dict):
                self.assertIsNot(a,b)
                for k in a:walk(a[k],b[k])
            elif isinstance(a,list):
                self.assertIsNot(a,b)
                for x,y in zip(a,b):walk(x,y)
        walk(value,result)
        result['a'][0]['x'].append(2);result['b']['c'].append(3)
        self.assertEqual(value['a'][0]['x'],[1]);self.assertEqual(value['b']['c'],[])

    def test_unknown_nested_fields_retained(self):
        value={'future_field':{'nested':[{'future_number':123.4}]}}
        self.assertEqual(detached_json_value(value),value)
        self.assertIsNot(detached_json_value(value)['future_field'],value['future_field'])

    def test_mapping_order_preserved(self):
        value={k:i for i,k in enumerate(['z','a','b','0'])}
        self.assertEqual(list(detached_json_value(value)),list(value))

    def test_non_json_leaf_delegates(self):
        value={'diagnostic':Decimal('1.234')}
        self.assertEqual(detached_json_value(value),copy.deepcopy(value))

    def test_random_json_values(self):
        rng=random.Random(251)
        def tree(depth):
            if depth==0 or rng.random()<.4:
                return rng.choice([None,False,True,rng.randrange(-100000,100000),rng.random(),'x'])
            if rng.random()<.5:return [tree(depth-1) for _ in range(rng.randrange(6))]
            return {str(i):tree(depth-1) for i in range(rng.randrange(6))}
        for _ in range(1000):
            value=tree(5)
            self.assertEqual(encoded(detached_json_value(wrap(value))),encoded(value))


if __name__=="__main__":
    unittest.main(verbosity=2)
