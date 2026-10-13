"""Non-vacuous focused suite runner, including real optimized child CLIs."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent

def main() -> int:
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern="test_batch*.py")
    count = suite.countTestCases()
    print(f"python={sys.version.split()[0]} optimize={sys.flags.optimize} discovered={count}", flush=True)
    if count < 108:
        print("ERROR: focused discovery is incomplete", file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print("ERROR: focused suite has skipped tests", file=sys.stderr)
        return 2
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
