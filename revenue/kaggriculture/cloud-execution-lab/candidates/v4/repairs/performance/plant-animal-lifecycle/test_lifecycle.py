# SPDX-License-Identifier: Apache-2.0
"""Independent native/official-engine parity, shape, alias and source controls.

PHENOLOGY_RUNTIME must point at the authenticated artifact-native package.
PHENOLOGY_MUTANT is for the negative-control gate, never for installation.
"""
from __future__ import annotations
import ast
import copy
import os
import unittest
from pathlib import Path

from evidence_support import NAMES, initial, invoke, load_inputs, module, signature, world
from repair_lifecycle import FUNCTION_SHA256, function_spans, repair_source

MUTANTS = {
    'decay_parity': ('if (step - mls) % 2 != 0:', 'if (step - mls) % 2 == 0:'),
    'water_threshold': ('if tile["consecutive_unwatered"] >= 2:', 'if tile["consecutive_unwatered"] >= 3:'),
    'fertilizer_water': ('fertilized = was_watered and ', 'fertilized = '),
    'animal_escape': ('if tile["consecutive_unfed"] >= 2:', 'if tile["consecutive_unfed"] >= 3:'),
    'care_carry': ('tile.pop("pending_care_bonus", 0) if tile["fed_today"] else 0', '0'),
    'visit_tail': ('for x in columns:', 'for x in range(len(row)):'),
    'copy_rows': ('row = tiles[y]', 'row = list(tiles[y])'),
}


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = Path(os.environ['PHENOLOGY_RUNTIME'])
        cls.source, cls.base, cls.candidate, cls.loader, cls.engine = load_inputs(cls.runtime)
        mutant = os.environ.get('PHENOLOGY_MUTANT')
        if mutant:
            old, new = MUTANTS[mutant]
            altered = repair_source(cls.source)
            if old not in altered:
                raise RuntimeError('negative control did not engage source')
            cls.candidate = module(altered.replace(old, new), 'negative_control')
        cls.args = [(name, args) for name, values in (
            (NAMES[0], [(s,) for s in (0, 1, 23, 24, 25, 48, 96, 199, 200, 201, 718)]),
            (NAMES[1], [(day, turns) for day in (-1, 0, 1, 3, 7, 9, 10, 11, 17, 29) for turns in (1, 24)]),
            (NAMES[2], [(day,) for day in (-1, 0, 1, 3, 5, 7, 9, 11, 17, 29)]),
        ) for args in values]

    def compare(self, farm, name, args):
        outcomes = [invoke(getattr(m, name), copy.deepcopy(farm), args)
                    for m in (self.base, self.engine, self.candidate)]
        self.assertEqual(outcomes[0], outcomes[1], 'native versus full official primitive')
        self.assertEqual(outcomes[0], outcomes[2], 'candidate changed ordered data/alias/error behavior')

    def test_01_exact_official_definitions(self):
        source = (self.runtime/'checks/reference/engine/kaggriculture.py').read_text()
        official = function_spans(source)
        native = function_spans(self.source)
        for name in NAMES:
            self.assertEqual(official[name][2], native[name][2])

    def test_02_physiological_matrix(self):
        for seed in range(32):
            farm = world(self.base, seed)
            for name, args in self.args:
                with self.subTest(seed=seed, function=name, args=args):
                    self.compare(farm, name, args)

    def test_03_aliases_and_row_replacement(self):
        for kind in ('plant', 'animal'):
            tile = (self.base._new_plant('WHEAT', 0, 24) if kind == 'plant'
                    else self.base._new_animal('COW', 0))
            tile.update(yield_units=1, max_lifespan_step=0, consecutive_unwatered=1,
                        consecutive_unfed=1, fed_today=False)
            row = [tile, tile]
            farm = {'tiles': [row, row], 'external_tile': tile, 'external_row': row}
            for name, args in self.args:
                with self.subTest(kind=kind, function=name, args=args):
                    self.compare(farm, name, args)

    def test_04_empty_wide_ragged_and_immutable_rows(self):
        tile = self.base._new_plant('WHEAT', 0, 24)
        tile.update(max_lifespan_step=0, yield_units=1)
        shapes = [[], [[]], [[], []], [[None, None, tile], [None, None, tile]],
                  [[tile], [tile, tile]], [(tile, tile), (None, None)]]
        for tiles in shapes:
            for name, args in self.args:
                with self.subTest(shape=repr(tiles), function=name, args=args):
                    self.compare({'tiles': tiles}, name, args)

    def test_05_all_crop_and_animal_boundary_values(self):
        for crop, data in self.base.CROPS.items():
            for watered in (False, True):
                for quantity in (0, 1, data['max_yield']):
                    tile = self.base._new_plant(crop, 0, 24)
                    tile.update(watered_today=watered, yield_units=quantity, fertilized_until_day=10)
                    for name, args in self.args:
                        self.compare({'tiles': [[tile]]}, name, args)
        for animal, data in self.base.ANIMALS.items():
            for fed in (False, True):
                for cared in (False, True):
                    for bonus in (0, 1, 3):
                        tile = self.base._new_animal(animal, 0)
                        tile.update(fed_today=fed, cared_today=cared, pending_care_bonus=bonus,
                                    yield_units=data['max_held']-1)
                        for name, args in self.args:
                            self.compare({'tiles': [[tile]]}, name, args)

    def test_06_multiday_sequence(self):
        farms = [world(self.base, 99) for _ in range(3)]
        for step in range(720):
            for farm, m in zip(farms, (self.base, self.engine, self.candidate)):
                for y, row in enumerate(farm['tiles']):
                    for x, tile in enumerate(row):
                        if isinstance(tile, dict):
                            if tile.get('kind') == 'PLANT' and (step+x+y)%3 == 0:
                                tile['watered_today'] = True
                            if 'animal' in tile:
                                if (step+x)%5 == 0: tile['fed_today'] = True
                                if (step+y)%7 == 0: tile['cared_today'] = True
                m._decay_plants(farm, step)
                if (step+1)%24 == 0:
                    m._daily_refresh_plants(farm, step//24, 24)
                    m._daily_refresh_animals(farm, step//24)
            self.assertEqual(signature(farms[0]), signature(farms[1]))
            self.assertEqual(signature(farms[0]), signature(farms[2]))

    def test_07_full_interpreter_pairs_both_seats(self):
        originals = {name: getattr(self.engine, name) for name in NAMES}
        try:
            for seed in range(12):
                for seat in (0, 1):
                    for step in (22, 23, 239, 263, 718):
                        state, env = initial(self.loader, self.engine, seed)
                        for idx in (0, 1):
                            state[0].observation.farms[idx]['tiles'] = world(self.base, seed*3+idx)['tiles']
                            state[idx].observation.step = step
                            farm = state[0].observation.farms[idx]
                            farm['farmer'] = [seed%10, (seed*3)%10]
                            state[idx].action = {'farmer': ['WATER'] if idx == seat else ['FEED'],
                                                 'hands': [['PLANT', 'WHEAT']],
                                                 'market': [['SELL', 'FERTILIZER', 2], ['BUY', 'WHEAT', 1]]}
                        baseline, candidate = copy.deepcopy((state, env)), copy.deepcopy((state, env))
                        for name in NAMES: setattr(self.engine, name, originals[name])
                        self.engine.interpreter(*baseline)
                        for name in NAMES: setattr(self.engine, name, getattr(self.candidate, name))
                        self.engine.interpreter(*candidate)
                        with self.subTest(seed=seed, seat=seat, step=step):
                            self.assertEqual(signature(baseline), signature(candidate))
                        for name in NAMES: setattr(self.engine, name, originals[name])
        finally:
            for name in NAMES: setattr(self.engine, name, originals[name])

    def test_08_peer_source_preservation(self):
        extra = '\n# peer exact delta\nSENTINEL = {"geometry": 42}\n'
        altered = self.source.replace('def _is_shed_adjacent(', 'def _peer_is_shed_adjacent(') + extra
        out = repair_source(altered)
        self.assertTrue(out.endswith(extra))
        for source in (altered, out):
            nodes = ast.parse(source).body
            others = [node for node in nodes if not isinstance(node, ast.FunctionDef) or node.name not in NAMES]
            tree = ast.dump(ast.Module(body=others, type_ignores=[]))
            if source == altered: before = tree
            else: self.assertEqual(before, tree)
        # Exact surrounding bytes, not just AST equivalence.
        def without_targets(source):
            lines = source.splitlines(True)
            for start, end, _ in sorted(function_spans(source).values(), reverse=True):
                lines[start:end] = []
            return ''.join(lines)
        self.assertEqual(without_targets(altered), without_targets(out))

    def test_09_source_drift_fails_closed(self):
        for name in NAMES:
            with self.assertRaises(ValueError):
                repair_source(self.source.replace('def '+name+'(', 'def renamed_'+name+'('))
        with self.assertRaises(ValueError):
            repair_source(self.source.replace('board_size = len(farm["tiles"])', 'board_size = 10', 1))
        with self.assertRaises(ValueError): repair_source(repair_source(self.source))
        with self.assertRaises(ValueError): repair_source(self.source+'\ndef _decay_plants(farm, step):\n    pass\n')
        with self.assertRaises(TypeError): repair_source(self.source.encode())

    def test_10_no_cache_or_added_callable(self):
        result = repair_source(self.source)
        before = ast.parse(self.source)
        after = ast.parse(result)
        self.assertEqual([getattr(n, 'name', None) for n in before.body],
                         [getattr(n, 'name', None) for n in after.body])
        self.assertNotIn('lru_cache', result)
        # Every output access still uses the original bounded x prefix.
        for _, _, text in function_spans(result).values():
            self.assertEqual(text.count('for x in columns:'), 1)
            self.assertIn('row = tiles[y]', text)


class MutationWitnessTests(unittest.TestCase):
    """Small, independent counterexamples; negative-control failures stay readable."""
    @classmethod
    def setUpClass(cls):
        LifecycleTests.setUpClass.__func__(cls)
    compare = LifecycleTests.compare

    def test_decay_parity(self):
        tile = self.base._new_plant('WHEAT', 0, 24)
        tile.update(max_lifespan_step=0, yield_units=2)
        self.compare({'tiles': [[tile]]}, NAMES[0], (0,))

    def test_water_threshold(self):
        self.compare({'tiles': [[self.base._new_plant('WHEAT', 0, 24)]]}, NAMES[1], (0, 24))

    def test_fertilizer_water(self):
        tile = self.base._new_plant('TOMATO', 0, 24)
        tile.update(consecutive_unwatered=0, watered_today=False, fertilized_until_day=7)
        self.compare({'tiles': [[tile]]}, NAMES[1], (7, 24))

    def test_animal_escape(self):
        tile = self.base._new_animal('COW', 0)
        tile['consecutive_unfed'] = 1
        self.compare({'tiles': [[tile]]}, NAMES[2], (0,))

    def test_care_carry(self):
        tile = self.base._new_animal('COW', 0)
        tile.update(fed_today=True, pending_care_bonus=2)
        self.compare({'tiles': [[tile]]}, NAMES[2], (7,))

    def test_visit_tail(self):
        tile = self.base._new_plant('WHEAT', 0, 24)
        tile.update(max_lifespan_step=0, yield_units=2)
        self.compare({'tiles': [[None, None, tile], [None, None, tile]]}, NAMES[0], (0,))

    def test_copy_rows(self):
        tile = self.base._new_plant('WHEAT', 0, 24)
        tile.update(max_lifespan_step=0, yield_units=1)
        self.compare({'tiles': [[tile]], 'alias': tile}, NAMES[0], (0,))


if __name__ == '__main__':
    unittest.main(verbosity=2)
