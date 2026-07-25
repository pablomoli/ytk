import { Children, isValidElement, useEffect, useMemo, useRef } from "react";
import type { ReactNode } from "react";
import { DUR, Flip, HOUSE_EASE, reducedMotion } from "../lib/motion";
import { columnSpec, computeMasonryLayout } from "../lib/masonry";
import "../styles.css";

const GAP = 12;
const COL_MIN = 190;
const WIDE_RATIO = 1.3;

/* The ordered card keys. This is the layout's real dependency: `children` is a
   fresh array on every parent render, so keying the effect on it re-packed and
   re-tweened the whole grid whenever anything on the page changed — a selection
   toggle, a poll, the inbox's 1s job clock. Only membership and order can change
   the packing, and both are visible here (#22). */
function structuralSignature(children: ReactNode): string {
  return Children.toArray(children)
    .map((child, i) => (isValidElement(child) ? String(child.key) : `#${i}`))
    .join("|");
}

/* A landscape cover means the card should tile two columns wide. Marked on
   the DOM (not React state) so the layout pass can read it synchronously. */
function markWide(img: HTMLImageElement) {
  if (!img.naturalWidth || !img.naturalHeight) return;
  const card = img.closest<HTMLElement>(".card");
  if (!card) return;
  if (img.naturalWidth / img.naturalHeight >= WIDE_RATIO) {
    card.dataset.wide = "1";
  } else {
    delete card.dataset.wide;
  }
}

export function MasonryGrid({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const laidOut = useRef(false);
  const signature = useMemo(() => structuralSignature(children), [children]);

  useEffect(() => {
    const grid = ref.current;
    if (!grid) return;

    let raf = 0;
    let wantsMotion = false;
    const relayout = (animate: boolean) => {
      /* Motion is reserved for structural change. A card growing under a
         late-loading image, or the window resizing, snaps: tweening those
         fights the scroll and the drag. */
      if (animate) wantsMotion = true;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const width = grid.clientWidth;
        if (!width) return;
        const items = [...grid.children].filter(
          (el): el is HTMLElement => el instanceof HTMLElement,
        );
        const motion = wantsMotion && laidOut.current && !reducedMotion();
        wantsMotion = false;
        /* Captured before the sizing pass mutates widths, and discarded below
           if the geometry turns out unchanged. */
        const state = motion ? Flip.getState(items) : null;
        /* Two passes because height depends on width: first size every card
           for its span, then measure and place. Cards are absolutely
           positioned with explicit widths, so offsetHeight reflects content
           at that width and relayout stays idempotent (no ratchet). */
        const { nCols, colW } = columnSpec(width, GAP, COL_MIN);
        items.forEach((el) => {
          const wide = el.dataset.wide === "1" && nCols >= 2;
          el.style.position = "absolute";
          el.style.width = `${wide ? 2 * colW + GAP : colW}px`;
        });
        const boxes = items.map((el) => ({
          height: el.offsetHeight,
          wide: el.dataset.wide === "1",
        }));
        const layout = computeMasonryLayout(boxes, { width, gap: GAP, colMin: COL_MIN });
        /* Compared against what each element is actually wearing, not against
           the previous placement list: a reorder produces the same list of
           positions handed to different cards, and skipping that write would
           leave every card at its predecessor's coordinates. */
        const settled =
          grid.style.height === `${layout.height}px` &&
          items.every(
            (el, i) =>
              el.style.left === `${layout.placed[i].left}px` &&
              el.style.top === `${layout.placed[i].top}px`,
          );
        if (settled) return;
        items.forEach((el, i) => {
          el.style.left = `${layout.placed[i].left}px`;
          el.style.top = `${layout.placed[i].top}px`;
          el.style.width = `${layout.placed[i].width}px`;
        });
        grid.style.height = `${layout.height}px`;
        laidOut.current = true;
        if (state) {
          Flip.from(state, {
            duration: DUR.base,
            ease: HOUSE_EASE,
            overwrite: true,
            onEnter: (els) => els.forEach((el) => ((el as HTMLElement).style.opacity = "1")),
          });
        }
      });
    };

    relayout(true);

    /* Observing the cards as well as the grid is what lets the effect stop
       re-running on every render: anything that changes a card's height —
       image decode, an errored cover falling back to text, a font landing —
       reaches the layout through here instead of through a re-render. */
    const ro = new ResizeObserver(() => relayout(false));
    ro.observe(grid);
    for (const el of grid.children) {
      if (el instanceof HTMLElement) ro.observe(el);
    }

    const onLoad = (e: Event) => {
      markWide(e.target as HTMLImageElement);
      relayout(false);
    };
    const images = [...grid.querySelectorAll("img")];
    images.forEach((img) => {
      if (img.complete) markWide(img);
      img.addEventListener("load", onLoad);
    });

    return () => {
      ro.disconnect();
      images.forEach((img) => img.removeEventListener("load", onLoad));
      if (raf) cancelAnimationFrame(raf);
    };
  }, [signature]);

  return (
    <main ref={ref} className="masonry">
      {children}
    </main>
  );
}
