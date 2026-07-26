/* The sticky stack above the rail is `.hub-nav`'s rendered height plus
   `.hub-body`'s top padding. Neither is a constant: `.hub-nav` wraps its
   eleven links at widths that don't line up with any padding breakpoint,
   so the sum rises and falls non-monotonically as the viewport narrows
   (measured: 102 at 1440-1152, 133 at 1100-1050, back down to 118 at
   1024-980). A static number or a media-query staircase can't encode
   that saw-tooth, so it's measured at runtime instead. */

export function stickyTopPx(navHeight: number, bodyPaddingTop: number): number {
  const nav = Number.isFinite(navHeight) ? Math.max(0, navHeight) : 0;
  const pad = Number.isFinite(bodyPaddingTop) ? Math.max(0, bodyPaddingTop) : 0;
  return Math.round(nav + pad);
}

function readStickyTop(nav: Element, body: Element): number {
  const navHeight = nav.getBoundingClientRect().height;
  const bodyPaddingTop = parseFloat(getComputedStyle(body).paddingTop);
  return stickyTopPx(navHeight, bodyPaddingTop);
}

function applyStickyTop(nav: Element, body: Element): void {
  const value = readStickyTop(nav, body);
  document.documentElement.style.setProperty("--sticky-top", `${value}px`);
}

/* Keeps --sticky-top current as the nav re-wraps or the body's padding
   breakpoint changes. Returns a no-op cleanup when either element is
   absent (e.g. a route rendered outside the hub shell) rather than
   throwing, since this runs unconditionally from the root layout. */
export function observeStickyTop(): () => void {
  const nav = document.querySelector(".hub-nav");
  const body = document.querySelector(".hub-body");
  if (!nav || !body) return () => {};

  const update = () => applyStickyTop(nav, body);
  update();

  if (typeof ResizeObserver === "undefined") {
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }

  const ro = new ResizeObserver(update);
  ro.observe(nav);
  return () => ro.disconnect();
}
