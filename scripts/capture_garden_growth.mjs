// Records the garden's own growth animation from the real renderer.
//
//   node scripts/capture_garden_growth.mjs [port] [outDir] [growSeconds]
//
// The HUD is composited afterwards by scripts/hud_frames.py + ffmpeg, so this
// captures the canvas alone: nav and controls are hidden rather than cropped,
// which keeps the tree centred in the frame.
import { chromium } from "./../web/node_modules/playwright/index.mjs";

const port = process.argv[2] ?? "6970";
const outDir = process.argv[3] ?? "/tmp/garden-capture";
const grow = Number(process.argv[4] ?? 14);

const browser = await chromium.launch({
  headless: true,
  args: ["--use-gl=angle", "--use-angle=metal", "--enable-unsafe-swiftshader"],
});
const context = await browser.newContext({
  viewport: { width: 1600, height: 900 },
  recordVideo: { dir: outDir, size: { width: 1600, height: 900 } },
});
const page = await context.newPage();
await page.goto(`http://localhost:${port}/garden`, { waitUntil: "networkidle" });
await page.waitForSelector("canvas");

const dataBtn = page.locator("button", { hasText: /^data trees$/ });
if (!(await dataBtn.getAttribute("class"))?.includes("on")) await dataBtn.click();

// Open the knobs only long enough to lengthen the growth, then close them.
const knobs = page.locator("button", { hasText: /^knobs$/ });
if (!(await knobs.getAttribute("class"))?.includes("on")) await knobs.click();
await page.waitForTimeout(600);
await page.evaluate((seconds) => {
  const row = [...document.querySelectorAll("label, div")].find((el) =>
    /grow time/i.test(el.textContent ?? ""),
  );
  const input = row?.querySelector('input[type="range"]');
  if (!input) return false;
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, String(seconds));
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}, grow);
await page.waitForTimeout(900);
if ((await knobs.getAttribute("class"))?.includes("on")) await knobs.click();

// Hide the chrome so the recording is canvas only.
await page.addStyleTag({
  content: `nav, header, .hub-nav, [class*="controls"], button { opacity: 0 !important; pointer-events: none !important; }
            body { background: #08080a !important; }`,
});

await page.waitForTimeout(15000); // let the first growth settle before framing

const box = await page.locator("canvas").boundingBox();
const cx = box.x + box.width / 2;
const cy = box.y + box.height / 2;
for (let i = 0; i < 4; i += 1) {
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, 240);
  await page.waitForTimeout(120);
}
await page.waitForTimeout(1200);

// Replay from zero, and orbit slowly while it grows.
await page.evaluate(() => {
  const b = [...document.querySelectorAll("button")].find((x) =>
    /replay growth/i.test(x.textContent ?? ""),
  );
  b?.click();
});

const steps = Math.round((grow + 4) * 20);
await page.mouse.move(cx, cy);
await page.mouse.down();
for (let i = 0; i < steps; i += 1) {
  await page.mouse.move(cx + Math.sin(i / steps) * 260, cy - 14 * Math.sin(i / (steps / 2)));
  await page.waitForTimeout(50);
}
await page.mouse.up();
await page.waitForTimeout(1500);

await context.close();
await browser.close();
console.log(`recorded into ${outDir}`);
