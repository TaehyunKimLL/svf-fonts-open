#!/usr/bin/env python3
"""Census test for docs/tools.md: every tool file has a section, and every section names a tool file.

The file population is the one docs/tools.md documents: every non-test file in tools/*.py, tools/*.sh,
tools/build/*, web/*.py and web/*.sh. __pycache__
is skipped, and so is any file whose name starts with test_.

A section is a heading line `### `<repo-relative path>``, outside a fenced code block. The headings must be exactly
the population: the test fails with "undocumented: <path>" for a file with no heading and "stale: <path>" for a heading
that is not one of the population's paths (a heading naming README.md, a test file, an absolute path or a path with
`..` is stale). It also checks that README.md points at docs/tools.md.
"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "tools.md")
README = os.path.join(ROOT, "README.md")

PATTERNS = (
    "tools/*.py",
    "tools/*.sh",
    "tools/build/*",
    "web/*.py",
    "web/*.sh",
)

HEADING = re.compile(r"^### `([^`]+)`\s*$")
FENCE = re.compile(r"^\s*```")


def tool_files(root=ROOT):
    """Repo-relative paths of the file population docs/tools.md documents, sorted."""
    out = set()
    for pattern in PATTERNS:
        for path in glob.glob(os.path.join(root, pattern)):
            if not os.path.isfile(path):
                continue
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            name = os.path.basename(rel)
            if name.startswith("test_"):
                continue
            if "__pycache__" in rel:
                continue
            out.add(rel)
    return sorted(out)


def documented_paths(doc=DOC):
    """The path of every `### `path`` heading in the document, in order, ignoring fenced code blocks."""
    out = []
    in_fence = False
    with open(doc, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = HEADING.match(line)
            if m:
                out.append(m.group(1))
    return out


class ToolsDocCensus(unittest.TestCase):
    def test_population_is_not_empty(self):
        self.assertTrue(tool_files(), "the tool file population is empty")

    def test_every_file_is_documented(self):
        headings = set(documented_paths())
        missing = [p for p in tool_files() if p not in headings]
        self.assertEqual(missing, [], "\n".join("undocumented: " + p for p in missing))

    def test_every_heading_is_a_file(self):
        population = set(tool_files())
        stale = [p for p in documented_paths() if p not in population]
        self.assertEqual(stale, [], "\n".join("stale: " + p for p in stale))

    def test_no_duplicate_headings(self):
        paths = documented_paths()
        dupes = sorted({p for p in paths if paths.count(p) > 1})
        self.assertEqual(dupes, [], "\n".join("duplicate heading: " + p for p in dupes))

    def test_readme_points_to_the_doc(self):
        with open(README, encoding="utf-8") as fh:
            self.assertIn("docs/tools.md", fh.read(), "README.md does not point at docs/tools.md")


if __name__ == "__main__":
    unittest.main()
