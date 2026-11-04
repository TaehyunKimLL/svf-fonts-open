// node --test maker/test/test_clip_math.mjs with CLIP_CASES=<json file> (written by test_clip_math.py): the page's
// cut-row math equals mkfont.fit_counts for every case.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cutList, cutRows } from '../static/clip.js';

const cases = JSON.parse(readFileSync(process.env.CLIP_CASES, 'utf8'));

test('cutList counts equal fit_counts', () => {
  assert.ok(cases.cases.length > 0);
  for (const c of cases.cases) {
    const got = cutList(cases.report, c.ascent, c.cellH, c.cellW);
    assert.equal(got.top, c.top, JSON.stringify(c));
    assert.equal(got.bottom, c.bottom, JSON.stringify(c));
    assert.equal(got.wide, c.wide, JSON.stringify(c));
    assert.equal(got.cut, c.cut, JSON.stringify(c));
    assert.equal(got.rows.length, c.cut);
  }
});

test('cutRows gives known integers for known boxes', () => {
  // box rows -12..3 (15 rows): cell 12, baseline row 10 -> 2 rows above, 1 below
  assert.deepEqual(cutRows([0, -12, 5, 3], 10, 12), { top: 2, bottom: 1 });
  assert.deepEqual(cutRows([0, -12, 5, 3], 12, 15), { top: 0, bottom: 0 });
  assert.deepEqual(cutRows([0, -12, 5, 3], 14, 15), { top: 0, bottom: 2 });
  assert.deepEqual(cutRows([0, -12, 5, 3], 6, 15), { top: 6, bottom: 0 });
  assert.deepEqual(cutRows([1, 0, 4, 2], 8, 8), { top: 0, bottom: 2 });
});

test('the list is sorted by rows cut then code point', () => {
  // at ascent 4, cell 8: 0x41 and 0x42 cut 8 + 0 rows... (top 8, bottom 0), 0x44 cuts 2 + 0, 0x43 cuts 0, 0x45 cuts 3 + 1
  const got = cutList({ boxes: { '0x42': [0, -12, 5, 3], '0x41': [0, -12, 5, 3], '0x43': [0, -2, 5, 0],
                                 '0x44': [0, -6, 5, 0], '0x45': [0, -7, 5, 5] } }, 4, 8, 16);
  assert.deepEqual(got.rows.map((r) => [r.cp, r.top + r.bottom]), [[0x41, 8], [0x42, 8], [0x45, 4], [0x44, 2]]);
  assert.equal(got.cut, 4);
});
