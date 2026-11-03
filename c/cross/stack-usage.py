"""stack-usage.py CI_DIR [ROOT...] - worst-case stack depth over the call graph of gcc's -fcallgraph-info=su files.

CI_DIR holds the *.ci files of one build (gcc -fstack-usage -fcallgraph-info=su); a node's own frame is the "N bytes
(static)" of its label, the depth of a function is its frame plus the deepest callee (cycles are cut; a function the
graph does not define, e.g. memset or libgcc's division, counts 0: they are leaf routines of a few words; calls through
function pointers are not in the graph: the callback's own frames are the caller's to add). ROOTS default to every
non-static function of the library (names svf_*); a ROOT named on the command line that no .ci defines is an error
(message on stderr, exit 1, no peak line). Prints "frame depth name  path" lines, deepest first, then 'peak'.
Usage: python3 -I c/cross/stack-usage.py DIR [svf_draw_utf8 ...]
"""
import glob
import os
import re
import sys

node = re.compile(r'node: \{ title: "([^"]+)" label: "([^"]*)"')
edge = re.compile(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)"')


def short(t):
    return t.rsplit(":", 1)[-1]


def main(argv):
    frame, calls, defined = {}, {}, set()
    for p in glob.glob(os.path.join(argv[1], "*.ci")):
        for line in open(p):
            m = node.match(line)
            if m:
                s = re.search(r"(\d+) bytes \((static|dynamic[^)]*)\)", m.group(2).replace("\\n", " "))
                if s:
                    frame[m.group(1)] = int(s.group(1))
                    defined.add(m.group(1))
                continue
            m = edge.match(line)
            if m:
                calls.setdefault(m.group(1), set()).add(m.group(2))
    memo = {}

    def depth(n, stack=()):
        if n in memo:
            return memo[n]
        if n in stack:
            return (0, [])
        best = (0, [])
        for c in calls.get(n, ()):
            if c in defined:
                d = depth(c, stack + (n,))
                if d[0] > best[0] or not best[1]:
                    best = d
        r = (frame.get(n, 0) + best[0], [n] + best[1])
        memo[n] = r
        return r

    roots = argv[2:] or sorted(n for n in defined if not n.startswith("/") and short(n).startswith("svf_") and not short(n).startswith("svf__"))
    rows, missing = [], []
    for r in roots:
        names = [n for n in defined if short(n) == r or n == r]
        if not names and argv[2:]:
            missing.append(r)
        for n in names:
            d, path = depth(n)
            rows.append((d, frame[n], short(n), " > ".join("%s(%d)" % (short(x).split(".")[0], frame.get(x, 0)) for x in path)))
    rows.sort(reverse=True)
    for d, f, n, path in rows:
        print("%5d %5d %s  %s" % (f, d, n, path))
    if missing:
        sys.stderr.write("stack-usage.py: root not found in %s: %s\n" % (argv[1], " ".join(missing)))
        return 1
    print("peak %d" % (rows[0][0] if rows else 0))
    return 0


sys.exit(main(sys.argv))
