/* clip.js - the clipping panel's cut-row math (pure, no DOM): the same rule as mkfont's fit_counts, applied to the
 * boxes of a probe report for any ascent, so the list, the counts and the overlay agree with what a build with
 * --clip-cell --ascent will cut. A box is [left, top, right, bottom], rows relative to the baseline (top is negative
 * above it, bottom one past the last ink row). */

/** The rows of @p box that fall above and below a cell of height @p cellH whose baseline is row @p ascent. */
export function cutRows(box, ascent, cellH) {
  return {top: Math.max(0, -box[1] - ascent), bottom: Math.max(0, box[3] + ascent - cellH)};
}

/** The report's glyphs cut by (ascent, cellH): {rows: [{cp, top, bottom}] sorted by rows cut, then code point,
 *  top: glyphs cut at the top, bottom: glyphs cut at the bottom, wide: glyphs wider than @p cellW, cut: glyphs
 *  cut either way}. */
export function cutList(report, ascent, cellH, cellW) {
  const rows = [];
  let top = 0, bottom = 0, wide = 0;
  for (const [key, box] of Object.entries(report.boxes || {})) {
    const cp = parseInt(key, 16);
    const cut = cutRows(box, ascent, cellH);
    if (cut.top > 0) top++;
    if (cut.bottom > 0) bottom++;
    if (box[2] - box[0] > cellW) wide++;
    if (cut.top > 0 || cut.bottom > 0) rows.push({cp, top: cut.top, bottom: cut.bottom});
  }
  rows.sort((a, b) => (b.top + b.bottom) - (a.top + a.bottom) || a.cp - b.cp);
  return {rows, top, bottom, wide, cut: rows.length};
}
