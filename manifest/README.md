Face baseline (acceptance data for later changes to `svf/`):

- baseline.tsv: the sha256 and size of every `.SVF` face under `svf/` (licence notes, `*.TSV` and `*.md` excluded), one
  row a face, 116 rows. 115 rows are those of the 2026-10-21 SVFN v3 baseline of the original working repository
  (written there by `facecheck.py manifest` after the v3 conversion) for the faces this repository publishes; those faces
  have not changed since. The 116th, `svf/dos/NEODG16G.SVF`, was added on 2026-11-03 (made by
  `tools/build/build_faces.py`).

Check the working tree against it (run in the repository root):

    python3 -I tools/facecheck.py verify manifest/baseline.tsv

Exit 0 when every face exists with the same sha256; MISSING / CHANGED lines otherwise. The same table from a commit:

    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf \
        --exclude '*.TXT' --exclude '*.txt' --exclude '*.TSV' --exclude '*.md' -o /tmp/check.tsv
    cmp /tmp/check.tsv manifest/baseline.tsv
