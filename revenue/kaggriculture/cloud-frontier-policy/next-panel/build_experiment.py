"""Rebuild an explicitly named development experiment and official adapter."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
VARIANTS = {
    'feed-rescue': ('frozen', 'feed_rescue.py'),
    'feed-priority': ('frozen', 'feed_priority.py'),
    'harvest-rescue': ('frozen', 'harvest_rescue.py'),
    'animal-harvest': ('frozen', 'animal_harvest.py'),
    'deferred-milk': ('arlene', 'deferred_milk.py'),
    'dairy-continuation': ('arlene', 'dairy_continuation.py'),
    'carrot-demand': ('arlene', 'carrot_demand.py'),
    'carrot-opportunity': ('arlene', 'carrot_opportunity.py'),
    'demand-dairy': ('arlene', 'demand_dairy.py'),
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('variant', choices=VARIANTS)
    p.add_argument('--runtime', type=Path, required=True)
    args = p.parse_args()
    runtime = args.runtime.resolve()
    family, helper = VARIANTS[args.variant]
    base = runtime/'frozen/main.py' if family == 'frozen' else HERE/'vendor/arlene.py'
    expected = ('16d7f213e06c563487e5f613f8c94116a094b36ba46927329cbfc3b4195d461d'
                if family == 'frozen' else
                '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4')
    assert hashlib.sha256(base.read_bytes()).hexdigest() == expected
    target = runtime/(args.variant+'-main.py')
    target.write_bytes(base.read_bytes()+b'\n'+(HERE/helper).read_bytes())
    template = (runtime/(family+'-adapter.py')).read_text()
    adapter = runtime/(args.variant+'-adapter.py')
    assert repr(str(base)) in template
    adapter.write_text(template.replace(repr(str(base)), repr(str(target))))
    print('source', target, hashlib.sha256(target.read_bytes()).hexdigest())
    print('official adapter', adapter)


if __name__ == '__main__':
    main()
