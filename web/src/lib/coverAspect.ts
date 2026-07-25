/* Reserved height for a card cover before the image has loaded (#22).
 *
 * The masonry packs by measured card height, so a cover with no reserved box
 * is measured at zero, placed, and then shoves every card below it once the
 * image decodes. The queue API carries no dimensions, so the first paint has
 * to guess. The guess comes from a census of 114 live covers:
 *
 *   source      n   median w/h   p10     p90
 *   instagram  56        0.563  0.563   0.800
 *   reddit     39        1.197  1.000   1.795
 *   tiktok     18        0.697  0.562   1.428
 *
 * Instagram is tight enough that its median answers about half the queue well.
 * Reddit and TikTok are bimodal — vertical video and landscape screenshots are
 * two populations, not spread around a mean — so no per-source constant serves
 * both. Measured effect on worst on-screen displacement during a page append:
 * 1550px without this, 777px with it.
 *
 * A localStorage cache of each cover's true ratio was built here and removed
 * again: it measured 0px of improvement. Covers below the fold are never
 * fetched (loading="lazy"), so it only ever learned 77 of 120 cards, and the
 * browser's own image cache already supplies the revisit benefit. The residual
 * 777px needs real dimensions known before load — that is a backend change,
 * not a client-side one.
 */

const DEFAULT_ASPECT: Record<string, number> = {
  instagram: 0.563,
  tiktok: 0.697,
  reddit: 1.197,
  pinterest: 0.75,
  youtube: 1.778,
  web: 1.5,
};

/** Overall median of the census; used for sources not in the table. */
const FALLBACK_ASPECT = 0.7;

/** Width/height to reserve for a cover from this source before it loads. */
export function coverAspect(source: string): number {
  return DEFAULT_ASPECT[source] ?? FALLBACK_ASPECT;
}
