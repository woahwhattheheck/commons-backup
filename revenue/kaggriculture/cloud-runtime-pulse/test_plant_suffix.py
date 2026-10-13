# SPDX-License-Identifier: Apache-2.0
"""Value/order/immutability equivalence to the original Counter construction."""
import copy
from collections import Counter
import random
from types import MappingProxyType
import unittest
from plant_suffix import immutable_plant_suffixes


def original(route):
    suffix=[Counter() for _ in range(len(route)+1)]
    for step in range(len(route)-1,-1,-1):
        suffix[step]=suffix[step+1].copy()
        row=route[step]
        for action in [row.get('farmer',[]),*row.get('hands',[])]:
            if len(action)>=2 and action[0]=='PLANT':
                suffix[step][action[1]]+=1
    return tuple(MappingProxyType(dict(c)) for c in suffix)


class PlantSuffixTests(unittest.TestCase):
    def assert_equivalent(self,route):
        before=copy.deepcopy(route)
        old,new=original(route),immutable_plant_suffixes(route)
        self.assertEqual(len(new),len(route)+1)
        self.assertIs(type(new),tuple)
        self.assertEqual(route,before)
        self.assertEqual([list(x.items()) for x in old],[list(x.items()) for x in new])
        self.assertEqual(len({id(x) for x in new}),len(new))
        for item in new:
            self.assertIs(type(item),MappingProxyType)
            with self.assertRaises(TypeError):item['forbidden']=3
        return new

    def test_empty_route(self):self.assert_equivalent([])

    def test_missing_empty_unknown_actions(self):
        self.assert_equivalent([{}, {'farmer':[],'hands':[[],['PLANT'],['PASS']]},
                                {'farmer':['BUY_SEED','A',4],'market':[['PLANT','A']]}])

    def test_multiple_same_crop_at_one_step(self):
        result=self.assert_equivalent([{'farmer':['PLANT','A'],'hands':[['PLANT','A'],['PLANT','B'],['PLANT','A']]}])
        self.assertEqual(dict(result[0]),{'A':3,'B':1});self.assertEqual(dict(result[1]),{})

    def test_insertion_order_preserved(self):
        self.assert_equivalent([{'farmer':['PLANT','B']}, {'farmer':['PLANT','A'],'hands':[['PLANT','C']]}])

    def test_route_mutation_does_not_change_tables(self):
        route=[{'farmer':['PLANT','A'],'hands':[['PLANT','B']]}]
        result=self.assert_equivalent(route)
        route[0]['farmer'][1]='C';route[0]['hands'].clear();route.append({})
        self.assertEqual(dict(result[0]),{'A':1,'B':1});self.assertEqual(len(result),2)

    def test_separate_constructions_are_detached(self):
        a=immutable_plant_suffixes([{}]);b=immutable_plant_suffixes([{}])
        self.assertIsNot(a,b);self.assertIsNot(a[0],b[0])

    def test_tuple_sequence_and_non_string_hashable_keys(self):
        self.assert_equivalent(({'farmer':('PLANT',0),'hands':[('PLANT',('A',1)),('PLANT',None)]},))

    def test_malformed_input_exception_classes_match(self):
        for route in [[None],[{'hands':None}],[{'farmer':None}],[{'farmer':['PLANT',[]]}]]:
            exceptions=[]
            for implementation in (original,immutable_plant_suffixes):
                try:implementation(route)
                except Exception as exc:exceptions.append(type(exc))
            self.assertEqual(len(exceptions),2);self.assertIs(exceptions[0],exceptions[1])

    def test_generated_routes(self):
        rng=random.Random(9021307)
        crops=['A','B','C','D','E']
        def action():return rng.choice([[],['PASS'],['PLANT'],['PLANT',rng.choice(crops)],['WATER']])
        for _ in range(1000):
            self.assert_equivalent([{'farmer':action(),'hands':[action() for _ in range(rng.randrange(5))]}
                                   for _ in range(rng.randrange(41))])


if __name__=='__main__':unittest.main(verbosity=2)
