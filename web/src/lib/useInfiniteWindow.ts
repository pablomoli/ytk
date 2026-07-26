import { useCallback, useEffect, useRef, useState } from "react";

export const nextCount = (cur: number, total: number, step: number): number =>
  Math.min(cur + step, total);

/* The sentinel is the last thing in the scroll content and has no height of its
   own, so at the end of the scroll it lands exactly on its scroll container's
   clip edge: a zero-area intersection that never reports, and a window that
   never widens. rootMargin cannot rescue that — it grows the root rect, not the
   clip rect of an intermediate scroller — so the scroller itself has to be the
   root. Returns null when nothing above the sentinel scrolls, which is the
   viewport, which is what null means to IntersectionObserver. */
function scrollRoot(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const overflowY = getComputedStyle(node).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") return node;
  }
  return null;
}

export function useInfiniteWindow<T>(items: T[], step = 60, resetKey: unknown = null) {
  const [count, setCount] = useState(step);

  useEffect(() => {
    setCount(step);
  }, [resetKey, step]);

  const obs = useRef<IntersectionObserver | null>(null);

  const sentinelRef = useCallback(
    (el: HTMLElement | null) => {
      obs.current?.disconnect();
      if (!el) return;
      obs.current = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting) {
            setCount((c) => nextCount(c, items.length, step));
          }
        },
        /* A screenful of lead time, so the next page is requested while the
           reader still has one to go rather than at the edge itself. */
        { root: scrollRoot(el), rootMargin: "600px 0px" },
      );
      obs.current.observe(el);
    },
    [items.length, step],
  );

  return { visible: items.slice(0, count), sentinelRef };
}
