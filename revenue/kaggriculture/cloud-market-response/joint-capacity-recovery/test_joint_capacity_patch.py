from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path
import unittest

PATCH = Path(__file__).with_name('upstream.patch')


def load_helper():
    lines=[]; capture=False
    for raw in PATCH.read_text().splitlines():
        if raw.startswith('+def tighten_joint_sales'):
            capture=True
        if capture:
            if raw.startswith('+') and not raw.startswith('+++'):
                lines.append(raw[1:])
                continue
            if lines and raw.startswith(' '):
                break
            if lines and raw.startswith('@@'):
                break
    source='\n'.join(lines)+'\n'
    tree=ast.parse(source)
    ns={}
    exec(compile(tree, str(PATCH), 'exec'), ns)
    return ns['tighten_joint_sales'], source


@dataclass(frozen=True)
class I:
    step:int; product:str; lower:int; upper:int; admitted_lower:int; admitted_upper:int; reason:str


def make(*a): return I(*a)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f, cls.source=load_helper()
        cls.f=staticmethod(f)

    def test_capacity_identifies_other_product(self):
        rows=[I(10,'MILK',100,100,100,100,'identified'), I(10,'WOOL',0,100,0,100,'floor_censored')]
        out,diag=self.f(rows,100,make)
        self.assertEqual((out[1].lower,out[1].upper,out[1].reason),(0,0,'identified'))
        self.assertTrue(diag['changes'][0]['quantity_identified'])
        self.assertIsNone(diag['cash_receipts'])

    def test_partial_tightening_remains_uncertain(self):
        rows=[I(10,'MILK',80,100,70,100,'floor_censored'), I(10,'WOOL',0,100,0,100,'floor_censored')]
        out,_=self.f(rows,100,make)
        self.assertEqual((out[1].lower,out[1].upper,out[1].reason),(0,20,'floor_censored'))

    def test_no_change_preserves_object(self):
        row=I(2,'EGG',0,3,0,3,'identified')
        out,diag=self.f([row],100,make)
        self.assertIs(out[0],row); self.assertIsNone(diag)

    def test_operating_products_rejected(self):
        for product in ('WHEAT','FERTILIZER'):
            with self.subTest(product=product), self.assertRaises(ValueError):
                self.f([I(2,product,0,1,0,1,'identified')],100,make)

    def test_duplicate_product_rejected(self):
        with self.assertRaises(ValueError):
            self.f([I(2,'MILK',0,1,0,1,'identified'), I(2,'MILK',0,1,0,1,'identified')],100,make)

    def test_cross_step_rejected(self):
        with self.assertRaises(ValueError):
            self.f([I(2,'MILK',0,1,0,1,'identified'), I(3,'WOOL',0,1,0,1,'identified')],100,make)

    def test_lower_total_over_capacity_rejected(self):
        with self.assertRaisesRegex(ValueError,'lower bounds exceed'):
            self.f([I(2,'MILK',60,60,60,60,'identified'), I(2,'WOOL',50,50,50,50,'identified')],100,make)

    def test_bool_and_nonpositive_capacity_rejected(self):
        for cap in (True,False,0,-1,1.0):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.f([],cap,make)

    def test_invalid_interval_geometry_rejected(self):
        bad=[I(2,'MILK',5,4,0,4,'identified'), I(2,'MILK',2,5,3,5,'identified'), I(2,'MILK',2,5,0,6,'identified')]
        for row in bad:
            with self.subTest(row=row), self.assertRaises(ValueError): self.f([row],100,make)

    def test_empty_is_identity(self):
        self.assertEqual(self.f([],100,make),([],None))

    def test_small_exhaustive_marginals_match_joint_vectors(self):
        for cap in range(1,7):
            for alo in range(cap+1):
              for ahi in range(alo,cap+1):
               for blo in range(cap+1):
                for bhi in range(blo,cap+1):
                 vectors=[(a,b) for a in range(alo,ahi+1) for b in range(blo,bhi+1) if a+b<=cap]
                 rows=[I(4,'MILK',alo,ahi,alo,ahi,'identified'),I(4,'WOOL',blo,bhi,blo,bhi,'identified')]
                 if not vectors:
                    with self.assertRaises(ValueError): self.f(rows,cap,make)
                    continue
                 out,_=self.f(rows,cap,make)
                 self.assertEqual((out[0].lower,out[0].upper),(min(a for a,b in vectors),max(a for a,b in vectors)))
                 self.assertEqual((out[1].lower,out[1].upper),(min(b for a,b in vectors),max(b for a,b in vectors)))

if __name__=='__main__': unittest.main()
