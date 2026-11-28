#!/usr/bin/env python3
"""Checks for the agent skills in skills/: one folder per skill, whose SKILL.md carries valid frontmatter, names only
tool files that exist, uses only options the tool's argparse defines, links only to documents and anchors that exist,
and carries no local absolute path.

  python3 -B -m unittest tools.test_skills

A skill is `skills/<name>/SKILL.md`. The frontmatter is the first block: `---`, `name: <name>`, a one-line
`description: Use when ...`, `---`. Tool paths are `tools/`, `maker/` or `web/` Markdown-free paths ending in `.py`;
on a line that names `tools/jamohybrid.py` or `tools/jamoset.py`, every `--option` must be one that file's
`add_argument` calls define (a `BooleanOptionalAction` also defines `--no-<name>`).

Anchors resolve by GitHub's rules: an explicit `<a id="...">` or `<a name="...">`, or the slug of a heading (lowercase,
punctuation removed, spaces to hyphens, a repeated slug numbered -1, -2, ...). Fenced code blocks hold no headings and
no links. An absolute link (a leading `/`), a missing file or a missing anchor fails the test.

The basics skill quotes the JSET limits and the syllable count, so this test also reads `JSET_LIMITS` and `_JMAP_NSYL`
from `tools/jamoset.py` (as literals, without importing it) and requires the skill to state those numbers.
"""
import ast
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILLS = os.path.join(ROOT, "skills")

FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EXPLICIT = re.compile(r"<a\s+(?:id|name)=\"([^\"]+)\"")
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
TOOL = re.compile(r"(?<![\w./-])((?:tools|maker|web)/[\w./-]+\.py)\b")
OPTION = re.compile(r"(?<![\w-])(--[a-z0-9][a-z0-9-]*)")
ABSOLUTE = re.compile(r"(?<![\w:/.-])/[A-Za-z0-9._-]|[A-Za-z]:\\")
ARGUMENT = re.compile(r"add_argument\(")
STRING = re.compile(r"[\"'](--[A-Za-z0-9_-]+)[\"']")


def skill_dirs():
    return sorted(glob.glob(os.path.join(SKILLS, "*", "SKILL.md")))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def lines_outside_fences(text):
    """(line number, line) for every line not inside a fenced code block."""
    out, fence = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fence = not fence
            continue
        if not fence:
            out.append((n, line))
    return out


def github_slug(heading):
    """GitHub's heading slug: inline markup removed, lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def anchors(path):
    """Every link target a Markdown file offers: explicit ids and heading slugs."""
    seen, out = {}, set()
    for _, line in lines_outside_fences(read(path)):
        for m in EXPLICIT.finditer(line):
            out.add(m.group(1))
    for _, line in lines_outside_fences(read(path)):
        m = HEADING.match(line)
        if not m:
            continue
        slug = github_slug(m.group(2))
        if not slug:
            continue
        if slug in seen:
            seen[slug] += 1
            out.add("%s-%d" % (slug, seen[slug]))
        else:
            seen[slug] = 0
            out.add(slug)
    return out


def tool_options(rel):
    """The `--options` a tool's argparse defines."""
    src = read(os.path.join(ROOT, rel))
    out = set()
    for m in ARGUMENT.finditer(src):
        depth, i = 1, m.end()
        while i < len(src) and depth:
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        call = src[m.end():i]
        names = STRING.findall(call)
        out.update(names)
        if "BooleanOptionalAction" in call:
            out.update("--no-" + n[2:] for n in names)
    return out


