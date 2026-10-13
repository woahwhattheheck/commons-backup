"""Independent arithmetic checks; never substitutes finite samples for proof."""
import unittest
from fractions import Fraction
import primitive_obstruction as p

class PrimitiveObstructionTests(unittest.TestCase):
    def test_certificate(self):
        self.assertEqual(p.verify_certificate()["status"], "VERIFIED_FINITE_CERTIFICATE_FOR_INFINITE_PROOF")

    def test_mod8_categories(self):
        possible=set()
        for x in range(8):
            for y in range(8):
                for a,first in enumerate((1,4,0)):
                    for b,second in enumerate((1,4,0)):
                        if (x*x+y*y+first+second)%8==7:
                            possible.add((a,b))
        self.assertEqual(possible,{(0,0),(0,1),(1,0)})

    def test_mod9_no_residuals(self):
        for x in range(9):
            for y in range(9):
                self.assertNotIn((x*x+y*y)%9,(3,6))

    def test_lemma_exhaustive_small_range(self):
        for n in range(7,20001,72):
            left=p.specialized_witness(n) is not None
            right=p.two_square_witness(n-2) is not None or p.two_square_witness(n-5) is not None
            self.assertEqual(left,right)

    def test_explicit_first_member(self):
        self.assertTrue(p.is_certified_counterexample(2095))
        self.assertIsNone(p.specialized_witness(2095))

    def test_non_counterexample_in_lemma_class(self):
        self.assertIsNotNone(p.specialized_witness(7))
        self.assertFalse(p.is_certified_counterexample(7))

    def test_all_crt_classes_independent_scan(self):
        expected=tuple(n for n in range(7,426888,72)
                       if n%7==2 and n%49!=2 and n%11==5 and n%121!=5)
        self.assertEqual(p.certified_residues(),expected)
        self.assertEqual(len(expected),60)

    def test_all_classes_bad_square_residues(self):
        for r in p.certified_residues():
            for q,shift in ((7,2),(11,5)):
                forbidden=(r-shift)%(q*q)
                for x in range(q*q):
                    for y in range(q*q):
                        self.assertNotEqual((x*x+y*y)%(q*q),forbidden)

    def test_density(self):
        self.assertEqual(Fraction(60,426888),Fraction(5,35574))

    def test_huge_parameter(self):
        for t in (0,1,2,10**20,10**1000):
            n=2095+426888*t
            self.assertTrue(p.is_certified_counterexample(n))
            self.assertEqual(n%4,3)
            self.assertEqual((n-2)%49,35)
            self.assertEqual((n-5)%121,33)

    def test_exact_valuation_and_no_shift(self):
        for t in range(100):
            n=2095+426888*t
            self.assertEqual((n-2)%7,0)
            self.assertNotEqual((n-2)%49,0)
            self.assertEqual((n-5)%11,0)
            self.assertNotEqual((n-5)%121,0)
            self.assertFalse(p.is_certified_counterexample(n+1))

    def test_original_conjecture_witness(self):
        x,y,a,b,c,d=25,38,0,0,0,1
        self.assertEqual(x*x+y*y+(2**a*3**b)**2+(2**c*5**d)**2,2095)

    def test_two_square_oracle_exhaustive(self):
        possible={x*x+y*y for x in range(33) for y in range(33)}
        for n in range(1001):
            self.assertEqual(p.two_square_witness(n) is not None,n in possible)

    def test_two_square_oracle_edges(self):
        self.assertIsNone(p.two_square_witness(-1))
        self.assertEqual(p.two_square_witness(0),(0,0))
        self.assertEqual(p.two_square_witness(1),(0,1))

    def test_oracle_witness_substitution(self):
        for n in range(2,500):
            w=p.specialized_witness(n)
            if w is not None:
                x,y,a,b,d=w
                self.assertEqual(x*x+y*y+4**a+4**b*9**d,n)

    def test_invalid_inputs(self):
        for bad in (-1,True,1.0,"1",None):
            with self.assertRaises(ValueError):
                p.is_certified_counterexample(bad)
            with self.assertRaises(ValueError):
                p.specialized_witness(bad)
        for bad in (0,-1,True,1.5):
            with self.assertRaises(ValueError):
                p.two_square_residues(bad)

    def test_crt_requires_coprime_moduli(self):
        with self.assertRaises(ValueError):
            p.crt(((1,6),(2,9)))

    def test_crt_equations(self):
        self.assertEqual(p.crt(((7,72),(37,49),(38,121))),(2095,426888))

    def test_required_checks_survive_optimization(self):
        with self.assertRaisesRegex(ValueError,"deliberate"):
            p.require(False,"deliberate")

    def test_truth_ceiling(self):
        receipt=p.verify_certificate()
        for field in ("original_conjecture_refuted","original_conjecture_proved","sponsor_contacted","prize_claimed","payment_claimed"):
            self.assertIs(receipt[field],False)

if __name__=="__main__":
    unittest.main()
