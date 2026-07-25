import { useEffect, useRef } from "react";
import { reducedMotion } from "../lib/motion";
import { BAYER8 } from "../lib/bayer";

const CELL = 14;
const BLOOM_MS = 260;
const FADE_MS = 220;

/* Canvas hover effect: cells bloom center-out from the pointer's entry
   point and recede on leave — the growth dither at interaction scale.
   Pure rAF; the loop only runs while animating. Colors are read from the
   theme at effect start. */
export function PixelBloom() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = canvas?.parentElement;
    if (!canvas || !host || reducedMotion()) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    let raf = 0;
    let start = 0;
    let dir: 1 | -1 = 1;
    let origin = { x: 0.5, y: 0.5 };
    let level = 0; // 0 = clear, 1 = fully bloomed

    const draw = (now: number) => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const w = host.clientWidth,
        h = host.clientHeight;
      if (canvas.width !== w * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      const t = Math.min(1, (now - start) / (dir === 1 ? BLOOM_MS : FADE_MS));
      level = dir === 1 ? t : 1 - t;
      context.clearRect(0, 0, canvas.width, canvas.height);
      const accent =
        getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#e2b04a";
      const cols = Math.ceil(w / CELL),
        rows = Math.ceil(h / CELL);
      const maxDist = Math.hypot(
        Math.max(origin.x, 1 - origin.x) * w,
        Math.max(origin.y, 1 - origin.y) * h,
      );
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          const cx = (x + 0.5) * CELL,
            cy = (y + 0.5) * CELL;
          const dist = Math.hypot(cx - origin.x * w, cy - origin.y * h) / maxDist;
          const threshold = dist * 0.75 + (BAYER8[y % 8][x % 8] / 64) * 0.25;
          if (threshold < level) {
            context.globalAlpha = 0.14 * Math.min(1, (level - threshold) * 6);
            context.fillStyle = accent;
            context.fillRect(x * CELL * dpr, y * CELL * dpr, (CELL - 2) * dpr, (CELL - 2) * dpr);
          }
        }
      }
      context.globalAlpha = 1;
      if (t < 1) raf = requestAnimationFrame(draw);
      else if (dir === -1) context.clearRect(0, 0, canvas.width, canvas.height);
    };

    const begin = (nextDir: 1 | -1, event?: MouseEvent) => {
      if (event) {
        const rect = host.getBoundingClientRect();
        origin = {
          x: (event.clientX - rect.left) / rect.width,
          y: (event.clientY - rect.top) / rect.height,
        };
      }
      dir = nextDir;
      start = performance.now();
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(draw);
    };

    const enter = (e: MouseEvent) => begin(1, e);
    const leave = () => begin(-1);
    host.addEventListener("mouseenter", enter);
    host.addEventListener("mouseleave", leave);
    return () => {
      host.removeEventListener("mouseenter", enter);
      host.removeEventListener("mouseleave", leave);
      cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={canvasRef} className="pixel-bloom" aria-hidden="true" />;
}
