#!/usr/bin/env python3
"""run-suite.py DIR [PATTERN] - unittest discovery of DIR (default pattern test_*.py) with one summary at the end:
`SUITE <dir> ran=N failures=N errors=N skipped=N`, then every skip reason with its count (`SKIP <n> <reason>`).
Exit 1 on any failure or error. The Windows workflow runs the maker and tools suites through it so the skip count
and reasons are in the log (docs/desktop-app.md, Windows); it works the same on Linux.
"""

import collections
import faulthandler
import os
import sys
import unittest


def main(argv):
    if not argv or len(argv) > 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    start = argv[0]
    pattern = argv[1] if len(argv) > 1 else "test_*.py"
    # a hung test prints every thread's stack every 10 minutes (the job's timeout then names where it hung)
    faulthandler.dump_traceback_later(600, repeat=True, file=sys.stderr)
    suite = unittest.defaultTestLoader.discover(start, pattern=pattern, top_level_dir=start)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    reasons = collections.Counter(reason for _, reason in result.skipped)
    print("SUITE %s ran=%d failures=%d errors=%d skipped=%d" % (os.path.normpath(start).replace(os.sep, "/"), result.testsRun,
                                                              len(result.failures), len(result.errors), len(result.skipped)))
    for reason, count in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])):
        print("SKIP %d %s" % (count, reason))
    for test, _ in result.failures + result.errors:
        print("FAILED %s" % test.id())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
