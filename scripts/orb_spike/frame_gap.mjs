// Longest gap between drawn frames while the terrain redraws for a change of arrangement.
// Usage: node scripts/orb_spike/frame_gap.mjs [shot-prefix]   (spike server on :8877, headless)
import { chromium } from "../../web/node_modules/playwright/index.mjs";
const b = await chromium.launch({ headless: true, args: ["--use-gl=angle", "--use-angle=metal", "--enable-unsafe-swiftshader"] });
const p = await b.newPage({ viewport: { width: 1100, height: 800 } });
const errs = [];
p.on("console", (m) => { if (m.type() === "error" && !m.text().includes("ERR_FAILED")) errs.push(m.text()); });
p.on("pageerror", (e) => errs.push(String(e)));
await p.route("**/*", (r) => (r.request().method() !== "GET" || r.request().url().includes("/api/cover") ? r.abort() : r.continue()));
await p.goto("http://127.0.0.1:8877/orb");
await p.waitForSelector('[data-orb-view="globe"]');
await p.waitForTimeout(2500);
await p.click('[data-orb-view="globe"]');
await p.click("[data-orb-terrain]");
await p.waitForTimeout(3000);
await p.evaluate(() => {
  const w = window; w.__gaps = []; let last = performance.now();
  const tick = (now) => { w.__gaps.push(now - last); last = now; requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
});
const rows = [];
for (const lens of ["radial", "time", "lattice", "radial", "time", "lattice"]) {
  await p.evaluate(() => { window.__gaps.length = 0; });
  await p.click(`[data-orb-lens="${lens}"]`);
  await p.waitForTimeout(3500);
  const g = await p.evaluate(() => window.__gaps.slice());
  const sorted = [...g].sort((a, c) => a - c);
  if (process.argv[2]) await p.screenshot({ path: `${process.argv[2]}-${rows.length}-${lens}.png` });
  rows.push({ lens, worst: Math.max(...g).toFixed(1), median: sorted[sorted.length >> 1].toFixed(1), frames: g.length });
}
console.table(rows);
console.log("errors", JSON.stringify(errs));
await b.close();
