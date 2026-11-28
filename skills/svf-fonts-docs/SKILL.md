---
name: svf-fonts-docs
description: Use when writing or maintaining a document, figure or README entry in this repository.
---

# Writing docs in this repository

Habits and checks for `docs/`, `spec/`, `README.md` and the figures they use. The repository is public: everything you
write is read by people who do not have the machine or the private sources.

## When to use

- Adding or editing a document, a recipe, the specification or a README.
- Adding, regenerating or re-checking a figure or a sample image.
- Changing a tool or a recipe whose documents must follow in the same change.

## Language pairs

- Every document is a pair: `X.md` and `X.ko.md`. Each opens with a one-line language switch: the English file shows
  `English` in bold and links its `.ko.md` sibling as `한국어`; the Korean file links its `.md` sibling as `English` and
  shows `한국어` in bold.
- Keep the pair in step: same sections, same numbers, same tables. A change to one is a change to the other in the same
  commit; a pair that has drifted is a defect.
- Anchors belong to each file. Heading slugs differ between the languages, and some files carry explicit
  `<a id="...">` anchors; a link points at the anchor of the file it names, so check it in that file.

## Style

- Plain and compact: short sentences, one idea each; a table for any comparison of three or more; no filler opening,
  no restating the heading, no closing summary.
- Numbers are measured: name the input and the settings, and re-run rather than adjust by hand. Say "about" only where
  the run itself varies.
- Commands run from the repository root, in a fenced or indented block, with uppercase placeholders for the reader's own
  paths. Brackets mark optional arguments; say so when they could be typed.
- A fact lives in one document; the others link to it. Do not copy a command or a table between documents.
- No private material: no local absolute paths, host names, machine names, agent ids or card ids.

## Figures and samples

- Figures come from `tools/doc_figures_*.py`, which render deterministically. Each takes `--check`, which re-renders in
  memory and compares byte for byte with the committed files (exit 1 on a difference or a missing file). Run `--check`
  after touching the script or the document it draws for, and regenerate with `--out` instead of editing a PNG.
- Only the sample images listed in [`NOTICE.md`](../../NOTICE.md) (`docs/images/recipes/`) may show a proprietary
  bitmap; every other figure must come from the OFL faces the scripts pin, and the scripts refuse other paths. Keep
  that refusal in place.
- New images go under `docs/images/<document>/`, and the document says which script draws them.

## Checks

Run from the repository root:

```sh
python3 -B -m unittest tools.test_skills tools.test_tools_doc tools.test_recipes
```

- `tools/test_tools_doc.py`: the tool-path section headings of `docs/tools.md` and the population of tool files must be
  the same set; a new tool needs its section, and an old heading with no file fails as stale. Test files are outside
  the population, so they are described in prose, not as a section heading.
- `tools/test_recipes.py`: the recipe commands run end to end on synthetic and OFL inputs.
- `tools/test_skills.py`: the skills' frontmatter, the tool paths and jamo-tool options they name, and their links and
  anchors.
- Links and anchors: the repository has no in-tree slug checker. Verify a new or moved anchor by opening the target
  file and confirming the heading or `<a id="...">` it names, and run the host's slug checker over the changed files
  when one is available.
- A tool change that alters output updates its document's numbers in the same commit; a recipe row names the command
  that produced its result.

## Where a fact goes

- A tool's purpose, inputs and options: `docs/tools.md` and `docs/tools.ko.md`.
- A conversion procedure: the recipe document for that source, plus a row in
  [`docs/recipes.md`](../../docs/recipes.md#recipe-documents) when the source is a new kind.
- A file-format or reader rule: `spec/SVF.md` and `spec/SVF.ko.md`.
- A new document: add it to the README document index in both languages, and link it from the pages that need it.
