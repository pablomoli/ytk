import { useEffect, useMemo, useRef, useState } from "react";
import { DUR, reducedMotion } from "../lib/motion";
import { ditherOrder, hashString } from "../lib/bayer";

/* A cover that dissolves in seeded Bayer order: the growth renderer's
   dither language extended to DOM surfaces. CSS transitions carry the
   per-cell fade; JS only assigns the per-cell delay from the order. */
export function PixelDissolve({
  seedKey,
  cell = 28,
  color = "var(--bg1)",
  onDone,
}: {
  seedKey: string;
  cell?: number;
  color?: string;
  onDone?: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [grid, setGrid] = useState<{ cols: number; rows: number } | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (reducedMotion()) {
      setGone(true);
      onDone?.();
      return;
    }
    const cols = Math.max(1, Math.round((host.clientWidth || cell) / cell));
    const rows = Math.max(1, Math.round((host.clientHeight || cell) / cell));
    setGrid({ cols, rows });
    const id = setTimeout(
      () => {
        setGone(true);
        onDone?.();
      },
      DUR.reveal * 1000 + 80,
    );
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey]);

  const delays = useMemo(() => {
    if (!grid) return [];
    const order = ditherOrder(grid.cols, grid.rows, hashString(seedKey));
    const delayByCell = new Array<number>(order.length);
    order.forEach((cellIndex, rank) => {
      delayByCell[cellIndex] = (rank / order.length) * (DUR.reveal - 0.12);
    });
    return delayByCell;
  }, [grid, seedKey]);

  if (gone || !grid)
    return gone ? null : (
      <div
        ref={hostRef}
        className="pixel-dissolve"
        style={{ background: color }}
        aria-hidden="true"
      />
    );

  return (
    <div
      ref={hostRef}
      className="pixel-dissolve on"
      aria-hidden="true"
      style={{
        gridTemplateColumns: `repeat(${grid.cols}, 1fr)`,
        gridTemplateRows: `repeat(${grid.rows}, 1fr)`,
      }}
    >
      {delays.map((delay, i) => (
        <i key={i} style={{ background: color, transitionDelay: `${delay}s` }} />
      ))}
    </div>
  );
}
