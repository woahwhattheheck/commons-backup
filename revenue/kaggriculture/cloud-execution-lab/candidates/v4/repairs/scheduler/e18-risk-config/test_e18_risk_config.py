# SPDX-License-Identifier: Apache-2.0
import math
import unittest


def finite(value):
    try:
        number=float(value)
    except (TypeError,ValueError,OverflowError):
        return 0.0
    return max(0.0,number) if math.isfinite(number) else 0.0


def weights(names, raw):
    vals=[finite(raw.get(name,0.0)) for name in names] if isinstance(raw,dict) else []
    total=sum(vals)
    if len(vals)!=len(names) or total<=0:
        vals=[1.0 for _ in names]; total=sum(vals)
    elif not math.isfinite(total):
        scale=max(vals); vals=[v/scale for v in vals]; total=sum(vals)
    return [v/total for v in vals]


class E18FiniteConfigTests(unittest.TestCase):
    def test_nonfinite_and_overflow_conversion_fail_closed(self):
        self.assertEqual(finite(float('inf')),0.0)
        self.assertEqual(finite(float('-inf')),0.0)
        self.assertEqual(finite(float('nan')),0.0)
        self.assertEqual(finite(10**10000),0.0)

    def test_all_invalid_falls_back_uniform(self):
        got=weights(['a','b'],{'a':float('inf'),'b':float('nan')})
        self.assertEqual(got,[0.5,0.5])

    def test_finite_sum_overflow_preserves_ratio(self):
        got=weights(['a','b'],{'a':1e308,'b':5e307})
        self.assertTrue(all(math.isfinite(x) for x in got))
        self.assertAlmostEqual(sum(got),1.0)
        self.assertAlmostEqual(got[0]/got[1],2.0)

    def test_ordinary_inputs_keep_expected_normalization(self):
        self.assertEqual(weights(['a','b','c'],{'a':1,'b':2,'c':3}),[1/6,2/6,3/6])

    def test_downside_parser_cannot_be_unbounded(self):
        self.assertEqual(finite(float('inf')),0.0)
        self.assertEqual(finite('12.5'),12.5)


if __name__=='__main__': unittest.main()
