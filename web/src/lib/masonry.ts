export type MasonryBox = { height: number; wide: boolean };
export type MasonryPlacement = { left: number; top: number; width: number };
export type MasonryLayout = {
  nCols: number;
  colW: number;
  placed: MasonryPlacement[];
  height: number;
};

export function columnSpec(width: number, gap = 12, colMin = 190): { nCols: number; colW: number } {
  const nCols = Math.max(1, Math.floor((width + gap) / (colMin + gap)));
  // floored: fractional widths round outward per card and the last column
  // spills past the container, which reads as a horizontal scrollbar
  return { nCols, colW: Math.floor((width - (nCols - 1) * gap) / nCols) };
}

/* Shortest-column masonry. Boxes are placed strictly in input order: each
   1-col box drops into the currently shortest column, each wide box into the
   adjacent column pair whose taller side is lowest. Ties break leftmost, so
   the layout is deterministic and never puts a box above an earlier one in
   its column. */
export function computeMasonryLayout(
  boxes: MasonryBox[],
  opts: { width: number; gap?: number; colMin?: number },
): MasonryLayout {
  const gap = opts.gap ?? 12;
  const { nCols, colW } = columnSpec(opts.width, gap, opts.colMin ?? 190);
  const cols = new Array<number>(nCols).fill(0);
  const placed: MasonryPlacement[] = [];

  for (const box of boxes) {
    if (box.wide && nCols >= 2) {
      let c = 0;
      let top = Math.max(cols[0], cols[1]);
      for (let i = 1; i < nCols - 1; i++) {
        const h = Math.max(cols[i], cols[i + 1]);
        if (h < top) {
          top = h;
          c = i;
        }
      }
      placed.push({ left: c * (colW + gap), top, width: 2 * colW + gap });
      cols[c] = cols[c + 1] = top + box.height + gap;
    } else {
      let c = 0;
      for (let i = 1; i < nCols; i++) if (cols[i] < cols[c]) c = i;
      const top = cols[c];
      placed.push({ left: c * (colW + gap), top, width: colW });
      cols[c] = top + box.height + gap;
    }
  }

  const height = placed.length ? Math.max(...cols) - gap : 0;
  return { nCols, colW, placed, height };
}
