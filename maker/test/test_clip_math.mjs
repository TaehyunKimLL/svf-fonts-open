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

test('cutRows per glyph is the max(0, ...) of the box', () => {
  for (const c of cases.cases) {
    for (const [key, box] of Object.entries(cases.report.boxes)) {
      const got = cutRows(box, c.ascent, c.cellH);
      assert.deepEqual(got, { top: Math.max(0, -box[1] - c.ascent), bottom: Math.max(0, box[3] + c.ascent - c.cellH) }, key);
    }
  }
});

test('the list is sorted by rows cut then code point', () => {
  const got = cutList({ boxes: { '0x42': [0, -12, 5, 3], '0x41': [0, -12, 5, 3], '0x43': [0, -2, 5, 0] } }, 4, 8, 16);
  assert.deepEqual(got.rows.map((r) => r.cp), [0x41, 0x42]);
});
