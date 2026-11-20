// Headless stills of the orb spike: inside, globe, and the globe at the dial's atom and coil stops.
// node scripts/orb_spike/shoot.mjs <outdir>. Never opens the inbox: the newest pending items are private notes.
import { chromium } from "../../web/node_modules/playwright/index.mjs";
import { mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
const out = process.argv[2];
mkdirSync(out, { recursive: true });
const ring = JSON.parse(readFileSync(`${homedir()}/.ytk/orb-spike/ring.json`, "utf8")).items;
const cached = new Set(ring.filter((r) => r.k >= 0).map((r) => r.u));
const browser = await chromium.launch({ headless: true, args: ["--use-gl=angle", "--use-angle=metal", "--enable-unsafe-swiftshader"] });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })).newPage();
const errors = [], writes = [];
page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("ERR_FAILED")) errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
await page.route("**/*", (r) => {
  const q = r.request(), u = new URL(q.url());
  if (q.method() !== "GET") { writes.push(`${q.method()} ${u.pathname}`); return r.abort(); }
  // an uncached cover would make the hub download it
  if (u.pathname === "/api/cover" && !cached.has(u.searchParams.get("u"))) return r.abort();
  return r.continue();
});
await page.goto("http://localhost:8877/orb", { waitUntil: "networkidle" });
await page.waitForSelector("canvas");
await page.waitForTimeout(8000);
await page.mouse.move(720, 880);
await page.screenshot({ path: `${out}/1-inside.png` });
await page.locator('[data-orb-view="globe"]').click();
await page.waitForTimeout(4500);
await page.screenshot({ path: `${out}/2-globe-ring.png` });
const dial = page.locator('[role="slider"][aria-label="orb state"]');
for (const [name, ticks] of [["3-globe-atom", 10], ["4-globe-coil", 10]]) {
  await dial.focus();
  for (let i = 0; i < ticks; i++) { await page.keyboard.press("ArrowRight"); await page.waitForTimeout(60); }
  await page.waitForTimeout(4500);
  await page.screenshot({ path: `${out}/${name}.png` });
}
console.log("writes:", writes, "errors:", errors.length ? errors : "none");
await browser.close();
