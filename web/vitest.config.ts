import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";

// Vite+ beta's integrated `vp test` is broken (missing vitest bin), and its
// vite.config.ts defineConfig hook crashes upstream vitest. So tests run on
// plain vitest with this isolated config. Invoke with: pnpm exec vitest run
//
// Tests execute in real Chromium, not jsdom (#135). jsdom has no layout
// engine: every element reports 0x0 at the origin, so size, position,
// overflow and visibility are all unobservable, and several native
// behaviours are missing outright. Three real bugs shipped past a fully
// green jsdom suite - prose left blurred and unreadable (#124), an ingest
// button stranded 102px below the fold, and a disclosure section that
// ignored its first click (#125) - because each needed real layout or a real
// native behaviour to be visible at all.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    browser: {
      enabled: true,
      provider: playwright(),
      headless: true,
      instances: [{ browser: "chromium" }],
    },
  },
});