def frontmatter(text):
    """The frontmatter as a dict, or None when the file does not start with a `---` block."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 3)
    if end < 0:
        return None
    out = {}
    for line in text[4:end + 1].splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            return None
        out[key.strip()] = value.strip()
    return out


def module_constant(name, rel="tools/jamoset.py"):
    """A module-level literal of a tool, read without importing it (no side effects, no dependencies)."""
    tree = ast.parse(read(os.path.join(ROOT, rel)))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError("no %s in %s" % (name, rel))


class Skills(unittest.TestCase):
    def test_skills_exist(self):
        self.assertTrue(skill_dirs(), "no skills/*/SKILL.md")

    def test_frontmatter(self):
        problems = []
        for path in skill_dirs():
            folder = os.path.basename(os.path.dirname(path))
            fm = frontmatter(read(path))
            if fm is None:
                problems.append("%s: no frontmatter block" % path)
                continue
            if fm.get("name") != folder:
                problems.append("%s: name %r does not match the folder %r" % (path, fm.get("name"), folder))
            desc = fm.get("description", "")
            if not desc.startswith("Use when "):
                problems.append("%s: description does not start with 'Use when '" % path)
            if "\n" in desc:
                problems.append("%s: description is not one line" % path)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_tool_paths_exist(self):
        problems = []
        for path in skill_dirs():
            for n, line in enumerate(read(path).splitlines(), 1):
                for rel in TOOL.findall(line):
                    if not os.path.isfile(os.path.join(ROOT, rel)):
                        problems.append("%s:%d: no such tool %s" % (path, n, rel))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_jamo_tool_options_exist(self):
        problems, cache = [], {}
        for path in skill_dirs():
            for n, line in enumerate(read(path).splitlines(), 1):
                tools = [rel for rel in ("tools/jamohybrid.py", "tools/jamoset.py") if rel in line]
                if not tools:
                    continue
                allowed = set()
                for rel in tools:
                    if rel not in cache:
                        cache[rel] = tool_options(rel)
                    allowed |= cache[rel]
                for opt in OPTION.findall(line):
                    if opt not in allowed:
                        problems.append("%s:%d: %s has no option %s" % (path, n, " or ".join(tools), opt))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_links_resolve(self):
        problems = []
        for path in skill_dirs():
            base = os.path.dirname(path)
            for n, line in lines_outside_fences(read(path)):
                line = re.sub(r"`[^`]*`", "", line)  # a link written inside inline code is not a link
                for target in LINK.findall(line):
                    if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#!"):
                        continue  # an external URL
                    if target.startswith("/"):
                        problems.append("%s:%d: absolute link %s" % (path, n, target))
                        continue
                    file_part, _, fragment = target.partition("#")
                    dest = path if not file_part else os.path.normpath(os.path.join(base, file_part))
                    if not os.path.isfile(dest):
                        problems.append("%s:%d: no such file %s" % (path, n, target))
                        continue
                    if fragment and not dest.endswith(".md"):
                        problems.append("%s:%d: anchor on a non-Markdown file %s" % (path, n, target))
                    elif fragment and fragment not in anchors(dest):
                        problems.append("%s:%d: no anchor #%s in %s" % (path, n, fragment, dest))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_no_local_absolute_paths(self):
        problems = []
        for path in skill_dirs():
            for n, line in enumerate(read(path).splitlines(), 1):
                if ABSOLUTE.search(line):
                    problems.append("%s:%d: local absolute path" % (path, n))
        self.assertEqual(problems, [], "\n".join(problems))


class Basics(unittest.TestCase):
    """The basics skill states the JSET limits and the syllable count; they must be the tool's constants."""

    PATH = os.path.join(SKILLS, "svf-fonts-hangul-basics", "SKILL.md")

    def setUp(self):
        if not os.path.isfile(self.PATH):
            self.skipTest("no svf-fonts-hangul-basics skill")

    def row(self, text, needle):
        """The one line of the skill that states @p needle (the row that carries the concept)."""
        hits = [line for line in text.splitlines() if needle in line]
        self.assertEqual(len(hits), 1, "the basics skill has %d lines with %r" % (len(hits), needle))
        return hits[0]

    def test_jset_limits_are_the_tool_s(self):
        limits = module_constant("JSET_LIMITS")
        text = read(self.PATH)
        std_row, big_row = self.row(text, "| Standard limits |"), self.row(text, "| BIG |")
        for row, row_limits in ((std_row, limits["std"]), (big_row, limits["big"])):
            for want in ("%d x %d" % row_limits[:2], " / ".join(map(str, row_limits[2:]))):
                self.assertIn(want, row, "the row does not state %r: %s" % (want, row))

    def test_syllable_count_is_the_tool_s(self):
        row = self.row(read(self.PATH), "| Syllables | 19 x 21 x 28")
        self.assertIn("{:,}".format(module_constant("_JMAP_NSYL")), row)


if __name__ == "__main__":
    unittest.main()
