// Headless render of /garden into docs/assets/, so the screenshot is
// reproducible rather than a one-off. Needs a hub on the given port.
//
//   node scripts/shoot_garden.mjs [port] [out.png] [zoomOutClicks]
//
// Metal ANGLE is requested explicitly: the default headless GL is SwiftShader,
// which renders the same scene correctly but at a tenth the frame rate.
import { chromium } from "./../web/node_modules/playwright/index.mjs";

const port = process.argv[2] ?? "6970";
const out = process.argv[3] ?? "docs/assets/14-garden-allometry/04-first-render.png";
const zoom = Number(process.argv[4] ?? 6);

const browser = await chromium.launch({
  headless: true,
  args: ["--use-gl=angle", "--use-angle=metal", "--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto(`http://localhost:${port}/garden`, { waitUntil: "networkidle" });
await page.waitForSelector("canvas");

const dataBtn = page.locator("button", { hasText: /^data trees$/ });
if (!(await dataBtn.getAttribute("class"))?.includes("on")) await dataBtn.click();
const knobs = page.locator("button", { hasText: /^knobs$/ });
if ((await knobs.getAttribute("class"))?.includes("on")) await knobs.click();

await page.waitForTimeout(13000);

const box = await page.locator("canvas").boundingBox();
for (let i = 0; i < zoom; i += 1) {
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, 240);
  await page.waitForTimeout(90);
}
await page.waitForTimeout(2500);

const renderer = await page.evaluate(() => {
  const gl = document.querySelector("canvas").getContext("webgl2");
  const dbg = gl?.getExtension("WEBGL_debug_renderer_info");
  return dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "unknown";
});

await page.screenshot({ path: out });
console.log(`wrote ${out}\nrenderer: ${renderer}`);
await browser.close();
