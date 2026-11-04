#!/usr/bin/env python3
"""recog_score.py - scores the pieces of a jamo-set face with an optional recogniser (the identity check).

  python3 -P maker/recog_score.py FACE.SVF -o OUT.json [--threads N] [--batch 256] [--arrays numpy|lists]

Every syllable of the face is composed (the engine's own composition) and read by the recogniser's three heads
(initial, medial, final). A piece is the (slot, piece number) of the face's JSET; it passes when the syllables
composed with it are read as the right jamo on that slot's head often enough (THRESHOLDS). The recogniser is not part
of the repository: $SVF_RECOG_DIR names a folder holding recog.py (and its weights) with

    load(model) -> net, split(syllable indices) -> (L, V, T), _heads(net, bool[n, h, w]) -> three log-probability rows

(the calls tools/jamomerge.py's Scorer makes). Exit 0 after writing OUT; 2 when SVF_RECOG_DIR is not a directory with
recog.py or the face cannot be read; 1 with "recog: <exception>" on stderr when the recogniser raises.
A face whose JSET is a LIST/JMAP is "not applicable (LIST)" (exit 0): its pieces are not per-jamo.
"""

import argparse
import importlib.util
import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(os.path.dirname(HERE), "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detect  # noqa: E402
import jamoset  # noqa: E402
import mkfont  # noqa: E402

THRESHOLDS = {"pass": 0.95, "warn": 0.80}
MODEL = "11-12"
NSYL = 11172
SLOTS = ("i", "m", "f")
SLOT_SIZE = (19, 21, 27)            # jamo a slot's table row names (the final has no "none")
WORST = 5


def lists_array(cells, h, w, bpp):
    """The cells (bytes, rows padded to a byte) as nested bool lists [n][h][w]; a 2 bpp pixel is on from level 2."""
    out = []
    for cell in cells:
        pitch = (w * bpp + 7) // 8
        rows = []
        for y in range(h):
            row = cell[y * pitch:(y + 1) * pitch]
            if bpp == 1:
                rows.append([bool(row[x >> 3] >> (7 - (x & 7)) & 1) for x in range(w)])
            elif bpp == 2:
                rows.append([(row[x >> 2] >> (6 - 2 * (x & 3)) & 3) >= 2 for x in range(w)])
            else:
                rows.append([row[x] >= 128 for x in range(w)])
        out.append(rows)
    return out


def numpy_array(cells, h, w, bpp):
    """The same as a numpy bool[n, h, w] (numpy is imported here, nowhere else)."""
    import numpy as np
    return np.array(lists_array(cells, h, w, bpp), dtype=bool).reshape(len(cells), h, w)


def _rows(x):
    return x.tolist() if hasattr(x, "tolist") else [list(r) for r in x]


def _argmax(row):
    best = 0
    for i, v in enumerate(row):
        if v > row[best]:
            best = i
    return best


def _letter(slot, idx):
    """The compatibility letter of jamo idx of slot 0 (initial), 1 (medial) or 2 (final; 0 = none)."""
    if slot == 2 and idx == 0:
        return ""
    base = (0x1100, 0x1161, 0x11A8 - 1)[slot]
    return unicodedata.normalize("NFKC", chr(base + idx))


def _flag(read):
    return "pass" if read >= THRESHOLDS["pass"] else "warn" if read >= THRESHOLDS["warn"] else "fail"


def _table_entries(t):
    """(slot, piece) -> (set, jamo index) for every piece the tables name, first entry wins."""
    out = {}
    for slot, (pieces, n) in enumerate(((t.init_piece, 19), (t.med_piece, 21), (t.fin_piece, 27))):
        for i, p in enumerate(pieces):
            if p != jamoset.BLANK:
                out.setdefault((SLOTS[slot], p), (i // n, i % n + (1 if slot == 2 else 0)))
    return out


def score_face(face_bytes, R, net, to_array, batch=256, index_array=list):
    """The identity JSON of the face (see the module doc). Cells go to R._heads(net, to_array(cells, h, w)) in ascending
    syllable index, @p batch at a time; @p to_array builds the recogniser's input (lists_array / numpy_array with the
    face's bpp bound); R.split gets index_array(syllable indices) (a list, or numpy.array in production)."""
    face = jamoset.parse_svfn(face_bytes)
    t = detect.usable_jset(face)
    if t is None:
        raise ValueError("the face has no usable jamo set")
    if not isinstance(t, jamoset.Tables):
        return {"available": True, "applicable": False, "reason": "not applicable (LIST)"}
    cells = {}
    for s in range(NSYL):
        cell = jamoset.compose(face, t, 0xAC00 + s)
        if cell is not None:
            cells[s] = cell
    syls = sorted(cells)
    h, w = face.cell_h, face.cell_w
    LVT = [_rows(x) if hasattr(x, "tolist") else list(x) for x in R.split(index_array(syls))]
    right_of = {s: (LVT[0][i], LVT[1][i], LVT[2][i]) for i, s in enumerate(syls)}
    read_ok = {}      # syllable -> (ok L, ok V, ok T)
    nll = {}          # syllable -> -log p of the right jamo per head
    got = {}          # syllable -> argmax per head
    for b in range(0, len(syls), batch):
        chunk = syls[b:b + batch]
        heads = [_rows(x) for x in R._heads(net, to_array([cells[s] for s in chunk], h, w))]
        for i, s in enumerate(chunk):
            g = tuple(_argmax(heads[k][i]) for k in range(3))
            r = right_of[s]
            got[s] = g
            read_ok[s] = tuple(g[k] == r[k] for k in range(3))
            nll[s] = tuple(-float(heads[k][i][r[k]]) for k in range(3))
    users = {}
    for s in syls:
        ps = jamoset.pieces_of(t, 0xAC00 + s)
        if ps is None:
            continue
        L, V, T = right_of[s]
        for k, p in enumerate(ps):
            if p == jamoset.BLANK:
                continue
            cell = (t.lead_class[L] * 21 + V) * t.tc + t.tail_class[T]
            users.setdefault((SLOTS[k], p), []).append((s, cell))
    entries = _table_entries(t)
    pieces = []
    for (slot, p), us in users.items():
        k = SLOTS.index(slot)
        ok = sum(1 for s, _ in us if read_ok[s][k])
        read = ok / len(us)
        first_s, first_cell = us[0]
        sets = (t.init_set, t.med_set, t.fin_set)[k]
        worst = sorted(us, key=lambda u: -nll[u[0]][k])[:WORST]
        pieces.append({"piece": p, "slot": slot, "jamo": _letter(k, right_of[first_s][k]),
                       "set": sets[first_cell], "users": len(us), "read": read,
                       "nll": sum(nll[s][k] for s, _ in us) / len(us), "flag": _flag(read),
                       "worst": [{"cp": 0xAC00 + s, "got": _letter(k, got[s][k])} for s, _ in worst]})
    for (slot, p), (setno, j) in entries.items():
        if (slot, p) not in users:
            pieces.append({"piece": p, "slot": slot, "jamo": _letter(SLOTS.index(slot), j), "set": setno,
                           "users": 0, "read": 0.0, "nll": 0.0, "flag": "unused", "worst": []})
    order = {"fail": 0, "warn": 1, "pass": 2, "unused": 3}
    pieces.sort(key=lambda p: (order[p["flag"]], p["read"], SLOTS.index(p["slot"]), p["piece"]))
    ks = [cp - 0xAC00 for cp in mkfont.NAMED_RANGES["ksx1001-hangul"]()]
    counts = {k: sum(1 for p in pieces if p["flag"] == k) for k in order}
    worst_flag = next((f for f in ("fail", "warn") if counts[f]), "pass")
    bpp = face.bpp
    return {"available": True, "applicable": True, "model": MODEL, "thresholds": dict(THRESHOLDS),
            "bpp_note": "2 bpp thresholded at level 2" if bpp == 2 else None,
            "face": {"recog_ks": sum(1 for s in ks if s in read_ok and all(read_ok[s])) / len(ks),
                     "recog_all": sum(1 for s in syls if all(read_ok[s])) / NSYL,
                     "pieces": counts, "identity": worst_flag},
            "pieces": pieces}


def main(argv=None):
    ap = argparse.ArgumentParser(description="score the pieces of a jamo-set face with a recogniser")
    ap.add_argument("face")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--arrays", choices=("numpy", "lists"), default="numpy")
    args = ap.parse_args(argv)
    d = os.environ.get("SVF_RECOG_DIR", "")
    if not (d and os.path.isdir(d) and os.path.isfile(os.path.join(d, "recog.py"))):
        print("SVF_RECOG_DIR is not a directory with recog.py", file=sys.stderr)
        return 2
    try:
        with open(args.face, "rb") as f:
            data = f.read()
        face = jamoset.parse_svfn(data)
    except (OSError, ValueError) as e:
        print("recog_score: %s: %s" % (args.face, e), file=sys.stderr)
        return 2
    t = detect.usable_jset(face)
    if t is None:
        print("recog_score: %s has no usable jamo set" % args.face, file=sys.stderr)
        return 2
    if not isinstance(t, jamoset.Tables):
        out = {"available": True, "applicable": False, "reason": "not applicable (LIST)"}
    else:
        try:
            if args.threads and importlib.util.find_spec("torch"):
                import torch
                torch.set_num_threads(args.threads)
            sys.path.insert(0, d)
            import recog as R
            net = R.load(MODEL)
            build = numpy_array if args.arrays == "numpy" else lists_array
            index_array = list
            if args.arrays == "numpy":
                import numpy as np
                index_array = np.array
            to_array = lambda cells, h, w: build(cells, h, w, face.bpp)  # noqa: E731
            out = score_face(data, R, net, to_array, args.batch, index_array)
        except Exception as e:  # noqa: BLE001 - whatever the recogniser raises is the report
            print("recog: %s" % e, file=sys.stderr)
            return 1
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
